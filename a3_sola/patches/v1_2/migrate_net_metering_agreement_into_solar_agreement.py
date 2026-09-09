# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every executed Net Metering Agreement becomes a Solar Agreement.

The two doctypes described the same instrument: the KSEB agreement on stamp paper with its
three schedules. The Solar Agreement is the one that generates its text and carries the
stamp-paper task, so it is the one that stays. Each submitted Net Metering Agreement whose
installation has no live Solar Agreement is copied across field for field, the text is
rendered, and the copy is executed when it passes the same gates a hand-made one must
(stamp paper, text, SPIN); otherwise it is left as a draft with a comment saying why.

Nothing is deleted. The old records stay read-only, cross-referenced by comment, until the
user has checked the copies and asks for the retirement patch that removes them.
"""

import frappe
from frappe import _

COMMON = (
	"solar_installation", "solar_consumer", "commissioning_report", "agreement_date",
	"place_of_execution", "validity_years", "discom_representative_name", "stamp_paper_value",
	"stamp_paper_serial", "signed_agreement", "consumer_name", "permanent_address",
	"consumer_number_and_category", "supply_voltage", "connected_load_or_contract_demand",
	"installation_address", "spin", "plant_capacity_kwp", "electrical_section", "solar_meter_type",
	"solar_meter_number", "solar_meter_make", "solar_meter_initial_reading",
	"distribution_transformer_details", "local_body_type", "local_body_name", "village",
	"survey_number", "gps_coordinates", "solar_meter_calibration_certificate", "ht_feeder_details",
	"is_terminated", "terminated_on", "terminated_by", "termination_reason",
)
RENAMED = {"witness_1_name": "first_party_witness_1", "witness_2_name": "first_party_witness_2"}
CHILD_SKIP = {"name", "parent", "parentfield", "parenttype", "idx", "docstatus", "creation", "modified",
              "modified_by", "owner", "doctype"}


def execute():
	if not frappe.db.exists("DocType", "Net Metering Agreement"):
		return None
	frappe.reload_doc("solar_operations", "doctype", "solar_agreement")
	result = run()
	frappe.db.commit()
	print(
		f"a3_sola: {result['migrated']} net metering agreement(s) migrated into solar agreements "
		f"({result['executed']} executed, {result['skipped']} skipped)"
	)
	return result


def run():
	"""Migrate every candidate; safe to call again - a migrated record is never copied twice."""
	migrated = executed = skipped = 0
	# Terminated ones first: a live one must not be refused because its predecessor exists.
	for name in frappe.get_all(
		"Net Metering Agreement", filters={"docstatus": 1}, pluck="name", order_by="is_terminated desc, creation asc"
	):
		if frappe.db.exists("Solar Agreement", {"migrated_from": name}):
			continue
		nma = frappe.get_doc("Net Metering Agreement", name)
		if not nma.is_terminated and frappe.db.exists(
			"Solar Agreement", {"solar_installation": nma.solar_installation, "docstatus": 1, "is_terminated": 0}
		):
			if not _already_noted(name):
				skipped += 1
				nma.add_comment("Comment", NOT_MIGRATED)
			continue
		frappe.db.savepoint("a3s_nma")
		try:
			doc = migrate_one(nma)
			migrated += 1
			executed += 1 if doc.docstatus == 1 else 0
		except Exception:
			frappe.db.rollback(save_point="a3s_nma")
			skipped += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: net metering agreement {name} not migrated")
	return {"migrated": migrated, "executed": executed, "skipped": skipped}


NOT_MIGRATED = "Not migrated: the installation already has an executed Solar Agreement."


def _already_noted(name):
	return bool(
		frappe.db.exists(
			"Comment",
			{"reference_doctype": "Net Metering Agreement", "reference_name": name, "comment_type": "Comment",
			 "content": NOT_MIGRATED},
		)
	)


def migrate_one(nma):
	from a3_sola.api import agreement as builder

	doc = frappe.new_doc("Solar Agreement")
	for field in COMMON:
		if nma.get(field) not in (None, ""):
			doc.set(field, nma.get(field))
	for old, new in RENAMED.items():
		if nma.get(old):
			doc.set(new, nma.get(old))
	doc.company = nma.company
	doc.stamp_paper_status = "Purchased"
	doc.stamp_paper_purchased_on = nma.agreement_date or frappe.utils.getdate(nma.creation)
	doc.migrated_from = nma.name
	for row in nma.get("wheeling_preferences") or []:
		doc.append("wheeling_preferences", {k: v for k, v in row.as_dict().items() if k not in CHILD_SKIP})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)

	left_as_draft = None
	try:
		builder.generate(doc.name, force=1)
		doc.reload()
		doc.flags.ignore_permissions = True
		doc.submit()
	except Exception as exc:
		left_as_draft = str(exc)
	doc.reload()
	if left_as_draft:
		doc.add_comment(
			"Comment",
			_("Migrated from Net Metering Agreement {0} but left as a draft: {1}").format(nma.name, left_as_draft),
		)
	else:
		doc.add_comment("Comment", _("Migrated from Net Metering Agreement {0}.").format(nma.name))
	nma.add_comment(
		"Comment",
		_("Migrated to Solar Agreement {0}. This record is retired and read-only.").format(
			frappe.utils.get_link_to_form("Solar Agreement", doc.name)
		),
	)
	return doc
