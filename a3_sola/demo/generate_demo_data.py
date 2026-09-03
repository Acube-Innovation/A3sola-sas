# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Demo data for the whole app.

ONE generator with per-module functions and a single entry point. Phases 2 to 8 extend
this file rather than writing their own, so a demo site is built by one command.

    bench --site <site> execute a3_sola.demo.generate_demo_data.run
    bench --site <site> execute a3_sola.demo.generate_demo_data.teardown

Idempotent: every record is tagged and re-running updates rather than duplicating.
"""

import frappe
from frappe.utils import add_days, flt, nowdate, today

from a3_sola.setup.install import default_company, seed_masters

from a3_sola.demo.scale import take

DEMO_TAG = "a3s-demo"
SECOND_COMPANY = "Sunwise Energy Solutions"
SECOND_ABBR = "SWES"

# Districts and bill sizes the client actually sells into.
LEADS = [
	# name, mobile, city, bill, kW, call status, stage, lead status, followup offset
	("Rajesh Nair", "9876543210", "Chalakudy", 4500, 3, "Not Answered", "Step 2: 24hr Nudge", "Contacted", -4),
	("Suresh Kumar", "9847012345", "Thrissur", 8500, 5, "Busy", "Step 1: First Contact", "New", -5),
	("Anil Menon", "9946056789", "Ernakulam", 15000, 10, "Connected", "Completed: Proposal Sent", "Site Visit Scheduled", 1),
	("Dr. Thomas George", "9447112233", "Angamaly", 22000, 15, "Connected", "Completed: Proposal Sent", "In Discussion", -3),
	("Priya Varghese", "9744556677", "Muringoor", 3200, 3, "Switched Off", "Step 3: Value/ROI", "Contacted", 2),
	("Kabeer Ibrahim", "9895001122", "Kochi", 12000, 8, "Connected", "Completed: Proposal Sent", "Converted / Won", 1),
	("Vijay Shankar", "9846223344", "Irinjalakuda", 6000, 4, "Not Answered", "Step 4: Breakup/Close", "Closed / Unresponsive", None),
	("Mathew Paul", "9961334455", "Chalakudy", 9500, 6, "Connected", "Step 1: First Contact", "New", 3),
	("Sneha Rajan", "9895778899", "Aluva", 5200, 4, "Connected", "Step 3: Value/ROI", "In Discussion", 4),
	("Joseph Antony", "9847445566", "Perumbavoor", 18000, 12, "Connected", "Step 2: 24hr Nudge", "Contacted", 5),
	("Fathima Beevi", "9633221100", "Cherthala", 3800, 3, "Busy", "Step 1: First Contact", "New", 6),
	("Deepak Menon", "9995462313", "Kottayam", 7400, 5, "Not Answered", "Step 2: 24hr Nudge", "Not Interested", None),
]

#: (name, category, units/cycle, sanctioned kW, phase, bank details, prior subsidy)
CONSUMERS = [
	("Melking Antony", "Residential", 400, 5, "Single Phase", True, False),
	("Achuthanandan A", "Residential", 320, 3, "Single Phase", True, False),
	("Varghese K D", "Residential", 620, 5, "Single Phase", True, False),
	("A V Johnson", "Residential", 280, 3, "Single Phase", True, False),
	("Bindu Sunilraj", "Residential", 300, 3, "Single Phase", False, False),
	("Godly Francis", "Residential", 900, 8, "Three Phase", True, True),
	("Kalpaka Residents Association", "Group Housing", 2400, 20, "Three Phase", True, False),
	("Athani Industries", "Commercial", 5200, 40, "Three Phase", True, False),
]


def _log(message):
	print(f"  {message}")


# --------------------------------------------------------------------- helpers
def _tagged(doctype, key):
	return frappe.db.get_value(doctype, {"a3s_demo_key": key}, "name") if _has_tag(doctype) else None


def _has_tag(doctype):
	return frappe.get_meta(doctype).has_field("a3s_demo_key")


def _company_b():
	"""A second tenant, with its own masters - so isolation is visibly demonstrable."""
	if not frappe.db.exists("Company", SECOND_COMPANY):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": SECOND_COMPANY,
				"abbr": SECOND_ABBR,
				"default_currency": "INR",
				"country": "India",
			}
		).insert(ignore_permissions=True)
	if not frappe.db.get_value("DISCOM", {"company": SECOND_COMPANY}, "name"):
		seed_masters(SECOND_COMPANY)
	return SECOND_COMPANY


def _master(doctype, title_field, value, company):
	return frappe.db.get_value(doctype, {title_field: value, "company": company}, "name")


def _address(city):
	title = f"Demo {city} {frappe.generate_hash(length=4)}"
	return frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": title,
			"address_type": "Other",
			"address_line1": "Demo House",
			"city": city,
			"state": "Kerala",
			"country": "India",
			"pincode": "683585",
		}
	).insert(ignore_permissions=True).name


# ------------------------------------------------------------------ entity roles
def setup_company_identity(company):
	"""The three roles every outgoing document depends on.

	The proposal and the bank account belong to the EPC; the portal registration and the
	DISCOM paperwork name the registered vendor. Populating both makes the generated
	documents complete.
	"""
	doc = frappe.get_doc("Company", company)
	values = {
		"registered_vendor_name": "RIM Projects Pvt. Ltd.",
		"registered_vendor_address": "12/372-2 Karunalayam Road, near YWCA Aluva, Periyar Nagar, Aluva, Kerala 683101",
		"mnre_vendor_registration_no": "DEMO-MNRE-VENDOR-001",
		"epc_name": "Renewcore Innovations LLP",
		"epc_address": "14/204A, 1st Floor, Maliyekkal, Kalpaka Nagar, Athani, Nedumbassery 683585",
		"epc_contact_no": "+91 8891024312",
		"epc_email": "renewcoreinnovations@gmail.com",
		"epc_authorised_signatory": "Shiju N K",
		"epc_signatory_designation": "Managing Partner",
		"payee_legal_name": "Renewcore Innovations LLP",
		"payee_pan": "ABKFR4380H",
		"payee_gstin": "32ABKFR4380H1Z3",
		"payee_bank_name": "ICICI Bank",
		"payee_bank_account_no": "028905004574",
		"payee_bank_branch": "Aluva",
		"payee_bank_ifsc": "ICIC0000289",
	}
	changed = False
	for field, value in values.items():
		if not doc.get(field):
			doc.set(field, value)
			changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
	_log(f"entity blocks set on {company}")


# ------------------------------------------------------------------------ leads
def generate_leads(company):
	created = 0
	for name, mobile, city, bill, kw, call_status, stage, status, offset in take(LEADS):
		if frappe.db.exists("Lead", {"lead_name": name, "company": company}):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Lead",
				"company": company,
				"lead_name": name,
				"mobile_no": mobile,
				"city": city,
				"source": "Walk In",
				"discom": _master("DISCOM", "discom_name", "KSEB", company),
				"consumer_category": "Residential",
				"connection_type": "Three Phase" if kw > 3 else "Single Phase",
				"avg_monthly_bill": bill,
				"approx_capacity_kw": kw,
				"approx_consumption_units": bill / 6.0 * 2,
				"call_status": call_status,
				"outreach_stage": stage,
				"solar_lead_status": status,
				"last_message_date": add_days(today(), -2),
				"next_followup_date": add_days(today(), offset) if offset is not None else None,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		created += 1
	_log(f"{created} leads (3 deliberately overdue for follow-up)")


# -------------------------------------------------------------------- consumers
def generate_consumers(company):
	names = []
	for name, category, units, load, phase, bank, prior in take(CONSUMERS):
		existing = frappe.db.get_value("Solar Consumer", {"consumer_name": name, "company": company}, "name")
		if existing:
			names.append(existing)
			continue
		values = {
			"doctype": "Solar Consumer",
			"company": company,
			"consumer_name": name,
			"consumer_category": category,
			"discom": _master("DISCOM", "discom_name", "KSEB", company),
			"discom_section": _master("DISCOM Section", "section_name", "Athani", company),
			"consumer_number": f"11565{frappe.utils.random_string(8).upper()[:8]}",
			"tariff_category": "LT-1/Single" if phase == "Single Phase" else "LT-1/Three",
			"connection_type": phase,
			"connected_load_watts": load * 1000 * 0.6,
			"sanctioned_load_kw": load,
			"avg_consumption_units": units,
			"billing_frequency": "Bimonthly",
			"installation_address": _address("Ernakulam"),
			"roof_type": _master("Roof Type", "roof_type", "RCC Flat", company),
			"local_body_type": "Panchayat",
			"local_body_name": "Nedumbassery",
			"village": "Athani",
			"survey_number": "142/3",
			"has_availed_prior_subsidy": 1 if prior else 0,
			"prior_scheme_name": "PM Surya Ghar" if prior else None,
			"prior_subsidy_year": 2024 if prior else None,
		}
		if bank:
			values.update(
				{
					"bank_account_holder_name": name,
					"bank_account_no": f"0289{frappe.utils.random_string(10)[:10]}",
					"bank_name": "ICICI Bank",
					"bank_branch": "Aluva",
					"bank_ifsc_code": "ICIC0000289",
				}
			)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		names.append(doc.name)
	_log(f"{len(names)} solar consumers (one without bank details, one with a prior subsidy)")
	return names


# ---------------------------------------------------------------------- surveys
def generate_surveys(company, consumers):
	"""Five surveys: heavy shading, civil work, an asbestos go/no-go failure, two clean."""
	profiles = [
		{"segments": [(280, True)], "shading": 0},
		{"segments": [(420, True), (120, False)], "shading": 22},
		{"segments": [(240, True)], "shading": 0, "civil_work_required": 1, "additional_civil_cost": 35000},
		{"segments": [(700, True)], "shading": 5},
		{"segments": [(300, True)], "shading": 0, "asbestos_present": 1},
	]
	made = []
	for consumer_name, profile in zip(consumers, profiles):
		if frappe.db.exists("Site Survey", {"solar_consumer": consumer_name, "docstatus": ["<", 2]}):
			continue
		consumer = frappe.get_doc("Solar Consumer", consumer_name)
		segments = profile.pop("segments")
		shading = profile.pop("shading", 0)
		values = {
			"doctype": "Site Survey",
			"company": company,
			"solar_consumer": consumer.name,
			"survey_date": add_days(today(), -10),
			"roof_type": consumer.roof_type,
			"total_roof_area_sqft": sum(a for a, _ in segments),
			"feasibility_status": "Feasible",
			"capacity_applied_kw": 5,
			"roof_access_24x7": 1,
			"owner_consent_obtained": 1,
			"water_source_for_cleaning": "Owner Overhead Tank",
			"roof_segments": [
				{"segment_name": f"Segment {i}", "area_sqft": area, "is_usable": 1 if usable else 0}
				for i, (area, usable) in enumerate(segments, start=1)
			],
		}
		if shading:
			values["shadow_observations"] = [
				{"time_slot": slot, "shading_percent": shading, "obstruction_source": "Coconut palm"}
				for slot in ("08:00", "10:00", "14:00", "16:00")
			]
		values.update(profile)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		if not doc.asbestos_present:
			doc.submit()
		made.append(doc.name)
	_log(f"{len(made)} site surveys (one shaded, one needing civil work, one asbestos-blocked)")
	return made


# -------------------------------------------------------------------- estimates
def generate_estimates(company, consumers):
	"""Estimates covering all three binding constraints, plus a three-option 10 kWp job."""
	scheme = _master("Subsidy Scheme", "scheme_name", "PM Surya Ghar: Muft Bijli Yojana", company)
	tariff = _master("Electricity Tariff", "tariff_name", "KSEB Domestic Bimonthly", company)
	made = []

	for consumer_name in consumers[:4]:
		if frappe.db.exists("Solar Design Estimate", {"solar_consumer": consumer_name, "docstatus": ["<", 2]}):
			continue
		survey = frappe.db.get_value(
			"Site Survey", {"solar_consumer": consumer_name, "docstatus": 1}, "name"
		)
		if not survey:
			continue
		consumer = frappe.get_doc("Solar Consumer", consumer_name)
		package = _master("Solar Package", "specification_code", "3Kw 1PH", company)
		doc = frappe.get_doc(
			{
				"doctype": "Solar Design Estimate",
				"company": company,
				"solar_consumer": consumer.name,
				"site_survey": survey,
				"estimate_date": add_days(today(), -7),
				"subsidy_scheme": scheme,
				"electricity_tariff": tariff,
				"net_meter_mode": "Purchased by Customer",
				"options": [
					{
						"option_name": "Option 1 - String Inverter",
						"inverter_topology": "String",
						"solar_package": package,
						"system_cost": 215000,
						"is_recommended": 1,
						"display_order": 1,
					}
				],
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		made.append(doc.name)

	_log(f"{len(made)} design estimates")
	return made


def generate_three_option_proposal(company, consumers):
	"""The client's most recent real proposal: 10 kWp non-DCR with three inverter options."""
	consumer_name = consumers[6] if len(consumers) > 6 else consumers[-1]
	if frappe.db.exists("Solar Proposal", {"solar_consumer": consumer_name, "docstatus": ["<", 2]}):
		return None

	consumer = frappe.get_doc("Solar Consumer", consumer_name)
	survey = frappe.get_doc(
		{
			"doctype": "Site Survey",
			"company": company,
			"solar_consumer": consumer.name,
			"survey_date": add_days(today(), -6),
			"roof_type": consumer.roof_type,
			"total_roof_area_sqft": 900,
			"feasibility_status": "Feasible",
			"roof_access_24x7": 1,
			"owner_consent_obtained": 1,
			"roof_segments": [{"segment_name": "Terrace", "area_sqft": 800, "is_usable": 1}],
		}
	)
	survey.flags.ignore_permissions = True
	survey.insert(ignore_permissions=True)
	survey.submit()

	package = _master("Solar Package", "specification_code", "10KW 3PH Non-DCR", company)
	make = lambda m: frappe.db.get_value(  # noqa: E731
		"Component Make", {"make_name": m, "component_type": "Inverter", "company": company}, "name"
	)
	estimate = frappe.get_doc(
		{
			"doctype": "Solar Design Estimate",
			"company": company,
			"solar_consumer": consumer.name,
			"site_survey": survey.name,
			"estimate_date": add_days(today(), -5),
			"electricity_tariff": _master("Electricity Tariff", "tariff_name", "KSEB Domestic Bimonthly", company),
			"net_meter_mode": "Purchased by Customer",
			"connection_type": "Three Phase",
			"options": [
				{
					"option_name": "Option 1 - String Inverter", "inverter_topology": "String",
					"solar_package": package, "inverter_make": make("Solinteg"),
					"inverter_specification": "10kW Three Phase On-Grid with Online Monitoring",
					"inverter_count": 1, "system_cost": 480000, "is_recommended": 1, "display_order": 1,
				},
				{
					"option_name": "Option 2 - SolarEdge with Optimiser",
					"inverter_topology": "String with Optimiser", "solar_package": package,
					"inverter_make": make("SolarEdge"),
					"inverter_specification": "10kW Three Phase On-Grid with Panel level optimizer and Online Monitoring",
					"inverter_count": 1, "system_cost": 490000, "display_order": 2,
				},
				{
					"option_name": "Option 3 - Microinverter", "inverter_topology": "Microinverter",
					"solar_package": package, "inverter_make": make("Hoymiles"),
					"inverter_specification": "5 kW Three Phase On-Grid Microinverter with 4 MPPT and Online Monitoring",
					"inverter_count": 2, "system_cost": 510000, "display_order": 3,
				},
			],
		}
	)
	estimate.flags.ignore_permissions = True
	estimate.insert(ignore_permissions=True)
	estimate.submit()
	_log("10 kWp non-DCR estimate with three priced inverter options")
	return estimate.name


