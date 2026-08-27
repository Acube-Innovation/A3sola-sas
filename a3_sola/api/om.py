# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Project creation from commissioning, and the five-year obligation.

The vendor's agreement carries a five-year comprehensive O&M obligation from the date of
DISCOM commissioning, and requires the performance ratio to be MAINTAINED at the
contractual floor for the whole period. The ministry can temporarily deactivate a vendor
that fails to resolve complaints or rectify defects.

So this is a liability layer, not a service module: every commissioned job creates a
five-year cost commitment that is accrued at commissioning, not discovered over five years.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, add_years, flt, getdate, today

from a3_sola.api import accounting, billing, costing
from a3_sola.api.settings import get_float, get_int, get_settings, get_value

#: Coverage the client actually offers. The vendor agreement makes O&M comprehensive; the
#: proposal excludes panel washing and puts water and cleaning on the customer. Both are
#: true of the same job, so both are represented.
DEFAULT_COVERAGE = [
	("Preventive inspection visits", "Included", 0, "Three visits a year for five years."),
	("Inverter and system health check", "Included", 0, ""),
	("Earthing and surge protection check", "Included", 0, ""),
	("Structure torque check", "Included", 0, ""),
	("Cabling inspection", "Included", 0, ""),
	("Workmanship rectification", "Included", 0, ""),
	("Warranty liaison with manufacturers", "Included", 0, ""),
	("Remote monitoring", "Included", 0, "Internet connectivity provided by the customer."),
	("Consumer training on cleaning and maintenance", "Included", 0, ""),
	("Module washing", "Chargeable", 0,
	 "Not included in the contract. The consumer provides water and arranges periodic cleaning; "
	 "we advise on best practice and can quote for it."),
	("Damage from customer modification", "Excluded", 0, ""),
	("Force majeure and theft", "Excluded", 0, ""),
	("Grid faults", "Excluded", 0, ""),
	("Civil work beyond the original scope", "Excluded", 0, ""),
	("Net meter faults owned by the DISCOM", "Excluded", 0, ""),
]

VISIT_CHECKLIST = [
	("Module surface condition and soiling", "Module"),
	("Module mounting clamps and torque", "Structure"),
	("Structure corrosion and fasteners", "Structure"),
	("DC cable dressing and UV condition", "Cabling"),
	("AC cable and conduit condition", "Cabling"),
	("DCDB / ACDB condition and SPD status", "Cabling"),
	("Earth pit resistance and continuity", "Earthing"),
	("Lightning arrester and earth kit", "Earthing"),
	("Inverter error log and firmware", "Inverter"),
	("Inverter protection settings unchanged", "Inverter"),
	("Inverter ventilation and mounting", "Inverter"),
	("Net meter and solar meter readings", "Meter"),
	("Isolators and labelling legible", "Safety"),
	("Roof access and housekeeping", "Housekeeping"),
]


