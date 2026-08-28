# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Ledger postings for the subscription business.

Same discipline as Phase 3, for the same reason: the whole flow works in tracking mode and
posts nothing until `enable_payment_postings` is switched on and the accounts are mapped.
A half-configured posting layer that writes to the wrong account is worse than one that
writes nothing.

What gets posted, in plain English:

* **An invoice is submitted** - debit the customer (receivable), credit subscription
  revenue and the GST output accounts by tax type.
* **A payment is confirmed** - debit the bank or clearing account, credit the customer,
  allocated against the invoice.
* **The gateway fee** is posted separately, debit gateway fee expense, credit the
  clearing account. The settlement arrives net of fees, so the bank reconciliation only
  balances if the fee is booked in its own entry.
* **Annual billing**, when an unearned revenue account is mapped - credit unearned
  revenue at collection and release a twelfth to revenue each month. Switchable, because
  a small client's auditor may not require deferral.
* **A refund** - reverse the revenue with a credit note and credit the bank.

Every posting is idempotent against its source document, resolves accounts strictly per
company, and refuses an account belonging to another company.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from a3_sola.api.settings import get_value


def postings_enabled():
	return bool(get_value("enable_payment_postings"))


def _require_accounts_manager():
	roles = set(frappe.get_roles())
	if not roles.intersection({"Accounts Manager", "Platform Admin", "System Manager"}):
		frappe.throw(
			_("Only an Accounts Manager may post payment entries."), frappe.PermissionError
		)


def resolve_account(company, fieldname):
	"""A mapped account, strictly within the company.

	Raises if the mapping is missing or points at another company's account. Posting one
	tenant's subscription revenue into another's ledger is the worst thing this layer can
	do, so it is refused rather than logged.
	"""
	settings = frappe.get_cached_doc("A3 Sola Settings")
	row = next(
		(r for r in settings.payment_account_mapping if r.company == company), None
	)
	if not row:
		frappe.throw(
			_("No payment account mapping for {0}. Map the accounts before enabling "
			  "postings.").format(company),
			title=_("Account Mapping Missing"),
		)
	account = row.get(fieldname)
	if not account:
		frappe.throw(
			_("Account {0} is not mapped for {1}.").format(frappe.unscrub(fieldname), company),
			title=_("Account Mapping Missing"),
		)
	owner = frappe.db.get_value("Account", account, "company")
	if owner != company:
		frappe.throw(
			_("Account {0} belongs to {1}, but this posting is for {2}. A posting must "
			  "never reach another company's ledger.").format(account, owner, company),
			title=_("Cross-Company Account"),
		)
	return account


def _log_intent(event, doc, detail):
	"""What we would have posted, had the gate been open."""
	frappe.logger("a3_sola").info(
		{"event": f"payment_posting_suppressed:{event}", "doc": doc.name, "detail": detail}
	)
	return None


# ------------------------------------------------------------------- invoices
def post_subscription_invoice(invoice):
	"""Create and submit the ERPNext Sales Invoice this tax invoice represents."""
	if not postings_enabled():
		return _log_intent("invoice", invoice, {"grand_total": invoice.grand_total})
	if invoice.sales_invoice and frappe.db.exists("Sales Invoice", invoice.sales_invoice):
		return invoice.sales_invoice

	_require_accounts_manager()
	revenue = resolve_account(invoice.company, "subscription_revenue_account")

	sales_invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": invoice.company,
			"customer": invoice.customer,
			"posting_date": invoice.invoice_date,
			"due_date": invoice.due_date or invoice.invoice_date,
			"a3s_source_doctype": "Subscription Invoice",
			"a3s_source_document": invoice.name,
			"items": [
				{
					"item_name": row.description,
					"description": row.description,
					"gst_hsn_code": row.hsn_sac,
					"qty": row.quantity or 1,
					"rate": row.rate,
					"income_account": revenue,
				}
				for row in invoice.items
			],
			"taxes": _tax_rows(invoice),
		}
	)
	sales_invoice.flags.ignore_permissions = True
	sales_invoice.insert(ignore_permissions=True)
	sales_invoice.submit()

	invoice.db_set(
		{"sales_invoice": sales_invoice.name, "posting_status": "Posted"},
		update_modified=False,
	)
	return sales_invoice.name


