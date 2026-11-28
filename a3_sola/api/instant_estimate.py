# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The indicative estimate a visitor sees the moment they register at an event.

From one number - their electricity bill - to a system size, its price, the subsidy, the net
cost, the monthly saving and the payback. Built from what the design estimate itself uses:
the default tariff (`calculations.calculate_bill`, telescopic, per two-month bill as KSEB
bills), the default specific yield, and the packages' own prices and subsidy
(`solar_package.price_for`). It is always "indicative": the engineer's design estimate after
the site visit is what is quoted.
"""

import frappe
from frappe.utils import cint, flt

from a3_sola.api import calculations
from a3_sola.api.settings import get_float, get_value

#: A KSEB bill covers two months; the tariff's slabs are per bill (solar_design_estimate).
CYCLE_MONTHS = 2
#: ₹ per unit, when no tariff is set: roughly the domestic average.
FALLBACK_RATE = 7.0
#: Systems with a battery: the PM Surya Ghar subsidy and the grid saving do not apply, and the
#: engineer designs the battery - the estimate gives the size and the price only.
BATTERY_SYSTEMS = ("Off-grid", "Hybrid")
#: The form's system (custom_fields.SYSTEM_TYPE) as a Solar Package's system_type. "Not sure"
#: (or nothing) is offered an on-grid package.
PACKAGE_SYSTEM = {"On-grid": "On-Grid", "Off-grid": "Off-Grid", "Hybrid": "Hybrid"}
#: Off the grid there is no PM Surya Ghar subsidy and no bill to save on.
OFF_GRID = "Off-grid"
#: The visitor's connection and subsidy answers (the form's), as the Solar Package and the
#: design estimate name them. Not answered: the package is chosen without them.
CONNECTION_TYPES = ("Single Phase", "Three Phase")
WITH_SUBSIDY, WITHOUT_SUBSIDY = "With Subsidy", "Without Subsidy"
SUBSIDY_OPTIONS = (WITH_SUBSIDY, WITHOUT_SUBSIDY)
#: Single phase up to this size; above it a three-phase package is offered first.
SINGLE_PHASE_UPTO_KW = 5

#: A need no package covers is sized by the sales team's rule of thumb (`custom_size`):
#: the monthly bill less its fixed charges, at an average rate per unit, over the days of a
#: month and what a kWp makes a day.
CUSTOM_ENERGY_SHARE = 0.9  # 10% of a bill is fixed charges
CUSTOM_RATE_PER_UNIT = 8.0  # ₹ per unit, on average
CUSTOM_DAYS = 30
CUSTOM_UNITS_PER_KW_DAY = 4.0
#: ₹ per kW of a custom system (above 10 kW, on average), quoted on the top of its range.
CUSTOM_PRICE_PER_KW = 42000
#: The range a custom size is shown in: 46.9 kW is "45-50 kW".
CUSTOM_RANGE_KW = 5


def units_for_bill(tariff, bill_per_cycle):
	"""The units a two-month bill of this amount means under the tariff: the tariff's bill
	rises with the units, so it is found by halving the range."""
	bill = flt(bill_per_cycle)
	if bill <= 0:
		return 0.0
	if not tariff:
		return bill / (get_float("estimate_rate_per_unit", FALLBACK_RATE) or FALLBACK_RATE)
	low, high = 0.0, 20000.0
	if flt(calculations.calculate_bill(tariff, high)["total_amount"]) < bill:
		return high
	for _ in range(40):
		mid = (low + high) / 2
		if flt(calculations.calculate_bill(tariff, mid)["total_amount"]) < bill:
			low = mid
		else:
			high = mid
	return round(high, 1)


def package_system(system_type):
	"""The Solar Package system_type for the form's system: On-Grid when not sure."""
	return PACKAGE_SYSTEM.get(system_type or "", "On-Grid")


def candidate_packages(company, names=None, system_type=None, connection_type=None, subsidy_option=None):
	"""[{name, package_name, capacity_kw, connection_type, price, subsidy, net, option}] the
	estimate may offer for the visitor's system (`package_system`): the event's chosen packages
	of that system, else every active package of that system of the company - each at its
	lowest price (`lowest_option`): the visitor's proposal quotes that option. A hybrid visitor
	is never priced on an on-grid package.

	The visitor's connection, when given, is the packages' (a single-phase home is never priced
	on a three-phase package). With subsidy: the subsidy - DCR - packages only, as an on-grid
	visitor who did not say always is. Without subsidy: the non-DCR packages, else the DCR ones
	(priced without it)."""
	system = package_system(system_type)
	filters = {"system_type": system}
	if connection_type in CONNECTION_TYPES:
		filters["connection_type"] = connection_type
	if subsidy_option == WITH_SUBSIDY or (system == "On-Grid" and subsidy_option != WITHOUT_SUBSIDY):
		filters["is_dcr_compliant"] = 1

	def of(where):
		rows = _packages({**where, **filters, "is_dcr_compliant": 0}) if subsidy_option == WITHOUT_SUBSIDY else []
		return rows or _packages({**where, **filters})

	rows = of({"name": ["in", list(names)]}) if names else []
	if not rows:
		rows = of({"company": company, "is_active": 1})
	return _priced(rows)


