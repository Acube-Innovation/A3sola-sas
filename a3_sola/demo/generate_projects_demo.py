# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Solar Projects demo data.

Extends the single demo generator rather than adding a second one. Phase 2 leaves behind
commissioned installations, and every one of those already carries a Project, a billing
plan and a five-year O&M contract - so this does not create projects. It gives them a
history: costs booked, milestones invoiced and part-collected, visits done and one missed,
tickets raised with one breached and one reopened, a warranty claim replaced and one
rejected, and generation readings that walk a system down through both thresholds.

Nothing here posts to a ledger. The accounting gates stay shut in demo data exactly as they
ship, because a demo that quietly posts is a demo that teaches the wrong habit.
"""

import frappe
from frappe.utils import add_days, add_months, flt, getdate, now_datetime, today

from a3_sola.api import calculations, costing, om, sla

MODULE_FAILURES = (
	("Module", "Cell cracking visible under EL imaging; string output down 38%."),
	("Inverter", "Inverter reporting ISO fault and shutting down at midday."),
)

TICKETS = (
	("Low Generation", "Critical", "Output halved since the last billing cycle.", "Component Failure"),
	("Inverter Fault", "Critical", "Inverter offline, display blank, no output since Tuesday.", "Component Failure"),
	("Other", "Minor", "Monitoring portal has not updated since the router was changed.", "No Fault Found"),
	("Module Damage", "Major", "Coconut frond has cracked the corner of one module.", "External Damage"),
	("Structure", "Major", "Seepage around a roof penetration after the first heavy rain.", "Workmanship"),
)


def _log(message):
	print(f"  {message}")


#: A small named crew, because one technician cannot be on five roofs at once - the work
#: order guards against exactly that, and demo data must not need the guard switched off.
CREW = (
	("Ajith Kumar", "P", "Male", "1992-04-11"),
	("Sanoop", "Varghese", "Male", "1994-08-23"),
	("Rejith", "Nair", "Male", "1990-02-17"),
	("Fousiya", "Rahman", "Female", "1995-11-05"),
	("Vishnu", "Prasad", "Male", "1993-06-30"),
	("Anish", "Thomas", "Male", "1991-01-19"),
	("Deepthi", "Menon", "Female", "1996-09-12"),
)


def _technician(company, index=0):
	first, last, gender, born = CREW[index % len(CREW)]
	existing = frappe.db.get_value(
		"Employee", {"company": company, "employee_name": f"{first} {last}"}, "name"
	)
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": first,
			"last_name": last,
			"company": company,
			"gender": gender,
			"date_of_birth": born,
			"date_of_joining": "2021-06-01",
			"status": "Active",
			"ctc": 480000 + (index * 40000),
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	return doc.insert(ignore_permissions=True).name


#: Jobs the client has already delivered. Operations demonstrates the chain with seven live
#: installations; Projects needs a completed book behind those, because costing, billing,
#: O&M and every report here only exist once a job is commissioned.
COMPLETED_JOBS = [
	("Chandran Nair", 3.0, "Purchased by Customer", 215000),
	("Sreelatha Devi", 5.0, "Purchased by Customer", 320000),
	("Varghese Kurian", 5.0, "Availed from DISCOM on Rental", 318000),
	("Naseema Beevi", 3.0, "Purchased by Customer", 212000),
	("Thomas Zachariah", 8.0, "Purchased by Customer", 496000),
	("Radhika Menon", 5.0, "Purchased by Customer", 322000),
]

#: Jobs for the second tenant, so isolation is visible in every report rather than
#: asserted only in a test.
COMPLETED_JOBS_B = [
	("Abdul Salam", 3.0, "Purchased by Customer", 218000),
	("Geetha Ravindran", 5.0, "Purchased by Customer", 324000),
]

FULL_CHAIN = ["ORD", "NPA", "FEAS", "DSGN", "PROC", "DISP", "INST", "KREG", "NMTR", "KTST"]


def _build_completed_book(company, jobs=None):
	"""Drive a handful of jobs the whole way through, so Projects has a real book."""
	from a3_sola.demo import generate_operations_demo as ops

	for consumer_name, capacity, meter_mode, value in (jobs or COMPLETED_JOBS):
		estimate = ops._build_estimate(company, consumer_name)
		if not estimate:
			continue
		if frappe.db.exists("Solar Installation", {"solar_design_estimate": estimate.name}):
			continue
		installation = ops.make_installation(
			company,
			estimate,
			capacity_kw=capacity,
			net_meter_mode=meter_mode,
			gross_contract_value=value,
			order_date=add_days(today(), -150),
		)
		ops._serials(installation)
		ops._fee_payment(company, installation)
		installation = ops._advance(installation, FULL_CHAIN)
		ops._commission(company, installation)
	frappe.db.commit()


def _projects(company):
	return [
		frappe.get_doc("Project", name)
		for name in frappe.get_all(
			"Project",
			filters={"company": company, "solar_installation": ["is", "set"]},
			pluck="name",
			order_by="creation",
		)
	]


def _contract(project):
	name = frappe.db.get_value(
		"Solar OM Contract", {"project": project.name, "docstatus": 1}, "name"
	)
	return frappe.get_doc("Solar OM Contract", name) if name else None


def _plan(project):
	name = frappe.db.get_value(
		"Solar Billing Plan", {"project": project.name, "docstatus": 1}, "name"
	)
	return frappe.get_doc("Solar Billing Plan", name) if name else None


# ---------------------------------------------------------------------- costing
def _book_costs(company, project, index=0):
	"""Work orders with real crew hours, so margin is not a straight line."""
	installation = project.solar_installation
	if frappe.db.exists("Installation Work Order", {"solar_installation": installation}):
		return
	technician = _technician(company, index)
	# Non-overlapping windows: the same technician cannot be booked twice over one date.
	for kind, hours, offset in (
		("Structure Erection", 14.0, -24),
		("Module Mounting", 10.0, -21),
		("DC Wiring", 8.0, -18),
		("AC Wiring & Earthing", 9.0, -15),
		("Testing", 4.0, -12),
	):
		doc = frappe.get_doc(
			{
				"doctype": "Installation Work Order",
				"company": company,
				"solar_installation": installation,
				"work_order_type": kind,
				"planned_start_date": add_days(today(), offset),
				"planned_end_date": add_days(today(), offset + 1),
				"actual_start_date": add_days(today(), offset),
				"actual_end_date": add_days(today(), offset + 1),
				"safety_briefing_done": 1,
				"ppe_verified": 1,
				"work_description": f"{kind} completed as per approved drawing.",
			}
		)
		doc.append("crew", {"technician": technician, "actual_hours": hours})
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
	costing.recalculate_project_costs(project.name)


# ---------------------------------------------------------------------- billing
def _bill(project, through=2, collect=1):
	"""Trigger and invoice the first milestones, collecting some of them."""
	plan = _plan(project)
	if not plan:
		return
	changed = False
	for index, row in enumerate(plan.milestones):
		if index >= through or row.is_triggered:
			continue
		row.is_triggered = 1
		row.triggered_on = add_days(today(), -30 + index * 10)
		changed = True
	if changed:
		plan.flags.ignore_validate_update_after_submit = True
		plan.save(ignore_permissions=True)
		_log(f"{plan.name}: {through} milestone(s) triggered")


# -------------------------------------------------------------------------- O&M
def _visits(company, contract, done=2, missed=0, index=0):
	"""Completed preventive visits, and optionally one that was never made."""
	if frappe.db.exists("Solar OM Visit", {"om_contract": contract.name}):
		return
	technician = _technician(company, index)
	checklist = [(item, category) for item, category in om.VISIT_CHECKLIST]

	for index in range(done):
		visit_date = add_days(today(), -120 + index * 45)
		doc = frappe.get_doc(
			{
				"doctype": "Solar OM Visit",
				"company": company,
				"om_contract": contract.name,
				"visit_date": visit_date,
				"visit_type": "Preventive" if index else "Annual Health Check",
				"technician": technician,
				"time_in": f"{visit_date} 09:30:00",
				"time_out": f"{visit_date} 12:00:00",
				"travel_km": 34,
				"customer_present": 1,
				"customer_feedback": "Satisfied",
				"soiling_observed": "Moderate" if index else "Light",
				"next_visit_recommendation": "Clean the array before the next billing cycle.",
			}
		)
		for item, category in checklist:
			result = "Attention Required" if (index and item.startswith("Module surface")) else "OK"
			doc.append(
				"checklist",
				{
					"checklist_item": item,
					"category": category,
					"result": result,
					"observation": "Dust build-up on the lower row." if result != "OK" else None,
				},
			)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()

	for row in contract.visit_plan[:missed]:
		frappe.db.set_value(
			"Solar OM Visit Plan",
			row.name,
			{"scheduled_date": add_days(today(), -40), "status": "Missed"},
			update_modified=False,
		)
	if missed:
		_log(f"{contract.name}: {missed} visit(s) recorded as missed")


def _tickets(company, contract, specs, breach_first=False, reopen_last=False):
	if frappe.db.exists("Service Ticket", {"om_contract": contract.name}):
		return
	created = []
	for index, (category, severity, description, cause) in enumerate(specs):
		reported = add_days(today(), -60 + index * 12)
		doc = frappe.get_doc(
			{
				"doctype": "Service Ticket",
				"company": company,
				"om_contract": contract.name,
				"reported_on": f"{reported} 10:15:00",
				"reported_via": "WhatsApp" if index % 2 else "Phone",
				"category": category,
				"severity": severity,
				"description": description,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		created.append((doc, cause))

	for index, (doc, cause) in enumerate(created):
		if breach_first and index == 0:
			# Left open past its window: this is what the SLA report exists to surface.
			continue
		doc.reload()
		doc.status = "Resolved"
		doc.root_cause = cause
		doc.resolution_description = "Attended on site, rectified and output verified."
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)

	if reopen_last and created:
		doc, _cause = created[-1]
		doc.reload()
		doc.status = "Reopened"
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
		_log(f"{doc.name}: reopened - the fault came back")


def _warranty(company, contract, status="Replaced"):
	installation = frappe.get_doc("Solar Installation", contract.solar_installation)
	serials = [r for r in installation.serials if r.component_type == "Module" and not r.is_replaced]
	if not serials:
		return
	if frappe.db.exists("Solar Warranty Claim", {"om_contract": contract.name}):
		return
	component, description = MODULE_FAILURES[0]
	doc = frappe.get_doc(
		{
			"doctype": "Solar Warranty Claim",
			"company": company,
			"om_contract": contract.name,
			"component_type": component,
			"serial_no": serials[0].serial_no,
			"failure_date": add_days(today(), -35),
			"failure_description": description,
			"claim_basis": "Product",
			"claim_status": "Submitted",
			"claim_submitted_on": add_days(today(), -30),
			"manufacturer_reference_no": "RZN-CLM-" + frappe.generate_hash(length=5).upper(),
			"claim_value": 9800,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()

	doc.reload()
	if status == "Replaced":
		doc.claim_status = "Replaced"
		doc.replacement_serial_no = f"RZN-RPL-{frappe.generate_hash(length=6).upper()}"
		doc.replacement_received_on = add_days(today(), -12)
		doc.replacement_installed_on = add_days(today(), -8)
		doc.old_unit_returned = 1
		doc.amount_recovered = 9800
	else:
		doc.claim_status = "Rejected"
		doc.rejection_reason = (
			"Manufacturer attributes the crack to impact damage, which the product warranty "
			"excludes. Being challenged with the site photographs."
		)
		doc.amount_recovered = 0
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	_log(f"{doc.name}: {doc.claim_status}")


def _readings(company, contract, ratios):
	"""Monthly meter readings that walk a system down through both thresholds."""
	installation = frappe.get_doc("Solar Installation", contract.solar_installation)
	if frappe.db.exists("Generation Reading", {"solar_installation": installation.name}):
		return
	annual = calculations.estimate_generation(installation.capacity_kw)["annual_generation_kwh"]
	lifetime, date = 0.0, add_months(getdate(today()), -len(ratios) - 1)
	for ratio in ratios:
		date = add_months(date, 1)
		lifetime += (annual / 12.0) * ratio / 100.0
		doc = frappe.get_doc(
			{
				"doctype": "Generation Reading",
				"company": company,
				"solar_installation": installation.name,
				"reading_date": date,
				"reading_source": "Inverter Portal",
				"inverter_lifetime_kwh": flt(lifetime, 2),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()


def _age_for_renewal(company, contract):
	"""An early customer coming to the end of their five years.

	Every EPC has these - jobs from the first year of trading whose obligation is about to
	end - and they are the warmest renewal leads on the book. Without one the pipeline
	report is an empty page.
	"""
	window = frappe.db.get_single_value("A3 Sola Settings", "contract_expiry_window_days") or 90
	start = add_months(getdate(today()), -60 + int(window) // 30)
	frappe.db.set_value(
		"Solar OM Contract",
		contract.name,
		{"start_date": start, "end_date": add_days(today(), int(window) - 20)},
		update_modified=False,
	)
	om.detect_renewals()
	_log(f"{contract.name}: aged into the renewal window")


def _funded_gap_claim(company, project, recovered=False, aged_days=95):
	"""Jobs where the company fronted the subsidy gap.

	Under "Customer Claims Directly" the company funds nothing and there is no receivable -
	so without a funded-gap job the ageing report has nothing to age. One recovered and one
	well past ninety days shows both ends of it.
	"""
	installation = frappe.get_doc("Solar Installation", project.solar_installation)
	if frappe.db.exists("Subsidy Claim", {"solar_installation": installation.name}):
		return
	expected = flt(installation.expected_subsidy_amount) or 78000
	doc = frappe.get_doc(
		{
			"doctype": "Subsidy Claim",
			"company": company,
			"solar_installation": installation.name,
			"claim_model": "Company Funded Gap",
			"claim_status": "Disbursed",
			"claim_submitted_on": add_days(today(), -aged_days),
			"expected_subsidy_amount": expected,
			"amount_recoverable_from_customer": expected,
			"amount_recovered": expected if recovered else 0,
			"recovery_date": add_days(today(), -aged_days + 20) if recovered else None,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	_log(f"{doc.name}: subsidy gap funded by the company, still to recover")


# ------------------------------------------------------------------------- run
def run(company=None):
	"""Build the Projects demo on top of whatever Operations left commissioned."""
	from a3_sola.setup.install import default_company

	company = company or default_company()
	_build_completed_book(company)
	projects = _projects(company)
	if not projects:
		_log("no commissioned projects; run the Operations demo first")
		return
	_log(f"{len(projects)} delivered project(s) to build a history on")

	for index, project in enumerate(projects):
		contract = _contract(project)
		_book_costs(company, project, index)

		# A healthy job: billed and part-collected, visits on time, nothing outstanding.
		if index == 0:
			_bill(project, through=2)
			if contract:
				_visits(company, contract, done=2, index=index)
				_readings(company, contract, [102, 99, 101, 98, 100])
				_warranty(company, contract, status="Replaced")

		# A job in trouble: a breached ticket, a missed visit, generation sliding.
		elif index == 1:
			_bill(project, through=1)
			if contract:
				_visits(company, contract, done=1, missed=1, index=index)
				_tickets(company, contract, TICKETS[:3], breach_first=True, reopen_last=True)
				_readings(company, contract, [98, 88, 79, 76, 71])
				_warranty(company, contract, status="Rejected")

		# A third with a full year of readings, sliding steadily - the one a performance
		# review would pick out.
		elif index == 2:
			_bill(project, through=2)
			if contract:
				_visits(company, contract, done=2, index=index)
				_tickets(company, contract, TICKETS[3:])
				_readings(
					company, contract,
					[101, 99, 97, 96, 94, 92, 90, 88, 86, 84, 82, 79],
				)

		# Everything else: ordinary service history so the reports are not two-row tables.
		else:
			_bill(project, through=min(2, index))
			if contract:
				_visits(company, contract, done=1, index=index)
				_tickets(company, contract, TICKETS[3:])
				_readings(company, contract, [100, 99, 98, 97, 99, 100, 98, 97, 99, 98, 100, 97])

		costing.recalculate_project_costs(project.name)
		_log(f"{project.name}: costs, billing and service history built")

	# Two company-funded subsidy gaps: one recovered, one aged past ninety days.
	_funded_gap_claim(company, projects[0], recovered=True)
	if len(projects) > 1:
		_funded_gap_claim(company, projects[1], recovered=False, aged_days=115)

	# Two contracts on their way out, so the renewal pipeline is not a one-row page.
	for project in projects[-2:]:
		contract = _contract(project)
		if contract and len(projects) > 2:
			_age_for_renewal(company, contract)

	frappe.db.commit()


def teardown():
	order = [
		"Generation Reading",
		"Solar Warranty Claim",
		"Service Ticket",
		"Solar OM Visit",
		"Solar OM Contract",
		"Statutory Fee Recovery",
		"Solar Billing Plan",
	]
	for doctype in order:
		for name in frappe.get_all(doctype, pluck="name"):
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.flags.ignore_links = True
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		_log(f"removed {doctype}")

	for name in frappe.get_all("Project", filters={"solar_installation": ["is", "set"]}, pluck="name"):
		frappe.delete_doc("Project", name, force=True, ignore_permissions=True)
	_log("removed Project")
	frappe.db.commit()


def run_second_tenant(company):
	"""A smaller book for the second tenant.

	Every Projects report is company-filtered, so isolation only reads as real if there is
	something on the other side of the filter to be excluded.
	"""
	_build_completed_book(company, COMPLETED_JOBS_B)
	projects = _projects(company)
	for index, project in enumerate(projects):
		contract = _contract(project)
		_book_costs(company, project, index)
		_bill(project, through=2)
		if contract:
			_visits(company, contract, done=1, index=index)
			_tickets(company, contract, TICKETS[:2])
			_readings(company, contract, [100, 98, 99])
		costing.recalculate_project_costs(project.name)
	_log(f"{len(projects)} delivered project(s) for {company}")
	frappe.db.commit()
