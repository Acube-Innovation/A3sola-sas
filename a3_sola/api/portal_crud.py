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
from a3_sola.api.portal_fields import NUMERIC_TYPES
from a3_sola.www.a3solaportal.collections import (
	COLLECTIONS, DETAIL_SLUGS, SUBMIT_SLUGS, get_collection, form_fields, desk_route,
	load_record, edit_allowlist, needs_prompt_name, record_route,
)

TRUE = {"1", "true", "on", "yes"}


@frappe.whitelist()
def create_record(slug=None, source_dt=None, source=None, **values):
	cfg = get_collection(slug)
	doctype = cfg["doctype"]
	meta = frappe.get_meta(doctype)
	specs, _unrenderable = form_fields(meta, None, cfg.get("form_extra") or ())
	allowed = {s["fieldname"]: s for s in specs}

	doc = frappe.new_doc(doctype)

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
	step, source_doc = None, None
	if source_dt and source:
		step, source_doc = _load_source(slug, source_dt, source)
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

	doc.insert()

	# Only once the record exists: the source now points at it, so the button on the
	# source's page becomes the card for this record.
	if step and source_doc:
		portal_chain.link_back(step, source_doc, doc.name)

	route = record_route(slug, doc.name) if slug in DETAIL_SLUGS else f"/a3solaportal/{slug}"
	return {"name": doc.name, "route": route, "desk": desk_route(doctype, doc.name)}


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
	if not step or not step.get("via"):
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

	doc = frappe.get_attr(step["via"])(source)
	doc.insert()
	return {"name": doc.name, "route": record_route(slug, doc.name), "desk": desk_route(step["doctype"], doc.name)}


#: What a portal image upload will accept. Narrow on purpose: this endpoint exists to put
#: a photograph on a record, not to become a general file store.
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@frappe.whitelist()
def upload_image(slug=None, fieldname=None, name=None):
	"""Store one uploaded picture and return its URL for the form to carry.

	The field must be an Attach Image on that collection's own doctype, so this cannot be
	pointed at some other field or doctype. The file is saved private and returned as a
	URL; the form posts it back like any other value, which is what lets the same endpoint
	serve both the create form, where no record exists yet, and the edit form.
	"""
	cfg = get_collection(slug)
	doctype = cfg["doctype"]
	df = frappe.get_meta(doctype).get_field(fieldname)
	if not df or df.fieldtype != "Attach Image":
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
	if len(content) > MAX_IMAGE_BYTES:
		frappe.throw(_("That picture is larger than 5MB."), frappe.ValidationError)
	if (upload.content_type or "").split(";")[0] not in IMAGE_TYPES:
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

	Only the sales order, and only through `doc.submit()`. That matters: submitting the
	order is what opens the Solar Installation, its document register and its billing
	plan, and all of that hangs off the `on_submit` hook. Calling `submit` rather than
	reproducing any of it here means the portal and the desk run the identical code, and
	a change to the handoff is picked up by both without this function being touched.
	"""
	if slug not in SUBMIT_SLUGS:
		frappe.throw(_("A {0} cannot be submitted from the portal.").format(slug), frappe.PermissionError)
	doc = load_record(slug, name, "submit")
	if cint(doc.docstatus) != 0:
		frappe.throw(_("{0} is not a draft.").format(name), frappe.ValidationError)
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
	for fieldname, spec in edit_allowlist(doc).items():
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
	doc.save()
	return {"name": doc.name, "route": record_route(slug, doc.name)}
