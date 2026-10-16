# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A micro-inverter system has no DCDB (api/microinverter.py). What was recorded before the
rule says 1: on micro-inverter packages, on the designs and projects priced with a micro
inverter, and on those projects' open Material Procurement lists, the DCDB is made 0."""

import frappe

from a3_sola.api.microinverter import MICROINVERTER, is_dcdb


def execute():
	frappe.db.sql("""update `tabSolar Package System Item` si join `tabSolar Package` p on p.name = si.parent
		set si.qty = 0 where si.parenttype = 'Solar Package' and si.system_type = 'DCDB'
		and p.inverter_topology = %s""", MICROINVERTER)

	micro = frappe.get_all("Component Technology", filters={"technology_name": MICROINVERTER}, pluck="name")
	if not micro:
		return
	for parenttype in ("Solar Design Estimate", "Solar Installation"):
		parents = set(frappe.get_all("Design Estimate Inverter", filters={"parenttype": parenttype,
			"is_option": 0, "inverter_type": ["in", micro]}, pluck="parent"))
		for parent in parents:
			for row in frappe.get_all("Design Estimate BOS Item", filters={"parenttype": parenttype, "parent": parent},
					fields=["name", "item"]):
				if is_dcdb(row.item):
					frappe.db.set_value("Design Estimate BOS Item", row.name, {"numbers": 0, "amount": 0}, update_modified=False)
			if parenttype != "Solar Installation":
				continue
			for task in frappe.get_all("Installation Task", filters={"solar_installation": parent, "task_code": "PROC",
					"status": ["!=", "Completed"], "docstatus": ["<", 2]}, pluck="name"):
				for line in frappe.get_all("Installation Task Material", filters={"parent": task, "parenttype": "Installation Task"},
						fields=["name", "material"]):
					if is_dcdb(line.material):
						frappe.db.set_value("Installation Task Material", line.name, "qty", 0, update_modified=False)
