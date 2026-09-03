# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Three tenants with real data, and users at every role level.

Three rather than two on purpose. With two, an isolation bug that leaks "everything except
my own" and one that leaks "exactly one other tenant" look identical. With three, a suite
that only ever sees tenant B from tenant A cannot tell the difference between a working
filter and a filter that happens to exclude one company.
"""

import frappe
from frappe.utils import add_days, cint, today

from a3_sola.api.entitlements import TENANT_FIELD

PREFIX = "sec"

#: Role level -> the roles that level holds. Deliberately spans the range, because a
#: permission gap often exists only at one level - typically the one nobody tested.
ROLE_LEVELS = {
	"admin": ("Solar CRM Manager", "Solar Project Manager", "Accounts Manager"),
	"ordinary": ("Solar Sales Executive",),
	"technician": ("Solar Technician",),
}


def build(tag, index):
	"""One tenant: company, tenant record, users at three role levels, and data.

	Returns a dict, not a document - the callers want the pieces, and holding documents
	across a test's transaction boundary is how stale-reference bugs start.
	"""
	company = _company(f"{PREFIX.title()} {tag} Solar", f"S{tag}{index}")
	subscription = _subscription(tag, company)
	tenant = _tenant(tag, company, subscription)
	users = {
		level: _user(f"{PREFIX}.{tag.lower()}.{level}@security.example", tenant, roles,
		             company)
		for level, roles in ROLE_LEVELS.items()
	}
	data = _data(company, tag)
	frappe.db.set_value("Tenant", tenant, "admin_user", users["admin"],
	                    update_modified=False)
	return {
		"tag": tag, "company": company, "tenant": tenant,
		"subscription": subscription, "users": users, "data": data,
	}


def _company(name, abbr):
	existing = frappe.db.exists("Company", name)
	if existing:
		return name
	doc = frappe.get_doc({
		"doctype": "Company", "company_name": name, "abbr": abbr,
		"default_currency": "INR", "country": "India",
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _subscription(tag, company):
	organisation = f"{PREFIX.title()} {tag} Solar"
	existing = frappe.db.get_value("Platform Subscription",
	                               {"organisation_name": organisation}, "name")
	if existing:
		return existing
	plan = frappe.db.get_value("Subscription Plan", {"is_active": 1}, "name")
	doc = frappe.get_doc({
		"doctype": "Platform Subscription",
		"organisation_name": organisation,
		"primary_contact_email": f"{PREFIX}.{tag.lower()}.billing@security.example",
		"subscription_plan": plan, "billing_cycle": "Monthly",
		"included_users": 5, "subtotal": 3000, "tax_amount": 540, "currency": "INR",
		"state_code": "32", "start_date": add_days(today(), -200),
		"current_period_start": today(), "current_period_end": add_days(today(), 29),
		"next_billing_date": add_days(today(), 30),
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	doc.db_set({"status": "Active", "recurring_amount": 3540}, update_modified=False)
	return doc.name


def _tenant(tag, company, subscription):
	from a3_sola.api.provisioning import identifiers

	name = f"{PREFIX.title()} {tag} Tenant"
	existing = frappe.db.get_value("Tenant", {"tenant_name": name}, "name")
	if existing:
		frappe.db.set_value("Tenant", existing,
		                    {"company": company, "platform_subscription": subscription},
		                    update_modified=False)
		return existing
	doc = frappe.new_doc("Tenant")
	doc.update({
		"tenant_name": name, "tenant_code": identifiers.generate_code(name),
		"platform_subscription": subscription,
		"primary_contact_name": name, "primary_contact_phone": "9847000000",
		"primary_contact_email": f"{PREFIX}.{tag.lower()}.billing@security.example",
		"city": "Kochi", "state": "Kerala", "state_code": "32", "country": "India",
		"tenancy_strategy": "Multi Company", "included_users": 5, "user_quota": 10,
		"status": "Active", "access_gate": "Full",
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	doc.db_set("company", company, update_modified=False)
	frappe.db.set_value("Company", company, "a3_sola_tenant", doc.name,
	                    update_modified=False)
	return doc.name


def _user(email, tenant, roles, company):
	"""A user of this tenant, with the User Permission that IS the isolation.

	That single record is the whole of the boundary in a multi-company model. Creating the
	user without it produces something that looks like a working tenant and reads the
	entire instance, which is exactly the bug the suite exists to catch - so the fixture
	creates it explicitly rather than relying on a hook.
	"""
	was = frappe.flags.in_import
	frappe.flags.in_import = True
	try:
		if not frappe.db.exists("User", email):
			frappe.get_doc({
				"doctype": "User", "email": email, "first_name": email.split("@")[0],
				"send_welcome_email": 0, "user_type": "System User", "enabled": 1,
				TENANT_FIELD: tenant,
				"roles": [{"role": r} for r in roles if frappe.db.exists("Role", r)],
			}).insert(ignore_permissions=True)
		else:
			frappe.db.set_value("User", email, {TENANT_FIELD: tenant, "enabled": 1},
			                    update_modified=False)
	finally:
		frappe.flags.in_import = was

	if not frappe.db.exists("User Permission", {"user": email, "allow": "Company",
	                                            "for_value": company}):
		frappe.get_doc({
			"doctype": "User Permission", "user": email, "allow": "Company",
			"for_value": company, "apply_to_all_doctypes": 1,
		}).insert(ignore_permissions=True)
	frappe.defaults.set_user_default("company", company, user=email)
	frappe.clear_cache(user=email)
	return email


def _data(company, tag):
	"""Enough real data that an attack has something to find.

	Deliberately spread across all four modules: a permission hook is usually registered
	per module, and a module with no data in it proves nothing.
	"""
	made = {}
	consumer = _consumer(company, tag)
	made["Solar Consumer"] = consumer
	made["Lead"] = _lead(company, tag)
	made["Site Survey"] = _survey(company, consumer, tag)
	made.update(_seed_every_doctype(company, tag))
	return made


def _seed_every_doctype(company, tag):
	"""One minimal row in every company-scoped doctype the registries know about.

	The rows are not business-valid and do not need to be. What an isolation attack needs
	is a record OWNED BY ANOTHER COMPANY to try to reach; whether that record would pass a
	controller's business rules is irrelevant to whether the permission layer hides it.

	Without this the suite reports a thousand attempts as "skipped - no foreign record
	exists", and skipped is not passed. It is the difference between "we could not reach
	their data" and "there was nothing there to reach".

	Best effort: a doctype whose controller refuses even a mandatory-ignored insert is
	left alone and shows up honestly in the skipped list.
	"""
	from a3_sola import registry

	made, refused = {}, []
	for doctype in sorted(set(registry.all_doctypes())):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if meta.istable or meta.issingle or not meta.get_field("company"):
			continue
		if frappe.db.exists(doctype, {"company": company}):
			made[doctype] = frappe.db.get_value(doctype, {"company": company}, "name")
			continue
		frappe.db.savepoint("sec_seed")
		try:
			doc = frappe.new_doc(doctype)
			doc.company = company
			_fill_required(doc, meta, company, tag)
			doc.flags.ignore_permissions = True
			doc.flags.ignore_mandatory = True
			doc.flags.ignore_links = True
			doc.flags.ignore_validate = True
			doc.insert(ignore_permissions=True)
			made[doctype] = doc.name
		except Exception as exception:
			frappe.db.rollback(save_point="sec_seed")
			refused.append(f"{doctype}: {str(exception)[:60]}")
	if refused:
		print(f"  security fixture: {len(refused)} doctype(s) would not take a bare row")
	return made


def _fill_required(doc, meta, company, tag):
	"""Enough to get past NOT NULL and unique constraints, and nothing more."""
	for field in meta.fields:
		if field.fieldname == "company" or not field.reqd:
			continue
		if doc.get(field.fieldname):
			continue
		if field.fieldtype in ("Data", "Small Text", "Text", "Long Text", "Text Editor"):
			doc.set(field.fieldname, f"{PREFIX}-{tag}-{field.fieldname}")
		elif field.fieldtype in ("Int", "Float", "Currency", "Percent"):
			doc.set(field.fieldname, 1)
		elif field.fieldtype == "Date":
			doc.set(field.fieldname, today())
		elif field.fieldtype == "Datetime":
			doc.set(field.fieldname, frappe.utils.now_datetime())
		elif field.fieldtype == "Select" and field.options:
			choices = [o for o in field.options.split("\n") if o]
			if choices:
				doc.set(field.fieldname, choices[0])
		elif field.fieldtype == "Link" and field.options:
			existing = frappe.db.get_value(field.options, {}, "name")
			if existing:
				doc.set(field.fieldname, existing)
	return doc


def _consumer(company, tag):
	name = f"{PREFIX.title()} {tag} Consumer"
	existing = frappe.db.get_value("Solar Consumer",
	                               {"consumer_name": name, "company": company}, "name")
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Solar Consumer", "company": company, "consumer_name": name,
		"consumer_category": "Residential",
		"discom": _master("DISCOM", "discom_name", "KSEB", company),
		"consumer_number": f"11565{index_of(tag)}0000001",
		"connection_type": "Single Phase", "sanctioned_load_kw": 5,
		"avg_consumption_units": 320, "billing_frequency": "Bimonthly",
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _lead(company, tag):
	name = f"{PREFIX.title()} {tag} Enquiry"
	existing = frappe.db.get_value("Lead", {"lead_name": name}, "name")
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Lead", "lead_name": name, "first_name": f"{tag}", "last_name": "Enquiry",
		"company": company, "status": "Open",
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _survey(company, consumer, tag):
	existing = frappe.db.get_value("Site Survey",
	                               {"solar_consumer": consumer, "company": company}, "name")
	if existing:
		return existing
	doc = frappe.get_doc({
		"doctype": "Site Survey", "company": company, "solar_consumer": consumer,
		"survey_date": today(),
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _master(doctype, field, value, company):
	existing = frappe.db.get_value(doctype, {field: value, "company": company}, "name")
	if existing:
		return existing
	doc = frappe.get_doc({"doctype": doctype, field: value, "company": company})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def index_of(tag):
	return {"A": 1, "B": 2, "C": 3}.get(tag, 9)


def purge():
	"""Remove everything the fixture made. Children first, companies last."""
	companies = frappe.get_all("Company",
	                           filters={"company_name": ["like", f"{PREFIX.title()}%Solar"]},
	                           pluck="name")
	from a3_sola import registry

	for doctype in reversed(sorted(set(registry.all_doctypes()))):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if meta.istable or meta.issingle or not meta.get_field("company"):
			continue
		for name in frappe.get_all(doctype, filters={"company": ["in", companies or [""]]},
		                           pluck="name"):
			try:
				frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True,
				                  ignore_on_trash=True)
			except Exception:
				pass
	for name in frappe.get_all("User",
	                           filters={"email": ["like", f"{PREFIX}.%@security.example"]},
	                           pluck="name"):
		frappe.delete_doc("User", name, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
	for name in frappe.get_all("Tenant",
	                           filters={"tenant_name": ["like", f"{PREFIX.title()}%Tenant"]},
	                           pluck="name"):
		frappe.db.set_value("Tenant", name, "docstatus", 2, update_modified=False)
		frappe.delete_doc("Tenant", name, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
	for name in frappe.get_all("Platform Subscription",
	                           filters={"organisation_name": ["like", f"{PREFIX.title()}%"]},
	                           pluck="name"):
		frappe.db.set_value("Platform Subscription", name, "docstatus", 2,
		                    update_modified=False)
		frappe.delete_doc("Platform Subscription", name, force=True,
		                  ignore_permissions=True, ignore_on_trash=True)
	frappe.db.commit()
	return companies
