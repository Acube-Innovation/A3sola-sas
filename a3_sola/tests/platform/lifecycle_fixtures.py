# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Shared scaffolding for the Phase 7 suites.

Everything here builds a subscription and, where a test needs one, a tenant with users
stamped to it - because most of what Phase 7 does is decided by which users belong to whom.
"""

import frappe
from frappe.utils import add_days, cint, today

from a3_sola.api.entitlements import TENANT_FIELD
from a3_sola.api.settings import get_value

POLICY = "Standard Non-Payment Policy"


def settings(**values):
	"""Set lifecycle settings for one test and remember nothing - the suite resets them."""
	frappe.db.set_single_value("A3 Sola Settings", values)
	frappe.clear_cache(doctype="A3 Sola Settings")
	return values


INERT = {
	"dry_run_mode": 1,
	"enable_automatic_suspension": 0,
	"require_manual_approval_for_suspension": 1,
	"lifecycle_kill_switch": 0,
	"max_suspensions_per_run": 10,
	"min_days_active_before_suspension": 14,
	"notify_before_suspension_days": 3,
}

#: What the tests need to see the engine actually act.
LIVE = dict(INERT, dry_run_mode=0, enable_automatic_suspension=1,
            require_manual_approval_for_suspension=0)


def a_plan(name="Lifecycle Test Plan", monthly=3000, annual=30000, included=5,
           per_seat_monthly=500, per_seat_annual=5000, trial_days=0):
	# Subscription Plan is autonamed PLT-PLAN-###, so it is found by its plan_name, not
	# by `name`. Checking the wrong one made every test try to insert a second plan with
	# a plan_code that is unique.
	existing = frappe.db.get_value("Subscription Plan", {"plan_name": name}, "name")
	if existing:
		frappe.db.set_value("Subscription Plan", existing, {
			"monthly_price": monthly, "annual_price": annual,
			"included_users": included,
			"additional_user_price_monthly": per_seat_monthly,
			"additional_user_price_annual": per_seat_annual,
			"trial_days": trial_days,
		}, update_modified=False)
		return existing
	doc = frappe.get_doc({
		"doctype": "Subscription Plan",
		"plan_name": name,
		"plan_code": name.upper().replace(" ", "-")[:20],
		"monthly_price": monthly,
		"annual_price": annual,
		"included_users": included,
		"additional_user_price_monthly": per_seat_monthly,
		"additional_user_price_annual": per_seat_annual,
		"trial_days": trial_days,
		"is_active": 1,
		# Explicitly unpublished. `is_published` defaults to 1, so a test plan left alone
		# appears on the public pricing page - and the pricing suite, which quite
		# reasonably asserts exactly which plans are listed, starts failing.
		"is_published": 0,
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def a_subscription(prefix, plan=None, status="Active", days_into_period=0,
                   overdue_days=0, cycle="Monthly", subtotal=3000, tax=540,
                   additional_users=0, days_active=400):
	"""A submitted subscription positioned wherever the test needs it in its period."""
	email = f"{prefix}@lifecycle.example"
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": prefix.title(),
			"send_welcome_email": 0, "user_type": "Website User",
		}).insert(ignore_permissions=True)

	start = add_days(today(), -days_into_period)
	end = add_days(start, 29)
	due = add_days(today(), -overdue_days) if overdue_days else add_days(end, 1)

	doc = frappe.get_doc({
		"doctype": "Platform Subscription",
		"organisation_name": f"{prefix.title()} Renewables",
		"primary_contact_email": email,
		"subscription_plan": plan or a_plan(),
		"billing_cycle": cycle,
		"included_users": 5,
		"additional_users": additional_users,
		"subtotal": subtotal,
		"tax_amount": tax,
		"currency": "INR",
		"state_code": "32",
		# The engine derives lifetime_days_active from start_date on every run, so a
		# test that wants a young tenant has to set the date, not the derived field.
		"start_date": add_days(today(), -days_active),
		"current_period_start": start,
		"current_period_end": end,
		"next_billing_date": due,
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	doc.db_set({"status": status, "recurring_amount": subtotal + tax,
	            "lifetime_days_active": days_active,
	            "state_since": add_days(today(), -overdue_days or -1)},
	           update_modified=False)
	doc.reload()
	return doc


def overdue_invoice(subscription, days=1, amount=3540):
	"""An unpaid invoice past its due date - what makes a subscription actually overdue."""
	doc = frappe.get_doc({
		"doctype": "Subscription Invoice",
		"platform_subscription": subscription.name,
		"invoice_date": add_days(today(), -days),
		"due_date": add_days(today(), -days),
		"grand_total": amount,
		"paid_amount": 0,
		"payment_status": "Unpaid",
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	# The controller recomputes grand_total from the items table, and an invoice built
	# without items therefore totals zero - which quietly makes every "there is money
	# outstanding" test measure nothing at all.
	frappe.db.set_value("Subscription Invoice", doc.name, "grand_total", amount,
	                    update_modified=False)
	doc.reload()
	return doc


def a_tenant(prefix, subscription, users=2, quota=5):
	"""A tenant with its own users, stamped so the access controller can resolve them."""
	from a3_sola.api.provisioning import identifiers

	name = f"{prefix.title()} Tenant"
	existing = frappe.db.get_value("Tenant", {"tenant_name": name}, "name")
	if existing:
		# Re-point it at the subscription being asked about. A tenant left over from an
		# earlier test in the same class still names that test's subscription, and every
		# lookup that goes Tenant-by-subscription then finds nothing - which reads as a
		# permission failure rather than as stale state.
		frappe.db.set_value("Tenant", existing,
		                    {"platform_subscription": subscription.name},
		                    update_modified=False)
		return frappe.get_doc("Tenant", existing)
	doc = frappe.new_doc("Tenant")
	doc.update({
		"tenant_name": name,
		"tenant_code": identifiers.generate_code(name),
		"platform_subscription": subscription.name,
		"primary_contact_name": prefix.title(),
		"primary_contact_email": subscription.primary_contact_email,
		"primary_contact_phone": "9847000000",
		"city": "Kochi", "state": "Kerala", "state_code": "32", "country": "India",
		"tenancy_strategy": "Multi Company",
		"subscription_plan": subscription.subscription_plan,
		"included_users": 5, "user_quota": quota,
		"status": "Active", "access_gate": "Full",
	})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	for index in range(users):
		# With a desk role, deliberately. Frappe demotes a user holding none to Website
		# User, and a Website User consumes no seat - so a tenant "with three users" would
		# measure as having none, and every quota test would pass for the wrong reason.
		stamp_user(f"{prefix}.user{index}@lifecycle.example", doc.name,
		           first_name=f"{prefix.title()}{index}",
		           roles=("Solar Sales Executive",))
	return doc


def stamp_user(email, tenant, first_name="Tenant", enabled=1, roles=()):
	"""A user belonging to a tenant.

	`frappe.flags.in_import` is set to skip Frappe's 60-users-per-minute throttle, which a
	suite creating a dozen users trips immediately. It also skips `_set_defaults`, so
	`enabled` has to be passed explicitly - left out, the field arrives as None and lands
	in the database as 0, and every suspension test then measures an already-disabled user.
	"""
	if frappe.db.exists("User", email):
		frappe.db.set_value("User", email, {TENANT_FIELD: tenant, "enabled": cint(enabled)},
		                    update_modified=False)
		return email
	was = frappe.flags.in_import
	frappe.flags.in_import = True
	try:
		doc = frappe.get_doc({
			"doctype": "User", "email": email, "first_name": first_name,
			"send_welcome_email": 0, "user_type": "System User",
			"enabled": cint(enabled),
			TENANT_FIELD: tenant,
			"roles": [{"role": r} for r in roles],
		})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
	finally:
		frappe.flags.in_import = was
	return email


def purge(prefix):
	"""Remove everything a suite made under one prefix, children first."""
	for doctype, field in (
		("Subscription Event", "platform_subscription"),
		("Access Suspension", "platform_subscription"),
		("Plan Change Request", "platform_subscription"),
		("Seat Change Request", "platform_subscription"),
		("Cancellation Request", "platform_subscription"),
		("Subscription Invoice", "platform_subscription"),
	):
		subscriptions = frappe.get_all(
			"Platform Subscription",
			filters={"organisation_name": ["like", f"{prefix.title()}%"]},
			pluck="name",
		) or [""]
		names = frappe.get_all(doctype, filters={field: ["in", subscriptions]}, pluck="name")
		for name in names:
			frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True,
			                  ignore_on_trash=True)
	for name in frappe.get_all("User", filters={"email": ["like", f"{prefix}%@lifecycle.example"]},
	                           pluck="name"):
		frappe.delete_doc("User", name, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
	for name in frappe.get_all("Tenant", filters={"tenant_name": ["like", f"{prefix.title()}%"]},
	                           pluck="name"):
		frappe.db.set_value("Tenant", name, "docstatus", 2, update_modified=False)
		frappe.delete_doc("Tenant", name, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
	# Plans, so they cannot reach the public pricing page, and policies, because one left
	# behind pointing at the shared test plan silently governs every other test.
	for name in frappe.get_all("Subscription Plan",
	                           filters={"plan_name": ["like", f"{prefix}%"]}, pluck="name"):
		frappe.delete_doc("Subscription Plan", name, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
	for name in frappe.get_all("Subscription Policy",
	                           filters={"policy_name": ["like", f"{prefix}%"]}, pluck="name"):
		frappe.delete_doc("Subscription Policy", name, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
	for name in frappe.get_all("Platform Subscription",
	                           filters={"organisation_name": ["like", f"{prefix.title()}%"]},
	                           pluck="name"):
		frappe.db.set_value("Platform Subscription", name, "docstatus", 2,
		                    update_modified=False)
		frappe.delete_doc("Platform Subscription", name, force=True,
		                  ignore_permissions=True, ignore_on_trash=True)
	frappe.db.commit()