def _packages(filters):
	return frappe.get_all("Solar Package", filters=filters,
		fields=["name", "package_name", "capacity_kw", "connection_type", "status", "system_type"])


def _priced(rows):
	from a3_sola.solar_crm.doctype.solar_package.solar_package import price_for, system_inverters

	out = []
	for row in rows:
		if row.status and row.status != "Active" or not flt(row.capacity_kw):
			continue
		# A Hybrid package with no hybrid inverter would be priced as an on-grid plant.
		if row.system_type == "Hybrid" and not system_inverters(row.name):
			continue
		try:
			price = price_for(row.name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: instant estimate price of {row.name}")
			continue
		option = lowest_option(row.name, row.connection_type)
		cost = flt(option.cost) if option else flt(price.system_cost)
		if not cost:
			continue
		subsidy = flt(price.indicative_subsidy)
		out.append(frappe._dict(name=row.name, package_name=row.package_name, capacity_kw=flt(row.capacity_kw),
			connection_type=row.connection_type, price=cost, subsidy=subsidy, net=cost - subsidy,
			option=option.name if option else None))
	return out


def lowest_option(package, phase=None):
	"""The package's cheapest priced Pricing Options row for this connection (any, when it has
	none for it), or None when no row has a price."""
	from a3_sola.solar_crm.doctype.solar_package.solar_package import pricing_combinations

	combos = [c for c in pricing_combinations(package, phase) if flt(c.cost) > 0]
	if not combos and phase:
		combos = [c for c in pricing_combinations(package) if flt(c.cost) > 0]
	return min(combos, key=lambda c: (flt(c.cost), not c.default)) if combos else None


def pick(packages, need_kw):
	"""The package for `need_kw`: the smallest size that covers it (the largest when none does),
	single phase first up to 5 kW and three phase above, then the lowest price."""
	if not packages:
		return None, False
	sizes = sorted({p.capacity_kw for p in packages})
	size = next((s for s in sizes if s + 0.05 >= need_kw), sizes[-1])
	larger = need_kw > sizes[-1] + 0.05
	phase = "Single Phase" if size <= SINGLE_PHASE_UPTO_KW else "Three Phase"
	same = [p for p in packages if p.capacity_kw == size]
	same.sort(key=lambda p: (p.connection_type != phase, p.price))
	return same[0], larger


def custom_size(monthly_bill):
	"""The kW a monthly bill calls for when no package covers it: ₹50,000 x 0.9 / ₹8 a unit /
	30 days / 4 units a kWp a day = 46.9 kW."""
	return flt(monthly_bill) * CUSTOM_ENERGY_SHARE / CUSTOM_RATE_PER_UNIT / CUSTOM_DAYS / CUSTOM_UNITS_PER_KW_DAY


def custom_estimate(kw, monthly_bill, monthly_units, battery=False):
	"""The estimate for a system no package covers: a size range, a price on its top end, and
	no package - so no proposal; our engineer designs it after a site survey."""
	low = int(flt(kw) // CUSTOM_RANGE_KW) * CUSTOM_RANGE_KW
	high = low + CUSTOM_RANGE_KW
	price = high * CUSTOM_PRICE_PER_KW
	return {
		"kw": high, "kw_min": low, "kw_max": high, "need_kw": round(flt(kw), 1),
		"package": None, "package_name": None, "option": None, "connection_type": None,
		"price": price, "subsidy": 0, "net": price,
		"monthly_units": round(monthly_units), "monthly_bill": round(monthly_bill),
		"monthly_saving": 0, "payback_years": None, "larger": True, "custom": True, "battery": bool(battery),
	}


def estimate(company, bill_amount, bill_months=CYCLE_MONTHS, interest="Home", packages=None, system_type=None,
		connection_type=None, subsidy_option=None):
	"""The indicative estimate for an electricity bill of `bill_amount` covering `bill_months`
	(1 or 2), or None when there is no bill. A dict of plain numbers:

	kw, package, package_name, price, subsidy, net, monthly_units, monthly_bill, monthly_saving,
	payback_years, larger (the need is above the largest package: the engineer sizes it).

	A need no package covers (above the largest, or no package at all) is a `custom_estimate`:
	`custom`, a kw_min-kw_max range, a price at CUSTOM_PRICE_PER_KW, and no package - no proposal.

	The package is one of the visitor's system (`candidate_packages`): a hybrid visitor is
	priced on a hybrid package. The subsidy (PM Surya Ghar) is for homes on the grid - on-grid
	or hybrid, as the design estimate allows it; anything else (a shop, an off-grid system) is
	shown without it, and without a saving worked from the domestic tariff. `battery` marks an
	off-grid or hybrid system (BATTERY_SYSTEMS): our engineer confirms the battery.

	`connection_type` and `subsidy_option` are the visitor's answers, when given: the package
	is of that connection, and one without subsidy is shown - and quoted - without it.

	An Event Package Rule of the company that matches the bill and answers (`ruled_package`)
	gives the package instead, `rule` naming it; the event's own packages do not limit it."""
	bill = flt(bill_amount)
	months = 1 if cint(bill_months) == 1 else CYCLE_MONTHS
	if bill <= 0:
		return None
	cycle_bill = bill * CYCLE_MONTHS / months
	tariff = get_value("default_tariff")
	tariff = tariff if tariff and frappe.db.exists("Electricity Tariff", tariff) else None
	units = units_for_bill(tariff, cycle_bill)
	specific_yield = get_float("default_specific_yield", 1500.0) or 1500.0
	need_kw = units * (12 / CYCLE_MONTHS) / specific_yield

	package, larger, rule = None, False, ruled_package(company, cycle_bill, interest, system_type, connection_type,
		subsidy_option)
	if rule:
		package, rule = rule
	else:
		package, larger = pick(candidate_packages(company, packages, system_type, connection_type, subsidy_option), need_kw)
	battery = (system_type or "") in BATTERY_SYSTEMS
	if not package or larger:
		monthly_bill = cycle_bill / CYCLE_MONTHS
		return custom_estimate(max(custom_size(monthly_bill), need_kw), monthly_bill, units / CYCLE_MONTHS, battery)
	home = (interest or "Home") == "Home" and system_type != OFF_GRID
	subsidy = package.subsidy if home and subsidy_option != WITHOUT_SUBSIDY else 0.0
	net = package.price - subsidy

	monthly_saving = 0.0
	if home and tariff and units:
		generated = package.capacity_kw * specific_yield / (12 / CYCLE_MONTHS)
		saving = calculations.calculate_savings(tariff, units, max(units - generated, 0))
		monthly_saving = flt(saving["saving_amount"]) / CYCLE_MONTHS
	payback = round(net / (monthly_saving * 12), 1) if monthly_saving > 0 and net > 0 else None

	return {
		"kw": package.capacity_kw, "package": package.name, "package_name": package.package_name,
		"option": package.option, "connection_type": package.connection_type,
		"price": round(package.price), "subsidy": round(subsidy), "net": round(net),
		"monthly_units": round(units / CYCLE_MONTHS), "monthly_bill": round(cycle_bill / CYCLE_MONTHS),
		"monthly_saving": round(monthly_saving / 10) * 10, "payback_years": payback, "larger": bool(larger),
		"battery": battery, "system_type": package_system(system_type),
		"subsidy_option": WITH_SUBSIDY if subsidy else WITHOUT_SUBSIDY,
		"rule": rule,
	}


def ruled_package(company, cycle_bill, interest=None, system_type=None, connection_type=None, subsidy_option=None):
	"""(package, rule name) when an Event Package Rule of the company (Administration > Event
	Packages) matches the two-month bill and the answers and its package can be priced; else None,
	and the package is chosen automatically."""
	from a3_sola.api.event_package_rules import match

	rule = match(company, cycle_bill, interest, system_type, connection_type, subsidy_option)
	if not rule:
		return None
	priced = _priced(_packages({"name": rule.package}))
	if not priced:
		frappe.log_error(f"Event Package Rule {rule.name}: package {rule.package} has no price", "a3_sola: event package rule")
		return None
	return priced[0], rule.name


def summary(est):
	"""One line for a message: "3 kW system - ₹2,16,600, ₹78,000 subsidy, ₹1,38,600 after subsidy -
	saves about ₹2,400 a month"."""
	if not est:
		return ""
	if est.get("custom"):
		return "{0}-{1} kW system · about ₹{2} · custom-designed by our engineer after a site survey".format(
			_kw(est["kw_min"]), _kw(est["kw_max"]), inr(est["price"]))
	parts = ["{0} kW system".format(_kw(est["kw"])), "₹{0}".format(inr(est["price"]))]
	if est.get("subsidy"):
		parts.append("₹{0} subsidy, ₹{1} after subsidy".format(inr(est["subsidy"]), inr(est["net"])))
	line = " · ".join(parts)
	if est.get("battery"):
		line += " · battery system designed by our engineer"
	if est.get("monthly_saving"):
		line += " · saves about ₹{0} a month".format(inr(est["monthly_saving"]))
	return line


def _kw(kw):
	return ("%g" % flt(kw))


def inr(amount):
	"""₹ grouping the Indian way: 2,16,600."""
	n = int(round(flt(amount)))
	sign, n = ("-" if n < 0 else ""), abs(n)
	s = str(n)
	if len(s) <= 3:
		return sign + s
	head, tail = s[:-3], s[-3:]
	groups = []
	while len(head) > 2:
		groups.insert(0, head[-2:])
		head = head[:-2]
	if head:
		groups.insert(0, head)
	return sign + ",".join(groups + [tail])
