# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEBL Form 2 (Annexure 2): the application to register the solar plant, under regulation
13(7) of the KSERC's 2014 grid interactive distributed solar energy systems regulations, as
the team's own KSEBL Form 2.docx lays it out - its printed Malayalam labels (scanned, in
public/images/kseb_form2, and the ones it shares with Form 1 in public/images/kseb_form1)
beside the customer's answers:

1. Name, consumer number, category, telephone, email and full address - as Form 1's row 1
2. Connected load
3. Capacity of the solar plant - the panels' kWp
4. Panel, grid-tied inverter and interlock specifications attached
5. Solar meter and net meter bought by the consumer, their specifications attached - or the
   net meter is KSEBL's, its request attached
6. Technical drawings of the plant attached
7. Date by which the installation is to be completed

then place, date and the consumer's signature, and KSEBL's blank acknowledgement receipt for
the section office to fill in. Rendered for the Form 2 Submission task (FRM2); nothing is
saved. Row 1's details come and go missing exactly as Form 1's (form1_print.missing).
"""

import base64
import os

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, today

from a3_sola.api import documents
from a3_sola.api.form1_print import _consumer, _priced, _row1

CODE = "KSEB-FORM-2"
#: The label images: Form 2's own, then those it shares with Form 1.
IMAGES = ("header", "row1", "row4", "row5", "row6", "row7", "footer")
SHARED = ("row2", "row3", "place", "date", "signature")


def url(installation, download=False):
	return "/api/method/a3_sola.api.form2_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download. The system makes the PDF, so the
	row is Generated and takes no upload."""
	return [{"label": _("View Form 2"), "url": url(installation)},
		{"label": _("Download Form 2"), "url": url(installation, download=True)}]


def _images():
	out = {}
	for folder, names in (("kseb_form2", IMAGES), ("kseb_form1", SHARED)):
		path = frappe.get_app_path("a3_sola", "public", "images", folder)
		for name in names:
			with open(os.path.join(path, name + ".png"), "rb") as f:
				out[name] = "data:image/png;base64," + base64.b64encode(f.read()).decode()
	return out


def _kwp(inst):
	"""The plant's capacity: its panels' - each row's kWp, else its watts times how many -
	else the job's."""
	kwp = sum(flt(r.total_capacity_kwp) or flt(r.panel_capacity_wp) * cint(r.nos) / 1000 for r in _priced(inst, "panels"))
	return flt(kwp, 3) or flt(inst.get("capacity_kw"))


def _place(inst, consumer):
	"""Where the consumer signs: the site's city, else the section's name, upper-cased."""
	place = consumer.get("site_city") or consumer.get("permanent_city") or ""
	if not place and inst.get("discom_section"):
		place = frappe.db.get_value("DISCOM Section", inst.discom_section, "section_name") or ""
	return place.upper()


def _completion_date(inst):
	"""When the installation is done, or is planned to be: its work order stage's."""
	for r in inst.stages:
		if r.stage_code == "IWOI":
			return r.get("actual_completion_date") or r.get("planned_date")
	return None


def context(inst):
	"""The form's answers for the job `inst`."""
	consumer = _consumer(inst)
	pick = lambda field: consumer.get(field) or inst.get(field)  # noqa: E731
	row1 = _row1(inst, consumer)
	category = "/".join(x for x in (row1["tariff"], row1["phase"] if row1["tariff"] else "") if x)
	details = [row1["name"], row1["number"], category, row1["address"], row1["mobile"], row1["email"]]

	load = flt(pick("connected_load_watts")) / 1000 or flt(pick("sanctioned_load_kw"))
	kwp = _kwp(inst)

	rental = inst.get("net_meter_mode") == "Availed from DISCOM on Rental"
	meters = ["Solar Meter – Yes"] + (["Net Meter – From KSEBL", "(Request Attached)"] if rental else ["Net Meter – Yes"])
	complete_by = _completion_date(inst)

	return frappe._dict({
		"details": [d for d in details if d],
		"load": "{0:g}kW".format(flt(load, 3)) if load else "",
		"capacity": "{0:g}kWp".format(kwp) if kwp else "",
		"specifications": "Yes",
		"meters": meters,
		"drawings": "Yes",
		"complete_by": formatdate(complete_by, "dd.MM.yyyy") if complete_by else "",
		"place": _place(inst, consumer),
		"date": formatdate(today(), "dd-MM-yyyy"),
	})


def file_name(inst):
	return documents.customer_file_name(documents.job_customer(inst), "KSEBL Form 2")


def render(inst):
	"""(file name, PDF) of Form 2 for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	html = frappe.render_template("a3_sola/templates/print/kseb_form_2.html", {"f": context(inst), "img": _images()})
	return file_name(inst), documents.plain_pdf(html, margins="8mm")


@frappe.whitelist()
def pdf(installation, download=0):
	"""Form 2, shown in the browser; saved as a file with `download`."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst)
	frappe.local.response.type = "download" if cint(download) else "pdf"
