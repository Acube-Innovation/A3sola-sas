# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer's covering letter to the Assistant Engineer for the Form 3 Submission - the
documents for the plant's registration and completion report - as the Word file "To The Asst.
Engineer-Covering Letter" lays it out: the date, the section's Assistant Engineer, the subject,
the plant (its panels' kWp, as Forms 2 and 3 say), the consumer number and the address, and
what is enclosed - Annexure 2, Annexure 3 with its five attachments, the solar agreement.

On plain paper: the customer signs it. Rendered for the Form 3 Submission task (KFORMS) and
its pack; nothing is saved, and the signed copy is uploaded to the same row.
"""

import base64
import functools
import os

import frappe
from frappe import _
from frappe.utils import cint, formatdate, today

from a3_sola.api import documents
from a3_sola.api.form1_print import _consumer, _row1
from a3_sola.api.form2_print import _kwp

CODE = "KSEB-COVERING-COMPLETION"
TITLE = "Covering Letter to the Assistant Engineer"
#: Word's margins for the letter: 30mm top, 25.4mm each side, 20.6mm at the foot.
MARGINS = "30mm 25.4mm 20.6mm 25.4mm"


@functools.lru_cache(maxsize=1)
def fonts():
	"""@font-face rules for "Letter Antiqua": URW's P052, the Palatino design Book Antiqua is,
	bundled (public/fonts/p052, AGPL-3 with the font exception) since neither this server nor
	the PDF renderer has Book Antiqua - embedded so the letters look alike everywhere."""
	folder = frappe.get_app_path("a3_sola", "public", "fonts", "p052")
	rules = []
	for weight, name in (("normal", "P052-Roman.ttf"), ("bold", "P052-Bold.ttf")):
		with open(os.path.join(folder, name), "rb") as f:
			data = base64.b64encode(f.read()).decode()
		# No format() hint: the renderer's CSS parser rejects it, and the font loads without.
		rules.append('@font-face { font-family: "Letter Antiqua"; font-weight: %s; '
			"src: url(data:application/x-font-ttf;base64,%s); }" % (weight, data))
	return "\n".join(rules)


def url(installation, download=False):
	return "/api/method/a3_sola.api.kseb_covering_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download. The system makes the PDF, so the
	row is Generated and takes no upload."""
	return [{"label": _("View Covering Letter"), "url": url(installation)},
		{"label": _("Download Covering Letter"), "url": url(installation, download=True)}]


def context(inst):
	"""The letter's details for the job `inst`."""
	consumer = _consumer(inst)
	row1 = _row1(inst, consumer)
	section = inst.get("discom_section") or consumer.get("discom_section")
	kwp = _kwp(inst)
	return frappe._dict({
		"date": formatdate(today(), "dd-MM-yyyy"),
		"section": (frappe.db.get_value("DISCOM Section", section, "section_name") or "") if section else "",
		"capacity": "{0:g}kWp".format(kwp) if kwp else "",
		"consumer_number": row1["number"] or "",
		"address": row1["address"] or "",
		"name": row1["name"] or "",
	})


def file_name(inst):
	return "{0} - {1}.pdf".format(TITLE, inst.consumer_name or inst.name)


def render(inst):
	"""(file name, PDF) of the letter for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	return file_name(inst), documents.letterhead_pdf(html(inst), inst.company, letterhead=False, margins=MARGINS)


def html(inst):
	"""The letter as HTML. (The PDF draws the embedded font as outlines where the renderer is
	the unpatched wkhtmltopdf, so its words are checked here.)"""
	return frappe.render_template("a3_sola/templates/print/kseb_covering_letter.html", {"f": context(inst), "fonts": fonts()})


@frappe.whitelist()
def pdf(installation, download=0):
	"""The letter, shown in the browser; saved as a file with `download`."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst)
	frappe.local.response.type = "download" if cint(download) else "pdf"
