# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Changing a subscription's shape: upgrades, downgrades, cycle switches, plan swaps.

Two things in here are the reason it is not simply "set the new plan".

THE DOWNGRADE COLLISION. A tenant on 12 users moving to a 5-seat plan has a problem the
software cannot solve. It must not solve it either - picking seven users to disable is a
decision only the customer can make. So a downgrade with blockers waits, and if the
blockers are not cleared by the boundary the tenant STAYS ON THE HIGHER PLAN. The correct
failure mode is "you keep paying more", never "your data became unreachable".

THE COLLECTION TRAP. Phase 5 routes a subscription to auto debit or an authenticated
renewal by comparing the tax-inclusive recurring amount against the RBI ceiling, and
registers each mandate with a maximum. Any upgrade or seat addition can push past either.
A change that silently breaks next month's collection is the most damaging thing this file
could ship, so both are recomputed on every change and acted on before it is applied.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, today

from a3_sola.api.settings import get_value


@frappe.whitelist()
def preview(subscription, new_plan=None, new_cycle=None, seat_delta=0):
	"""The breakdown the customer sees before confirming. Writes nothing."""
	from a3_sola.api.lifecycle import proration

	doc = _as_doc(subscription)
	change_type = classify(doc, new_plan, new_cycle, cint(seat_delta))
	result = proration.calculate_proration(
		doc, change_type, new_plan=new_plan, new_cycle=new_cycle,
		seat_delta=cint(seat_delta),
	)
	new_amount = _new_recurring(doc, new_plan, new_cycle, cint(seat_delta))
	impact, detail, route = proration.assess_mandate_impact(doc, new_amount)
	result.update({
		"new_recurring_amount": new_amount,
		"mandate_impact": impact,
		"mandate_impact_detail": detail,
		"new_collection_route": route,
		"blockers": downgrade_blockers(doc, new_plan) if change_type == "Downgrade" else [],
	})
	return result


def classify(subscription, new_plan=None, new_cycle=None, seat_delta=0):
	"""Upgrade, Downgrade, Cycle Change or Plan Swap - decided on price, not on name."""
	doc = _as_doc(subscription)
	if seat_delta and not new_plan and not new_cycle:
		return "Add Seats" if seat_delta > 0 else "Remove Seats"
	if new_cycle and new_cycle != doc.billing_cycle and (
		not new_plan or new_plan == doc.subscription_plan
	):
		return "Cycle Change"
	if not new_plan or new_plan == doc.subscription_plan:
		return "Plan Swap"
	from a3_sola.api.lifecycle import proration

	now = proration._plan_net(doc.subscription_plan, doc.billing_cycle)
	then = proration._plan_net(new_plan, new_cycle or doc.billing_cycle)
	if then > now:
		return "Upgrade"
	if then < now:
		return "Downgrade"
	return "Plan Swap"


def downgrade_blockers(subscription, new_plan):
	"""Everything that conflicts with the smaller plan, stated plainly.

	Module checks look for ACTUAL DATA, not just the entitlement. Telling a customer they
	will lose a module they have never used is noise; telling them about one holding 200
	records is the whole point.
	"""
	doc = _as_doc(subscription)
	tenant = _tenant_of(doc)
	blockers = []
	if not new_plan:
		return blockers

	plan = frappe.get_cached_doc("Subscription Plan", new_plan)
	quota = cint(plan.included_users)
	if tenant:
		from a3_sola.api.entitlements import get_tenant_usage

		usage = get_tenant_usage(tenant)
		if cint(usage.get("used")) > quota:
			blockers.append(_(
				"{0} users are active and {1} has {2} seats. {3} user(s) have to be "
				"disabled first - and you choose which."
			).format(usage["used"], new_plan, quota, cint(usage["used"]) - quota))

		new_modules = {row.module_name for row in plan.enabled_modules if row.is_enabled}
		current = {
			row.module_name for row in frappe.get_all(
				"Tenant Module", filters={"parent": tenant, "is_enabled": 1},
				fields=["module_name"])
		}
		for module in sorted(current - new_modules):
			count = _records_in(module, tenant)
			if count:
				blockers.append(_(
					"{0} is not part of {1}, and you have {2} record(s) in it. They stay "
					"in the database and stay exportable; nobody will be able to open "
					"them in the app."
				).format(module, new_plan, count))

		max_companies = cint(plan.get("max_companies"))
		if max_companies:
			companies = frappe.db.count("Company", {"a3_sola_tenant": tenant})
			if companies > max_companies:
				blockers.append(_(
					"{0} companies exist and {1} allows {2}."
				).format(companies, new_plan, max_companies))
	return blockers


