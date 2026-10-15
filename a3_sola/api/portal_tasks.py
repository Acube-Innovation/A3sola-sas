# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A task on the portal's project board, worked from its card: its documents, listed from
the job's document register with a file to open, an upload for one still missing, and a
print for the ones the system writes itself. Skipping and putting a task back are
`tasks.skip_task` / `tasks.unskip_task`, called from the card as they are from the desk.

Reading needs read permission on the job; uploading needs write permission on it.
"""

import os

import frappe
from frappe import _
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api import documents
from a3_sola.api.reimbursements import claims_for
from a3_sola.api.stages import _get_stage

INSTALLATION = "Solar Installation"


def _job(installation, ptype):
	if not installation or not frappe.db.exists(INSTALLATION, installation):
		raise frappe.DoesNotExistError(_("That project does not exist."))
	doc = frappe.get_doc(INSTALLATION, installation)
	doc.check_permission(ptype)
	return doc


@frappe.whitelist()
def task_documents(installation, task_code):
	"""The task and its documents, as the card's Documents panel shows them."""
	inst = _job(installation, "read")
	return _panel(inst, task_code)


@frappe.whitelist(methods=["POST"])
def upload(installation, task_code, row=None, document_name=None):
	"""File the posted `file` as one of the task's documents: the register row `row` when it
	is still waiting for its file, else a new row named `document_name`. Returns the panel."""
	inst = _job(installation, "write")
	_get_stage(inst, task_code)
	expected = next((r for r in inst.documents if r.name == row and r.stage_code == task_code), None) if row else None
	name = (expected.document_name if expected else (document_name or "")).strip()
	if not name:
		frappe.throw(_("Say what the document is."), frappe.ValidationError)
	posted = frappe.request.files.get("file") if frappe.request and frappe.request.files else None
	if not posted:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	content = posted.stream.read()
	limit = get_max_file_size()
	if len(content) > limit:
		frappe.throw(_("{0} is larger than {1} MB.").format(posted.filename, limit // (1024 * 1024)), frappe.ValidationError)
	try:
		file = frappe.get_doc({
			"doctype": "File", "file_name": posted.filename, "content": content, "is_private": 1,
			"attached_to_doctype": INSTALLATION, "attached_to_name": inst.name,
		}).insert(ignore_permissions=True)
	except frappe.ValidationError:
		raise
	except Exception:
		# Frappe reads every PDF for embedded scripts; a damaged one cannot be read.
		frappe.throw(_("{0} could not be read. If it is a PDF, it may be damaged - save it again and retry.").format(
			posted.filename), frappe.ValidationError)
	documents.register_document(
		inst, task_code, INSTALLATION, inst.name, name, file.file_url, kind="Uploaded",
		template=expected.solar_document_template if expected else None,
	)
	return _panel(frappe.get_doc(INSTALLATION, inst.name), task_code)


def _panel(inst, task_code):
	row = _get_stage(inst, task_code)
	prints = _prints(row, inst.name)
	templates = dict(frappe.get_all(
		"Solar Document Template",
		filters={"name": ["in", [d.solar_document_template for d in inst.documents if d.solar_document_template]]},
		fields=["name", "template_code"], as_list=True,
	))
	rows = loan_pack(inst, row) if task_code == "LOAN" else []
	for d in ([] if task_code == "LOAN" else inst.documents):
		if d.stage_code != task_code:
			continue
		row_prints = prints.get(templates.get(d.solar_document_template), [])
		# A document the system prints (the bank's, in RIM format) opens as printed now, with
		# today's values - never a copy stored before a change.
		live = next((p["url"] + ("&signed=1" if p.get("signable") else "") for p in row_prints), None)
		rows.append({
			"row": d.name,
			"name": d.document_name,
			"kind": d.document_kind or "Expected",
			"mandatory": bool(d.is_mandatory),
			"verified": bool(d.is_verified),
			"file_url": live or d.attachment or "",
			"file_name": "" if live else os.path.basename(d.attachment or ""),
			"prints": row_prints,
		})
	return {
		"task": {
			"code": row.stage_code, "name": row.stage_name, "status": row.status,
			"mandatory": bool(row.is_mandatory), "reason": row.skip_reason or "",
		},
		"documents": rows,
		"claims": claims_for(inst.name, task_code),
		# The loan's list is the bank's, fixed: nothing is added to it by hand.
		"fixed": task_code == "LOAN",
		"can_upload": bool(inst.has_permission("write")),
		"max_file_mb": get_max_file_size() // (1024 * 1024),
	}


def _prints(row, installation):
	"""The documents the system prints for this task, by template code: the loan's bank
	letter and feasibility report (api/loan_print.py), for which the panel adds `&signed=1`
	or `0` from its "With sign & seal" box; the stamp paper data (api/stamp_print.py)."""
	if row.stage_code == "STMP":
		from a3_sola.api import stamp_print

		return {stamp_print.CODE: [{"label": _("Download"), "url": stamp_print.url(installation, row.task_document)}]}
	if row.task_doctype != "Loan Application" or not row.task_document:
		return {}
	from a3_sola.api.loan_print import DOCUMENTS

	base = "/api/method/a3_sola.api.loan_print.pdf?name=" + frappe.utils.quote(row.task_document)
	return {code: [{"label": _("Print"), "url": f"{base}&document={key}", "signable": True}] for key, code in DOCUMENTS.items()}


#: What the bank receives for the loan, in order: printed by us in the RIM format, the
#: Jan Samarth approval, and the consumer's own papers - (label, consumer document types).
LOAN_PACK_CONSUMER = (
	("KYC", ("Aadhaar Front", "Aadhaar Back", "PAN")),
	("KSEB bill", ("KSEB Bill",)),
	("Land tax receipt", ("Land Tax Receipt",)),
	("Building tax receipt", ("Building Tax Receipt",)),
	("Income tax return (ITR)", ("Income Tax Return",)),
)
LOAN_PACK_PRINTED = (("Covering letter", "letter"), ("Vendor feasibility report", "feasibility"), ("Quotation", "quotation"))


def loan_pack(inst, row):
	"""The Loan Documents panel: the bank's documents, each with its files to open, an upload
	for each still missing, and a print for the ones we write."""
	from a3_sola.solar_operations.doctype.installation_task.installation_task import approval_letters

	out = []
	loan = row.task_document if row.task_doctype == "Loan Application" else None
	base = "/api/method/a3_sola.api.loan_print.pdf?name=" + frappe.utils.quote(loan) if loan else None
	for label, key in LOAN_PACK_PRINTED:
		if base:
			url = f"{base}&document={key}"
			out.append({"name": label, "kind": "Generated", "files": [{"label": "", "url": url + "&signed=1"}],
				"missing": [], "prints": [{"label": _("Print"), "url": url, "signable": True}]})
		else:
			out.append({"name": label, "kind": "Expected", "files": [], "missing": [],
				"note": _("Printed once the loan application is created.")})

	dal = next((r for r in inst.stages if r.stage_code == "DAL"), None)
	if dal and dal.status == "Skipped":
		out.append({"name": "Digital approval letter", "kind": "Expected", "files": [], "missing": [], "note": _("Not needed - not financed.")})
	else:
		task = frappe._dict(name=dal.task_document if dal and dal.task_doctype == "Installation Task" else None,
			solar_installation=inst.name)
		files = [{"label": "", "url": f["file_url"]} for f in approval_letters(task)]
		out.append({"name": "Digital approval letter", "kind": "Uploaded" if files else "Expected", "files": files,
			"missing": [] if files else [{"label": "Digital approval letter",
				"upload": {"kind": "task", "task_code": "DAL", "document_name": "Digital approval letter"}}]})

	consumer = inst.get("solar_consumer")
	readable = consumer and frappe.has_permission("Solar Consumer", "read", consumer)
	have = consumer_files(consumer) if readable else {}
	for label, types in LOAN_PACK_CONSUMER:
		if not readable:
			out.append({"name": label, "kind": "Expected", "files": [], "missing": [], "note": _("No access to the consumer.")})
			continue
		files = [{"label": t if len(types) > 1 else "", "url": url} for t in types for url in have.get(t, [])]
		missing = [{"label": t, "upload": {"kind": "consumer", "consumer": consumer, "document_type": t}}
			for t in types if not have.get(t)]
		out.append({"name": label, "kind": "Uploaded" if files and not missing else "Expected",
			"files": files, "missing": missing})
	return out


def consumer_files(consumer):
	"""The consumer's files by document type - typed on upload, or a KYC row's."""
	by_type = {}
	for f in frappe.get_all("File", filters={"attached_to_doctype": "Solar Consumer", "attached_to_name": consumer,
			"is_folder": 0}, fields=["file_url", "a3s_document_type"], order_by="creation asc"):
		if f.a3s_document_type:
			by_type.setdefault(f.a3s_document_type, []).append(f.file_url)
	for r in frappe.get_all("Customer KYC Document", filters={"parent": consumer, "parenttype": "Solar Consumer"},
			fields=["kyc_type", "attachment"]):
		if r.attachment and r.attachment not in by_type.get(r.kyc_type, []):
			by_type.setdefault(r.kyc_type, []).append(r.attachment)
	return by_type

