# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEBL Form 1 (Annexure 1): the application to connect a solar plant to the grid, as the
team's own KSEBL Form 1.docx lays it out - its printed Malayalam labels (scanned, in
public/images/kseb_form1) beside the customer's answers:

1. Name, consumer number, category, telephone, email and full address
2. Connected load / contract demand
3. Capacity of the solar plant to be installed - the inverters' capacity
4. Other premises of the consumer to use the energy at, in order of priority (consumer
   number, address and electrical section) - the agreement's wheeling preferences
5. Rooftop or ground mounted
6. Date by which the plant is to be completed

then place, date and the consumer's signature, and the panel and inverter below. Rendered for
the Form 1 Generation task (FRM1); nothing is saved. A row 1 detail the customer's record does
not have yet is left blank, and the task's page says which (missing): the form is made from
the job each time, so filling it there fills the form.
"""

import base64
import os

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, today

from a3_sola.api import documents

CODE = "KSEB-FORM-1"
IMAGES = ("header", "row1", "row2", "row3", "row4", "row5", "row6", "place", "date", "signature")


def url(installation, download=False):
	return "/api/method/a3_sola.api.form1_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download."""
	return [{"label": _("View Form 1"), "url": url(installation)},
		{"label": _("Download Form 1"), "url": url(installation, download=True)}]


def _images():
	folder = frappe.get_app_path("a3_sola", "public", "images", "kseb_form1")
	out = {}
	for name in IMAGES:
		with open(os.path.join(folder, name + ".png"), "rb") as f:
			out[name] = "data:image/png;base64," + base64.b64encode(f.read()).decode()
	return out


def _make(name):
	return (frappe.db.get_value("Component Make", name, "make_name") or name) if name else ""


def _priced(inst, table):
	return [r for r in inst.get(table) or [] if not r.get("is_option")]


#: Row 1's details: (key, what the form asks, the Customer field it comes from).
ROW1 = (
	("name", "Name", "Customer Name"),
	("number", "Consumer number", "Consumer Number"),
	("tariff", "Category", "Tariff Category"),
	("phase", "Category (phase)", "Connection Type"),
	("address", "Address", "Installation Site Address"),
	("mobile", "Telephone number", "Mobile"),
	("email", "Email address", "Email"),
)


def _row1(inst, consumer):
	"""Row 1's details for the job `inst`, by ROW1 key."""
	from a3_sola.api.material_delivery import site

	_name, address, mobile, _point = site(inst)
	return {
		"name": inst.consumer_name or consumer.get("consumer_name"),
		"number": inst.get("consumer_number") or consumer.get("consumer_number"),
		"tariff": consumer.get("tariff_category") or inst.get("tariff_category") or "",
		"phase": (consumer.get("connection_type") or inst.get("connection_type") or "").replace(" Phase", ""),
		# One line, its parts once comma-separated: the lines may end in commas already.
		"address": ", ".join(x.strip().rstrip(",").strip() for x in (address or "").splitlines() if x.strip(" ,")),
		"mobile": mobile or consumer.get("mobile_no"),
		"email": consumer.get("email_id"),
	}


def _consumer(inst):
	return frappe.get_doc("Solar Consumer", inst.solar_consumer) if inst.get("solar_consumer") else frappe._dict()


def missing(inst):
	"""Row 1's details the job does not have yet, for the task's page: [{what, field}], the
	field being the Customer's that fills it."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	held = _row1(inst, _consumer(inst))
	return [{"what": _(what), "field": _(field)} for key, what, field in ROW1 if not held[key]]


def context(inst):
	"""The form's answers for the job `inst`."""
	consumer = _consumer(inst)
	pick = lambda field: consumer.get(field) or inst.get(field)  # noqa: E731
	row1 = _row1(inst, consumer)
	# The category as the form writes it: the tariff code and the phase, "LT-I/Single".
	category = "/".join(x for x in (row1["tariff"], row1["phase"] if row1["tariff"] else "") if x)
	details = [row1["name"], row1["number"], category, row1["address"], row1["mobile"], row1["email"]]

	load = flt(pick("connected_load_watts"))
	if not load and flt(pick("sanctioned_load_kw")):
		load = flt(pick("sanctioned_load_kw")) * 1000

	# The other premises the energy is to be used at: the agreement's wheeling preferences.
	agreement = frappe.db.get_value("Solar Agreement", {"solar_installation": inst.name, "docstatus": ["<", 2]},
		"name", order_by="creation desc")
	premises = []
	if agreement:
		for p in frappe.get_all("Wheeling Preference", filters={"parent": agreement, "parenttype": "Solar Agreement"},
				fields=["preference_order", "consumer_number", "premises_address", "electrical_section"], order_by="preference_order asc"):
			premises.append("{0}. {1}".format(cint(p.preference_order) or len(premises) + 1, ", ".join(
				x for x in (p.consumer_number, p.premises_address, p.electrical_section) if x)))

	# Completed by: the plan's commissioning date, else its installation's.
	planned = next((r.get("planned_date") for code in ("COMM", "IWOI") for r in inst.stages
		if r.stage_code == code and r.get("planned_date")), None)

	place = consumer.get("site_city") or consumer.get("permanent_city") or ""
	if not place and inst.get("discom_section"):
		place = frappe.db.get_value("DISCOM Section", inst.discom_section, "section_name") or ""

	panels = [_("{0} {1:g}Wp X {2} Nos").format(_make(r.panel_make), flt(r.panel_capacity_wp), cint(r.nos)).strip()
		for r in _priced(inst, "panels")]
	inverters = [_("{0}-{1:g}kW X {2}- {3}").format(_make(r.inverter_make), flt(r.inverter_capacity_kw), cint(r.nos) or 1,
		(r.inverter_phase or "").replace("Single Phase", "1 Phase").replace("Three Phase", "3 Phase")).strip(" -")
		for r in _priced(inst, "inverters")]
	# The plant's capacity is its inverters': each one's kW times how many.
	capacity = sum(flt(r.inverter_capacity_kw) * (cint(r.nos) or 1) for r in _priced(inst, "inverters"))

	return frappe._dict({
		"details": [d for d in details if d],
		"load": "{0:g} Watts".format(load) if load else "",
		"capacity": "{0:g}KW".format(capacity) if capacity else "",
		"premises": premises,
		"mounting": "Rooftop",
		"complete_by": formatdate(planned, "dd.MM.yyyy") if planned else "",
		"place": place.upper(),
		"date": formatdate(today(), "dd-MM-yyyy"),
		"panels": panels,
		"inverters": inverters,
	})


def file_name(inst):
	return documents.customer_file_name(documents.job_customer(inst), "KSEBL Form 1")


def render(inst):
	"""(file name, PDF) of Form 1 for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	html = frappe.render_template("a3_sola/templates/print/kseb_form_1.html", {"f": context(inst), "img": _images()})
	return file_name(inst), documents.plain_pdf(html, margins="8mm")


@frappe.whitelist()
def pdf(installation, download=0):
	"""Form 1, shown in the browser; saved as a file with `download`."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst)
	frappe.local.response.type = "download" if cint(download) else "pdf"
