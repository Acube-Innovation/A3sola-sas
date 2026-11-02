# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What the partner roles may do on ERPNext's own doctypes. Idempotent; run on every migrate.

The app's doctypes carry the Solar Dealer and Solar Contractor Partner rows in their JSON.
Lead, Customer and Quotation belong to ERPNext, so their grants are Custom DocPerms - and the
copy first is not optional: the moment a doctype has any Custom DocPerm, Frappe stops reading
its standard ones (as install_projects.grant_project_financial_access explains).

Which records a partner sees is api/partner_scope's business, not this one's.
"""

import frappe

from a3_sola.api.partner_scope import DEALER

#: doctype -> rights at permlevel 0. Nothing on bills, payments, stock or costing.
DEALER_GRANTS = {
	"Lead": {"read": 1, "write": 1, "create": 1, "print": 1},
	"Customer": {"read": 1, "write": 1, "create": 1, "print": 1},
	"Quotation": {"read": 1, "write": 1, "create": 1, "submit": 1, "print": 1},
}


def setup():
	from frappe.permissions import setup_custom_perms

	if not frappe.db.exists("Role", DEALER):
		return
	for doctype, rights in DEALER_GRANTS.items():
		setup_custom_perms(doctype)
		name = frappe.db.get_value("Custom DocPerm", {"parent": doctype, "role": DEALER, "permlevel": 0})
		if name:
			frappe.db.set_value("Custom DocPerm", name, rights)
		else:
			frappe.get_doc({"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType",
				"parentfield": "permissions", "role": DEALER, "permlevel": 0, **rights}).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)
