# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The one write path behind every metadata-driven create form.

`create_record` accepts a collection slug and the posted values, and is deliberately
narrow: the slug must be a known collection, and only the fields that collection's form
renders may be set - the form's field list is the allow-list. Everything else about
whether the record may be written - permission, validation, naming - is left to
`doc.insert`, which is the single authority. Not `allow_guest`: a signed-in user with
create permission on the target doctype, and a valid CSRF token, are both required
before this function is reached.
"""

import frappe
from frappe import _

from frappe.utils import cint, flt

from a3_sola.api import portal_chain
from a3_sola.api.portal_fields import NUMERIC_TYPES, is_portal_file
from a3_sola.www.a3solaportal.collections import (
	COLLECTIONS, DETAIL_SLUGS, SUBMIT_SLUGS, get_collection, form_extra, form_fields, desk_route,
	is_editable, load_record, edit_allowlist, item_rows, lead_first_allowlist, needs_prompt_name, record_route,
	TASK_FORM_CHECKS, task_form_choices, task_form_groups, task_source,
	reimbursable,
)

TRUE = {"1", "true", "on", "yes"}


@frappe.whitelist()
def create_record(slug=None, source_dt=None, source=None, source_task=None, **values):
	cfg = get_collection(slug)
	doctype = cfg["doctype"]
	meta = frappe.get_meta(doctype)
	specs, _unrenderable = form_fields(meta, None, form_extra(cfg, meta))
	allowed = {s["fieldname"]: s for s in specs}

	step, source_doc = None, None
	if source_dt == "Solar Installation" and source and source_task:
		return _create_for_task(slug, cfg, source, source_task, values)
	if source_dt and source:
		step, source_doc = _load_source(slug, source_dt, source)
	# A step with a mapper starts from what the mapper builds - an order with the
	# quotation's items, rates and taxes - and the form's values go on top.
	doc = portal_chain.mapped_doc(step, source_doc) if step and step.get("via") else frappe.new_doc(doctype)

	# Prompt-named doctypes carry their id in the synthetic __name field. A doctype that
	# allocates its own series has no such field and must not be given a name here.
	if "__name" in allowed and needs_prompt_name(meta):
		name = (values.get("__name") or "").strip()
		if not name:
			frappe.throw(_("Enter a reference ID."), frappe.MandatoryError)
		doc.name = name

	# Created from another record: everything the chain carries across is applied first,
	# so the fields the form does not render still arrive. The form is authoritative for
	# what it does render, so those are overwritten below - including with a blank, if
	# the person cleared a suggested value.
	if step and not step.get("via"):
		for fieldname, value in portal_chain.mapped_values(step, source_doc).items():
			if fieldname not in allowed:
				doc.set(fieldname, value)

	for fieldname, spec in allowed.items():
		if fieldname == "__name":
			continue
		value = values.get(fieldname)
		if spec["type"] == "Check":
			doc.set(fieldname, 1 if str(value).lower() in TRUE else 0)
		elif value not in (None, ""):
			doc.set(fieldname, value)

	# Company is never asked for; fill it from the user's default so the mandatory link
	# is satisfied without putting a tenant concern in front of the person.
	if meta.get_field("company") and not doc.get("company"):
		company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		if company:
			doc.company = company

	_set_item_rows(doc, slug, values)
	doc.insert()
	# A KSEB bill read on the form (api/kseb_bill.py) becomes this record's.
	if values.get("kseb_bill_file"):
		from a3_sola.api import kseb_bill

		kseb_bill.claim(values["kseb_bill_file"], doctype, doc.name)

	# Only once the record exists: the source now points at it, so the button on the
	# source's page becomes the card for this record.
	if step and source_doc:
		portal_chain.link_back(step, source_doc, doc.name)

	route = record_route(slug, doc.name) if slug in DETAIL_SLUGS else f"/a3solaportal/{slug}"
	if cfg.get("edit_after_create") and is_editable(doc):
		route = record_route(slug, doc.name) + "/edit"
	return {"name": doc.name, "route": route, "desk": desk_route(doctype, doc.name)}


def _create_for_task(slug, cfg, installation, task_code, values):
	"""A task's document, created on its whole form from the project board.

	What makes it that task's - the job, the code, the kind of document (TASK_FIXED) - is
	worked out again here from the job, never taken from the post; the rest is the form's,
	allowed field by field as the form rendered it (task_form_groups).
	"""
	task_values = task_source(slug, installation, task_code)
	if task_values is None:
		frappe.throw(_("Task {0} on {1} does not open a new {2}.").format(task_code, installation, cfg["singular"]),
			frappe.ValidationError)
	doc, groups = task_form_groups(slug, task_values)
	allowed = {spec["fieldname"]: spec for g in groups for s in g["sections"] for spec in s["fields"]}
	_set_posted(doc, allowed, values)
	_set_item_rows(doc, slug, values)
	# A select asked as a tick box (stamp paper purchased) takes its own values back.
	for field, (_label, on, off) in TASK_FORM_CHECKS.get(task_values.get("task_code"), {}).items():
		if field in allowed:
			doc.set(field, on if str(values.get(field)).lower() in TRUE else off)
	# A choice that sets several fields (who paid: Company, Customer, I paid) sets them from
	# its label; a label the form did not offer is refused.
	can_claim = reimbursable(installation, task_values.get("task_code"))
	for field, choices in task_form_choices(task_values.get("task_code"), can_claim).items():
		if field not in allowed or field not in values:
			continue
		sets = dict(choices).get(values.get(field))
		if sets is None:
			frappe.throw(_("Choose who paid: {0}.").format(", ".join(label for label, _set in choices)),
				frappe.ValidationError)
		doc.update(sets)
	doc.insert()
	# On to the document's page, where the task is completed (Complete task / Submit).
	return {"name": doc.name, "route": record_route(slug, doc.name), "desk": desk_route(cfg["doctype"], doc.name)}


def _set_posted(doc, allowed, values):
	"""Set each allowed field the caller posted, typed as its spec says. A field not posted
	is left as it is."""
	for fieldname, spec in allowed.items():
		if fieldname not in values:
			continue
		raw = values.get(fieldname)
		if spec["type"] == "Check":
			doc.set(fieldname, 1 if str(raw).lower() in TRUE else 0)
			continue
		text = ("" if raw is None else str(raw)).strip()
		if spec["type"] in NUMERIC_TYPES:
			doc.set(fieldname, (cint(text) if spec["type"] == "Int" else flt(text)) if text else None)
		else:
			doc.set(fieldname, text or None)


@frappe.whitelist()
def create_from_lead(slug=None, tables=None, **values):
	"""Create a project from the lead-first form, then open it.

	The allow-list is the editable fields that form renders. Values the desk derives -
	the fetched details, the fees - are not taken from the browser; the installation's own
	`validate` fills them from the lead, exactly as on the desk.

	`tables` carries the System tables the person changed in the add-row popups, keyed by
	table. Each row keeps only the fields that popup asks for; the counts and amounts are
	worked out again on save, and the estimate's own computed rows are kept from the
	estimate, not from the browser.
	"""
	if slug != "projects":
		frappe.throw(_("A {0} is not created from a lead here.").format(slug), frappe.ValidationError)
	cfg = get_collection(slug)
	meta = frappe.get_meta(cfg["doctype"])
	allowed = lead_first_allowlist(meta)
	if not (values.get("lead") or "").strip():
		frappe.throw(_("Choose the lead this project is for."), frappe.MandatoryError)

	doc = frappe.new_doc(cfg["doctype"])
	for fieldname, spec in allowed.items():
		value = values.get(fieldname)
		if spec["type"] == "Check":
			doc.set(fieldname, 1 if str(value).lower() in TRUE else 0)
		elif value not in (None, ""):
			doc.set(fieldname, value)
	if not doc.get("company"):
		doc.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	doc.flags.portal_design_rows = _design_rows(tables)
	doc.flags.portal_task_rows = _task_rows(tables)

	doc.insert()
	return {"name": doc.name, "route": record_route(slug, doc.name), "desk": desk_route(cfg["doctype"], doc.name)}


def _design_rows(tables):
	"""The hand-entered rows of each editable System table, reduced to the popup's fields."""
	from a3_sola.api.portal_estimate import SECTION_BY_KEY
	from a3_sola.www.a3solaportal.collections import EDITABLE_TABLES

	tables = frappe.parse_json(tables) if tables else {}
	out = {}
	for key, rows in (tables or {}).items():
		if key not in EDITABLE_TABLES or not isinstance(rows, list):
			continue
		allowed = [f["fieldname"] for f in SECTION_BY_KEY[key]["fields"]]
		out[key] = [
			{f: (row.get(f) if row.get(f) not in ("",) else None) for f in allowed}
			for row in rows if isinstance(row, dict)
		]
	return out


