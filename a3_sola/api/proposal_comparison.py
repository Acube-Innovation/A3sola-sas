# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal's Design Comparison: the first design estimate in full, then each of the
others by what it changes.

Option 1 is set out item by item with its price and total. Every further option is
compared with Option 1 on its main components - the solar panels, the inverters and the
batteries - and shows only those that differ, with its own total beside Option 1's; the
rest of the system is as in Option 1. One builder serves the desk form, the portal page
and the proposal PDF, so all three say the same.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

#: The components an option is compared on, as (table, label).
MAIN_COMPONENTS = (("panels", "Solar Panel"), ("inverters", "Inverter"), ("batteries", "Battery"))


def _make(name):
	return frappe.db.get_value("Component Make", name, "make_name") if name else ""


def _technology(name):
	if not name:
		return ""
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	return technology_name(name) or ""


def _join(*parts):
	return " ".join(str(p) for p in parts if p not in (None, "", 0))


def _describe(table, row):
	"""A component as a customer reads it: make, size and kind."""
	if table == "panels":
		return _join(_make(row.panel_make), f"{flt(row.panel_capacity_wp):g} Wp" if flt(row.panel_capacity_wp) else "",
			row.panel_type, _technology(row.panel_variant))
	if table == "inverters":
		return _join(_make(row.inverter_make), f"{flt(row.inverter_capacity_kw):g} kW" if flt(row.inverter_capacity_kw) else "",
			_technology(row.inverter_type), row.inverter_phase)
	return _join(_make(row.battery_make), f"{flt(row.battery_voltage):g} V" if flt(row.battery_voltage) else "",
		f"{flt(row.battery_capacity_ah):g} Ah" if flt(row.battery_capacity_ah) else "", _technology(row.battery_variant))


def _component_lines(doc, table, label):
	"""The priced rows of one main component; a row marked as an Option is not priced."""
	return [
		{
			"component": _(label),
			"description": _describe(table, row),
			"qty": cint(row.nos),
			"rate": flt(row.rate),
			"amount": flt(row.amount),
		}
		for row in doc.get(table) or []
		if not row.get("is_option")
	]


def estimate_summary(name):
	"""One estimate as the comparison shows it: its main components and its commercials."""
	doc = frappe.get_doc("Solar Design Estimate", name)
	commercials = doc.commercials()
	main = {table: _component_lines(doc, table, label) for table, label in MAIN_COMPONENTS}
	main_keys = {table for table, _label in MAIN_COMPONENTS}
	package = frappe.db.get_value("Solar Package", doc.solar_package, "package_name") if doc.solar_package else ""
	return {
		"name": doc.name,
		"package": package or "",
		"capacity_kw": flt(doc.final_capacity_kw),
		"main": main,
		# Everything else priced, as one line each, in the commercials' order.
		"other_lines": [line for line in commercials["lines"] if line["key"] not in main_keys and flt(line["amount"])],
		"subtotal": commercials["subtotal"],
		"gst_percent": commercials["gst_percent"],
		"gst_amount": commercials["gst_amount"],
		"total": commercials["total"],
	}


def _signature(lines):
	"""What a component is, regardless of its price: compared between options."""
	return sorted((line["description"], line["qty"]) for line in lines)


def comparison(estimates):
	"""Option 1 in full, and for each further option the main components that differ."""
	names = [n for n in dict.fromkeys(estimates or []) if n and frappe.db.exists("Solar Design Estimate", n)]
	if not names:
		return None
	summaries = [estimate_summary(n) for n in names]
	base = summaries[0]
	variants = []
	for number, other in enumerate(summaries[1:], start=2):
		changes = []
		for table, label in MAIN_COMPONENTS:
			if _signature(base["main"][table]) != _signature(other["main"][table]):
				changes.append({
					"component": _(label),
					"base": base["main"][table],
					"this": other["main"][table],
				})
		variants.append({
			"number": number,
			"estimate": other,
			"changes": changes,
			"difference": flt(other["total"] - base["total"], 2),
		})
	return {"base": base, "variants": variants}


def render(estimates, for_print=False):
	"""The comparison as HTML, or an empty string when there is nothing to compare."""
	data = comparison(estimates)
	if not data:
		return ""
	return frappe.render_template(
		"a3_sola/templates/includes/proposal_comparison.html",
		{"data": data, "for_print": for_print, "money": lambda v: frappe.utils.fmt_money(v, currency="INR"), "_": _},
	)


@frappe.whitelist()
def get_design_comparison(estimates):
	"""The comparison for the estimates given, in order - the desk form's table as it stands,
	saved or not. Each estimate is read with the caller's own permissions."""
	names = frappe.parse_json(estimates) if isinstance(estimates, str) else estimates
	names = [n for n in (names or []) if n]
	for name in names:
		frappe.has_permission("Solar Design Estimate", "read", name, throw=True)
	return render(names)
