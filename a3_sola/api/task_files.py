# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A task's documents are one list, wherever they are filed.

A project task's files live in two places: the task's own record (its Portal Application,
Installation Task, ...) carries them on its Attachments card (api/portal_attachments), and the
project's document register (Solar Installation `documents`) lists what the task needs, on the
board's Documents panel (api/portal_tasks). A file filed in one is filed in the other:

- uploaded on the Attachments card as one of the task's documents ("Portal acknowledgement"),
  it fills that register row - or adds a row, for a document the checklist does not name;
- uploaded on the Documents panel, it is attached to the task's record too, under the
  document's name;
- removed in either place, it goes from the other.

A general document type matches the register row it means (PM Surya Ghar Acknowledgement is
the "Portal acknowledgement"); the Attachments card offers the task's own documents by name.
"""

import re

import frappe

INSTALLATION = "Solar Installation"
#: General document types -> the register document they are, by the words a checklist names it.
ALIASES = {
	"PM Surya Ghar Acknowledgement": ("portal acknowledgement", "acknowledgement"),
	"Pre-Installation Photo": ("pre-installation site photo", "pre-installation photo", "site photo"),
	"Digital Approval Letter": ("approval letter", "digital approval", "sanction letter"),
	"KSEB Bill": ("kseb bill", "electricity bill"),
}
#: Documents a task's record files on its Attachments card beside its checklist's, by task code.
TASK_TYPES = {"FRM1": ("Feasibility Report",)}


def _norm(text):
	return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def task_of(doctype, name):
	"""(project, task code) whose task document is this record; (None, None) when it is no task's."""
	if not (doctype and name) or doctype == INSTALLATION:
		return None, None
	row = frappe.db.get_value("Installation Stage Log", {"parenttype": INSTALLATION, "task_doctype": doctype,
		"task_document": name}, ["parent", "stage_code"], as_dict=True)
	if not row:
		return None, None
	return frappe.get_doc(INSTALLATION, row.parent), row.stage_code


def task_document(inst, code):
	"""(doctype, name) of the task's record, where it has one."""
	row = next((r for r in inst.stages if r.stage_code == code), None)
	if row and row.task_doctype and row.task_document and frappe.db.exists(row.task_doctype, row.task_document):
		return row.task_doctype, row.task_document
	return None, None


def uploadable(inst, code):
	"""The task's register documents a person files (not the ones the system prints)."""
	from a3_sola.api.portal_tasks import _panel

	try:
		rows = _panel(inst, code)["documents"]
	except Exception:
		return []
	return [d["name"] for d in rows if d.get("kind") != "Generated" and d.get("name") and d.get("row")]


def names_for(doctype=None, name=None, installation=None, task=None):
	"""The task's own document names, for the Attachments card's choices."""
	if installation and task and frappe.db.exists(INSTALLATION, installation):
		inst, code = frappe.get_doc(INSTALLATION, installation), task
	else:
		inst, code = task_of(doctype, name)
	if not inst:
		return []
	own = uploadable(inst, code)
	return own + [t for t in TASK_TYPES.get(code, ()) if t not in own]


def register_name(inst, code, document_type):
	"""The register document a file of `document_type` is on this task: the row of that name, or
	the one its general type means; else the type itself (a new row)."""
	rows = [r for r in inst.documents if r.stage_code == code]
	wanted = _norm(document_type)
	for r in rows:
		if _norm(r.document_name) == wanted:
			return r.document_name
	for alias in ALIASES.get(document_type, ()):
		for r in rows:
			if alias in _norm(r.document_name):
				return r.document_name
	return document_type


