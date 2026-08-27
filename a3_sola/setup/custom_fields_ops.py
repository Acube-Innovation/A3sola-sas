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
		}
	],
}
