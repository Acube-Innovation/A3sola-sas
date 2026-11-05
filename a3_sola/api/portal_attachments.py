# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A record's attachments on the portal: the files the desk's sidebar shows, listed,
uploaded and removed from the record's view and edit pages.

They are ordinary File records attached to the document, so a file added here is the one
the desk shows, and the Snapshot's Attachments count is a count of them. Reading needs
read permission on the record; adding or removing needs write permission on it, as the
desk asks. Files are stored private: they open only for someone who can read the record.

Each file says what it is - the KSEB bill, an Aadhaar face, the PAN - in File's
`a3s_document_type`, chosen when it is uploaded and fixed from then on. On a Solar Consumer a file of one of the KYC types is also its row in
the consumer's KYC Documents, which the KYC status, the sales order and the job's register
read, so a PAN uploaded here counts as the PAN. A typed file on the lead counts for its
customer too (api/kyc), so the customer's KYC status is re-derived after every change.
"""

import frappe
from frappe import _
from frappe.utils import format_datetime
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api import document_evidence, task_files


def _record(doctype, name, ptype):
	if not (doctype and name) or not frappe.db.exists(doctype, name):
		raise frappe.DoesNotExistError(_("That record does not exist."))
	frappe.has_permission(doctype, ptype, name, throw=True)


CONSUMER = "Solar Consumer"


def document_types(doctype=None, name=None, installation=None, task=None):
	"""What a file may be filed as: on a project task's record, the task's own documents first
	("Portal acknowledgement"), then the general types (api/task_files)."""
	from a3_sola.api import task_files
	from a3_sola.setup.custom_fields import DOCUMENT_TYPES

	general = [o for o in DOCUMENT_TYPES.split("\n") if o]
	own = task_files.names_for(doctype, name, installation, task) if (doctype or installation) else []
	return own + [g for g in general if g not in own]


#: The types the Attachments card offers, where a record keeps to a few: a customer's KYC papers.
#: A file of another type - the KYC card's pre-installation photo - is still accepted.
OFFERED = {CONSUMER: ("Aadhaar Front", "Aadhaar Back", "KSEB Bill", "Bank Proof", "PAN")}


def offered_types(doctype=None, name=None, installation=None, task=None):
	"""The card's list of types: the record's few, or all it may be filed as."""
	return list(OFFERED.get(doctype) or document_types(doctype, name, installation, task))


def _kyc_types():
	return set((frappe.get_meta("Customer KYC Document").get_options("kyc_type") or "").split("\n")) - {""}


def _check_type(document_type, doctype=None, name=None):
	if document_type and document_type not in document_types(doctype, name):
		frappe.throw(_("{0} is not a document type.").format(document_type), frappe.ValidationError)


def _sync_kyc(consumer_name, file_url, document_type):
	"""Make the consumer's KYC row for this file say `document_type`: added, retyped, or -
	for no type, or one that is not a KYC type - removed. Saved, so the KYC status follows."""
	consumer = frappe.get_doc(CONSUMER, consumer_name)
	rows = [r for r in consumer.get("kyc_documents") or [] if r.attachment == file_url]
	wanted = document_type if document_type in _kyc_types() else None
	if wanted and rows:
		changed = any(r.kyc_type != wanted for r in rows)
		for r in rows:
			r.kyc_type = wanted
	elif wanted:
		consumer.append("kyc_documents", {"kyc_type": wanted, "attachment": file_url})
		changed = True
	else:
		changed = bool(rows)
		consumer.set("kyc_documents", [r for r in consumer.get("kyc_documents") or [] if r.attachment != file_url])
	if changed:
		# A KYC row recorded, not the customer finished: its required fields are asked for when
		# its form is saved (a customer made from its lead has no consumer number yet).
		consumer.flags.ignore_mandatory = True
		consumer.save(ignore_permissions=True)


#: Document types a record holds one of: a newer one replaces the one before.
SINGLE_TYPES = ("KSEB Bill", "Aadhaar Front", "Aadhaar Back", "Digital Approval Letter", "PM Surya Ghar Acknowledgement",
	"Feasibility Report")
#: A file of one of these types on the record is also the value of its Attach field.
FILE_FIELDS = {("Installation Task", "Feasibility Report"): "feasibility_report"}


def _fill_field(doctype, name, document_type, file_url):
	"""The record's Attach field for this type holds the file."""
	field = FILE_FIELDS.get((doctype, document_type))
	if field:
		frappe.db.set_value(doctype, name, field, file_url)


