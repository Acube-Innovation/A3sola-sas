# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Administration > Page Layout: an admin hides fields, sections and parts of the portal's
pages from everyone.

Two kinds of thing can be hidden:

- On a record's pages (a customer, a survey, an eligibility check...), any field or whole
  section of its doctype: it leaves the create form, the edit form and the detail page alike.
  A mandatory field cannot be hidden, as the record could then not be saved.
- On a page laid out by hand (the design proposal's builder), the named parts in `PARTS`.

Hidden only: the desk is unchanged and nothing is deleted, so ticking it again brings it
back. Kept in A3 Sola Settings (hidden_page_parts), one entry per line - "Doctype:fieldname"
for a field, "part:page:key" for a part.
"""

import json

import frappe
from frappe import _

from a3_sola.api.portal_users import require_admin

SETTINGS = "A3 Sola Settings"
FIELD = "hidden_page_parts"
ROUTE = "/a3solaportal/page-layout"

#: The parts of the hand-laid pages that may be hidden: {page: {label, parts: [{key, label,
#: hint, selector}]}}. The selector is the part's own element on that page; hiding writes a
#: CSS rule for it, so a part never needs a change to its page to be hideable.
PARTS = {
	"design": {
		"label": "Solar Design Proposal - System & commercials",
		"parts": [
			{"key": "option_bar", "label": "Option bar",
				"hint": "The whole box under the option tabs: the option's name, its summary, download, WhatsApp and Save. Save all, at the top, still saves every option.",
				"selector": "#de-tabhead"},
			{"key": "option_summary", "label": "Option summary",
				"hint": "Only the option's name and its size, connection, system type, subsidy, package and price. Download, WhatsApp and Save stay.",
				"selector": "#de-tabhead .a3s-de-tabhead__main"},
			{"key": "option_share", "label": "Download and WhatsApp buttons",
				"hint": "The option's PDF download and Send to WhatsApp buttons.",
				"selector": "#de-tabhead #de-pdf-link, #de-tabhead #de-whatsapp"},
			{"key": "steps", "label": "Steps line",
				"hint": "1 · Proposal details, 2 · System & commercials, 3 · Proposal, above the title.",
				"selector": "#de-steps"},
			{"key": "next_step", "label": "Create Proposal under the commercials",
				"hint": "The next-step button and its line at the foot of the Commercials card.",
				"selector": "#de-com-print"},
		],
	},
}


# ------------------------------------------------------------------ reading
def _entries():
	"""Every hidden entry, read once per request."""
	cached = getattr(frappe.local, "a3s_hidden_page_parts", None)
	if cached is None:
		value = frappe.db.get_single_value(SETTINGS, FIELD) or ""
		cached = frappe.local.a3s_hidden_page_parts = {line.strip() for line in value.splitlines() if line.strip()}
	return cached


def hidden_fields(doctype):
	"""The fields of `doctype` an admin has hidden from the portal."""
	prefix = doctype + ":"
	return {e[len(prefix):] for e in _entries() if e.startswith(prefix) and not e.startswith("part:")}


def hidden_css():
	"""A CSS rule hiding every part an admin has hidden, for the shell's <head>; "" if none.
	The selectors are this module's own, never typed by anyone."""
	selectors = [part["selector"] for page, spec in PARTS.items() for part in spec["parts"]
		if "part:{0}:{1}".format(page, part["key"]) in _entries()]
	return "{0} {{ display: none !important; }}".format(", ".join(selectors)) if selectors else ""


# ------------------------------------------------------------------ the admin page
def _record_pages():
	"""The record pages, one per doctype: {doctype: label}, in menu order."""
	from a3_sola.www.a3solaportal.collections import COLLECTIONS

	out = {}
	for cfg in COLLECTIONS.values():
		out.setdefault(cfg["doctype"], cfg.get("title") or cfg["doctype"])
	return out


def pages():
	"""The pages that can be laid out, for the page's list: designed pages first, then the
	record pages, each with how much is hidden on it."""
	entries = _entries()
	out = [{"key": "part:" + page, "label": spec["label"], "kind": "Page",
		"hidden": sum("part:{0}:{1}".format(page, p["key"]) in entries for p in spec["parts"])}
		for page, spec in PARTS.items()]
	for doctype, label in _record_pages().items():
		if frappe.db.exists("DocType", doctype):
			out.append({"key": doctype, "label": label, "kind": "Record", "hidden": len(hidden_fields(doctype))})
	return out


def page(key):
	"""One page's layout: its sections, each with its fields (or a designed page's parts), and
	whether each is shown."""
	entries = _entries()
	if key.startswith("part:"):
		name = key[len("part:"):]
		spec = PARTS.get(name)
		if not spec:
			frappe.throw(_("Unknown page: {0}").format(name))
		return {"key": key, "label": spec["label"], "sections": [{"label": _("Parts of the page"), "fields": [
			{"name": p["key"], "label": _(p["label"]), "hint": _(p["hint"]),
				"shown": "part:{0}:{1}".format(name, p["key"]) not in entries, "locked": False}
			for p in spec["parts"]]}]}

	from a3_sola.www.a3solaportal.collections import STATIC_HIDDEN, form_groups

	pages_ = _record_pages()
	if key not in pages_:
		frappe.throw(_("Unknown page: {0}").format(key))
	meta = frappe.get_meta(key)
	off = hidden_fields(key)
	always_off = set(STATIC_HIDDEN.get(key, ()))
	sections = []
	for g in form_groups(meta, pages_[key]):
		for s in g["sections"]:
			fields = [{"name": df.fieldname, "label": _(df.label or df.fieldname),
				"hint": _("Required: always shown.") if df.reqd else "",
				"shown": df.fieldname not in off, "locked": bool(df.reqd)}
				for df in s["fields"] if df.fieldname not in always_off]
			if fields:
				label = s["label"] if s["label"] and s["label"] != g["label"] else ""
				sections.append({"label": " / ".join(filter(None, [g["label"], label])), "fields": fields})
	return {"key": key, "label": pages_[key], "sections": sections}


@frappe.whitelist()
def get_page(key=None):
	require_admin()
	return page(key or "")


@frappe.whitelist(methods=["POST"])
def save(key=None, hidden=None):
	"""Hide `hidden` (a list of fieldnames, or of part keys) on page `key`, and show the rest of it.
	Other pages' entries are kept as they are."""
	require_admin()
	layout = page(key or "")
	names = json.loads(hidden) if isinstance(hidden, str) else hidden or []
	known = {f["name"]: f for s in layout["sections"] for f in s["fields"]}
	unknown = [n for n in names if n not in known]
	if unknown:
		frappe.throw(_("Not on this page: {0}").format(", ".join(unknown)))
	locked = [known[n]["label"] for n in names if known[n]["locked"]]
	if locked:
		frappe.throw(_("Required, so always shown: {0}").format(", ".join(locked)))

	prefix = key + ":"
	kept = {e for e in _entries() if not (e.startswith(prefix) and e[len(prefix):] in known)}
	value = "\n".join(sorted(kept | {prefix + n for n in names}))
	frappe.db.set_single_value(SETTINGS, FIELD, value)
	frappe.local.a3s_hidden_page_parts = None
	return {"page": page(key), "pages": pages()}
