# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Move each package's single module spec into the module options table.

A package is one array offered several ways. The two inverter options have always sat side
by side on one package for exactly that reason - the same panels quoted with a string
inverter and with microinverters. The modules were the exception: one specification, one
make, one wattage, so quoting the DCR panel and its non-DCR equivalent meant duplicating
the whole package and keeping the two in step by hand.

They are a table now, with one row marked default. This carries the existing values into
that first row and ticks it, so every package keeps quoting exactly what it quoted before.

The old columns are read with raw SQL: doctype sync has already removed the fields from
the meta by the time this runs, but Frappe never drops a column, so the values are still
there. They are left in place rather than dropped - a column costs nothing and is the only
copy of what the package said before today.
"""

import frappe

COLUMNS = (
	"module_specification",
	"module_make",
	"module_alternate_makes",
	"module_wattage",
	"module_count",
)


def execute():
	if not frappe.db.exists("DocType", "Solar Package Module"):
		return None
	present = [c for c in COLUMNS if frappe.db.has_column("Solar Package", c)]
	if not present:
		return None  # a fresh install: the packages were seeded into the table already

	rows = frappe.db.sql(
		"select name, {} from `tabSolar Package`".format(", ".join(f"`{c}`" for c in present)),
		as_dict=True,
	)
	moved, skipped = 0, 0
	for row in rows:
		if frappe.db.exists("Solar Package Module", {"parent": row.name}):
			skipped += 1
			continue
		if not any(row.get(c) for c in present):
			skipped += 1
			continue
		package = frappe.get_doc("Solar Package", row.name)
		package.append("modules", {c: row.get(c) for c in present} | {"is_default": 1})
		package.flags.ignore_permissions = True
		package.flags.ignore_validate_update_after_submit = True
		package.save(ignore_permissions=True)
		moved += 1

	frappe.db.commit()
	print(f"a3_sola: {moved} package(s) moved to the module options table, {skipped} left alone")
	return {"moved": moved, "skipped": skipped}
