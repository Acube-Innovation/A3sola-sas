# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""How the portal shows and edits one field, for any doctype.

A detail page turns a value into a display row; an edit page turns a field into a form
spec. Both decisions come from the field's own metadata, so a page built from these
helpers shows a relabelled custom field under its new label without a change here. The
Lead pages and the metadata-driven collection pages share this module so the two never
render the same field two different ways.
"""

import frappe
from frappe.utils import cint, flt, fmt_money, format_date, format_datetime

# Field types a plain form can capture. Anything else is shown on the detail page only.
INPUT_TYPES = {
	"Data", "Select", "Link", "Date", "Datetime", "Int", "Float", "Currency", "Percent",
	"Check", "Small Text", "Text", "Phone",
}
# Field types a detail page can show as text or a link.
DISPLAY_TYPES = INPUT_TYPES | {"Attach", "Attach Image", "Read Only", "Long Text"}

#: A picture is the one attachment a portal form can capture: it uploads on choice
#: and the form then carries the resulting file URL like any other value.
INPUT_TYPES = INPUT_TYPES | {"Attach Image"}
NUMERIC_TYPES = {"Int", "Float", "Currency", "Percent"}
LINK_CHOICE_LIMIT = 300
TRUE = {"1", "true", "on", "yes"}


def format_value(value, df):
	"""A value as a person would read it. Plain text, never HTML."""
	if value in (None, ""):
		return ""
	fieldtype = df.fieldtype
	if fieldtype == "Check":
		return "Yes" if cint(value) else "No"
	if fieldtype == "Date":
		return format_date(value, "medium")
	if fieldtype == "Datetime":
		return format_datetime(value, "medium")
	if fieldtype == "Currency":
		return fmt_money(value)
	if fieldtype == "Percent":
		return "{0}%".format(flt(value, 1))
	if fieldtype == "Float":
		precision = cint(df.precision) if df.precision else 2
		return "{0:,.{p}f}".format(flt(value), p=precision)
	if fieldtype == "Int":
		return "{0:,}".format(cint(value))
	return str(value)


def detail_row(df, value):
	"""One label/value row for a detail page, with the kind of thing the value is."""
	row = {"fieldname": df.fieldname, "label": df.label, "kind": "text", "value": "", "href": None, "external": False}
	# A numeric field that was never filled in reads as 0; "not set" is what a person means.
	if value in (None, "") or (df.fieldtype in ("Float", "Currency", "Percent") and not flt(value)):
		row["kind"] = "empty"
		return row

	row["value"] = format_value(value, df)
	if df.fieldname == "status":
		row["kind"] = "badge"
		row["slug"] = str(value).lower().replace(" ", "-")
	elif df.options == "Email" and df.fieldtype == "Data":
		row["kind"] = "link"
		row["href"] = "mailto:" + str(value)
	elif df.options == "Phone" or df.fieldtype == "Phone":
		row["kind"] = "link"
		row["href"] = "tel:" + str(value).replace(" ", "")
	elif df.fieldname == "website":
		url = str(value)
		row["kind"] = "link"
		row["href"] = url if url.startswith(("http://", "https://")) else "https://" + url
		row["external"] = True
	elif df.fieldtype in ("Attach", "Attach Image"):
		row["kind"] = "link"
		row["href"] = str(value)
		row["value"] = "View file"
		row["external"] = True
	elif df.fieldtype in ("Small Text", "Text", "Long Text"):
		row["kind"] = "multiline"
	elif df.fieldtype in ("Select", "Check"):
		row["kind"] = "pill"
	elif df.fieldtype == "Link":
		row["value"] = link_title(df.options, value)
	return row


def link_title(doctype, name):
	"""The linked record's title where its doctype has one, else its id.

	Series-named records (SOL-DISCOM-00001) mean nothing to a person; the DISCOM's name
	does. Cached per request because a page shows the same link more than once.
	"""
	if not name or not doctype:
		return name or ""
	cache = getattr(frappe.local, "_a3s_link_titles", None)
	if cache is None:
		cache = frappe.local._a3s_link_titles = {}
	key = (doctype, name)
	if key not in cache:
		title = name
		try:
			title_field = frappe.get_meta(doctype).title_field
			if title_field and title_field != "name":
				title = frappe.db.get_value(doctype, name, title_field) or name
		except Exception:
			title = name
		cache[key] = str(title)
	return cache[key]


def link_choices(doctype, filters=None, limit=None):
	"""Options for a Link field as {value, label}, permission-checked, capped.

	The value is the record's id, because that is what the field stores; the label is its
	title, because SOL-DISCOM-00001 tells a person nothing and "KSEB" tells them
	everything. `filters` narrows the list where one field depends on another - the
	districts of the chosen state, say.
	"""
	if doctype == "User":
		# Only people who can own a record: real, enabled system users.
		filters = (filters or []) + [
			["enabled", "=", 1], ["user_type", "=", "System User"],
			["name", "not in", ["Guest", "Administrator"]],
		]
	try:
		meta = frappe.get_meta(doctype)
		title_field = meta.title_field if meta.title_field and meta.title_field != "name" else None
		fields = ["name"] + ([title_field] if title_field else [])
		rows = frappe.get_list(
			doctype, fields=fields, filters=filters, order_by=title_field or "name",
			limit_page_length=limit or LINK_CHOICE_LIMIT,
		)
	except frappe.PermissionError:
		return []
	return [
		{"value": r["name"], "label": str((r.get(title_field) if title_field else None) or r["name"])}
		for r in rows
	]


#: Link fields whose options depend on another field of the same document.
#: fieldname -> (field on the linked doctype, fieldname on this document to match).
DEPENDENT_LINKS = {
	"district": ("state", "state"),
	"a3s_district": ("state", "state"),
	"discom_section": ("discom", "discom"),
}


def link_filters(df, doc=None):
	"""Narrow a Link field's options by another field of the same record.

	A district belongs to a state and a section belongs to a DISCOM, so offering all of
	them would make the person find the right one rather than be given it.
	"""
	rule = DEPENDENT_LINKS.get(df.fieldname)
	if not rule or doc is None:
		return None
	target_field, source_field = rule
	value = doc.get(source_field) if hasattr(doc, "get") else None
	return [[target_field, "=", value]] if value else None


def edit_spec(df, value, doc=None):
	"""What a form needs to render one field with its current value."""
	spec = {
		"fieldname": df.fieldname,
		"label": df.label,
		"type": df.fieldtype,
		"reqd": bool(df.reqd),
		"value": "" if value is None else value,
		"input": "text",
	}
	if df.fieldtype == "Attach Image":
		spec["input"] = "image"
	elif df.fieldtype == "Select":
		spec["options"] = (df.options or "").split("\n")
	elif df.fieldtype == "Link":
		spec["link_doctype"] = df.options
		rule = DEPENDENT_LINKS.get(df.fieldname)
		spec["depends_field"] = rule[1] if rule else ""
		choices = link_choices(df.options, filters=link_filters(df, doc))
		# Past the limit the list is not the whole table, so offer a free-text field with
		# the fetched names as suggestions rather than a dropdown that hides the rest.
		spec["many"] = len(choices) >= LINK_CHOICE_LIMIT
		if value and not any(c["value"] == value for c in choices):
			choices.insert(0, {"value": value, "label": link_title(df.options, value)})
		spec["choices"] = choices
	elif df.fieldtype == "Check":
		spec["value"] = cint(value)
	elif df.fieldtype == "Date":
		spec["value"] = str(value)[:10] if value else ""
	elif df.fieldtype == "Datetime":
		spec["value"] = str(value)[:16].replace(" ", "T") if value else ""
	elif df.fieldtype in NUMERIC_TYPES:
		spec["input"] = "number"
		spec["step"] = "1" if df.fieldtype == "Int" else "any"
		# A decimal field that was never filled in reads as 0; leave the box empty so the
		# person is not asked to overtype a value nobody entered.
		if df.fieldtype != "Int" and not flt(value):
			spec["value"] = ""
	elif df.options == "Email":
		spec["input"] = "email"
	elif df.options == "Phone" or df.fieldtype == "Phone":
		spec["input"] = "tel"
	return spec


@frappe.whitelist()
def dependent_options(doctype=None, fieldname=None, value=None):
	"""The options for a dependent Link field, given what its source field now holds.

	Called when the form's source field changes - pick a state, get that state's
	districts. Only fields `DEPENDENT_LINKS` declares, so this cannot be used to list an
	arbitrary doctype, and the listing itself is permission-checked like any other.
	"""
	rule = DEPENDENT_LINKS.get(fieldname)
	if not rule:
		frappe.throw(frappe._("{0} does not depend on another field.").format(fieldname))
	df = frappe.get_meta(doctype).get_field(fieldname)
	if not df or df.fieldtype != "Link":
		frappe.throw(frappe._("{0} is not a link field.").format(fieldname))
	target_field = rule[0]
	filters = [[target_field, "=", value]] if value else None
	return {"choices": link_choices(df.options, filters=filters)}
