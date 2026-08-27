# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Statutory fee recovery, on the Projects side.

Operations records what was paid to the DISCOM; Projects tracks what comes back - the
reimbursement from the customer and the 80% refund from the DISCOM. Both are real money
and neither was tracked anywhere before.
"""

import frappe
from frappe.utils import flt


def sync_from_payment(payment, project):
	"""Create or update the recovery record for a statutory fee payment. Idempotent."""
	existing = frappe.db.get_value(
		"Statutory Fee Recovery",
		{"statutory_fee_payment": payment.name, "docstatus": ["<", 2]},
		"name",
	)
	values = {
		"fees_paid_by_company": flt(payment.amount_gross)
		if payment.paid_by == "Company on Behalf of Customer"
		else 0,
		"reimbursed_amount": flt(payment.reimbursed_amount),
		"refund_expected": flt(payment.refundable_amount),
		"refund_received": flt(payment.refund_received_amount),
	}

	if existing:
		doc = frappe.get_doc("Statutory Fee Recovery", existing)
		doc.update(values)
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
		return doc.name

	doc = frappe.get_doc(
		{
			"doctype": "Statutory Fee Recovery",
			"company": payment.company,
			"project": project,
			"solar_installation": payment.solar_installation,
			"customer": frappe.db.get_value("Solar Installation", payment.solar_installation, "customer"),
			"statutory_fee_payment": payment.name,
			**values,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def backfill_for_project(project, installation):
	"""Catch up every fee already paid before the project existed.

	Statutory fees are paid at application and registration - months before commissioning
	creates the project - so at the moment they were recorded there was nothing to attach a
	recovery to. Without this they would never be tracked at all.
	"""
	payments = frappe.get_all(
		"Statutory Fee Payment",
		filters={"solar_installation": installation, "docstatus": 1},
		pluck="name",
	)
	created = []
	for name in payments:
		try:
			created.append(sync_from_payment(frappe.get_doc("Statutory Fee Payment", name), project))
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: recovery backfill {name}")
	return [name for name in created if name]
