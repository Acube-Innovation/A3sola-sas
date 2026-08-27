# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Roles and role profiles for the Solar CRM module.

The permission matrix itself lives on each doctype JSON. This module only guarantees the
roles exist before those permissions are applied, and bundles them into role profiles.

Commercial fields on Solar Design Estimate sit at permlevel 1 and the consumer's bank
details at permlevel 2, so a Survey Engineer sees no cost anywhere and no technician sees
a customer's account number.
"""

import frappe

ROLES = [
	("Solar Sales Executive", "Takes an enquiry through the outreach cadence to a proposal and a quotation."),
	("Solar Survey Engineer", "Completes site surveys including the lender EHS block. Sees no commercial figure."),
	("Solar Design Engineer", "Owns design estimates and eligibility checks."),
	("Solar Sales Manager", "Approves designs, waives eligibility rules, sees commercials."),
	("Solar CRM Manager", "Full access including master data and settings."),
]

ROLE_PROFILES = {
	"Solar Sales": ["Solar Sales Executive", "Sales User", "Employee"],
	"Solar Survey": ["Solar Survey Engineer", "Employee"],
	"Solar Design": ["Solar Design Engineer", "Employee"],
	"Solar Sales Management": ["Solar Sales Manager", "Solar Sales Executive", "Sales Manager", "Employee"],
	"Solar CRM Administration": ["Solar CRM Manager", "Solar Sales Manager", "Sales Manager", "Employee"],
}


def create_roles():
	"""Create every role and role profile this module needs. Idempotent."""
	for role, description in ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
				"is_custom": 1,
				"search_bar": 1,
				"notifications": 1,
				"list_sidebar": 1,
				"bulk_actions": 1,
				"form_sidebar": 1,
				"timeline": 1,
				"dashboard": 1,
			}
		).insert(ignore_permissions=True)

	for profile, roles in ROLE_PROFILES.items():
		available = [r for r in roles if frappe.db.exists("Role", r)]
		if not available:
			continue
		if frappe.db.exists("Role Profile", profile):
			doc = frappe.get_doc("Role Profile", profile)
			existing = {r.role for r in doc.roles}
			added = False
			for role in available:
				if role not in existing:
					doc.append("roles", {"role": role})
					added = True
			if added:
				doc.save(ignore_permissions=True)
			continue
		frappe.get_doc(
			{
				"doctype": "Role Profile",
				"role_profile": profile,
				"roles": [{"role": r} for r in available],
			}
		).insert(ignore_permissions=True)
