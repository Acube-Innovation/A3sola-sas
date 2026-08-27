# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Per-company uniqueness for master data.

Under the multi-company tenancy model every tenant needs its own copy of the masters -
its own KSEB, its own "RCC Flat", its own package codes. A database-level unique index is
therefore wrong: it would let the first tenant claim a name globally and block every
tenant after it. Uniqueness is scoped to the company instead, and enforced here so all the
masters do it identically.
"""

import frappe
from frappe import _


def assert_unique_in_company(doc, fields, label=None):
	"""Raise if another document in the same company already uses these field values."""
	filters = {"name": ["!=", doc.name]}
	if doc.get("company"):
		filters["company"] = doc.company
	for field in fields:
		value = doc.get(field)
		if not value:
			return
		filters[field] = value

	existing = frappe.db.get_value(doc.doctype, filters, "name")
	if not existing:
		return

	shown = " / ".join(str(doc.get(f)) for f in fields)
	frappe.throw(
		_("{0} {1} already exists in {2} as {3}.").format(
			_(label or doc.doctype),
			frappe.bold(shown),
			doc.get("company") or _("this site"),
			frappe.utils.get_link_to_form(doc.doctype, existing),
		),
		title=_("Duplicate {0}").format(_(doc.doctype)),
	)
