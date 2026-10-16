# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Data for Completion Report laid out as the client's sheet (06_DATA FOR COMPLETION
REPORT.pdf). A template is data a tenant may have edited, so only a body still exactly as
first seeded is replaced with the new one."""

import frappe

from a3_sola.setup import seed_documents

CODE = "COMPLETION-REPORT-DATA"
OLD_BODY = '<h3 style="text-align:center;margin:0 0 10px">DATA FOR COMPLETION REPORT</h3>\n<table style="width:100%;border-collapse:collapse;font-size:12px">\n{% set cd = completion_data %}\n{% macro row(label, value) -%}\n<tr><td style="border:1px solid #444;padding:5px;width:38%"><b>{{ label }}</b></td>\n    <td style="border:1px solid #444;padding:5px">{{ value or "" }}</td></tr>\n{%- endmacro %}\n{{ row("Consumer Name", cd.consumer_name) }}\n{{ row("Address", address_text or cd.address) }}\n{{ row("Consumer Number", cd.consumer_number) }}\n{{ row("KSEB Section", cd.electrical_section) }}\n{{ row("Service Connection Type", cd.service_connection_type) }}\n{{ row("Solar Plant Capacity", cd.plant_capacity) }}\n{{ row("PV Module Make &amp; Wattage", cd.module_make_and_wattage) }}\n<tr><td style="border:1px solid #444;padding:5px;vertical-align:top"><b>PV Module Serial Numbers</b>\n    <div style="font-size:10px;color:#555">{{ cd.module_count }} modules</div></td>\n    <td style="border:1px solid #444;padding:0">\n    <table style="width:100%;border-collapse:collapse">\n    {% for serial in cd.module_serial_numbers %}\n      <tr><td style="border-bottom:1px solid #bbb;padding:3px 5px">{{ loop.index }}. {{ serial }}</td></tr>\n    {% else %}<tr><td style="padding:5px;color:#888">No module serials captured yet</td></tr>{% endfor %}\n    </table></td></tr>\n{{ row("Inverter Make &amp; Capacity", cd.inverter_make_and_capacity) }}\n{{ row("Inverter Serial Number", cd.inverter_serial_number) }}\n</table>\n{% if contractor %}<p style="font-size:11px;margin-top:10px">For: {{ contractor.contractor_name }}{% if contractor.licence_no %} · Licence {{ contractor.licence_no }}{% endif %}</p>{% endif %}\n<p style="font-size:11px">Prepared by {{ company.epc_name or company.company_name }} on {{ today }}.</p>\n'


def execute():
	frappe.reload_doc("solar_crm", "doctype", "a3_sola_settings")
	new = next(t["body"] for t in seed_documents.TEMPLATES if t["template_code"] == CODE)
	for name, body in frappe.get_all("Solar Document Template", filters={"template_code": CODE},
			fields=["name", "body_template"], as_list=True):
		if (body or "").strip() == OLD_BODY.strip():
			frappe.db.set_value("Solar Document Template", name, "body_template", new, update_modified=False)
