# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Editing a task's printed paper on the portal, from the task's documents panel.

Every paper a task prints - Form 1, the bank's quotation, the vendor agreement, the covering
letters - is generated from the job each time it is opened. Edit opens it, as generated, in an
editor on the page; what is saved is kept per job (Edited Document) and printed in its place
(documents.edited_body) until it is reset. The letterhead, the signature and seal and the page
layout are still added when it prints: what is edited is the paper's text.

Staff only, and only someone who may change the job.
"""

import re

import frappe
from frappe import _
from frappe.utils import format_datetime, now_datetime

from a3_sola.api import documents

DOCTYPE = "Edited Document"
INSTALLATION = "Solar Installation"
MAX_BYTES = 8 * 1024 * 1024


def _task_document(inst, code, doctype):
	row = next((r for r in inst.stages if r.stage_code == code), None)
	return row.task_document if row and row.task_doctype == doctype else None


def _loan(inst):
	name = frappe.db.get_value("Loan Application", {"solar_installation": inst.name, "docstatus": ["<", 2]}, "name",
		order_by="docstatus desc, creation desc")
	if not name:
		frappe.throw(_("This project has no loan application yet."))
	return name


def _generators():
	"""{edit key: (title, make)} - `make(inst)` prints the paper, which hands its HTML to the
	editor at documents.edited_body before any PDF is made."""
	from a3_sola.api import (bank_completion_print, completion_print, form1_print, form2_print, form3_print,
		kseb_agreement_print, kseb_checklist_print, kseb_covering_print, kseb_netmeter_print, loan_print,
		payment_statement_print, refund_print, stamp_print, vendor_agreement_print)

	out = {
		form1_print.CODE: (_("KSEBL Form 1"), lambda inst: form1_print.render(inst)),
		form2_print.CODE: (_("KSEBL Form 2"), lambda inst: form2_print.render(inst)),
		form3_print.CODE: (_("KSEBL Form 3"), lambda inst: form3_print.render(inst)),
		kseb_agreement_print.CODE: (_("KSEB Solar Agreement"), lambda inst: kseb_agreement_print.render(inst)),
		kseb_checklist_print.CODE: (_("Testing Checklist"), lambda inst: kseb_checklist_print.render(inst)),
		kseb_covering_print.CODE: (_("Covering Letter"), lambda inst: kseb_covering_print.render(inst)),
		kseb_netmeter_print.CODE: (_("Net Meter Request"), lambda inst: kseb_netmeter_print.render(inst)),
		payment_statement_print.CODE: (_("Payment Statement"), lambda inst: payment_statement_print.render(inst)),
		vendor_agreement_print.CODE: (_("Consumer-vendor Agreement"), lambda inst: vendor_agreement_print.render(inst)),
		completion_print.CODE: (_("Data for Completion Report"),
			lambda inst: completion_print.render(inst, _task_document(inst, "MATL", "Material Dispatch Notice"))),
		stamp_print.CODE: (_("Data for Stamp Paper"),
			lambda inst: stamp_print.pdf(inst.name, _task_document(inst, "STMP", "Solar Agreement"))),
		refund_print.CODE: (_("Refund Request"), lambda inst: refund_print.pdf(inst.name)),
		loan_print.PROPOSAL: (_("Bank Quotation (Project Proposal)"), lambda inst: loan_print.proposal(inst.name)),
	}
	for code in bank_completion_print.CODES:
		out[code] = (_("Bank Completion Paper"), lambda inst, code=code: bank_completion_print.render(inst, code))
	for key, code in loan_print.DOCUMENTS.items():
		if code not in out and key in ("letter", "feasibility", "ehs"):
			out[code] = (_(loan_print.TITLES.get(key, code)), lambda inst, key=key: loan_print.pdf(_loan(inst), key))
	return out


def editable(code):
	"""Whether a paper (by its template code) can be edited here."""
	return bool(code) and documents.edit_key(code) in _generators()


def _job(installation):
	from a3_sola.api.partner_scope import is_partner

	if is_partner():
		frappe.throw(_("Only the company's staff can edit documents."), frappe.PermissionError)
	inst = frappe.get_doc(INSTALLATION, installation)
	inst.check_permission("write")
	return inst


def generated_html(inst, code):
	"""The paper's HTML as the system generates it now."""
	key = documents.edit_key(code)
	gen = _generators().get(key)
	if not gen:
		frappe.throw(_("{0} cannot be edited here.").format(code))
	response = frappe.local.response
	kept = {k: response.get(k) for k in ("filename", "filecontent", "type")}
	frappe.flags.a3s_capture_document = key
	try:
		gen[1](inst)
	except documents.CapturedDocument as captured:
		return captured.html
	finally:
		frappe.flags.a3s_capture_document = None
		# A print that is also a download set the response up; this answer is JSON.
		for k, v in kept.items():
			if v is None:
				response.pop(k, None)
			else:
				response[k] = v
	frappe.throw(_("{0} could not be opened for editing.").format(gen[0]))


