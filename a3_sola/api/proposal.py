# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One context builder for the proposal print format.

Every value the proposal prints is resolved here, once, so the covering letter, the
specification table and the KSEBL expenses block cannot disagree with each other. Nothing
in the template computes anything.
"""

import json

import frappe
from frappe.utils import cint, flt, getdate

from a3_sola.api import regulation
from a3_sola.api.settings import get_settings
from a3_sola.solar_crm.doctype.solar_package.solar_package import (
	default_inverter,
	default_module,
	default_system_items,
)


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

	module = default_module(package)
	rows = [
		{
			"item": "Solar Panels",
			"specification": module.module_specification if module else None,
			"make": (module.module_alternate_makes or _make_name(module.module_make))
			if module
			else None,
			"nos": module.module_count if module else None,
		}
	]

	for index, option in enumerate(options, start=1):
		pkg = packages.get(option.solar_package) or package
		# The estimate option records the inverter it was quoted with, so it is the answer.
		# The package's default is only the fallback for an option added before it did.
		fallback = default_inverter(pkg) if pkg else None
		spec = option.inverter_specification or (fallback.inverter_specification if fallback else None)
		make = _make_name(option.inverter_make) or (
			_make_name(fallback.inverter_make) if fallback else None
		)
		rows.append(
			{
				"item": "Solar PV Inverter",
				"specification": f"Option {index}\n{spec}" if len(options) > 1 else spec,
				"make": make,
				"nos": option.inverter_count or pkg.get(f"inverter_{suffix}_count"),
			}
		)

	rows.extend(_system_rows(package))
	rows.append(
		{
			"item": "Installation, Testing, Commissioning",
			"specification": "Complying with Electrical Inspectorate & DISCOM standards",
			"make": "",
			"nos": "",
		}
	)
	return rows


def _statutory_rows(estimate):
	"""The KSEBL Expenses block, computed - never typed."""
	if not estimate.statutory_breakdown:
		return {"rows": [], "total": 0}
	data = json.loads(estimate.statutory_breakdown)
	return {"rows": data.get("breakdown", []), "total": data.get("statutory_total", 0)}


#: How each balance-of-system part is presented, and what it says when the package's own
#: row does not. These were literals inside the row builder; they are the client's standing
#: defaults, so a package whose system table is filled in overrides them and one carried
#: over from the old fixed fields - which could hold no make at all - reads as it always did.
#:
#: (system_type, label, default specification, default make, quantity)
SYSTEM_PRESENTATION = (
	("DCDB", "DCDB", None, "MCBs - ABB/Eaton, Fuses - Mersen, SPD - Mersen", 1),
	("ACDB", "ACDB", None, "MCBs - ABB/Eaton, SPD - Mersen/Citel", 1),
	("DC Cable", "DC Cables", None, "Apar / Seichem", "Ls."),
	("AC Cable", "AC Cables", None, "Apar / Polycab", "Ls."),
	("Earthing", "Earthing",
	 "Maintenance free chemical earthing with 250 micron copper bonded earth rod, "
	 "14 mm dia / 1.2 m long", "Excel Earthing", "{qty} Sets"),
	("Lightning Protection", "Lightning Protection",
	 "Spike air termination rod with insulated base and chemical earth kit",
	 "Excel Earthing", "{qty} Set"),
	("Solar Energy Meter", "Solar Energy Meter", "Watt-hour meter", "L&T", "{qty}"),
	("Mounting Structure", "Solar PV Roof Mounting Structure", None,
	 "Apollo / Equivalent", "{capacity} kWp"),
	("Battery", "Battery Bank", None, None, "{qty}"),
)

#: Quantities that stand in for a count when the old fields held none.
FALLBACK_QUANTITY = {"Earthing": 2, "Lightning Protection": 1, "Solar Energy Meter": 1}


def _system_rows(package):
	"""The balance of system, from the package's own table.

	A type the package does not list is omitted rather than printed empty - a proposal that
	promises a battery bank the package has no row for is worse than one that is silent.
	The exception is the parts every job has: those keep printing on their standing
	defaults, because that is what the client's proposal has always said.
	"""
	if not package:
		return []
	chosen = default_system_items(package)
	rows = []
	for system_type, label, specification, make, quantity in SYSTEM_PRESENTATION:
		row = chosen.get(system_type)
		if row is None and system_type not in FALLBACK_QUANTITY and not specification:
			continue
		if row is None and system_type == "Battery":
			continue
		qty = cint(row.qty) if row and cint(row.qty) else FALLBACK_QUANTITY.get(system_type, 1)
		rows.append(
			{
				"item": label,
				"specification": (row.specification if row else None) or specification,
				"make": (_make_name(row.make) if row and row.make else None) or make or "",
				"nos": _quantity(quantity, qty, package),
			}
		)
	return rows


def _quantity(template, qty, package):
	"""`Ls.` stays `Ls.`; a count becomes the row's count; the structure is priced by kWp."""
	if not isinstance(template, str):
		return template
	return template.format(qty=qty, capacity=f"{flt(package.capacity_kw):g}")


def _warranty_rows(options, package):
	"""Warranty by make, read from Component Make. A change of brand cannot leave a stale term."""
	rows = []
	seen = set()

	module = default_module(package) if package else None
	if module and module.module_make:
		make = frappe.get_cached_doc("Component Make", module.module_make)
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
