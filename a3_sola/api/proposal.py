# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One context builder for the proposal print format.

Every value the proposal prints is resolved here, once, so the covering letter, the
specification table and the KSEBL expenses block cannot disagree with each other. Nothing
in the template computes anything.
"""

import json

import frappe
from frappe.utils import flt, getdate

from a3_sola.api import regulation
from a3_sola.api.settings import get_settings


def proposal_context(proposal):
	"""Assemble everything the Solar Proposal print format renders."""
	doc = frappe.get_doc("Solar Proposal", proposal) if isinstance(proposal, str) else proposal
	settings = get_settings()
	estimate = frappe.get_doc("Solar Design Estimate", doc.solar_design_estimate)
	consumer = frappe.get_doc("Solar Consumer", estimate.solar_consumer)
	survey = frappe.get_doc("Site Survey", estimate.site_survey) if estimate.site_survey else None
	company = frappe.get_doc("Company", doc.company)

	options = sorted(estimate.options, key=lambda r: (r.display_order or 0, r.idx))
	packages = {}
	for row in options:
		if row.solar_package and row.solar_package not in packages:
			packages[row.solar_package] = frappe.get_doc("Solar Package", row.solar_package)
	primary = None
	for row in options:
		if row.is_recommended and row.solar_package:
			primary = packages.get(row.solar_package)
			break
	if not primary and packages:
		primary = next(iter(packages.values()))

	return {
		"doc": doc,
		"settings": settings,
		"discom_name": frappe.db.get_value("DISCOM", consumer.discom, "discom_name") if consumer.discom else None,
		"estimate": estimate,
		"consumer": consumer,
		"survey": survey,
		"company": company,
		"options": options,
		"packages": packages,
		"primary_package": primary,
		"specification_rows": _specification_rows(primary, options, packages),
		"statutory": _statutory_rows(estimate),
		"warranty": _warranty_rows(options, primary),
		"scope": {
			"company": [r for r in settings.scope_of_work if r.responsibility == "Company"],
			"customer": [r for r in settings.scope_of_work if r.responsibility == "Customer"],
		},
		"regulation_clauses": regulation.get_customer_clauses(consumer.discom, doc.proposal_date, doc.company),
		"executive_summary": _executive_summary(doc, estimate, consumer, survey, primary),
	}


def _executive_summary(doc, estimate, consumer, survey, package):
	"""The client's Executive Summary table, row for row."""
	location = doc.location or ""
	building = "Residential Building" if consumer.consumer_category == "Residential" else "Commercial Building"
	roof_type = (survey.roof_type if survey else None) or consumer.roof_type
	roof = (
		frappe.db.get_value("Roof Type", roof_type, ["roof_type", "typical_tilt_degrees"], as_dict=True)
		if roof_type
		else None
	)
	roof_label = roof.roof_type if roof else None
	tilt = roof.typical_tilt_degrees if roof else None
	area = flt(package.area_required_sqft) if package else flt(estimate.final_capacity_kw) * 80

	phase = estimate.connection_type or consumer.connection_type or ""
	capacity = f"{flt(estimate.final_capacity_kw):g} kWp"
	if phase:
		capacity = f"{capacity} {phase}"

	return [
		("Site Location", f"{building} in {location}" if location else building),
		("Capacity of the Plant Proposed", capacity),
		("Tilt & Orientation", f"{flt(tilt or 11):g} degrees, South"),
		("Type of Solar Power Plant", "Grid Connected Rooftop"),
		("Roof Area Required", f"{flt(area):g} Sq. Ft."),
		("Type of Roof", roof_label or "-"),
		(
			"Expected generation per day",
			f"{flt(estimate.expected_daily_units_low):g} - {flt(estimate.expected_daily_units_high):g} units",
		),
	]


