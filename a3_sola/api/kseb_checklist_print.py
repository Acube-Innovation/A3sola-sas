# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEB's "Details of installation & checklist to be furnished along with the request for
testing solar inverters", as the team's CHECKLIST.xlsx lays it out: the section, the consumer
and the installer, the plant, the checks and the inverter's protection settings, the
consumer's or installer's declaration, then the Assistant Engineer's, the Assistant Executive
Engineer's and the Executive Engineer's boxes.

It goes with the Form 3 Submission (KFORMS), before the job is commissioned, so it is made from
the job: the section, the customer, the company, the panels and inverters (with the serial
numbers captured at dispatch), the inspectorate's approval. What only commissioning records -
the checks, the protection settings, the DC input voltage - comes from the job's Commissioning
Report once it has one; until then the checks are the installer's YES, the settings the
standard ones in A3 Sola Settings, and the DC input voltage a line to write on. Nothing is saved.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, today

from a3_sola.api import documents
from a3_sola.api.form1_print import _consumer, _make, _priced, _row1
from a3_sola.api.form2_print import _kwp
from a3_sola.api.form3_print import _inspectorate
from a3_sola.api.settings import get_float

CODE = "KSEB-TESTING-CHECKLIST"
TITLE = "Installation and Inverter Testing Checklist"
BLANK = "…………………………"
YES = "YES"

#: The standard protection settings (A3 Sola Settings field, default), until commissioning.
STANDARD = {
	"Over Voltage Trip": ("kseb_over_voltage_trip_v", 264),
	"Under Voltage Trip": ("kseb_under_voltage_trip_v", 192),
	"Over Frequency Trip": ("kseb_over_frequency_trip_hz", 50.5),
	"Under Frequency Trip": ("kseb_under_frequency_trip_hz", 47.5),
	"Grid Failure Trip Delay": ("kseb_grid_failure_trip_delay_s", 60),
	"Re-Energisation Delay": ("kseb_re_energisation_delay_s", 60),
}
TRIP_TIME = {"voltage": ("kseb_voltage_trip_time_ms", 200), "frequency": ("kseb_frequency_trip_time_ms", 200)}
#: Earthing is YES when the Commissioning Report ticks every one of these.
EARTHING =("earthing_provided_ac_db", "earthing_provided_dc_db", "earthing_provided_structure_and_panels",
	"earthing_provided_la_and_inverter_body", "earthing_provided_isolator")


def url(installation, download=False):
	return "/api/method/a3_sola.api.kseb_checklist_print.pdf?installation=" + frappe.utils.quote(installation) + (
		"&download=1" if download else "")


def prints(installation):
	"""The task's links: view in the browser, or download. The system makes the PDF, so the
	row is Generated and takes no upload."""
	return [{"label": _("View Testing Checklist"), "url": url(installation)},
		{"label": _("Download Testing Checklist"), "url": url(installation, download=True)}]


def _report(inst):
	"""The job's Commissioning Report - submitted, else the latest draft - or None."""
	name = frappe.db.get_value("Commissioning Report", {"solar_installation": inst.name, "docstatus": 1}, "name") or (
		frappe.db.get_value("Commissioning Report", {"solar_installation": inst.name, "docstatus": 0}, "name",
			order_by="creation desc"))
	return frappe.get_doc("Commissioning Report", name) if name else None


def _yes(value):
	return YES if value else "NO"


def _num(value, unit):
	return "{0:g} {1}".format(flt(value), unit).strip()


def _settings(report):
	"""{function: (provided, setting, trip time)} - the report's where it gives them, else the
	standard ones."""
	rows = {r.protection_function: r for r in (report.protection_settings if report else [])}

	def setting(function, unit):
		row = rows.get(function)
		if row and (row.setting_value or "").strip():
			return "{0} {1}".format(row.setting_value.strip(), row.setting_unit or unit).strip()
		field, default = STANDARD[function]
		return _num(get_float(field, default), unit)

	def trip(function, kind):
		row = rows.get(function)
		if row and (row.trip_time or "").strip():
			return row.trip_time.strip().upper()
		field, default = TRIP_TIME[kind]
		return _num(get_float(field, default), "MS")

	def provided(*functions):
		return YES if not rows else _yes(all(cint(rows[f].is_provided) for f in functions if f in rows))

	return frappe._dict({
		"voltage_provided": provided("Over Voltage Trip", "Under Voltage Trip"),
		"over_voltage": setting("Over Voltage Trip", "V"),
		"under_voltage": setting("Under Voltage Trip", "V"),
		"voltage_trip_time": trip("Over Voltage Trip", "voltage"),
		"frequency_provided": provided("Over Frequency Trip", "Under Frequency Trip"),
		"over_frequency": setting("Over Frequency Trip", "Hz"),
		"under_frequency": setting("Under Frequency Trip", "Hz"),
		"frequency_trip_time": trip("Over Frequency Trip", "frequency"),
		"anti_islanding": provided("Anti-Islanding"),
		"grid_failure_delay": setting("Grid Failure Trip Delay", "s").replace(" s", " SECONDS"),
		"re_energisation_provided": provided("Re-Energisation Delay"),
		"re_energisation_delay": setting("Re-Energisation Delay", "s").replace(" s", " SECONDS"),
	})


