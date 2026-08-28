# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Service ticket SLAs, escalation, and generation performance.

A breached complaint SLA is a registration risk, not a customer-service metric: the
ministry's grievance and enforcement framework permits temporary deactivation of vendors
that fail to address consumer complaints. So escalation is designed to be impossible to
ignore, and every escalation is logged so the compliance report can prove the client acted.
"""

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_to_date,
	flt,
	get_datetime,
	getdate,
	now_datetime,
	time_diff_in_hours,
	today,
)

from a3_sola.api import calculations
from a3_sola.api.settings import get_float, get_int, get_value

#: Escalate to a wider audience at each threshold, never twice at the same one.
ESCALATION_LADDER = (
	(0.75, "assigned"),
	(1.0, "manager"),
	(1.5, "escalation_role"),
)


# --------------------------------------------------------------------- SLA clock
def compute_sla(ticket):
	"""Response and resolution due times, from the contract's service levels."""
	contract = frappe.get_cached_doc("Solar OM Contract", ticket.om_contract)
	reported = get_datetime(ticket.reported_on or now_datetime())

	if ticket.severity == "Critical":
		response = int(contract.critical_response_hours or 24)
		resolution = int(contract.critical_resolution_hours or 72)
	elif ticket.severity == "Major":
		response = int(contract.major_response_hours or 48)
		resolution = int(contract.major_resolution_hours or 120)
	else:
		response = int(contract.major_response_hours or 48)
		resolution = int(contract.minor_resolution_days or 15) * 24

	ticket.response_due_by = add_to_date(reported, hours=response)
	ticket.resolution_due_by = add_to_date(reported, hours=resolution)
	return ticket


def stamp_progress(ticket):
	"""First response, resolution, and whether each SLA was met."""
	if ticket.status != "Open" and not ticket.first_response_on:
		ticket.first_response_on = now_datetime()

	reported = get_datetime(ticket.reported_on) if ticket.reported_on else None

	if ticket.first_response_on and reported:
		ticket.hours_to_response = flt(
			time_diff_in_hours(get_datetime(ticket.first_response_on), reported), 2
		)
		ticket.response_sla_met = (
			1 if get_datetime(ticket.first_response_on) <= get_datetime(ticket.response_due_by) else 0
		)

	if ticket.status in ("Resolved", "Closed") and not ticket.resolved_on:
		ticket.resolved_on = now_datetime()
	if ticket.status not in ("Resolved", "Closed"):
		ticket.resolved_on = None

	if ticket.resolved_on and reported:
		ticket.hours_to_resolution = flt(
			time_diff_in_hours(get_datetime(ticket.resolved_on), reported), 2
		)
		ticket.resolution_sla_met = (
			1 if get_datetime(ticket.resolved_on) <= get_datetime(ticket.resolution_due_by) else 0
		)
	return ticket


def handle_reopen(ticket):
	"""A reopened ticket restarts the resolution clock and escalates past a threshold."""
	before = ticket.get_doc_before_save()
	if not before or before.status == ticket.status or ticket.status != "Reopened":
		return ticket

	ticket.reopen_count = int(ticket.reopen_count or 0) + 1
	ticket.resolved_on = None
	ticket.resolution_sla_met = 0
	ticket.escalation_level = 0
	compute_sla(ticket)

	threshold = get_int("ticket_reopen_escalation_threshold", 2) or 2
	if ticket.reopen_count >= threshold:
		_escalate(
			ticket,
			"escalation_role",
			_("Ticket {0} has been reopened {1} times. Something is not actually fixed.").format(
				ticket.name, ticket.reopen_count
			),
		)
	return ticket


# ------------------------------------------------------------------- escalation
def hourly_sla_scan():
	"""Hourly, per company. Registered through the module registry."""
	summary = {}
	for company in frappe.get_all("Company", pluck="name"):
		tickets = frappe.get_all(
			"Service Ticket",
			filters={
				"company": company,
				"docstatus": 1,
				"status": ["not in", ["Resolved", "Closed"]],
			},
			fields=["name", "severity", "reported_on", "resolution_due_by", "escalation_level"],
		)
		escalated = 0
		for row in tickets:
			if _scan_one(row):
				escalated += 1
		summary[company] = escalated
	frappe.logger("a3_sola").info({"event": "hourly_sla_scan", "summary": summary})
	return summary


