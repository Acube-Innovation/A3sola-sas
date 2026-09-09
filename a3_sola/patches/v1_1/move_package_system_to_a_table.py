# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Move each package's balance-of-system fields into the system items table.

Ten fixed fields described the boards, cables, structure, meters, earthing, protection and
battery: five of them a specification with no quantity, three a quantity with no
specification, and the battery one of each. None of them carried a make, a rating or a
price, so what the DCDB actually costs lived in somebody's workbook and not in the app.

They are rows now, typed, each with its make, capacity, quantity and cost, and one row per
type marked as the one quoted - so a package can offer two boards with one standard.

The five specification fields become rows with a quantity of one, because that is what they
meant. The three count fields become rows with the count and no specification, because that
is what *they* meant, and inventing a specification here would be putting words in the
client's mouth. The battery contributes one row carrying both.

The old columns are read with raw SQL - doctype sync has already dropped them from the meta
- and are left in the table as the only record of what the package said before today.
"""

import frappe
from frappe.utils import cint

#: (column, system_type, kind). "spec" columns hold text and imply one of the thing;
#: "count" columns hold a number and say nothing about what it is.
SOURCES = (
	("dcdb_specification", "DCDB", "spec"),
	("acdb_specification", "ACDB", "spec"),
	("dc_cable_specification", "DC Cable", "spec"),
	("ac_cable_specification", "AC Cable", "spec"),
	("mounting_structure_specification", "Mounting Structure", "spec"),
	("solar_energy_meter_count", "Solar Energy Meter", "count"),
	("earthing_sets", "Earthing", "count"),
	("lightning_protection_sets", "Lightning Protection", "count"),
	("battery_specification", "Battery", "spec"),
	("battery_count", "Battery", "count"),
)
COLUMNS = tuple(dict.fromkeys(column for column, _type, _kind in SOURCES))


def execute():
	if not frappe.db.exists("DocType", "Solar Package System Item"):
		return None
	present = [c for c in COLUMNS if frappe.db.has_column("Solar Package", c)]
	if not present:
		return None  # a fresh install: the packages were seeded into the table already

	rows = frappe.db.sql(
		"select name, {} from `tabSolar Package`".format(", ".join(f"`{c}`" for c in present)),
		as_dict=True,
	)
	moved, items, skipped = 0, 0, 0
	for row in rows:
		if frappe.db.exists("Solar Package System Item", {"parent": row.name}):
			skipped += 1
			continue
		built = _items_of(row, present)
		if not built:
			skipped += 1
			continue
		package = frappe.get_doc("Solar Package", row.name)
		for item in built:
			package.append("system_items", item)
		package.flags.ignore_permissions = True
		package.flags.ignore_validate_update_after_submit = True
		package.save(ignore_permissions=True)
		moved += 1
		items += len(built)

	frappe.db.commit()
	print(
		f"a3_sola: {moved} package(s) moved to the system items table "
		f"({items} rows), {skipped} left alone"
	)
	return {"moved": moved, "items": items, "skipped": skipped}


def _items_of(row, present):
	"""One row per type, merging the specification and count columns of the same type."""
	built = {}
	for column, system_type, kind in SOURCES:
		if column not in present:
			continue
		value = row.get(column)
		if not value:
			continue
		item = built.setdefault(
			system_type,
			{"system_type": system_type, "specification": None, "qty": 0, "is_default": 1},
		)
		if kind == "spec":
			item["specification"] = value
		else:
			item["qty"] = cint(value)
	# A specification with no count meant one of the thing; that is what the form showed.
	for item in built.values():
		if not item["qty"]:
			item["qty"] = 1
	return list(built.values())
