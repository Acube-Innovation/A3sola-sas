# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Settlement reconciliation.

The gateway pays out net of its fees, so what lands in the bank never equals what the
customers paid. Reconciliation is what proves the difference is exactly the fees and not
something else.

**An unmatched settlement line is never silently absorbed.** It means money moved that
this system cannot explain - a payment we did not record, a refund we did not know about,
or an integration bug. Every one is flagged, and the Unreconciled Payments report exists
to make sure none of them sits unexamined.

A CSV import path sits alongside the API fetch on purpose: settlement report formats
change, and an import is the escape hatch that keeps the client working on the day it does.
"""

import csv
import io

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from a3_sola.api import tax
from a3_sola.api.permissions import require_role
from a3_sola.api.settings import get_int

#: Column names we accept from a settlement CSV, in the shapes gateways actually use.
COLUMN_ALIASES = {
	"gateway_payment_id": ("payment_id", "entity_id", "id", "transaction_id"),
	"gateway_refund_id": ("refund_id",),
	"entry_type": ("type", "entity_type", "record_type"),
	"gross_amount": ("amount", "gross", "gross_amount", "debit", "credit"),
	"gateway_fee": ("fee", "fees", "commission"),
	"gateway_tax": ("tax", "gst", "fee_tax"),
	"net_amount": ("net", "net_amount", "settled_amount"),
	"settled_on": ("settled_at", "settlement_date", "date"),
}

ENTRY_TYPES = {
	"payment": "Payment", "refund": "Refund", "adjustment": "Adjustment",
	"fee": "Fee", "tax": "Tax", "chargeback": "Chargeback",
}


@frappe.whitelist()
def import_settlement_csv(company, settlement_id, settlement_date, csv_text, net_settled=None):
	"""Build a reconciliation from a pasted settlement report."""
	require_role(
		("Platform Billing Manager", "Platform Admin", "System Manager"),
		_("Working with settlements"),
	)

	existing = frappe.db.get_value(
		"Settlement Reconciliation", {"settlement_id": settlement_id}, "name"
	)
	if existing:
		return existing

	rows = _parse_csv(csv_text)
	if not rows:
		frappe.throw(_("No settlement lines could be read from that file."))

	doc = frappe.get_doc(
		{
			"doctype": "Settlement Reconciliation",
			"company": company,
			"gateway": "Razorpay",
			"settlement_id": settlement_id,
			"settlement_date": settlement_date or today(),
			"net_settled": flt(net_settled),
			"lines": rows,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	match(doc)

	from a3_sola.api import audit

	audit.record(
		"Reconciliation Imported",
		f"Settlement {settlement_id} imported with {len(rows)} line(s)",
		reference_doctype="Settlement Reconciliation",
		reference_name=doc.name,
		amount=doc.net_settled,
		detail=f"{doc.matched_count} matched, {doc.unmatched_count} unmatched on import.",
	)
	return doc.name


def _parse_csv(csv_text):
	reader = csv.DictReader(io.StringIO(csv_text or ""))
	if not reader.fieldnames:
		return []
	headers = {
		(name or "").strip().lower().replace(" ", "_"): name for name in reader.fieldnames
	}

	def pick(row, field):
		for alias in (field,) + COLUMN_ALIASES.get(field, ()):
			if alias in headers:
				value = (row.get(headers[alias]) or "").strip()
				if value:
					return value
		return None

	out = []
	for row in reader:
		payment_id = pick(row, "gateway_payment_id")
		if not payment_id:
			continue
		entry_type = ENTRY_TYPES.get((pick(row, "entry_type") or "payment").lower(), "Payment")
		out.append(
			{
				"gateway_payment_id": payment_id,
				"gateway_refund_id": pick(row, "gateway_refund_id"),
				"entry_type": entry_type,
				"gross_amount": flt(pick(row, "gross_amount")),
				"gateway_fee": flt(pick(row, "gateway_fee")),
				"gateway_tax": flt(pick(row, "gateway_tax")),
				"net_amount": flt(pick(row, "net_amount")),
				"settled_on": pick(row, "settled_on") or today(),
				"match_status": "Unmatched",
			}
		)
	return out


def match(reconciliation):
	"""Match each line to a Payment Transaction and compute the variance."""
	matched = unmatched = 0
	gross = fees = fee_tax = refunds = variance = 0.0

	for line in reconciliation.lines:
		transaction = frappe.db.get_value(
			"Payment Transaction",
			{"gateway_payment_id": line.gateway_payment_id},
			["name", "payment_order", "amount"],
			as_dict=True,
		)
		if transaction:
			line.payment_transaction = transaction.name
			line.payment_order = transaction.payment_order
			difference = flt(flt(line.gross_amount) - flt(transaction.amount), 2)
			line.variance_amount = difference
			if abs(difference) < 0.01:
				line.match_status = "Matched"
				matched += 1
			else:
				line.match_status = "Partially Matched"
				line.variance_reason = _("Settled {0} against a recorded {1}.").format(
					line.gross_amount, transaction.amount
				)
				unmatched += 1
		else:
			line.match_status = "Unmatched"
			# Money moved that this system cannot explain. Never absorbed silently.
			line.variance_reason = _(
				"No payment in this system matches {0}. Money has moved that we cannot "
				"account for."
			).format(line.gateway_payment_id)
			line.variance_amount = flt(line.gross_amount)
			unmatched += 1

		gross += flt(line.gross_amount)
		fees += flt(line.gateway_fee)
		fee_tax += flt(line.gateway_tax)
		if line.entry_type == "Refund":
			refunds += flt(line.gross_amount)
		variance += flt(line.variance_amount)

	reconciliation.gross_total = flt(gross, 2)
	reconciliation.total_fees = flt(fees, 2)
	reconciliation.total_tax = flt(fee_tax, 2)
	reconciliation.total_refunds = flt(refunds, 2)
	reconciliation.matched_count = matched
	reconciliation.unmatched_count = unmatched
	reconciliation.variance_total = flt(variance, 2)
	reconciliation.status = "Variance" if unmatched else "Reconciled"
	reconciliation.flags.ignore_permissions = True
	reconciliation.save(ignore_permissions=True)

	if unmatched:
		frappe.log_error(
			title="a3_sola: unmatched settlement lines",
			message=(
				f"Settlement {reconciliation.settlement_id} has {unmatched} line(s) this "
				"system cannot match to a recorded payment. Each one is money that moved "
				"without a corresponding record - investigate before posting."
			),
		)
	return reconciliation


@frappe.whitelist()
def fetch_settlement(company, settlement_id):
	"""Pull a settlement from the gateway. Falls back to the CSV path when unavailable."""
	require_role(
		("Platform Billing Manager", "Platform Admin", "System Manager"),
		_("Working with settlements"),
	)
	from a3_sola.api.gateways.razorpay_client import get_client

	client = get_client()
	fetch = getattr(client, "fetch_settlement", None)
	if not fetch:
		frappe.throw(
			_("This gateway client cannot fetch settlements yet. Import the settlement "
			  "report as a CSV instead."),
			title=_("Use the CSV Import"),
		)
	return fetch(settlement_id)


def unreconciled_payments(days=None):
	"""Captured payments with no settlement line, and lines with no payment.

	The report that catches both gateway problems and integration bugs - each direction
	means something different, and neither should be discovered by an accountant months
	later.
	"""
	window = int(days or get_int("unreconciled_alert_days", 5) or 5)
	cutoff = add_days(today(), -window)

	settled = set(
		frappe.get_all(
			"Settlement Line",
			filters={"payment_transaction": ["is", "set"]},
			pluck="payment_transaction",
		)
	)
	orphan_payments = [
		row
		for row in frappe.get_all(
			"Payment Transaction",
			filters={"status": "Captured", "creation": ["<", cutoff]},
			fields=["name", "gateway_payment_id", "amount", "payment_order", "creation"],
			limit_page_length=0,
		)
		if row.name not in settled
	]
	orphan_lines = frappe.get_all(
		"Settlement Line",
		filters={"match_status": "Unmatched"},
		fields=["parent", "gateway_payment_id", "gross_amount", "settled_on"],
		limit_page_length=0,
	)
	return {"payments_without_settlement": orphan_payments, "settlement_lines_without_payment": orphan_lines}


def alert_on_unreconciled():
	"""Scheduled. Silence is the failure mode that goes unnoticed for weeks."""
	result = unreconciled_payments()
	payments_count = len(result["payments_without_settlement"])
	lines_count = len(result["settlement_lines_without_payment"])
	if payments_count or lines_count:
		frappe.log_error(
			title="a3_sola: unreconciled payments",
			message=(
				f"{payments_count} captured payment(s) have no settlement line, and "
				f"{lines_count} settlement line(s) match no payment. Both directions mean "
				"money this system cannot fully explain."
			),
		)
	frappe.logger("a3_sola").info(
		{"event": "unreconciled_scan", "payments": payments_count, "lines": lines_count}
	)
	return {"payments": payments_count, "lines": lines_count}


def gateway_health_check():
	"""Ping the gateway and check the webhook is still being fed.

	A gateway that stops answering is obvious. A webhook endpoint that quietly stops
	receiving is not, and that is the one that costs a month of revenue before anyone
	notices.
	"""
	import time

	from a3_sola.api.gateways.exceptions import GatewayError
	from a3_sola.api.gateways.razorpay_client import get_client

	started = time.monotonic()
	reachable, detail = True, None
	try:
		get_client().fetch_order("order_healthcheck")
	except GatewayError as exc:
		reachable, detail = False, str(exc)
	except Exception as exc:
		reachable, detail = False, str(exc)
	latency_ms = int((time.monotonic() - started) * 1000)

	window_hours = 24
	recent = frappe.db.count(
		"Payment Webhook Log",
		{"received_on": [">", frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-window_hours)]},
	)
	if not recent:
		frappe.log_error(
			title="a3_sola: no webhooks received",
			message=(
				f"No webhook has arrived in {window_hours} hours. Either nothing is being "
				"paid, or the endpoint has stopped being delivered to. Check the gateway's "
				"webhook configuration before assuming the former."
			),
		)

	frappe.logger("a3_sola").info(
		{
			"event": "gateway_health", "reachable": reachable, "latency_ms": latency_ms,
			"webhooks_24h": recent, "detail": detail,
		}
	)
	return {"reachable": reachable, "latency_ms": latency_ms, "webhooks_24h": recent}
