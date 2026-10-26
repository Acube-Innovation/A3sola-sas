# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Data for Completion Report - what the electrical contractor writes the completion
report from: the customer, the connection, the plant and every module and inverter serial -
as the client's sheet (06_DATA FOR COMPLETION REPORT.pdf) lays it out, to print on the
letterhead or on plain paper.

Rendered from the COMPLETION-REPORT-DATA template for the job, with the serials of its
dispatch notice when there is one (what actually went to site), else the job's register.
The letterhead is the one A3 Sola Settings names for this report (Renewcore's), else the
company's. Nothing is saved.
"""

import frappe
from frappe import _

from a3_sola.api import documents
from a3_sola.api.settings import get_value

CODE = "COMPLETION-REPORT-DATA"
#: The sheet's margins on plain paper, as the Word file has them.
MARGINS = "20mm 19mm 0 26mm"


def url(installation, notice=None, letterhead=True, download=False):
	"""Where a page links to print the sheet."""
	link = "/api/method/a3_sola.api.completion_print.pdf?installation=" + frappe.utils.quote(installation)
	if notice:
		link += "&notice=" + frappe.utils.quote(notice)
	return link + "&letterhead=" + ("1" if letterhead else "0") + ("&download=1" if download else "")


def prints(installation, notice=None):
	"""The two prints a page offers: on the letterhead, and on plain paper."""
	return [
		{"label": _("Print on letterhead"), "url": url(installation, notice, True)},
		{"label": _("Print without letterhead"), "url": url(installation, notice, False)},
	]


@frappe.whitelist()
def pdf(installation, notice=None, letterhead=1, download=0):
	"""The sheet as a PDF, opened in the browser to print or save from there; saved as a file
	with `download`. Read with the caller's own permissions on the job (and the dispatch
	notice, when one is named - it must be the job's)."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	if notice:
		doc = frappe.get_doc("Material Dispatch Notice", notice)
		doc.check_permission("read")
		if doc.solar_installation != inst.name:
			frappe.throw(_("Dispatch notice {0} is not for {1}.").format(notice, inst.name), frappe.PermissionError)
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst, notice, letterhead)
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"


def file_name(inst):
	return documents.customer_file_name(documents.job_customer(inst), "Data for Completion Report")


def render(inst, notice=None, letterhead=1):
	"""(file name, PDF bytes) of the sheet for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	source = ("Material Dispatch Notice", notice) if notice else None
	name = frappe.db.get_value("Solar Document Template", {"template_code": CODE, "company": inst.company}, "name") \
		or frappe.db.get_value("Solar Document Template", {"template_code": CODE}, "name")
	if not name:
		frappe.throw(_("Document template {0} does not exist.").format(CODE))
	tpl = frappe.get_cached_doc("Solar Document Template", name)
	html = frappe.render_template(tpl.body_template or "", documents.get_document_context(inst, tpl, source=source))
	on_letterhead = frappe.utils.cint(letterhead)
	return file_name(inst), documents.letterhead_pdf(
		html, inst.company, letterhead=bool(on_letterhead), margins=None if on_letterhead else MARGINS,
		letter_head=get_value("completion_report_letter_head") or None,
	)
