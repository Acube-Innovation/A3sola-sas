# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""DISCOM application, registration and net-meter fees, and the registration refund.

THE SINGLE SOURCE OF TRUTH FOR EVERY RUPEE THE CUSTOMER PAYS A GOVERNMENT BODY.
Nothing in this app may print a statutory fee that did not come from here.

Why this is a computed master and not typed text: the client's own proposal templates
disagree with each other. Their 3 kW template states Rs 3,540 charged with Rs 2,400
refundable, which is exactly Rs 1,000/kW + 18% GST with 80% of the base refunded.
Their 5 kW and 8 kW templates state Rs 8,288, which is not derivable from any rule, and
their 10 kW template states Rs 11,800 charged (correct) with Rs 4,000 refundable (should
be Rs 8,000). Computing the figures makes that class of error impossible to repeat.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from a3_sola.api.lookup import resolve
from a3_sola.api.settings import get_value, precision


def _round(value):
	return flt(value, precision())


def resolve_schedule(discom, on_date=None, company=None):
	"""Return the active Statutory Fee Schedule for a DISCOM on a date.

	Raises rather than returning zeros. A silently zero fee reaches a customer proposal.
	"""
	on_date = getdate(on_date or today())
	discom = resolve("DISCOM", discom) or discom
	filters = {
		"discom": discom,
		"is_active": 1,
		"effective_from": ["<=", on_date],
	}
	if company:
		filters["company"] = company

	rows = frappe.get_all(
		"Statutory Fee Schedule",
		filters=filters,
		fields=["name", "effective_to", "effective_from"],
		order_by="effective_from desc",
	)
	for row in rows:
		if not row.effective_to or getdate(row.effective_to) >= on_date:
			return row.name

	# The Settings default stands in for a missing DISCOM-specific schedule, but it is
	# still subject to its own effective dates. Using it outside them would quote a job
	# with fees that were not in force - the exact silent-wrong-number failure this
	# module exists to prevent.
	default = get_value("default_fee_schedule")
	if default and frappe.db.exists("Statutory Fee Schedule", default):
		row = frappe.db.get_value(
			"Statutory Fee Schedule", default, ["effective_from", "effective_to", "is_active"], as_dict=True
		)
		if (
			row
			and row.is_active
			and getdate(row.effective_from) <= on_date
			and (not row.effective_to or getdate(row.effective_to) >= on_date)
		):
			return default

	frappe.throw(
		_("No active Statutory Fee Schedule for DISCOM {0} on {1}. Statutory fees cannot be quoted without one.").format(
			frappe.bold(discom), on_date
		),
		title=_("Fee Schedule Missing"),
	)


@frappe.whitelist()
def get_statutory_fees(
	discom, connection_type, capacity_kw, net_meter_mode="Purchased by Customer", on_date=None, company=None
) -> dict:
	"""Resolve every statutory charge for one job.

	Returns application, registration and net-meter figures plus the refundable portion and
	a human-readable breakdown the proposal renders. No caller may override a figure.
	"""
	capacity_kw = flt(capacity_kw)
	schedule_name = resolve_schedule(discom, on_date, company)
	sched = frappe.get_cached_doc("Statutory Fee Schedule", schedule_name)

	# --- application fee -------------------------------------------------
	app_base = flt(sched.application_fee_base)
	app_gst_pct = flt(sched.application_fee_gst_percent) if sched.application_fee_gst_applicable else 0.0
	app_gst = app_base * app_gst_pct / 100.0
	app_gross = app_base + app_gst

	# --- registration fee ------------------------------------------------
	reg_base = flt(sched.registration_fee_per_kw) * capacity_kw
	if sched.registration_fee_min and reg_base < flt(sched.registration_fee_min):
		reg_base = flt(sched.registration_fee_min)
	if sched.registration_fee_max and reg_base > flt(sched.registration_fee_max):
		reg_base = flt(sched.registration_fee_max)
	reg_gst = reg_base * flt(sched.registration_fee_gst_percent) / 100.0
	reg_gross = reg_base + reg_gst

	refund_on = reg_gross if sched.refund_computed_on == "Gross Amount" else reg_base
	refundable = refund_on * flt(sched.registration_refund_percent) / 100.0

	# --- net meter -------------------------------------------------------
	charge = rental = 0.0
	lead_days = 0
	for row in sched.net_meter_charges:
		if row.connection_type == connection_type and row.supply_mode == net_meter_mode:
			charge = flt(row.charge_amount)
			rental = flt(row.monthly_rental)
			lead_days = int(row.allocation_lead_days or 0)
			break

	total = app_gross + reg_gross + charge

	breakdown = [
		{
			"item": _("KSEB Application Fee"),
			"base": _round(app_base),
			"gst": _round(app_gst),
			"amount": _round(app_gross),
			"note": "",
		},
		{
			"item": _("Solar Plant Registration Fee"),
			"base": _round(reg_base),
			"gst": _round(reg_gst),
			"amount": _round(reg_gross),
			"note": _("{0} refundable after commissioning").format(
				frappe.utils.fmt_money(refundable, currency="INR")
			),
		},
	]
	if net_meter_mode == "Availed from DISCOM on Rental":
		breakdown.append(
			{
				"item": _("Bi-directional (Net) Meter"),
				"base": 0.0,
				"gst": 0.0,
				"amount": 0.0,
				"note": _(
					"Availed from the DISCOM on monthly rental of {0}; allocation takes about {1} days"
				).format(frappe.utils.fmt_money(rental, currency="INR"), lead_days),
			}
		)
	else:
		breakdown.append(
			{
				"item": _("Bi-directional (Net) Meter"),
				"base": _round(charge),
				"gst": 0.0,
				"amount": _round(charge),
				"note": "",
			}
		)

	return {
		"schedule": schedule_name,
		"application_fee_base": _round(app_base),
		"application_fee_gst": _round(app_gst),
		"application_fee_gross": _round(app_gross),
		"registration_fee_base": _round(reg_base),
		"registration_fee_gst": _round(reg_gst),
		"registration_fee_gross": _round(reg_gross),
		"registration_refundable": _round(refundable),
		"net_meter_charge": _round(charge),
		"net_meter_monthly_rental": _round(rental),
		"net_meter_allocation_lead_days": lead_days,
		"statutory_total": _round(total),
		"breakdown": breakdown,
	}


@frappe.whitelist()
def get_refund_due(discom, connection_type, capacity_kw, net_meter_mode="Purchased by Customer", on_date=None, company=None) -> dict:
	"""The registration-fee refund recoverable after commissioning.

	Phases 2 and 3 consume this: Phase 2 to raise the refund request letter, Phase 3 to
	carry the receivable.
	"""
	fees = get_statutory_fees(discom, connection_type, capacity_kw, net_meter_mode, on_date, company)
	return {
		"refundable_amount": fees["registration_refundable"],
		"registration_fee_gross": fees["registration_fee_gross"],
		"registration_fee_base": fees["registration_fee_base"],
		"schedule": fees["schedule"],
	}