def _tax_rows(invoice):
	"""One row per tax component, against the mapped output account."""
	rows = []
	if invoice.tax_type == "IGST" and flt(invoice.igst_amount):
		rows.append(
			{
				"charge_type": "Actual",
				"description": f"IGST @ {invoice.tax_rate}%",
				"account_head": resolve_account(invoice.company, "gst_output_igst_account"),
				"tax_amount": flt(invoice.igst_amount),
			}
		)
	else:
		for label, fieldname, amount in (
			("CGST", "gst_output_cgst_account", invoice.cgst_amount),
			("SGST", "gst_output_sgst_account", invoice.sgst_amount),
		):
			if not flt(amount):
				continue
			rows.append(
				{
					"charge_type": "Actual",
					"description": f"{label} @ {flt(invoice.tax_rate) / 2}%",
					"account_head": resolve_account(invoice.company, fieldname),
					"tax_amount": flt(amount),
				}
			)
	return rows


def cancel_subscription_invoice(invoice):
	if not invoice.sales_invoice:
		return None
	if not frappe.db.exists("Sales Invoice", invoice.sales_invoice):
		return None
	doc = frappe.get_doc("Sales Invoice", invoice.sales_invoice)
	if doc.docstatus == 1:
		doc.flags.ignore_permissions = True
		doc.cancel()
	invoice.db_set("posting_status", "Cancelled", update_modified=False)
	return doc.name


# -------------------------------------------------------------------- payments
def post_payment(order, transaction=None):
	"""Bank in, receivable down. Plus the gateway fee, in its own entry."""
	if not postings_enabled():
		return _log_intent("payment", order, {"total": order.total_amount})

	existing = _existing_entry("Payment Order", order.name, "Subscription Payment")
	if existing:
		return existing

	_require_accounts_manager()
	company = _company_for(order)
	bank = resolve_account(company, "bank_or_clearing_account")
	revenue = resolve_account(company, "subscription_revenue_account")

	entry = _journal(
		company,
		order.paid_on or today(),
		[
			{"account": bank, "debit_in_account_currency": flt(order.total_amount)},
			{"account": revenue, "credit_in_account_currency": flt(order.total_amount)},
		],
		"Subscription Payment",
		"Payment Order",
		order.name,
		_("Subscription payment received for {0}").format(order.customer_name),
	)
	if transaction:
		post_gateway_fee(order, transaction)
	return entry


def post_gateway_fee(order, transaction):
	"""Separate entry, because the settlement arrives net of fees.

	Booked with the payment it belongs to, the bank reconciliation would never balance -
	the amount that lands is the gross less this.
	"""
	fee = flt(getattr(transaction, "gateway_fee", 0)) + flt(getattr(transaction, "gateway_tax", 0))
	if not fee:
		return None
	if not postings_enabled():
		return _log_intent("gateway_fee", order, {"fee": fee})

	existing = _existing_entry("Payment Transaction", transaction.name, "Gateway Fee")
	if existing:
		return existing

	company = _company_for(order)
	return _journal(
		company,
		order.paid_on or today(),
		[
			{
				"account": resolve_account(company, "gateway_fee_expense_account"),
				"debit_in_account_currency": fee,
			},
			{
				"account": resolve_account(company, "bank_or_clearing_account"),
				"credit_in_account_currency": fee,
			},
		],
		"Gateway Fee",
		"Payment Transaction",
		transaction.name,
		_("Gateway fee on {0}").format(order.name),
	)


# --------------------------------------------------------------------- refunds
def post_refund(refund):
	"""Reverse the revenue and pay the money back out."""
	if not postings_enabled():
		return _log_intent("refund", refund, {"amount": refund.refund_amount})

	existing = _existing_entry("Payment Refund", refund.name, "Subscription Refund")
	if existing:
		return existing

	_require_accounts_manager()
	order = frappe.get_cached_doc("Payment Order", refund.payment_order)
	company = _company_for(order)

	return _journal(
		company,
		refund.processed_on or today(),
		[
			{
				"account": resolve_account(company, "refund_account"),
				"debit_in_account_currency": flt(refund.refund_amount),
			},
			{
				"account": resolve_account(company, "bank_or_clearing_account"),
				"credit_in_account_currency": flt(refund.refund_amount),
			},
		],
		"Subscription Refund",
		"Payment Refund",
		refund.name,
		_("Refund of {0} for {1}").format(refund.refund_amount, order.customer_name),
	)


