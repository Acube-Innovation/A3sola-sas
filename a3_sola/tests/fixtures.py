# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Helpers shared across the Phase 1 test suite."""

import frappe
from frappe.utils import today


def default_company():
	company = frappe.defaults.get_global_default("company")
	return company or frappe.get_all("Company", pluck="name", limit=1)[0]


def name_of(doctype, title_field, value, company=None):
	"""Resolve a master by title, scoped to a company.

	Defaults to the site's own company so a second tenant created by the isolation tests
	cannot shadow the first one's masters.
	"""
	filters = {title_field: value}
	filters["company"] = company or default_company()
	return frappe.db.get_value(doctype, filters, "name")


def scheme(company=None):
	return name_of("Subsidy Scheme", "scheme_name", "PM Surya Ghar: Muft Bijli Yojana", company)


def tariff(company=None):
	return name_of("Electricity Tariff", "tariff_name", "KSEB Domestic Bimonthly", company)


def discom(company=None):
	return name_of("DISCOM", "discom_name", "KSEB", company)


def section(name="Athani", company=None):
	return name_of("DISCOM Section", "section_name", name, company)


def package(code="3Kw 1PH", company=None):
	return name_of("Solar Package", "specification_code", code, company)


def make_company(name, abbr, seed=True):
	"""A second company with its own masters, so tenant isolation is testable.

	Masters are per-company by design, so a second tenant needs its own set - which is
	exactly what Phase 6 provisioning will do for every new tenant.
	"""
	if not frappe.db.exists("Company", name):
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": name,
				"abbr": abbr,
				"default_currency": "INR",
				"country": "India",
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
	if seed:
		from a3_sola.setup.install import seed_masters

		# Idempotent, and it covers modules added after the company was created.
		seed_masters(name)
	return name


def make_address(city="Ernakulam", state="Kerala"):
	doc = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": f"Site {frappe.generate_hash(length=6)}",
			"address_type": "Other",
			"address_line1": "Test House",
			"city": city,
			"state": state,
			"country": "India",
			"pincode": "683585",
		}
	)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True).name


def make_consumer(company=None, **kwargs):
	company = company or default_company()
	values = {
		"doctype": "Solar Consumer",
		"company": company,
		"consumer_name": "Test Consumer",
		"consumer_category": "Residential",
		"discom": discom(company),
		"discom_section": section(company=company),
		"consumer_number": frappe.generate_hash(length=10),
		"connection_type": "Single Phase",
		"sanctioned_load_kw": 5,
		"avg_consumption_units": 500,
		"billing_frequency": "Bimonthly",
		"bank_account_holder_name": "Test Consumer",
		"bank_account_no": "028905004574",
		"bank_name": "ICICI Bank",
		"bank_ifsc_code": "ICIC0000289",
	}
	values.setdefault("installation_address", make_address())
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


def make_survey(consumer, segments=((400, True),), shading=0, submit=True, **kwargs):
	values = {
		"doctype": "Site Survey",
		"company": consumer.company,
		"solar_consumer": consumer.name,
		"survey_date": today(),
		"roof_type": name_of("Roof Type", "roof_type", "RCC Flat", consumer.company),
		"total_roof_area_sqft": sum(a for a, _ in segments),
		"feasibility_status": "Feasible",
		"roof_segments": [
			{"segment_name": f"S{i}", "area_sqft": area, "is_usable": 1 if usable else 0}
			for i, (area, usable) in enumerate(segments, start=1)
		],
	}
	if shading:
		values["shadow_observations"] = [
			{"time_slot": "10:00", "shading_percent": shading},
			{"time_slot": "14:00", "shading_percent": shading},
		]
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def make_estimate(consumer, survey=None, with_default_options=True, submit=False, **kwargs):
	values = {
		"doctype": "Solar Design Estimate",
		"company": consumer.company,
		"solar_consumer": consumer.name,
		"site_survey": survey.name if survey else None,
		"estimate_date": today(),
		"subsidy_scheme": scheme(consumer.company),
		"electricity_tariff": tariff(consumer.company),
		"net_meter_mode": "Purchased by Customer",
	}
	if with_default_options and "options" not in kwargs:
		pkg = package("3Kw 1PH", consumer.company)
		values["options"] = [
			{
				"option_name": "Option 1 - String Inverter",
				"inverter_topology": "String",
				"solar_package": pkg,
				"system_cost": 215000,
				"is_recommended": 1,
				"display_order": 1,
			}
		]
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc
