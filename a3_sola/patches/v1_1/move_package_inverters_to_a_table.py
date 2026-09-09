# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Move each package's two fixed inverter options into the inverter options table.

The package always carried two inverter options side by side - the same array quoted with
a string inverter and with panel-level optimisers - and two prices to match, `cost_option_1`
and `cost_option_2`, paired to the options by number. Two was the ceiling, and the pairing
lived in the field names, so a third option could be described but never priced.

They are rows now, each carrying its own cost, so the price and the inverter it is the
price of cannot drift apart. This moves option 1 and, where it exists, option 2 - marking
option 1 the default, because that is what every reader used when there was a choice.

A package with a price but no inverter spec still gets a row: the price is the thing that
must survive, and an empty specification is visible on the form where a lost figure is not.

The old columns are read with raw SQL - doctype sync has already dropped them from the
meta - and are left in the table afterwards as the only record of what the package said.
"""

import frappe
from frappe.utils import flt

OPTIONS = (
	("inverter_1_specification", "inverter_1_make", "inverter_1_capacity_kw",
	 "inverter_1_count", "cost_option_1"),
	("inverter_2_specification", "inverter_2_make", "inverter_2_capacity_kw",
	 "inverter_2_count", "cost_option_2"),
)
COLUMNS = tuple(column for option in OPTIONS for column in option)


def execute():
	if not frappe.db.exists("DocType", "Solar Package Inverter"):
		return None
	present = [c for c in COLUMNS if frappe.db.has_column("Solar Package", c)]
	if not present:
		return None  # a fresh install: the packages were seeded into the table already

	rows = frappe.db.sql(
		"select name, {} from `tabSolar Package`".format(", ".join(f"`{c}`" for c in present)),
		as_dict=True,
	)
	moved, options, skipped = 0, 0, 0
	for row in rows:
		if frappe.db.exists("Solar Package Inverter", {"parent": row.name}):
			skipped += 1
			continue
		built = _options_of(row)
		if not built:
			skipped += 1
			continue
		package = frappe.get_doc("Solar Package", row.name)
		for option in built:
			package.append("inverters", option)
		package.flags.ignore_permissions = True
		package.flags.ignore_validate_update_after_submit = True
		package.save(ignore_permissions=True)
		moved += 1
		options += len(built)

	frappe.db.commit()
	print(
		f"a3_sola: {moved} package(s) moved to the inverter options table "
		f"({options} option rows), {skipped} left alone"
	)
	return {"moved": moved, "options": options, "skipped": skipped}


def _options_of(row):
	"""One row per inverter option that has anything in it at all."""
	built = []
	for index, (spec, make, capacity, count, cost) in enumerate(OPTIONS):
		values = {
			"inverter_specification": row.get(spec),
			"inverter_make": row.get(make),
			"inverter_capacity_kw": flt(row.get(capacity)),
			"inverter_count": row.get(count),
			"cost": flt(row.get(cost)),
		}
		if not values["inverter_specification"] and not values["cost"]:
			continue
		values["is_default"] = 1 if not built else 0
		built.append(values)
	return built
