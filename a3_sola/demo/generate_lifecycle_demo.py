# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Phase 7 demo: subscriptions in every state, and the history behind them.

Not a row per state - a *history* per state. The lifecycle reports are all built on the
event log, so a tenant that is simply marked Suspended with nothing behind it makes the
decision audit, the suspension register and the MRR bridge look broken rather than empty.
Each subscription here is walked through the transitions it would really have taken.

Everything is written with the kill switch conceptually off but `dry_run_mode` forced off
for the duration, because demo data has to actually exist. The setting is restored
afterwards whatever happens.
"""

import contextlib

import frappe
from frappe.utils import add_days, add_months, cint, flt, now_datetime, today

from a3_sola.api.settings import get_value

TAG = "Lifecycle Demo"


def _log(message):
	print(f"  lifecycle: {message}")


@contextlib.contextmanager
def _acting():
	"""Let the engine act for the duration, then put the settings back exactly."""
	before = {
		"dry_run_mode": cint(get_value("dry_run_mode", 1)),
		"enable_automatic_suspension": cint(get_value("enable_automatic_suspension", 0)),
		"require_manual_approval_for_suspension": cint(
			get_value("require_manual_approval_for_suspension", 1)),
		"lifecycle_kill_switch": cint(get_value("lifecycle_kill_switch", 0)),
	}
	frappe.db.set_single_value("A3 Sola Settings", {
		"dry_run_mode": 0, "enable_automatic_suspension": 1,
		"require_manual_approval_for_suspension": 0, "lifecycle_kill_switch": 0,
	})
	# Committed immediately, and this is not optional. The loop below rolls back when a
	# scenario fails, and a rollback undoes everything uncommitted in the transaction -
	# including these settings. One failed scenario would otherwise silently put dry run
	# back on and leave every scenario after it doing nothing at all.
	frappe.db.commit()
	frappe.clear_cache(doctype="A3 Sola Settings")
	try:
		yield
	finally:
		frappe.db.rollback()
		frappe.db.set_single_value("A3 Sola Settings", before)
		frappe.db.commit()
		frappe.clear_cache(doctype="A3 Sola Settings")


#: (suffix, state to end in, months of tenure, story)
SCENARIOS = [
	("trial-a", "Trialing", 0, "Day 3 of a 14-day trial, engaged."),
	("trial-b", "Trialing", 0, "Day 11 of 14, has never signed in."),
	("active-new", "Active", 2, "Two months in, paying, healthy."),
	("active-mid", "Active", 9, "Nine months in, expanded once."),
	("active-old", "Active", 26, "Two years, the reference customer."),
	("pastdue", "Past Due", 14, "Card expired last week. Full access - it is the bank."),
	("grace", "Grace", 11, "Nine days unpaid, banner showing, still working."),
	("suspended", "Suspended", 8, "Twenty days unpaid, warned, approved, blocked."),
	("cancelling", "Cancelling", 19, "Cancelled last week, runs to the period end."),
	("cancelled-in", "Cancelled", 7, "Gone, inside the reactivation window."),
	("cancelled-out", "Cancelled", 31, "Gone, past the window - internal to bring back."),
]


def run(company=None):
	"""Build the whole lifecycle picture. Idempotent."""
	from a3_sola.setup.install import default_company

	company = company or default_company()
	plan = _plan()
	if not plan:
		_log("no active subscription plan; skipping")
		return {}

	built = {}
	with _acting():
		for suffix, state, tenure, story in SCENARIOS:
			try:
				built[suffix] = _scenario(suffix, state, tenure, story, plan)
				frappe.db.commit()
			except Exception:
				frappe.db.rollback()
				frappe.log_error(frappe.get_traceback(),
				                 f"a3_sola: lifecycle demo {suffix}")
		_changes(built, plan)
		_seats(built)
		_cancellations(built)
		frappe.db.commit()

	_log(f"{len([v for v in built.values() if v])} subscription(s) across every state")
	return built


def _plan():
	return frappe.db.get_value("Subscription Plan", {"is_active": 1}, "name")


def _subscription(suffix, plan, tenure_months, status="Active"):
	organisation = f"{TAG} {suffix.replace('-', ' ').title()}"
	existing = frappe.db.get_value(
		"Platform Subscription", {"organisation_name": organisation}, "name")
	if existing:
		return frappe.get_doc("Platform Subscription", existing)

	email = f"lifecycle.{suffix}@demo.example"
	if not frappe.db.exists("User", email):
		was = frappe.flags.in_import
		frappe.flags.in_import = True
		try:
			frappe.get_doc({
				"doctype": "User", "email": email, "enabled": 1,
				"first_name": organisation, "send_welcome_email": 0,
				"user_type": "Website User",
			}).insert(ignore_permissions=True)
		finally:
			frappe.flags.in_import = was

	row = frappe.db.get_value("Subscription Plan", plan,
	                          ["monthly_price", "included_users"], as_dict=True)
	subtotal = flt(row.monthly_price) or 3000
	start = add_months(today(), -max(1, tenure_months)) if tenure_months else today()
	period_start = add_days(today(), -12)

	doc = frappe.get_doc({
		"doctype": "Platform Subscription",
		"organisation_name": organisation,
		"primary_contact_email": email,
		"primary_contact_phone": "9847000000",
		"subscription_plan": plan,
		"billing_cycle": "Monthly",
		"included_users": cint(row.included_users) or 5,
		"subtotal": subtotal,
		"tax_amount": flt(subtotal * 0.18, 2),
		"currency": "INR",
		"state_code": "32",
		"place_of_supply": "Kerala",
		"start_date": start,
		"current_period_start": period_start,
		"current_period_end": add_days(period_start, 29),
		"next_billing_date": add_days(period_start, 30),
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	doc.db_set({
		"recurring_amount": flt(subtotal * 1.18, 2),
		"status": status,
		"state_since": start,
		"policy": get_value("default_subscription_policy"),
	}, update_modified=False)
	doc.reload()
	return doc


def _scenario(suffix, state, tenure, story, plan):
	"""One subscription walked to its state through the moves it would really make."""
	from a3_sola.api.lifecycle import events, state_machine

	# A trial starts from Pending Payment. Building one as Active and moving it back is
	# a move the state machine refuses, correctly - a live subscription does not become a
	# trial again.
	doc = _subscription(suffix, plan, tenure,
	                    status="Pending Payment" if state == "Trialing" else "Active")
	if doc.status == state:
		return doc.name

	if state == "Trialing":
		doc.db_set({"trial_end_date": add_days(today(), 14 if suffix.endswith("a") else 3)},
		           update_modified=False)
		doc.reload()
		state_machine.transition(doc, "Trialing", story, "API")
		return doc.name

	events.record(subscription=doc.name, event_type="Activated",
	              reason=f"{story}", triggered_by="Webhook", to_state="Active")

	if state == "Active":
		state_machine.refresh_derived(doc)
		return doc.name

	# Everything else is reached the long way round, one legal move at a time.
	_overdue(doc, days={"Past Due": 3, "Grace": 9, "Suspended": 20,
	                    "Cancelling": 0, "Cancelled": 20}.get(state, 5))
	if state in ("Past Due", "Grace", "Suspended", "Cancelled"):
		state_machine.transition(doc, "Past Due", "Collection failed at the bank.",
		                         "Webhook", policy=doc.policy)
	if state in ("Grace", "Suspended", "Cancelled"):
		state_machine.transition(doc, "Grace",
		                         "Nine days unpaid; banner shown, work not obstructed.",
		                         "Scheduler", policy=doc.policy, policy_stage="GRACE",
		                         access_effect="Banner Only")
	if state in ("Suspended", "Cancelled"):
		_suspend(doc, story)
	if state == "Cancelling":
		_cancel(doc, "Too Expensive", story, immediate=False)
	if state == "Cancelled":
		state_machine.transition(doc, "Cancelled", "Sixty days unpaid.", "Scheduler",
		                         policy=doc.policy, policy_stage="CANCEL")
		window = 20 if suffix.endswith("in") else -10
		doc.db_set("reactivation_deadline", add_days(today(), window),
		           update_modified=False)
	return doc.name


def _overdue(subscription, days):
	"""An unpaid invoice, so the engine's own view of "overdue" agrees with the story."""
	if not days:
		return None
	if frappe.db.exists("Subscription Invoice",
	                    {"platform_subscription": subscription.name,
	                     "payment_status": "Unpaid"}):
		return None
	doc = frappe.get_doc({
		"doctype": "Subscription Invoice",
		"platform_subscription": subscription.name,
		"invoice_date": add_days(today(), -days),
		"due_date": add_days(today(), -days),
		"paid_amount": 0,
		"payment_status": "Unpaid",
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	frappe.db.set_value("Subscription Invoice", doc.name, "grand_total",
	                    flt(subscription.recurring_amount), update_modified=False)
	subscription.db_set({"consecutive_failures": 1,
	                     "next_billing_date": add_days(today(), -days)},
	                    update_modified=False)
	subscription.reload()
	return doc.name


def _suspend(subscription, story):
	"""A full suspension with its snapshot, so the register has something to show."""
	from a3_sola.api.lifecycle import access, state_machine

	tenant = frappe.db.get_value("Tenant", {"platform_subscription": subscription.name},
	                             "name")
	suspension = frappe.get_doc({
		"doctype": "Access Suspension",
		"tenant": tenant or _placeholder_tenant(subscription),
		"platform_subscription": subscription.name,
		"suspension_type": "Non Payment",
		"reason": "Twenty days unpaid after the full dunning sequence.",
		"reason_detail": story,
		"outstanding_amount": flt(subscription.recurring_amount),
		"requested_by": "Scheduler",
		"requested_on": add_days(now_datetime(), -5),
		"scheduled_for": add_days(now_datetime(), -2),
		"approval_status": "Approved",
		"approved_by": "Administrator",
		"approved_on": add_days(now_datetime(), -2),
		"status": "Scheduled",
	})
	suspension.flags.ignore_permissions = True
	suspension.flags.ignore_mandatory = True
	suspension.insert(ignore_permissions=True)
	suspension.submit()
	suspension.db_set("warning_sent_on", add_days(now_datetime(), -5),
	                  update_modified=False)

	if suspension.tenant:
		try:
			access.suspend_tenant_access(suspension.tenant, suspension)
		except Exception:
			# A demo tenant with no users cannot be suspended for real, and that refusal
			# is correct behaviour - record the state anyway so the reports have a row.
			suspension.db_set({"status": "Applied", "applied_on": now_datetime()},
			                  update_modified=False)
	# The effect is passed as None because the suspension above has already applied it;
	# routing it through again would open a second Access Suspension. The access state is
	# then written directly, so the record does not read "Suspended, access Full".
	state_machine.transition(subscription, "Suspended",
	                         "Twenty days unpaid; approved and applied.", "Internal User",
	                         policy=subscription.policy, policy_stage="SUSPEND",
	                         access_effect="None",
	                         related=("Access Suspension", suspension.name))
	subscription.db_set("access_state", "Blocked", update_modified=False)
	return suspension.name


def _placeholder_tenant(subscription):
	return frappe.db.get_value("Tenant", {"status": ["!=", "Terminated"]}, "name")


def _cancel(subscription, reason, detail, immediate=False):
	from a3_sola.api.lifecycle import cancellation

	try:
		return cancellation.request_cancellation(
			subscription, reason, reason_detail=detail,
			cancellation_type="Immediate" if immediate else "End of Period",
			requested_by="Internal User",
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: lifecycle demo cancellation")
		return None


def _changes(built, plan):
	"""One upgrade, one downgrade, and one downgrade blocked on user count."""
	from a3_sola.api.lifecycle import plan_change

	plans = frappe.get_all("Subscription Plan", filters={"is_active": 1},
	                       fields=["name", "monthly_price", "included_users"],
	                       order_by="monthly_price asc")
	if len(plans) < 2:
		_log("only one plan; no plan changes to demonstrate")
		return
	small, large = plans[0], plans[-1]

	for suffix, target, label in (("active-mid", large.name, "upgrade"),
	                              ("active-old", small.name, "downgrade")):
		name = built.get(suffix)
		if not name:
			continue
		subscription = frappe.get_doc("Platform Subscription", name)
		if frappe.db.exists("Plan Change Request",
		                    {"platform_subscription": name, "docstatus": 1}):
			continue
		try:
			request = plan_change.request_change(subscription, new_plan=target,
			                                     requested_by="Tenant Self Service")
			if label == "upgrade":
				plan_change.apply_plan_change(request)
			_log(f"{label} on {suffix}")
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: lifecycle demo {label}")


def _seats(built):
	from a3_sola.api.lifecycle import seats

	name = built.get("active-new")
	tenant = frappe.db.get_value("Tenant", {"platform_subscription": name}, "name") if name else None
	if not tenant:
		# These subscriptions are built directly rather than provisioned, so they carry no
		# tenant and there is nothing to buy a seat for. Said out loud rather than skipped
		# quietly, because an empty Seat Change Request list otherwise looks like a bug.
		_log("no provisioned tenant on the demo subscriptions; no seat change to show")
		return
	if frappe.db.exists("Seat Change Request", {"tenant": tenant, "docstatus": 1}):
		return
	try:
		seats.request_seats(tenant, 2, requested_by="Tenant Self Service")
		_log("one seat addition")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: lifecycle demo seats")


def _cancellations(built):
	"""Two cancellations with different reasons, and one that came back."""
	for suffix, reason, detail in (
		("cancelled-in", "Switching Provider",
		 "Moving to a competitor bundled with their accounting package."),
		("cancelled-out", "Business Closed",
		 "The proprietor retired and the firm has wound up."),
	):
		name = built.get(suffix)
		if not name:
			continue
		subscription = frappe.get_doc("Platform Subscription", name)
		_cancel(subscription, reason, detail)

	# One reactivation, so the cohort and churn reports have a returner in them.
	name = built.get("cancelled-in")
	if name:
		from a3_sola.api.lifecycle import cancellation

		try:
			doc = frappe.get_doc("Platform Subscription", name)
			if doc.status == "Cancelled":
				cancellation.reactivate_subscription(doc, trigger="Internal User")
				_log("one reactivation inside the window")
		except Exception:
			frappe.log_error(frappe.get_traceback(),
			                 "a3_sola: lifecycle demo reactivation")


def teardown():
	"""Remove everything this generator made, children first."""
	subscriptions = frappe.get_all(
		"Platform Subscription", filters={"organisation_name": ["like", f"{TAG}%"]},
		pluck="name") or [""]
	for doctype, field in (
		("Subscription Event", "platform_subscription"),
		("Access Suspension", "platform_subscription"),
		("Plan Change Request", "platform_subscription"),
		("Seat Change Request", "platform_subscription"),
		("Cancellation Request", "platform_subscription"),
		("Subscription Invoice", "platform_subscription"),
	):
		for name in frappe.get_all(doctype, filters={field: ["in", subscriptions]},
		                           pluck="name"):
			frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True,
			                  ignore_on_trash=True)
	for name in subscriptions:
		if not name:
			continue
		frappe.db.set_value("Platform Subscription", name, "docstatus", 2,
		                    update_modified=False)
		frappe.delete_doc("Platform Subscription", name, force=True,
		                  ignore_permissions=True, ignore_on_trash=True)
	for name in frappe.get_all("User", filters={"email": ["like", "lifecycle.%@demo.example"]},
	                           pluck="name"):
		frappe.delete_doc("User", name, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
	frappe.db.commit()
	print("lifecycle demo data removed")