# ----------------------------------------------------------------- eligibility
def generate_eligibility(company, consumers):
	scheme = _master("Subsidy Scheme", "scheme_name", "PM Surya Ghar: Muft Bijli Yojana", company)
	made = []
	for consumer_name in consumers[:5]:
		if frappe.db.exists("Subsidy Eligibility Check", {"solar_consumer": consumer_name, "docstatus": ["<", 2]}):
			continue
		estimate = frappe.db.get_value(
			"Solar Design Estimate", {"solar_consumer": consumer_name, "docstatus": 1}, "name"
		)
		doc = frappe.get_doc(
			{
				"doctype": "Subsidy Eligibility Check",
				"company": company,
				"solar_consumer": consumer_name,
				"design_estimate": estimate,
				"subsidy_scheme": scheme,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		made.append(doc.name)
	_log(f"{len(made)} eligibility checks")
	return made


# -------------------------------------------------------------------- proposals
def generate_proposals(company, estimates):
	made = []
	for index, estimate_name in enumerate(estimates):
		estimate = frappe.get_doc("Solar Design Estimate", estimate_name)
		if frappe.db.exists("Solar Proposal", {"solar_design_estimate": estimate_name, "docstatus": ["<", 2]}):
			continue
		consumer = frappe.get_doc("Solar Consumer", estimate.solar_consumer)
		doc = frappe.get_doc(
			{
				"doctype": "Solar Proposal",
				"company": company,
				"solar_consumer": consumer.name,
				"solar_design_estimate": estimate.name,
				"salutation": "Mr",
				"customer_name": consumer.consumer_name,
				"mobile_no": consumer.mobile_no or "9895778516",
				"location": "Athani",
				"district": "Ernakulam",
				"proposal_date": add_days(today(), -4),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		if index < 2:
			doc.db_set("sent_via", "WhatsApp", update_modified=False)
			doc.db_set("status", "Sent", update_modified=False)
		made.append(doc.name)
	_log(f"{len(made)} proposals on the register")
	return made


# ------------------------------------------------------------------- entrypoint
def run_sample(count=5):
	"""Five of everything, across all six phases. The default way to fill a demo site.

	`run()` builds the full hand-written set, which is more records than anyone wants to
	read. This caps every list at `count` so each list view, report and filter has enough
	to be meaningful and little enough to take in at a glance.

	Operations and Projects are not capped, and deliberately: they do not build N of one
	thing, they build a scenario - a job stuck at DISCOM feasibility past its SLA, a
	financed one awaiting sanction, one with a breached service ticket, one whose
	generation is sliding. Slicing that to a number would leave whichever states happened
	to sort first, which is the opposite of useful. They produce five to seven jobs anyway.
	"""
	frappe.flags.a3s_demo_limit = int(count)
	try:
		return run()
	finally:
		frappe.flags.a3s_demo_limit = None


def run():
	"""Build the whole demo. Idempotent - safe to re-run."""
	frappe.flags.in_demo = True
	company = default_company()
	print(f"a3_sola demo data for {company}")

	setup_company_identity(company)
	generate_leads(company)
	consumers = generate_consumers(company)
	generate_surveys(company, consumers)
	estimates = generate_estimates(company, consumers)
	generate_eligibility(company, consumers)
	generate_proposals(company, estimates)
	generate_three_option_proposal(company, consumers)

	# Phase 2: the execution chain, from order to refund.
	from a3_sola.demo import generate_operations_demo

	generate_operations_demo.run(company)

	# Phase 3: what those commissioned jobs cost, billed and now owe in service.
	from a3_sola.demo import generate_projects_demo

	generate_projects_demo.run(company)

	# Phase 4: the public funnel, which is platform-level and not per company.
	from a3_sola.demo import generate_platform_demo

	generate_platform_demo.run()

	# Phase 5: subscriptions, collections, invoices and settlements. Mock gateway only.
	from a3_sola.demo import generate_payments_demo

	generate_payments_demo.run(company)

	# Phase 6: provisioned tenants, including the awkward states an operator has to deal
	# with. Without these the Provisioning Failures view and the isolation report are empty.
	from a3_sola.demo import generate_provisioning_demo

	generate_provisioning_demo.run(company)

	# Phase 7: the lifecycle. Subscriptions in every state with the history behind them,
	# because the decision audit, the suspension register and the MRR bridge are all built
	# on the event log - a tenant simply marked Suspended makes them look broken.
	from a3_sola.demo import generate_lifecycle_demo

	generate_lifecycle_demo.run(company)

	# A second tenant with its own masters, so isolation is demonstrable.
	company_b = _company_b()
	generate_consumers(company_b)
	generate_projects_demo.run_second_tenant(company_b)
	_log(f"second tenant {company_b} with its own master data")

	frappe.db.commit()
	print("done")


def teardown():
	"""Remove everything run() created, newest dependency first."""
	frappe.flags.in_demo = True
	from a3_sola.demo import generate_operations_demo

	from a3_sola.demo import (
		generate_payments_demo,
		generate_platform_demo,
		generate_projects_demo,
	)

	from a3_sola.demo import generate_provisioning_demo

	generate_provisioning_demo.teardown()
	generate_payments_demo.teardown()
	generate_platform_demo.teardown()
	generate_projects_demo.teardown()
	generate_operations_demo.teardown()
	order = [
		"Solar Proposal",
		"Subsidy Eligibility Check",
		"Solar Design Estimate",
		"Site Survey",
		"Solar Consumer",
	]
	for doctype in order:
		for name in frappe.get_all(doctype, pluck="name"):
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				# Teardown removes the whole graph, so a link into a document that is
				# about to go too must not block the cancel.
				doc.flags.ignore_links = True
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		_log(f"removed {doctype}")
	for name, *_ in LEADS:
		for lead in frappe.get_all("Lead", filters={"lead_name": name}, pluck="name"):
			frappe.delete_doc("Lead", lead, force=True, ignore_permissions=True)
	frappe.db.commit()
	print("demo data removed")
