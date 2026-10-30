# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The design freeze tasks: the job's design, settled in two pages.

Nothing about installation is asked here. Each page shows what the design was sold on - the
job's quotations - and what it rests on: the site survey (changeable, with its photographs).
Solar Design Freeze (DSGN) then settles the system: the material BOM, the single line diagram
and the design's own images. Structural Design Freeze (SDSGN) settles what it stands on: the
structure BOM and the structure drawing. They are kept on the job (Solar Installation.site_survey,
.structure_bom, .material_bom, .design_images) and stay changeable after the freeze.

Structure and material procurement read the job's BOMs (api/structure_bom), so a change here
reaches them: a procurement task still in draft is re-pointed and its list refilled; one
already submitted is the record of what was bought and is left alone.
"""

import frappe
from frappe import _
from frappe.utils import fmt_money, today
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api import stages, structure_bom
from a3_sola.api.stages import _get_stage

DESIGN_TASK = "DSGN"
STRUCTURE_TASK = "SDSGN"
INSTALLATION = "Solar Installation"
#: The structure drawing, filed under Structural Design Freeze's documents.
STRUCTURE_DRAWING = "Structure drawing"


def is_design_task(code):
	return code in (DESIGN_TASK, STRUCTURE_TASK)


def _task(task_code):
	if not is_design_task(task_code):
		frappe.throw(_("{0} is not a design freeze task.").format(task_code), frappe.ValidationError)
	return task_code


def _job(installation, ptype, task_code=DESIGN_TASK):
	doc = frappe.get_doc(INSTALLATION, installation, for_update=ptype == "write")
	doc.check_permission(ptype)
	_get_stage(doc, _task(task_code))
	return doc


def _quotations(inst):
	"""Every quotation of the job's customer, estimate or proposal - the job's own first."""
	names = {inst.quotation} if inst.get("quotation") else set()
	for field, value in (("solar_consumer", inst.get("solar_consumer")),
			("solar_design_estimate", inst.get("solar_design_estimate")), ("solar_proposal", inst.get("solar_proposal"))):
		if value:
			names |= set(frappe.get_all("Quotation", filters={field: value, "docstatus": ["<", 2]}, pluck="name"))
	rows = frappe.get_all("Quotation", filters={"name": ["in", list(names) or [""]]},
		fields=["name", "status", "transaction_date", "grand_total", "currency", "selected_option", "docstatus"],
		order_by="transaction_date desc, creation desc")
	out = [{
		"name": q.name, "status": q.status, "date": frappe.utils.format_date(q.transaction_date, "d MMM yyyy"),
		"total": fmt_money(q.grand_total, currency=q.currency or "INR"), "option": q.selected_option or "",
		"is_job": q.name == inst.get("quotation"),
		"route": "/a3solaportal/quotations/{0}".format(frappe.utils.quote(q.name)),
	} for q in rows]
	return sorted(out, key=lambda q: not q["is_job"])


def _survey(inst):
	"""Every site survey of the job's customer or its lead, as the quotations are listed -
	the job's own first, each opening the survey - with the job's survey's photographs."""
	name = inst.get("site_survey")
	filters = [["solar_consumer", "=", inst.solar_consumer]] if inst.get("solar_consumer") else []
	or_filters = filters + ([["lead", "=", inst.lead]] if inst.get("lead") else [])
	rows = frappe.get_all("Site Survey", filters={"docstatus": ["<", 2]}, or_filters=or_filters,
		fields=["name", "survey_date", "feasibility_status", "capacity_installable_kw", "docstatus"],
		order_by="creation desc") if or_filters else []
	if name and name not in {r.name for r in rows}:
		rows.insert(0, frappe.db.get_value("Site Survey", name, ["name", "survey_date", "feasibility_status",
			"capacity_installable_kw", "docstatus"], as_dict=True))
	images = frappe.get_all("Survey Image", filters={"parent": name, "parenttype": "Site Survey"},
		fields=["image", "caption"], order_by="idx asc") if name else []
	surveys = [{
		"name": r.name, "is_job": r.name == name,
		"date": frappe.utils.format_date(r.survey_date, "d MMM yyyy") if r.survey_date else "",
		"feasibility": r.feasibility_status or "",
		"capacity": "{0:g} kW".format(r.capacity_installable_kw) if r.capacity_installable_kw else "",
		"status": _("Draft") if r.docstatus == 0 else _("Submitted"),
		"route": "/a3solaportal/site-surveys/{0}".format(frappe.utils.quote(r.name)),
	} for r in rows if r]
	return {
		"name": name or "",
		"surveys": sorted(surveys, key=lambda r: not r["is_job"]),
		"images": [{"url": i.image, "caption": i.caption or ""} for i in images if i.image],
		# None on file: a survey is made from the customer, as the chain makes it.
		"create_route": "/a3solaportal/site-surveys/new?source_dt=Solar+Consumer&source={0}".format(
			frappe.utils.quote(inst.solar_consumer)) if inst.get("solar_consumer") else "",
	}


