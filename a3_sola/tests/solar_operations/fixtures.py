# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Helpers for the Solar Operations test suite."""

import frappe
from frappe.utils import today

from a3_sola.tests.fixtures import (
	default_company,
	make_consumer,
	make_estimate,
	make_survey,
	name_of,
	package,
)


def stage_template(company=None, name="PM Surya Ghar Residential (Default)"):
	return name_of("Installation Stage Template", "template_name", name, company)


def make_installation(consumer=None, estimate=None, submit=True, **kwargs):
	"""A Solar Installation, built the way the Sales Order handoff builds one."""
	consumer = consumer or make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
	if estimate is None:
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey, submit=True)

	values = {
		"doctype": "Solar Installation",
		"company": consumer.company,
		"solar_consumer": consumer.name,
		"solar_design_estimate": estimate.name,
		"solar_package": package("3Kw 1PH", consumer.company),
		"capacity_kw": estimate.final_capacity_kw,
		"system_type": "On-Grid",
		"connection_type": consumer.connection_type,
		"discom": consumer.discom,
		"discom_section": consumer.discom_section,
		"installation_address": consumer.installation_address,
		"subsidy_scheme": estimate.subsidy_scheme,
		"net_meter_mode": estimate.net_meter_mode,
		"gross_contract_value": 215000,
		"expected_subsidy_amount": estimate.applicable_subsidy_amount,
		"stage_template": stage_template(consumer.company),
		"order_date": today(),
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def attach_stage_documents(installation, stage_code, verified=True):
	"""Satisfy the evidence gate for a stage so a test can move past it."""
	doc = frappe.get_doc("Solar Installation", installation.name)
	for row in doc.documents:
		if row.stage_code != stage_code or not row.is_mandatory:
			continue
		row.attachment = "/files/test-evidence.pdf"
		row.document_date = today()
		if verified:
			row.is_verified = 1
			row.verified_by = frappe.session.user
			row.verified_on = frappe.utils.now_datetime()
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return doc


def complete_through(installation, stage_codes):
	"""Advance a chain of stages, attaching evidence for each."""
	from a3_sola.api import stages

	for code in stage_codes:
		attach_stage_documents(installation, code)
		stages.advance_stage(installation.name, code)
	return frappe.get_doc("Solar Installation", installation.name)


def capture_serials(installation, modules=6, inverters=1):
	doc = frappe.get_doc("Solar Installation", installation.name)
	prefix = frappe.generate_hash(length=6).upper()
	for i in range(modules):
		doc.append(
			"serials",
			{
				"component_type": "Module",
				"serial_no": f"{prefix}-M{i:03d}",
				"manufacturer": "Rayzon",
				"wattage": 550,
			},
		)
	for i in range(inverters):
		doc.append(
			"serials",
			{"component_type": "Inverter", "serial_no": f"{prefix}-I{i:03d}", "manufacturer": "Solinteg"},
		)
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return doc
