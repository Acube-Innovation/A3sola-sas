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
	COLLECTIONS, DETAIL_SLUGS, get_collection, form_fields, desk_route, load_record,
	edit_allowlist, needs_prompt_name, record_route,
)

TRUE = {"1", "true", "on", "yes"}


@frappe.whitelist()
def create_record(slug=None, source_dt=None, source=None, **values):
	cfg = get_collection(slug)
	doctype = cfg["doctype"]
	meta = frappe.get_meta(doctype)
	specs, _unrenderable = form_fields(meta)
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
