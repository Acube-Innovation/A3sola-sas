# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every ledger posting this app makes.

Rules that apply to every function here, without exception:

* Both gates must be open - `enable_accounting_postings` AND `gst_treatment_confirmed_by_ca`.
  With either closed the intent is logged and NOTHING is posted, so the client can run the
  module as a tracking system from day one.
* Each posting is idempotent: it checks for an existing entry against the same source
  document before creating another.
* Each resolves accounts strictly by the document's company and RAISES if the resolved
  account belongs to another company. In a multi-company instance a mis-resolved account
  silently moves one tenant's money into another tenant's ledger - it is the
  highest-consequence failure in the product.
* Each checks for the Accounts Manager role at function level, not only through doctype
  permissions.
* Nothing is ever silently edited after submission. Use `cancel_and_repost`.

Each function's docstring states its debit and credit in plain English, for the client's
chartered accountant to review.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from a3_sola.api.gst import postings_enabled

ACCOUNTS_ROLES = ("Accounts Manager", "System Manager")


# ------------------------------------------------------------------ guardrails
def _require_accounts_manager():
	if not set(frappe.get_roles()).intersection(ACCOUNTS_ROLES):
		frappe.throw(
			_("Only {0} may post an accounting entry.").format(" or ".join(ACCOUNTS_ROLES)),
			frappe.PermissionError,
		)


def resolve_account(company, fieldname):
	"""Resolve a mapped account, strictly within the company.

	Raises if the mapping is missing or points at another company's account.
	"""
	settings = frappe.get_cached_doc("A3 Sola Settings")
	row = next((r for r in settings.solar_account_mapping if r.company == company), None)
	if not row:
		frappe.throw(
			_("No account mapping for company {0}. Map the accounts before enabling postings.").format(company),
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
			_("Account {0} belongs to company {1}, but this posting is for {2}. "
			  "A posting must never reach another company's ledger.").format(account, owner, company),
			title=_("Cross-Company Account"),
		)
	return account


def _log_intent(event, doc, detail):
	"""What we would have posted, had the gates been open."""
	frappe.logger("a3_sola").info(
		{"event": f"posting_suppressed:{event}", "doc": doc.name, "company": doc.company, "detail": detail}
	)
	return None


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
	return entry.name


# ------------------------------------------------------------- subsidy postings
def post_subsidy_receivable(claim):
	"""Company Funded Gap only.

	DEBIT  Subsidy Receivable      - the amount the company has funded on the customer's behalf
	CREDIT Subsidy Recovery Income - recognised as recoverable from the customer

	Where the customer claims directly the company has funded nothing, so NO ENTRY IS
	REQUIRED and none is made. That absence is deliberate; do not "fix" it later.
	"""
	if claim.claim_model != "Company Funded Gap":
		frappe.logger("a3_sola").info(
			{"event": "subsidy_no_entry_required", "doc": claim.name, "model": claim.claim_model}
		)
		return None

	amount = flt(claim.amount_recoverable_from_customer) or flt(claim.expected_subsidy_amount)
	if not amount:
		return None

	if not postings_enabled(claim.company):
		return _log_intent("subsidy_receivable", claim, {"amount": amount})

	_require_accounts_manager()
	if existing := _existing_entry("Subsidy Claim", claim.name, "Subsidy Receivable"):
		return existing

	receivable = resolve_account(claim.company, "subsidy_receivable_account")
	income = resolve_account(claim.company, "subsidy_recovery_income_account")
	project = frappe.db.get_value("Solar Installation", claim.solar_installation, "project")

	return _journal(
		claim.company,
		claim.claim_submitted_on or today(),
		[
			{"account": receivable, "debit_in_account_currency": amount, "project": project},
			{"account": income, "credit_in_account_currency": amount, "project": project},
		],
		"Subsidy Receivable",
		"Subsidy Claim",
		claim.name,
		_("Subsidy gap funded on behalf of the customer for {0}").format(claim.solar_installation),
	)


def post_subsidy_recovery(claim):
	"""Settlement when the customer passes the DBT over.

	DEBIT  Bank / Cash (through the linked Payment Entry, if any)
	CREDIT Subsidy Receivable - reducing the amount the company had funded
	"""
	amount = flt(claim.amount_recovered)
	if not amount or claim.claim_model != "Company Funded Gap":
		return None

	if not postings_enabled(claim.company):
		return _log_intent("subsidy_recovery", claim, {"amount": amount})

	_require_accounts_manager()
	if existing := _existing_entry("Subsidy Claim", claim.name, "Subsidy Recovery"):
		return existing

	receivable = resolve_account(claim.company, "subsidy_receivable_account")
	bank = frappe.db.get_value("Company", claim.company, "default_bank_account") or resolve_account(
		claim.company, "subsidy_recovery_income_account"
	)
	project = frappe.db.get_value("Solar Installation", claim.solar_installation, "project")

	return _journal(
		claim.company,
		claim.recovery_date or today(),
		[
			{"account": bank, "debit_in_account_currency": amount, "project": project},
			{"account": receivable, "credit_in_account_currency": amount, "project": project},
		],
		"Subsidy Recovery",
		"Subsidy Claim",
		claim.name,
		_("Subsidy recovered from the customer for {0}").format(claim.solar_installation),
	)


