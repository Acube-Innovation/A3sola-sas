# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A loan application's bank documents, printed: the covering letter or the vendor
feasibility report, each one page on the company letterhead - as the Word files the bank
is used to.

Rendered from the same Solar Document Templates the lender pack is generated from, with
the application as its source, so a draft prints its own values. Nothing is saved.
"""

import frappe
from frappe import _

from a3_sola.api import documents
from a3_sola.www.a3solaportal.collections import load_record

SLUG = "loan-applications"
#: The documents Print gives, by the name the Print menu asks for, in order.
DOCUMENTS = {
	"letter": "BANK-COVERING-LOAN", "feasibility": "BANK-VENDOR-FEASIBILITY",
	"ehs": "BANK-EHS-CHECKLIST", "proposal": "BANK-PROJECT-PROPOSAL", "quotation": "BANK-QUOTATION",
}
PRINTED = ("BANK-COVERING-LOAN", "BANK-VENDOR-FEASIBILITY")
TITLES = {"letter": "Covering Letter", "feasibility": "Feasibility Report", "ehs": "EHS Checklist", "proposal": "Project Proposal", "quotation": "Quotation"}


@frappe.whitelist()
def pdf(name, document=None, download=0, signed=1):
	"""One `document` ("letter" or "feasibility"), or both when none is named, as a PDF to
	read in the browser or, with `download=1`, to save - with the company's signature and
	seal, or with `signed=0` without them, to sign by hand. Read with the caller's own
	permissions on the application."""
	if document and document not in DOCUMENTS:
		frappe.throw(_("Unknown document {0}.").format(document))
	from a3_sola.solar_operations.doctype.loan_application.loan_application import loan_defaults

	loan = load_record(SLUG, name, "read")
	inst = frappe.get_doc("Solar Installation", loan.solar_installation)
	# What the application leaves blank prints as the job knows it - on this copy only.
	for field, value in loan_defaults(inst).items():
		if value not in (None, "") and loan.get(field) in (None, "", 0):
			loan.set(field, value)
	pages = []
	for code in ([DOCUMENTS[document]] if document else PRINTED):
		tpl = _template(code, inst.company)
		context = documents.get_document_context(inst, tpl, source=(loan.doctype, loan.name))
		context.loan = context.task = context.source = loan
		pages.append(frappe.render_template(tpl.body_template or "", context))
	signed = frappe.utils.cint(signed)
	frappe.local.response.filename = documents.customer_file_name(documents.job_customer(inst),
		TITLES.get(document, "Loan Documents") + ("" if signed else " (unsigned)"))
	codes = [DOCUMENTS[document]] if document else PRINTED
	# The bank's documents are RIM's (the registered vendor's): on RIM's letterhead.
	head = documents.rim_letter_head()
	if len(codes) == 1 and codes[0] in documents.LETTERHEAD_FLOW_TEMPLATES:
		cover = documents.bank_proposal_cover(inst, context) if codes[0] == "BANK-PROJECT-PROPOSAL" else None
		content = documents.letterhead_flow_pdf(pages[0], inst.company, signed=bool(signed), letter_head=head, cover=cover)
	else:
		content = documents.letterhead_pdf(pages, inst.company, signed=bool(signed), letter_head=head)
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"


QUOTATION = "BANK-QUOTATION"


def quotation_url(installation):
	return "/api/method/a3_sola.api.loan_print.quotation?installation=" + frappe.utils.quote(installation)


@frappe.whitelist()
def quotation(installation, download=0, signed=1):
	"""The job's accepted quotation in the RIM format - the bank's Quotation, which reads the
	job and its quotation only - for a job with or without a loan (the PM Surya Ghar
	registration asks for it too). Read with the caller's own permissions on the job."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	if not has_quotation(inst):
		frappe.throw(_("{0} has no quotation or design estimate yet.").format(inst.name), frappe.ValidationError)
	tpl = _template(QUOTATION, inst.company)
	context = documents.get_document_context(inst, tpl, source=("Solar Installation", inst.name))
	signed = frappe.utils.cint(signed)
	page = frappe.render_template(tpl.body_template or "", context)
	frappe.local.response.filename = documents.customer_file_name(documents.job_customer(inst),
		"Quotation" + ("" if signed else " (unsigned)"))
	frappe.local.response.filecontent = documents.letterhead_flow_pdf(page, inst.company, signed=bool(signed),
		letter_head=documents.rim_letter_head())
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"


def has_quotation(inst):
	"""Whether the RIM quotation can print: the job has its quotation, or a design estimate to
	price one from."""
	if inst.get("quotation") and frappe.db.exists("Quotation", inst.quotation):
		return True
	est = inst.get("solar_design_estimate")
	return bool(est and frappe.db.get_value("Solar Design Estimate", est, "solar_package"))


def quotation_doc(inst):
	"""What the RIM quotation prints: the job's Quotation, else one priced from its design
	estimate as a quotation for that option would be (quotation_option.apply_option) - made
	for the print only, never saved."""
	if inst.get("quotation") and frappe.db.exists("Quotation", inst.quotation):
		return frappe.get_doc("Quotation", inst.quotation)
	if not has_quotation(inst):
		return None
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	from a3_sola.api.quotation_option import apply_option

	currency = frappe.db.get_value("Company", inst.company, "default_currency") or "INR"
	q = frappe.new_doc("Quotation")
	q.update({"company": inst.company, "transaction_date": frappe.utils.today(), "quotation_to": "Customer",
		"customer_name": inst.get("consumer_name") or "", "currency": currency, "conversion_rate": 1,
		"price_list_currency": currency, "plc_conversion_rate": 1,
		"selling_price_list": frappe.db.get_single_value("Selling Settings", "selling_price_list"),
		"solar_design_estimate": inst.solar_design_estimate})
	template = frappe.db.get_value("Sales Taxes and Charges Template", {"company": inst.company, "is_default": 1,
		"disabled": 0}, "name")
	if template:
		q.taxes_and_charges = template
		for tax in get_taxes_and_charges("Sales Taxes and Charges Template", template) or []:
			q.append("taxes", tax)
	apply_option(q)
	if not q.get("items"):
		return None
	# Numbered by the estimate it is priced from, until the job has a quotation of its own.
	q.name = inst.solar_design_estimate
	return q


def _template(code, company):
	name = frappe.db.get_value(
		"Solar Document Template", {"template_code": code, "company": company}, "name"
	) or frappe.db.get_value("Solar Document Template", {"template_code": code}, "name")
	if not name:
		frappe.throw(_("Document template {0} does not exist.").format(code))
	return frappe.get_cached_doc("Solar Document Template", name)