# ---------------------------------------------------------- project from commissioning
def create_project_from_commissioning(commissioning_report):
	"""Turn a submitted Commissioning Report into a Project. Strictly idempotent."""
	report = (
		frappe.get_doc("Commissioning Report", commissioning_report)
		if isinstance(commissioning_report, str)
		else commissioning_report
	)
	if not get_value("auto_create_project"):
		return None

	installation = frappe.get_doc("Solar Installation", report.solar_installation)
	if installation.project and frappe.db.exists("Project", installation.project):
		project = frappe.get_doc("Project", installation.project)
		_populate_project(project, installation, report)
		project.flags.ignore_permissions = True
		project.save(ignore_permissions=True)
		return project.name

	project = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": _project_name(installation),
			"company": installation.company,
			"customer": installation.customer,
			"status": "Open",
			"project_type": get_value("project_type_solar"),
			"expected_start_date": installation.order_date,
			"expected_end_date": report.commissioning_date,
			"actual_start_date": installation.order_date,
		}
	)
	_populate_project(project, installation, report)
	project.flags.ignore_permissions = True
	project.insert(ignore_permissions=True)

	frappe.db.set_value(
		"Solar Installation", installation.name, "project", project.name, update_modified=False
	)

	_create_billing_plan(project, installation)

	from a3_sola.api import recovery

	recovery.backfill_for_project(project.name, installation.name)
	if get_value("auto_create_om_contract"):
		try:
			create_om_contract(project.name)
		except NotImplementedError:
			frappe.log_error("create_om_contract is not implemented", "a3_sola")
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: O&M contract for {project.name}")

	try:
		costing.recalculate_project_costs(project.name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: initial costing for {project.name}")

	return project.name


def _project_name(installation):
	"""Readable and unique. ERPNext enforces uniqueness on Project.project_name, and a
	consumer can hold more than one service connection - so the consumer number carries
	the identity, with a counter only for the genuine repeat (a capacity enhancement)."""
	base = f"{installation.consumer_name} - {flt(installation.capacity_kw):g} kWp"
	if installation.consumer_number:
		base = f"{base} ({installation.consumer_number})"
	name, suffix = base, 1
	while frappe.db.exists("Project", {"project_name": name}):
		suffix += 1
		name = f"{base} #{suffix}"
	return name


def _populate_project(project, installation, report):
	project.solar_installation = installation.name
	project.solar_consumer = installation.solar_consumer
	project.capacity_kw = installation.capacity_kw
	project.solar_package = installation.solar_package
	project.commissioning_date = report.commissioning_date
	project.warranty_start_date = installation.warranty_start_date
	project.warranty_end_date = installation.warranty_end_date
	project.subsidy_scheme = installation.subsidy_scheme
	project.discom = installation.discom
	project.discom_section = installation.discom_section
	project.gross_contract_value = installation.gross_contract_value
	project.expected_subsidy_amount = installation.expected_subsidy_amount
	project.net_payable_by_customer = installation.net_payable_by_customer


def _create_billing_plan(project, installation):
	if frappe.db.exists("Solar Billing Plan", {"project": project.name, "docstatus": ["<", 2]}):
		return None
	consumer_category = frappe.db.get_value(
		"Solar Consumer", installation.solar_consumer, "consumer_category"
	)
	plan = frappe.get_doc(
		{
			"doctype": "Solar Billing Plan",
			"company": project.company,
			"project": project.name,
			"solar_installation": installation.name,
			"customer": installation.customer,
			"sales_order": installation.sales_order,
			"consumer_category": consumer_category,
			"net_meter_mode": installation.net_meter_mode,
			"is_financed": installation.is_financed,
			"gross_contract_value": installation.gross_contract_value,
			"expected_subsidy_amount": installation.expected_subsidy_amount,
		}
	)
	plan.flags.ignore_permissions = True
	plan.insert(ignore_permissions=True)
	plan.submit()
	return plan.name


# ------------------------------------------------------------------ O&M contract
@frappe.whitelist()
def create_om_contract(project):
	"""Create the five-year obligation record with its visit calendar. Idempotent."""
	doc = frappe.get_doc("Project", project) if isinstance(project, str) else project
	existing = frappe.db.get_value(
		"Solar OM Contract", {"project": doc.name, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		return existing
	if not doc.solar_installation:
		frappe.throw(_("Project {0} has no linked installation.").format(doc.name))

	installation = frappe.get_doc("Solar Installation", doc.solar_installation)
	contract = frappe.get_doc(
		{
			"doctype": "Solar OM Contract",
			"company": doc.company,
			"project": doc.name,
			"solar_installation": installation.name,
			"solar_consumer": installation.solar_consumer,
			"customer": installation.customer,
			"capacity_kw": installation.capacity_kw,
			"solar_package": installation.solar_package,
			"installation_address": installation.installation_address,
			"contract_type": "Comprehensive (Scheme Mandated)"
			if installation.subsidy_scheme
			else "Warranty Only",
			"start_date": installation.warranty_start_date or doc.commissioning_date or today(),
			"end_date": installation.warranty_end_date
			or add_years(getdate(doc.commissioning_date or today()), 5),
			"performance_ratio_at_commissioning": installation.performance_ratio_at_commissioning,
			"coverage": [
				{
					"coverage_item": item,
					"coverage_type": kind,
					"chargeable_rate": rate,
					"description": note,
				}
				for item, kind, rate, note in DEFAULT_COVERAGE
			],
		}
	)
	contract.flags.ignore_permissions = True
	contract.insert(ignore_permissions=True)
	contract.submit()

	accrue_provision(contract)
	return contract.name


def build_visit_plan(contract):
	"""Even spacing across the term, biased away from the monsoon.

	Kerala's soiling pattern is not the national one, so the monsoon months are configurable
	- a hardcoded assumption is wrong for the first client outside the state.
	"""
	if contract.visit_plan:
		return contract

	per_year = int(contract.preventive_visits_per_year or 3)
	if per_year <= 0:
		return contract
	start = getdate(contract.start_date)
	end = getdate(contract.end_date)
	years = max(int(contract.duration_years or 5), 1)
	interval = max(12 // per_year, 1)

	monsoon_start = get_int("monsoon_start_month", 6) or 6
	monsoon_end = get_int("monsoon_end_month", 9) or 9

	washing_excluded = any(
		row.coverage_item == "Module washing" and row.coverage_type != "Included"
		for row in contract.coverage
	)

	number = 0
	for year in range(years):
		for slot in range(per_year):
			scheduled = add_months(start, year * 12 + slot * interval)
			if scheduled > end:
				break
			scheduled = _avoid_monsoon(scheduled, monsoon_start, monsoon_end)
			number += 1
			# A visit just before and just after the monsoon is where soiling matters.
			month = getdate(scheduled).month
			is_cleaning_slot = month in (monsoon_start - 1, monsoon_end + 1)
			contract.append(
				"visit_plan",
				{
					"visit_number": number,
					"visit_type": "Annual Health Check" if slot == 0 else "Preventive",
					"scheduled_date": scheduled,
					"scheduled_month": getdate(scheduled).strftime("%Y-%m"),
					"status": "Scheduled",
					"is_chargeable": 1 if (is_cleaning_slot and washing_excluded) else 0,
				},
			)
	return contract


def _avoid_monsoon(date, monsoon_start, monsoon_end):
	"""Push a visit that lands mid-monsoon to just after it."""
	month = getdate(date).month
	if monsoon_start <= month <= monsoon_end:
		return add_months(date, monsoon_end - month + 1)
	return date


def compute_warranty_terms(contract):
	"""Read every term from Component Make. Never a constant.

	The client's proposals state different terms per make - Rayzon at 15/30, Vikram and
	Renewsys at 12/30, Solinteg at 10, SolarEdge at 8, Hoymiles at 12. A hardcoded 25 here
	would silently misstate every warranty claim.
	"""
	installation = frappe.get_cached_doc("Solar Installation", contract.solar_installation)
	contract.module_make = installation.module_make
	contract.inverter_make = installation.inverter_make

	parts = []
	if installation.module_make:
		make = frappe.get_cached_doc("Component Make", installation.module_make)
		contract.module_product_warranty_years = make.product_warranty_years
		contract.module_performance_warranty_years = make.performance_warranty_years
		contract.module_performance_floor_10yr = make.performance_floor_10yr_percent
		contract.module_performance_floor_25yr = make.performance_floor_25yr_percent
		parts.append(
			_("Modules ({0}): {1} years product, {2} years performance").format(
				make.make_name, make.product_warranty_years, make.performance_warranty_years
			)
		)
	if installation.inverter_make:
		make = frappe.get_cached_doc("Component Make", installation.inverter_make)
		contract.inverter_warranty_years = make.product_warranty_years
		parts.append(_("Inverter ({0}): {1} years").format(make.make_name, make.product_warranty_years))

	if installation.solar_package:
		contract.workmanship_warranty_years = (
			frappe.db.get_value("Solar Package", installation.solar_package, "warranty_years") or 5
		)
	parts.append(_("System workmanship: {0} years from commissioning").format(
		contract.workmanship_warranty_years or 5
	))
	contract.warranty_summary = ". ".join(parts)
	return contract


def warranty_years_for(make, basis="Product"):
	"""The applicable warranty term for a component make."""
	if not make:
		return 0
	row = frappe.db.get_value(
		"Component Make", make, ["product_warranty_years", "performance_warranty_years"], as_dict=True
	)
	if not row:
		return 0
	return int(
		(row.performance_warranty_years if basis == "Performance" else row.product_warranty_years) or 0
	)


# --------------------------------------------------------------------- provision
def compute_provision(contract):
	"""By the configured method - percent of contract, per kW, or fixed."""
	method = get_value("om_provision_method") or "Percent of Contract Value"
	if method == "Fixed per kW":
		return flt(get_float("om_provision_per_kw", 0.0) * flt(contract.capacity_kw), 2)
	if method == "Fixed per Contract":
		return flt(get_float("om_provision_per_kw", 0.0), 2)

	value = flt(
		frappe.db.get_value("Project", contract.project, "gross_contract_value")
	) or flt(contract.contract_value)
	return flt(value * get_float("om_provision_percent", 2.0) / 100.0, 2)


def accrue_provision(contract):
	"""Accrue the five-year commitment at commissioning."""
	if not get_value("enable_om_provision"):
		return None
	amount = compute_provision(contract)
	if not amount:
		return None

	frappe.db.set_value("Solar OM Contract", contract.name, "om_provision_allocated", amount, update_modified=False)
	frappe.db.set_value("Project", contract.project, "om_provision_amount", amount, update_modified=False)
	return accounting.post_om_provision(contract, amount)


def release_om_provision(project, amount, reference):
	"""Release the provision as a visit consumes it, and roll the balance."""
	entry = accounting.release_om_provision(project, amount, reference)

	contract = frappe.db.get_value("Solar OM Contract", {"project": project, "docstatus": 1}, "name")
	if contract:
		doc = frappe.get_doc("Solar OM Contract", contract)
		refresh_contract_financials(doc)
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
	return entry


def refresh_contract_financials(contract):
	"""Cost incurred, provision balance and the average cost per visit."""
	visits = frappe.get_all(
		"Solar OM Visit",
		filters={"om_contract": contract.name, "docstatus": 1},
		fields=["total_visit_cost"],
	)
	incurred = sum(flt(v.total_visit_cost) for v in visits)
	contract.om_cost_incurred = flt(incurred, 2)
	contract.om_provision_balance = flt(flt(contract.om_provision_allocated) - incurred, 2)
	contract.om_cost_per_visit_average = flt(incurred / len(visits), 2) if visits else 0.0

	frappe.db.set_value(
		"Project", contract.project, "om_provision_released", flt(incurred, 2), update_modified=False
	)
	return contract


def refresh_contract_compliance(contract):
	"""Visit compliance, next visit and open ticket count."""
	completed = len([r for r in contract.visit_plan if r.status == "Completed"])
	missed = len([r for r in contract.visit_plan if r.status == "Missed"])
	due = [r for r in contract.visit_plan if r.status in ("Scheduled", "Due")]
	elapsed = [r for r in contract.visit_plan if getdate(r.scheduled_date) <= getdate(today())]

	contract.visits_completed = completed
	contract.visits_missed = missed
	contract.visit_compliance_percent = (
		flt(completed * 100.0 / len(elapsed), 2) if elapsed else 100.0
	)
	contract.next_visit_date = min((getdate(r.scheduled_date) for r in due), default=None)
	contract.open_tickets = frappe.db.count(
		"Service Ticket",
		{
			"om_contract": contract.name,
			"status": ["not in", ["Resolved", "Closed"]],
			"docstatus": ["<", 2],
		},
	)

	window = get_int("contract_expiry_window_days", 90) or 90
	contract.days_to_expiry = frappe.utils.date_diff(contract.end_date, today())
	if contract.docstatus == 1:
		if contract.status in ("Renewed", "Terminated"):
			pass
		elif contract.days_to_expiry < 0:
			contract.status = "Expired"
		elif contract.days_to_expiry <= window:
			contract.status = "Expiring Soon"
		else:
			contract.status = "Active"
	return contract


# ------------------------------------------------------------------- schedulers
def mark_due_and_missed_visits():
	"""Daily: mark visits due, and overdue ones missed."""
	grace = 14
	summary = {}
	for company in frappe.get_all("Company", pluck="name"):
		contracts = frappe.get_all(
			"Solar OM Contract",
			filters={"company": company, "docstatus": 1, "status": ["not in", ["Terminated", "Expired"]]},
			pluck="name",
		)
		changed = 0
		for name in contracts:
			contract = frappe.get_doc("Solar OM Contract", name)
			dirty = False
			for row in contract.visit_plan:
				if row.status != "Scheduled":
					continue
				scheduled = getdate(row.scheduled_date)
				if scheduled <= getdate(today()):
					row.status = "Due"
					dirty = True
				if scheduled < getdate(add_days(today(), -grace)):
					row.status = "Missed"
					dirty = True
			if dirty:
				refresh_contract_compliance(contract)
				contract.flags.ignore_validate_update_after_submit = True
				contract.save(ignore_permissions=True)
				changed += 1
		summary[company] = changed
	return summary


def detect_renewals():
	"""Daily: contracts approaching expiry become renewal Opportunities in Solar CRM."""
	window = get_int("contract_expiry_window_days", 90) or 90
	created = {}
	for company in frappe.get_all("Company", pluck="name"):
		contracts = frappe.get_all(
			"Solar OM Contract",
			filters={
				"company": company,
				"docstatus": 1,
				"status": ["not in", ["Renewed", "Terminated"]],
				"end_date": ["<=", add_days(today(), window)],
			},
			fields=["name", "solar_consumer", "customer", "capacity_kw", "visit_compliance_percent",
			        "open_tickets", "end_date"],
		)
		count = 0
		for row in contracts:
			if frappe.db.exists("Opportunity", {"om_contract": row.name}):
				continue
			if _renewal_opportunity(company, row):
				count += 1
		created[company] = count
	return created


@frappe.whitelist()
def renew_contract(contract, years=None, contract_value=None):
	"""Raise the successor contract when the five years are up.

	The obligation that started at commissioning was scheme-mandated and free. What follows
	is a paid AMC, so the type changes - but the coverage and the service levels the
	customer is used to carry across rather than being retyped, and the predecessor is
	marked Renewed with a link in both directions so the service history stays continuous.
	"""
	previous = frappe.get_doc("Solar OM Contract", contract) if isinstance(contract, str) else contract
	previous.check_permission("write")

	if previous.docstatus != 1:
		frappe.throw(_("Only a submitted contract can be renewed."))
	if previous.renewed_to and frappe.db.exists("Solar OM Contract", previous.renewed_to):
		return previous.renewed_to

	years = int(years or previous.duration_years or 1)
	start = add_days(getdate(previous.end_date), 1)

	successor = frappe.get_doc(
		{
			"doctype": "Solar OM Contract",
			"company": previous.company,
			"project": previous.project,
			"solar_installation": previous.solar_installation,
			"solar_consumer": previous.solar_consumer,
			"customer": previous.customer,
			"capacity_kw": previous.capacity_kw,
			"solar_package": previous.solar_package,
			"installation_address": previous.installation_address,
			"site_contact_person": previous.site_contact_person,
			"site_contact_number": previous.site_contact_number,
			"contract_type": "AMC (Paid Renewal)",
			"start_date": start,
			"end_date": add_years(start, years),
			"contract_value": flt(contract_value),
			"renewed_from": previous.name,
			# The service levels the customer is already used to.
			"preventive_visits_per_year": previous.preventive_visits_per_year,
			"critical_response_hours": previous.critical_response_hours,
			"critical_resolution_hours": previous.critical_resolution_hours,
			"major_response_hours": previous.major_response_hours,
			"major_resolution_hours": previous.major_resolution_hours,
			"minor_resolution_days": previous.minor_resolution_days,
			"contractual_performance_ratio_percent": previous.contractual_performance_ratio_percent,
			"performance_ratio_at_commissioning": previous.performance_ratio_at_commissioning,
			"coverage": [
				{
					"coverage_item": row.coverage_item,
					"coverage_type": row.coverage_type,
					"chargeable_rate": row.chargeable_rate,
					"description": row.description,
				}
				for row in previous.coverage
			],
		}
	)
	successor.flags.ignore_permissions = True
	successor.insert(ignore_permissions=True)
	successor.submit()

	frappe.db.set_value(
		"Solar OM Contract",
		previous.name,
		{"status": "Renewed", "renewed_to": successor.name},
		update_modified=False,
	)
	previous.add_comment(
		"Comment",
		_("Renewed as {0}, running to {1}.").format(successor.name, successor.end_date),
	)
	return successor.name


def _renewal_party(contract):
	"""Who the renewal is actually addressed to.

	The contract normally carries the customer. Where it does not - an installation that
	never went through a sales order - the consumer record still knows the party, and a
	renewal against nobody is worse than no renewal at all.
	"""
	if contract.customer:
		return "Customer", contract.customer
	if not contract.solar_consumer:
		return None, None
	row = frappe.db.get_value(
		"Solar Consumer", contract.solar_consumer, ["customer", "lead"], as_dict=True
	)
	if row and row.customer:
		return "Customer", row.customer
	if row and row.lead:
		return "Lead", row.lead
	return None, None


def _renewal_opportunity(company, contract):
	party_type, party = _renewal_party(contract)
	if not party:
		frappe.logger("a3_sola").info(
			{"event": "renewal_skipped_no_party", "contract": contract.name}
		)
		return None

	description = _(
		"O&M contract {0} expires on {1}. Visit compliance {2}%, {3} open ticket(s) over the term."
	).format(contract.name, contract.end_date, flt(contract.visit_compliance_percent), contract.open_tickets)
	doc = frappe.get_doc(
		{
			"doctype": "Opportunity",
			"company": company,
			"opportunity_from": party_type,
			"party_name": party,
			"opportunity_type": "AMC Renewal",
			"solar_consumer": contract.solar_consumer,
			"om_contract": contract.name,
			"capacity_kw": contract.capacity_kw,
			"contact_date": today(),
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	doc.add_comment("Comment", description)
	return doc.name
