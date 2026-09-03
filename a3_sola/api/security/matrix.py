# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every doctype against every role, generated so it cannot drift from reality.

A permission matrix written by hand is a description of what somebody intended. This one
is read from the doctypes, so it is a description of what is actually true - and the
checks below turn the four rules that matter into assertions rather than observations.
"""

import frappe

from a3_sola.api.entitlements import INTERNAL_PLATFORM_ROLES

#: Roles a customer's user may hold. Anything else on a tenant user is a finding.
TENANT_ROLE_PREFIXES = ("Solar ", "Customer", "Accounts ", "Sales ", "Projects ")

#: What guest may read, and nothing else.
GUEST_ALLOWLIST_SOURCE = "a3_sola.registry.platform.PUBLIC_CONTENT_DOCTYPES"

RIGHTS = ("read", "write", "create", "delete", "submit", "cancel", "report", "export",
          "share", "print", "email")


def app_roles():
	"""Roles this app defines, plus the ERPNext ones its role profiles hand out."""
	from a3_sola import registry

	roles = set()
	for doctype in sorted(set(registry.all_doctypes())):
		if not frappe.db.exists("DocType", doctype):
			continue
		for perm in frappe.get_meta(doctype).permissions:
			if perm.role:
				roles.add(perm.role)
	return sorted(roles)


def matrix():
	"""{doctype: {role: {right: bool, ..., 'permlevel': n}}} for every registered doctype."""
	from a3_sola import registry

	out = {}
	for doctype in sorted(set(registry.all_doctypes())):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		rows = {}
		for perm in meta.permissions:
			entry = rows.setdefault(perm.role, {})
			key = f"permlevel_{perm.permlevel}" if perm.permlevel else "base"
			entry[key] = {right: bool(perm.get(right)) for right in RIGHTS}
		out[doctype] = {"istable": bool(meta.istable), "issingle": bool(meta.issingle),
		                "roles": rows}
	return out


# ------------------------------------------------------------------- the rules
def guest_beyond_the_allowlist():
	"""Guest holding anything outside the published-content allowlist."""
	from a3_sola.registry import platform as platform_registry

	allowed = set(platform_registry.PUBLIC_CONTENT_DOCTYPES)
	offenders = []
	for doctype, row in matrix().items():
		if "Guest" not in row["roles"]:
			continue
		if doctype not in allowed:
			offenders.append(doctype)
			continue
		for level, rights in row["roles"]["Guest"].items():
			for right in ("write", "create", "delete", "submit", "cancel"):
				if rights.get(right):
					offenders.append(f"{doctype} (guest can {right})")
	return sorted(set(offenders))


def tenant_roles_holding_platform_rights():
	"""A customer-facing role with access to your own business records.

	The single worst configuration error available in this product: one role profile
	pointing the wrong way and every customer reads your tenant list.
	"""
	from a3_sola.api.isolation import PLATFORM_PRIVATE_DOCTYPES

	offenders = []
	for doctype in PLATFORM_PRIVATE_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		for perm in frappe.get_meta(doctype).permissions:
			role = perm.role or ""
			if role in INTERNAL_PLATFORM_ROLES or role in ("System Manager", "Administrator"):
				continue
			if any(role.startswith(prefix) for prefix in TENANT_ROLE_PREFIXES):
				offenders.append(f"{doctype}: {role} has {_rights(perm)}")
	return sorted(offenders)


def users_holding_both_sides():
	"""An actual user carrying both a tenant stamp and an internal Platform role.

	Checked on the data, not on the configuration - the matrix can be right while a user
	created by hand is wrong, and it is the user that leaks.
	"""
	from a3_sola.api.entitlements import TENANT_FIELD

	offenders = []
	for row in frappe.get_all("User", filters={TENANT_FIELD: ["is", "set"]},
	                          fields=["name", TENANT_FIELD]):
		held = set(frappe.get_roles(row["name"])) & set(INTERNAL_PLATFORM_ROLES)
		if held:
			offenders.append(f"{row['name']} ({row[TENANT_FIELD]}) holds {sorted(held)}")
	return sorted(offenders)


def unprotected_currency_fields():
	"""Currency fields at permlevel 0 on doctypes where costs are meant to be restricted.

	Phases 2, 3 and 5 put margin and cost behind permlevel 1 so a site engineer cannot see
	what a job cost. A field added later at the default level quietly undoes that.
	"""
	from a3_sola import registry

	watched = {
		"Solar Installation", "Project", "Solar Billing Plan", "Solar OM Contract",
		"Installation Work Order", "Solar Design Estimate",
	}
	offenders = []
	for doctype in sorted(watched & set(registry.all_doctypes())):
		if not frappe.db.exists("DocType", doctype):
			continue
		for field in frappe.get_meta(doctype).fields:
			if field.fieldtype != "Currency":
				continue
			if field.permlevel:
				continue
			if any(word in (field.fieldname or "") for word in
			       ("cost", "margin", "profit", "purchase", "landed")):
				offenders.append(f"{doctype}.{field.fieldname}")
	return sorted(offenders)


def platform_roles_are_separated():
	"""Billing, provisioning, lifecycle and admin should not be one role wearing four hats."""
	overlaps = []
	pairs = (
		("Platform Billing Executive", "Tenant"),
		("Platform Billing Executive", "Provisioning Job"),
		("Platform Provisioning Operator", "Payment Order"),
		("Platform Provisioning Operator", "Payment Refund"),
		("Platform Lifecycle Operator", "Payment Refund"),
		("Platform Retention Manager", "Provisioning Job"),
	)
	for role, doctype in pairs:
		if not frappe.db.exists("DocType", doctype):
			continue
		for perm in frappe.get_meta(doctype).permissions:
			if perm.role == role and (perm.write or perm.create or perm.delete):
				overlaps.append(f"{role} can change {doctype}")
	return sorted(set(overlaps))


def _rights(perm):
	return ", ".join(r for r in RIGHTS if perm.get(r)) or "read only"


def findings():
	return {
		"guest_beyond_allowlist": guest_beyond_the_allowlist(),
		"tenant_roles_with_platform_rights": tenant_roles_holding_platform_rights(),
		"users_holding_both_sides": users_holding_both_sides(),
		"unprotected_currency_fields": unprotected_currency_fields(),
		"platform_role_overlap": platform_roles_are_separated(),
	}


def render_markdown():
	data = matrix()
	roles = app_roles()
	out = [
		"# Permission matrix",
		"",
		"Generated from the doctypes by `a3_sola.api.security.matrix`. It describes what "
		"is true, not what was intended.",
		"",
		f"- Doctypes: **{len(data)}**",
		f"- Roles appearing in them: **{len(roles)}**",
		"",
		"## Findings",
		"",
	]
	results = findings()
	clean = True
	for label, rows in results.items():
		if rows:
			clean = False
			out.append(f"### {label.replace('_', ' ').title()} — {len(rows)}")
			out += [f"- {row}" for row in rows]
			out.append("")
	if clean:
		out.append("None. Every rule below holds.")
		out.append("")
	out += [
		"The rules checked:",
		"",
		"1. Guest holds nothing outside the published-content allowlist, and cannot write.",
		"2. No customer-facing role has any right on a platform-private doctype.",
		"3. No actual user carries both a tenant stamp and an internal Platform role.",
		"4. Cost and margin fields stay at permlevel 1.",
		"5. Billing, provisioning, lifecycle and admin are separate roles.",
		"",
		"## The matrix",
		"",
		"| Doctype | Role | Level | Rights |",
		"|---|---|---|---|",
	]
	for doctype in sorted(data):
		for role in sorted(data[doctype]["roles"]):
			for level, rights in sorted(data[doctype]["roles"][role].items()):
				granted = ", ".join(r for r, on in rights.items() if on) or "—"
				out.append(f"| {doctype} | {role} | {level} | {granted} |")
	return "\n".join(out)
