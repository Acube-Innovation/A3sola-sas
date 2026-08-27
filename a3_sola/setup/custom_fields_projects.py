# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Custom fields for Solar Projects.

The Project extension carries the solar context, the commercials and the costing. Every
Currency field sits at permlevel 1: a service technician must never see contract value,
margin or provision.
"""

MODULE = "Solar Projects"


def _pl1(fieldname, label, insert_after, fieldtype="Currency", **kwargs):
	field = {
		"fieldname": fieldname,
		"fieldtype": fieldtype,
		"label": label,
		"insert_after": insert_after,
		"permlevel": 1,
	}
	field.update(kwargs)
	return field


CUSTOM_FIELDS = {
	"Project": [
		# --------------------------------------------------------- solar context
		{"fieldname": "a3s_solar_sb", "fieldtype": "Section Break", "label": "Solar Details",
		 "insert_after": "project_type", "collapsible": 1},
		{"fieldname": "solar_installation", "fieldtype": "Link", "options": "Solar Installation",
		 "label": "Solar Installation", "insert_after": "a3s_solar_sb", "read_only": 1},
		{"fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer",
		 "label": "Solar Consumer", "insert_after": "solar_installation"},
		{"fieldname": "capacity_kw", "fieldtype": "Float", "label": "Capacity (kW)",
		 "insert_after": "solar_consumer", "precision": "3"},
		{"fieldname": "solar_package", "fieldtype": "Link", "options": "Solar Package",
		 "label": "Solar Package", "insert_after": "capacity_kw"},
		{"fieldname": "a3s_solar_cb", "fieldtype": "Column Break", "insert_after": "solar_package"},
		{"fieldname": "commissioning_date", "fieldtype": "Date", "label": "Commissioning Date",
		 "insert_after": "a3s_solar_cb"},
		{"fieldname": "warranty_start_date", "fieldtype": "Date", "label": "Warranty Start",
		 "insert_after": "commissioning_date"},
		{"fieldname": "warranty_end_date", "fieldtype": "Date", "label": "Warranty End",
		 "insert_after": "warranty_start_date"},
		{"fieldname": "subsidy_scheme", "fieldtype": "Link", "options": "Subsidy Scheme",
		 "label": "Subsidy Scheme", "insert_after": "warranty_end_date"},
		{"fieldname": "discom", "fieldtype": "Link", "options": "DISCOM", "label": "DISCOM",
		 "insert_after": "subsidy_scheme"},
		{"fieldname": "discom_section", "fieldtype": "Link", "options": "DISCOM Section",
		 "label": "DISCOM Section", "insert_after": "discom"},

		# ----------------------------------------------------------- commercials
		{"fieldname": "a3s_commercials_sb", "fieldtype": "Section Break",
		 "label": "Solar Commercials", "insert_after": "discom_section", "collapsible": 1,
		 "permlevel": 1},
		_pl1("gross_contract_value", "Contract Value", "a3s_commercials_sb"),
		_pl1("expected_subsidy_amount", "Expected Subsidy", "gross_contract_value"),
		_pl1("net_payable_by_customer", "Net Payable by Customer", "expected_subsidy_amount"),
		_pl1("subsidy_receivable_amount", "Subsidy Receivable", "net_payable_by_customer", read_only=1),
		{"fieldname": "a3s_commercials_cb", "fieldtype": "Column Break",
		 "insert_after": "subsidy_receivable_amount", "permlevel": 1},
		_pl1("total_billed_amount", "Billed", "a3s_commercials_cb", read_only=1),
		_pl1("total_collected_amount", "Collected", "total_billed_amount", read_only=1),
		_pl1("outstanding_amount", "Outstanding", "total_collected_amount", read_only=1),
		_pl1("om_provision_amount", "O&M Provision", "outstanding_amount", read_only=1),
		_pl1("om_provision_released", "Provision Released", "om_provision_amount", read_only=1),

		# --------------------------------------------------------------- costing
		{"fieldname": "a3s_costing_sb", "fieldtype": "Section Break", "label": "Solar Costing",
		 "insert_after": "om_provision_released", "collapsible": 1, "permlevel": 1},
		_pl1("material_cost", "Material", "a3s_costing_sb", read_only=1),
		_pl1("labour_cost", "Labour", "material_cost", read_only=1),
		_pl1("subcontractor_cost", "Subcontractor", "labour_cost", read_only=1),
		_pl1("logistics_cost", "Logistics", "subcontractor_cost", read_only=1),
		_pl1("liaison_and_statutory_cost", "Liaison", "logistics_cost", read_only=1),
		_pl1("rework_cost", "Rework", "liaison_and_statutory_cost", read_only=1,
		     description="Isolated deliberately - it is the client's quality-cost signal."),
		_pl1("om_cost_to_date", "O&M to Date", "rework_cost", read_only=1),
		{"fieldname": "a3s_costing_cb", "fieldtype": "Column Break",
		 "insert_after": "om_cost_to_date", "permlevel": 1},
		_pl1("total_direct_cost", "Direct Cost", "a3s_costing_cb", read_only=1),
		_pl1("overhead_allocated", "Overhead", "total_direct_cost", read_only=1),
		_pl1("total_cost", "Total Cost", "overhead_allocated", read_only=1),
		_pl1("gross_margin_amount", "Gross Margin", "total_cost", read_only=1),
		_pl1("gross_margin_percent", "Margin %", "gross_margin_amount", fieldtype="Percent",
		     read_only=1),
		_pl1("cost_per_kw", "Cost per kW", "gross_margin_percent", read_only=1),
		_pl1("margin_per_kw", "Margin per kW", "cost_per_kw", read_only=1),
		_pl1("quoted_margin_percent", "Quoted Margin %", "margin_per_kw", fieldtype="Percent",
		     read_only=1,
		     description="From the Phase 1 design estimate. The variance closes the loop "
		                 "between what sales promised and what operations delivered."),
		_pl1("margin_variance_percent", "Margin Variance %", "quoted_margin_percent",
		     fieldtype="Percent", read_only=1),
		_pl1("statutory_pass_through", "Statutory (pass-through)", "margin_variance_percent",
		     read_only=1,
		     description="Excluded from cost and margin - recovered from the customer "
		                 "against receipts."),

		{"fieldname": "a3s_cost_entries_sb", "fieldtype": "Section Break",
		 "label": "Cost Entries", "insert_after": "statutory_pass_through", "permlevel": 1,
		 "collapsible": 1},
		{"fieldname": "cost_entries", "fieldtype": "Table", "options": "Project Cost Entry",
		 "label": "Cost Entries", "insert_after": "a3s_cost_entries_sb", "permlevel": 1,
		 "read_only": 1},
	],
	"Sales Invoice": [
		{"fieldname": "a3s_solar_sb", "fieldtype": "Section Break", "label": "Solar",
		 "insert_after": "project", "collapsible": 1},
		{"fieldname": "solar_billing_plan", "fieldtype": "Link", "options": "Solar Billing Plan",
		 "label": "Billing Plan", "insert_after": "a3s_solar_sb", "read_only": 1},
		{"fieldname": "billing_milestone", "fieldtype": "Data", "label": "Milestone",
		 "insert_after": "solar_billing_plan", "read_only": 1},
		{"fieldname": "is_statutory_reimbursement", "fieldtype": "Check",
		 "label": "Statutory Reimbursement", "insert_after": "billing_milestone",
		 "description": "A pass-through recovered against receipts. Outside the composite supply."},
	],
	# Every posting this app makes is traceable back to the document that caused it, and
	# that trace is what makes reposting idempotent rather than duplicating a ledger entry.
	"Journal Entry": [
		{"fieldname": "a3s_solar_sb", "fieldtype": "Section Break", "label": "Solar",
		 "insert_after": "user_remark", "collapsible": 1},
		{"fieldname": "a3s_source_doctype", "fieldtype": "Link", "options": "DocType",
		 "label": "Solar Source Type", "insert_after": "a3s_solar_sb", "read_only": 1,
		 "no_copy": 1, "search_index": 1},
		{"fieldname": "a3s_source_document", "fieldtype": "Dynamic Link",
		 "options": "a3s_source_doctype", "label": "Solar Source Document",
		 "insert_after": "a3s_source_doctype", "read_only": 1, "no_copy": 1, "search_index": 1},
		{"fieldname": "a3s_purpose", "fieldtype": "Data", "label": "Solar Posting Purpose",
		 "insert_after": "a3s_source_document", "read_only": 1, "no_copy": 1,
		 "search_index": 1,
		 "description": "What this entry represents. One purpose per source document."},
	],
	"Opportunity": [
		{"fieldname": "om_contract", "fieldtype": "Link", "options": "Solar OM Contract",
		 "label": "Renewal of O&M Contract", "insert_after": "solar_design_estimate",
		 "read_only": 1},
	],
}