def _specification_rows(package, options, packages):
	"""The eleven-row specification table, in the client's order.

	The inverter appears once per quoted option, labelled as the client labels them.
	"""
	if not package:
		return []

	rows = [
		{
			"item": "Solar Panels",
			"specification": package.module_specification,
			"make": package.module_alternate_makes or _make_name(package.module_make),
			"nos": package.module_count,
		}
	]

	for index, option in enumerate(options, start=1):
		pkg = packages.get(option.solar_package) or package
		suffix = "2" if option.inverter_topology in ("String with Optimiser",) and pkg.inverter_2_specification else "1"
		spec = option.inverter_specification or pkg.get(f"inverter_{suffix}_specification")
		make = _make_name(option.inverter_make) or _make_name(pkg.get(f"inverter_{suffix}_make"))
		rows.append(
			{
				"item": "Solar PV Inverter",
				"specification": f"Option {index}\n{spec}" if len(options) > 1 else spec,
				"make": make,
				"nos": option.inverter_count or pkg.get(f"inverter_{suffix}_count"),
			}
		)

	rows.extend(
		[
			{"item": "DCDB", "specification": package.dcdb_specification, "make": "MCBs - ABB/Eaton, Fuses - Mersen, SPD - Mersen", "nos": 1},
			{"item": "ACDB", "specification": package.acdb_specification, "make": "MCBs - ABB/Eaton, SPD - Mersen/Citel", "nos": 1},
			{"item": "DC Cables", "specification": package.dc_cable_specification, "make": "Apar / Seichem", "nos": "Ls."},
			{"item": "AC Cables", "specification": package.ac_cable_specification, "make": "Apar / Polycab", "nos": "Ls."},
			{
				"item": "Earthing",
				"specification": "Maintenance free chemical earthing with 250 micron copper bonded earth rod, 14 mm dia / 1.2 m long",
				"make": "Excel Earthing",
				"nos": f"{package.earthing_sets or 2} Sets",
			},
			{
				"item": "Lightning Protection",
				"specification": "Spike air termination rod with insulated base and chemical earth kit",
				"make": "Excel Earthing",
				"nos": f"{package.lightning_protection_sets or 1} Set",
			},
			{"item": "Solar Energy Meter", "specification": "Watt-hour meter", "make": "L&T", "nos": package.solar_energy_meter_count or 1},
			{
				"item": "Solar PV Roof Mounting Structure",
				"specification": package.mounting_structure_specification,
				"make": "Apollo / Equivalent",
				"nos": f"{flt(package.capacity_kw):g} kWp",
			},
			{
				"item": "Installation, Testing, Commissioning",
				"specification": "Complying with Electrical Inspectorate & DISCOM standards",
				"make": "",
				"nos": "",
			},
		]
	)
	return rows


def _statutory_rows(estimate):
	"""The KSEBL Expenses block, computed - never typed."""
	if not estimate.statutory_breakdown:
		return {"rows": [], "total": 0}
	data = json.loads(estimate.statutory_breakdown)
	return {"rows": data.get("breakdown", []), "total": data.get("statutory_total", 0)}


def _warranty_rows(options, package):
	"""Warranty by make, read from Component Make. A change of brand cannot leave a stale term."""
	rows = []
	seen = set()

	if package and package.module_make:
		make = frappe.get_cached_doc("Component Make", package.module_make)
		rows.append(
			{
				"component": "Solar PV Modules",
				"make": make.make_name,
				"terms": _warranty_sentence(make),
			}
		)
		seen.add(make.name)

	for option in options:
		if not option.inverter_make or option.inverter_make in seen:
			continue
		make = frappe.get_cached_doc("Component Make", option.inverter_make)
		rows.append({"component": "Inverter", "make": make.make_name, "terms": _warranty_sentence(make)})
		seen.add(make.name)

	return rows


def _warranty_sentence(make):
	parts = []
	if make.product_warranty_years:
		parts.append(f"{make.product_warranty_years} years product warranty")
	if make.performance_warranty_years:
		parts.append(f"{make.performance_warranty_years} years performance warranty")
	if make.performance_floor_10yr_percent and make.performance_floor_25yr_percent:
		parts.append(
			f"output not less than {flt(make.performance_floor_10yr_percent):g}% at 10 years and "
			f"{flt(make.performance_floor_25yr_percent):g}% at 25 years"
		)
	return ", ".join(parts) or "As offered by the manufacturer"


def _make_name(make):
	return frappe.db.get_value("Component Make", make, "make_name") if make else None