def _task_rows(tables):
	"""The task rows from the create page, if they were changed there, reduced to what a
	person may set: the job's own fields on a template task, everything on an added one."""
	from a3_sola.api.stages import TASK_JOB_FIELDS, TASK_OWN_FIELDS

	rows = ((frappe.parse_json(tables) if tables else None) or {}).get("stages")
	if not isinstance(rows, list):
		return None
	out = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		fields = TASK_JOB_FIELDS + (("stage_code",) if row.get("__template") else TASK_OWN_FIELDS)
		out.append({"__template": bool(row.get("__template")), **{f: row.get(f) for f in fields if f in row}})
	return out


def _load_source(slug, source_dt, source):
	"""The record a create-from was launched from, with the step that allows it.

	The pairing must be one the chain declares - an arbitrary doctype cannot be named
	here to pull its field values into a new record. Where the link is stored on the
	source, writing it is an edit of that record, so write permission is required; where
	it is stored on the new record instead, reading the source is enough.
	"""
	step = portal_chain.find_step(source_dt, slug)
	if not step:
		frappe.throw(_("Cannot create a {0} from a {1}.").format(slug, source_dt), frappe.ValidationError)
	if not frappe.db.exists(source_dt, source):
		frappe.throw(_("That record does not exist."), frappe.DoesNotExistError)
	doc = frappe.get_doc(source_dt, source)
	doc.check_permission("write" if step.get("link_field") else "read")
	if step.get("needs_submit") and cint(doc.docstatus) != 1:
		frappe.throw(_("{0} must be submitted before a {1} can be raised from it.").format(source, step["doctype"]),
			frappe.ValidationError)
	return step, doc