def _ei_details(inst, report):
	"""The inspectorate's approval: its number and date, as approved on the portal."""
	if report and report.get("energisation_approval_details"):
		return report.energisation_approval_details
	approval = frappe.db.get_value("Portal Application", {"solar_installation": inst.name,
		"application_type": "Electrical Inspectorate", "application_status": "Approved", "docstatus": ["<", 2]},
		["approval_number", "approval_date"], as_dict=True)
	if not (approval and approval.approval_number):
		return ""
	return " dated ".join(x for x in (approval.approval_number,
		formatdate(approval.approval_date, "dd.MM.yyyy") if approval.approval_date else "") if x)


def context(inst):
	"""The checklist's answers for the job `inst`."""
	consumer = _consumer(inst)
	row1 = _row1(inst, consumer)
	report = _report(inst)
	section_name = inst.get("discom_section") or consumer.get("discom_section")
	section = frappe.get_cached_doc("DISCOM Section", section_name) if section_name else frappe._dict()
	company = frappe.get_cached_doc("Company", inst.company) if inst.get("company") else frappe._dict()

	load = flt(consumer.get("connected_load_watts") or inst.get("connected_load_watts")) / 1000 or flt(
		consumer.get("sanctioned_load_kw") or inst.get("sanctioned_load_kw"))
	panels = _priced(inst, "panels")
	inverters = _priced(inst, "inverters")
	serials = [r.serial_no for r in inst.get("serials") or [] if r.component_type == "Inverter" and not r.is_replaced and r.serial_no]
	makes = [_make(r.inverter_make) for r in inverters if r.inverter_make]
	phases = {(r.inverter_phase or inst.get("connection_type") or "").upper() for r in inverters} or {(inst.get("connection_type") or "").upper()}
	kwp = _kwp(inst)
	plant_type = {"On-Grid": "ON GRID", "Off-Grid": "OFF GRID", "Hybrid": "HYBRID"}.get(inst.get("system_type"), "ON GRID")

	def check(field):
		return _yes(report.get(field)) if report else YES

	return frappe._dict({
		"division": " / ".join(x for x in (section.get("electrical_division"), section.get("electrical_subdivision")) if x),
		"section": section.get("section_name") or "",
		"consumer_number": row1["number"] or "",
		"tariff": "/".join(x for x in (row1["tariff"], row1["phase"] if row1["tariff"] else "") if x).upper(),
		"load": "{0:.3f} kW".format(load) if load else "",
		"owner": row1["name"] or "",
		"address": row1["address"] or "",
		"email": row1["email"] or "",
		"mobile": row1["mobile"] or "",
		"alternate": consumer.get("alternate_contact_no") or "",
		"bank_name": consumer.get("bank_name") or "",
		"bank_account": consumer.get("bank_account_no") or "",
		"bank_ifsc": consumer.get("bank_ifsc_code") or "",
		"installer": company.get("epc_name") or company.get("company_name") or "",
		"installer_address": [x.strip() for x in (company.get("epc_address") or "").splitlines() if x.strip(" ,")],
		"installer_email": company.get("epc_email") or "",
		"installer_phone": company.get("epc_contact_no") or "",
		"plant_type": plant_type,
		"capacity": "{0:g} KWp".format(kwp) if kwp else "",
		"panel_count": "{0} NOS.".format(sum(cint(r.nos) for r in panels)) if panels else "",
		"panel_capacity": ", ".join("{0:g} Wp{1}".format(flt(r.panel_capacity_wp),
			" ({0})".format(_make(r.panel_make)) if r.panel_make else "") for r in panels),
		"inverter": ", ".join(x for x in (" / ".join(dict.fromkeys(makes)), ", ".join(serials)) if x),
		"inverter_phase": " / ".join(p for p in phases if p),
		"inverter_capacity": ", ".join("{0:g} KW".format(flt(r.inverter_capacity_kw)) for r in inverters),
		"inverter_count": str(sum(cint(r.nos) or 1 for r in inverters)) if inverters else "",
		"dc_voltage": "{0:g}".format(flt(report.dc_input_voltage)) if report and report.get("dc_input_voltage") else BLANK,
		"hybrid": _yes(report.get("hybrid_scheme_conforms_to_ce_rees")) if report and plant_type == "HYBRID" else YES,
		"completion_certificate": check("completion_certificate_submitted_to_section"),
		"ei_approval": _inspectorate(inst).upper(),
		"ei_details": _ei_details(inst, report),
		"dc_isolator": check("dc_isolator_on_inverter_incoming"),
		"visual_isolator": check("visual_isolator_before_connectivity_point"),
		"wiring": check("wiring_as_per_approved_scheme"),
		"earthing": _yes(all(report.get(f) for f in EARTHING)) if report else YES,
		"protection": _yes(any(cint(r.is_provided) for r in report.protection_settings)) if report and report.protection_settings else YES,
		"settings": _settings(report),
		"date": formatdate(today(), "dd-MM-yyyy"),
	})


def file_name(inst):
	return "{0} - {1}.pdf".format(TITLE, inst.consumer_name or inst.name)


def render(inst):
	"""(file name, PDF) of the checklist for the job `inst` - the caller has checked access."""
	if isinstance(inst, str):
		inst = frappe.get_doc("Solar Installation", inst)
	html = frappe.render_template("a3_sola/templates/print/kseb_checklist.html", {"f": context(inst)})
	return file_name(inst), documents.plain_pdf(html, margins="10mm")


@frappe.whitelist()
def pdf(installation, download=0):
	"""The checklist, shown in the browser; saved as a file with `download`."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(inst)
	frappe.local.response.type = "download" if cint(download) else "pdf"
