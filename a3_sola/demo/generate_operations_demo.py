# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Solar Operations demo data.

Extends the single demo generator rather than adding a second one. Builds jobs across the
whole chain so every report has something real in it: stuck at feasibility, awaiting a loan,
awaiting a net meter, fully commissioned, blocked by a snag, and a refund short-received.
"""

import frappe
from frappe.utils import add_days, flt, today

from a3_sola.api import stages
from a3_sola.tests.fixtures import name_of


def _log(message):
	print(f"  {message}")


def _package(code, company):
	return name_of("Solar Package", "specification_code", code, company)


def _stage_template(company):
	return frappe.db.get_value(
		"Installation Stage Template", {"is_default": 1, "company": company}, "name"
	)


#: Consumers the Operations demo owns, so it never competes with the CRM demo for estimates.
OPS_CONSUMERS = [
	"Chacko M K", "Bindu Sunilraj", "K Y Antony", "Syam Nath",
	"Jose Mathew", "Ramesh Pillai", "Latha Krishnan",
]


def _consumers_with_estimates(company, needed=7):
	"""Reuse spare CRM estimates, then build our own so the chain is always complete."""
	spare = [
		row
		for row in frappe.get_all(
			"Solar Design Estimate",
			filters={"company": company, "docstatus": 1},
			fields=["name", "solar_consumer", "final_capacity_kw", "subsidy_scheme", "net_meter_mode"],
			order_by="creation",
		)
		if not frappe.db.exists("Solar Installation", {"solar_design_estimate": row.name})
		# Never adopt a test fixture's estimate - demo data must read as real jobs.
		and not (frappe.db.get_value("Solar Consumer", row.solar_consumer, "consumer_name") or "").startswith("Test ")
	]
	while len(spare) < needed:
		built = _build_estimate(company, OPS_CONSUMERS[len(spare) % len(OPS_CONSUMERS)])
		if not built:
			break
		spare.append(built)
	return spare[:needed]


def _build_estimate(company, consumer_name):
	"""A consumer, a survey and a submitted estimate - the Phase 1 chain, minimally."""
	from a3_sola.tests.fixtures import make_address

	suffix = frappe.generate_hash(length=4).upper()
	consumer = frappe.get_doc(
		{
			"doctype": "Solar Consumer",
			"company": company,
			"consumer_name": f"{consumer_name} {suffix}",
			"consumer_category": "Residential",
			"discom": name_of("DISCOM", "discom_name", "KSEB", company),
			"discom_section": name_of("DISCOM Section", "section_name", "Athani", company),
			"consumer_number": f"11565{frappe.utils.random_string(8).upper()[:8]}",
			"tariff_category": "LT-1/Single",
			"connection_type": "Single Phase",
			"connected_load_watts": 2300,
			"sanctioned_load_kw": 5,
			"avg_consumption_units": 750,
			"billing_frequency": "Bimonthly",
			"installation_address": make_address(),
			"roof_type": name_of("Roof Type", "roof_type", "RCC Flat", company),
			"local_body_type": "Panchayat",
			"local_body_name": "Nedumbassery",
			"village": "Athani",
			"survey_number": "142/3",
			"bank_account_holder_name": f"{consumer_name} {suffix}",
			"bank_account_no": f"0289{frappe.utils.random_string(10)[:10]}",
			"bank_name": "ICICI Bank",
			"bank_branch": "Aluva",
			"bank_ifsc_code": "ICIC0000289",
		}
	)
	consumer.flags.ignore_permissions = True
	consumer.insert(ignore_permissions=True)

	survey = frappe.get_doc(
		{
			"doctype": "Site Survey",
			"company": company,
			"solar_consumer": consumer.name,
			"survey_date": add_days(today(), -70),
			"roof_type": consumer.roof_type,
			"total_roof_area_sqft": 300,
			"feasibility_status": "Feasible",
			"roof_access_24x7": 1,
			"owner_consent_obtained": 1,
			"water_source_for_cleaning": "Owner Overhead Tank",
			"roof_segments": [{"segment_name": "Terrace", "area_sqft": 240, "is_usable": 1}],
		}
	)
	survey.flags.ignore_permissions = True
	survey.insert(ignore_permissions=True)
	survey.submit()

	estimate = frappe.get_doc(
		{
			"doctype": "Solar Design Estimate",
			"company": company,
			"solar_consumer": consumer.name,
			"site_survey": survey.name,
			"estimate_date": add_days(today(), -65),
			"subsidy_scheme": name_of(
				"Subsidy Scheme", "scheme_name", "PM Surya Ghar: Muft Bijli Yojana", company
			),
			"electricity_tariff": name_of(
				"Electricity Tariff", "tariff_name", "KSEB Domestic Bimonthly", company
			),
			"net_meter_mode": "Purchased by Customer",
			"options": [
				{
					"option_name": "Option 1 - String Inverter",
					"inverter_topology": "String",
					"solar_package": _package("3Kw 1PH", company),
					"system_cost": 215000,
					"is_recommended": 1,
					"display_order": 1,
				}
			],
		}
	)
	estimate.flags.ignore_permissions = True
	estimate.insert(ignore_permissions=True)
	estimate.submit()
	return frappe._dict(
		{
			"name": estimate.name,
			"solar_consumer": consumer.name,
			"final_capacity_kw": estimate.final_capacity_kw,
			"subsidy_scheme": estimate.subsidy_scheme,
			"net_meter_mode": estimate.net_meter_mode,
		}
	)


def make_installation(company, estimate, **kwargs):
	consumer = frappe.get_doc("Solar Consumer", estimate.solar_consumer)
	values = {
		"doctype": "Solar Installation",
		"company": company,
		"solar_consumer": consumer.name,
		"solar_design_estimate": estimate.name,
		"solar_package": _package("3Kw 1PH", company),
		"capacity_kw": estimate.final_capacity_kw,
		"system_type": "On-Grid",
		"connection_type": consumer.connection_type,
		"discom": consumer.discom,
		"discom_section": consumer.discom_section,
		"installation_address": consumer.installation_address,
		"roof_type": consumer.roof_type,
		"subsidy_scheme": estimate.subsidy_scheme,
		"net_meter_mode": estimate.net_meter_mode or "Purchased by Customer",
		"gross_contract_value": 215000,
		"expected_subsidy_amount": 78000,
		"stage_template": _stage_template(company),
		"order_date": add_days(today(), -60),
		"project_manager": frappe.session.user,
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc


def _evidence(installation, stage_code):
	doc = frappe.get_doc("Solar Installation", installation.name)
	for row in doc.documents:
		if row.stage_code == stage_code and row.is_mandatory:
			row.attachment = "/files/demo-evidence.pdf"
			row.document_date = today()
			row.is_verified = 1
			row.verified_by = frappe.session.user
			row.verified_on = frappe.utils.now_datetime()
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)


def _advance(installation, codes):
	for code in codes:
		_evidence(installation, code)
		try:
			stages.advance_stage(installation.name, code, actual_date=today())
		except frappe.ValidationError as exc:
			_log(f"stopped at {code}: {exc}")
			break
	return frappe.get_doc("Solar Installation", installation.name)


def _serials(installation, modules=6):
	doc = frappe.get_doc("Solar Installation", installation.name)
	if doc.serials:
		return doc
	prefix = frappe.generate_hash(length=6).upper()
	for i in range(modules):
		doc.append(
			"serials",
			{
				"component_type": "Module",
				"serial_no": f"{prefix}-M{i:03d}",
				"manufacturer": "Rayzon",
				"model_number": "550 Wp Mono PERC Bifacial DCR",
				"wattage": 550,
				"dcr_certificate_no": f"DCR-{prefix}",
			},
		)
	doc.append(
		"serials",
		{
			"component_type": "Inverter",
			"serial_no": f"{prefix}-INV",
			"manufacturer": "Solinteg",
			"model_number": "3kW Single Phase On-Grid",
		},
	)
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return doc


def _backdate_stage(installation, stage_code, days):
	"""Make a stage look genuinely old, so the ageing reports have real numbers."""
	frappe.db.sql(
		"""update `tabInstallation Stage Log`
		   set actual_start_date = %(start)s, days_in_stage = %(days)s,
		       is_sla_breached = case when sla_days and %(days)s > sla_days then 1 else 0 end
		   where parent = %(parent)s and stage_code = %(code)s""",
		{"parent": installation.name, "code": stage_code, "days": days, "start": add_days(today(), -days)},
	)
	doc = frappe.get_doc("Solar Installation", installation.name)
	stages.recompute(doc)
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return doc


def run(company=None):
	"""Build the Operations demo. Idempotent."""
	from a3_sola.setup.install import default_company

	company = company or default_company()
	estimates = _consumers_with_estimates(company, needed=7)
	if not estimates:
		_log("no unused design estimates; Operations demo already built")
		return

	built = []

	# 1 & 2 - stuck at DISCOM feasibility well past SLA, one with an open query.
	for index in range(min(2, len(estimates))):
		installation = make_installation(company, estimates[index])
		_advance(installation, ["ORD", "NPA"])
		_backdate_stage(installation, "FEAS", 75)
		built.append(installation.name)
	if len(built) >= 1:
		_raise_query(company, built[0])

	# 3 - financed job awaiting sanction.
	if len(estimates) > 2:
		installation = make_installation(company, estimates[2], is_financed=1)
		_advance(installation, ["ORD", "NPA", "FEAS", "VFR"])
		_make_loan(company, installation, disbursed=False)
		built.append(installation.name)

	# 4 - financed job with the advance received, balance outstanding.
	if len(estimates) > 3:
		installation = make_installation(company, estimates[3], is_financed=1)
		_advance(installation, ["ORD", "NPA", "FEAS", "VFR"])
		_make_loan(company, installation, disbursed=True)
		built.append(installation.name)

	# 5 - awaiting a net meter from the DISCOM.
	if len(estimates) > 4:
		installation = make_installation(
			company, estimates[4], net_meter_mode="Availed from DISCOM on Rental"
		)
		_serials(installation)
		_advance(installation, ["ORD", "NPA", "FEAS", "DSGN", "PROC", "DISP", "INST", "KREG"])
		_backdate_stage(installation, "NMTR", 28)
		_fee_payment(company, installation)
		built.append(installation.name)

	# 6 - fully commissioned, with an executed agreement and a document pack.
	if len(estimates) > 5:
		installation = make_installation(company, estimates[5])
		_serials(installation)
		_advance(
			installation,
			["ORD", "NPA", "FEAS", "DSGN", "PROC", "DISP", "INST", "KREG", "NMTR", "KTST"],
		)
		_commission(company, installation)
		built.append(installation.name)

	# 7 - commissioned but blocked at PCR by an open major snag.
	if len(estimates) > 6:
		installation = make_installation(company, estimates[6])
		_serials(installation)
		_advance(
			installation,
			["ORD", "NPA", "FEAS", "DSGN", "PROC", "DISP", "INST", "KREG", "NMTR", "KTST"],
		)
		_snag(company, installation, "Major")
		built.append(installation.name)

	# 8 - a critical safety snag, straight from the field.
	if built:
		_snag(company, frappe.get_doc("Solar Installation", built[-1]), "Critical", category="Safety")

	frappe.db.commit()
	_log(f"{len(built)} installations across the chain (feasibility, loan, net meter, commissioned, blocked)")


def _raise_query(company, installation_name):
	if frappe.db.exists("Portal Application", {"solar_installation": installation_name}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Portal Application",
			"company": company,
			"solar_installation": installation_name,
			"application_type": "DISCOM Feasibility",
			"application_number": f"FEAS-{frappe.generate_hash(length=6).upper()}",
			"application_date": add_days(today(), -75),
			"application_status": "Query Raised",
			"queries": [
				{
					"query_date": add_days(today(), -30),
					"query_raised_by": "Assistant Engineer",
					"query_description": "Sanctioned load documentation required for the proposed capacity.",
				}
			],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	_log("one job carrying an open DISCOM query")


def _make_loan(company, installation, disbursed):
	if frappe.db.exists("Loan Application", {"solar_installation": installation.name}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Loan Application",
			"company": company,
			"solar_installation": installation.name,
			"lender": "State Bank of India",
			"lender_branch": "Chalakudy",
			"loan_scheme": "PM Surya Ghar via Jan Samarth",
			"jan_samarth_id": f"ANS-SOLAR-{frappe.utils.random_string(8)}",
			"loan_sanction_no": f"SOL-{frappe.utils.random_string(6)}",
			"applied_on": add_days(today(), -40),
			"project_cost_all_inclusive": 215000,
			"status": "Sanctioned",
			"sanctioned_on": add_days(today(), -30),
			"sanctioned_amount": 200000,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()

	if disbursed:
		doc.append(
			"disbursements",
			{
				"tranche": "Advance",
				"disbursement_date": add_days(today(), -25),
				"amount": 140000,
				"utr_or_reference": f"UTR{frappe.utils.random_string(10)}",
				"credited_to": "EPC Account",
			},
		)
		doc.status = "Disbursed (Advance)"
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)


def _fee_payment(company, installation):
	if frappe.db.exists("Statutory Fee Payment", {"solar_installation": installation.name}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Statutory Fee Payment",
			"company": company,
			"solar_installation": installation.name,
			"fee_type": "Registration Fee",
			"paid_by": "Company on Behalf of Customer",
			"payment_date": add_days(today(), -20),
			"payment_reference": f"RCPT-{frappe.utils.random_string(6)}",
			"receipt": "/files/demo-receipt.pdf",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()


def _commission(company, installation):
	if frappe.db.exists("Commissioning Report", {"solar_installation": installation.name}):
		return
	# First-day output has to scale with the array, or a 5 kWp job commissions at a
	# performance ratio the DISCOM would reject.
	capacity = flt(
		frappe.db.get_value("Solar Installation", installation.name, "capacity_kw")
	) or 3.0
	first_day = flt(capacity * 4.5, 2)
	report = frappe.get_doc(
		{
			"doctype": "Commissioning Report",
			"company": company,
			"solar_installation": installation.name,
			"commissioning_date": add_days(today(), -10),
			"net_meter_serial_no": f"NM{frappe.utils.random_string(8).upper()}",
			"net_meter_make": "L&T",
			"commissioning_certificate_no": f"CC-{frappe.utils.random_string(6).upper()}",
			"commissioning_certificate": "/files/demo-cc.pdf",
			"earthing_verified": 1,
			"surge_protection_installed": 1,
			"dc_isolator_on_inverter_incoming": 1,
			"visual_isolator_before_connectivity_point": 1,
			"wiring_as_per_approved_scheme": 1,
			"earthing_provided_ac_db": 1,
			"earthing_provided_dc_db": 1,
			"earthing_provided_structure_and_panels": 1,
			"earthing_provided_la_and_inverter_body": 1,
			"earthing_provided_isolator": 1,
			"completion_certificate_submitted_to_section": 1,
			"first_day_generation_kwh": first_day,
			"radiation_sensor_id": "PYR-2024-11",
			"radiation_sensor_calibration_certificate": "/files/demo-calibration.pdf",
			"calibration_lab": "NABL Accredited",
			"calibration_valid_until": add_days(today(), 200),
			"measured_irradiance_w_m2": 940,
			"customer_handover_done": 1,
			"user_manual_provided": 1,
			"warranty_certificates_provided": 1,
			"customer_trained_on_monitoring": 1,
		}
	)
	report.flags.ignore_permissions = True
	report.insert(ignore_permissions=True)

	# The DISCOM inspects every protection setting and asks for proof of each.
	values = {
		"Over Voltage Trip": ("264", "V", "200 ms"),
		"Under Voltage Trip": ("192", "V", "200 ms"),
		"Over Frequency Trip": ("50.50", "Hz", "200 ms"),
		"Under Frequency Trip": ("47.50", "Hz", "200 ms"),
		"Anti-Islanding": ("Provided", None, None),
		"Grid Failure Trip Delay": ("60", "s", None),
		"Re-Energisation Delay": ("60", "s", None),
	}
	for row in report.protection_settings:
		value, unit, trip = values[row.protection_function]
		row.setting_value = value
		row.setting_unit = unit
		row.trip_time = trip
		row.proof_type = "OEM Factory Test Certificate"
		row.proof_attachment = "/files/demo-proof.pdf"
	report.save(ignore_permissions=True)
	report.submit()

	_agreement(company, installation, report)
	_log("one fully commissioned job with an executed net metering agreement")


def _agreement(company, installation, report):
	if frappe.db.exists("Net Metering Agreement", {"solar_installation": installation.name}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Net Metering Agreement",
			"company": company,
			"solar_installation": installation.name,
			"commissioning_report": report.name,
			"agreement_date": report.commissioning_date,
			"place_of_execution": "Ernakulam",
			"discom_representative_name": "Assistant Engineer, Athani",
			"witness_1_name": "K. Rajan",
			"witness_2_name": "S. Meera",
			"spin": f"SPIN{frappe.utils.random_string(8).upper()}",
			"supply_voltage": "240 V",
			"stamp_paper_serial": frappe.utils.random_string(10).upper(),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()


def _snag(company, installation, severity, category="Cabling"):
	if frappe.db.exists(
		"Installation Snag", {"solar_installation": installation.name, "severity": severity}
	):
		return
	descriptions = {
		"Cabling": "DC cable dressing incomplete along the roof run; UV exposure risk.",
		"Safety": "Lightning arrester earth pit cover missing at the array edge.",
	}
	doc = frappe.get_doc(
		{
			"doctype": "Installation Snag",
			"company": company,
			"solar_installation": installation.name,
			"reported_on": add_days(today(), -5),
			"source": "Internal QC",
			"category": category,
			"severity": severity,
			"description": descriptions.get(category, "Defect observed during inspection."),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)


def teardown():
	order = [
		"Net Metering Agreement",
		"Commissioning Report",
		"Statutory Fee Payment",
		"Subsidy Claim",
		"Installation Snag",
		"Loan Application",
		"Portal Application",
		"Installation Work Order",
		"Solar Installation",
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
	frappe.db.commit()
