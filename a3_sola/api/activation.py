# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The last step: switching the tenant on, and making sure it will bill again.

The second half of that sentence is the part worth attention. A tenant that provisions
perfectly but never appears in a billing run is a silent revenue leak - nothing breaks,
nobody complains, and the money simply stops. So activation does not merely set dates; it
asserts afterwards that the subscription is actually in the next run's candidate set, and
fails loudly if it is not.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, add_years, getdate, now_datetime, today


def activate(context):
	tenant = context.reload_tenant()
	subscription = frappe.get_doc("Platform Subscription", context.subscription.name)

	if not tenant.isolation_test_passed:
		from a3_sola.api.settings import get_value

		if frappe.utils.cint(get_value("run_isolation_test_on_provision", 1)):
			frappe.throw(
				_("Isolation verification has not passed, so this tenant will not be "
				  "activated. A tenant that might see another customer's data is never "
				  "handed over."),
				title=_("Blocked by Isolation"),
			)

	_set_billing_window(subscription)
	subscription.set_status(
		"Active", reason=_("Provisioned and activated on {0}.").format(today())
	)

	tenant.db_set(
		{
			"status": "Active",
			"status_reason": None,
			"activated_on": now_datetime(),
			"provisioned_on": tenant.provisioned_on or now_datetime(),
			"provisioning_job": context.job.name if context.job else tenant.provisioning_job,
		},
		update_modified=False,
	)

	_finish_signup(context, tenant)
	billing = _assert_will_bill_again(subscription)

	return {
		"created_doctype": "Tenant",
		"created_name": tenant.name,
		"remarks": _("Active; next billing {0}.").format(billing["next_billing_date"]),
	}


def _set_billing_window(subscription):
	"""Set the first period and the first billing date, once.

	Only when they are unset. A resumed job must not shunt an already-running
	subscription's billing date forward - that would skip a cycle, and skipping a cycle is
	money nobody ever invoices.
	"""
	if subscription.current_period_start and subscription.next_billing_date:
		return
	start = getdate(subscription.start_date or today())
	if (subscription.billing_cycle or "").lower() == "annual":
		end = add_days(add_years(start, 1), -1)
	else:
		end = add_days(add_months(start, 1), -1)
	next_billing = add_days(end, 1)
	subscription.db_set(
		{
			"start_date": start,
			"current_period_start": start,
			"current_period_end": end,
			"next_billing_date": next_billing,
			"next_debit_date": next_billing,
			"billing_day": start.day,
		},
		update_modified=False,
	)
	subscription.reload()


def _assert_will_bill_again(subscription):
	"""Prove the subscription is in the next billing run's candidate set.

	This mirrors `billing_engine._due_subscriptions` deliberately rather than calling it:
	the point is to check the same filters the engine uses, on a future date, without
	actually running a collection.
	"""
	subscription.reload()
	if not subscription.next_billing_date:
		frappe.throw(
			_("The subscription has no next billing date, so it would never bill again."),
			title=_("Billing Not Scheduled"),
		)
	if subscription.docstatus != 1:
		frappe.throw(
			_("The subscription is not submitted, so no billing run will pick it up."),
			title=_("Billing Not Scheduled"),
		)
	candidates = frappe.get_all(
		"Platform Subscription",
		filters={
			"name": subscription.name,
			"docstatus": 1,
			"status": ["in", ["Active", "Past Due"]],
			"next_billing_date": ["<=", add_days(getdate(subscription.next_billing_date), 1)],
		},
		pluck="name",
	)
	if subscription.name not in candidates:
		frappe.throw(
			_("Subscription {0} would not appear in the billing run on {1}. A tenant that "
			  "provisions but never bills again is a silent revenue leak, so activation "
			  "stops here.").format(subscription.name, subscription.next_billing_date),
			title=_("Billing Not Scheduled"),
		)
	return {
		"next_billing_date": subscription.next_billing_date,
		"collection_route": subscription.collection_route,
	}


def _finish_signup(context, tenant):
	"""Write the results back where Phase 4 said they would appear."""
	signup_name = context.signup.name if context.signup else tenant.subscription_signup
	if not signup_name or not frappe.db.exists("Subscription Signup", signup_name):
		return
	signup = frappe.get_doc("Subscription Signup", signup_name)
	signup.db_set(
		{
			"provisioned_company": tenant.company,
			"provisioned_site": tenant.site_name or frappe.local.site,
			"admin_user": tenant.admin_user,
			"subscription": context.subscription.name,
		},
		update_modified=False,
	)
	signup.reload()
	if signup.status != "Active":
		signup.set_status(
			"Active",
			details=_("Workspace {0} provisioned and activated.").format(tenant.company),
		)
		signup.flags.ignore_permissions = True
		signup.flags.ignore_validate_update_after_submit = True
		signup.save(ignore_permissions=True)


def notify_phase_seven(subscription):
	"""Hand off to Phase 7 if it exists, and carry on if it does not."""
	from a3_sola.platform.doctype.platform_subscription.platform_subscription import (
		on_subscription_activated,
		safely,
	)

	return safely(on_subscription_activated, subscription, "on_subscription_activated")
