# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer's request to the Assistant Engineer for the refund of 80% of the registration
fee - as the Word file "To The Asst. Engineer_Refund" lays it out - to download, sign and
hand in with a cancelled cheque.

Rendered from the KSEB-REFUND-REQUEST template for the job, on plain paper: the customer
signs it. Nothing is saved; the signed copy is uploaded to the same row of the Completion
File task.
"""

import frappe
from frappe import _

from a3_sola.api import documents

CODE = "KSEB-REFUND-REQUEST"
#: Word's margins for the letter: 30mm top, 25.4mm each side.
MARGINS = "30mm 25.4mm 0 25.4mm"


def url(installation):
	"""Where a page links to download the letter."""
	return "/api/method/a3_sola.api.refund_print.pdf?installation=" + frappe.utils.quote(installation)


def prints(installation):
	"""The download the Completion File panel offers. `keep_file`: the row still shows the
	signed copy uploaded to it, and an upload while there is none."""
	return [{"label": _("Download"), "url": url(installation), "keep_file": True}]


@frappe.whitelist()
def pdf(installation):
	"""The letter as a PDF download. Read with the caller's own permissions on the job."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	name = frappe.db.get_value("Solar Document Template", {"template_code": CODE, "company": inst.company}, "name") \
		or frappe.db.get_value("Solar Document Template", {"template_code": CODE}, "name")
	if not name:
		frappe.throw(_("Document template {0} does not exist.").format(CODE))
	tpl = frappe.get_cached_doc("Solar Document Template", name)
	html = frappe.render_template(tpl.body_template or "", documents.get_document_context(inst, tpl))
	frappe.local.response.filename = documents.customer_file_name(documents.job_customer(inst), "Refund Request")
	frappe.local.response.filecontent = documents.letterhead_pdf(html, inst.company, letterhead=False, margins=MARGINS)
	frappe.local.response.type = "download"
