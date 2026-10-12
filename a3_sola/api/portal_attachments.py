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
read, so a PAN uploaded here counts as the PAN.
"""

import frappe
from frappe import _
from frappe.utils import format_datetime
from frappe.utils.file_manager import get_max_file_size


def _record(doctype, name, ptype):
	if not (doctype and name) or not frappe.db.exists(doctype, name):
		raise frappe.DoesNotExistError(_("That record does not exist."))
	frappe.has_permission(doctype, ptype, name, throw=True)


CONSUMER = "Solar Consumer"


def document_types():
	return [o for o in (frappe.get_meta("File").get_options("a3s_document_type") or "").split("\n") if o]


def _kyc_types():
	return set((frappe.get_meta("Customer KYC Document").get_options("kyc_type") or "").split("\n")) - {""}


def _check_type(document_type):
	if document_type and document_type not in document_types():
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
		consumer.save(ignore_permissions=True)


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
	return {"files": _files(doctype, name), "can_upload": bool(frappe.has_permission(doctype, "write", name)),
		"document_types": document_types(), "max_file_mb": get_max_file_size() // (1024 * 1024)}


@frappe.whitelist(methods=["POST"])
def upload(doctype, name, document_type=None):
	"""Attach each file posted as `file` to the record, private, as `document_type`, and
	return the new list."""
	_record(doctype, name, "write")
	_check_type(document_type)
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
	return {"files": _files(doctype, name)}


@frappe.whitelist(methods=["POST"])
def set_type(doctype, name, file, document_type=None):
	"""Say what one of the record's files is - once. A file's type is fixed when it is set:
	it is what the file was filed as, so a wrong one is removed and uploaded again."""
	_record(doctype, name, "write")
	_check_type(document_type)
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
	return {"files": _files(doctype, name)}