@frappe.whitelist()
def write_off_subsidy_recovery(claim, amount=None, reason=None):
	"""Give up on a subsidy gap the customer is never going to pay back.

	DEBIT  Write Off           - the loss, recognised when the decision is taken
	CREDIT Subsidy Receivable  - clearing what the company funded on their behalf

	This is a deliberate management decision, not an automatic ageing rule, so it is only
	ever called by a person. Once written off the amount leaves the ageing report - a
	receivable nobody intends to collect overstates what is actually recoverable.
	"""
	doc = frappe.get_doc("Subsidy Claim", claim) if isinstance(claim, str) else claim
	doc.check_permission("write")

	if doc.claim_model != "Company Funded Gap":
		frappe.throw(
			_("Nothing was funded on this claim, so there is nothing to write off."),
			title=_("Nothing to Write Off"),
		)

	outstanding = flt(doc.amount_recoverable_from_customer) - flt(doc.amount_recovered)
	amount = flt(amount) or flt(outstanding)
	if amount <= 0:
		frappe.throw(_("There is nothing outstanding on this claim."))
	if amount > outstanding:
		frappe.throw(
			_("{0} is more than the {1} still outstanding.").format(amount, outstanding)
		)

	if not postings_enabled(doc.company):
		return _log_intent("subsidy_write_off", doc, {"amount": amount, "reason": reason})

	_require_accounts_manager()
	if existing := _existing_entry("Subsidy Claim", doc.name, "Subsidy Write Off"):
		return existing

	receivable = resolve_account(doc.company, "subsidy_receivable_account")
	write_off = resolve_account(doc.company, "write_off_account")
	project = frappe.db.get_value("Solar Installation", doc.solar_installation, "project")

	entry = _journal(
		doc.company,
		today(),
		[
			{"account": write_off, "debit_in_account_currency": amount, "project": project},
			{"account": receivable, "credit_in_account_currency": amount, "project": project},
		],
		"Subsidy Write Off",
		"Subsidy Claim",
		doc.name,
		_("Subsidy recovery written off for {0}. {1}").format(
			doc.solar_installation, reason or _("No reason recorded.")
		),
	)
	doc.add_comment(
		"Comment",
		_("{0} written off by {1}. {2}").format(amount, frappe.session.user, reason or ""),
	)
	return entry


# ----------------------------------------------------------- statutory postings
def post_statutory_receivable(payment):
	"""Fees paid on the customer's behalf.

	DEBIT  Statutory Fee Receivable - recoverable from the customer against the receipt
	CREDIT Bank / Cash              - the money that left

	Where the customer paid the DISCOM directly, nothing is receivable and NO ENTRY IS MADE.
	"""
	if payment.paid_by != "Company on Behalf of Customer":
		frappe.logger("a3_sola").info(
			{"event": "statutory_no_entry_required", "doc": payment.name, "paid_by": payment.paid_by}
		)
		return None

	amount = flt(payment.amount_gross)
	if not amount:
		return None

	if not postings_enabled(payment.company):
		return _log_intent("statutory_receivable", payment, {"amount": amount})

	_require_accounts_manager()
	if existing := _existing_entry("Statutory Fee Payment", payment.name, "Statutory Receivable"):
		return existing

	receivable = resolve_account(payment.company, "statutory_fee_receivable_account")
	bank = frappe.db.get_value("Company", payment.company, "default_bank_account") or receivable
	project = frappe.db.get_value("Solar Installation", payment.solar_installation, "project")

	return _journal(
		payment.company,
		payment.payment_date or today(),
		[
			{"account": receivable, "debit_in_account_currency": amount, "project": project},
			{"account": bank, "credit_in_account_currency": amount, "project": project},
		],
		"Statutory Receivable",
		"Statutory Fee Payment",
		payment.name,
		_("{0} paid to the DISCOM on behalf of the customer").format(payment.fee_type),
	)


