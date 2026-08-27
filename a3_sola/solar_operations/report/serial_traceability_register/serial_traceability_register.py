# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Serial Traceability Register.

Structured to satisfy a DCR audit request: every serial with its installation, consumer,
DISCOM, purchase receipt, delivery note and DCR certificate."""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		filters.company = frappe.defaults.get_user_default("Company")
	return get_columns(filters), get_data(filters)


def get_columns(filters):
	return [
		{"label": _("Serial No"), "fieldname": "serial_no", "fieldtype": "Data", "width": 170},
		{"label": _("Type"), "fieldname": "component_type", "fieldtype": "Data", "width": 100},
		{"label": _("Manufacturer"), "fieldname": "manufacturer", "fieldtype": "Data", "width": 130},
		{"label": _("Model"), "fieldname": "model_number", "fieldtype": "Data", "width": 150},
		{"label": _("Wattage"), "fieldname": "wattage", "fieldtype": "Float", "precision": 0, "width": 90},
		{"label": _("DCR Certificate"), "fieldname": "dcr_certificate_no", "fieldtype": "Data", "width": 150},
		{"label": _("Installation"), "fieldname": "parent", "fieldtype": "Link", "options": "Solar Installation", "width": 150},
		{"label": _("Consumer No"), "fieldname": "consumer_number", "fieldtype": "Data", "width": 130},
		{"label": _("Purchase Receipt"), "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 150},
		{"label": _("Delivery Note"), "fieldname": "delivery_note", "fieldtype": "Link", "options": "Delivery Note", "width": 150},
		{"label": _("Commissioned"), "fieldname": "warranty_start_date", "fieldtype": "Date", "width": 120},
		{"label": _("Replaced"), "fieldname": "is_replaced", "fieldtype": "Check", "width": 90},
	]


def get_data(filters):
	return frappe.db.sql(
		"""
		select reg.serial_no, reg.component_type, reg.manufacturer, reg.model_number,
		       reg.wattage, reg.dcr_certificate_no, reg.parent, reg.purchase_receipt,
		       reg.delivery_note, reg.is_replaced,
		       inst.consumer_number, inst.warranty_start_date
		from `tabInstallation Serial Register` reg
		join `tabSolar Installation` inst on inst.name = reg.parent
		where inst.company = %(company)s and inst.docstatus < 2
		order by reg.parent, reg.component_type, reg.serial_no
		""",
		{"company": filters.company},
		as_dict=True,
	)