def _sld(inst):
	"""The single line diagram, filed under this task's documents; it goes to the electrical
	contractor with the Installation work order (api/work_order_print)."""
	from a3_sola.api.work_order_print import SLD, sld_for

	url, row = sld_for(inst)
	return {"url": url or "", "row": row or "", "name": SLD}


def _drawing(inst):
	"""The structure drawing, filed under Structural Design Freeze's documents."""
	row = next((d for d in inst.get("documents") or [] if d.stage_code == STRUCTURE_TASK
		and (d.document_name or "").lower() == STRUCTURE_DRAWING.lower()), None)
	return {"url": (row.attachment if row else "") or "", "row": row.name if row else "", "name": STRUCTURE_DRAWING}


def _bom(value, choices, inst=None):
	return {"value": value or "", "choices": choices, "lines": structure_bom.bom_items(value, inst)["lines"] if value else []}


def _procurement(inst):
	"""The procurement tasks that read the job's BOMs, and where each stands."""
	out = []
	for code in structure_bom.MATERIAL_LISTS:
		row = next((r for r in inst.stages if r.stage_code == code), None)
		if not row:
			continue
		doc = frappe.db.get_value("Installation Task", {"solar_installation": inst.name, "task_code": code,
			"docstatus": ["<", 2]}, ["name", "docstatus"], as_dict=True, order_by="creation desc")
		out.append({"code": code, "name": row.stage_name, "status": row.status,
			"document": doc.name if doc else "", "locked": bool(doc and doc.docstatus == 1)})
	return out


@frappe.whitelist()
def state(installation, task_code=DESIGN_TASK):
	"""Everything a design freeze page shows: the shared parts, then the task's own - the
	material BOM, single line diagram and images (DSGN), or the structure BOM and drawing (SDSGN)."""
	inst = _job(installation, "read", task_code)
	row = _get_stage(inst, task_code)
	editable = bool(inst.has_permission("write")) and row.status != "Skipped"
	out = {
		"task": {"code": row.stage_code, "name": row.stage_name, "status": row.status,
			"completed_on": frappe.utils.format_date(row.actual_completion_date, "d MMM yyyy") if row.status == "Completed" and row.actual_completion_date else "",
			"completed_by": frappe.db.get_value("User", row.completed_by, "full_name") or row.completed_by or "" if row.status == "Completed" else ""},
		"quotations": _quotations(inst),
		"survey": _survey(inst),
		"frozen": {"structure_bom": inst.get("structure_bom") or "", "material_bom": inst.get("material_bom") or ""},
		"procurement": _procurement(inst),
		"can_edit": editable,
		"can_freeze": editable and row.status not in ("Completed", "Skipped"),
		"max_file_mb": get_max_file_size() // (1024 * 1024),
	}
	if task_code == STRUCTURE_TASK:
		out["structure_bom"] = _bom(structure_bom.bom_for(inst), structure_bom.structure_choices_for(inst) if editable else [])
		out["sld"] = _drawing(inst)
	else:
		out["material_bom"] = _bom(structure_bom.material_bom_for(inst), structure_bom.material_choices_for(inst) if editable else [], inst)
		out["sld"] = _sld(inst)
		out["images"] = [{"row": i.name, "url": i.image, "caption": i.caption or ""} for i in inst.get("design_images") or [] if i.image]
	return out


