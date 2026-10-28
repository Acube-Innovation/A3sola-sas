# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Agreement between Consumer & Vendor under PM Surya Ghar: Muft Bijli Yojana, as the
team's "05_PMSGY Vendor Agreement.docx" words it: executed on the day it is printed, between the
consumer - name, address - and the registered vendor, for the system's cost; the First Party's
six undertakings and the Second Party's sixteen clauses word for word, then both parties'
signatures, the vendor's signature and seal printed (`.a3s-sign`: hidden when unsigned).

Printed in the Accept Customer task (ACPT) on plain paper, as the Word file is, in its Book
Antiqua; also what the template MNRE-CONSUMER-VENDOR-AGREEMENT files when generated
(documents.generate_document). Nothing is saved here.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, getdate, today

from a3_sola.api import documents
from a3_sola.api.form1_print import _consumer, _row1
from a3_sola.api.kseb_covering_print import fonts

CODE = "MNRE-CONSUMER-VENDOR-AGREEMENT"
TITLE = "Consumer-Vendor Agreement"
#: Word's margins for the agreement, near enough all round (23mm top, 28mm sides).
MARGINS = "25mm"


def url(installation, download=False):
	return "/api/method/a3_sola.api.vendor_agreement_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download - signed and sealed, or without,
	as the panel's box says (`signable`). The system makes it: no upload."""
	return [{"label": _("View Vendor Agreement"), "url": url(installation), "signable": True},
		{"label": _("Download Vendor Agreement"), "url": url(installation, download=True), "signable": True}]


def context(inst):
	"""The agreement's blanks for the job `inst`: executed today; the cost is the contract's."""
	row1 = _row1(inst, _consumer(inst))
	company = frappe.get_cached_doc("Company", inst.company) if inst.get("company") else frappe._dict()
	cost = flt(inst.get("gross_contract_value"))
	return frappe._dict({
		"date": getdate(today()).strftime("%d/%m/%Y"),
		"name": row1["name"] or "",
		"address": row1["address"] or "",
		"vendor": company.get("registered_vendor_name") or company.get("company_name") or "",
		"vendor_address": ", ".join(x.strip().rstrip(",").strip()
			for x in (company.get("registered_vendor_address") or company.get("epc_address") or "").splitlines()
			if x.strip(" ,")),
		"cost": fmt_money(cost, precision=0 if cost == int(cost) else 2) if cost else "",
		"signature": documents.image_src(company.get("epc_signature_image")) if company else "",
		"stamp": documents.image_src(company.get("company_stamp_image")) if company else "",
	})


def file_name(inst, signed=True):
	return documents.customer_file_name(documents.job_customer(inst), TITLE + ("" if signed else " (unsigned)"))


def html(inst, signed=True):
	return frappe.render_template("a3_sola/templates/print/vendor_agreement.html",
		{"f": context(inst), "fonts": fonts(), "signed": signed})


def render(inst, signed=True):
	"""(file name, PDF) of the agreement for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	# Two pages that flow, as the Word file: a fixed letter sheet would cut it at one.
	return file_name(inst, signed), documents.plain_pdf(html(inst, signed), margins=MARGINS)


@frappe.whitelist()
def pdf(installation, download=0, signed=1):
	"""The agreement, shown in the browser; saved as a file with `download`; with the vendor's
	signature and seal, or with `signed=0` without them, to sign by hand."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst, bool(cint(signed)))
	frappe.local.response.type = "download" if cint(download) else "pdf"
