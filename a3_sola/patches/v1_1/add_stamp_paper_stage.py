# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Insert the stamp paper stage into templates and in-flight installations.

The agreement is written on stamp paper that somebody has to go and buy, and until now
that errand lived in nobody's queue: the chain jumped from the order straight to the
portal application, and the paper turned up - or didn't - on the day of execution.

STMP sits immediately after ORD, right behind the customer's advance, because that advance
is what pays for the paper. It is a status and a serial number and nothing else, which is
why it carries no document checklist: there is no evidence to upload, only a fact to record.

Seeding skips templates that already exist, so this reaches the tenants who installed
before the stage existed. It touches:

* every stage template whose chain contains ORD but not STMP;
* every installation not yet past ORD, since one already at the portal has either bought
  the paper or does not need reminding.

An installation past ORD is left alone. Backfilling a pending stage behind a completed one
would reopen a chain the site has already moved on from, and the progress figures with it.
"""

import frappe
from frappe.utils import add_days, getdate

#: The stage as the template holds it. The stage log keeps a subset of these - it records
#: what happened, not what was configured - so each row is filtered to its own fields.
STAGE = {
	"stage_code": "STMP",
	"stage_name": "Stamp Paper Purchased",
	"owner_type": "Internal",
	"sla_days": 3,
	"is_mandatory": 1,
	"applicability": "Always",
	"applicability_threshold_kw": 0,
	"requires_document": 0,
	"document_checklist_template": None,
	"stage_description": (
		"Status only - no document is uploaded here. The agreement itself is generated "
		"from this stage onward and is filed at AGMT"
	),
}

#: Stages that mean the chain has moved past the point where buying paper is news.
DONE = ("Completed", "Skipped")


def execute():
	if not frappe.db.exists("DocType", "Installation Stage Template"):
		return None
	counts = {"templates": 0, "installations": 0}

	for name in frappe.get_all("Installation Stage Template", pluck="name"):
		if _insert_into(frappe.get_doc("Installation Stage Template", name)):
			counts["templates"] += 1

	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		doc = frappe.get_doc("Solar Installation", name)
		if _order_is_done(doc):
			continue
		if _insert_into(doc):
			counts["installations"] += 1

	frappe.db.commit()
	print(
		f"a3_sola: STMP added to {counts['templates']} templates, "
		f"{counts['installations']} installations"
	)
	return counts


def _order_is_done(installation):
	return any(row.stage_code == "ORD" and row.status in DONE for row in installation.stages)


def _insert_into(doc):
	"""Put STMP straight after ORD and renumber, leaving every other row untouched."""
	codes = [row.stage_code for row in doc.stages]
	if "STMP" in codes or "ORD" not in codes:
		return False

	position = codes.index("ORD") + 1
	row = frappe.new_doc(doc.stages[0].doctype)
	row.parent, row.parenttype, row.parentfield = doc.name, doc.doctype, "stages"
	for field, value in STAGE.items():
		if row.meta.has_field(field):
			row.set(field, value)
	if row.meta.has_field("status"):
		row.status = "Pending"
	if row.meta.has_field("planned_date"):
		row.planned_date = _planned_from(doc.stages[position - 1])

	doc.stages.insert(position, row)
	for index, existing in enumerate(doc.stages, start=1):
		existing.idx = index
		if existing.meta.has_field("display_order"):
			existing.display_order = index

	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return True


def _planned_from(order_row):
	"""Three days after the order was due; blank if the order itself has no date."""
	anchor = getattr(order_row, "actual_completion_date", None) or getattr(
		order_row, "planned_date", None
	)
	return add_days(getdate(anchor), STAGE["sla_days"]) if anchor else None