def _check_bom(bom):
	if bom and not frappe.db.exists("BOM", {"name": bom, "docstatus": 1, "is_active": 1}):
		frappe.throw(_("{0} is not an active, submitted BOM.").format(bom), frappe.ValidationError)


def _save_job(inst, message):
	# The design fields change after submit; the engine's own rows are untouched here.
	inst.flags.ignore_validate_update_after_submit = True
	inst.save(ignore_permissions=True)
	if message:
		inst.add_comment("Comment", message)


def refresh_procurement(inst):
	"""Draft procurement tasks follow the job's BOMs: re-pointed, and their lists refilled from
	the new BOM. A submitted one is what was bought and stays. Returns the tasks updated."""
	updated = []
	for code, (_table, field) in structure_bom.MATERIAL_LISTS.items():
		wanted = structure_bom.bom_for(inst) if code == "SPROC" else structure_bom.material_bom_for(inst)
		for name in frappe.get_all("Installation Task", filters={"solar_installation": inst.name, "task_code": code,
				"docstatus": 0}, pluck="name"):
			task = frappe.get_doc("Installation Task", name)
			if not wanted or task.get(field) == wanted:
				continue
			task.set(field, wanted)
			structure_bom.fill_materials(task)
			task.flags.ignore_permissions = True
			task.save()
			updated.append(name)
	return updated


@frappe.whitelist(methods=["POST"])
def save(installation, site_survey=None, structure_bom_name=None, material_bom=None, task_code=DESIGN_TASK):
	"""Change the job's site survey or either BOM; the draft procurement tasks follow."""
	inst = _job(installation, "write", task_code)
	changes = []
	if site_survey is not None and site_survey != (inst.site_survey or ""):
		owner = frappe.db.get_value("Site Survey", site_survey, ["solar_consumer", "lead"], as_dict=True) if site_survey else None
		if site_survey and not (owner and ((owner.solar_consumer and owner.solar_consumer == inst.solar_consumer)
				or (owner.lead and owner.lead == inst.get("lead")))):
			frappe.throw(_("Site survey {0} is of another customer.").format(site_survey), frappe.ValidationError)
		inst.site_survey = site_survey or None
		survey = frappe.db.get_value("Site Survey", site_survey, ["roof_type", "total_usable_area_sqft",
			"structure_type_required", "capacity_installable_kw"], as_dict=True) if site_survey else frappe._dict()
		inst.survey_roof_type = survey.get("roof_type")
		inst.survey_usable_area_sqft = survey.get("total_usable_area_sqft")
		inst.survey_structure_type = survey.get("structure_type_required")
		inst.survey_installable_kw = survey.get("capacity_installable_kw")
		changes.append(_("site survey {0}").format(site_survey or _("cleared")))
	for field, value, label in (("structure_bom", structure_bom_name, _("structure BOM")),
			("material_bom", material_bom, _("material BOM"))):
		if value is None or value == (inst.get(field) or ""):
			continue
		_check_bom(value)
		inst.set(field, value or None)
		changes.append(_("{0} {1}").format(label, value or _("cleared")))
	if changes:
		_save_job(inst, _("Design changed: {0}.").format(", ".join(changes)))
	updated = refresh_procurement(inst) if changes else []
	out = state(installation, task_code)
	out["updated_tasks"] = updated
	return out


