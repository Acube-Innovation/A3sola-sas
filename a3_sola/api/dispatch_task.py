# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Material Dispatch task: the godown's delivery to the customer, recorded on its page.

No ERPNext document is made here. The page shows what goes - the material lists of the
procurement tasks that come through the company godown (api/material_delivery), and what the
vendors ship straight to the site instead - from where to where, and records the dispatch
itself: the date, the vehicle and driver, the module and inverter serial numbers (into the
job's serial register) and the signed delivery slip or photograph. Mark dispatched completes
the task.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from a3_sola.api import material_delivery, stages
from a3_sola.api.stages import _get_stage

DISPATCH = material_delivery.DISPATCH
INSTALLATION = "Solar Installation"
FIELDS = ("dispatch_date", "dispatch_vehicle", "dispatch_driver", "dispatch_driver_mobile", "dispatch_notes")
#: The serials the page captures, by the register's component type.
SERIAL_TYPES = ("Module", "Inverter")
SLIP = "Delivery note"


def is_dispatch_task(code):
	return code == DISPATCH


def _job(installation, ptype):
	doc = frappe.get_doc(INSTALLATION, installation, for_update=True)
	doc.check_permission(ptype)
	_get_stage(doc, DISPATCH)
	return doc


def _lists(inst):
	"""Each procurement task's material, and whether it comes through the godown."""
	from a3_sola.api.purchase_list import TITLES, lines

	out = []
	for code in material_delivery.PROCUREMENT:
		name = frappe.db.get_value("Installation Task", {"solar_installation": inst.name, "task_code": code,
			"docstatus": ["<", 2]}, "name", order_by="creation desc")
		if not name:
			continue
		task = frappe.get_doc("Installation Task", name)
		out.append({"title": TITLES[code], "task": name, "method": task.delivery_method or material_delivery.VENDOR,
			"godown": task.delivery_method == material_delivery.GODOWN, "rows": lines(task)["rows"]})
	return out


@frappe.whitelist()
def state(installation):
	inst = _job(installation, "read")
	row = _get_stage(inst, DISPATCH)
	company = material_delivery.company_lines(inst.company)
	name, address, mobile, point = material_delivery.site(inst)
	# The newest slip filed - a replaced one is filed again under the same name.
	slips = [d for d in inst.documents if d.stage_code == DISPATCH and d.document_name == SLIP]
	slip = next((d for d in reversed(slips) if d.attachment), slips[0] if slips else None)
	return {
		"task": {"code": row.stage_code, "name": row.stage_name, "status": row.status, "reason": row.skip_reason or "",
			"completed_on": frappe.utils.format_date(row.actual_completion_date, "d MMM yyyy") if row.actual_completion_date else ""},
		"ship_from": [_("Company godown")] + [line for line in company if line],
		"ship_to": [line for line in (name, address, _("Phone: {0}").format(mobile) if mobile else "") if line],
		"map": "https://www.google.com/maps?q={0},{1}".format(*point) if point else "",
		"lists": _lists(inst),
		"dispatch": {f: str(inst.get(f) or "") for f in FIELDS},
		"serials": {t: [r.serial_no for r in inst.get("serials") or [] if r.component_type == t and not r.is_replaced]
			for t in SERIAL_TYPES},
		"expected_modules": int(inst.get("modules_expected") or inst.get("module_count") or 0),
		"slip": {"row": slip.name if slip else None, "name": SLIP, "file_url": slip.attachment if slip else None},
		"can_edit": bool(inst.has_permission("write")) and row.status not in ("Skipped",),
		"can_complete": bool(inst.has_permission("write")) and row.status not in ("Completed", "Skipped"),
	}


def _set_serials(inst, kind, text):
	"""The register's `kind` serials as typed, one a line: rows that came from a delivery note
	or a receipt stay; the ones typed here are replaced."""
	wanted = []
	for line in (text or "").replace(",", "\n").splitlines():
		serial = line.strip()
		if serial and serial.upper() not in {w.upper() for w in wanted}:
			wanted.append(serial)
	kept = [r for r in inst.get("serials") or [] if r.component_type != kind or r.delivery_note or r.purchase_receipt]
	have = {r.serial_no.strip().upper() for r in kept if r.component_type == kind}
	inst.set("serials", kept)
	for serial in wanted:
		if serial.upper() not in have:
			inst.append("serials", {"component_type": kind, "serial_no": serial})


@frappe.whitelist(methods=["POST"])
def save(installation, module_serials=None, inverter_serials=None, **values):
	"""Record the dispatch details and serial numbers; the task stays open."""
	inst = _job(installation, "write")
	for field in FIELDS:
		if field in values:
			inst.set(field, (values.get(field) or "").strip() or None)
	if inst.dispatch_date and getdate(inst.dispatch_date) > getdate(today()):
		frappe.throw(_("The dispatch date cannot be in the future."))
	if module_serials is not None:
		_set_serials(inst, "Module", module_serials)
	if inverter_serials is not None:
		_set_serials(inst, "Inverter", inverter_serials)
	row = _get_stage(inst, DISPATCH)
	stages.check_half_paid(inst, DISPATCH)  # dispatch waits for half the project value
	if row.status == "Pending":
		row.status = "In Progress"
		row.actual_start_date = row.actual_start_date or today()
	inst.flags.ignore_validate_update_after_submit = True
	inst.save(ignore_permissions=True)
	return state(installation)


@frappe.whitelist(methods=["POST"])
def mark_dispatched(installation, **values):
	"""Save what is posted, then complete the task: the material left the godown that day."""
	save(installation, **values)
	inst = _job(installation, "write")
	row = _get_stage(inst, DISPATCH)
	stages.check_half_paid(inst, DISPATCH)
	if row.status in ("Completed", "Skipped"):
		frappe.throw(_("{0} is already {1}.").format(row.stage_name, row.status.lower()))
	if not inst.dispatch_date:
		frappe.throw(_("Enter the date the material was dispatched."), title=_("Dispatch Date Needed"))
	row.status = "Completed"
	row.actual_completion_date = inst.dispatch_date
	row.completed_by = frappe.session.user
	stages._save(inst, _("{0}: dispatched on {1}{2}.").format(row.stage_name,
		frappe.utils.format_date(inst.dispatch_date, "d MMM yyyy"),
		_(" in {0}").format(inst.dispatch_vehicle) if inst.dispatch_vehicle else ""))
	from a3_sola.api.tasks import notify_task_completed

	notify_task_completed(inst, DISPATCH)
	return state(installation)