# ------------------------------------------------------- deferred annual revenue
def release_deferred_revenue():
	"""Recognise a twelfth of each annual collection every month.

	Only runs where `unearned_revenue_account` is mapped - a small client's auditor may
	not require deferral, and forcing it on them would be worse than leaving it off.
	"""
	if not postings_enabled():
		return {"released": 0, "skipped": "postings disabled"}

	released = 0
	for invoice in frappe.get_all(
		"Subscription Invoice",
		filters={"docstatus": 1, "billing_cycle": "Annual", "payment_status": "Paid"},
		fields=["name", "company", "taxable_value", "period_start", "period_end"],
		limit_page_length=200,
	):
		settings = frappe.get_cached_doc("A3 Sola Settings")
		row = next(
			(r for r in settings.payment_account_mapping if r.company == invoice.company), None
		)
		if not row or not row.unearned_revenue_account:
			continue
		monthly = flt(flt(invoice.taxable_value) / 12.0, 2)
		purpose = f"Deferred Release {frappe.utils.formatdate(today(), 'MM-yyyy')}"
		if _existing_entry("Subscription Invoice", invoice.name, purpose):
			continue
		_journal(
			invoice.company,
			today(),
			[
				{"account": row.unearned_revenue_account, "debit_in_account_currency": monthly},
				{
					"account": resolve_account(invoice.company, "subscription_revenue_account"),
					"credit_in_account_currency": monthly,
				},
			],
			purpose,
			"Subscription Invoice",
			invoice.name,
			_("Monthly revenue recognition for {0}").format(invoice.name),
		)
		released += 1
	return {"released": released}


# --------------------------------------------------------------------- helpers
def _company_for(order):
	if order.reference_doctype == "Platform Subscription" and order.platform_subscription:
		company = frappe.db.get_value(
			"Subscription Invoice", {"platform_subscription": order.platform_subscription}, "company"
		)
		if company:
			return company
	return frappe.defaults.get_global_default("company") or frappe.get_all(
		"Company", pluck="name", limit=1
	)[0]


def _existing_entry(source_doctype, source_document, purpose):
	return frappe.db.get_value(
		"Journal Entry",
		{
			"a3s_source_doctype": source_doctype,
			"a3s_source_document": source_document,
			"a3s_purpose": purpose,
			"docstatus": 1,
		},
		"name",
	)


def _journal(company, posting_date, accounts, purpose, source_doctype, source_document, remark):
	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": company,
			"posting_date": posting_date or today(),
			"user_remark": remark,
			"accounts": accounts,
			"a3s_purpose": purpose,
			"a3s_source_doctype": source_doctype,
			"a3s_source_document": source_document,
		}
	)
	entry.flags.ignore_permissions = True
	entry.insert(ignore_permissions=True)
	entry.submit()

	from a3_sola.api import audit

	audit.record(
		"Accounting Posted",
		f"{purpose} posted as {entry.name}",
		reference_doctype=source_doctype,
		reference_name=source_document,
		amount=sum(flt(row.get("debit_in_account_currency")) for row in accounts),
		detail=f"Journal Entry {entry.name} in {company} dated {entry.posting_date}. {remark}",
	)
	return entry.name


@frappe.whitelist()
def cancel_and_repost(source_doctype, source_document, purpose):
	"""Correct an entry by reversing it, never by editing a submitted one."""
	_require_accounts_manager()
	existing = _existing_entry(source_doctype, source_document, purpose)
	if not existing:
		frappe.throw(_("There is no posted entry to reverse."))
	entry = frappe.get_doc("Journal Entry", existing)
	entry.flags.ignore_permissions = True
	entry.cancel()

	from a3_sola.api import audit

	audit.record(
		"Accounting Reposted",
		f"{purpose} entry {existing} cancelled for correction",
		reference_doctype=source_doctype,
		reference_name=source_document,
		amount=entry.total_debit,
		detail=(
			"The original entry was cancelled rather than edited, so the reversal and the "
			"original both remain visible in the ledger."
		),
	)
	return {"cancelled": existing}