@frappe.whitelist(methods=["POST"])
def add_image(installation, caption=None):
	"""Add each posted image to the job's design images."""
	inst = _job(installation, "write")
	uploads = frappe.request.files.getlist("file") if frappe.request and frappe.request.files else []
	if not uploads:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	limit = get_max_file_size()
	for upload in uploads:
		content = upload.stream.read()
		if len(content) > limit:
			frappe.throw(_("{0} is larger than {1} MB.").format(upload.filename, limit // (1024 * 1024)), frappe.ValidationError)
		file = frappe.get_doc({"doctype": "File", "file_name": upload.filename, "content": content, "is_private": 1,
			"attached_to_doctype": INSTALLATION, "attached_to_name": inst.name}).insert(ignore_permissions=True)
		inst.append("design_images", {"image": file.file_url, "caption": (caption or "").strip() or None})
	_save_job(inst, None)
	return state(installation)


@frappe.whitelist(methods=["POST"])
def remove_image(installation, row):
	inst = _job(installation, "write")
	if not any(i.name == row for i in inst.get("design_images") or []):
		frappe.throw(_("That image is not on this job."), frappe.ValidationError)
	inst.set("design_images", [i for i in inst.design_images if i.name != row])
	_save_job(inst, None)
	return state(installation)


@frappe.whitelist(methods=["POST"])
def freeze(installation, task_code=DESIGN_TASK):
	"""Freeze the task's side of the design: its BOM in use is written onto the job - the
	material BOM (DSGN) or the structure BOM (SDSGN) - and the task is done."""
	inst = _job(installation, "write", task_code)
	row = _get_stage(inst, task_code)
	if row.status in ("Completed", "Skipped"):
		frappe.throw(_("{0} is already {1}.").format(row.stage_name, row.status.lower()))
	field, label, bom = (("structure_bom", _("structure BOM"), structure_bom.bom_for(inst)) if task_code == STRUCTURE_TASK
		else ("material_bom", _("material BOM"), structure_bom.material_bom_for(inst)))
	if not bom:
		frappe.throw(_("Choose the {0} before freezing the design.").format(label), title=_("BOM Needed"))
	if field == "material_bom" and bom in structure_bom.capacity_boms():
		bom = _with_panels(inst, bom)
	inst.set(field, bom)
	row.status = "Completed"
	row.actual_completion_date = today()
	row.actual_start_date = row.actual_start_date or row.actual_completion_date
	row.completed_by = frappe.session.user
	stages._save(inst, _("{0}: design frozen by {1} - {2} {3}.").format(
		row.stage_name, frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user, label, bom))
	refresh_procurement(inst)
	from a3_sola.api.tasks import notify_task_completed

	notify_task_completed(inst, task_code)
	return state(installation, task_code)


#: The item a job's own structure BOM is made for when it starts from no BOM at all.
JOB_STRUCTURE_ITEM = "MNT-STRUCT-JOB"


@frappe.whitelist()
def item_options(txt=""):
	"""Items a design BOM line can be: enabled, not a package, matching `txt` by code or name."""
	txt = "%{0}%".format((txt or "").strip())
	return frappe.get_list("Item", filters={"disabled": 0, "item_group": ["!=", "Solar Packages"]},
		or_filters={"item_code": ["like", txt], "item_name": ["like", txt]},
		fields=["item_code", "item_name", "stock_uom"], order_by="item_name asc", limit_page_length=20)


def _job_bom_item(inst, field, base):
	"""The item a job's own BOM is made for: its current BOM's, else the package's (material)
	or a generic mounting structure (structure)."""
	if base:
		return frappe.db.get_value("BOM", base, "item")
	if field == "material_bom":
		item = frappe.db.get_value("Solar Package", inst.solar_package, "item") if inst.get("solar_package") else None
		if item:
			return item
	if not frappe.db.exists("Item", JOB_STRUCTURE_ITEM):
		frappe.get_doc({"doctype": "Item", "item_code": JOB_STRUCTURE_ITEM, "item_name": "Mounting Structure (job design)",
			"item_group": frappe.db.exists("Item Group", "Mounting Structures") or "All Item Groups",
			"stock_uom": "Nos", "is_stock_item": 0}).insert(ignore_permissions=True)
	return JOB_STRUCTURE_ITEM


def _retire(bom, inst):
	"""A job's own BOM it no longer uses goes inactive, unless a package, another job or a
	submitted procurement task still holds it."""
	if not bom or frappe.db.get_value("Solar Package", {"bom": bom}) or bom in structure_bom.structure_boms() \
			or bom in structure_bom.capacity_boms():
		return
	for field in ("material_bom", "structure_bom"):
		if frappe.db.exists(INSTALLATION, {field: bom, "name": ["!=", inst.name]}) or frappe.db.exists(
				"Installation Task", {field: bom, "docstatus": 1}):
			return
	frappe.db.set_value("BOM", bom, "is_active", 0)


@frappe.whitelist(methods=["POST"])
def save_lines(installation, bom_field, lines, task_code=DESIGN_TASK):
	"""The job's own BOM from the lines edited on the page: a new BOM made for this job (the
	package's is never changed), put on the job, and the draft procurement tasks follow."""
	if bom_field != {DESIGN_TASK: "material_bom", STRUCTURE_TASK: "structure_bom"}.get(task_code):
		frappe.throw(_("{0} is not settled on this task.").format(bom_field), frappe.ValidationError)
	inst = _job(installation, "write", task_code)
	rows = frappe.parse_json(lines) if isinstance(lines, str) else lines
	items, seen = [], set()
	for row in rows or []:
		code, qty = (row.get("item_code") or "").strip(), frappe.utils.flt(row.get("qty"))
		if not code or qty <= 0:
			continue
		if code in seen:
			frappe.throw(_("{0} is listed twice.").format(code), frappe.ValidationError)
		if not frappe.db.exists("Item", {"name": code, "disabled": 0}):
			frappe.throw(_("Item {0} does not exist.").format(code), frappe.ValidationError)
		seen.add(code)
		items.append({"item_code": code, "qty": qty, "uom": frappe.db.get_value("Item", code, "stock_uom")})
	if not items:
		frappe.throw(_("Add at least one line with a quantity."), frappe.ValidationError)

	base = structure_bom.bom_for(inst) if bom_field == "structure_bom" else structure_bom.material_bom_for(inst)
	name = _make_job_bom(inst, bom_field, base, items)
	label = _("structure BOM") if bom_field == "structure_bom" else _("material BOM")
	inst.set(bom_field, name)
	_save_job(inst, _("Design changed: {0} edited for this job - {1} ({2} lines).").format(label, name, len(items)))
	_retire(base, inst)
	updated = refresh_procurement(inst)
	out = state(installation, task_code)
	out["updated_tasks"] = updated
	return out


def _with_panels(inst, bom):
	"""The BOM by inverter capacity, frozen with the job's panels as a BOM of its own."""
	lines = structure_bom.bom_items(bom, inst)["lines"]
	missing = [l["item_name"] for l in lines if not l["item_code"]]
	if missing:
		frappe.throw(_("Choose the module Item for {0} in the Material BOM before freezing.").format(", ".join(missing)),
			title=_("Panel Item Needed"))
	if len(lines) == frappe.db.count("BOM Item", {"parent": bom, "parenttype": "BOM"}):
		return bom
	return _make_job_bom(inst, "material_bom", bom, [{"item_code": l["item_code"], "qty": l["qty"],
		"uom": frappe.db.get_value("Item", l["item_code"], "stock_uom")} for l in lines if frappe.utils.flt(l["qty"]) > 0])


def _make_job_bom(inst, bom_field, base, items):
	"""A submitted BOM made for this job from `items` ({item_code, qty, uom}), costed as `base` is."""
	bom = frappe.get_doc({
		"doctype": "BOM",
		"item": _job_bom_item(inst, bom_field, base),
		"company": inst.company,
		"quantity": 1,
		"is_active": 1,
		"is_default": 0,
		"project": inst.get("project"),
		"items": items,
	})
	if base:
		bom.update({k: v for k, v in frappe.db.get_value("BOM", base, ["rm_cost_as_per", "buying_price_list"], as_dict=True).items() if v})
	bom.insert(ignore_permissions=True)
	bom.submit()
	# ERPNext makes the first BOM of an item its default; a job's own BOM is never anyone's default.
	if frappe.db.get_value("BOM", bom.name, "is_default"):
		frappe.db.set_value("BOM", bom.name, "is_default", 0)
		if frappe.db.get_value("Item", bom.item, "default_bom") == bom.name:
			frappe.db.set_value("Item", bom.item, "default_bom", None)
	return bom.name
