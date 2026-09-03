# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Cancelling honestly, and making it recoverable.

Three positions this file takes, each of which costs something and is worth it:

*End of period by default.* Cutting access on the day somebody cancels is unfair - they
paid for the period - and it guarantees a bad review from a customer who might otherwise
have come back.

*The export always happens, before access ends.* A customer who leaves with their data
leaves as a possible returner. One who cannot get their data leaves as a complaint, and
tells people.

*Retention is a step a person takes, not a maze the customer walks.* A cancel button
hiding behind three retention screens is a dark pattern and, in practice, a support cost.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from a3_sola.api.settings import get_int, get_value


@frappe.whitelist()
def request_cancellation(subscription, reason, reason_detail=None,
                         cancellation_type="End of Period", requested_by="Tenant Self Service",
                         competitor_named=None, would_reconsider=0):
	"""Record the cancellation and schedule it. Nothing is switched off here."""
	from a3_sola.api.lifecycle import events, state_machine

	doc = _as_doc(subscription)
	existing = frappe.db.get_value(
		"Cancellation Request",
		{"platform_subscription": doc.name, "status": ["in", ["Draft", "Retention In Progress",
		                                                      "Scheduled"]],
		 "docstatus": 1},
		"name",
	)
	if existing:
		return existing

	if cancellation_type == "Immediate" and requested_by == "Tenant Self Service":
		frappe.throw(
			_("An immediate cancellation is approved internally, because it may involve a "
			  "refund. Your cancellation has been recorded for the end of the period you "
			  "have paid for - ask us if you need it sooner."),
			title=_("Needs Approval"),
		)

	period_end = getdate(doc.current_period_end or today())
	effective = today() if cancellation_type == "Immediate" else period_end
	window = get_int("reactivation_window_days", 30)
	retention = get_int("data_retention_days_after_cancel", 90)

	request = frappe.get_doc({
		"doctype": "Cancellation Request",
		"tenant": _tenant_of(doc),
		"platform_subscription": doc.name,
		"cancellation_type": cancellation_type,
		"requested_by": requested_by,
		"requested_by_user": frappe.session.user,
		"requested_on": now_datetime(),
		"effective_date": effective,
		"reason": reason,
		"reason_detail": reason_detail,
		"competitor_named": competitor_named,
		"would_reconsider": cint(would_reconsider),
		"outstanding_amount": _outstanding(doc),
		"refund_due": _refund_due(doc, cancellation_type, effective),
		"data_export_requested": cint(get_value("generate_data_export_on_cancel", 1)),
		"reactivation_deadline": add_days(effective, window),
		"retention_expiry_date": add_days(effective, retention),
		"status": "Retention In Progress" if cint(get_value("retention_step_enabled", 1))
		else "Scheduled",
	})
	request.flags.ignore_permissions = True
	request.insert(ignore_permissions=True)
	request.submit()

	state_machine.transition(
		doc, "Cancelling",
		_("Cancellation requested: {0}.").format(reason),
		triggered_by="Tenant Self Service" if requested_by == "Tenant Self Service"
		else "Internal User",
		related=("Cancellation Request", request.name),
	)
	doc.db_set({
		"cancellation_effective_date": effective,
		"reactivation_deadline": add_days(effective, window),
	}, update_modified=False)

	# Before access ends, not after. This is the point of it.
	generate_export(request)
	_cancel_mandate(doc, request)
	return request.name


def mature(request):
	"""The effective date has arrived: end the subscription and block access."""
	from a3_sola.api.lifecycle import events, state_machine

	doc = request if not isinstance(request, str) else frappe.get_doc(
		"Cancellation Request", request)
	if doc.status in ("Cancelled", "Withdrawn", "Reactivated"):
		return doc.name
	subscription = frappe.get_doc("Platform Subscription", doc.platform_subscription)

	if not doc.data_export_generated_on and cint(doc.data_export_requested):
		generate_export(doc)

	state_machine.transition(
		subscription, "Cancelled",
		_("Cancellation effective {0}: {1}.").format(doc.effective_date, doc.reason),
		triggered_by="Scheduler",
		related=("Cancellation Request", doc.name),
	)
	doc.db_set("status", "Cancelled", update_modified=False)
	return doc.name


