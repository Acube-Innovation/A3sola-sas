# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A set of documents that leaves together.

Three tasks are packs: the Form 2/3 submission to KSEB, the completion pack to the bank,
the completion file the customer keeps. Each has a fixed list of items - templates the
engine renders, and prints of ERPNext documents already on the job - generated one at a
time so one failure never blanks the rest, merged into a single PDF, and the pack completes
when the recipient has it: acknowledged, sent, or handed over.
"""

import io

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime, today

from a3_sola.api import documents
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_value

LINKS = (
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
	("solar_agreement", "Solar Agreement"),
	("loan_application", "Loan Application"),
	("sales_invoice", "Sales Invoice"),
	("quotation", "Quotation"),
	("solar_om_contract", "Solar OM Contract"),
)

#: What each pack holds, in print order. A code is a Solar Document Template; an `@` item is
#: a print of a document already on the job.
PACKS = {
	"KSEB Submission": {
		"code": "KFORMS",
		"items": [
			"KSEB-FORM-2", "KSEB-FORM-3", "KSEB-COVERING-COMPLETION", "KSEB-NETMETER-REQUEST",
			"KSEB-TESTING-CHECKLIST", "@agreement_print",
		],
		"done_when": ("acknowledged_on", "ae_acknowledgement_no"),
		"done_label": "the Assistant Engineer's acknowledgement",
	},
	"Bank Completion Pack": {
		"code": "BCOM",
		"items": [
			"BANK-COVERING-COMPLETION", "BANK-COMPLETION-REPORT", "MNRE-CONSUMER-VENDOR-AGREEMENT",
			"COMPLETION-REPORT-DATA", "@photo_collage", "@sales_invoice_print",
		],
		"done_when": ("sent_to_bank_on",),
		"done_label": "the date it was sent to the bank",
	},
	"Customer Completion File": {
		"code": "CFILE",
		"items": [
			"CUST-HANDOVER-PACK", "@quotation_print", "@sales_invoice_print", "CUSTOMER-STATEMENT",
			"@work_order_print", "WARRANTY-CERTIFICATE", "CUSTOMER-CONTACTS", "KSEB-REFUND-REQUEST",
		],
		"done_when": ("handed_over_on",),
		"done_label": "the handover date",
	},
}
SPECIAL = {
	"@agreement_print": "Executed agreement",
	"@photo_collage": "Site photographs",
	"@sales_invoice_print": "Tax invoice",
	"@quotation_print": "Quotation",
	"@work_order_print": "Work order",
}


class DocumentPack(Document):
	def autoname(self):
		set_name(self, "document_pack_series_prefix", ".YYYY.-.#####", fallback="SOL-PACK")

	def validate(self):
		installation = frappe.get_cached_doc("Solar Installation", self.solar_installation)
		self.company = installation.company
		assert_same_company(self, LINKS)
		spec = PACKS.get(self.pack_type)
		if not spec:
			frappe.throw(_("Unknown pack type {0}.").format(self.pack_type))
		self.task_code = spec["code"]
		self.validate_one_open()
		self.pull_defaults(installation)
		self.set_defaults()

	def validate_one_open(self):
		other = frappe.db.get_value(
			"Document Pack",
			{
				"solar_installation": self.solar_installation,
				"pack_type": self.pack_type,
				"docstatus": 0,
				"name": ["!=", self.name],
			},
			"name",
		)
		if other:
			frappe.throw(
				_("{0} already has an open {1}, {2}. Finish or delete that one.").format(
					self.solar_installation, self.pack_type, frappe.utils.get_link_to_form("Document Pack", other)
				)
			)

	def pull_defaults(self, installation):
		"""Each pack knows which records it prints; the job already names them."""
		if self.pack_type == "KSEB Submission":
			if not self.solar_agreement:
				self.solar_agreement = frappe.db.get_value(
					"Solar Agreement",
					{"solar_installation": installation.name, "docstatus": 1, "is_terminated": 0},
					"name",
				)
			self.form2_due_date = installation.get("form2_due_on")
		elif self.pack_type == "Bank Completion Pack":
			if not self.loan_application:
				self.loan_application = installation.get("loan_application") or frappe.db.get_value(
					"Loan Application",
					{"solar_installation": installation.name, "docstatus": ["<", 2]},
					"name",
					order_by="creation desc",
				)
			if not self.loan_application:
				frappe.throw(
					_("A bank completion pack is for a financed job; {0} has no loan application.").format(
						installation.name
					),
					title=_("Not Financed"),
				)
			lender = frappe.db.get_value(
				"Loan Application", self.loan_application, ["lender", "lender_branch"], as_dict=True
			) or frappe._dict()
			self.lender_name = lender.lender
			self.lender_branch = lender.lender_branch
		elif self.pack_type == "Customer Completion File":
			self.quotation = self.quotation or installation.get("quotation")
			self.sales_invoice = self.sales_invoice or frappe.db.get_value(
				"Sales Invoice",
				{"solar_installation": installation.name, "docstatus": 1},
				"name",
				order_by="posting_date desc",
			)
			self.solar_om_contract = self.solar_om_contract or frappe.db.get_value(
				"Solar OM Contract",
				{"solar_installation": installation.name, "docstatus": ["<", 2]},
				"name",
				order_by="creation desc",
			)

	def set_defaults(self):
		if not self.assigned_by:
			self.assigned_by = frappe.session.user
		if not self.assigned_on:
			self.assigned_on = today()
		if self.status == "Completed" and not self.completed_on:
			self.completed_on = today()
		for row in self.uploads or []:
			if not row.uploaded_by:
				row.uploaded_by = frappe.session.user
				row.uploaded_on = now_datetime()

	def before_submit(self):
		if self.status == "Skipped":
			if not (self.skip_reason or "").strip():
				frappe.throw(_("A reason is mandatory when skipping a pack."))
			return
		if self.status != "Completed":
			frappe.throw(_("Set the status to Completed before submitting."), title=_("Not Finished"))
		if not (self.generated or self.uploads):
			frappe.throw(_("The pack is empty. Generate or upload its documents first."), title=_("Empty Pack"))
		spec = PACKS[self.pack_type]
		if not any(self.get(field) for field in spec["done_when"]):
			frappe.throw(
				_("Record {0} before completing the pack.").format(_(spec["done_label"])),
				title=_("Not Delivered"),
			)


# ------------------------------------------------------------------ helpers
def _load(pack, action="write"):
	doc = frappe.get_doc("Document Pack", pack)
	doc.check_permission(action)
	return doc


def _save(doc):
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()
	return doc


def _attach_pdf(doc, file_name, content):
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)
	return file_doc.file_url


def _print(doc, doctype, name, print_format=None):
	pdf = frappe.get_print(doctype, name, print_format, as_pdf=True)
	return _attach_pdf(doc, f"{name}.pdf", pdf)


def _upsert_row(doc, item, document_name, file_url, template_name=None, version=None, status="Generated"):
	row = next(
		(r for r in doc.generated if r.template_code == item and (r.document_name == document_name or not file_url)),
		None,
	) or doc.append("generated", {"template_code": item})
	row.update(
		{
			"document_name": document_name,
			"solar_document_template": template_name,
			"file": file_url,
			"template_version": version,
			"generated_on": now_datetime(),
			"generated_by": frappe.session.user,
			"status": status,
			"is_stale": 0,
		}
	)
	return row


def _special(doc, item):
	"""Prints of documents already on the job. Returns [(document_name, file_url)]."""
	installation = frappe.get_cached_doc("Solar Installation", doc.solar_installation)
	if item == "@agreement_print":
		agreement = doc.solar_agreement or frappe.db.get_value(
			"Solar Agreement", {"solar_installation": installation.name, "docstatus": 1, "is_terminated": 0}, "name"
		)
		if not agreement:
			frappe.throw(_("No executed agreement on {0}.").format(installation.name))
		return [(f"Agreement {agreement}", _print(doc, "Solar Agreement", agreement, "Solar Agreement"))]
	if item == "@photo_collage":
		from a3_sola.api import photos

		url = photos.build_collage_pdf(
			installation.name, attach_to=(doc.doctype, doc.name), title=_("Site photographs - {0}").format(doc.consumer_name or installation.name)
		)
		return [(SPECIAL[item], url)]
	if item == "@sales_invoice_print":
		invoice = doc.sales_invoice or frappe.db.get_value(
			"Sales Invoice", {"solar_installation": installation.name, "docstatus": 1}, "name", order_by="posting_date desc"
		)
		if not invoice:
			frappe.throw(_("No submitted tax invoice on {0}.").format(installation.name))
		return [(f"Invoice {invoice}", _print(doc, "Sales Invoice", invoice))]
	if item == "@quotation_print":
		quotation = doc.quotation or installation.get("quotation")
		if not quotation:
			frappe.throw(_("{0} has no quotation.").format(installation.name))
		return [(f"Quotation {quotation}", _print(doc, "Quotation", quotation))]
	if item == "@work_order_print":
		orders = frappe.get_all(
			"Installation Work Order",
			filters={"solar_installation": installation.name, "docstatus": 1},
			fields=["name", "work_order_kind"],
			order_by="creation asc",
		)
		if not orders:
			frappe.throw(_("No submitted work orders on {0}.").format(installation.name))
		return [
			(f"{o.work_order_kind or 'Work'} order {o.name}", _print(doc, "Installation Work Order", o.name))
			for o in orders
		]
	frappe.throw(_("Unknown pack item {0}.").format(item))


def _generate_item(doc, item):
	if item.startswith("@"):
		files = _special(doc, item)
		for document_name, file_url in files:
			_upsert_row(doc, item, document_name, file_url)
			documents.register_document(
				doc.solar_installation, doc.task_code, doc.doctype, doc.name, document_name, file_url, kind="Generated"
			)
		return len(files)
	result = documents.generate_document(
		doc.solar_installation, item, force=True, source_doctype=doc.doctype, source_name=doc.name
	)
	_upsert_row(doc, item, result["template"], result["file_url"], result["template_name"], result["template_version"])
	return 1


# ------------------------------------------------------------------ form actions
@frappe.whitelist()
def generate_pack(pack):
	"""Every item, each on its own footing: a failure is recorded on its row, not raised."""
	doc = _load(pack)
	if doc.docstatus != 0:
		frappe.throw(_("{0} is submitted; its contents are final.").format(doc.name))
	notes, made = [], 0
	for item in PACKS[doc.pack_type]["items"]:
		frappe.db.savepoint("a3s_pack_item")
		try:
			made += _generate_item(doc, item)
		except Exception as exc:
			frappe.db.rollback(save_point="a3s_pack_item")
			label = SPECIAL.get(item, item)
			_upsert_row(doc, item, label, None, status="Failed")
			notes.append(f"{label}: {frappe.utils.strip_html(str(exc))[:200]}")
	doc.generation_notes = "\n".join(notes) or None
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return {"generated": made, "failed": notes}


@frappe.whitelist()
def generate_item(pack, item):
	doc = _load(pack)
	if doc.docstatus != 0:
		frappe.throw(_("{0} is submitted; its contents are final.").format(doc.name))
	if item not in PACKS[doc.pack_type]["items"]:
		frappe.throw(_("{0} is not part of a {1}.").format(item, doc.pack_type))
	made = _generate_item(doc, item)
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return made


@frappe.whitelist()
def attach_upload(pack, document_name, file_url, document_date=None, reference_no=None):
	doc = _load(pack)
	if not (document_name and file_url):
		frappe.throw(_("A document name and a file are both needed."))
	doc.append(
		"uploads",
		{"document_name": document_name, "attachment": file_url, "document_date": document_date or today(),
		 "reference_no": reference_no},
	)
	documents.register_document(
		doc.solar_installation, doc.task_code, doc.doctype, doc.name, document_name, file_url,
		kind="Uploaded", reference_no=reference_no, document_date=document_date,
	)
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return doc.name


def _content(file_url):
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return None
	return frappe.get_doc("File", name).get_content()


@frappe.whitelist()
def merge_pdf(pack):
	"""One PDF in print order. Images become pages; an encrypted PDF is skipped and named."""
	from pypdf import PasswordType, PdfReader, PdfWriter

	doc = _load(pack)
	writer, notes, merged = PdfWriter(), [], 0
	sources = [(r.document_name, r.file) for r in doc.generated if r.file]
	if cint(doc.include_uploads_in_merge):
		sources += [(r.document_name, r.attachment) for r in doc.uploads if r.attachment]
	for label, url in sources:
		content = _content(url)
		if not content:
			notes.append(_("{0}: file not found, skipped").format(label))
			continue
		if content[:5] == b"%PDF-":
			try:
				reader = PdfReader(io.BytesIO(content))
				if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
					notes.append(_("{0}: password-protected, skipped").format(label))
					continue
				writer.append(reader)
				merged += 1
			except Exception as exc:
				notes.append(_("{0}: unreadable PDF ({1}), skipped").format(label, str(exc)[:80]))
			continue
		try:
			from PIL import Image

			with Image.open(io.BytesIO(content)) as image:
				page = io.BytesIO()
				image.convert("RGB").save(page, format="PDF")
			writer.append(PdfReader(io.BytesIO(page.getvalue())))
			merged += 1
		except Exception:
			notes.append(_("{0}: not a PDF or image, skipped").format(label))
	if not merged:
		frappe.throw(_("Nothing could be merged. Generate the pack first."), title=_("Empty Pack"))
	out = io.BytesIO()
	writer.write(out)
	doc.merged_pdf = _attach_pdf(doc, f"{doc.name}-pack.pdf", out.getvalue())
	doc.merged_on = now_datetime()
	doc.merge_notes = "\n".join(notes) or None
	documents.register_document(
		doc.solar_installation, doc.task_code, doc.doctype, doc.name, f"{doc.pack_type} (merged)", doc.merged_pdf,
		kind="Generated",
	)
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return {"file_url": doc.merged_pdf, "documents": merged, "skipped": notes}


def _default_recipient(doc):
	if doc.pack_type == "Customer Completion File" and doc.solar_consumer:
		return frappe.db.get_value("Solar Consumer", doc.solar_consumer, "email_id")
	return None


@frappe.whitelist()
def send(pack, recipients=None, message=None):
	"""Email the merged PDF and record the delivery the pack type expects."""
	from frappe.core.doctype.communication.email import make

	doc = _load(pack)
	if doc.docstatus != 0:
		frappe.throw(_("{0} is already submitted.").format(doc.name))
	if not doc.merged_pdf:
		merge_pdf(pack)
		doc.reload()
	recipients = recipients or _default_recipient(doc)
	if not recipients:
		frappe.throw(_("Give an email address to send the pack to."), title=_("No Recipient"))
	account = frappe.db.get_value("Email Account", {"enable_outgoing": 1}, "name")
	if not account and not frappe.flags.in_test:
		frappe.throw(
			_("No outgoing Email Account is enabled on this site, so nothing can be sent."),
			title=_("Email Not Configured"),
		)
	subject = _("{0} - {1}").format(doc.pack_type, doc.consumer_name or doc.solar_installation)
	body = message or _("Please find attached the {0} for {1}.").format(doc.pack_type.lower(), doc.consumer_name or "")
	attachments = frappe.get_all(
		"File", filters={"file_url": doc.merged_pdf, "attached_to_name": doc.name}, pluck="name", limit=1
	)
	result = make(
		doctype=doc.doctype, name=doc.name, content=body, subject=subject, recipients=recipients,
		send_email=bool(account), attachments=attachments or None,
	)
	doc.sent_on = now_datetime()
	doc.sent_to = recipients
	doc.communication = result.get("name") if isinstance(result, dict) else None
	if doc.pack_type == "KSEB Submission":
		doc.submitted_to_ae_on = doc.submitted_to_ae_on or today()
	elif doc.pack_type == "Bank Completion Pack":
		doc.sent_to_bank_on = doc.sent_to_bank_on or today()
		doc.sent_via = doc.sent_via or "Email"
	else:
		doc.handed_over_on = doc.handed_over_on or today()
		doc.handover_mode = doc.handover_mode or "Email"
		doc.handed_over_to = doc.handed_over_to or recipients
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return doc.name


@frappe.whitelist()
def mark_sent(pack, on=None, reference=None, via=None):
	"""Left with the AE, sent to the bank, or handed to the customer - by whatever means."""
	doc = _load(pack)
	on = on or today()
	if doc.pack_type == "KSEB Submission":
		doc.submitted_to_ae_on = on
	elif doc.pack_type == "Bank Completion Pack":
		doc.sent_to_bank_on = on
		doc.sent_via = via or doc.sent_via or "By Hand"
		doc.bank_reference = reference or doc.bank_reference
	else:
		doc.handed_over_on = on
		doc.handover_mode = via or doc.handover_mode or "By Hand"
		doc.handed_over_to = reference or doc.handed_over_to
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return doc.name


@frappe.whitelist()
def mark_acknowledged(pack, acknowledgement_no=None, on=None, ae_name=None, file_url=None):
	doc = _load(pack)
	if doc.pack_type != "KSEB Submission":
		frappe.throw(_("Only the KSEB submission is acknowledged by an Assistant Engineer."))
	if not (acknowledgement_no or file_url):
		frappe.throw(_("Record the acknowledgement number or attach the acknowledged copy."))
	doc.acknowledged_on = on or today()
	doc.ae_acknowledgement_no = acknowledgement_no or doc.ae_acknowledgement_no
	doc.ae_name = ae_name or doc.ae_name
	doc.submitted_to_ae_on = doc.submitted_to_ae_on or doc.acknowledged_on
	if file_url:
		doc.ae_acknowledgement = file_url
		documents.register_document(
			doc.solar_installation, doc.task_code, doc.doctype, doc.name, _("AE acknowledgement"), file_url,
			kind="Uploaded", reference_no=acknowledgement_no, document_date=doc.acknowledged_on,
		)
	if doc.status == "Pending":
		doc.status = "In Progress"
	_save(doc)
	return doc.name


@frappe.whitelist()
def complete(pack):
	"""Status Completed, then submit - the submit is what completes the installation's row."""
	doc = _load(pack)
	if doc.docstatus != 0:
		frappe.throw(_("{0} is already submitted.").format(doc.name))
	doc.status = "Completed"
	doc.completed_on = today()
	doc.save()
	doc.submit()
	return doc.name


@frappe.whitelist()
def skip(pack, reason=None):
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when skipping a pack."))
	doc = _load(pack)
	if doc.docstatus != 0:
		frappe.throw(_("{0} is already submitted.").format(doc.name))
	from a3_sola.api.stages import _require_manager

	_require_manager(_("skip a document pack"))
	doc.status = "Skipped"
	doc.skip_reason = reason.strip()
	doc.save()
	doc.submit()
	return doc.name
