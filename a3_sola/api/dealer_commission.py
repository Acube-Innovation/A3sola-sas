# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The dealer commission of a package: the Dealer Commission row of its Expenses, priced by the
package's own rule (its Expenses tab, Dealer Commission section). The rule is one of three:

* Formula - a base amount plus an amount per kW of the package's capacity
  (10,000 + 1,000 x 3 kW = 13,000), both the package's own;
* Percentage - a percent of the package's cost before the commission and the margin: its
  panel, inverter, battery, installation, materials, structure and other expenses;
* Lump Sum - a fixed amount.

A package carries the commission only when its Expenses has the Dealer Commission Item. Each
Pricing Options row has its own commission (solar_package.pricing_build_up), as each has its
own build cost; the Expenses row shows the default option's.
"""

from frappe.utils import flt

ITEM = "Dealer Commission"
RULES = ("Formula", "Percentage", "Lump Sum")


def is_commission(row):
	"""Whether an Expenses row is the dealer commission."""
	return row.get("item") == ITEM


def carries(package):
	"""Whether the package's Expenses has the commission row."""
	return any(is_commission(r) for r in package.get("expenses") or [])


def amount(package, before):
	"""The commission on `package` by its rule; `before` is its cost before the commission and the margin."""
	rule = package.get("dealer_commission_rule") or "Formula"
	if rule == "Percentage":
		value = flt(before) * flt(package.get("dealer_commission_percent")) / 100
	elif rule == "Lump Sum":
		value = flt(package.get("dealer_commission_lump_sum"))
	else:
		value = flt(package.get("dealer_commission_base")) + flt(package.get("dealer_commission_per_kw")) * flt(package.get("capacity_kw"))
	return flt(value, 2)