def _scan_one(row):
	if not row.resolution_due_by:
		return False
	reported = get_datetime(row.reported_on)
	due = get_datetime(row.resolution_due_by)
	total = time_diff_in_hours(due, reported) or 1
	elapsed = time_diff_in_hours(now_datetime(), reported)
	ratio = elapsed / total

	level = int(row.escalation_level or 0)
	for index, (threshold, audience) in enumerate(ESCALATION_LADDER, start=1):
		if ratio >= threshold and level < index:
			ticket = frappe.get_doc("Service Ticket", row.name)
			breached = ratio >= 1.0
			_escalate(
				ticket,
				audience,
				_("Ticket {0} ({1}) is at {2}% of its resolution SLA.{3}").format(
					ticket.name, ticket.severity, int(ratio * 100),
					_(" The SLA is BREACHED.") if breached else "",
				),
				persist=True,
			)
			return True
	return False


def _escalate(ticket, audience, message, persist=False):
	"""Notify, log a timeline comment, and record the level. Never re-notify a threshold."""
	recipients = _audience(ticket, audience)
	for user in recipients:
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": user,
				"date": today(),
				"priority": "High" if ticket.severity == "Critical" else "Medium",
				"description": message,
				"reference_type": "Service Ticket",
				"reference_name": ticket.name,
			}
		).insert(ignore_permissions=True)

	ticket.add_comment("Comment", message)
	if persist:
		level = next(
			(i for i, (_t, a) in enumerate(ESCALATION_LADDER, start=1) if a == audience), 1
		)
		frappe.db.set_value("Service Ticket", ticket.name, "escalation_level", level, update_modified=False)
	return recipients


def _audience(ticket, audience):
	"""Who to wake up. An escalation that reaches nobody is not an escalation.

	Roles can legitimately have no holder yet - a fresh tenant, someone who left - so this
	falls through to progressively wider audiences and, failing everything, records the
	fact loudly rather than escalating into thin air.
	"""
	if audience == "assigned" and ticket.assigned_to:
		return [ticket.assigned_to]

	role = {
		"manager": "Solar O&M Manager",
		"escalation_role": get_value("outreach_escalation_role"),
	}.get(audience) or "Solar O&M Manager"

	for candidate in (role, "Solar O&M Manager", "Solar Operations Manager", "System Manager"):
		if not candidate or not frappe.db.exists("Role", candidate):
			continue
		users = frappe.get_all(
			"Has Role", filters={"role": candidate, "parenttype": "User"}, pluck="parent", limit=5
		)
		users = [u for u in users if u != "Administrator" and frappe.db.get_value("User", u, "enabled")]
		if users:
			return users

	frappe.log_error(
		title="a3_sola: escalation reached nobody",
		message=f"Ticket {ticket.name} breached its SLA but no user holds {role}, "
		"Solar O&M Manager, Solar Operations Manager or System Manager. "
		"Nobody was notified.",
	)
	return []


# --------------------------------------------------------------- bulk readings
#: What an inverter portal export actually looks like once the noise is stripped out.
READING_COLUMNS = ("reading_date", "inverter_lifetime_kwh", "import_reading", "export_reading")


@frappe.whitelist()
def import_readings(solar_installation, csv_text, reading_source="Inverter Portal"):
	"""Load a month of readings from an inverter portal export.

	Nobody keys these in. Every client exports a CSV from SolarEdge, Solinteg or Hoymiles,
	so the import takes a header row naming any of the reading columns, skips rows already
	recorded for that date, and reports what it did rather than failing the whole file for
	one bad line.
	"""
	import csv
	import io as _io

	installation = frappe.get_doc("Solar Installation", solar_installation)
	installation.check_permission("read")

	reader = csv.DictReader(_io.StringIO(csv_text or ""))
	if not reader.fieldnames:
		frappe.throw(_("The file has no header row."))

	headers = {(name or "").strip().lower().replace(" ", "_"): name for name in reader.fieldnames}
	if "reading_date" not in headers:
		frappe.throw(_("The file needs a reading_date column."))
	if not any(column in headers for column in READING_COLUMNS[1:]):
		frappe.throw(
			_("The file needs at least one of: {0}.").format(", ".join(READING_COLUMNS[1:]))
		)

	created, skipped, failed = [], [], []
	for index, row in enumerate(reader, start=2):
		date = (row.get(headers["reading_date"]) or "").strip()
		if not date:
			continue
		try:
			date = getdate(date)
		except Exception:
			failed.append({"line": index, "reason": _("Unreadable date {0}").format(date)})
			continue
		if frappe.db.exists(
			"Generation Reading",
			{"solar_installation": installation.name, "reading_date": date, "docstatus": ["<", 2]},
		):
			skipped.append({"line": index, "reading_date": str(date)})
			continue

		values = {
			"doctype": "Generation Reading",
			"company": installation.company,
			"solar_installation": installation.name,
			"reading_date": date,
			"reading_source": reading_source,
		}
		for column in READING_COLUMNS[1:]:
			if column in headers:
				raw = (row.get(headers[column]) or "").strip()
				if raw:
					values[column] = flt(raw)
		try:
			doc = frappe.get_doc(values)
			doc.flags.ignore_permissions = True
			doc.insert(ignore_permissions=True)
			doc.submit()
			created.append(doc.name)
		except Exception as exc:
			failed.append({"line": index, "reason": str(exc)})

	frappe.logger("a3_sola").info(
		{
			"event": "generation_readings_imported",
			"installation": installation.name,
			"created": len(created),
			"skipped": len(skipped),
			"failed": len(failed),
		}
	)
	return {"created": created, "skipped": skipped, "failed": failed}