def _clear_field(doctype, name, file_url):
	for (dt, _type), field in FILE_FIELDS.items():
		if dt == doctype and frappe.db.get_value(doctype, name, field) == file_url:
			frappe.db.set_value(doctype, name, field, None)


def supersede(doctype, name, document_type, file_url):
	"""The record's file at `file_url` is now its `document_type`: of a type it holds one of
	(SINGLE_TYPES), only the newest file at that URL is kept - the same bill uploaded twice is
	one File per upload, at one URL - and the other files of the type are removed, with, on a
	customer, their KYC rows and any row of that type on another file (an e-Aadhaar's back,
	once a photo of the back replaces it)."""
	if document_type not in SINGLE_TYPES:
		return
	files = frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name,
		"a3s_document_type": document_type, "is_folder": 0}, fields=["name", "file_url"], order_by="creation desc")
	keep = next((f for f in files if f.file_url == file_url), None)
	if not keep:
		return
	older = [f for f in files if f.name != keep.name]
	if doctype == CONSUMER:
		consumer = frappe.get_doc(CONSUMER, name)
		rows = consumer.get("kyc_documents") or []
		gone = {f.file_url for f in older} - {file_url}
		kept, seen = [], set()
		for r in rows:
			if r.attachment in gone or (r.kyc_type == document_type and r.attachment != file_url):
				continue
			if (r.kyc_type, r.attachment) in seen:  # the same file's row twice
				continue
			seen.add((r.kyc_type, r.attachment))
			kept.append(r)
		if len(kept) != len(rows):
			consumer.set("kyc_documents", kept)
			# A KYC row recorded, not the customer finished: its required fields are asked for when
			# its form is saved (a customer made from its lead has no consumer number yet).
			consumer.flags.ignore_mandatory = True
			consumer.save(ignore_permissions=True)
	for f in older:
		frappe.delete_doc("File", f.name, ignore_permissions=True)


def _refresh_kyc(doctype, name):
	"""The customer's KYC status, after a file came or went on it or on its lead."""
	if doctype in (CONSUMER, "Lead"):
		from a3_sola.api import kyc

		kyc.refresh(kyc.pair(doctype, name)[0])


def _files(doctype, name):
	rows = frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name, "is_folder": 0},
		fields=["name", "file_name", "file_url", "file_size", "owner", "creation", "a3s_document_type"],
		order_by="creation desc")
	# A KYC file added on the desk carries no type of its own; its KYC row says what it is.
	kyc = {r.attachment: r.kyc_type for r in frappe.get_all("Customer KYC Document",
		filters={"parent": name, "parenttype": CONSUMER}, fields=["attachment", "kyc_type"])} if doctype == CONSUMER else {}
	can_write = bool(frappe.has_permission(doctype, "write", name))
	names = {r.owner for r in rows}
	full = dict(frappe.get_all("User", filters={"name": ["in", list(names)]}, fields=["name", "full_name"], as_list=True)) if names else {}
	return [{
		"name": r.name, "file_name": r.file_name or r.name, "file_url": r.file_url,
		"document_type": r.a3s_document_type or kyc.get(r.file_url) or "",
		"size": frappe.utils.cint(r.file_size), "by": full.get(r.owner) or r.owner,
		"on": format_datetime(r.creation, "d MMM yyyy, h:mm a"), "can_remove": can_write,
	} for r in rows]


@frappe.whitelist()
def list_files(doctype, name):
	_record(doctype, name, "read")
	can_write = bool(frappe.has_permission(doctype, "write", name))
	return {"files": _files(doctype, name), "can_upload": can_write,
		"document_types": offered_types(doctype, name), "max_file_mb": get_max_file_size() // (1024 * 1024),
		# The types a row's Read button reads again into the form - only for someone who can save it.
		"readable": _readable(doctype) if can_write else []}


def _readable(doctype):
	return sorted(t for (dt, t) in READERS if dt == doctype)


# ------------------------------------------------------------------ reading a file again
def _read_kseb(doctype, name, content, filename, password):
	from a3_sola.api import kseb_bill

	return kseb_bill.read_content(content, filename, doctype)


def _read_aadhaar_front(doctype, name, content, filename, password):
	from a3_sola.api import aadhaar_card

	return aadhaar_card.read_content(content, filename, password, "front")


def _read_aadhaar_back(doctype, name, content, filename, password):
	from a3_sola.api import aadhaar_card

	return aadhaar_card.read_content(content, filename, password, "back")


def _read_bank(doctype, name, content, filename, password):
	from a3_sola.api import bank_document

	known = frappe.db.get_value(CONSUMER, name, "consumer_name") if name else None
	fields, warnings = bank_document.read_content(content, filename, known)
	return {"fields": fields, "warnings": warnings}