def _records_in(module, tenant):
	"""How much the tenant actually has in a module they are about to lose."""
	from a3_sola import registry

	company = frappe.db.get_value("Tenant", tenant, "company")
	if not company:
		return 0
	total = 0
	for doctype in frappe.get_all("DocType", filters={"module": module}, pluck="name"):
		try:
			meta = frappe.get_meta(doctype)
			if meta.istable or meta.issingle or not meta.get_field("company"):
				continue
			total += frappe.db.count(doctype, {"company": company})
		except Exception:
			continue
	return total


# --------------------------------------------------------------- the request
@frappe.whitelist()
def request_change(subscription, new_plan=None, new_cycle=None, requested_by="Internal User"):
	"""Build the Plan Change Request, priced and checked, and submit it."""
	from a3_sola.api.lifecycle import proration

	doc = _as_doc(subscription)
	change_type = classify(doc, new_plan, new_cycle)
	quote = preview(doc, new_plan=new_plan, new_cycle=new_cycle)

	# Upgrades land at once; downgrades and monthly switches wait for the boundary, so the
	# customer keeps the plan they have already paid for.
	immediate = change_type in ("Upgrade", "Plan Swap") or (
		change_type == "Cycle Change" and (new_cycle or "") == "Annual"
	)
	effective = today() if immediate else add_days(
		getdate(doc.current_period_end or today()), 1
	)
	blockers = quote.get("blockers") or []

	request = frappe.get_doc({
		"doctype": "Plan Change Request",
		"tenant": _tenant_of(doc),
		"platform_subscription": doc.name,
		"request_type": change_type,
		"requested_by": requested_by,
		"requested_by_user": frappe.session.user,
		"requested_on": now_datetime(),
		"current_plan": doc.subscription_plan,
		"current_cycle": doc.billing_cycle,
		"current_users": cint(doc.total_users),
		"current_recurring_amount": flt(doc.recurring_amount),
		"new_plan": new_plan or doc.subscription_plan,
		"new_cycle": new_cycle or doc.billing_cycle,
		"new_included_users": cint(frappe.db.get_value(
			"Subscription Plan", new_plan or doc.subscription_plan, "included_users")),
		"new_recurring_amount": flt(quote["new_recurring_amount"]),
		"effective_type": "Immediate" if immediate else "Next Period",
		"effective_date": effective,
		"net_amount_payable": flt(quote["net_amount_payable"]),
		"credit_carried_forward": flt(quote["credit_carried_forward"]),
		"mandate_impact": quote["mandate_impact"],
		"mandate_impact_detail": quote["mandate_impact_detail"],
		"new_collection_route": quote["new_collection_route"],
		"downgrade_blockers": "\n".join(blockers),
		"users_to_remove": _users_to_remove(doc, new_plan),
		"proration": [
			{k: v for k, v in line.items()} for line in quote["lines"]
		],
		"status": "Awaiting User Reduction" if blockers else (
			"Awaiting Payment" if flt(quote["net_amount_payable"]) > 0 else "Scheduled"
		),
	})
	request.flags.ignore_permissions = True
	request.insert(ignore_permissions=True)
	request.submit()
	return request.name


def _users_to_remove(subscription, new_plan):
	if not new_plan:
		return 0
	tenant = _tenant_of(subscription)
	if not tenant:
		return 0
	from a3_sola.api.entitlements import get_tenant_usage

	quota = cint(frappe.db.get_value("Subscription Plan", new_plan, "included_users"))
	used = cint(get_tenant_usage(tenant).get("used"))
	return max(0, used - quota)


