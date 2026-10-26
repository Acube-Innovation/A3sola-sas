# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEBL Form 3 (Annexure 3): the application to test the solar plant once it is installed,
as the team's own KSEBL Form 3.docx lays it out - its printed Malayalam labels (scanned, in
public/images/kseb_form3, and the ones it shares with Forms 1 and 2) beside the customer's
answers:

1. Name, consumer number, category, telephone, email and full address - as Form 1's row 1
2. Solar registration number - the acknowledgement number of the Form 2 the AE received
3. Capacity of the installed plant - the panels' kWp
4. Type test certificates of the MCB, ELCB, fuse, inverter and the like provided
5. Panel, grid-tied inverter and interlock specifications attached
6. The Electrical Inspector's energisation certificate attached - not applicable when the
   job needs no inspectorate approval (its CEIG stage is skipped, below the threshold)

then place, date and the consumer's signature, and KSEBL's blank acknowledgement receipt for
the section office to fill in. Rendered for the Form 3 Submission task (KFORMS); nothing is
saved. Row 1's details come and go missing exactly as Form 1's (form1_print.missing).
"""

import base64
import os

import frappe
from frappe import _
from frappe.utils import cint, formatdate, today

from a3_sola.api import documents
from a3_sola.api.form1_print import _consumer, _row1
from a3_sola.api.form2_print import _kwp, _place

CODE = "KSEB-FORM-3"
#: The label images: Form 3's own, then those it shares with Forms 1 and 2, by folder.
IMAGES = ("header", "row2", "row3", "row4", "row5", "row6", "footer")
SHARED = {"row1": "kseb_form2", "place": "kseb_form1", "date": "kseb_form1", "signature": "kseb_form1"}


def url(installation, download=False):
	return "/api/method/a3_sola.api.form3_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download. The system makes the PDF, so the
	row is Generated and takes no upload."""
	return [{"label": _("View Form 3"), "url": url(installation)},
		{"label": _("Download Form 3"), "url": url(installation, download=True)}]


def _images():
	folder = lambda name: frappe.get_app_path("a3_sola", "public", "images", name)  # noqa: E731
	files = [(name, folder("kseb_form3")) for name in IMAGES] + [(name, folder(f)) for name, f in SHARED.items()]
	out = {}
	for name, path in files:
		with open(os.path.join(path, name + ".png"), "rb") as f:
			out[name] = "data:image/png;base64," + base64.b64encode(f.read()).decode()
	return out


def _registration_no(inst):
	"""The solar registration number: the acknowledgement number the AE gave the Form 2."""
	return frappe.db.get_value("Document Pack", {"solar_installation": inst.name, "pack_type": "KSEB Form 2",
		"docstatus": ["<", 2], "ae_acknowledgement_no": ["is", "set"]}, "ae_acknowledgement_no", order_by="creation desc") or ""


def _inspectorate(inst):
	"""Row 6: the energisation certificate is attached when the job needs the inspectorate's
	approval, and not applicable when its CEIG stage is skipped (or it has none)."""
	ceig = next((r for r in inst.stages if r.stage_code == "CEIG"), None)
	return "Yes" if ceig and ceig.status != "Skipped" else "Not Applicable"


def context(inst):
	"""The form's answers for the job `inst`."""
	consumer = _consumer(inst)
	row1 = _row1(inst, consumer)
	category = "/".join(x for x in (row1["tariff"], row1["phase"] if row1["tariff"] else "") if x)
	details = [row1["name"], row1["number"], category, row1["address"], row1["mobile"], row1["email"]]
	kwp = _kwp(inst)
	return frappe._dict({
		"details": [d for d in details if d],
		"registration": _registration_no(inst),
		"capacity": "{0:g}kWp".format(kwp) if kwp else "",
		"certificates": "Yes",
		"specifications": "Yes",
		"inspectorate": _inspectorate(inst),
		"place": _place(inst, consumer),
		"date": formatdate(today(), "dd-MM-yyyy"),
	})


def file_name(inst):
	return documents.customer_file_name(documents.job_customer(inst), "KSEBL Form 3")


def render(inst):
	"""(file name, PDF) of Form 3 for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	html = frappe.render_template("a3_sola/templates/print/kseb_form_3.html", {"f": context(inst), "img": _images()})
	return file_name(inst), documents.plain_pdf(html, margins="8mm")


@frappe.whitelist()
def pdf(installation, download=0):
	"""Form 3, shown in the browser; saved as a file with `download`."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst)
	frappe.local.response.type = "download" if cint(download) else "pdf"