@frappe.whitelist()
def create_mapped(slug=None, source_dt=None, source=None):
	"""Build the next document with ERPNext's own mapper and save it as a draft.

	The chain step names the mapper (`via`), so the only thing the browser chooses is
	which step to take from which record - never which function to call. ERPNext's
	mappers read a submitted source and carry its items, rates and taxes across, which is
	why this exists at all: a portal form cannot produce a valid order from nothing.

	Returned as a draft, not submitted. Submitting is a commitment, and this endpoint
	only gets the person to a document they can check first.
	"""
	step = portal_chain.find_step(source_dt, slug)
	if not step or not (step.get("via") or step.get("make")):
		frappe.throw(_("Cannot create a {0} from a {1}.").format(slug, source_dt), frappe.ValidationError)
	if not frappe.db.exists(source_dt, source):
		frappe.throw(_("That record does not exist."), frappe.DoesNotExistError)

	source_doc = frappe.get_doc(source_dt, source)
	source_doc.check_permission("read")
	if step.get("needs_submit") and cint(source_doc.docstatus) != 1:
		frappe.throw(
			_("{0} must be submitted before a {1} can be raised from it.").format(source, step["doctype"]),
			frappe.ValidationError,
		)
	frappe.has_permission(step["doctype"], "create", throw=True)

	if step.get("needs_setting") and not portal_chain.get_value(step["needs_setting"]):
		frappe.throw(_("Creating a {0} is turned off in A3 Sola Settings.").format(
			_(step.get("kind_label") or step["doctype"]).lower()), frappe.ValidationError)
	if step.get("make"):
		# The step's own creator writes the whole record (the project, by the handoff).
		name = frappe.get_attr(step["make"])(source_doc)
		if not name:
			frappe.throw(_("{0} cannot open a {1}: it was not raised from a solar quotation.").format(
				source, _(step.get("kind_label") or step["doctype"]).lower()), frappe.ValidationError)
		return {"name": name, "route": record_route(slug, name), "desk": desk_route(step["doctype"], name)}

	doc = frappe.get_attr(step["via"])(source)
	doc.insert()
	return {"name": doc.name, "route": record_route(slug, doc.name), "desk": desk_route(step["doctype"], doc.name)}


#: What a portal image upload will accept. Narrow on purpose: this endpoint exists to put
#: a photograph on a record, not to become a general file store.
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024
#: A file field (PORTAL_FILE_FIELDS): a scanned report, as a PDF or a photograph of it.
FILE_TYPES = {"application/pdf", "image/png", "image/jpeg"}
MAX_FILE_BYTES = 10 * 1024 * 1024


