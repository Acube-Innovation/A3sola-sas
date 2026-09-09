# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Move each package's commercial figures onto a priced configuration row.

The package carried one set of commercials: one discount, one subsidy, one net rate, one
set of statutory fees, one generation band. But a package is not one thing - it is a module
option and an inverter option and a choice of boards, and those combinations do not cost the
same. The single net rate was therefore the price of a configuration nobody had named.

Prices are rows now, and each one names the module, inverter, DCDB, ACDB and meter it is
the price of. This carries the existing figures onto the configuration the package is
already offered in: the default module, the default inverter, and the default board and
meter of each type. That row is what `default_price` finds afterwards, so every downstream
reader sees the same number it saw before.

Packages whose option tables cannot name a full configuration are left alone rather than
given a row with holes in it. A price attached to an incomplete combination is worse than
no price: it prints on a quotation looking exactly as authoritative as a real one.

The old columns are read with raw SQL - doctype sync has already dropped them from the meta
- and are left in the table as the only record of what the package said before today.
"""

import frappe
from frappe.utils import flt

COLUMNS = (
	"standard_discount", "additional_structure_and_cable_cost", "indicative_subsidy",
	"net_rate", "kseb_application_fee", "kseb_registration_fee",
	"kseb_registration_refundable", "net_meter_charge", "statutory_total",
	"expected_daily_units_low", "expected_daily_units_high",
)


def execute():
	if not frappe.db.exists("DocType", "Solar Package Price"):
		return None
	present = [c for c in COLUMNS if frappe.db.has_column("Solar Package", c)]
	if not present:
		return None  # a fresh install: nothing was ever on the package

	rows = frappe.db.sql(
		"select name, {} from `tabSolar Package`".format(", ".join(f"`{c}`" for c in present)),
		as_dict=True,
	)
	moved, incomplete, skipped = 0, [], 0
	for row in rows:
		if frappe.db.exists("Solar Package Price", {"parent": row.name}):
			skipped += 1
			continue
		package = frappe.get_doc("Solar Package", row.name)
		_name_the_nameless_parts(package)
		configuration = _default_configuration(package)
		if not all(configuration.values()):
			incomplete.append(row.name)
			continue
		package.append("prices", configuration | _figures(row, present))
		package.flags.ignore_permissions = True
		package.flags.ignore_validate_update_after_submit = True
		package.save(ignore_permissions=True)
		moved += 1

	frappe.db.commit()
	print(
		f"a3_sola: {moved} package(s) given a price row, {skipped} already had one, "
		f"{len(incomplete)} could not name a full configuration"
	)
	if incomplete:
		print("  no price row for: " + ", ".join(incomplete[:20])
		      + (" ..." if len(incomplete) > 20 else ""))
	return {"moved": moved, "skipped": skipped, "incomplete": incomplete}


#: What the proposal has always printed for a part whose old field held only a count. Not
#: an invention: these strings were literals in the proposal's row builder for as long as
#: the package has existed, so every quotation already said them.
STANDING_SPECIFICATIONS = {
	"Solar Energy Meter": "Watt-hour meter",
	"Earthing": (
		"Maintenance free chemical earthing with 250 micron copper bonded earth rod, "
		"14 mm dia / 1.2 m long"
	),
	"Lightning Protection": "Spike air termination rod with insulated base and chemical earth kit",
}


def _name_the_nameless_parts(package):
	"""Give a count-only part the specification its proposals were already printing.

	The old form had a *count* of energy meters and no place for what kind, so the system
	table carried that over faithfully - a row with a quantity and a blank name. A price
	row has to name its meter, and a blank cannot be chosen. The name it gets is the one
	the proposal has printed for it all along, so nothing changes on paper.
	"""
	for row in package.system_items or []:
		if row.specification or row.system_type not in STANDING_SPECIFICATIONS:
			continue
		row.specification = STANDING_SPECIFICATIONS[row.system_type]


def _default_configuration(package):
	"""The five choices the package is already offered with."""
	from a3_sola.solar_crm.doctype.solar_package.solar_package import (
		default_inverter,
		default_module,
		default_system_items,
	)

	module = default_module(package)
	inverter = default_inverter(package)
	system = default_system_items(package)
	return {
		"module": module.module_specification if module else None,
		"inverter": inverter.inverter_specification if inverter else None,
		"dcdb": (system.get("DCDB") or frappe._dict()).get("specification"),
		"acdb": (system.get("ACDB") or frappe._dict()).get("specification"),
		"energy_meter": (system.get("Solar Energy Meter") or frappe._dict()).get("specification"),
	}


def _figures(row, present):
	"""What the package said, carried across verbatim.

	`system_cost` is the one figure with nowhere to come from: the package never held a
	gross price, only a net rate computed from the default inverter's cost. So it is
	reconstructed the way the net rate was built - and where there was no price at all it
	stays zero, which is what an unpriced package has always been.
	"""
	figures = {column: flt(row.get(column)) for column in present}
	net = flt(row.get("net_rate"))
	if net:
		figures["system_cost"] = (
			net
			+ flt(row.get("indicative_subsidy"))
			+ flt(row.get("standard_discount"))
			- flt(row.get("additional_structure_and_cable_cost"))
		)
	else:
		figures["system_cost"] = 0.0
	return figures
