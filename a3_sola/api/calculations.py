# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sizing, generation, telescopic billing, savings, subsidy and cashflow.

No rate, yield, area or subsidy figure is a constant in this module. Everything comes
from a master or from A3 Sola Settings, because every one of them is a number the client
must be able to change without a deployment.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api.lookup import resolve
from a3_sola.api.settings import get_float, get_int, precision


def _round(value, prec=None):
	return flt(value, prec if prec is not None else precision())


@frappe.whitelist()
def get_subsidy_amount(scheme: str, capacity_kw: float, consumer_category: str) -> dict:
	"""Resolve the central financial assistance for a capacity under a scheme.

	Returns {"subsidy_amount", "slab_used", "capped", "message"}. A scheme that does not
	cover the category, or that is outside its effective dates, returns zero with an
	explanatory message rather than raising - those are ordinary sales situations, not
	programming errors. Only a missing scheme raises.
	"""
	capacity_kw = flt(capacity_kw)
	result = {"subsidy_amount": 0.0, "slab_used": None, "capped": False, "message": ""}

	scheme_name = resolve("Subsidy Scheme", scheme)
	if not scheme_name:
		frappe.throw(_("Subsidy Scheme {0} does not exist.").format(scheme))

	doc = frappe.get_cached_doc("Subsidy Scheme", scheme_name)

	if not doc.is_active:
		result["message"] = _("Scheme {0} is not active.").format(scheme)
		return result

	if doc.consumer_category and doc.consumer_category != consumer_category:
		result["message"] = _("Scheme {0} covers {1} connections; this is {2}.").format(
			scheme, doc.consumer_category, consumer_category or _("unspecified")
		)
		return result

	today = frappe.utils.today()
	if doc.effective_from and str(doc.effective_from) > today:
		result["message"] = _("Scheme {0} takes effect on {1}.").format(scheme, doc.effective_from)
		return result
	if doc.effective_to and str(doc.effective_to) < today:
		result["message"] = _("Scheme {0} expired on {1}.").format(scheme, doc.effective_to)
		return result

	if doc.max_eligible_capacity_kw and capacity_kw > flt(doc.max_eligible_capacity_kw):
		# Capacity above the ceiling is still subsidised, but only up to the ceiling.
		capacity_kw = flt(doc.max_eligible_capacity_kw)
		result["capped"] = True
		result["message"] = _("Capacity capped at the scheme ceiling of {0} kW.").format(
			doc.max_eligible_capacity_kw
		)

	slab = None
	for row in doc.slabs:
		if flt(row.capacity_from_kw) <= capacity_kw <= flt(row.capacity_to_kw):
			slab = row
			break
	if not slab and doc.slabs:
		top = max(doc.slabs, key=lambda r: flt(r.capacity_to_kw))
		if capacity_kw > flt(top.capacity_to_kw):
			slab = top
			result["capped"] = True

	if not slab:
		result["message"] = result["message"] or _("No subsidy slab in {0} covers {1} kW.").format(
			scheme, capacity_kw
		)
		return result

	if slab.calculation_basis == "Per kW":
		amount = flt(slab.subsidy_amount) * capacity_kw
	else:
		amount = flt(slab.subsidy_amount)

	if slab.max_subsidy_cap and amount > flt(slab.max_subsidy_cap):
		amount = flt(slab.max_subsidy_cap)
		result["capped"] = True

	result["subsidy_amount"] = _round(amount)
	result["slab_used"] = f"{slab.capacity_from_kw}-{slab.capacity_to_kw} kW"
	if result["capped"] and not result["message"]:
		result["message"] = _("Subsidy capped at the slab maximum.")
	return result


@frappe.whitelist()
def calculate_bill(tariff: str, units: float) -> dict:
	"""Bill `units` against a telescopic tariff, slab by slab.

	Kerala's domestic tariff is telescopic: units falling in each slab are charged at that
	slab's rate and accumulate upward. Applying a flat average rate understates the saving
	from a solar system materially, which is exactly the mistake this function prevents.
	"""
	units = flt(units)
	tariff_name = resolve("Electricity Tariff", tariff)
	if not tariff_name:
		frappe.throw(_("Electricity Tariff {0} does not exist.").format(tariff))

	doc = frappe.get_cached_doc("Electricity Tariff", tariff_name)
	slabs = sorted(doc.slabs, key=lambda r: flt(r.units_from))

	energy_charge = 0.0
	fixed_charge = 0.0
	duty = 0.0
	breakdown = []
	remaining = units

	for row in slabs:
		if remaining <= 0:
			break
		lower = flt(row.units_from)
		upper = flt(row.units_to)
		if units <= lower:
			break
		width = max(upper - lower, 0)
		billed = min(remaining, width) if width else remaining
		amount = billed * flt(row.rate_per_unit)
		slab_duty = amount * flt(row.duty_percent) / 100.0

		energy_charge += amount
		fixed_charge += flt(row.fixed_charge)
		duty += slab_duty
		remaining -= billed
		breakdown.append(
			{
				"units_from": lower,
				"units_to": upper,
				"units_billed": _round(billed),
				"rate_per_unit": flt(row.rate_per_unit),
				"amount": _round(amount),
				"fixed_charge": flt(row.fixed_charge),
				"duty": _round(slab_duty),
			}
		)

	total = energy_charge + fixed_charge + duty
	return {
		"total_amount": _round(total),
		"energy_charge": _round(energy_charge),
		"fixed_charge": _round(fixed_charge),
		"duty": _round(duty),
		"effective_rate_per_unit": _round(total / units) if units else 0.0,
		"slab_breakdown": breakdown,
	}


