# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Serial traceability - a compliance requirement, not bookkeeping.

The ministry rejects national-portal submissions containing repeated module or inverter
serial numbers, and NISE operates a DCR verification portal tracing cells to modules by
serial. Serials must flow Purchase Receipt -> Delivery Note -> one and only one
installation, with a hard uniqueness guard and a manifest export.
"""

import csv
import io

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api.settings import get_value


def validate_serial_uniqueness(serial_no, installation, company=None):
	"""Raise if this serial is already consumed by another installation."""
	if not get_value("enforce_serial_uniqueness"):
		return
	filters = {
		"serial_no": serial_no,
		"parenttype": "Solar Installation",
		"parent": ["!=", installation],
	}
	rows = frappe.get_all("Installation Serial Register", filters=filters, fields=["parent"], limit=1)
	if not rows:
		return
	other = rows[0].parent
	if company and frappe.db.get_value("Solar Installation", other, "company") != company:
		# Still a duplicate on the portal, but name it precisely.
		pass
	frappe.throw(
		_("Serial {0} is already recorded on installation {1}. The national portal rejects "
		  "submissions containing a repeated serial.").format(
			frappe.bold(serial_no), frappe.utils.get_link_to_form("Solar Installation", other)
		),
		title=_("Duplicate Serial"),
	)


def validate_register(installation):
	"""Guard uniqueness within the document and across installations, then roll counts."""
	seen = set()
	modules = inverters = 0
	for row in installation.serials:
		if not row.serial_no:
			continue
		key = row.serial_no.strip().upper()
		if key in seen:
			frappe.throw(
				_("Serial {0} appears twice on this installation.").format(frappe.bold(row.serial_no)),
				title=_("Duplicate Serial"),
			)
		seen.add(key)
		validate_serial_uniqueness(row.serial_no, installation.name, installation.company)
		if row.component_type == "Module":
			modules += 1
		elif row.component_type == "Inverter":
			inverters += 1

	expected = 0
	if installation.solar_package:
		expected = flt(frappe.db.get_value("Solar Package", installation.solar_package, "module_count"))
	installation.modules_expected = int(expected or installation.module_count or 0)
	installation.modules_captured = modules
	installation.inverters_captured = inverters
	installation.serial_capture_complete = (
		1 if installation.modules_expected and modules >= installation.modules_expected and inverters else 0
	)


@frappe.whitelist()
def pull_serials_from_delivery_note(installation):
	"""Import every serialised item from Delivery Notes linked to this installation."""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")

	notes = frappe.get_all(
		"Delivery Note",
		filters={"solar_installation": doc.name, "docstatus": 1},
		pluck="name",
	)
	if not notes and doc.sales_order:
		notes = frappe.get_all(
			"Delivery Note Item",
			filters={"against_sales_order": doc.sales_order, "docstatus": 1},
			pluck="parent",
			distinct=True,
		)

	existing = {r.serial_no for r in doc.serials if r.serial_no}
	added = 0
	for note in notes:
		for item in frappe.get_all(
			"Delivery Note Item",
			filters={"parent": note},
			fields=["item_code", "serial_no"],
		):
			for serial in (item.serial_no or "").split("\n"):
				serial = serial.strip()
				if not serial or serial in existing:
					continue
				doc.append("serials", _serial_row(serial, item.item_code, note))
				existing.add(serial)
				added += 1

	if added:
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
	return {"added": added, "delivery_notes": notes}


def _serial_row(serial, item_code, delivery_note):
	item = frappe.db.get_value(
		"Item", item_code, ["item_name", "is_dcr", "dcr_certificate_no", "item_group"], as_dict=True
	) or frappe._dict()
	detail = frappe.db.get_value(
		"Serial No", serial, ["item_code", "purchase_document_no"], as_dict=True
	) or frappe._dict()
	component = "Module" if "module" in (item.item_name or "").lower() or "panel" in (item.item_name or "").lower() else (
		"Inverter" if "inverter" in (item.item_name or "").lower() else "Other"
	)
	return {
		"component_type": component,
		"serial_no": serial,
		"item": item_code,
		"model_number": item.item_name,
		"dcr_certificate_no": item.dcr_certificate_no,
		"delivery_note": delivery_note,
		"purchase_receipt": detail.purchase_document_no,
	}


@frappe.whitelist()
def export_serial_manifest(installation):
	"""CSV in the format chosen in Settings, for portal submission and DCR audit."""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("read")

	columns = [
		"Installation", "Consumer Number", "DISCOM", "Capacity kW", "Component Type",
		"Manufacturer", "Model", "Serial Number", "Wattage", "DCR Certificate", "Installation Date",
	]
	buffer = io.StringIO()
	writer = csv.writer(buffer)
	writer.writerow(columns)
	discom = frappe.db.get_value("DISCOM", doc.discom, "discom_name") if doc.discom else ""
	for row in doc.serials:
		writer.writerow(
			[
				doc.name, doc.consumer_number, discom, doc.capacity_kw, row.component_type,
				row.manufacturer, row.model_number, row.serial_no, row.wattage,
				row.dcr_certificate_no, doc.warranty_start_date or "",
			]
		)

	frappe.response["filename"] = f"serial-manifest-{doc.name}.csv"
	frappe.response["filecontent"] = buffer.getvalue()
	frappe.response["type"] = "binary"
	return buffer.getvalue()


@frappe.whitelist()
def get_completion_report_data(installation):
	"""The exact field set the bank and DISCOM completion reports carry.

	Both document templates render from this one function, so the two completion reports
	cannot disagree with each other or with the serial register.
	"""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("read")
	consumer = frappe.get_doc("Solar Consumer", doc.solar_consumer)
	section = frappe.db.get_value("DISCOM Section", doc.discom_section, "section_name") if doc.discom_section else ""

	modules = [r for r in doc.serials if r.component_type == "Module"]
	inverters = [r for r in doc.serials if r.component_type == "Inverter"]

	return {
		"consumer_name": consumer.consumer_name,
		"address": frappe.db.get_value("Address", consumer.installation_address, "address_line1")
		if consumer.installation_address
		else "",
		"consumer_number": consumer.consumer_number,
		"electrical_section": section,
		"service_connection_type": consumer.connection_type,
		"plant_capacity": f"{flt(doc.capacity_kw):g} kW {doc.system_type or ''}".strip(),
		"module_make_and_wattage": (
			f"{frappe.db.get_value('Component Make', doc.module_make, 'make_name') or ''} "
			f"{flt(doc.module_wattage):g}Wp"
		).strip(),
		"module_serial_numbers": [r.serial_no for r in modules],
		"module_count": len(modules),
		"inverter_make_and_capacity": (
			f"{frappe.db.get_value('Component Make', doc.inverter_make, 'make_name') or ''} "
			f"{flt(doc.inverter_capacity_kw):g}kW {doc.system_type or ''}"
		).strip(),
		"inverter_serial_number": inverters[0].serial_no if inverters else "",
	}
