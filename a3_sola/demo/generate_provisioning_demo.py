# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Provisioning demo data: the states an operator actually has to deal with.

Four healthy tenants would make a pretty screenshot and teach nobody anything. What the
Provisioning Failures view, the Isolation Test Status report and the runbook all need is a
set of tenants in the awkward states - stuck past the point of no return, rolled back at
step three, at their seat limit with a failed acceptance, failing isolation, suspended
after a refund. Each one below exists because some report or procedure would otherwise have
nothing to show.

Deliberately does NOT run the real orchestrator for the broken cases: reproducing a genuine
mid-pipeline failure would mean sabotaging the code. The records are built directly, in the
shape the orchestrator leaves behind.
"""

import frappe
from frappe.utils import add_days, add_to_date, cint, now_datetime, today

from a3_sola.api.provisioning import identifiers
from a3_sola.api.provisioning import steps as step_module

from a3_sola.demo.scale import take

MARKER = "demo-tenant"

#: (organisation, plan_code, outcome)
TENANTS = [
	("Kerala Rooftop Energy", "starter", "active"),
	("Malabar Solar Works", "growth", "active"),
	("Backwater Power Systems", "starter", "active"),
	("Cochin Green Energy", "growth", "active"),
	("Highrange Solar Traders", "starter", "stuck-at-10"),
	("Periyar Renewables", "starter", "rolled-back"),
	("Kuttanad Sun Power", "starter", "at-quota"),
	("Wayanad Solar Collective", "growth", "isolation-failed"),
	("Attingal Energy Systems", "starter", "refund-suspended"),
]


def run(company=None):
	"""Demo tenants across the states an operator actually has to deal with.

	Each one is pointed at a company that already exists rather than provisioning a new
	one. Two reasons: a demo should not quietly triple the number of companies on the
	site, and a Tenant with no company shows blank in the Tenant Register, Seat Utilisation
	and Isolation Test Status reports - which are the three reports this data exists to
	fill.
	"""
	frappe.flags.in_demo = True
	companies = frappe.get_all("Company", pluck="name", order_by="creation asc")
	made = []
	for index, (organisation, plan_code, outcome) in enumerate(take(TENANTS)):
		host = companies[index % len(companies)] if companies else None
		made.append(_tenant(organisation, plan_code, outcome, host))
	frappe.db.commit()
	print(f"  provisioning: {len(made)} demo tenants across {len(set(t[2] for t in TENANTS))} states")
	return made


def _tenant(organisation, plan_code, outcome, host_company=None):
	existing = frappe.db.get_value("Tenant", {"tenant_name": organisation}, "name")
	if existing:
		return existing

	plan = frappe.db.get_value("Subscription Plan", {"plan_code": plan_code}, "name") \
		or frappe.get_all("Subscription Plan", pluck="name", limit=1)[0]
	plan_doc = frappe.get_cached_doc("Subscription Plan", plan)
	subscription = _subscription(organisation, plan_doc)

	tenant = frappe.new_doc("Tenant")
	tenant.company = None
	tenant.update(
		{
			"tenant_name": organisation,
			"tenant_code": identifiers.generate_code(organisation),
			"platform_subscription": subscription,
			"primary_contact_name": f"Admin, {organisation}",
			"primary_contact_email": _email(organisation),
			"primary_contact_phone": "9847000000",
			"city": "Kochi",
			"state": "Kerala",
			"state_code": "32",
			"country": "India",
			"tenancy_strategy": "Multi Company",
			"subscription_plan": plan,
			"plan_code": plan_doc.plan_code,
			"included_users": cint(plan_doc.included_users),
			"additional_users": 0,
			"user_quota": cint(plan_doc.included_users),
			"max_companies": cint(plan_doc.included_companies) or 1,
			"storage_limit_gb": cint(plan_doc.storage_limit_gb),
			"assigned_role_profile": plan_doc.role_profile,
			"status": "Provisioning",
			"company": None,
		}
	)
	for row in plan_doc.enabled_modules:
		tenant.append(
			"enabled_modules",
			{"module_name": row.module_name, "is_enabled": cint(row.is_enabled)},
		)
	tenant.flags.ignore_permissions = True
	tenant.insert(ignore_permissions=True)
	tenant.submit()

	# Rolled back means nothing was built, so it gets no company - that is the state.
	if host_company and outcome != "rolled-back":
		tenant.db_set("company", host_company, update_modified=False)
		if not frappe.db.get_value("Company", host_company, "a3_sola_tenant"):
			frappe.db.set_value("Company", host_company, "a3_sola_tenant", tenant.name,
			                    update_modified=False)
		tenant.reload()

	job = _job(tenant, subscription, outcome)
	tenant.db_set("provisioning_job", job, update_modified=False)
	_apply_outcome(tenant, outcome)
	return tenant.name


def _apply_outcome(tenant, outcome):
	now = now_datetime()
	if outcome == "active":
		tenant.db_set(
			{
				"status": "Active",
				"provisioned_on": add_to_date(now, days=-30),
				"activated_on": add_to_date(now, days=-30),
				"active_users": max(1, cint(tenant.user_quota) - 2),
				"seats_available": 2,
				"isolation_test_passed": 1,
				"isolation_test_on": add_to_date(now, days=-30),
			},
			update_modified=False,
		)
		_isolation_rows(tenant, passed=True)
		_onboarding(tenant, done=5)
	elif outcome == "stuck-at-10":
		tenant.db_set(
			{
				"status": "Provisioned with Errors",
				"status_reason": (
					"10_ASSIGN_PERMISSIONS: the company User Permission could not be "
					"created. Nothing was rolled back - see the runbook."
				),
				"provisioned_on": add_to_date(now, days=-2),
			},
			update_modified=False,
		)
		_onboarding(tenant, done=0)
	elif outcome == "rolled-back":
		tenant.db_set(
			{"status": "Cancelled",
			 "status_reason": "Rolled back cleanly at step 3. Nothing was left behind."},
			update_modified=False,
		)
	elif outcome == "at-quota":
		tenant.db_set(
			{
				"status": "Active",
				"provisioned_on": add_to_date(now, days=-60),
				"activated_on": add_to_date(now, days=-60),
				"active_users": cint(tenant.user_quota),
				"seats_available": 0,
				"isolation_test_passed": 1,
				"isolation_test_on": add_to_date(now, days=-60),
			},
			update_modified=False,
		)
		_isolation_rows(tenant, passed=True)
		_onboarding(tenant, done=7)
		_invitations(tenant)
	elif outcome == "isolation-failed":
		tenant.db_set(
			{
				"status": "Provisioned with Errors",
				"status_reason": "Isolation verification failed. Activation was blocked.",
				"provisioned_on": add_to_date(now, days=-1),
				"isolation_test_passed": 0,
				"isolation_test_on": add_to_date(now, days=-1),
			},
			update_modified=False,
		)
		_isolation_rows(tenant, passed=False)
		_onboarding(tenant, done=0)
	elif outcome == "refund-suspended":
		tenant.db_set(
			{
				"status": "Suspended",
				"status_reason": "The initial payment was refunded, so the subscription is unpaid.",
				"provisioned_on": add_to_date(now, days=-14),
				"activated_on": add_to_date(now, days=-14),
				"isolation_test_passed": 1,
				"isolation_test_on": add_to_date(now, days=-14),
			},
			update_modified=False,
		)
		_isolation_rows(tenant, passed=True)
		_onboarding(tenant, done=2)


def _subscription(organisation, plan_doc):
	existing = frappe.db.get_value(
		"Platform Subscription", {"organisation_name": organisation}, "name"
	)
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Platform Subscription",
			"organisation_name": organisation,
			"primary_contact_email": _email(organisation),
			"primary_contact_phone": "9847000000",
			"subscription_plan": plan_doc.name,
			"plan_code": plan_doc.plan_code,
			"billing_cycle": "Monthly",
			"included_users": cint(plan_doc.included_users),
			"subtotal": plan_doc.monthly_price,
			"tax_amount": round(float(plan_doc.monthly_price or 0) * 0.18, 2),
			"currency": "INR",
			"state_code": "32",
			"place_of_supply": "Kerala",
			"start_date": add_days(today(), -30),
			"current_period_start": add_days(today(), -30),
			"current_period_end": add_days(today(), -1),
			"next_billing_date": today(),
			"status": "Active",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _job(tenant, subscription, outcome):
	stop_at = {
		"active": None,
		"stuck-at-10": "10_ASSIGN_PERMISSIONS",
		"rolled-back": "03_CREATE_TENANT_RECORD",
		"at-quota": None,
		"isolation-failed": "12_VERIFY_ISOLATION",
		"refund-suspended": None,
	}[outcome]

	status = {
		"active": "Completed",
		"stuck-at-10": "Failed Past Point of No Return",
		"rolled-back": "Rolled Back",
		"at-quota": "Completed",
		"isolation-failed": "Failed Past Point of No Return",
		"refund-suspended": "Completed",
	}[outcome]

	job = frappe.new_doc("Provisioning Job")
	job.update(
		{
			"tenant": tenant.name,
			"platform_subscription": subscription,
			"idempotency_key": f"demo::{tenant.name}",
			"triggered_by": "Payment Webhook",
			"triggered_on": now_datetime(),
			"started_on": now_datetime(),
			"completed_on": now_datetime(),
			"status": status,
			"tenancy_strategy": "Multi Company",
			"attempt_number": 1,
			"duration_seconds": 11.4,
			"point_of_no_return_passed": 1 if status.startswith("Failed Past") or status == "Completed" else 0,
			"requires_manual_intervention": 1 if status.startswith("Failed") else 0,
			"progress_percent": 100 if status == "Completed" else 80,
		}
	)
	reached_stop = False
	for step in step_module.steps():
		if stop_at and step.step_code == stop_at:
			reached_stop = True
			step_status = "Failed" if status != "Rolled Back" else "Failed"
		elif reached_stop:
			step_status = "Pending"
		elif status == "Rolled Back":
			step_status = "Rolled Back"
		else:
			step_status = "Completed"
		job.append(
			"steps",
			{
				"step_code": step.step_code,
				"step_name": step.step_name,
				"sequence": step.sequence,
				"is_reversible": cint(step.is_reversible),
				"status": step_status,
				"duration_seconds": 0.8,
				"started_on": now_datetime(),
				"completed_on": now_datetime() if step_status != "Pending" else None,
			},
		)
	if status.startswith("Failed"):
		job.failure_summary = (
			f"{stop_at}: this is demo data - nothing actually failed, the record exists so "
			f"the Provisioning Failures view has something to show."
		)
	job.flags.ignore_permissions = True
	job.insert(ignore_permissions=True)
	job.submit()
	return job.name


def _isolation_rows(tenant, passed):
	doc = frappe.get_doc("Tenant", tenant.name)
	if doc.isolation_results:
		return
	checks = [
		("LIST::Solar Consumer", "A list query returns nothing from another company", "Passed"),
		("LIST::Solar Installation", "A list query returns nothing from another company", "Passed"),
		("DIRECT::Solar Consumer", "Opening another company's record by name is refused", "Passed"),
		("PLATFORM::Payment Order", "The tenant admin cannot read Payment Order", "Passed"),
		("SETTINGS::A3 Sola Settings", "The tenant admin cannot read the settings singleton", "Passed"),
		("ROLES::escalation", "The tenant admin cannot edit roles", "Passed"),
	]
	if not passed:
		checks.append(
			("LIST::Solar Design Estimate",
			 "A list query returns nothing from another company", "Failed")
		)
	for code, description, status in checks:
		doc.append(
			"isolation_results",
			{
				"test_code": code,
				"test_description": description,
				"status": status,
				"expected_result": "0 foreign rows",
				"actual_result": "0 foreign rows" if status == "Passed" else "3 foreign rows",
				"details": "" if status == "Passed" else "demo data - not a real leak",
				"run_on": now_datetime(),
			},
		)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)


def _onboarding(tenant, done):
	from a3_sola.api.onboarding import build_checklist

	build_checklist(tenant.name)
	rows = frappe.get_all(
		"Tenant Onboarding Task",
		filters={"parent": tenant.name, "parenttype": "Tenant"},
		fields=["name"], order_by="idx asc",
	)
	for row in rows[:done]:
		frappe.db.set_value(
			"Tenant Onboarding Task", row.name,
			{"is_complete": 1, "completed_on": now_datetime()},
			update_modified=False,
		)


def _invitations(tenant):
	"""One accepted, one expired, one that failed because the seats had gone."""
	specs = [
		("accepted@example.com", "Accepted"),
		("expired@example.com", "Expired"),
		("toolate@example.com", "Failed"),
	]
	for email, status in specs:
		if frappe.db.exists("Tenant Invitation", {"tenant": tenant.name, "invited_email": email}):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Tenant Invitation",
				"tenant": tenant.name,
				"invited_email": email,
				"status": status,
				"sent_on": add_to_date(now_datetime(), days=-20),
				"token_expires_on": add_to_date(now_datetime(), days=-6),
				"failure_reason": (
					"All seats were taken before this invitation was accepted."
					if status == "Failed" else None
				),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


def teardown():
	frappe.flags.in_demo = True
	names = [t[0] for t in TENANTS]
	tenants = frappe.get_all("Tenant", filters={"tenant_name": ["in", names]}, pluck="name")
	for tenant in tenants:
		frappe.db.delete("Tenant Invitation", {"tenant": tenant})
		for job in frappe.get_all("Provisioning Job", filters={"tenant": tenant}, pluck="name"):
			frappe.db.set_value("Provisioning Job", job, "docstatus", 2, update_modified=False)
			frappe.delete_doc("Provisioning Job", job, force=True, ignore_permissions=True)
		# The company was borrowed, not provisioned - unstamp it and leave it standing.
		borrowed = frappe.db.get_value("Tenant", tenant, "company")
		if borrowed and frappe.db.get_value("Company", borrowed, "a3_sola_tenant") == tenant:
			frappe.db.set_value("Company", borrowed, "a3_sola_tenant", None,
			                    update_modified=False)
		frappe.db.set_value("Tenant", tenant, {"docstatus": 2, "company": None},
		                    update_modified=False)
		frappe.delete_doc("Tenant", tenant, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
	for name in names:
		for subscription in frappe.get_all(
			"Platform Subscription", filters={"organisation_name": name}, pluck="name"
		):
			frappe.db.set_value("Platform Subscription", subscription, "docstatus", 2,
			                    update_modified=False)
			frappe.delete_doc("Platform Subscription", subscription, force=True,
			                  ignore_permissions=True)
	frappe.db.commit()
	return len(tenants)


def _email(organisation):
	slug = identifiers.slugify(organisation) or "tenant"
	return f"admin@{slug}.example"