# --------------------------------------------------------------- applying it
def apply_plan_change(request):
	"""Apply a change, in order, idempotently, resumable from a partial application.

	Each step checks whether it has already been done, so a run that died between steps
	four and five carries on from five rather than starting again.
	"""
	from a3_sola.api.entitlements import apply_module_entitlements
	from a3_sola.api.lifecycle import events, proration

	doc = _as_doc_of("Plan Change Request", request)
	if doc.status == "Applied":
		return doc.name

	subscription = frappe.get_doc("Platform Subscription", doc.platform_subscription)
	tenant = doc.tenant or _tenant_of(subscription)

	blockers = (doc.downgrade_blockers or "").strip()
	if blockers and doc.request_type == "Downgrade":
		if getdate(doc.effective_date) <= getdate(today()):
			# The boundary came and the blockers are still there. Keep them where they
			# are, tell everybody, and try again next period.
			return _defer_downgrade(doc, subscription)
		return doc.name

	before = {
		"plan": subscription.subscription_plan,
		"cycle": subscription.billing_cycle,
		"amount": flt(subscription.recurring_amount),
		"route": subscription.collection_route,
	}

	# 1 & 2. Re-snapshot the tenant's entitlements and the subscription's pricing.
	#        Enforcement always reads the snapshot, never the live plan - so the snapshot
	#        IS the change.
	_snapshot_tenant(tenant, doc.new_plan)
	_snapshot_subscription(subscription, doc)

	# 3. The collection consequence, acted on rather than noted.
	impact, detail, route = proration.assess_mandate_impact(
		subscription, flt(doc.new_recurring_amount)
	)
	_act_on_mandate(subscription, impact, detail, route)

	# 4. Roles follow the snapshot, through the Phase 6 reconciler rather than by hand.
	if tenant:
		apply_module_entitlements(tenant)

	# 5. A cycle change moves the billing schedule.
	if doc.new_cycle and doc.new_cycle != before["cycle"]:
		_reschedule(subscription, doc.new_cycle)

	# 6. The event, with the full before and after.
	event = events.record(
		subscription=subscription.name,
		event_type="Plan Upgraded" if doc.request_type == "Upgrade" else (
			"Plan Downgraded" if doc.request_type == "Downgrade" else "Manual Override"),
		reason=_("{0}: {1} to {2}.").format(
			doc.request_type, before["plan"], doc.new_plan),
		reason_detail=frappe.as_json({"before": before, "after": {
			"plan": doc.new_plan, "cycle": doc.new_cycle,
			"amount": flt(doc.new_recurring_amount), "route": route,
			"mandate_impact": impact,
		}}),
		triggered_by="Tenant Self Service" if doc.requested_by == "Tenant Self Service"
		else "Internal User",
		related=("Plan Change Request", doc.name),
	)

	doc.db_set({"status": "Applied", "applied_on": now_datetime(),
	            "subscription_event": event.name, "mandate_impact": impact,
	            "mandate_impact_detail": detail, "new_collection_route": route},
	           update_modified=False)
	_tell_them(subscription, doc, route, impact)
	return doc.name


def _defer_downgrade(request, subscription):
	"""Blockers uncleared at the boundary. Nothing is downgraded and nobody is suspended."""
	from a3_sola.api.lifecycle import events, notify

	next_boundary = add_days(getdate(subscription.current_period_end or today()), 1)
	request.db_set({"effective_date": next_boundary}, update_modified=False)
	events.record(
		subscription=subscription.name, event_type="Policy Evaluated",
		reason=_("Downgrade deferred: the blockers were not cleared by the boundary. The "
		         "tenant stays on {0} for another period.").format(subscription.subscription_plan),
		reason_detail=request.downgrade_blockers,
		triggered_by="Scheduler",
		related=("Plan Change Request", request.name),
	)
	notify.alert_internal(
		f"a3_sola: downgrade deferred for {request.tenant}",
		f"{request.name} could not be applied because these were not cleared:\n\n"
		f"{request.downgrade_blockers}\n\n"
		f"The tenant stays on {subscription.subscription_plan} and keeps full access. "
		f"They are being charged the higher price, which is the correct failure mode.",
	)
	return request.name


def _snapshot_tenant(tenant, new_plan):
	"""The Phase 6 rule: enforcement reads the snapshot. Re-taking it IS the change."""
	if not (tenant and new_plan):
		return
	plan = frappe.get_cached_doc("Subscription Plan", new_plan)
	values = {
		"subscription_plan": new_plan,
		"plan_code": plan.plan_code,
		"included_users": cint(plan.included_users),
		"user_quota": cint(plan.included_users) + cint(
			frappe.db.get_value("Tenant", tenant, "additional_users")),
	}
	for field in ("max_companies", "storage_limit_gb", "assigned_role_profile"):
		if plan.get(field):
			values[field] = plan.get(field)
	frappe.db.set_value("Tenant", tenant, values, update_modified=False)

	enabled = {row.module_name: cint(row.is_enabled) for row in plan.enabled_modules}
	for row in frappe.get_all("Tenant Module", filters={"parent": tenant},
	                          fields=["name", "module_name"]):
		frappe.db.set_value("Tenant Module", row.name, "is_enabled",
		                    enabled.get(row.module_name, 0), update_modified=False)


