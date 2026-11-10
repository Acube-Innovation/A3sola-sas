# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The bank's completion letters - the project completion report and the covering letter asking
for the balance - printed live for the Bank Completion Documents task (BCOM), as Form 1 and
Form 2 are: from the job as it is now, on the letterhead.
Nothing is saved; the Bank Completion Pack still files them when it is generated.
"""

import frappe
from frappe import _
from frappe.utils import cint

from a3_sola.api import documents

REPORT, COVERING = "BANK-COMPLETION-REPORT", "BANK-COVERING-COMPLETION"
CODES = (REPORT, COVERING)
LABELS = {REPORT: _("Completion Report"), COVERING: _("Covering Letter")}


def url(installation, code, download=False):
	return ("/api/method/a3_sola.api.bank_completion_print.pdf?installation=" + frappe.utils.quote(installation)
		+ "&code=" + code + ("&download=1" if download else ""))


def prints(installation, code):
	"""The task's links: view or download. The letters carry no printed signature or seal (they
	are signed by hand), so there is no signed / unsigned choice."""
	label = LABELS[code]
	return [{"label": _("View {0}").format(label), "url": url(installation, code)},
		{"label": _("Download {0}").format(label), "url": url(installation, code, download=True)}]


def _template(inst, code):
	name = frappe.db.get_value("Solar Document Template", {"template_code": code, "company": inst.company}, "name") \
		or frappe.db.get_value("Solar Document Template", {"template_code": code}, "name")
	if not name:
		frappe.throw(_("Document template {0} does not exist.").format(code))
	return frappe.get_cached_doc("Solar Document Template", name)


def render(inst, code, signed=True):
	"""(file name, PDF) of the letter `code` for the job `inst` - the caller has checked access."""
	if code not in CODES:
		frappe.throw(_("{0} is not a bank completion letter.").format(code))
	tpl = _template(inst, code)
	html = frappe.render_template(tpl.body_template or "", documents.get_document_context(inst, tpl))
	if code == COVERING:
		content = documents.letterhead_pdf(html, inst.company, signed=signed, letter_head=documents.rim_letter_head())
	else:
		# One sheet, as the bank takes it: smaller type where the serials run long.
		content = documents.one_page_flow_pdf(html, inst.company, signed=signed, letter_head=documents.rim_letter_head())
	name = documents.customer_file_name(documents.job_customer(inst), tpl.document_name + ("" if signed else " (unsigned)"))
	return name, content


@frappe.whitelist()
def pdf(installation, code, download=0, signed=1):
	"""The letter, shown in the browser; saved as a file with `download`; with `signed=0`, without
	the signature and seal, to sign by hand."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst, code, bool(cint(signed)))
	frappe.local.response.type = "download" if cint(download) else "pdf"