@frappe.whitelist()
def capture_reading(om_visit, inverter_lifetime_kwh=None, import_reading=None, export_reading=None):
	"""Record the meter while the technician is still on the roof.

	A reading taken a week later against a remembered number is worse than no reading, so
	this is raised straight off the visit form and sourced as an O&M Visit.
	"""
	visit = frappe.get_doc("Solar OM Visit", om_visit)
	visit.check_permission("read")
	if not visit.solar_installation:
		frappe.throw(_("This visit has no installation on it."))

	existing = frappe.db.get_value(
		"Generation Reading",
		{
			"solar_installation": visit.solar_installation,
			"reading_date": visit.visit_date,
			"docstatus": ["<", 2],
		},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Generation Reading",
			"company": visit.company,
			"solar_installation": visit.solar_installation,
			"om_contract": visit.om_contract,
			"reading_date": visit.visit_date,
			"reading_source": "O&M Visit",
			"inverter_lifetime_kwh": flt(inverter_lifetime_kwh)
			or flt(visit.inverter_lifetime_generation),
			"import_reading": flt(import_reading) or flt(visit.import_reading),
			"export_reading": flt(export_reading) or flt(visit.export_reading),
			"recorded_by": frappe.session.user,
			"remarks": _("Captured on visit {0}.").format(visit.name),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


# ------------------------------------------------------------------ performance
def compute_reading(reading):
	"""Generation since the last reading, expected output, and the performance ratio."""
	installation = frappe.get_cached_doc("Solar Installation", reading.solar_installation)
	previous = frappe.db.get_value(
		"Generation Reading",
		{
			"solar_installation": reading.solar_installation,
			"docstatus": 1,
			"reading_date": ["<", reading.reading_date],
			"name": ["!=", reading.name or ""],
		},
		["reading_date", "export_reading", "inverter_lifetime_kwh"],
		as_dict=True,
		order_by="reading_date desc",
	)

	if previous:
		reading.days_since_last_reading = frappe.utils.date_diff(
			reading.reading_date, previous.reading_date
		)
		if flt(reading.inverter_lifetime_kwh) and flt(previous.inverter_lifetime_kwh):
			reading.units_generated_since_last = flt(
				flt(reading.inverter_lifetime_kwh) - flt(previous.inverter_lifetime_kwh), 2
			)
		else:
			reading.units_generated_since_last = flt(
				flt(reading.export_reading) - flt(previous.export_reading), 2
			)
	else:
		reading.days_since_last_reading = 0
		reading.units_generated_since_last = flt(reading.inverter_lifetime_kwh) or 0.0

	days = reading.days_since_last_reading or 1
	# Prorate the design expectation by the elapsed days.
	annual = calculations.estimate_generation(installation.capacity_kw)["annual_generation_kwh"]
	reading.expected_generation_kwh = flt(annual * days / 365.0, 2)
	reading.performance_ratio_percent = (
		flt(flt(reading.units_generated_since_last) * 100.0 / flt(reading.expected_generation_kwh), 2)
		if flt(reading.expected_generation_kwh)
		else 0.0
	)
	reading.variance_percent = flt(reading.performance_ratio_percent - 100.0, 2)
	return reading


def evaluate_performance(reading):
	"""Append to the contract log, and act on sustained underperformance.

	Two separate things happen here, and they are not the same:

	* A run of readings below the operational threshold raises a Major ticket - the system
	  is not producing what it was designed to.
	* The contractual floor (75% by default) is a clause in a signed agreement. Falling
	  below it is a contractual exposure and raises a Critical ticket.
	"""
	contract = _contract_for(reading)
	if not contract:
		return None

	doc = frappe.get_doc("Solar OM Contract", contract)
	period = getdate(reading.reading_date).strftime("%Y-%m")
	existing = next((r for r in doc.performance_log if r.period == period), None)
	row = existing or doc.append("performance_log", {"period": period})
	row.expected_generation_kwh = reading.expected_generation_kwh
	row.actual_generation_kwh = reading.units_generated_since_last
	row.performance_ratio_percent = reading.performance_ratio_percent
	row.variance_percent = reading.variance_percent

	threshold = get_float("underperformance_threshold_percent", 80.0)
	required = get_int("underperformance_consecutive_readings", 3) or 3
	floor = flt(doc.contractual_performance_ratio_percent) or 75.0

	if flt(reading.performance_ratio_percent) < threshold:
		doc.consecutive_underperforming_readings = int(doc.consecutive_underperforming_readings or 0) + 1
	else:
		doc.consecutive_underperforming_readings = 0

	doc.current_performance_ratio_percent = reading.performance_ratio_percent
	if flt(reading.performance_ratio_percent) < floor:
		doc.performance_obligation_status = "Breached"
	elif flt(reading.performance_ratio_percent) < floor + 5:
		doc.performance_obligation_status = "At Risk"
	else:
		doc.performance_obligation_status = "Meeting"

	ticket = None
	if doc.consecutive_underperforming_readings >= required:
		ticket = _raise_performance_ticket(doc, reading, "Major", threshold)
		row.alert_raised = 1
	if doc.performance_obligation_status == "Breached":
		ticket = _raise_performance_ticket(doc, reading, "Critical", floor, contractual=True) or ticket
		row.alert_raised = 1

	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return ticket


@frappe.whitelist()
def performance_series(om_contract, months=12):
	"""Expected against actual by month, for the contract's own chart."""
	contract = frappe.get_doc("Solar OM Contract", om_contract)
	contract.check_permission("read")

	rows = frappe.get_all(
		"Generation Reading",
		filters={"solar_installation": contract.solar_installation, "docstatus": 1},
		fields=[
			"reading_date", "expected_generation_kwh", "units_generated_since_last",
			"performance_ratio_percent",
		],
		order_by="reading_date asc",
		limit_page_length=int(months),
	)
	return {
		"labels": [getdate(row.reading_date).strftime("%b %Y") for row in rows],
		"expected": [flt(row.expected_generation_kwh, 1) for row in rows],
		"actual": [flt(row.units_generated_since_last, 1) for row in rows],
		"ratio": [flt(row.performance_ratio_percent, 1) for row in rows],
	}


def _contract_for(reading):
	if reading.om_contract:
		return reading.om_contract
	return frappe.db.get_value(
		"Solar OM Contract",
		{"solar_installation": reading.solar_installation, "docstatus": 1},
		"name",
	)


def _raise_performance_ticket(contract, reading, severity, threshold, contractual=False):
	"""One open performance ticket per contract - do not spam the queue."""
	existing = frappe.db.exists(
		"Service Ticket",
		{
			"om_contract": contract.name,
			"category": "Low Generation",
			"severity": severity,
			"status": ["not in", ["Resolved", "Closed"]],
			"docstatus": ["<", 2],
		},
	)
	if existing:
		return existing

	if contractual:
		description = _(
			"Performance ratio is {0}%, below the contractual floor of {1}%. The consumer-vendor "
			"agreement requires this to be maintained for the warranty period, so this is a "
			"contractual exposure, not a service observation."
		).format(flt(reading.performance_ratio_percent), flt(threshold))
	else:
		description = _(
			"Performance ratio is {0}% against an operational threshold of {1}%, across {2} "
			"consecutive readings. Latest reading {3}."
		).format(
			flt(reading.performance_ratio_percent), flt(threshold),
			contract.consecutive_underperforming_readings, reading.name,
		)

	ticket = frappe.get_doc(
		{
			"doctype": "Service Ticket",
			"company": contract.company,
			"om_contract": contract.name,
			"project": contract.project,
			"solar_installation": contract.solar_installation,
			"customer": contract.customer,
			"reported_on": now_datetime(),
			"reported_via": "Field Observation",
			"category": "Low Generation",
			"severity": severity,
			"is_scheme_related": 1 if contractual else 0,
			"description": description,
		}
	)
	ticket.flags.ignore_permissions = True
	ticket.insert(ignore_permissions=True)
	ticket.submit()
	return ticket.name
