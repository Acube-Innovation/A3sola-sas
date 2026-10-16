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


def url(task, download=False, pending=False):
	"""The list to open in the browser - or, with `download`, to save; with `pending`, only
	what the supplier could not give."""
	return ("/api/method/a3_sola.api.purchase_list.pdf?task=" + frappe.utils.quote(task)
		+ ("&pending=1" if pending else "") + ("&download=1" if download else ""))


def pending_rows(task):
	"""The task's list rows the supplier could not give in full (a Pending Qty)."""
	from a3_sola.api.structure_bom import MATERIAL_LISTS

	table = MATERIAL_LISTS.get(task.get("task_code"), (None,))[0]
	return [r for r in task.get(table) or [] if flt(r.get("pending_qty")) > 0] if table else []


def location(inst):
	"""(lat, lng) of the site: the project's, else its consumer's."""
	lat, lng = flt(inst.get("latitude")), flt(inst.get("longitude"))
	if not (lat or lng) and inst.get("solar_consumer"):
		c = frappe.db.get_value("Solar Consumer", inst.solar_consumer, ["latitude", "longitude"], as_dict=True) or {}
		lat, lng = flt(c.get("latitude")), flt(c.get("longitude"))
	return (lat, lng) if (lat or lng) else None


#: What each procurement task's purchase list is headed.
TITLES = {"SPROC": "Structure Material", "PROC": "Material"}


def lines(task, pending=False):
	"""{title, bom, rows}: the task's own material list, as edited on it - the structure's on
	Structure Material Procurement, the package BOM's on Material Procurement. With `pending`,
	only the rows still pending, at their pending quantities."""
	from a3_sola.api.structure_bom import MATERIAL_LISTS

	table, bom_field = MATERIAL_LISTS[task.task_code]
	# What was written on the task goes out with the list: its Remarks, and the structure
	# task's Notes.
	notes = [(task.get(f) or "").strip() for f in (("structure_notes", "remarks") if task.task_code == "SPROC" else ("remarks",))]
	# A micro-inverter job buys no DCDB: its line is 0, starred, and the note says why.
	from a3_sola.api import microinverter

	micro = task.task_code == "PROC" and task.get("solar_installation") and microinverter.uses_microinverter(task.solar_installation)
	starred = lambda r: micro and not flt(r.qty) and microinverter.is_dcdb(r.material)  # noqa: E731
	source = pending_rows(task) if pending else task.get(table) or []
	rows = [{"material": r.material + (" *" if starred(r) else ""), "uom": r.uom,
		"qty": flt(r.pending_qty) if pending else flt(r.qty)} for r in source]
	if any(starred(r) for r in task.get(table) or []):
		notes.append(microinverter.NOTE)
	return {
		"title": TITLES[task.task_code] + (" - Pending Items" if pending else ""), "pending": bool(pending),
		"bom": task.get(bom_field),
		"rows": rows,
		"remarks": [n for n in notes if n],
	}


@frappe.whitelist()
def pdf(task, download=0, pending=0):
	"""The purchase list, shown in the browser; saved as a file with `download`; only the
	pending items with `pending`."""
	doc = frappe.get_doc("Installation Task", task)
	doc.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(doc, pending=frappe.utils.cint(pending))
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"


def file_name(doc, pending=False):
	consumer = frappe.db.get_value("Solar Installation", doc.solar_installation, "consumer_name")
	return "{0} - {1} - {2}.pdf".format("Pending Items" if pending else "Purchase List", consumer or doc.solar_installation, doc.name)


def render(doc, pending=False):
	"""(file name, PDF) of a procurement task's purchase list - downloaded, or sent to the
	supplier by email or WhatsApp (api/portal_share). With `pending`, the pending-items list:
	what the first supplier could not give, for the next."""
	if doc.task_code not in TITLES:
		frappe.throw(_("A purchase list is printed from the material and structure material procurement tasks."))
	if pending and not pending_rows(doc):
		frappe.throw(_("Nothing is pending on {0}: enter a Pending Qty on the rows the supplier could not give.").format(doc.name),
			title=_("Nothing Pending"))
	inst = frappe.get_doc("Solar Installation", doc.solar_installation)
	company = frappe.get_doc("Company", inst.company)
	address = frappe.get_doc("Address", inst.installation_address) if inst.get("installation_address") else None
	point = location(inst)
	system = " · ".join(filter(None, [
		"{0:g} kW".format(flt(inst.capacity_kw)) if flt(inst.capacity_kw) else "",
		inst.get("connection_type"), inst.get("system_type"),
	]))
	from a3_sola.api import material_delivery

	godown = doc.get("delivery_method") == material_delivery.GODOWN
	html = frappe.render_template("a3_sola/templates/print/purchase_list.html", {
		"company": company, "inst": inst, "task": doc, "system": system,
		"godown": godown, "delivery_method": doc.get("delivery_method") or material_delivery.VENDOR,
		"expected": formatdate(doc.expected_delivery_date, "dd-MM-yyyy") if doc.get("expected_delivery_date") else "",
		"ship_address": material_delivery.site(inst)[1]
		or (documents._address_text(address) if address else documents._party_address(None, inst)),
		"point": None if godown else point, "map_url": documents.maps_link(*point) if point and not godown else "",
		"date": formatdate(today(), "dd-MM-yyyy"), **lines(doc, pending),
	})
	return file_name(doc, pending), documents.plain_pdf(html)
