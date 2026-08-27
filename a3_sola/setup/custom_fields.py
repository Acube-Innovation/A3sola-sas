# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Custom fields on standard ERPNext doctypes.

Delivered as fixtures from a3_sola. Nothing here modifies a file inside the erpnext app.
Every field carries module="Solar CRM" so `bench export-fixtures` stays module-scoped.
"""

MODULE = "Solar CRM"
CATEGORY = "Residential\nGroup Housing\nCommercial\nIndustrial\nGovernment"
CADENCE = (
	"Step 1: First Contact\nStep 2: 24hr Nudge\nStep 3: Value/ROI\n"
	"Step 4: Breakup/Close\nCompleted: Proposal Sent"
)
LEAD_STATUS = (
	"New\nContacted\nIn Discussion\nSite Visit Scheduled\nConverted / Won\n"
	"Closed / Unresponsive\nNot Interested"
)

CUSTOM_FIELDS = {
	# ------------------------------------------------------------------ Company
	"Company": [
		{
			"fieldname": "a3s_registered_vendor_sb",
			"fieldtype": "Section Break",
			"label": "Registered Portal Vendor",
			"insert_after": "date_of_incorporation",
			"collapsible": 1,
			"description": (
				"The entity registered as the vendor on the national portal and named on DISCOM "
				"and bank paperwork. Often not the same entity that issues the proposal."
			),
		},
		{"fieldname": "registered_vendor_name", "fieldtype": "Data", "label": "Registered Vendor Name", "insert_after": "a3s_registered_vendor_sb"},
		{"fieldname": "registered_vendor_address", "fieldtype": "Small Text", "label": "Registered Vendor Address", "insert_after": "registered_vendor_name"},
		{"fieldname": "mnre_vendor_registration_no", "fieldtype": "Data", "label": "MNRE Vendor Registration No", "insert_after": "registered_vendor_address"},
		{"fieldname": "a3s_registered_vendor_cb", "fieldtype": "Column Break", "insert_after": "mnre_vendor_registration_no"},
		{"fieldname": "national_portal_vendor_id", "fieldtype": "Data", "label": "National Portal Vendor ID", "insert_after": "a3s_registered_vendor_cb"},
		{"fieldname": "registered_vendor_contact", "fieldtype": "Data", "label": "Registered Vendor Contact", "insert_after": "national_portal_vendor_id"},
		{"fieldname": "registered_vendor_email", "fieldtype": "Data", "label": "Registered Vendor Email", "insert_after": "registered_vendor_contact"},

		{"fieldname": "a3s_epc_sb", "fieldtype": "Section Break", "label": "Executing EPC", "insert_after": "registered_vendor_email", "collapsible": 1},
		{"fieldname": "epc_name", "fieldtype": "Data", "label": "EPC Name", "insert_after": "a3s_epc_sb"},
		{"fieldname": "epc_address", "fieldtype": "Small Text", "label": "EPC Address", "insert_after": "epc_name"},
		{"fieldname": "epc_contact_no", "fieldtype": "Data", "label": "EPC Contact No", "insert_after": "epc_address"},
		{"fieldname": "epc_email", "fieldtype": "Data", "label": "EPC Email", "insert_after": "epc_contact_no"},
		{"fieldname": "a3s_epc_cb", "fieldtype": "Column Break", "insert_after": "epc_email"},
		{"fieldname": "epc_authorised_signatory", "fieldtype": "Data", "label": "Authorised Signatory", "insert_after": "a3s_epc_cb"},
		{"fieldname": "epc_signatory_designation", "fieldtype": "Data", "label": "Signatory Designation", "insert_after": "epc_authorised_signatory"},
		{"fieldname": "epc_signature_image", "fieldtype": "Attach Image", "label": "Signature Image", "insert_after": "epc_signatory_designation"},
		{"fieldname": "company_stamp_image", "fieldtype": "Attach Image", "label": "Company Stamp", "insert_after": "epc_signature_image"},

		{"fieldname": "a3s_payee_sb", "fieldtype": "Section Break", "label": "Payee Bank", "insert_after": "company_stamp_image", "collapsible": 1},
		{"fieldname": "payee_legal_name", "fieldtype": "Data", "label": "Payee Legal Name", "insert_after": "a3s_payee_sb"},
		{"fieldname": "payee_pan", "fieldtype": "Data", "label": "PAN", "insert_after": "payee_legal_name"},
		{"fieldname": "payee_gstin", "fieldtype": "Data", "label": "GSTIN", "insert_after": "payee_pan"},
		{"fieldname": "payee_bank_name", "fieldtype": "Data", "label": "Bank", "insert_after": "payee_gstin"},
		{"fieldname": "a3s_payee_cb", "fieldtype": "Column Break", "insert_after": "payee_bank_name"},
		{"fieldname": "payee_bank_account_no", "fieldtype": "Data", "label": "Account Number", "insert_after": "a3s_payee_cb"},
		{"fieldname": "payee_bank_branch", "fieldtype": "Data", "label": "Branch", "insert_after": "payee_bank_account_no"},
		{"fieldname": "payee_bank_ifsc", "fieldtype": "Data", "label": "IFSC Code", "insert_after": "payee_bank_branch"},
		{"fieldname": "payment_qr_code", "fieldtype": "Attach Image", "label": "Payment QR Code", "insert_after": "payee_bank_ifsc"},
	],
	# --------------------------------------------------------------------- Item
	"Item": [
		{
			"fieldname": "is_dcr",
			"fieldtype": "Check",
			"label": "Is DCR (Domestic Content Requirement)",
			"insert_after": "is_fixed_asset",
			"description": "Set on solar modules manufactured in India to DCR standard. Required by subsidy schemes.",
		},
		{"fieldname": "dcr_certificate_no", "fieldtype": "Data", "label": "DCR Certificate No", "insert_after": "is_dcr", "depends_on": "eval:doc.is_dcr"},
	],
	# --------------------------------------------------------------------- Lead
	"Lead": [
		{"fieldname": "a3s_solar_sb", "fieldtype": "Section Break", "label": "Solar Details", "insert_after": "type", "collapsible": 1},
		{"fieldname": "subsidy_scheme", "fieldtype": "Link", "options": "Subsidy Scheme", "label": "Subsidy Scheme", "insert_after": "a3s_solar_sb"},
		{"fieldname": "discom", "fieldtype": "Link", "options": "DISCOM", "label": "DISCOM", "insert_after": "subsidy_scheme"},
		{"fieldname": "discom_section", "fieldtype": "Link", "options": "DISCOM Section", "label": "DISCOM Section", "insert_after": "discom"},
		{"fieldname": "consumer_number", "fieldtype": "Data", "label": "Consumer Number", "insert_after": "discom_section"},
		{"fieldname": "consumer_category", "fieldtype": "Select", "options": CATEGORY, "default": "Residential", "label": "Consumer Category", "insert_after": "consumer_number"},
		{"fieldname": "connection_type", "fieldtype": "Select", "options": "\nSingle Phase\nThree Phase", "label": "Connection Type", "insert_after": "consumer_category"},
		{"fieldname": "a3s_solar_cb", "fieldtype": "Column Break", "insert_after": "connection_type"},
		{"fieldname": "roof_type", "fieldtype": "Link", "options": "Roof Type", "label": "Roof Type", "insert_after": "a3s_solar_cb"},
		{"fieldname": "approx_consumption_units", "fieldtype": "Float", "label": "Approx Units per Cycle", "insert_after": "roof_type"},
		{"fieldname": "avg_monthly_bill", "fieldtype": "Currency", "label": "Avg Monthly Bill", "insert_after": "approx_consumption_units", "in_list_view": 1},
		{"fieldname": "approx_capacity_kw", "fieldtype": "Float", "label": "Proposed System Size (kW)", "insert_after": "avg_monthly_bill", "precision": "3", "in_list_view": 1},
		{"fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "label": "Solar Consumer", "insert_after": "approx_capacity_kw", "read_only": 1},
		{"fieldname": "solar_proposal", "fieldtype": "Link", "options": "Solar Proposal", "label": "Solar Proposal", "insert_after": "solar_consumer", "read_only": 1},

		{
			"fieldname": "a3s_outreach_sb",
			"fieldtype": "Section Break",
			"label": "Outreach",
			"insert_after": "solar_proposal",
			"description": (
				"Call status, cadence step and lead status are three separate dimensions. A lead "
				"can be at step 3 of the cadence while the last call went unanswered, and that "
				"combination is exactly what the sales manager needs to see."
			),
		},
		{"fieldname": "call_status", "fieldtype": "Select", "options": "\nNot Answered\nBusy\nSwitched Off\nConnected", "label": "Call Status", "insert_after": "a3s_outreach_sb", "in_standard_filter": 1},
		{"fieldname": "outreach_stage", "fieldtype": "Select", "options": "\n" + CADENCE, "label": "Outreach Stage", "insert_after": "call_status", "in_standard_filter": 1},
		{"fieldname": "solar_lead_status", "fieldtype": "Select", "options": "\n" + LEAD_STATUS, "label": "Lead Status", "insert_after": "outreach_stage", "in_standard_filter": 1, "in_list_view": 1},
		{"fieldname": "a3s_outreach_cb", "fieldtype": "Column Break", "insert_after": "solar_lead_status"},
		{"fieldname": "last_message_date", "fieldtype": "Date", "label": "Last Message Date", "insert_after": "a3s_outreach_cb"},
		{"fieldname": "next_followup_date", "fieldtype": "Date", "label": "Next Follow-up Date", "insert_after": "last_message_date", "in_list_view": 1},
		{
			"fieldname": "followup_status",
			"fieldtype": "Select",
			"options": "OK\nFOLLOW UP DUE",
			"default": "OK",
			"label": "Follow-up Status",
			"insert_after": "next_followup_date",
			"read_only": 1,
			"in_standard_filter": 1,
			"description": "Computed daily. Never editable.",
		},
		{"fieldname": "consecutive_non_connects", "fieldtype": "Int", "label": "Consecutive Non-Connects", "insert_after": "followup_status", "read_only": 1},
		{"fieldname": "a3s_outreach_log_sb", "fieldtype": "Section Break", "label": "Outreach Log", "insert_after": "consecutive_non_connects"},
		{"fieldname": "outreach_log", "fieldtype": "Table", "options": "Outreach Log", "label": "Outreach Log", "insert_after": "a3s_outreach_log_sb"},
		{"fieldname": "outreach_notes", "fieldtype": "Small Text", "label": "Notes / Remarks", "insert_after": "outreach_log"},
	],
	# -------------------------------------------------------------- Opportunity
	"Opportunity": [
		{"fieldname": "a3s_solar_sb", "fieldtype": "Section Break", "label": "Solar Details", "insert_after": "opportunity_type", "collapsible": 1},
		{"fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "label": "Solar Consumer", "insert_after": "a3s_solar_sb"},
		{"fieldname": "subsidy_scheme", "fieldtype": "Link", "options": "Subsidy Scheme", "label": "Subsidy Scheme", "insert_after": "solar_consumer"},
		{"fieldname": "solar_design_estimate", "fieldtype": "Link", "options": "Solar Design Estimate", "label": "Design Estimate", "insert_after": "subsidy_scheme"},
		{"fieldname": "a3s_solar_cb", "fieldtype": "Column Break", "insert_after": "solar_design_estimate"},
		{"fieldname": "capacity_kw", "fieldtype": "Float", "label": "Capacity (kW)", "insert_after": "a3s_solar_cb", "precision": "3"},
		{"fieldname": "expected_subsidy_amount", "fieldtype": "Currency", "label": "Expected Subsidy", "insert_after": "capacity_kw", "read_only": 1},
		{"fieldname": "net_customer_outflow", "fieldtype": "Currency", "label": "Net Customer Outflow", "insert_after": "expected_subsidy_amount", "read_only": 1},
	],
	# ---------------------------------------------------------------- Quotation
	"Quotation": [
		{"fieldname": "a3s_solar_sb", "fieldtype": "Section Break", "label": "Solar Details", "insert_after": "order_type", "collapsible": 1},
		{"fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "label": "Solar Consumer", "insert_after": "a3s_solar_sb"},
		{"fieldname": "solar_design_estimate", "fieldtype": "Link", "options": "Solar Design Estimate", "label": "Design Estimate", "insert_after": "solar_consumer"},
		{"fieldname": "selected_option", "fieldtype": "Data", "label": "Selected Option", "insert_after": "solar_design_estimate", "description": "The Design Estimate Option the customer chose. Mandatory when the estimate quotes more than one."},
		{"fieldname": "subsidy_eligibility_check", "fieldtype": "Link", "options": "Subsidy Eligibility Check", "label": "Eligibility Check", "insert_after": "selected_option"},
		{"fieldname": "solar_proposal", "fieldtype": "Link", "options": "Solar Proposal", "label": "Solar Proposal", "insert_after": "subsidy_eligibility_check"},
		{"fieldname": "a3s_solar_cb", "fieldtype": "Column Break", "insert_after": "solar_proposal"},
		{"fieldname": "subsidy_scheme", "fieldtype": "Link", "options": "Subsidy Scheme", "label": "Subsidy Scheme", "insert_after": "a3s_solar_cb", "read_only": 1},
		{"fieldname": "solar_package", "fieldtype": "Link", "options": "Solar Package", "label": "Solar Package", "insert_after": "subsidy_scheme"},
		{"fieldname": "capacity_kw", "fieldtype": "Float", "label": "Capacity (kW)", "insert_after": "solar_package", "read_only": 1, "precision": "3"},
		{"fieldname": "gross_amount", "fieldtype": "Currency", "label": "Gross Amount", "insert_after": "capacity_kw", "read_only": 1},
		{
			"fieldname": "expected_subsidy_to_customer",
			"fieldtype": "Currency",
			"label": "Expected Government Subsidy to Customer",
			"insert_after": "gross_amount",
			"read_only": 1,
			"description": (
				"DISPLAY ONLY. Paid by the government directly to the customer's bank account after "
				"commissioning. It is never our revenue or our liability, and it must never appear "
				"in the items table, the taxes table, or as a discount."
			),
		},
		{"fieldname": "net_payable_by_customer", "fieldtype": "Currency", "label": "Net Payable by Customer", "insert_after": "expected_subsidy_to_customer", "read_only": 1},
		{"fieldname": "estimated_annual_savings", "fieldtype": "Currency", "label": "Estimated Annual Savings", "insert_after": "net_payable_by_customer", "read_only": 1},
		{"fieldname": "simple_payback_years", "fieldtype": "Float", "label": "Simple Payback (years)", "insert_after": "estimated_annual_savings", "read_only": 1, "precision": "2"},

		{
			"fieldname": "a3s_statutory_sb",
			"fieldtype": "Section Break",
			"label": "Statutory & Net Meter",
			"insert_after": "simple_payback_years",
			"collapsible": 1,
			"description": (
				"A reimbursement, not revenue. These never enter the items or taxes tables - they "
				"print as a separate advisory block, exactly as the client's proposal prints its "
				"KSEBL Expenses table below the project cost."
			),
		},
		{"fieldname": "net_meter_mode", "fieldtype": "Select", "options": "\nPurchased by Customer\nAvailed from DISCOM on Rental", "label": "Net Meter Mode", "insert_after": "a3s_statutory_sb", "read_only": 1},
		{"fieldname": "kseb_application_fee", "fieldtype": "Currency", "label": "Application Fee", "insert_after": "net_meter_mode", "read_only": 1},
		{"fieldname": "kseb_registration_fee", "fieldtype": "Currency", "label": "Registration Fee", "insert_after": "kseb_application_fee", "read_only": 1},
		{"fieldname": "a3s_statutory_cb", "fieldtype": "Column Break", "insert_after": "kseb_registration_fee"},
		{"fieldname": "kseb_registration_refundable", "fieldtype": "Currency", "label": "Registration Refundable", "insert_after": "a3s_statutory_cb", "read_only": 1},
		{"fieldname": "net_meter_charge", "fieldtype": "Currency", "label": "Net Meter Charge", "insert_after": "kseb_registration_refundable", "read_only": 1},
		{"fieldname": "statutory_total", "fieldtype": "Currency", "label": "Statutory Total", "insert_after": "net_meter_charge", "read_only": 1},

		{"fieldname": "a3s_finance_sb", "fieldtype": "Section Break", "label": "Finance", "insert_after": "statutory_total", "collapsible": 1},
		{"fieldname": "is_financed", "fieldtype": "Check", "label": "Financed", "insert_after": "a3s_finance_sb"},
		{"fieldname": "lender", "fieldtype": "Data", "label": "Lender", "insert_after": "is_financed", "depends_on": "eval:doc.is_financed"},
		{"fieldname": "lender_branch", "fieldtype": "Data", "label": "Branch", "insert_after": "lender", "depends_on": "eval:doc.is_financed"},
		{"fieldname": "loan_scheme", "fieldtype": "Select", "options": "\nPM Surya Ghar via Jan Samarth\nBank Own Scheme\nOther", "label": "Loan Scheme", "insert_after": "lender_branch", "depends_on": "eval:doc.is_financed"},
		{"fieldname": "a3s_finance_cb", "fieldtype": "Column Break", "insert_after": "loan_scheme"},
		{"fieldname": "jan_samarth_id", "fieldtype": "Data", "label": "Jan Samarth ID", "insert_after": "a3s_finance_cb", "depends_on": "eval:doc.is_financed"},
		{"fieldname": "loan_sanction_no", "fieldtype": "Data", "label": "Loan Sanction No", "insert_after": "jan_samarth_id", "depends_on": "eval:doc.is_financed"},
		{"fieldname": "sanctioned_amount", "fieldtype": "Currency", "label": "Sanctioned Amount", "insert_after": "loan_sanction_no", "depends_on": "eval:doc.is_financed"},
		{
			"fieldname": "finance_status",
			"fieldtype": "Select",
			"options": "Not Applied\nApplied\nSanctioned\nRejected\nDisbursed (Advance)\nDisbursed (Full)",
			"default": "Not Applied",
			"label": "Finance Status",
			"insert_after": "sanctioned_amount",
			"depends_on": "eval:doc.is_financed",
		},
	],
	# --------------------------------------------------------------- Sales Order
	"Sales Order": [
		{"fieldname": "a3s_solar_sb", "fieldtype": "Section Break", "label": "Solar Details", "insert_after": "order_type", "collapsible": 1},
		{"fieldname": "solar_consumer", "fieldtype": "Link", "options": "Solar Consumer", "label": "Solar Consumer", "insert_after": "a3s_solar_sb", "read_only": 1},
	],
}