@frappe.whitelist()
def calculate_savings(tariff: str, units_before: float, units_after: float) -> dict:
	"""Differential bill between pre- and post-solar consumption.

	Because the tariff is telescopic the units removed are the most expensive ones, so the
	saving per unit is higher than the average rate. effective_saving_per_unit reflects it.
	"""
	before = calculate_bill(tariff, units_before)
	after = calculate_bill(tariff, units_after)
	units_saved = flt(units_before) - flt(units_after)
	saving = flt(before["total_amount"]) - flt(after["total_amount"])
	return {
		"saving_amount": _round(saving),
		"units_saved": _round(units_saved),
		"effective_saving_per_unit": _round(saving / units_saved) if units_saved else 0.0,
		"bill_before": before,
		"bill_after": after,
	}


@frappe.whitelist()
def estimate_generation(capacity_kw: float, specific_yield: float = None, shading_percent: float = 0) -> dict:
	"""Annual and monthly generation for a capacity, derated for shading."""
	capacity_kw = flt(capacity_kw)
	specific_yield = flt(specific_yield) or get_float("default_specific_yield", 1500.0)
	derate = max(0.0, 1 - flt(shading_percent) / 100.0)
	annual = capacity_kw * specific_yield * derate
	return {
		"annual_generation_kwh": _round(annual),
		"monthly_generation_kwh": _round(annual / 12),
		"daily_generation_kwh": _round(annual / 365),
		"specific_yield": specific_yield,
		"shading_percent": flt(shading_percent),
		"derate_factor": _round(derate, 4),
	}


@frappe.whitelist()
def estimate_daily_generation_band(capacity_kw: float, discom_section: str = None) -> dict:
	"""The daily unit range the proposal prints.

	The client quotes a band - "20 - 25 units" for a 5 kW system - not a single figure, and
	a single figure invites a complaint on the first cloudy week. Sourced from the district
	yield band where the section defines one, otherwise from Settings.
	"""
	capacity_kw = flt(capacity_kw)
	low = get_float("default_daily_yield_low", 4.0)
	high = get_float("default_daily_yield_high", 5.0)
	basis = "A3 Sola Settings"

	section = resolve("DISCOM Section", discom_section)
	if section:
		override = flt(frappe.db.get_value("DISCOM Section", section, "specific_yield_override"))
		if override:
			daily = override / 365.0
			low, high = daily * 0.9, daily * 1.1
			basis = f"DISCOM Section {section}"

	return {
		"low_units_per_day": _round(capacity_kw * low),
		"high_units_per_day": _round(capacity_kw * high),
		"basis": basis,
	}


@frappe.whitelist()
def build_cashflow(gross_cost, subsidy, annual_generation, annual_savings, years=None) -> dict:
	"""Year-wise projection with generation degradation and tariff escalation.

	Returns {"rows": [...], "simple_payback_years", "lifetime_savings", "net_outflow"}.
	Payback is interpolated within the crossover year rather than rounded up, because a
	payback of 6.0 and a payback of 6.9 are different sales conversations.
	"""
	years = get_int("cashflow_years", 25) if years in (None, "", 0) else int(years)
	degradation = get_float("annual_degradation_percent", 0.7) / 100.0
	escalation = get_float("tariff_escalation_percent", 3.0) / 100.0

	net_outflow = flt(gross_cost) - flt(subsidy)
	cumulative = 0.0
	rows = []
	payback = None

	for year in range(1, years + 1):
		generation = flt(annual_generation) * ((1 - degradation) ** (year - 1))
		savings = flt(annual_savings) * ((1 - degradation) ** (year - 1)) * ((1 + escalation) ** (year - 1))
		previous_cumulative = cumulative
		cumulative += savings
		net_position = cumulative - net_outflow

		if payback is None and cumulative >= net_outflow and savings:
			shortfall = net_outflow - previous_cumulative
			payback = (year - 1) + (shortfall / savings)

		rows.append(
			{
				"year": year,
				"generation_kwh": _round(generation),
				"savings_amount": _round(savings),
				"cumulative_savings": _round(cumulative),
				"net_position": _round(net_position),
			}
		)

	return {
		"rows": rows,
		"simple_payback_years": _round(payback) if payback else 0.0,
		"lifetime_savings": _round(cumulative),
		"net_outflow": _round(net_outflow),
	}


def recommend_capacity(annual_consumption_units, roof_usable_kw, sanctioned_load_kw, specific_yield=None):
	"""Constrain sizing to the lower of consumption, roof and sanctioned load.

	Every constraint is reported, not just the winner, because the client needs to know
	whether roof area or sanctioned load is their structural limiter.
	"""
	specific_yield = flt(specific_yield) or get_float("default_specific_yield", 1500.0)
	consumption_kw = flt(annual_consumption_units) / specific_yield if specific_yield else 0.0

	candidates = []
	if consumption_kw:
		candidates.append((consumption_kw, "Annual Consumption"))
	if flt(roof_usable_kw):
		candidates.append((flt(roof_usable_kw), "Usable Roof Area"))
	if flt(sanctioned_load_kw):
		candidates.append((flt(sanctioned_load_kw), "Sanctioned Load"))

	if not candidates:
		return {
			"recommended_kw": 0.0,
			"binding_constraint": None,
			"consumption_kw": 0.0,
			"roof_kw": flt(roof_usable_kw),
			"sanctioned_kw": flt(sanctioned_load_kw),
		}

	recommended, constraint = min(candidates, key=lambda c: c[0])
	return {
		"recommended_kw": _round(recommended, 3),
		"binding_constraint": constraint,
		"consumption_kw": _round(consumption_kw, 3),
		"roof_kw": _round(flt(roof_usable_kw), 3),
		"sanctioned_kw": _round(flt(sanctioned_load_kw), 3),
	}
