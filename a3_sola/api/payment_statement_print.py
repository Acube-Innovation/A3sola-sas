# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Payment Statement: the letter confirming to the customer what has been received and
what is still payable, as the team's "Rajesh P A due amount" lays it out - the date, the
customer, then one table:

    the project cost (the contract, structure included), the meter, the KSEB fees, their total;
    each payment received (its mode; its date in a column of its own), the meter and KSEB fees
    the customer paid back,
    the total received; the special discount; the balance payable

then the firm's regards, signature and seal. It reads the job's payment schedule (its billing
plan: the payments Accounts confirmed, the discount, the fees reimbursed) on the day it is
printed. The same statement is offered on each payment task (ADV, BAL, PCOM); nothing is saved.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, formatdate, today

from a3_sola.api import billing, documents
from a3_sola.api.form1_print import _consumer, _row1
from a3_sola.api.kseb_covering_print import fonts

CODE = "PAYMENT-STATEMENT"
TITLE = "Payment Statement"
TASKS = ("ADV", "BAL", "PCOM")
#: Word's margins for the letter: 30mm top, 25.4mm each side.
MARGINS = "30mm 25.4mm 0 25.4mm"
#: How the statement names a mode of payment, as the letter writes it: "(Bank)".
MODE_WORDS = {"Bank Transfer": "Bank", "Loan Disbursement": "Loan"}


def url(installation, download=False):
	return "/api/method/a3_sola.api.payment_statement_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download - signed and sealed, or without,
	as the panel's box says (`signable`). The system makes it: no upload."""
	return [{"label": _("View Payment Statement"), "url": url(installation), "signable": True},
		{"label": _("Download Payment Statement"), "url": url(installation, download=True), "signable": True}]


def amount_text(value):
	"""Rupees as the letter writes them: 2,15,000/- (paise only when there are any)."""
	value = flt(value, 2)
	return fmt_money(value, precision=0 if value == int(value) else 2) + "/-"


def context(inst):
	"""The letter's lines for the job `inst`: [{n, label, amount, bold}] and its addressee."""
	consumer = _consumer(inst)
	row1 = _row1(inst, consumer)
	plan = billing.plan_of(inst)
	lines = []

	def line(label, amount, bold=False, date=None):
		lines.append({"n": len(lines) + 1, "label": label, "amount": flt(amount, 2), "text": amount_text(amount), "bold": bold,
			"date": formatdate(date, "dd/MM/yyyy") if date else ""})
		return len(lines)

	cost = [line(_("Total Project Cost Including Structure"), inst.get("gross_contract_value"))]
	meter = flt(inst.get("net_meter_charge")) if inst.get("net_meter_mode") != "Availed from DISCOM on Rental" else 0
	if meter:
		cost.append(line(_("Meter"), meter))
	kseb = flt(inst.get("kseb_application_fee")) + flt(inst.get("kseb_registration_fee"))
	if kseb:
		cost.append(line(_("KSEB"), kseb))
	total = sum(lines[n - 1]["amount"] for n in cost)
	line(_("Total cost ({0})").format("+".join(str(n) for n in cost)), total, bold=True)

	paid = []
	confirmed = sorted((p for p in (plan.get("payments") if plan else []) or [] if p.status == "Confirmed"),
		key=lambda p: (str(p.payment_date or ""), p.idx))
	for p in confirmed:
		mode = MODE_WORDS.get(p.payment_mode, p.payment_mode or "")
		# The day it was received has a column of its own.
		paid.append(line(_("Payment received{0}").format(" ({0})".format(mode) if mode else ""), p.amount,
			date=p.payment_date))
	fees = flt(plan.get("statutory_reimbursed")) if plan else 0
	if fees:
		paid.append(line(_("Meter and KSEB amount received"), fees))
	received = sum(lines[n - 1]["amount"] for n in paid)
	if paid:
		line(_("Total Amount received ({0})").format("+".join(str(n) for n in paid)), received, bold=True)
	discount = flt(plan.get("special_discount")) if plan else 0
	if discount:
		line(_("Special Discount"), discount)
	balance = flt(total - received - discount, 2)
	line(_("Balance Payable") if balance >= 0 else _("Received in Excess"), abs(balance), bold=True)

	company = frappe.get_cached_doc("Company", inst.company) if inst.get("company") else frappe._dict()
	return frappe._dict({
		"date": formatdate(today(), "dd.MM.yyyy"),
		"name": (row1["name"] or "").upper(),
		"address": (row1["address"] or "").upper(),
		"lines": lines,
		"balance": balance,
		"firm": company.get("epc_name") or company.get("company_name") or inst.get("company") or "",
		"signature": documents.image_src(company.get("epc_signature_image")) if company else "",
		"stamp": documents.image_src(company.get("company_stamp_image")) if company else "",
	})


def file_name(inst, signed=True):
	return "{0} - {1}{2}.pdf".format(TITLE, inst.consumer_name or inst.name, "" if signed else " (unsigned)")


def html(inst):
	return frappe.render_template("a3_sola/templates/print/payment_statement.html", {"f": context(inst), "fonts": fonts()})


def render(inst, signed=True):
	"""(file name, PDF) of the statement for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	return file_name(inst, signed), documents.letterhead_pdf(html(inst), inst.company, signed=signed, letterhead=False,
		margins=MARGINS)


@frappe.whitelist()
def pdf(installation, download=0, signed=1):
	"""The statement, shown in the browser; saved as a file with `download`; with the
	signature and seal, or with `signed=0` without them, to sign by hand."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst, bool(cint(signed)))
	frappe.local.response.type = "download" if cint(download) else "pdf"
