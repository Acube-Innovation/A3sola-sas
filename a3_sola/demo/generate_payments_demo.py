# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Payments demo data.

Extends the single demo generator rather than adding a second one, and uses the MOCK
gateway only - no demo run ever reaches a real payment API.

The shape is deliberate: both plans, both cycles, both collection routes, two subscriptions
in different dunning stages, a rejected mandate, and one mandate whose registered maximum
has fallen below the current amount. That last one is a silent future failure, and the
Mandate Health report exists to catch it - so the demo has one to catch.
"""

import frappe
from frappe.utils import add_days, add_months, add_to_date, flt, now_datetime, today

from a3_sola.api import tax

from a3_sola.demo.scale import take

#: (organisation, plan, cycle, extra users, status, note)
SUBSCRIPTIONS = (
	("Suryodaya Solar", "starter", "Monthly", 0, "Active", None),
	("Greenvolt Energy", "starter", "Monthly", 3, "Active", None),
	("Keralasun EPC", "growth", "Monthly", 0, "Active", None),
	("Bright Roof Systems", "growth", "Monthly", 5, "Active", "mandate-under"),
	("Vayu Solar Works", "starter", "Annual", 0, "Active", None),
	("Nova Renewables", "growth", "Annual", 2, "Active", None),
	("Anantha Power", "growth", "Annual", 0, "Active", None),
	("Coastal Solar", "starter", "Monthly", 0, "Past Due", "dunning-early"),
	("Sahya Energy", "growth", "Monthly", 0, "Past Due", "dunning-late"),
	("Malabar Solar Co", "starter", "Monthly", 0, "Active", "mandate-rejected"),
)

STATES = (
	("Kerala", "32"), ("Karnataka", "29"), ("Tamil Nadu", "33"),
	("Maharashtra", "27"), ("Kerala", "32"),
)


def _log(message):
	print(f"  {message}")


def run(company=None):
	"""Idempotent. Mock gateway only."""
	if frappe.db.exists("Platform Subscription", {"organisation_name": "Suryodaya Solar"}):
		_log("payments demo already built")
		return

	# Belt and braces: the demo must never touch a real gateway even if the site is Live.
	frappe.flags.use_mock_gateway = True
	frappe.flags.in_demo = True

	company = company or _default_company()
	created = []
	for index, (name, plan_code, cycle, extra, status, note) in enumerate(take(SUBSCRIPTIONS)):
		state, state_code = STATES[index % len(STATES)]
		subscription = _subscription(name, plan_code, cycle, extra, state, state_code)
		if not subscription:
			continue
		_mandate_for(subscription, note)
		_history(subscription, company, months=12 if cycle == "Monthly" else 2)
		if status == "Past Due":
			_past_due(subscription, note)
		created.append(subscription.name)

	_refunds(company)
	_settlements(company)
	_webhook_logs()

	frappe.flags.use_mock_gateway = False
	frappe.flags.in_demo = False
	frappe.db.commit()
	_log(f"{len(created)} subscriptions with mandates, invoices and history")


def _default_company():
	from a3_sola.setup.install import default_company

	return default_company()


def _subscription(name, plan_code, cycle, extra, state, state_code):
	plan = frappe.db.get_value("Subscription Plan", {"plan_code": plan_code}, "name")
	if not plan:
		return None
	plan_doc = frappe.get_cached_doc("Subscription Plan", plan)

	base = flt(plan_doc.annual_price if cycle == "Annual" else plan_doc.monthly_price)
	per_user = flt(
		plan_doc.additional_user_price_annual if cycle == "Annual"
		else plan_doc.additional_user_price_monthly
	)
	subtotal = flt(base + per_user * extra, 2)
	split = tax.compute_tax(subtotal, state_code)

	start = add_months(today(), -12 if cycle == "Monthly" else -14)
	doc = frappe.get_doc(
		{
			"doctype": "Platform Subscription",
			"organisation_name": name,
			"primary_contact_email": f"billing@{name.lower().replace(' ', '')}.example",
			"primary_contact_phone": "9847012345",
			"subscription_plan": plan,
			"billing_cycle": cycle,
			"included_users": plan_doc.included_users,
			"additional_users": extra,
			"subtotal": subtotal,
			"tax_amount": split["total_tax"],
			"currency": "INR",
			"state_code": state_code,
			"place_of_supply": state,
			"start_date": start,
			"current_period_start": add_months(today(), -1),
			"current_period_end": add_days(today(), -1),
			"next_billing_date": today(),
			"status": "Active",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _mandate_for(subscription, note):
	"""Only where the route allows it - an annual plan gets no auto-debit mandate."""
	if subscription.collection_route != "Auto Debit":
		return None

	mandate = frappe.get_doc(
		{
			"doctype": "Payment Mandate",
			"platform_subscription": subscription.name,
			"customer_name": subscription.organisation_name,
			"customer_email": subscription.primary_contact_email,
			"mandate_type": "Card e-Mandate",
			"recurring_debit_amount": subscription.recurring_amount,
			"registered_on": subscription.start_date,
			"valid_until": add_months(today(), 24),
			"instrument_masked": "1111",
			"bank_or_issuer": "HDFC",
		}
	)
	if note == "mandate-under":
		# Registered before the customer added users. The next debit will be declined,
		# and Mandate Health is what should catch it first.
		mandate.registered_max_amount = flt(subscription.recurring_amount) - 500
	mandate.flags.ignore_permissions = True
	mandate.insert(ignore_permissions=True)
	mandate.submit()

	if note == "mandate-rejected":
		mandate.set_status("Rejected", reason="The issuing bank declined the registration.")
	else:
		mandate.set_status("Active", reason="Confirmed by the bank.")

	subscription.db_set("payment_mandate", mandate.name, update_modified=False)
	return mandate


def _history(subscription, company, months):
	"""Collected cycles, each with its order, transaction and tax invoice."""
	for offset in range(months, 0, -1):
		period_start = add_months(today(), -offset)
		period_end = add_days(add_months(period_start, 1), -1)
		order = _order(subscription, period_start, period_end, company)
		if not order:
			continue
		_transaction(order)
		_invoice(subscription, order, company)
		subscription.append(
			"billing_cycles",
			{
				"period_start": period_start,
				"period_end": period_end,
				"debit_date": period_start,
				"amount": subscription.recurring_amount,
				"notice_sent_on": add_to_date(period_start, hours=-30),
				"payment_order": order.name,
				"outcome": "Collected",
				"confirmation_sent_on": period_start,
			},
		)
	subscription.flags.ignore_validate_update_after_submit = True
	subscription.save(ignore_permissions=True)
	subscription.db_set(
		{
			"successful_payments": months,
			"lifetime_value": flt(subscription.recurring_amount) * months,
			"last_successful_billing_date": add_months(today(), -1),
		},
		update_modified=False,
	)


def _order(subscription, period_start, period_end, company):
	from a3_sola.api import payments

	key = payments.idempotency_key(
		"Platform Subscription", subscription.name, "Renewal", str(period_start)
	)
	if frappe.db.exists("Payment Order", {"idempotency_key": key}):
		return None
	order = frappe.get_doc(
		{
			"doctype": "Payment Order",
			"reference_doctype": "Platform Subscription",
			"reference_name": subscription.name,
			"platform_subscription": subscription.name,
			"customer_name": subscription.organisation_name,
			"customer_email": subscription.primary_contact_email,
			"order_type": "Renewal",
			"billing_cycle": subscription.billing_cycle,
			"period_start": period_start,
			"period_end": period_end,
			"base_amount": subscription.base_amount or subscription.subtotal,
			"additional_user_amount": subscription.additional_user_amount,
			"subtotal": subscription.subtotal,
			"tax_amount": subscription.tax_amount,
			"total_amount": subscription.recurring_amount,
			"currency": "INR",
			"customer_state_code": subscription.state_code,
			"place_of_supply": subscription.place_of_supply,
			"collection_mode": (
				"Auto Debit" if subscription.collection_route == "Auto Debit" else "Payment Link"
			),
			"collection_reason": subscription.route_reason,
			"gateway_order_id": f"order_demo_{frappe.generate_hash(length=12)}",
			"idempotency_key": key,
			"price_breakdown": frappe.as_json(
				[{"label": f"{subscription.plan_code} plan", "detail": "Renewal",
				  "amount": subscription.subtotal}]
			),
		}
	)
	order.flags.ignore_permissions = True
	order.insert(ignore_permissions=True)
	order.db_set(
		{"status": "Paid", "paid_on": period_start, "amount_paid": subscription.recurring_amount,
		 "attempt_count": 1},
		update_modified=False,
	)
	order.reload()
	return order


def _transaction(order):
	fee = flt(flt(order.total_amount) * 0.0236, 2)
	doc = frappe.get_doc(
		{
			"doctype": "Payment Transaction",
			"payment_order": order.name,
			"attempt_number": 1,
			"gateway_payment_id": f"pay_demo_{frappe.generate_hash(length=12)}",
			"method": "Card",
			"method_detail": "Visa 1111",
			"amount": order.total_amount,
			"currency": "INR",
			"status": "Captured",
			"gateway_fee": flt(fee / 1.18, 2),
			"gateway_tax": flt(fee - fee / 1.18, 2),
			"initiated_on": order.paid_on,
			"completed_on": order.paid_on,
			"signature_verified": 1,
			"verification_method": "Webhook",
			"raw_response": frappe.as_json({"id": "pay_demo", "status": "captured"}),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc


def _invoice(subscription, order, company):
	doc = frappe.get_doc(
		{
			"doctype": "Subscription Invoice",
			"platform_subscription": subscription.name,
			"payment_order": order.name,
			"company": company,
			"customer_legal_name": subscription.organisation_name,
			"customer_state_code": subscription.state_code,
			"customer_state": subscription.place_of_supply,
			"place_of_supply": subscription.place_of_supply,
			"invoice_date": order.period_start,
			"period_start": order.period_start,
			"period_end": order.period_end,
			"billing_cycle": subscription.billing_cycle,
			"due_date": order.period_start,
			"currency": "INR",
			"payment_status": "Paid",
			"paid_amount": order.total_amount,
			"paid_on": order.paid_on,
			"payment_reference": order.gateway_order_id,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _past_due(subscription, note):
	"""A failed cycle, and dunning part-way through it."""
	subscription.append(
		"billing_cycles",
		{
			"period_start": today(),
			"period_end": add_days(add_months(today(), 1), -1),
			"debit_date": today(),
			"amount": subscription.recurring_amount,
			"notice_sent_on": add_to_date(now_datetime(), hours=-30),
			"outcome": "Failed",
		},
	)
	steps = (
		[(1, "Email Reminder", "Contacted")]
		if note == "dunning-early"
		else [
			(1, "Email Reminder", "Contacted"),
			(2, "Auto Retry", "Failed"),
			(3, "Auto Retry", "Failed"),
			(4, "Payment Link Issued", "Contacted"),
		]
	)
	for number, action, outcome in steps:
		subscription.append(
			"dunning_attempts",
			{
				"attempt_number": number,
				"attempt_date": add_to_date(now_datetime(), days=-(len(steps) - number)),
				"attempt_type": action,
				"outcome": outcome,
				"error_code": "insufficient_funds" if action == "Auto Retry" else None,
			},
		)
	subscription.flags.ignore_validate_update_after_submit = True
	subscription.save(ignore_permissions=True)
	subscription.db_set(
		{
			"status": "Past Due",
			"status_reason": "The bank declined the debit: insufficient funds.",
			"failed_payments": len([s for s in steps if s[2] == "Failed"]) or 1,
			"consecutive_failures": 1,
		},
		update_modified=False,
	)


def _refunds(company):
	"""One goodwill, one duplicate - different reasons read differently in the register."""
	orders = frappe.get_all(
		"Payment Order", filters={"status": "Paid"}, pluck="name", limit=2
	)
	for index, order_name in enumerate(orders):
		order = frappe.get_doc("Payment Order", order_name)
		doc = frappe.get_doc(
			{
				"doctype": "Payment Refund",
				"payment_order": order.name,
				"refund_type": "Goodwill" if index == 0 else "Duplicate Payment",
				"refund_amount": flt(flt(order.total_amount) * (0.25 if index == 0 else 1.0), 2),
				"currency": "INR",
				"reason": "Billing Error" if index == 0 else "Duplicate Charge",
				"reason_detail": (
					"Service was interrupted for two days; a quarter of the month credited."
					if index == 0
					else "The customer submitted the payment twice within a minute."
				),
				"status": "Approved",
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.db_set(
			{"status": "Processed", "processed_on": now_datetime(),
			 "gateway_refund_id": f"rfnd_demo_{frappe.generate_hash(length=10)}"},
			update_modified=False,
		)
	_log(f"{len(orders)} refunds")


def _settlements(company):
	"""Three settlements, one with a line nothing matches - the case that matters."""
	transactions = frappe.get_all(
		"Payment Transaction",
		filters={"status": "Captured"},
		fields=["gateway_payment_id", "amount", "gateway_fee", "gateway_tax"],
		limit=24,
	)
	if not transactions:
		return
	from a3_sola.api import reconciliation

	batches = [transactions[i::3] for i in range(3)]
	for index, batch in enumerate(batches, start=1):
		settlement_id = f"setl_demo_{index:03d}"
		if frappe.db.exists("Settlement Reconciliation", {"settlement_id": settlement_id}):
			continue
		lines = [
			{
				"gateway_payment_id": row.gateway_payment_id,
				"entry_type": "Payment",
				"gross_amount": row.amount,
				"gateway_fee": row.gateway_fee,
				"gateway_tax": row.gateway_tax,
				"net_amount": flt(
					flt(row.amount) - flt(row.gateway_fee) - flt(row.gateway_tax), 2
				),
				"settled_on": add_days(today(), -index * 7),
			}
			for row in batch
		]
		if index == 3:
			# Money that moved with no record behind it. Deliberately left unmatched so
			# the Unreconciled Payments report has the case it exists for.
			lines.append(
				{
					"gateway_payment_id": "pay_unknown_to_us_001",
					"entry_type": "Payment",
					"gross_amount": 3540,
					"gateway_fee": 70.8,
					"gateway_tax": 12.74,
					"net_amount": 3456.46,
					"settled_on": add_days(today(), -21),
				}
			)
		doc = frappe.get_doc(
			{
				"doctype": "Settlement Reconciliation",
				"company": company,
				"settlement_id": settlement_id,
				"settlement_date": add_days(today(), -index * 7),
				"from_date": add_days(today(), -index * 7 - 7),
				"to_date": add_days(today(), -index * 7),
				"net_settled": flt(sum(flt(line["net_amount"]) for line in lines), 2),
				"bank_reference": f"UTR{index:06d}",
				"lines": lines,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		reconciliation.match(doc)
	_log("3 settlements, one with an unmatched line")


def _webhook_logs():
	"""Realistic traffic, including one replay and one signature failure."""
	import hashlib

	samples = [
		("payment.captured", 1, "Processed", 0),
		("payment.captured", 1, "Processed", 1),
		("order.paid", 1, "Processed", 0),
		("payment.failed", 1, "Processed", 0),
		("token.confirmed", 1, "Processed", 0),
		("refund.processed", 1, "Ignored", 0),
		("unverified", 0, "Ignored", 0),
	]
	for index, (event_type, verified, status, replay) in enumerate(samples):
		event_id = f"evt_demo_{index:03d}"
		if frappe.db.exists("Payment Webhook Log", {"event_id": event_id}):
			continue
		frappe.get_doc(
			{
				"doctype": "Payment Webhook Log",
				"event_id": event_id,
				"event_type": event_type,
				"gateway": "Razorpay",
				"received_on": add_to_date(now_datetime(), days=-index),
				"signature_verified": verified,
				"is_replay": replay,
				"payload_hash": hashlib.sha256(event_id.encode()).hexdigest(),
				"processing_status": status,
				"processed_on": now_datetime() if status == "Processed" else None,
				"processing_attempts": 1,
				"source_ip": "52.66.0.10",
				# An unverified body is attacker-controlled and is never stored.
				"raw_payload": None if not verified else frappe.as_json({"event": event_type}),
			}
		).insert(ignore_permissions=True)
	_log("7 webhook logs including a replay and a signature failure")


def teardown():
	order = (
		"Settlement Reconciliation", "Payment Refund", "Subscription Invoice",
		"Payment Transaction", "Payment Order", "Payment Mandate",
		"Platform Subscription", "Payment Webhook Log",
	)
	for doctype in order:
		for name in frappe.get_all(doctype, pluck="name"):
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.flags.ignore_links = True
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		_log(f"removed {doctype}")
	frappe.db.commit()
