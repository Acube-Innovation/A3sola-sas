# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""An audit entry that cannot be quietly rewritten.

Frappe's version history is good, but it lives in a table an administrator can edit and
it records the change rather than the intent. What an auditor asks about a refund is not
"which field moved" but "who decided this, and what did they say the reason was" - so
that is what an entry holds, and it holds it in a form that resists being edited later.

Immutability here is enforced twice, because either alone is weak:

  * At the document layer, update and delete are refused outright. No role gets past it,
    including Administrator, because the point of the record is that the person with the
    most power is also the person most worth recording.
  * At the data layer, each entry carries a SHA-256 over its own content chained to the
    hash of the entry before it. Editing a row directly in MariaDB - which bypasses this
    controller entirely - breaks the chain from that row onward, and the break can be
    found by anyone who runs the verifier.

The chain does not stop a determined attacker with database access from rewriting every
subsequent hash too. It is not meant to. It converts silent tampering into work that
leaves traces, which is the honest claim to make for it.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.model.document import Document

#: Fields whose values decide the hash. Deliberately excludes `modified` and the chain
#: fields themselves, so the hash covers what was asserted and not the bookkeeping.
HASHED_FIELDS = (
	"entry_type",
	"subject",
	"occurred_on",
	"actor",
	"reference_doctype",
	"reference_name",
	"platform_subscription",
	"amount",
	"currency",
	"reason",
	"changed_field",
	"value_before",
	"value_after",
	"detail",
)


class PlatformAuditEntry(Document):
	def before_insert(self):
		self.occurred_on = self.occurred_on or frappe.utils.now_datetime()
		self.actor = self.actor or frappe.session.user
		if not self.actor_roles:
			# The whole list, not a slice. Which roles somebody held at the moment they
			# did something is exactly what gets asked about afterwards, and a truncated
			# list is the one that drops the role that mattered.
			self.actor_roles = ", ".join(sorted(frappe.get_roles(self.actor)))
		self._link_to_chain()
		self.entry_hash = self.compute_hash()

	def _link_to_chain(self):
		previous = frappe.db.sql(
			"""SELECT name, entry_hash, chain_index
			   FROM `tabPlatform Audit Entry`
			   ORDER BY chain_index DESC, creation DESC LIMIT 1""",
			as_dict=True,
		)
		if previous:
			self.previous_entry = previous[0].name
			self.chain_index = (previous[0].chain_index or 0) + 1
		else:
			self.previous_entry = None
			self.chain_index = 1

	def compute_hash(self):
		previous_hash = ""
		if self.previous_entry:
			previous_hash = frappe.db.get_value(
				"Platform Audit Entry", self.previous_entry, "entry_hash"
			) or ""
		payload = {field: _canonical(self.get(field)) for field in HASHED_FIELDS}
		payload["previous_hash"] = previous_hash
		payload["chain_index"] = self.chain_index
		body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
		return hashlib.sha256(body.encode("utf-8")).hexdigest()

	def on_update(self):
		# `on_update` fires for the insert too, and by then the document is no longer new
		# - `flags.in_insert` is the only reliable way to tell the two apart.
		if self.flags.in_insert:
			return
		frappe.throw(
			_("An audit entry cannot be changed once it is written."),
			title=_("Audit entries are permanent"),
		)

	def on_trash(self):
		frappe.throw(
			_("An audit entry cannot be deleted. If it was written in error, write a "
			  "correcting entry saying so."),
			title=_("Audit entries are permanent"),
		)


def _canonical(value):
	"""One string per value, identical whether it came from memory or from the database.

	This is the whole difficulty of a hash chain over a Frappe document. The same field
	is a `datetime` in memory and a `datetime` from the database but a string from a raw
	query; a Currency is `None` on a fresh document and `0.0` once stored; a Decimal and a
	float that are numerically equal must not hash differently. Every one of those has to
	collapse to the same text or the chain reports a break that never happened.
	"""
	import datetime
	from decimal import Decimal

	if value is None or value == "":
		return ""
	if isinstance(value, bool):
		return "1" if value else "0"
	if isinstance(value, (int, float, Decimal)):
		return f"{float(value):.6f}"
	if isinstance(value, (datetime.datetime, datetime.date)):
		return value.isoformat(sep=" ")
	return str(value)


def verify_chain(limit=None):
	"""Re-hash every entry in order and report the first break, if any.

	Returns a dict rather than throwing, because this is called both from a scheduled
	check (which wants to alert) and from the desk (which wants to display).
	"""
	rows = frappe.get_all(
		"Platform Audit Entry",
		fields=["name", "chain_index", "entry_hash", "previous_entry"] + list(HASHED_FIELDS),
		order_by="chain_index asc, creation asc",
		limit_page_length=limit or 0,
	)
	previous_hash = ""
	broken = []
	for row in rows:
		payload = {field: _canonical(row.get(field)) for field in HASHED_FIELDS}
		payload["previous_hash"] = previous_hash
		payload["chain_index"] = row.chain_index
		body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
		expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
		if expected != (row.entry_hash or ""):
			broken.append(row.name)
		# Continue from what is stored, not from what was expected, so one altered row
		# is reported once instead of invalidating everything after it.
		previous_hash = row.entry_hash or ""
	return {
		"checked": len(rows),
		"intact": not broken,
		"first_break": broken[0] if broken else None,
		"broken": broken,
	}


def alert_on_broken_audit_chain():
	"""Daily. Silence here is the expected state; noise means someone edited the table."""
	result = verify_chain()
	if result["intact"] or not result["checked"]:
		return result
	frappe.log_error(
		title="a3_sola: audit chain broken",
		message=(
			f"{len(result['broken'])} audit entries no longer match their own hash. "
			f"First break at {result['first_break']}. This means rows were changed "
			f"outside the application. Entries: {', '.join(result['broken'][:50])}"
		),
	)
	return result