def _read_letter(doctype, name, content, filename, password):
	from a3_sola.api import approval_letter

	found, source = approval_letter.read_content(content, filename)
	return {"fields": approval_letter.task_values(found), "warnings": approval_letter.warnings(found, task=name),
		"source": source}


def _read_ack(doctype, name, content, filename, password):
	from a3_sola.api import portal_ack
	from a3_sola.api.kseb_bill import extract_text

	text, source = extract_text(content, filename)
	if not portal_ack.is_acknowledgement(text):
		frappe.throw(_("This does not look like the National Portal's acknowledgement."), title=_("Not Read"))
	found = portal_ack.parse(text)
	installation = frappe.db.get_value(doctype, name, "solar_installation") if name else None
	return {"fields": portal_ack.fields_of(found), "warnings": portal_ack.warnings(found, installation), "source": source}


#: (doctype, document type): how a file of that type on that record is read into its form.
READERS = {
	("Lead", "KSEB Bill"): _read_kseb, (CONSUMER, "KSEB Bill"): _read_kseb,
	(CONSUMER, "Aadhaar Front"): _read_aadhaar_front, (CONSUMER, "Aadhaar Back"): _read_aadhaar_back,
	(CONSUMER, "Bank Proof"): _read_bank, (CONSUMER, "Bank Passbook"): _read_bank, (CONSUMER, "Cancelled Cheque"): _read_bank,
	("Installation Task", "Digital Approval Letter"): _read_letter,
	("Portal Application", "PM Surya Ghar Acknowledgement"): _read_ack,
}


@frappe.whitelist(methods=["POST"])
def read_file(doctype, name, file, password=None):
	"""Read one of the record's attached files again - its KSEB bill, Aadhaar card, passbook or
	cheque - and return the form's fields from it. Nothing is saved: the page fills its form,
	and the person checks it and saves."""
	_record(doctype, name, "write")
	_attached_url(doctype, name, file)
	document_type = next((f["document_type"] for f in _files(doctype, name) if f["name"] == file), None)
	reader = READERS.get((doctype, document_type))
	if not reader:
		frappe.throw(_("A {0} cannot be read into this form.").format(document_type or _("file of no type")),
			frappe.ValidationError)
	doc = frappe.get_doc("File", file)
	out = reader(doctype, name, doc.get_content(), doc.file_name or file, password)
	# What it was read as, kept on it: the eligibility check's evidence (api/document_evidence).
	document_evidence.store(file, out.get("fields"))
	if doctype == CONSUMER and len(out.get("sides") or []) == 2:
		_both_sides(name, doc.file_url)
	return dict(out, document_type=document_type)


def _both_sides(consumer_name, file_url):
	"""One Aadhaar file with both sides - a PDF of the front and the back - is the customer's
	Aadhaar Front and Aadhaar Back: a KYC row for each, so neither is asked for again."""
	consumer = frappe.get_doc(CONSUMER, consumer_name)
	rows = consumer.get("kyc_documents") or []
	added = False
	for kind in ("Aadhaar Front", "Aadhaar Back"):
		if not any(r.kyc_type == kind and r.attachment == file_url for r in rows):
			consumer.append("kyc_documents", {"kyc_type": kind, "attachment": file_url})
			added = True
	if added:
		consumer.flags.ignore_mandatory = True
		consumer.save(ignore_permissions=True)
		_refresh_kyc(CONSUMER, consumer_name)


