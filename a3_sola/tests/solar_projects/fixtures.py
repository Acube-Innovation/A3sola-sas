# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Helpers for the Solar Projects test suite.

Everything starts from a commissioned installation, because that is what Phase 3 consumes.
"""

import frappe
from frappe.utils import add_days, today

from a3_sola.tests.fixtures import default_company, name_of
from a3_sola.tests.solar_operations.fixtures import capture_serials, make_installation

PROTECTION_VALUES = {
	"Over Voltage Trip": ("264", "V", "200 ms"),
	"Under Voltage Trip": ("192", "V", "200 ms"),
	"Over Frequency Trip": ("50.50", "Hz", "200 ms"),
	"Under Frequency Trip": ("47.50", "Hz", "200 ms"),
	"Anti-Islanding": ("Provided", None, None),
	"Grid Failure Trip Delay": ("60", "s", None),
	"Re-Energisation Delay": ("60", "s", None),
}


def solar_customer(company=None):
	"""A real job always has a party. Everything downstream depends on one."""
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test Customer {frappe.generate_hash(length=6)}",
			"customer_type": "Individual",
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	return doc.insert(ignore_permissions=True).name


def installation_with_customer(**kwargs):
	from a3_sola.tests.fixtures import make_consumer

	consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
	customer = solar_customer(consumer.company)
	frappe.db.set_value("Solar Consumer", consumer.name, "customer", customer, update_modified=False)
	return make_installation(consumer=consumer, **kwargs)


def commission(installation=None, **kwargs):
	"""A submitted Commissioning Report - which is what creates the Project."""
	installation = installation or installation_with_customer()
	capture_serials(installation, modules=6, inverters=1)

	values = {
		"doctype": "Commissioning Report",
		"company": installation.company,
		"solar_installation": installation.name,
		"commissioning_date": today(),
		"net_meter_serial_no": "NM-" + frappe.generate_hash(length=6).upper(),
		"commissioning_certificate_no": "CC-" + frappe.generate_hash(length=6).upper(),
		"commissioning_certificate": "/files/cc.pdf",
		"earthing_verified": 1,
		"surge_protection_installed": 1,
		"first_day_generation_kwh": 13.0,
		"radiation_sensor_id": "SENSOR-01",
		"radiation_sensor_calibration_certificate": "/files/cal.pdf",
		"calibration_lab": "NABL Accredited",
		"calibration_valid_until": add_days(today(), 180),
		"dc_isolator_on_inverter_incoming": 1,
		"visual_isolator_before_connectivity_point": 1,
		"wiring_as_per_approved_scheme": 1,
		"earthing_provided_ac_db": 1,
		"earthing_provided_dc_db": 1,
		"earthing_provided_structure_and_panels": 1,
		"earthing_provided_la_and_inverter_body": 1,
		"earthing_provided_isolator": 1,
	}
	values.update(kwargs)
	report = frappe.get_doc(values)
	report.flags.ignore_permissions = True
	report.insert(ignore_permissions=True)
	for row in report.protection_settings:
		value, unit, trip = PROTECTION_VALUES[row.protection_function]
		row.setting_value = value
		row.setting_unit = unit
		row.trip_time = trip
		row.proof_type = "OEM Factory Test Certificate"
		row.proof_attachment = "/files/proof.pdf"
	report.save(ignore_permissions=True)
	report.submit()
	return report, installation


def commissioned_project(installation=None, **kwargs):
	"""Returns (project, installation, report) after the full Phase 3 cascade."""
	report, installation = commission(installation, **kwargs)
	installation.reload()
	project = frappe.get_doc("Project", installation.project)
	return project, installation, report


def billing_plan(project):
	name = frappe.db.get_value("Solar Billing Plan", {"project": project.name, "docstatus": 1}, "name")
	return frappe.get_doc("Solar Billing Plan", name) if name else None


def om_contract(project):
	name = frappe.db.get_value("Solar OM Contract", {"project": project.name, "docstatus": 1}, "name")
	return frappe.get_doc("Solar OM Contract", name) if name else None


def make_ticket(contract, **kwargs):
	values = {
		"doctype": "Service Ticket",
		"company": contract.company,
		"om_contract": contract.name,
		"reported_on": frappe.utils.now_datetime(),
		"reported_via": "Phone",
		"category": "Low Generation",
		"description": "Output has dropped since last month.",
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def make_visit(contract, checklist=None, **kwargs):
	values = {
		"doctype": "Solar OM Visit",
		"company": contract.company,
		"om_contract": contract.name,
		"visit_date": today(),
		"visit_type": "Preventive",
		"technician": kwargs.pop("technician", None) or new_technician(contract.company, 520000),
		"time_in": f"{today()} 09:00:00",
		"time_out": f"{today()} 11:00:00",
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	for item, category, result in checklist or []:
		doc.append("checklist", {"checklist_item": item, "category": category, "result": result})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc


def new_technician(company, ctc=None):
	doc = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": f"Technician {frappe.generate_hash(length=5)}",
			"company": company,
			"gender": "Other",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
			"status": "Active",
			"ctc": ctc or 0,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	return doc.insert(ignore_permissions=True).name


def _technician(company, ctc=None):
	name = frappe.db.get_value("Employee", {"company": company, "status": "Active"}, "name")
	if name:
		if ctc:
			frappe.db.set_value("Employee", name, "ctc", ctc, update_modified=False)
		return name
	doc = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Test Technician",
			"company": company,
			"gender": "Other",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
			"status": "Active",
			"ctc": ctc or 0,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	return doc.insert(ignore_permissions=True).name


def make_reading(installation, lifetime_kwh, reading_date=None, **kwargs):
	values = {
		"doctype": "Generation Reading",
		"company": installation.company,
		"solar_installation": installation.name,
		"reading_date": reading_date or today(),
		"reading_source": "Inverter Portal",
		"inverter_lifetime_kwh": lifetime_kwh,
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


# ------------------------------------------------------------------ cost sources
def make_work_order(installation, hours=8.0, ctc=520000, **kwargs):
	"""A submitted work order with crew hours - the labour cost source."""
	values = {
		"doctype": "Installation Work Order",
		"company": installation.company,
		"solar_installation": installation.name,
		"work_order_type": "Module Mounting",
		"planned_start_date": today(),
		"planned_end_date": today(),
		"actual_start_date": today(),
		"actual_end_date": today(),
		"safety_briefing_done": 1,
		"ppe_verified": 1,
		"work_description": "Structure and module mounting.",
	}
	values.update({k: v for k, v in kwargs.items() if k != "technician"})
	doc = frappe.get_doc(values)
	# A fresh technician each time: the work order guards against double-booking a crew
	# member over the same dates, which is exactly what a shared one would trip.
	doc.append(
		"crew",
		{"technician": kwargs.get("technician") or new_technician(installation.company, ctc),
		 "actual_hours": hours},
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def make_snag(installation, work_order=None, severity="Major", **kwargs):
	values = {
		"doctype": "Installation Snag",
		"company": installation.company,
		"solar_installation": installation.name,
		"reported_on": today(),
		"source": "Internal QC",
		"severity": severity,
		"category": "Mounting Structure",
		"description": "Rail spacing does not match the approved drawing.",
		"rectification_work_order": work_order,
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc


def make_statutory_fee(installation, fee_type="Application Fee", amount=1180.0, **kwargs):
	values = {
		"doctype": "Statutory Fee Payment",
		"company": installation.company,
		"solar_installation": installation.name,
		"fee_type": fee_type,
		"paid_by": "Company on Behalf of Customer",
		"payment_date": today(),
		"payment_reference": "REF-" + frappe.generate_hash(length=6).upper(),
		"amount_base": amount,
		"receipt": "/files/receipt.pdf",
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc
