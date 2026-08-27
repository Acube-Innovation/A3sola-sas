# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sales Order to Solar Installation.

Phase 2 is a module in this same app, not a separate app, so this is a direct call - there
is no stub, no feature-flag indirection and no cross-app import pattern. Phase 1's logging
stub has been replaced by `create_solar_installation` below.

`build_handoff_payload` remains the single contract describing what Operations needs from
CRM. Phase 3 reads the created installation, not this payload.
"""

import frappe
from frappe.utils import flt

from a3_sola.api.settings import get_value


def build_handoff_payload(sales_order):
	"""Everything Phase 2 needs to open a Solar Installation from a Sales Order."""
	so = frappe.get_doc("Sales Order", sales_order) if isinstance(sales_order, str) else sales_order
	quotation = None
	for item in so.items:
		if item.prevdoc_docname:
			quotation = item.prevdoc_docname
			break
	if not quotation:
		return None

	q = frappe.get_doc("Quotation", quotation)
	if not q.get("solar_consumer"):
		return None

	estimate = frappe.get_doc("Solar Design Estimate", q.solar_design_estimate) if q.solar_design_estimate else None
	consumer = frappe.get_doc("Solar Consumer", q.solar_consumer)

	return {
		"sales_order": so.name,
		"quotation": q.name,
		"company": so.company,
		"solar_consumer": consumer.name,
		"customer": so.customer,
		"solar_design_estimate": q.solar_design_estimate,
		"subsidy_eligibility_check": q.get("subsidy_eligibility_check"),
		"solar_proposal": q.get("solar_proposal"),
		"selected_option": q.get("selected_option"),
		"solar_package": q.get("solar_package"),
		"capacity_kw": flt(q.get("capacity_kw")),
		"subsidy_scheme": q.get("subsidy_scheme"),
		"expected_subsidy_amount": flt(q.get("expected_subsidy_to_customer")),
		"gross_contract_value": flt(so.grand_total),
		"net_payable_by_customer": flt(q.get("net_payable_by_customer")),
		"installation_address": consumer.installation_address,
		"discom": consumer.discom,
		"discom_section": consumer.discom_section,
		"consumer_number": consumer.consumer_number,
		"connection_type": consumer.connection_type,
		"net_meter_mode": estimate.net_meter_mode if estimate else None,
		"statutory": {
			"kseb_application_fee": flt(q.get("kseb_application_fee")),
			"kseb_registration_fee": flt(q.get("kseb_registration_fee")),
			"kseb_registration_refundable": flt(q.get("kseb_registration_refundable")),
			"net_meter_charge": flt(q.get("net_meter_charge")),
			"statutory_total": flt(q.get("statutory_total")),
		},
		"finance": {
			"is_financed": bool(q.get("is_financed")),
			"lender": q.get("lender"),
			"lender_branch": q.get("lender_branch"),
			"loan_scheme": q.get("loan_scheme"),
			"jan_samarth_id": q.get("jan_samarth_id"),
			"loan_sanction_no": q.get("loan_sanction_no"),
			"sanctioned_amount": flt(q.get("sanctioned_amount")),
		},
	}


def create_solar_installation(sales_order):
	"""Create the Solar Installation for a confirmed solar Sales Order.

	Strictly idempotent: re-submitting or amending a Sales Order returns the existing
	installation rather than creating a second. Missing Phase 1 links raise a clear error
	naming what is absent, rather than producing a half-populated record that fails three
	stages later.
	"""
	from frappe import _

	from a3_sola.api import stages

	payload = build_handoff_payload(sales_order)
	if not payload:
		return None

	existing = frappe.db.get_value(
		"Solar Installation",
		{"sales_order": payload["sales_order"], "docstatus": ["<", 2]},
		"name",
	)
	if existing:
		return existing

	missing = [
		label
		for label, value in (
			(_("Solar Consumer"), payload["solar_consumer"]),
			(_("Design Estimate"), payload["solar_design_estimate"]),
			(_("Capacity"), payload["capacity_kw"]),
		)
		if not value
	]
	if missing:
		frappe.throw(
			_("Sales Order {0} cannot open an installation: {1} missing on the source quotation.").format(
				payload["sales_order"], ", ".join(missing)
			),
			title=_("Incomplete Handoff"),
		)

	consumer = frappe.get_cached_doc("Solar Consumer", payload["solar_consumer"])
	package = (
		frappe.get_cached_doc("Solar Package", payload["solar_package"])
		if payload["solar_package"]
		else None
	)
	template = stages.resolve_template(
		payload["subsidy_scheme"],
		package.system_type if package else None,
		consumer.consumer_category,
		payload["company"],
	)

	installation = frappe.get_doc(
		{
			"doctype": "Solar Installation",
			"company": payload["company"],
			"solar_consumer": payload["solar_consumer"],
			"customer": payload["customer"],
			"sales_order": payload["sales_order"],
			"quotation": payload["quotation"],
			"solar_design_estimate": payload["solar_design_estimate"],
			"subsidy_eligibility_check": payload["subsidy_eligibility_check"],
			"solar_proposal": payload["solar_proposal"],
			"solar_package": payload["solar_package"],
			"capacity_kw": payload["capacity_kw"],
			"system_type": package.system_type if package else "On-Grid",
			"is_dcr_compliant": package.is_dcr_compliant if package else 0,
			"module_make": package.module_make if package else None,
			"module_wattage": package.module_wattage if package else None,
			"module_count": package.module_count if package else None,
			"inverter_make": package.inverter_1_make if package else None,
			"inverter_capacity_kw": package.inverter_1_capacity_kw if package else None,
			"installation_address": payload["installation_address"],
			"discom": payload["discom"],
			"discom_section": payload["discom_section"],
			"consumer_number": payload["consumer_number"],
			"connection_type": payload["connection_type"],
			"roof_type": consumer.roof_type,
			"latitude": consumer.latitude,
			"longitude": consumer.longitude,
			"subsidy_scheme": payload["subsidy_scheme"],
			"expected_subsidy_amount": payload["expected_subsidy_amount"],
			"gross_contract_value": payload["gross_contract_value"],
			"net_payable_by_customer": payload["net_payable_by_customer"],
			"net_meter_mode": payload["net_meter_mode"] or "Purchased by Customer",
			"company_funds_subsidy_gap": get_value("company_carries_subsidy_gap") or 0,
			"is_financed": 1 if payload["finance"]["is_financed"] else 0,
			"lender": payload["finance"]["lender"],
			"lender_branch": payload["finance"]["lender_branch"],
			"jan_samarth_id": payload["finance"]["jan_samarth_id"],
			"loan_sanction_no": payload["finance"]["loan_sanction_no"],
			"sanctioned_amount": payload["finance"]["sanctioned_amount"],
			"stage_template": template,
			"order_date": frappe.db.get_value("Sales Order", payload["sales_order"], "transaction_date"),
			"project_manager": frappe.session.user,
		}
	)
	installation.flags.ignore_permissions = True
	installation.insert(ignore_permissions=True)
	installation.submit()

	frappe.db.set_value(
		"Sales Order", payload["sales_order"], "solar_installation", installation.name, update_modified=False
	)
	return installation.name
