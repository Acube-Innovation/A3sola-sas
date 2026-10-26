# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer's request to the Assistant Engineer for a bidirectional meter (net meter), for
the Form 3 Submission, as the Word file "To The Asst. Engineer-Net Meter" lays it out: the
date, the section's Assistant Engineer, the consumer number and category, the address, the
plant (its panels' kWp), the solar meter procured by the consumer, and the phase of the net
meter asked for.

The same letter as the covering letter (api/kseb_covering_print) in all but its body. On plain
paper: the customer signs it. Nothing is saved; the signed copy is uploaded to the same row.
"""

import frappe
from frappe import _
from frappe.utils import cint

from a3_sola.api import documents
from a3_sola.api import kseb_covering_print as covering
from a3_sola.api.form1_print import _consumer, _row1

CODE = "KSEB-NETMETER-REQUEST"
TITLE = "Request for Allocation of Bidirectional Meter"


def url(installation, download=False):
	return "/api/method/a3_sola.api.kseb_netmeter_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download. The system makes the PDF, so the
	row is Generated and takes no upload."""
	return [{"label": _("View Net Meter Request"), "url": url(installation)},
		{"label": _("Download Net Meter Request"), "url": url(installation, download=True)}]


def context(inst):
	"""The letter's details for the job `inst`: the covering letter's, with the category and
	the phase."""
	f = covering.context(inst)
	row1 = _row1(inst, _consumer(inst))
	f.category = "/".join(x for x in (row1["tariff"], row1["phase"] if row1["tariff"] else "") if x)
	f.phase = "{0} Phase".format(row1["phase"]) if row1["phase"] else ""
	return f


def file_name(inst):
	return documents.customer_file_name(documents.job_customer(inst), TITLE)


def render(inst):
	"""(file name, PDF) of the letter for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	return file_name(inst), documents.letterhead_pdf(html(inst), inst.company, letterhead=False, margins=covering.MARGINS)


def html(inst):
	"""The letter as HTML (see kseb_covering_print.html)."""
	return frappe.render_template("a3_sola/templates/print/kseb_netmeter_request.html", {"f": context(inst),
		"fonts": covering.fonts()})


@frappe.whitelist()
def pdf(installation, download=0):
	"""The letter, shown in the browser; saved as a file with `download`."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst)
	frappe.local.response.type = "download" if cint(download) else "pdf"