def _saved(inst_name, key):
	return frappe.db.get_value(DOCTYPE, {"solar_installation": inst_name, "document_code": key},
		["name", "html", "edited_by", "edited_on"], as_dict=True)


def _state(inst, key, saved):
	return {
		"code": key, "title": _generators()[key][0],
		"edited": bool(saved),
		"edited_by": (frappe.db.get_value("User", saved.edited_by, "full_name") or saved.edited_by) if saved else "",
		"edited_on": format_datetime(saved.edited_on, "d MMM yyyy, h:mm a") if saved and saved.edited_on else "",
	}


@frappe.whitelist()
def load(installation, code):
	"""The paper to edit: as last edited, else as generated now."""
	inst = _job(installation)
	key = documents.edit_key(code)
	saved = _saved(inst.name, key)
	html = saved.html if saved else generated_html(inst, key)
	return {**_state(inst, key, saved), "html": html}


def clean(html):
	"""What the editor sends, safe to keep and print: no script, no event handler, no
	javascript: link, nothing loaded in a frame."""
	html = html or ""
	if len(html.encode()) > MAX_BYTES:
		frappe.throw(_("The document is too large to save."))
	html = re.sub(r"<\s*(script|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>", "", html, flags=re.I | re.S)
	html = re.sub(r"<\s*(script|iframe|object|embed)\b[^>]*/?>", "", html, flags=re.I)
	html = re.sub(r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.I)
	html = re.sub(r"(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2", r"\1=\2#\2", html, flags=re.I)
	html = re.sub(r"\s*contenteditable\s*=\s*([\"'])[^\"']*\1", "", html, flags=re.I)
	return html


@frappe.whitelist(methods=["POST"])
def save(installation, code, html):
	"""Keep the paper as edited: it prints this way until it is reset."""
	inst = _job(installation)
	key = documents.edit_key(code)
	if key not in _generators():
		frappe.throw(_("{0} cannot be edited here.").format(code))
	html = clean(html)
	if not html.strip():
		frappe.throw(_("The document is empty. Reset it to bring back the generated one."))
	saved = _saved(inst.name, key)
	doc = frappe.get_doc(DOCTYPE, saved.name) if saved else frappe.new_doc(DOCTYPE)
	doc.update({"solar_installation": inst.name, "document_code": key, "document_title": _generators()[key][0],
		"html": html, "edited_by": frappe.session.user, "edited_on": now_datetime()})
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	inst.add_comment("Info", _("{0} edited on the portal by {1}.").format(doc.document_title,
		frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user))
	return _state(inst, key, _saved(inst.name, key))


@frappe.whitelist(methods=["POST"])
def reset(installation, code):
	"""Drop the edited copy: the paper is generated from the job again."""
	inst = _job(installation)
	key = documents.edit_key(code)
	saved = _saved(inst.name, key)
	if saved:
		frappe.delete_doc(DOCTYPE, saved.name, ignore_permissions=True, force=True)
		inst.add_comment("Info", _("{0} reset to the generated document by {1}.").format(_generators().get(key, (key,))[0],
			frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user))
	return {**_state(inst, key, None), "html": generated_html(inst, key)}


def edited_keys(installation):
	return set(frappe.get_all(DOCTYPE, filters={"solar_installation": installation}, pluck="document_code"))