@frappe.whitelist(methods=["POST"])
def read_upload(doctype, document_type, password=None, name=None):
	"""Read the document posted as `file` into a form whose record is not created yet: its
	fields, nothing kept - the card holds the file and uploads it once the record is saved."""
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	reader = READERS.get((doctype, document_type))
	if not reader:
		frappe.throw(_("A {0} cannot be read into this form.").format(document_type), frappe.ValidationError)
	upload = (frappe.request.files.getlist("file") or [None])[0] if frappe.request and frappe.request.files else None
	if not upload:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	content = upload.stream.read()
	if len(content) > get_max_file_size():
		frappe.throw(_("{0} is larger than {1} MB.").format(upload.filename, get_max_file_size() // (1024 * 1024)),
			frappe.ValidationError)
	return dict(reader(doctype, None, content, upload.filename, password), document_type=document_type)


@frappe.whitelist()
def held_card(doctype, installation=None, task=None):
	"""The card's choices for a record not yet created: the types, the size limit, and whether
	the person may create one - its files are held on the card until it is."""
	can_create = bool(frappe.has_permission(doctype, "create"))
	return {"files": [], "can_upload": can_create,
		"document_types": offered_types(doctype, None, installation, task), "max_file_mb": get_max_file_size() // (1024 * 1024),
		# Read with Read (read_upload), the form filled before it is saved.
		"readable": _readable(doctype) if can_create else []}


@frappe.whitelist(methods=["POST"])
def upload(doctype, name, document_type=None):
	"""Attach each file posted as `file` to the record, private, as `document_type`, and
	return the new list."""
	_record(doctype, name, "write")
	_check_type(document_type, doctype, name)
	uploads = frappe.request.files.getlist("file") if frappe.request and frappe.request.files else []
	if not uploads:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	limit = get_max_file_size()
	for upload in uploads:
		content = upload.stream.read()
		if len(content) > limit:
			frappe.throw(_("{0} is larger than {1} MB.").format(upload.filename, limit // (1024 * 1024)),
				frappe.ValidationError)
		try:
			file = frappe.get_doc({
				"doctype": "File", "file_name": upload.filename, "content": content, "is_private": 1,
				"attached_to_doctype": doctype, "attached_to_name": name, "a3s_document_type": document_type or None,
			}).insert(ignore_permissions=True)
		except frappe.ValidationError:
			raise
		except Exception:
			# Frappe reads every PDF for embedded scripts; a damaged one cannot be read.
			frappe.throw(_("{0} could not be read. If it is a PDF, it may be damaged - save it again and retry.").format(
				upload.filename), frappe.ValidationError)
		if doctype == CONSUMER and document_type:
			_sync_kyc(name, file.file_url, document_type)
		# Several of a one-only type sent together: the last one sent is kept.
		supersede(doctype, name, document_type, file.file_url)
		# A project task's record: the file is the task's document on the board's panel too.
		task_files.on_attached(doctype, name, document_type, file.file_url)
		_fill_field(doctype, name, document_type, file.file_url)
		if doctype == "Installation Task" and document_type == "Digital Approval Letter":
			from a3_sola.api import approval_letter

			approval_letter.fill_task(name, content, upload.filename)
		if doctype == "Portal Application" and document_type == "PM Surya Ghar Acknowledgement":
			from a3_sola.api import portal_ack

			portal_ack.fill_document(name, content, upload.filename)
	_refresh_kyc(doctype, name)
	return {"files": _files(doctype, name)}



@frappe.whitelist(methods=["POST"])
def set_type(doctype, name, file, document_type=None):
	"""Say what one of the record's files is - once. A file's type is fixed when it is set:
	it is what the file was filed as, so a wrong one is removed and uploaded again."""
	_record(doctype, name, "write")
	_check_type(document_type, doctype, name)
	if not document_type:
		frappe.throw(_("Choose the document type."), frappe.ValidationError)
	file_url = _attached_url(doctype, name, file)
	current = next((f["document_type"] for f in _files(doctype, name) if f["name"] == file), None)
	if current:
		frappe.throw(_("{0} is already filed as {1}. To change it, remove the file and upload it again.").format(
			frappe.db.get_value("File", file, "file_name"), current), frappe.ValidationError)
	frappe.db.set_value("File", file, "a3s_document_type", document_type or None)
	if doctype == CONSUMER:
		_sync_kyc(name, file_url, document_type)
	supersede(doctype, name, document_type, file_url)
	task_files.on_attached(doctype, name, document_type, file_url)
	_fill_field(doctype, name, document_type, file_url)
	_refresh_kyc(doctype, name)
	return {"files": _files(doctype, name)}


def _attached_url(doctype, name, file):
	"""The file's URL, once it is known to be attached to this record."""
	attached = frappe.db.get_value("File", file, ["attached_to_doctype", "attached_to_name", "file_url"], as_dict=True)
	if not attached or (attached.attached_to_doctype, attached.attached_to_name) != (doctype, name):
		frappe.throw(_("That file is not attached to {0}.").format(name), frappe.PermissionError)
	return attached.file_url


@frappe.whitelist(methods=["POST"])
def remove(doctype, name, file):
	"""Remove one of the record's attachments - only one actually attached to it."""
	_record(doctype, name, "write")
	file_url = _attached_url(doctype, name, file)
	if doctype == CONSUMER:
		_sync_kyc(name, file_url, None)  # its KYC row goes with it
	frappe.delete_doc("File", file, ignore_permissions=True)
	task_files.on_removed(doctype, name, file_url)
	_clear_field(doctype, name, file_url)
	_refresh_kyc(doctype, name)
	return {"files": _files(doctype, name)}
