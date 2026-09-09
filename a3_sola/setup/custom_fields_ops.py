# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Custom fields for Solar Operations.

Every material movement is attributable to a job, so Phase 3 can cost it and the site can
be reconciled against the package BOM.
"""

MODULE = "Solar Operations"

_LINK = {
	"fieldname": "solar_installation",
	"fieldtype": "Link",
	"options": "Solar Installation",
	"label": "Solar Installation",
}

CUSTOM_FIELDS = {
	"Material Request": [dict(_LINK, insert_after="material_request_type")],
	"Stock Entry": [dict(_LINK, insert_after="stock_entry_type")],
	"Delivery Note": [dict(_LINK, insert_after="customer")],
	"Purchase Order": [dict(_LINK, insert_after="supplier")],
	"Purchase Receipt": [dict(_LINK, insert_after="supplier")],
	"Sales Invoice": [dict(_LINK, insert_after="customer")],
	"Serial No": [
		{
			"fieldname": "solar_installation",
			"fieldtype": "Link",
			"options": "Solar Installation",
			"label": "Solar Installation",
			"insert_after": "item_code",
			"read_only": 1,
		},
		{
			"fieldname": "is_dcr",
			"fieldtype": "Check",
			"label": "Is DCR",
			"insert_after": "solar_installation",
		},
		{
			"fieldname": "dcr_certificate_no",
			"fieldtype": "Data",
			"label": "DCR Certificate No",
			"insert_after": "is_dcr",
			"depends_on": "eval:doc.is_dcr",
		},
	],
	"Sales Order": [
		{
			"fieldname": "solar_installation",
			"fieldtype": "Link",
			"options": "Solar Installation",
			"label": "Solar Installation",
			"insert_after": "solar_consumer",
			"read_only": 1,
		},
		# The order is the first task, and the KYC it fetches from the consumer is its evidence.
		{"fieldname": "a3s_kyc_sb", "fieldtype": "Section Break", "label": "Customer KYC",
		 "insert_after": "solar_installation", "collapsible": 1, "depends_on": "eval:doc.solar_consumer"},
		{"fieldname": "kyc_status", "fieldtype": "Small Text", "label": "KYC Status", "insert_after": "a3s_kyc_sb",
		 "read_only": 1},
		{"fieldname": "kyc_html", "fieldtype": "HTML", "label": "KYC Documents", "insert_after": "kyc_status"},
	],
}

#: The task header every executing ERPNext document carries, so the order, the purchase
#: order and the delivery note say who was to do them, by when, and what they cost.
TASK_HEADER = [
	{"fieldname": "a3s_task_sb", "fieldtype": "Section Break", "label": "Task", "collapsible": 1},
	{"fieldname": "assigned_by", "fieldtype": "Link", "options": "User", "label": "Assigned By", "read_only": 1},
	{"fieldname": "assigned_to", "fieldtype": "Link", "options": "User", "label": "Assigned To"},
	{"fieldname": "assigned_on", "fieldtype": "Date", "label": "Assigned On", "read_only": 1},
	{"fieldname": "a3s_task_cb", "fieldtype": "Column Break"},
	{"fieldname": "task_due_date", "fieldtype": "Date", "label": "Due Date"},
	{"fieldname": "task_cost", "fieldtype": "Currency", "label": "Task Cost", "permlevel": 1},
]


def _header(after):
	rows, previous = [], after
	for spec in TASK_HEADER:
		rows.append(dict(spec, insert_after=previous))
		previous = spec["fieldname"]
	return rows


CUSTOM_FIELDS["Sales Order"] += _header("kyc_html")
CUSTOM_FIELDS["Purchase Order"] += [
	# Where the materials go: the consumer's location, captured at survey, carried to the PO.
	{"fieldname": "a3s_site_sb", "fieldtype": "Section Break", "label": "Site", "insert_after": "solar_installation",
	 "collapsible": 1, "depends_on": "eval:doc.solar_installation"},
	{"fieldname": "site_google_location", "fieldtype": "Data", "options": "URL", "label": "Site Location",
	 "insert_after": "a3s_site_sb", "read_only": 1},
	{"fieldname": "site_landmark", "fieldtype": "Data", "label": "Landmark", "insert_after": "site_google_location",
	 "read_only": 1},
	{"fieldname": "site_contact_no", "fieldtype": "Data", "label": "Site Contact", "insert_after": "site_landmark",
	 "read_only": 1},
] + _header("site_contact_no")
CUSTOM_FIELDS["Delivery Note"] += _header("solar_installation")
