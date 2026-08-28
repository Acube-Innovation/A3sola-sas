# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Writing to the audit trail.

Every consequential money action funnels through `record()`. It is deliberately the only
way in: callers do not build the document themselves, so nobody can accidentally write an
entry that skips the hash chain or forgets who did it.

Two rules that shaped this module:

  * **An audit entry must never be the reason a legitimate action fails.** If the trail
    itself breaks, the refund still goes through and the failure is logged loudly. An
    audit system that can block payments becomes an outage waiting to happen, and the
    first thing anyone would do in that outage is switch it off.
  * **Secrets never enter the trail.** When a credential changes, the entry records that
    it changed and by whom - never the old or new value, not even truncated. A trail that
    quietly accumulates API keys is a worse liability than no trail at all.
"""

import frappe
from frappe.utils import flt

DOCTYPE = "Platform Audit Entry"

#: What a change to any of these means, said in the entry rather than left to the reader.
CREDENTIAL_FIELDS = {
	"razorpay_key_id": "Razorpay key id",
	"razorpay_key_secret": "Razorpay key secret",
	"razorpay_webhook_secret": "Razorpay webhook secret",
	"razorpay_account_id": "Razorpay account id",
	"captcha_secret_key": "Captcha secret key",
}

#: Settings that carry a compliance obligation. Moving one is worth a permanent record
#: even though it is a perfectly ordinary configuration change.
COMPLIANCE_FIELDS = {
	"gateway_mode": "Gateway mode",
	"payment_gateway": "Payment gateway",
	"afa_free_debit_ceiling": "AFA-free debit ceiling",
	"pre_debit_notice_hours": "Pre-debit notice hours",
	"refund_approval_threshold": "Refund approval threshold",
	"enable_accounting_postings": "Project postings to the ledger",
	"enable_payment_postings": "Payment postings to the ledger",
}


def record(
	entry_type,
	subject,
	reference_doctype=None,
	reference_name=None,
	reason=None,
	amount=None,
	platform_subscription=None,
	changed_field=None,
	value_before=None,
	value_after=None,
	detail=None,
	actor=None,
):
	"""Append one entry. Returns the entry name, or None if the trail could not be written.

	Never raises. See the module docstring for why.
	"""
	try:
		entry = frappe.new_doc(DOCTYPE)
		entry.update(
			{
				"entry_type": entry_type,
				"subject": (subject or entry_type)[:140],
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"platform_subscription": platform_subscription,
				"reason": reason,
				# Always a number, never None. The hash is recomputed from what the
				# database returns, and a Currency column reads back as 0.0 where the
				# document held None - which would break the chain on every entry that
				# names no amount.
				"amount": flt(amount),
				"changed_field": changed_field,
				"value_before": _stringify(value_before),
				"value_after": _stringify(value_after),
				"detail": detail,
				"actor": actor or frappe.session.user,
				"source_ip": _source_ip(),
			}
		)
		entry.insert(ignore_permissions=True)
		return entry.name
	except Exception:
		frappe.log_error(
			title="a3_sola: audit entry could not be written",
			message=(
				f"Entry type {entry_type!r} for {reference_doctype} {reference_name}.\n"
				f"The action itself was NOT blocked.\n\n{frappe.get_traceback()}"
			),
		)
		return None


def record_settings_change(doc):
	"""Called from the settings controller's validate. Writes one entry per changed field.

	Reads the stored values with a direct query rather than `get_doc_before_save`, which
	returns the in-memory copy for a Single and would compare a document to itself.
	"""
	if doc.is_new():
		return
	before = frappe.db.get_singles_dict(doc.doctype) or {}
	for fieldname, label in CREDENTIAL_FIELDS.items():
		if not doc.meta.has_field(fieldname):
			continue
		old, new = before.get(fieldname), doc.get(fieldname)
		if _same_secret(old, new):
			continue
		record(
			"Gateway Credentials Changed",
			f"{label} was changed",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			changed_field=fieldname,
			# The values themselves are never recorded - only whether one was in place.
			value_before="(was set)" if old else "(was empty)",
			value_after="(now set)" if new else "(now cleared)",
			detail=(
				"The credential value is deliberately not stored in this entry. What is "
				"recorded is that it moved, when, and who moved it."
			),
		)
	for fieldname, label in COMPLIANCE_FIELDS.items():
		if not doc.meta.has_field(fieldname):
			continue
		old, new = before.get(fieldname), doc.get(fieldname)
		if _same_value(old, new):
			continue
		entry_type = (
			"Gateway Mode Changed" if fieldname == "gateway_mode" else "Compliance Setting Changed"
		)
		record(
			entry_type,
			f"{label}: {_stringify(old) or '(empty)'} to {_stringify(new) or '(empty)'}",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			changed_field=fieldname,
			value_before=old,
			value_after=new,
		)


def _same_secret(old, new):
	"""A Password field reads back as the decrypted value, or as `***` when untouched."""
	if new in (None, "", "*" * len(new or "")) and old:
		return True
	return (old or "") == (new or "")


def _same_value(old, new):
	if isinstance(old, (int, float)) or isinstance(new, (int, float)):
		try:
			return flt(old, 6) == flt(new, 6)
		except (TypeError, ValueError):
			pass
	return (old if old is not None else "") == (new if new is not None else "")


def _stringify(value):
	if value is None:
		return None
	if isinstance(value, bool):
		return "Yes" if value else "No"
	return str(value)[:500]


def _source_ip():
	try:
		return frappe.local.request_ip
	except Exception:
		return None


@frappe.whitelist()
def verify():
	"""Desk-callable chain check. Read access to the trail is enough to run it."""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	from a3_sola.platform.doctype.platform_audit_entry.platform_audit_entry import verify_chain

	return verify_chain()


def trail_for(reference_doctype, reference_name, limit=50):
	"""Everything recorded about one record, newest first."""
	return frappe.get_all(
		DOCTYPE,
		filters={"reference_doctype": reference_doctype, "reference_name": reference_name},
		fields=["name", "entry_type", "subject", "occurred_on", "actor", "reason", "amount"],
		order_by="creation desc",
		limit_page_length=limit,
	)
