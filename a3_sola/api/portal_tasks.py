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

from a3_sola.api import documents, task_files
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
	file_url = posted_file(inst, name)
	if not file_url:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	documents.register_document(
		inst, task_code, INSTALLATION, inst.name, name, file_url, kind="Uploaded",
		template=expected.solar_document_template if expected else None,
	)
	# The same file on the task's own record, on its Attachments card (api/task_files).
	task_files.on_registered(inst, task_code, name, file_url)
	return _panel(frappe.get_doc(INSTALLATION, inst.name), task_code)


def posted_file(inst, document=None):
	"""The request's posted `file`, kept private on the job: its URL, or None when no file
	was sent. Refuses one over the size limit, or one that cannot be read. Filed as a
	`document`, it is named "<Customer> - <document>" with its own extension."""
	posted = frappe.request.files.get("file") if frappe.request and frappe.request.files else None
	if not posted:
		return None
	file_name = posted.filename
	if document:
		ext = os.path.splitext(posted.filename or "")[1]
		file_name = documents.customer_file_name(documents.job_customer(inst), document, ext)
	content = posted.stream.read()
	limit = get_max_file_size()
	if len(content) > limit:
		frappe.throw(_("{0} is larger than {1} MB.").format(posted.filename, limit // (1024 * 1024)), frappe.ValidationError)
	try:
		file = frappe.get_doc({
			"doctype": "File", "file_name": file_name, "content": content, "is_private": 1,
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
	inst.flags.ignore_mandatory = True
	inst.save(ignore_permissions=True)
	task_files.on_unregistered(inst, task_code, file_url)
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
	if task_code == JAN_SAMARTH_TASK:
		# The customer's papers first (PAN, Aadhaar, bank proof, KSEB bill, then tax papers), then
		# the task's own, the approval letter last.
		own = jan_samarth_rows(inst, rows)
		for d in own:
			d["name"] = JAN_SAMARTH_TITLES.get(d["name"], d["name"])
		letter = [d for d in own if d["name"] == "Digital Approval Letter"]
		rows = customer_rows(inst, JAN_SAMARTH_CUSTOMER, SURYA_GHAR_ANY_ONE) + \
			[d for d in own if d not in letter] + letter
	if task_code == FORM2_TASK:
		rows = form2_rows(inst, rows)
	if task_code == FORM1_TASK:
		# The customer's papers Form 1 is filled from and goes with, fetched from the customer,
		# before the form itself (as on Jan Samarth).
		rows = customer_rows(inst, FORM1_CUSTOMER) + rows
	if task_code == SURYA_GHAR_TASK:
		# The customer's own papers the portal asks for, fetched from the customer.
		rows.extend(customer_rows(inst, SURYA_GHAR_CUSTOMER, SURYA_GHAR_ANY_ONE))
	return {
		"task": {
			"code": row.stage_code, "name": row.stage_name, "status": row.status,
			"mandatory": bool(row.is_mandatory), "reason": row.skip_reason or "",
		},
		"documents": rows,
		"claims": claims_for(inst.name, task_code),
		# The loan's list is the bank's, and Jan Samarth files its letter only: nothing is added by hand.
		"fixed": task_code in ("LOAN", "DAL"),
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
		# The PM Surya Ghar portal's Net Metering Agreement (api/net_metering_print), the
		# consumer-vendor agreement (api/vendor_agreement_print) and the RIM quotation.
		from a3_sola.api import net_metering_print, vendor_agreement_print

		return {net_metering_print.CODE: net_metering_print.prints(installation),
			vendor_agreement_print.CODE: vendor_agreement_print.prints(installation), **_rim_quotation(installation)}
	if row.stage_code == "BCOM":
		# The bank's completion papers, printed live from the job (no pack to generate first):
		# the completion report and covering letter (api/bank_completion_print), the consumer-vendor
		# agreement (api/vendor_agreement_print) and the data for the completion report.
		from a3_sola.api import bank_completion_print, completion_print, vendor_agreement_print

		matl = next((r for r in frappe.get_doc(INSTALLATION, installation).stages if r.stage_code == "MATL"), None)
		notice = matl.task_document if matl and matl.task_doctype == "Material Dispatch Notice" else None
		return {**{code: bank_completion_print.prints(installation, code) for code in bank_completion_print.CODES},
			vendor_agreement_print.CODE: vendor_agreement_print.prints(installation),
			completion_print.CODE: completion_print.prints(installation, notice)}
	if row.stage_code == "DAL":
		# Jan Samarth asks for the quotation in the RIM format, as the bank gets it.
		return _rim_quotation(installation)
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


def _rim_quotation(installation):
	"""The quotation in the RIM format, as the bank gets it (api/loan_print.quotation): from
	the job's quotation, else priced from its design estimate."""
	from a3_sola.api import loan_print

	if not loan_print.has_quotation(frappe.get_doc("Solar Installation", installation)):
		return {}
	return {loan_print.QUOTATION: [{"label": _("Print"), "url": loan_print.quotation_url(installation),
		"signable": True}]}


#: What the bank receives for the loan, in order: printed by us in the RIM format, the
#: Jan Samarth approval, and the consumer's own papers - (label, consumer document types).
LOAN_PACK_CONSUMER = (
	("KYC", ("Aadhaar Front", "Aadhaar Back", "PAN")),
	("KSEB Bill", ("KSEB Bill",)),
	("Land Tax Receipt", ("Land Tax Receipt",)),
	("Building Tax Receipt", ("Building Tax Receipt",)),
	("Income Tax Return (ITR)", ("Income Tax Return",)),
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
		out.append({"name": "Digital Approval Letter", "kind": "Expected", "files": [], "missing": [], "note": _("Not needed - not financed.")})
	else:
		task = frappe._dict(name=dal.task_document if dal and dal.task_doctype == "Installation Task" else None,
			solar_installation=inst.name)
		files = [{"label": "", "url": f["file_url"]} for f in approval_letters(task)]
		out.append({"name": "Digital Approval Letter", "kind": "Uploaded" if files else "Expected", "files": files,
			"missing": [] if files else [{"label": "Digital Approval Letter",
				"upload": {"kind": "task", "task_code": "DAL", "document_name": "Digital Approval Letter"}}]})

	out.append(_surya_ghar_entry(inst))

	out.extend(customer_rows(inst, LOAN_PACK_CONSUMER))
	return out


def customer_rows(inst, wanted, any_one=()):
	"""A row per (label, document types) of the customer's own papers, read live from the
	customer and its lead: each file to open, an upload onto the customer for each type still
	missing. A label in `any_one` is complete with a file of any of its types."""
	consumer = inst.get("solar_consumer")
	readable = consumer and frappe.has_permission("Solar Consumer", "read", consumer)
	have = consumer_files(consumer) if readable else {}
	if readable:
		cheque = frappe.db.get_value("Solar Consumer", consumer, "cancelled_cheque")
		if cheque and cheque not in have.get("Cancelled Cheque", []):
			have.setdefault("Cancelled Cheque", []).append(cheque)
	out = []
	for label, types in wanted:
		if not readable:
			out.append({"name": label, "kind": "Expected", "files": [], "missing": [], "note": _("No access to the customer.")})
			continue
		files = [{"label": t if len(types) > 1 else "", "url": url} for t in types for url in have.get(t, [])]
		missing = [{"label": t, "upload": {"kind": "consumer", "consumer": consumer, "document_type": t}}
			for t in types if not have.get(t)]
		if label in any_one:
			missing = [] if files else missing[:1]
		out.append({"name": label, "kind": "Uploaded" if files and not missing else "Expected",
			"files": files, "missing": missing, "from_customer": True})
	return out


#: The customer's papers the PM Surya Ghar portal asks for, shown on its registration task from
#: the customer: fetched when the customer has them, uploaded onto the customer when not.
SURYA_GHAR_CUSTOMER = (
	("Aadhaar", ("Aadhaar Front", "Aadhaar Back")),
	("PAN", ("PAN",)),
	("KSEB Bill", ("KSEB Bill",)),
	("Bank Proof", ("Bank Proof", "Bank Passbook", "Cancelled Cheque")),
)
#: Bank proof is any one of a bank proof, the passbook or a cancelled cheque.
SURYA_GHAR_ANY_ONE = ("Bank Proof",)


#: KSEBL Form 1: the customer's KSEB bill and Aadhaar go with it, shown from the customer.
FORM1_TASK = "FRM1"
FORM1_CUSTOMER = (
	("KSEB Bill", ("KSEB Bill",)),
	("Aadhaar", ("Aadhaar Front", "Aadhaar Back")),
)

#: KSEBL Form 2 and its enclosures, in the order they go: the customer's KSEB bill, the form, the
#: SLD (Design Freeze), the panel and inverter papers, the meter test certificate (Meter Purchase).
FORM2_TASK = "FRM2"
FORM2_FORM = "Annexure / Form 2"
FORM2_COMPONENT_PAPERS = ("Solar Panel Test Certificate", "Solar Panel Data Sheet", "Inverter Data Sheet")
METER_CERTIFICATE = "Meter test certificate"


def form2_rows(inst, rows):
	from a3_sola.api.work_order_print import SLD, sld_for

	by_name = {d["name"]: d for d in rows}
	# The SLD or meter certificate filed on Form 2 itself (its own task skipped) is that row, not another.
	here = {key: (by_name.pop(name, None) or {}).get("file_url") for key, name in (("sld", SLD), ("meter", METER_CERTIFICATE))}
	out = customer_rows(inst, (("KSEB Bill", ("KSEB Bill",)),))
	if FORM2_FORM in by_name:
		out.append(by_name.pop(FORM2_FORM))
	out.append(_elsewhere_row("Approved Single Line Diagram (SLD)", sld_for(inst)[0] or here["sld"],
		_upload_to(inst, "DSGN", SLD)))
	for name in FORM2_COMPONENT_PAPERS:
		d = by_name.pop(name, None)
		if d:
			out.append(_with_component_sheet(inst, d))
	out.append(_elsewhere_row("Meter Test Certificate", meter_certificate(inst) or here["meter"],
		_upload_to(inst, "MTR", METER_CERTIFICATE)))
	return out + list(by_name.values())


def _upload_to(inst, code, document_name):
	"""Where a paper filed on another task is uploaded from here: that task, when the job has it
	and has not skipped it; else this one (Form 2)."""
	row = next((r for r in inst.stages if r.stage_code == code), None)
	target = code if row and row.status != "Skipped" else FORM2_TASK
	return {"kind": "task", "task_code": target, "document_name": document_name}


def _elsewhere_row(label, url, upload):
	"""A paper filed on another task, shown here: its file to open, or an upload into that task."""
	return {"name": label, "mandatory": True, "kind": "Uploaded" if url else "Expected",
		"files": [{"label": "", "url": url}] if url else [], "missing": [] if url else [{"label": label, "upload": upload}]}


def meter_certificate(inst):
	"""The net meter's test certificate: on the job's register (Meter Purchase, or filed here), else
	on the meter task's record."""
	filed = next((d.attachment for d in inst.documents if d.attachment
		and (d.document_name or "").lower() == METER_CERTIFICATE.lower()), None)
	return filed or frappe.db.get_value("Installation Task", {"solar_installation": inst.name,
		"meter_test_certificate": ["is", "set"]}, "meter_test_certificate", order_by="creation desc")


def _with_component_sheet(inst, d):
	"""A data sheet not yet uploaded on the job: the one attached to its panel item or inverter
	model, when there is one (a file named as a data sheet)."""
	if d.get("file_url") or "Data Sheet" not in d["name"]:
		return d
	if d["name"].startswith("Inverter"):
		owners = [("Inverter Model", r.inverter_model) for r in inst.get("inverters") or [] if r.inverter_model]
	else:
		owners = [("Item", r.panel_item) for r in inst.get("panels") or [] if r.panel_item]
	files = []
	for doctype, name in dict.fromkeys(owners):
		for f in frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name, "is_folder": 0},
				fields=["file_url", "file_name"], order_by="creation desc"):
			if "datasheet" in (f.file_name or "").lower().replace(" ", "").replace("_", "").replace("-", ""):
				files.append({"label": name, "url": f.file_url})
				break
	if not files:
		return d
	return {"row": d["row"], "name": d["name"], "mandatory": d["mandatory"], "kind": "Uploaded", "files": files,
		"missing": [], "prints": d.get("prints") or []}


#: Jan Samarth's task: its site photo and quotation are fetched where they already are.
JAN_SAMARTH_TASK = "DAL"
SITE_PHOTO = "Pre-installation site photo"
#: The customer's papers Jan Samarth asks for - KYC and tax - shown from the customer (the site photo is its own
#: row, fetched from the customer too - site_photos).
JAN_SAMARTH_CUSTOMER = (
	("PAN", ("PAN",)),
	("Aadhaar", ("Aadhaar Front", "Aadhaar Back")),
	("Bank Proof", ("Bank Proof", "Bank Passbook", "Cancelled Cheque")),
	("KSEB Bill", ("KSEB Bill",)),
	("Income Tax Return", ("Income Tax Return",)),
	("Land Tax Receipt", ("Land Tax Receipt",)),
	("Building Tax Receipt", ("Building Tax Receipt",)),
)
#: Jan Samarth's own documents' names as the panel shows them.
JAN_SAMARTH_TITLES = {SITE_PHOTO: "Pre-Installation Site Photo"}
BANK_QUOTATION = "Bank Quotation"


def jan_samarth_rows(inst, rows):
	"""Jan Samarth's site photo and quotation, when not uploaded on the task: the pre-installation
	photos filed on the customer, lead, site survey or proposal, or the survey's own images; and
	a file attached to the job's quotation when there is no quotation to print."""
	out = []
	for d in rows:
		if d.get("file_url") or "files" in d:
			out.append(d)
			continue
		files = []
		if d["name"] == SITE_PHOTO:
			files = [{"label": p["caption"], "url": p["url"]} for p in site_photos(inst)]
		elif d["name"] == BANK_QUOTATION:
			quotation = job_quotation(inst)
			files = [{"label": "", "url": u} for u in frappe.get_all("File", filters={"attached_to_doctype": "Quotation",
				"attached_to_name": quotation, "is_folder": 0}, pluck="file_url", order_by="creation desc")[:1]] if quotation else []
		if not files:
			out.append(d)
			continue
		out.append({"row": d["row"], "name": d["name"], "mandatory": d["mandatory"], "kind": "Uploaded",
			"files": files, "missing": [], "prints": d.get("prints") or []})
	return out


def job_quotation(inst):
	"""The job's quotation: the one it names, else the latest made for its customer or proposal."""
	if inst.get("quotation") and frappe.db.exists("Quotation", inst.quotation):
		return inst.quotation
	for field, value in (("solar_proposal", inst.get("solar_proposal")), ("solar_consumer", inst.get("solar_consumer"))):
		name = value and frappe.db.get_value("Quotation", {field: value, "docstatus": ["<", 2]}, "name",
			order_by="creation desc")
		if name:
			return name
	return None


def site_photos(inst):
	"""The site before the work, wherever it was filed (api/work_order_print._photos) - with the
	customer's or lead's latest site survey when the job does not name one."""
	from a3_sola.api import work_order_print

	survey = inst.get("site_survey") or (inst.get("solar_proposal") and frappe.db.get_value(
		"Solar Proposal", inst.solar_proposal, "site_survey"))
	if not survey:
		for field, value in (("solar_consumer", inst.get("solar_consumer")), ("lead", inst.get("lead"))):
			survey = value and frappe.db.get_value("Site Survey", {field: value, "docstatus": ["<", 2]}, "name",
				order_by="creation desc")
			if survey:
				break
	view = frappe._dict(solar_consumer=inst.get("solar_consumer"), lead=inst.get("lead"), site_survey=survey,
		solar_proposal=inst.get("solar_proposal"))
	return work_order_print._photos(view, work_order_print.STRUCTURE)


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