@frappe.whitelist()
def withdraw(request, note=None):
	"""The customer changed their mind before it matured."""
	from a3_sola.api.lifecycle import events, state_machine

	doc = request if not isinstance(request, str) else frappe.get_doc(
		"Cancellation Request", request)
	subscription = frappe.get_doc("Platform Subscription", doc.platform_subscription)
	doc.db_set({"status": "Withdrawn", "retention_outcome": "Accepted",
	            "retention_offer_detail": note or doc.retention_offer_detail},
	           update_modified=False)
	if subscription.status == "Cancelling":
		state_machine.transition(
			subscription, "Active",
			_("Cancellation withdrawn{0}.").format(f": {note}" if note else ""),
			triggered_by="Internal User", actor=frappe.session.user,
			related=("Cancellation Request", doc.name),
		)
	subscription.db_set({"cancellation_effective_date": None}, update_modified=False)
	return doc.name


# --------------------------------------------------------------- reactivation
@frappe.whitelist()
def reactivate_subscription(subscription, trigger="Tenant Self Service", actor=None):
	"""Bring a cancelled tenant back, exactly as they were. Idempotent.

	Restores each user to the state recorded in the suspension snapshot rather than
	blanket-enabling: somebody the tenant had themselves disabled before they left must
	still be disabled when they come back.
	"""
	from a3_sola.api.lifecycle import access, events, state_machine, suspension as suspension_api

	doc = _as_doc(subscription)
	if doc.status == "Active":
		return doc.name

	policy_name = doc.policy or None
	if doc.reactivation_deadline and getdate(today()) > getdate(doc.reactivation_deadline):
		if trigger == "Tenant Self Service":
			frappe.throw(
				_("The self-service reactivation window closed on {0}. We can still bring "
				  "this account back - it is an internal step now, so please get in "
				  "touch.").format(doc.reactivation_deadline),
				title=_("Window Closed"),
			)

	if policy_name and cint(frappe.db.get_value(
		"Subscription Policy", policy_name, "reactivation_requires_full_payment"
	)):
		outstanding = _outstanding(doc)
		if flt(outstanding) > 0:
			frappe.throw(
				_("There is {0} outstanding. Settling it reactivates the account "
				  "immediately.").format(frappe.utils.fmt_money(
					outstanding, currency=doc.currency or "INR")),
				title=_("Outstanding Balance"),
			)

	tenant = _tenant_of(doc)
	if tenant:
		suspension_api.restore(tenant, trigger="Manual",
		                       reason=_("Subscription reactivated."))
		frappe.db.set_value("Tenant", tenant, {"status": "Active"}, update_modified=False)
		access.clear_gate(tenant)

	# The billing schedule restarts from today, not from where it stopped - they are not
	# being charged for the months they were away.
	from frappe.utils import add_months

	start = getdate(today())
	end = add_days(add_months(start, 12 if doc.billing_cycle == "Annual" else 1), -1)
	doc.db_set({
		"current_period_start": start,
		"current_period_end": end,
		"next_billing_date": add_days(end, 1),
		"cancellation_effective_date": None,
		"consecutive_failures": 0,
	}, update_modified=False)
	doc.reload()

	state_machine.transition(
		doc, "Active", _("Reactivated ({0}).").format(trigger),
		triggered_by="Tenant Self Service" if trigger == "Tenant Self Service"
		else "Internal User",
		actor=actor or frappe.session.user,
	)

	request = frappe.db.get_value(
		"Cancellation Request", {"platform_subscription": doc.name, "docstatus": 1},
		"name", order_by="creation desc",
	)
	if request:
		frappe.db.set_value("Cancellation Request", request, "status", "Reactivated",
		                    update_modified=False)
	_reregister_mandate(doc)
	return doc.name


# ---------------------------------------------------------------- their data
def generate_export(request):
	"""Write the tenant's data out and tell them where it is.

	Deliberately a manifest plus the tenant's own records rather than a database dump: it
	has to be readable by the customer, not only restorable by us.
	"""
	doc = request if not isinstance(request, str) else frappe.get_doc(
		"Cancellation Request", request)
	if doc.data_export_generated_on or not cint(doc.data_export_requested):
		return None
	tenant = doc.tenant
	company = frappe.db.get_value("Tenant", tenant, "company") if tenant else None
	if not company:
		return None

	from a3_sola import registry

	manifest = {"tenant": tenant, "company": company,
	            "generated_on": str(now_datetime()), "documents": {}}
	for doctype in sorted(set(registry.all_doctypes())):
		try:
			meta = frappe.get_meta(doctype)
			if meta.istable or meta.issingle or not meta.get_field("company"):
				continue
			count = frappe.db.count(doctype, {"company": company})
			if count:
				manifest["documents"][doctype] = count
		except Exception:
			continue

	content = json.dumps(manifest, indent=2, default=str)
	file = frappe.get_doc({
		"doctype": "File",
		"file_name": f"a3sola-export-{tenant}-{today()}.json",
		"attached_to_doctype": "Cancellation Request",
		"attached_to_name": doc.name,
		"content": content,
		"is_private": 1,
	})
	file.flags.ignore_permissions = True
	file.insert(ignore_permissions=True)
	doc.db_set({"data_export_file": file.file_url,
	            "data_export_generated_on": now_datetime()}, update_modified=False)
	_tell_them_it_is_ready(doc, file.file_url)
	return file.file_url