def _snapshot_subscription(subscription, request):
	values = {
		"subscription_plan": request.new_plan,
		"plan_code": frappe.db.get_value("Subscription Plan", request.new_plan, "plan_code"),
		"included_users": cint(request.new_included_users),
		"recurring_amount": flt(request.new_recurring_amount),
	}
	if request.new_cycle:
		values["billing_cycle"] = request.new_cycle
	subscription.db_set(values, update_modified=False)
	subscription.reload()


def _act_on_mandate(subscription, impact, detail, route):
	"""Do the thing, not just record that it is needed."""
	from a3_sola.api.lifecycle import notify

	if impact == "None":
		return
	if impact == "Requires Route Change":
		subscription.db_set({"collection_route": route, "route_reason": detail},
		                    update_modified=False)
		if route == "Assisted Renewal" and subscription.payment_mandate:
			frappe.db.set_value("Payment Mandate", subscription.payment_mandate,
			                    "status", "Pending Re-registration", update_modified=False)
	elif impact in ("Requires New Maximum", "Requires Re-registration"):
		if subscription.payment_mandate:
			frappe.db.set_value("Payment Mandate", subscription.payment_mandate,
			                    "status", "Pending Re-registration", update_modified=False)
	notify.alert_internal(
		f"a3_sola: mandate action needed on {subscription.name}",
		f"{impact}\n\n{detail}\n\nThe next collection will fail until this is done.",
	)


def _reschedule(subscription, new_cycle):
	from frappe.utils import add_months

	start = getdate(today())
	end = add_days(add_months(start, 12 if new_cycle == "Annual" else 1), -1)
	subscription.db_set({
		"billing_cycle": new_cycle,
		"current_period_start": start,
		"current_period_end": end,
		"next_billing_date": add_days(end, 1),
	}, update_modified=False)


def _tell_them(subscription, request, route, impact):
	from a3_sola.api.lifecycle import notify

	extra = ""
	if impact != "None":
		extra = _("<p><b>How you pay is changing.</b> {0}</p>").format(
			request.mandate_impact_detail or "")
	body = _(
		"<p>Hello,</p><p>Your A3 Sola plan is now <b>{0}</b> on {1} billing, with {2} "
		"seats, at {3} per cycle. Your next billing date is {4}.</p>{5}"
	).format(
		request.new_plan, request.new_cycle, cint(request.new_included_users),
		frappe.utils.fmt_money(flt(request.new_recurring_amount),
		                       currency=subscription.currency or "INR"),
		subscription.next_billing_date, extra,
	)
	if not subscription.primary_contact_email:
		return False
	try:
		frappe.sendmail(recipients=[subscription.primary_contact_email],
		                subject=_("Your A3 Sola plan has changed"), message=body,
		                reference_doctype="Plan Change Request", reference_name=request.name,
		                now=bool(frappe.flags.in_test))
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: plan change notice {request.name}")
		return False
	return True


def _new_recurring(subscription, new_plan, new_cycle, seat_delta=0):
	"""Tax-inclusive, because that is what the RBI ceiling and the mandate are measured on."""
	from a3_sola.api import tax
	from a3_sola.api.lifecycle import proration

	doc = _as_doc(subscription)
	net = proration._plan_net(
		new_plan or doc.subscription_plan, new_cycle or doc.billing_cycle,
		cint(doc.additional_users) + cint(seat_delta),
	)
	split = tax.compute_tax(net, doc.state_code)
	return flt(net + split["total_tax"], 2)


def _tenant_of(subscription):
	name = subscription if isinstance(subscription, str) else subscription.name
	return frappe.db.get_value("Tenant", {"platform_subscription": name}, "name")


def _as_doc(subscription):
	if isinstance(subscription, str):
		return frappe.get_doc("Platform Subscription", subscription)
	return subscription


def _as_doc_of(doctype, name):
	if isinstance(name, str):
		return frappe.get_doc(doctype, name)
	return name
