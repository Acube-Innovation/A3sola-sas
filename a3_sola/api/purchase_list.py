# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The purchase list a procurement task sends out - Material Procurement's material,
Structure Material Procurement's structure - its own list as edited on the task, under who
is billed (the company) and where it goes (the customer, with a map link to the site), as
the team's own purchase lists are laid out.
"""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, today

from a3_sola.api import documents


def url(task):
	return "/api/method/a3_sola.api.purchase_list.pdf?task=" + frappe.utils.quote(task)


def location(inst):
	"""(lat, lng) of the site: the project's, else its consumer's."""
	lat, lng = flt(inst.get("latitude")), flt(inst.get("longitude"))
	if not (lat or lng) and inst.get("solar_consumer"):
		c = frappe.db.get_value("Solar Consumer", inst.solar_consumer, ["latitude", "longitude"], as_dict=True) or {}
		lat, lng = flt(c.get("latitude")), flt(c.get("longitude"))
	return (lat, lng) if (lat or lng) else None


#: What each procurement task's purchase list is headed.
TITLES = {"SPROC": "Structure Material", "PROC": "Material"}


def lines(task):
	"""{title, bom, rows}: the task's own material list, as edited on it - the structure's on
	Structure Material Procurement, the package BOM's on Material Procurement."""
	from a3_sola.api.structure_bom import MATERIAL_LISTS

	table, bom_field = MATERIAL_LISTS[task.task_code]
	# What was written on the task goes out with the list: its Remarks, and the structure
	# task's Notes.
	notes = [(task.get(f) or "").strip() for f in (("structure_notes", "remarks") if task.task_code == "SPROC" else ("remarks",))]
	return {
		"title": TITLES[task.task_code], "bom": task.get(bom_field),
		"rows": [{"material": r.material, "uom": r.uom, "qty": flt(r.qty)} for r in task.get(table) or []],
		"remarks": [n for n in notes if n],
	}


@frappe.whitelist()
def pdf(task):
	doc = frappe.get_doc("Installation Task", task)
	doc.check_permission("read")
	if doc.task_code not in TITLES:
		frappe.throw(_("A purchase list is printed from the material and structure material procurement tasks."))
	inst = frappe.get_doc("Solar Installation", doc.solar_installation)
	company = frappe.get_doc("Company", inst.company)
	address = frappe.get_doc("Address", inst.installation_address) if inst.get("installation_address") else None
	point = location(inst)
	system = " · ".join(filter(None, [
		"{0:g} kW".format(flt(inst.capacity_kw)) if flt(inst.capacity_kw) else "",
		inst.get("connection_type"), inst.get("system_type"),
	]))
	html = frappe.render_template("a3_sola/templates/print/purchase_list.html", {
		"company": company, "inst": inst, "task": doc, "system": system,
		"ship_address": documents._address_text(address) if address else documents._party_address(None, inst),
		"point": point, "map_url": documents.maps_link(*point) if point else "",
		"date": formatdate(today(), "dd-MM-yyyy"), **lines(doc),
	})
	frappe.local.response.filename = "Purchase List - {0} - {1}.pdf".format(inst.consumer_name or inst.name, doc.name)
	frappe.local.response.filecontent = documents.plain_pdf(html)
	frappe.local.response.type = "download"