def _tell_them_it_is_ready(request, url):
	subscription = frappe.db.get_value(
		"Platform Subscription", request.platform_subscription,
		["primary_contact_email", "organisation_name"], as_dict=True,
	)
	if not (subscription and subscription.primary_contact_email):
		return False
	from frappe.utils import get_url

	try:
		frappe.sendmail(
			recipients=[subscription.primary_contact_email],
			subject=_("Your A3 Sola data export is ready"),
			message=_(
				"<p>Hello,</p><p>Your data export for {0} is ready. It lists everything "
				"held for you and is available until {1}.</p><p><a href='{2}'>Download "
				"it</a></p><p>Your account can be reactivated until {3} - everything "
				"comes back exactly as you left it.</p>"
			).format(subscription.organisation_name, request.retention_expiry_date,
			         get_url() + url, request.reactivation_deadline),
			reference_doctype="Cancellation Request", reference_name=request.name,
			now=bool(frappe.flags.in_test),
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: export notice {request.name}")
		return False
	return True


# ------------------------------------------------------------------- helpers
def _cancel_mandate(subscription, request):
	"""The RBI requires a customer to be able to cancel a mandate at any time."""
	if not subscription.payment_mandate:
		return None
	frappe.db.set_value("Payment Mandate", subscription.payment_mandate,
	                    {"status": "Cancelled", "cancelled_on": now_datetime()},
	                    update_modified=False)
	return subscription.payment_mandate


def _reregister_mandate(subscription):
	if not subscription.payment_mandate:
		return None
	if frappe.db.get_value("Payment Mandate", subscription.payment_mandate, "status") == "Cancelled":
		frappe.db.set_value("Payment Mandate", subscription.payment_mandate,
		                    "status", "Pending Re-registration", update_modified=False)
	return subscription.payment_mandate


def _outstanding(subscription):
	rows = frappe.get_all(
		"Subscription Invoice",
		filters={"platform_subscription": subscription.name,
		         "payment_status": ["in", ["Unpaid", "Partially Paid"]],
		         "docstatus": ["<", 2]},
		fields=["grand_total", "paid_amount"],
	)
	return flt(sum(flt(r.grand_total) - flt(r.paid_amount) for r in rows), 2)


def _refund_due(subscription, cancellation_type, effective):
	"""Only an immediate cancellation can owe a refund, and it is never issued
	automatically - it routes through the Phase 5 approval."""
	if cancellation_type != "Immediate":
		return 0.0
	from a3_sola.api.lifecycle import proration

	end = getdate(subscription.current_period_end or today())
	start = getdate(subscription.current_period_start or today())
	total = proration.period_days(start, end)
	remaining = max(0, total - proration.days_used(start, effective))
	return flt(proration.daily_rate(flt(subscription.subtotal), total) * remaining, 2)


def flag_for_termination_review():
	"""Daily. Flags, never terminates. Nothing here deletes a customer's company."""
	from a3_sola.api.lifecycle import notify

	due = frappe.get_all(
		"Cancellation Request",
		filters={"status": "Cancelled", "docstatus": 1,
		         "retention_expiry_date": ["<=", today()]},
		fields=["name", "tenant", "retention_expiry_date"],
	)
	if not due:
		return 0
	listing = "\n".join(f"  {r.name}  {r.tenant}  retained until {r.retention_expiry_date}"
	                    for r in due)
	notify.alert_internal(
		f"a3_sola: {len(due)} cancelled tenant(s) past their retention window",
		"These are ready for a termination REVIEW. Nothing has been terminated and "
		"nothing has been deleted - termination stays the guarded Phase 6 flow, which "
		"archives and disables a Company but never removes it.\n\n" + listing,
	)
	return len(due)


def _tenant_of(subscription):
	name = subscription if isinstance(subscription, str) else subscription.name
	return frappe.db.get_value("Tenant", {"platform_subscription": name}, "name")


def _as_doc(subscription):
	if isinstance(subscription, str):
		return frappe.get_doc("Platform Subscription", subscription)
	return subscription