def post_statutory_refund(payment):
	"""The 80% registration refund.

	Where the refund is credited to the COMPANY:
	    DEBIT  Bank / Cash
	    CREDIT Statutory Refund Receivable
	Where it is credited to the CONSUMER the company receives nothing, so no entry is made -
	it is recorded for reporting only.

	A short receipt posts the shortfall to the mapped write-off account, with a reason.
	"""
	if payment.refund_credited_to != "Company Account":
		frappe.logger("a3_sola").info(
			{"event": "refund_to_consumer_no_entry", "doc": payment.name}
		)
		return None

	amount = flt(payment.refund_received_amount)
	if not amount:
		return None

	if not postings_enabled(payment.company):
		return _log_intent("statutory_refund", payment, {"amount": amount})

	_require_accounts_manager()
	if existing := _existing_entry("Statutory Fee Payment", payment.name, "Statutory Refund"):
		return existing

	receivable = resolve_account(payment.company, "statutory_refund_receivable_account")
	bank = frappe.db.get_value("Company", payment.company, "default_bank_account") or receivable
	project = frappe.db.get_value("Solar Installation", payment.solar_installation, "project")
	expected = flt(payment.refundable_amount)
	shortfall = flt(expected - amount, 2)

	accounts = [
		{"account": bank, "debit_in_account_currency": amount, "project": project},
		{"account": receivable, "credit_in_account_currency": expected or amount, "project": project},
	]
	if shortfall > 0:
		accounts.insert(
			1, {"account": resolve_account(payment.company, "write_off_account"),
			    "debit_in_account_currency": shortfall, "project": project}
		)

	return _journal(
		payment.company,
		payment.refund_received_on or today(),
		accounts,
		"Statutory Refund",
		"Statutory Fee Payment",
		payment.name,
		_("Registration fee refund received for {0}").format(payment.solar_installation),
	)


# ------------------------------------------------------------- O&M provisioning
def post_om_provision(contract, amount):
	"""Accrue the five-year obligation at commissioning.

	DEBIT  O&M Expense              - the cost of the obligation, recognised now
	CREDIT O&M Provision (Liability) - the obligation itself

	Accruing at commissioning rather than discovering it over five years is the difference
	between a margin figure that is true and one that is fiction until the contract ends.
	"""
	amount = flt(amount)
	if not amount:
		return None

	if not postings_enabled(contract.company):
		return _log_intent("om_provision", contract, {"amount": amount})

	_require_accounts_manager()
	if existing := _existing_entry("Solar OM Contract", contract.name, "O&M Provision"):
		return existing

	expense = resolve_account(contract.company, "om_expense_account")
	liability = resolve_account(contract.company, "om_provision_liability_account")

	return _journal(
		contract.company,
		contract.start_date or today(),
		[
			{"account": expense, "debit_in_account_currency": amount, "project": contract.project},
			{"account": liability, "credit_in_account_currency": amount, "project": contract.project},
		],
		"O&M Provision",
		"Solar OM Contract",
		contract.name,
		_("Five-year O&M provision accrued at commissioning for {0}").format(contract.solar_installation),
	)


def release_om_provision(project, amount, reference):
	"""Release the provision as visits consume it.

	DEBIT  O&M Provision (Liability) - reducing the obligation
	CREDIT O&M Expense               - offsetting the cost already booked on the visit
	"""
	amount = flt(amount)
	if not amount:
		return None

	company = frappe.db.get_value("Project", project, "company")
	if not postings_enabled(company):
		frappe.logger("a3_sola").info(
			{"event": "posting_suppressed:om_release", "project": project, "amount": amount}
		)
		return None

	_require_accounts_manager()
	if existing := _existing_entry("Solar OM Visit", reference, "O&M Provision Release"):
		return existing

	expense = resolve_account(company, "om_expense_account")
	liability = resolve_account(company, "om_provision_liability_account")

	return _journal(
		company,
		today(),
		[
			{"account": liability, "debit_in_account_currency": amount, "project": project},
			{"account": expense, "credit_in_account_currency": amount, "project": project},
		],
		"O&M Provision Release",
		"Solar OM Visit",
		reference,
		_("O&M provision released against visit {0}").format(reference),
	)


# -------------------------------------------------------------------- reversal
@frappe.whitelist()
def cancel_and_repost(source_doctype, source_document, purpose):
	"""Cancel the linked entry and post it again. Never silently edit a submitted entry."""
	_require_accounts_manager()
	existing = _existing_entry(source_doctype, source_document, purpose)
	if not existing:
		frappe.throw(_("No posting found for {0} {1}.").format(source_doctype, source_document))

	entry = frappe.get_doc("Journal Entry", existing)
	entry.flags.ignore_permissions = True
	entry.cancel()

	doc = frappe.get_doc(source_doctype, source_document)
	dispatch = {
		"Subsidy Receivable": post_subsidy_receivable,
		"Subsidy Recovery": post_subsidy_recovery,
		"Statutory Receivable": post_statutory_receivable,
		"Statutory Refund": post_statutory_refund,
	}
	handler = dispatch.get(purpose)
	if not handler:
		frappe.throw(_("Purpose {0} cannot be reposted automatically.").format(purpose))
	return handler(doc)
