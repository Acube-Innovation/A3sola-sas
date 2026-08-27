# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The three entity roles every outgoing document depends on.

The entity that issues the proposal and receives the money (the EPC) is not always the
entity registered as the vendor on the national portal and named on DISCOM and bank
paperwork. The client's own documents name both on the same page - their bank completion
report carries the registered vendor's details and the EPC's e-mail, and their loan
covering letter directs payment to the EPC's account.

Modelling all three separately is what makes it possible to generate the proposal, the
portal submission and the bank letters from one record.
"""

import frappe
from frappe import _

SECTIONS = {
	_("Registered Portal Vendor"): [
		"registered_vendor_name",
		"registered_vendor_address",
		"mnre_vendor_registration_no",
	],
	_("Executing EPC"): ["epc_name", "epc_address", "epc_contact_no"],
	_("Payee Bank"): [
		"payee_legal_name",
		"payee_bank_name",
		"payee_bank_account_no",
		"payee_bank_ifsc",
	],
}


def validate(doc, method=None):
	"""A half-filled bank block on a covering letter is a payment sent to nowhere."""
	for label, fields in SECTIONS.items():
		values = {f: (doc.get(f) or "").strip() if isinstance(doc.get(f), str) else doc.get(f) for f in fields}
		filled = [f for f, v in values.items() if v]
		if not filled or len(filled) == len(fields):
			continue
		missing = [f for f in fields if not values.get(f)]
		labels = [frappe.get_meta("Company").get_label(f) or f for f in missing]
		frappe.throw(
			_("The {0} block is partly filled. Complete it or clear it - missing: {1}.").format(
				frappe.bold(label), ", ".join(labels)
			),
			title=_("Incomplete Entity Block"),
		)


@frappe.whitelist()
def copy_from_company(company):
	"""Fill all three blocks from the standard Company fields.

	For a tenant that is a single entity playing all three roles, this is the whole setup.
	"""
	doc = frappe.get_doc("Company", company)
	doc.check_permission("write")

	address = frappe.db.get_value(
		"Address",
		{"link_doctype": "Company", "link_name": company},
		["address_line1", "address_line2", "city", "state", "pincode"],
		as_dict=True,
	)
	address_text = ""
	if address:
		address_text = ", ".join(
			str(v) for v in [address.address_line1, address.address_line2, address.city, address.state, address.pincode] if v
		)

	updates = {
		"registered_vendor_name": doc.company_name,
		"registered_vendor_address": address_text,
		"epc_name": doc.company_name,
		"epc_address": address_text,
		"epc_email": doc.email,
		"epc_contact_no": doc.phone_no,
		"payee_legal_name": doc.company_name,
		"payee_pan": doc.get("pan_details") or doc.get("tax_id"),
	}
	bank = frappe.db.get_value(
		"Bank Account", {"company": company, "is_default": 1}, ["bank", "bank_account_no", "branch_code"], as_dict=True
	)
	if bank:
		updates.update(
			{
				"payee_bank_name": bank.bank,
				"payee_bank_account_no": bank.bank_account_no,
				"payee_bank_ifsc": bank.branch_code,
			}
		)

	for field, value in updates.items():
		if value and not doc.get(field):
			doc.set(field, value)
	doc.save(ignore_permissions=True)
	return updates
