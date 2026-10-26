# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The data the stamp vendor writes the stamp paper from - the parties, the purpose, the
value - as the Word file "Data for Stamp Paper" lays it out, to download.

Rendered from the STAMP-PAPER-DATA template for the job, and the job's agreement when
there is one (its value); before the agreement exists - when the paper is still to be
bought - the job alone is enough. Nothing is saved.
"""

import frappe
from frappe import _

from a3_sola.api import documents

CODE = "STAMP-PAPER-DATA"
#: Word's margins for the sheet: 30mm top, 25.4mm each side.
MARGINS = "30mm 25.4mm 0 25.4mm"


def url(installation, agreement=None):
	"""Where a page links to download the sheet."""
	link = "/api/method/a3_sola.api.stamp_print.pdf?installation=" + frappe.utils.quote(installation)
	return link + ("&agreement=" + frappe.utils.quote(agreement) if agreement else "")


@frappe.whitelist()
def pdf(installation, agreement=None):
	"""The sheet as a PDF download. Read with the caller's own permissions on the job (and
	the agreement, when one is named - it must be the job's)."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	source = None
	if agreement:
		doc = frappe.get_doc("Solar Agreement", agreement)
		doc.check_permission("read")
		if doc.solar_installation != inst.name:
			frappe.throw(_("Agreement {0} is not for {1}.").format(agreement, inst.name), frappe.PermissionError)
		source = (doc.doctype, doc.name)
	name = frappe.db.get_value("Solar Document Template", {"template_code": CODE, "company": inst.company}, "name") \
		or frappe.db.get_value("Solar Document Template", {"template_code": CODE}, "name")
	if not name:
		frappe.throw(_("Document template {0} does not exist.").format(CODE))
	tpl = frappe.get_cached_doc("Solar Document Template", name)
	html = frappe.render_template(tpl.body_template or "", documents.get_document_context(inst, tpl, source=source))
	frappe.local.response.filename = documents.customer_file_name(documents.job_customer(inst), "Data for Stamp Paper")
	frappe.local.response.filecontent = documents.letterhead_pdf(html, inst.company, letterhead=False, margins=MARGINS)
	frappe.local.response.type = "download"