@frappe.whitelist()
def upload_image(slug=None, fieldname=None, name=None):
	"""Store one uploaded picture - or, for a file field the portal captures (a feasibility
	report), a PDF or picture - and return its URL for the form to carry.

	The field must be an Attach Image, or a listed Attach (PORTAL_FILE_FIELDS), on that
	collection's own doctype, so this cannot be pointed at some other field or doctype. The
	file is saved private and returned as a URL; the form posts it back like any other value,
	which is what lets the same endpoint serve both the create form, where no record exists
	yet, and the edit form.
	"""
	cfg = get_collection(slug)
	doctype = cfg["doctype"]
	df = frappe.get_meta(doctype).get_field(fieldname)
	is_file = bool(df) and is_portal_file(doctype, df)
	if not df or (df.fieldtype != "Attach Image" and not is_file):
		frappe.throw(_("{0} does not take a picture.").format(fieldname), frappe.ValidationError)

	# Write permission on the record being edited, create permission when there is none yet.
	if name:
		load_record(slug, name, "write")
	else:
		frappe.has_permission(doctype, "create", throw=True)

	upload = (frappe.request.files or {}).get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	content = upload.stream.read()
	kind = (upload.content_type or "").split(";")[0]
	if is_file:
		if len(content) > MAX_FILE_BYTES:
			frappe.throw(_("That file is larger than 10MB."), frappe.ValidationError)
		if kind not in FILE_TYPES:
			frappe.throw(_("Choose a PDF, or a PNG or JPEG image."), frappe.ValidationError)
	else:
		if len(content) > MAX_IMAGE_BYTES:
			frappe.throw(_("That picture is larger than 5MB."), frappe.ValidationError)
		if kind not in IMAGE_TYPES:
			frappe.throw(_("Choose a PNG, JPEG, WebP or GIF image."), frappe.ValidationError)

	doc = frappe.get_doc({
		"doctype": "File",
		"file_name": upload.filename,
		"content": content,
		"is_private": 1,
		"attached_to_doctype": doctype if name else None,
		"attached_to_name": name or None,
		"attached_to_field": fieldname if name else None,
	})
	doc.insert(ignore_permissions=True)
	return {"file_url": doc.file_url, "file_name": doc.file_name}


@frappe.whitelist()
def submit_record(slug=None, name=None):
	"""Submit a portal record, so the portal reaches the same handoff the desk does.

	Only the sales order and the task documents (SUBMIT_SLUGS), and only through the
	document's own `submit`. That matters: submitting the order is what opens the Solar
	Installation, its document register and its billing plan, and submitting a task's
	document is what completes the task - all of it hangs off `on_submit` hooks. Calling
	`submit` rather than reproducing any of it here means the portal and the desk run the
	identical code.
	"""
	if slug not in SUBMIT_SLUGS:
		frappe.throw(_("A {0} cannot be submitted from the portal.").format(slug), frappe.PermissionError)
	doc = load_record(slug, name, "submit")
	if cint(doc.docstatus) != 0:
		frappe.throw(_("{0} is not a draft.").format(name), frappe.ValidationError)
	if slug == "installation-tasks":
		# A task is submitted as done: the same `complete` the desk's button calls, which
		# marks it Completed (its evidence checked) and then submits it.
		from a3_sola.solar_operations.doctype.installation_task.installation_task import complete

		complete(doc.name)
	else:
		doc.submit()
	return {"name": doc.name, "route": record_route(slug, doc.name)}


@frappe.whitelist()
def update_record(slug=None, name=None, **values):
	"""Save a portal edit form onto an existing record and return its portal route.

	Only the fields the edit form renders may be set - `edit_allowlist` is the allow-list -
	and only the ones the caller actually posted are touched, so a partial post changes
	nothing it did not name. Permission and validation are left to `save`, the single
	authority on whether this user may change the record.
	"""
	doc = load_record(slug, name, "write")
	_set_posted(doc, edit_allowlist(doc), values)
	_set_item_rows(doc, slug, values)
	doc.save()
	return {"name": doc.name, "route": record_route(slug, doc.name)}


def _set_item_rows(doc, slug, values):
	"""Replace the collection's rows table with the posted rows, when it has one and they
	were posted. The rows are cut down to the grid's editable columns by `item_rows`; the
	amounts and the total are the controller's to work out."""
	if "__items" not in values:
		return
	table = item_rows(slug, values.get("__items"), doc)
	if not table:
		return
	fieldname, rows = table
	doc.set(fieldname, [])
	for row in rows:
		doc.append(fieldname, row)
