# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""KSEB, mounting and installation expense tables, shared by the package and the estimate.

Both carry the same three tables on the same child doctypes, so they are filled the same
way: the rows the system can work out are refreshed on every save, and rows added by hand
are kept as typed.
"""

import frappe
from frappe.utils import flt

# Each expense table's item column links to Items in its own group under EXPENSE_ITEM_GROUP,
# so each dropdown offers only its own kind. The Items the system fills in are listed per
# table, keyed by the row's source. Seeded by a3_sola.setup.install.seed_expense_items.
EXPENSE_ITEM_GROUP = "Solar Expenses"
EXPENSE_GROUPS = {
	"kseb_expenses": "KSEB Expenses",
	"mounting_expenses": "Mounting Structure Expenses",
	"installation_expenses": "Installation Expenses",
}
EXPENSE_ITEMS = {
	"kseb_expenses": {
		"application": "KSEB Application Fee",
		"registration": "KSEB Registration Fee",
		"net_meter": "Net Meter",
	},
	"mounting_expenses": {"roof_type": "Solar PV Roof Mounting Structure"},
	"installation_expenses": {"installation": "Installation, Testing and Commissioning"},
}


def fill_expense_tables(doc, roof_type, panel_kw, fees):
	"""Refresh the computed rows of kseb_expenses, mounting_expenses and installation_expenses.

	`fees` carries the resolved statutory figures: application_fee, registration_fee and
	net_meter_charge. Mounting and installation are priced per kW of panels on the roof type.
	"""
	kseb = EXPENSE_ITEMS["kseb_expenses"]
	upsert_computed_rows(
		doc,
		"kseb_expenses",
		{
			# A fee, once: its Rate the fee, Quantity 1.
			"application": _fee(kseb["application"], fees.get("application_fee")),
			"registration": _fee(kseb["registration"], fees.get("registration_fee")),
			"net_meter": _fee(kseb["net_meter"], fees.get("net_meter_charge")),
		},
	)

	roof = (
		frappe.db.get_value(
			"Roof Type",
			roof_type,
			[
				"mounting_structure_specification",
				"mounting_structure_make",
				"mounting_structure_rate_per_kw",
				"installation_specification",
				"installation_rate_per_kw",
			],
			as_dict=True,
		)
		if roof_type
		else None
	) or frappe._dict()

	upsert_computed_rows(
		doc,
		"mounting_expenses",
		{
			"roof_type": {
				"item": EXPENSE_ITEMS["mounting_expenses"]["roof_type"],
				"specification": roof.mounting_structure_specification,
				"make": roof.mounting_structure_make,
				"capacity_kw": panel_kw,
				"amount": flt(panel_kw * flt(roof.mounting_structure_rate_per_kw), 2),
			}
		},
	)

	fill_installation_line(doc, roof, panel_kw)


def fill_installation_line(doc, roof, panel_kw):
	"""The installation line (source "installation"), first in its table: the roof type's rate per kW
	for the panel kW - Rate and Quantity set from them - where the roof type has a rate; else priced
	at the Rate and Quantity typed on it. Its specification is typed here and kept. Before rows said
	where they came from, the table's first row was the line. Rows added by hand are left as they are."""
	rows = doc.get("installation_expenses") or []
	line = next((r for r in rows if r.get("source") == "installation"), None)
	if not line and rows and not any(r.get("source") for r in rows):
		line = rows[0]
		line.source = "installation"
	if not line:
		line = doc.append("installation_expenses", {"item": EXPENSE_ITEMS["installation_expenses"]["installation"],
			"specification": roof.installation_specification, "source": "installation"})
		rows = doc.get("installation_expenses")
		rows.remove(line)
		rows.insert(0, line)
		for idx, row in enumerate(rows, 1):
			row.idx = idx
	rate = flt(roof.installation_rate_per_kw)
	if rate:
		line.rate, line.qty = rate, flt(panel_kw, 3)
		line.amount = flt(rate * flt(panel_kw), 2)
	else:
		price_by_rate([line], computed_too=True)


def _fee(particulars, amount):
	return {"particulars": particulars, "rate": amount, "qty": 1, "amount": amount}


def price_by_rate(rows, computed_too=False):
	"""Each row added by hand (KSEB, installation, an optional add-on) priced at its Rate times its Quantity (one,
	left blank); a row with no Rate yet - blank, or the 0 a new column starts at - keeps the Amount it
	has. The rows the system fills in are priced by it, unless `computed_too`."""
	for row in rows or []:
		if (row.get("source") and not computed_too) or (not flt(row.get("rate")) and flt(row.get("amount"))):
			continue
		qty = 1 if row.get("qty") in (None, "") else flt(row.qty)
		row.amount = flt(flt(row.rate) * qty, 2)


def upsert_computed_rows(doc, table, computed):
	"""Refresh the rows the system computes, keyed by source; rows added by hand are kept as typed.

	A computed row deleted on the form comes back on save - these figures are not optional.
	"""
	existing = {row.source: row for row in doc.get(table) if row.source}
	for position, (source, values) in enumerate(computed.items()):
		row = existing.get(source)
		if row:
			row.update(values)
		else:
			row = doc.append(table, {"source": source, **values})
			# New computed rows go ahead of the hand-added ones, in their fixed order.
			doc.get(table).remove(row)
			doc.get(table).insert(position, row)
	for idx, row in enumerate(doc.get(table), 1):
		row.idx = idx
