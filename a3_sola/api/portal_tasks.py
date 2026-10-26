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
	file_url = posted_file(inst)
	if not file_url:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	documents.register_document(
		inst, task_code, INSTALLATION, inst.name, name, file_url, kind="Uploaded",
		template=expected.solar_document_template if expected else None,
	)
	return _panel(frappe.get_doc(INSTALLATION, inst.name), task_code)


def posted_file(inst):
	"""The request's posted `file`, kept private on the job: its URL, or None when no file
	was sent. Refuses one over the size limit, or one that cannot be read."""
	posted = frappe.request.files.get("file") if frappe.request and frappe.request.files else None
	if not posted:
		return None
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
	return file.file_url


@frappe.whitelist(methods=["POST"])
def remove(installation, task_code, row):
	"""Take the file off the task's document row `row`: a row the task's checklist expects
	waits for its file again (Missing), one added by hand goes. A verified file stays - it has
	been checked. The File goes too unless another row holds it. Returns the panel."""
	from a3_sola.setup import seed_stages

	inst = _job(installation, "write")
	_get_stage(inst, task_code)
	d = next((r for r in inst.documents if r.name == row and r.stage_code == task_code and r.attachment), None)
	if not d:
		frappe.throw(_("That document has no file to remove."), frappe.ValidationError)
	if d.is_verified:
		frappe.throw(_("{0} has been verified; it cannot be removed here.").format(d.document_name), frappe.ValidationError)
	file_url = d.attachment
	expected = {name for name, _m, _t in seed_stages.checklists().get(task_code, ("", []))[1]}
	if d.solar_document_template or d.is_mandatory or d.document_name in expected:
		d.update({"document_kind": "Expected", "attachment": None, "source_doctype": None, "source_document": None,
			"document_date": None})
	else:
		inst.remove(d)
	inst.flags.ignore_validate_update_after_submit = True
	inst.save(ignore_permissions=True)
	if not any(r.attachment == file_url for r in inst.documents):
		for name in frappe.get_all("File", filters={"file_url": file_url, "attached_to_doctype": INSTALLATION,
				"attached_to_name": inst.name}, pluck="name"):
			frappe.delete_doc("File", name, ignore_permissions=True)
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
		if d.document_name == KYC_DOCUMENTS:
			rows.append(kyc_entry(inst, d))
			continue
		if (d.document_name or "").startswith(KYC_REGISTERED) and d.document_kind == "Uploaded" and task_code == "ORD":
			continue  # each KYC paper is shown under the customer's KYC, above
		row_prints = prints.get(templates.get(d.solar_document_template), [])
		# A document the system prints (the bank's, in RIM format) opens as printed now, with
		# today's values - never a copy stored before a change. One the customer signs and
		# returns (`keep_file`) keeps its uploaded copy, and its upload while there is none.
		live = next((p["url"] + ("&signed=1" if p.get("signable") else "") for p in row_prints
			if not p.get("keep_file")), None)
		rows.append({
			"row": d.name,
			"name": d.document_name,
			# Printed live: generated, whatever the register row says.
			"kind": "Generated" if live else (d.document_kind or "Expected"),
			"mandatory": bool(d.is_mandatory),
			"verified": bool(d.is_verified),
			"file_url": live or d.attachment or "",
			"file_name": "" if live else os.path.basename(d.attachment or ""),
			"prints": row_prints,
			# A file someone filed here (not a live print, not yet verified) can be taken off.
			"removable": bool(d.attachment and not live and not d.is_verified),
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


#: The order task's KYC row, shown live from the customer and its lead, and the prefix of
#: the KYC papers the job's register copied from the customer (kyc.register_for_installation).
KYC_DOCUMENTS = "Customer KYC documents"
KYC_REGISTERED = "KYC - "


def kyc_entry(inst, d):
	"""The customer's KYC as it stands - uploaded on the customer or on its lead - each paper
	to open, an upload (onto the customer) for each still pending, and how many are in."""
	from a3_sola.api import kyc

	entry = {"row": d.name, "name": d.document_name, "mandatory": bool(d.is_mandatory), "kind": "Expected",
		"files": [], "missing": []}
	consumer = inst.get("solar_consumer")
	if not (consumer and frappe.has_permission("Solar Consumer", "read", consumer)):
		entry["note"] = _("No access to the customer.")
		return entry
	got = kyc.documents(consumer, frappe.db.get_value("Solar Consumer", consumer, "lead"),
		kyc.loan_amount_for(consumer=consumer))
	entry["files"] = [{"label": f["type"], "url": f["url"]} for item in got["items"] for f in item["files"]]
	entry["missing"] = [{"label": item["label"], "upload": {"kind": "consumer", "consumer": consumer,
		"document_type": item["types"][0]}} for item in got["items"] if not item["uploaded"]]
	entry["kind"] = "Uploaded" if not entry["missing"] else "Expected"
	return entry


def _prints(row, installation):
	"""The documents the system prints for this task, by template code: the loan's bank
	letter and feasibility report (api/loan_print.py), for which the panel adds `&signed=1`
	or `0` from its "With sign & seal" box; the stamp paper data (api/stamp_print.py)."""
	if row.stage_code == "MATL":
		# The data for the completion report, on the letterhead or plain paper.
		from a3_sola.api import completion_print

		notice = row.task_document if row.task_doctype == "Material Dispatch Notice" else None
		return {completion_print.CODE: completion_print.prints(installation, notice)}
	if row.stage_code == "FRM1":
		# KSEBL Form 1 with the customer's details (api/form1_print).
		from a3_sola.api import form1_print

		return {form1_print.CODE: form1_print.prints(installation)}
	if row.stage_code in ("ADV", "BAL", "PCOM"):
		# The payment statement - received and payable as of today (api/payment_statement_print).
		from a3_sola.api import payment_statement_print

		return {payment_statement_print.CODE: payment_statement_print.prints(installation)}
	if row.stage_code == "FRM2":
		# KSEBL Form 2 with the customer's details (api/form2_print); the row still takes
		# the signed copy.
		from a3_sola.api import form2_print

		return {form2_print.CODE: form2_print.prints(installation)}
	if row.stage_code == "KFORMS":
		# KSEBL Form 3, the KSEB Solar Agreement, the testing checklist, the covering letter
		# and the net meter request likewise (api/form3_print, api/kseb_agreement_print,
		# api/kseb_checklist_print, api/kseb_covering_print, api/kseb_netmeter_print).
		from a3_sola.api import (form3_print, kseb_agreement_print, kseb_checklist_print, kseb_covering_print,
			kseb_netmeter_print)

		return {m.CODE: m.prints(installation) for m in (form3_print, kseb_agreement_print, kseb_checklist_print,
			kseb_covering_print, kseb_netmeter_print)}
	if row.stage_code == "ACPT":
		# The PM Surya Ghar portal's Net Metering Agreement (api/net_metering_print).
		from a3_sola.api import net_metering_print

		return {net_metering_print.CODE: net_metering_print.prints(installation)}
	if row.stage_code == "NPA":
		# The quotation in the RIM format, as the bank gets it (api/loan_print.quotation),
		# once the job has a quotation.
		from a3_sola.api import loan_print

		if not frappe.db.get_value("Solar Installation", installation, "quotation"):
			return {}
		return {loan_print.QUOTATION: [{"label": _("Print"), "url": loan_print.quotation_url(installation),
			"signable": True}]}
	if row.stage_code == "STMP":
		from a3_sola.api import stamp_print

		return {stamp_print.CODE: [{"label": _("Download"), "url": stamp_print.url(installation, row.task_document)}]}
	if row.stage_code == "CFILE":
		# The customer's request to KSEBL for the registration fee refund, to sign.
		from a3_sola.api import refund_print

		return {refund_print.CODE: refund_print.prints(installation)}
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
		out.append({"name": "Jan Samarth approval letter", "kind": "Expected", "files": [], "missing": [], "note": _("Not needed - not financed.")})
	else:
		task = frappe._dict(name=dal.task_document if dal and dal.task_doctype == "Installation Task" else None,
			solar_installation=inst.name)
		files = [{"label": "", "url": f["file_url"]} for f in approval_letters(task)]
		out.append({"name": "Jan Samarth approval letter", "kind": "Uploaded" if files else "Expected", "files": files,
			"missing": [] if files else [{"label": "Jan Samarth approval letter",
				"upload": {"kind": "task", "task_code": "DAL", "document_name": "Jan Samarth approval letter"}}]})

	out.append(_surya_ghar_entry(inst))

	consumer = inst.get("solar_consumer")
	readable = consumer and frappe.has_permission("Solar Consumer", "read", consumer)
	have = consumer_files(consumer) if readable else {}
	for label, types in LOAN_PACK_CONSUMER:
		if not readable:
			out.append({"name": label, "kind": "Expected", "files": [], "missing": [], "note": _("No access to the customer.")})
			continue
		files = [{"label": t if len(types) > 1 else "", "url": url} for t in types for url in have.get(t, [])]
		missing = [{"label": t, "upload": {"kind": "consumer", "consumer": consumer, "document_type": t}}
			for t in types if not have.get(t)]
		out.append({"name": label, "kind": "Uploaded" if files and not missing else "Expected",
			"files": files, "missing": missing})
	return out


#: The PM Surya Ghar registration task, whose papers the bank also asks for.
SURYA_GHAR_TASK = "NPA"


def _surya_ghar_entry(inst):
	"""The PM Surya Ghar registration's papers - the application data sheet, the portal
	acknowledgement and anything else filed under that task - as one row of the loan pack,
	with an upload into that task for each required one still missing. What is uploaded in
	either place is the same register row, so it shows in both."""
	label = _("PM Surya Ghar registration")
	task = next((r for r in inst.stages if r.stage_code == SURYA_GHAR_TASK), None)
	if not task or task.status == "Skipped":
		return {"name": label, "kind": "Expected", "files": [], "missing": [], "note": _("Not needed - not subsidised.")}
	docs = [d for d in inst.documents if d.stage_code == SURYA_GHAR_TASK]
	files = [{"label": d.document_name, "url": d.attachment} for d in docs if d.attachment]
	missing = [{"label": d.document_name, "upload": {"kind": "task", "task_code": SURYA_GHAR_TASK,
		"document_name": d.document_name}} for d in docs if not d.attachment and d.is_mandatory]
	return {"name": label, "kind": "Uploaded" if files and not missing else "Expected", "files": files, "missing": missing}


def consumer_files(consumer):
	"""The customer's files by document type - typed on upload on it or on its lead, or a KYC row's."""
	from a3_sola.api import kyc

	return kyc.files_by_type(consumer, frappe.db.get_value("Solar Consumer", consumer, "lead"))
