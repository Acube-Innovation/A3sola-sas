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
	frappe.local.response.filename = "{0} - {1}{2}.pdf".format(
		TITLES.get(document, "Loan Documents"), loan.name, "" if signed else " (unsigned)"
	)
	codes = [DOCUMENTS[document]] if document else PRINTED
	if len(codes) == 1 and codes[0] in documents.LETTERHEAD_FLOW_TEMPLATES:
		content = documents.letterhead_flow_pdf(pages[0], inst.company, signed=bool(signed))
	else:
		content = documents.letterhead_pdf(pages, inst.company, signed=bool(signed))
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
	if not (inst.get("quotation") and frappe.db.exists("Quotation", inst.quotation)):
		frappe.throw(_("{0} has no quotation yet.").format(inst.name), frappe.ValidationError)
	tpl = _template(QUOTATION, inst.company)
	context = documents.get_document_context(inst, tpl, source=("Solar Installation", inst.name))
	signed = frappe.utils.cint(signed)
	page = frappe.render_template(tpl.body_template or "", context)
	frappe.local.response.filename = "Quotation - {0}{1}.pdf".format(inst.consumer_name or inst.name,
		"" if signed else " (unsigned)")
	frappe.local.response.filecontent = documents.letterhead_flow_pdf(page, inst.company, signed=bool(signed))
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"


def _template(code, company):
	name = frappe.db.get_value(
		"Solar Document Template", {"template_code": code, "company": company}, "name"
	) or frappe.db.get_value("Solar Document Template", {"template_code": code}, "name")
	if not name:
		frappe.throw(_("Document template {0} does not exist.").format(code))
	return frappe.get_cached_doc("Solar Document Template", name)
