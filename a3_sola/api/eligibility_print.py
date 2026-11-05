# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer's documents as a PDF, from the subsidy eligibility check: each document read
by OCR - the KSEB bill, the Aadhaar card, the bank proof - and each detail with what every
document says (api/document_evidence). Where documents spell a detail two ways the paper says
so plainly: the subsidy is paid only when the customer's documents agree, so a difference may
leave the customer not eligible until it is corrected.

It goes to the customer from the check's page: viewed, downloaded, or sent by WhatsApp or
email (api/portal_share), so they can see what has to be put right.
"""

import frappe
from frappe import _
from frappe.utils import format_date, today

from a3_sola.api import document_evidence, documents

CHECK = "Subsidy Eligibility Check"


def url(name, download=False):
	return "/api/method/a3_sola.api.eligibility_print.pdf?name=" + frappe.utils.quote(name) + ("&download=1" if download else "")


def file_name(doc):
	customer = (doc.get("consumer_name") or doc.name).replace("/", "-")
	return "Document Check - {0} - {1}.pdf".format(customer, doc.name)


def context(doc):
	found = document_evidence.evidence(doc)
	confirmed = bool(found["conflicts"]) and doc.get("documents_confirmed") == found["signature"]
	by = doc.get("documents_confirmed_by")
	return {
		"doc": doc,
		"date": format_date(today(), "dd-MM-yyyy"),
		"customer": doc.get("consumer_name") or "",
		"consumer_number": doc.get("consumer_number") or "",
		"scheme": (frappe.get_cached_value("Subsidy Scheme", doc.subsidy_scheme, frappe.get_meta("Subsidy Scheme").title_field or "name")
			if doc.get("subsidy_scheme") else "") or doc.get("subsidy_scheme") or "",
		"result": doc.get("overall_result") or "",
		"documents": [d for d in found["documents"]],
		"details": found["details"],
		"conflicts": found["conflicts"],
		"record_differs": found["record_differs"],
		"load": found["load"],
		"confirmed": confirmed,
		"confirmed_by": (frappe.db.get_value("User", by, "full_name") or by) if confirmed and by else "",
		"confirmed_on": format_date(doc.get("documents_confirmed_on"), "dd-MM-yyyy") if confirmed else "",
	}


def render(doc):
	"""(file name, PDF) of the customer's document check, on the company's letterhead - every
	page, however long it runs."""
	html = frappe.render_template("a3_sola/templates/print/eligibility_documents.html", context(doc))
	return file_name(doc), documents.letterhead_flow_pdf(html, doc.get("company"))


@frappe.whitelist()
def pdf(name, download=0):
	"""The document check, shown in the browser; saved as a file with `download`."""
	doc = frappe.get_doc(CHECK, name)
	doc.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(doc)
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"