def on_attached(doctype, name, document_type, file_url):
	"""A typed file on a task's record: its register row too."""
	if not document_type or not file_url:
		return
	inst, code = task_of(doctype, name)
	if not inst:
		return
	from a3_sola.api import documents

	document = register_name(inst, code, document_type)
	row = next((r for r in inst.documents if r.stage_code == code and r.document_name == document), None)
	if row and row.attachment and not row.is_verified:
		# A newer copy of a document the task already has: it replaces the one before.
		row.update({"document_kind": "Uploaded", "attachment": file_url, "source_doctype": doctype,
			"source_document": name, "document_date": frappe.utils.today()})
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_mandatory = True  # an old job missing its lead still files its papers
		inst.save(ignore_permissions=True)
		return
	if row and row.is_verified:
		return
	inst.flags.ignore_mandatory = True
	documents.register_document(inst, code, doctype, name, document, file_url, kind="Uploaded")


def on_removed(doctype, name, file_url):
	"""A file taken off a task's record: off its register rows too."""
	inst, code = task_of(doctype, name)
	if not inst:
		return
	if clear_register(inst, code, file_url):
		inst.flags.ignore_validate_update_after_submit = True
		inst.flags.ignore_mandatory = True  # an old job missing its lead still files its papers
		inst.save(ignore_permissions=True)
	# The project's own copy goes too, once no register row holds it.
	if not any(r.attachment == file_url for r in inst.documents):
		for f in frappe.get_all("File", filters={"attached_to_doctype": INSTALLATION, "attached_to_name": inst.name,
				"file_url": file_url}, pluck="name"):
			frappe.delete_doc("File", f, ignore_permissions=True)


def clear_register(inst, code, file_url):
	"""Empty the task's register rows holding `file_url`: a row the checklist expects waits for
	its file again, one added by hand goes. A verified row stays. Whether anything changed."""
	from a3_sola.setup import seed_stages

	expected = {n for n, _m, _t in seed_stages.checklists().get(code, ("", []))[1]}
	changed = False
	for d in [r for r in inst.documents if r.stage_code == code and r.attachment == file_url and not r.is_verified]:
		if d.solar_document_template or d.is_mandatory or d.document_name in expected:
			d.update({"document_kind": "Expected", "attachment": None, "source_doctype": None, "source_document": None,
				"document_date": None})
		else:
			inst.remove(d)
		changed = True
	return changed


def on_registered(inst, code, document_name, file_url):
	"""A file filed on the Documents panel: attached to the task's record too, under its name."""
	doctype, name = task_document(inst, code)
	if not doctype:
		return
	existing = frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name,
		"file_url": file_url}, fields=["name", "a3s_document_type"])
	if existing:
		# Already on the record - a paper the system made there - but not yet saying what it is.
		for f in existing:
			if not f.a3s_document_type:
				frappe.db.set_value("File", f.name, "a3s_document_type", document_name, update_modified=False)
		return
	source = frappe.db.get_value("File", {"file_url": file_url}, ["file_name", "is_private"], as_dict=True) or {}
	frappe.get_doc({"doctype": "File", "file_url": file_url, "file_name": source.get("file_name") or document_name,
		"is_private": source.get("is_private", 1), "attached_to_doctype": doctype, "attached_to_name": name,
		"a3s_document_type": document_name}).insert(ignore_permissions=True)
	from a3_sola.api.portal_attachments import _fill_field

	_fill_field(doctype, name, document_name, file_url)


def on_unregistered(inst, code, file_url):
	"""A file taken off on the Documents panel: off the task's record too."""
	doctype, name = task_document(inst, code)
	if not doctype:
		return
	for f in frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name,
			"file_url": file_url}, pluck="name"):
		frappe.delete_doc("File", f, ignore_permissions=True)


def sync_task(inst, code):
	"""Both ways, for a task already filed in one place only: the patch's, and safe to repeat."""
	doctype, name = task_document(inst, code)
	if not doctype:
		return
	for f in frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name, "is_folder": 0,
			"a3s_document_type": ["is", "set"]}, fields=["file_url", "a3s_document_type"]):
		if not any(r.stage_code == code and r.attachment == f.file_url for r in inst.documents):
			on_attached(doctype, name, f.a3s_document_type, f.file_url)
			inst.reload()
	for r in [r for r in inst.documents if r.stage_code == code and r.attachment]:
		on_registered(inst, code, r.document_name, r.attachment)
