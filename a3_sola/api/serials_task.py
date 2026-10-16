# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Serials to Electrical Contractor task, worked on its own page.

The electrical contractor writes the completion report from the job's module and inverter
serials. The page shows the contractor, keeps the serials (the job's register, as the
Material Dispatch page records them), prints the Data for Completion Report on the
Renewcore letterhead or plain paper (api/completion_print), and sends it - by email, which
completes the task, or by WhatsApp with a private link to the PDF, then Mark complete.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, today

from a3_sola.api import completion_print, portal_share, stages
from a3_sola.api.dispatch_task import SERIAL_TYPES, _set_serials
from a3_sola.api.settings import get_value
from a3_sola.api.stages import _get_stage

SERIALS = "MATL"
INSTALLATION = "Solar Installation"


def is_serials_task(code):
	return code == SERIALS


def _job(installation, ptype):
	doc = frappe.get_doc(INSTALLATION, installation, for_update=ptype == "write")
	doc.check_permission(ptype)
	_get_stage(doc, SERIALS)
	return doc


def _serials(inst):
	return {t: [r.serial_no for r in inst.get("serials") or [] if r.component_type == t and not r.is_replaced]
		for t in SERIAL_TYPES}


def _contractor(inst):
	if not inst.get("electrical_contractor"):
		return None
	row = frappe.db.get_value("Solar Contractor", inst.electrical_contractor,
		["name", "contractor_name", "contact_person", "mobile_no", "email_id"], as_dict=True)
	return {k: row.get(k) or "" for k in ("name", "contractor_name", "contact_person", "mobile_no", "email_id")} if row else None


def _message(inst, contractor):
	context = {"consumer_name": inst.get("consumer_name") or "", "company": inst.company,
		"contractor": (contractor or {}).get("contractor_name") or ""}
	subject = (get_value("completion_data_email_subject") or "Material and serial details - {consumer_name}").format(**context)
	body = (get_value("completion_data_email_body")
		or "Please find attached the material and serial number details for the completion report.").format(**context)
	return subject, body


@frappe.whitelist()
def state(installation):
	inst = _job(installation, "read")
	row = _get_stage(inst, SERIALS)
	contractor = _contractor(inst)
	serials = _serials(inst)
	subject, body = _message(inst, contractor)
	ready = bool(serials["Module"] or serials["Inverter"])
	link = portal_share.share_url(INSTALLATION, inst.name) if ready else ""
	whatsapp = ""
	if ready:
		from a3_sola.api.outreach import whatsapp_link

		text = "{0}\n\n{1}\n{2}".format(subject, body, link)
		whatsapp = whatsapp_link((contractor or {}).get("mobile_no") or "", text)
	prints = []
	for letterhead, label in ((True, _("On letterhead")), (False, _("Without letterhead"))):
		prints.append({"label": label, "view": completion_print.url(inst.name, letterhead=letterhead),
			"download": completion_print.url(inst.name, letterhead=letterhead, download=True)})
	return {
		"task": {"code": row.stage_code, "name": row.stage_name, "status": row.status, "reason": row.skip_reason or "",
			"completed_on": frappe.utils.format_date(row.actual_completion_date, "d MMM yyyy") if row.actual_completion_date else "",
			"sent_to": row.external_reference or ""},
		"contractor": contractor,
		"project_route": "/a3solaportal/projects/" + frappe.utils.quote(inst.name),
		"serials": serials,
		"expected_modules": int(inst.get("modules_expected") or inst.get("module_count") or 0),
		"prints": prints,
		"ready": ready,
		"email": {"to": (contractor or {}).get("email_id") or "", "subject": subject, "message": body},
		"whatsapp": whatsapp,
		"can_edit": bool(inst.has_permission("write")) and row.status not in ("Skipped",),
		"can_complete": bool(inst.has_permission("write")) and row.status not in ("Completed", "Skipped"),
	}


@frappe.whitelist(methods=["POST"])
def save(installation, module_serials=None, inverter_serials=None):
	"""Keep the serials as typed; the task stays open."""
	inst = _job(installation, "write")
	if module_serials is not None:
		_set_serials(inst, "Module", module_serials)
	if inverter_serials is not None:
		_set_serials(inst, "Inverter", inverter_serials)
	_start(inst)
	inst.flags.ignore_validate_update_after_submit = True
	inst.save(ignore_permissions=True)
	return state(installation)


def _start(inst):
	row = _get_stage(inst, SERIALS)
	if row.status == "Pending":
		row.status = "In Progress"
		row.actual_start_date = row.actual_start_date or today()


def _complete(inst, message, sent_to=None):
	row = _get_stage(inst, SERIALS)
	if row.status in ("Completed", "Skipped"):
		frappe.throw(_("{0} is already {1}.").format(row.stage_name, row.status.lower()))
	row.status = "Completed"
	row.actual_start_date = row.actual_start_date or today()
	row.actual_completion_date = today()
	row.completed_by = frappe.session.user
	if sent_to:
		row.external_reference = sent_to[:140]
	stages._save(inst, message)
	from a3_sola.api.tasks import notify_task_completed

	notify_task_completed(inst, SERIALS)


@frappe.whitelist(methods=["POST"])
def send_email(installation, recipients, subject, message, letterhead=1, cc=None):
	"""Email the Data for Completion Report to the contractor from the site's mailbox, keep
	a copy on the job's timeline, and complete the task."""
	from frappe.core.doctype.communication.email import make

	inst = _job(installation, "write")
	if not any(_serials(inst).values()):
		frappe.throw(_("Enter the module and inverter serials first; there is nothing to send."), title=_("No Serials"))
	recipients = ", ".join(r.strip() for r in (recipients or "").replace(";", ",").split(",") if r.strip())
	if not recipients:
		frappe.throw(_("Enter the email address to send it to."), title=_("No Recipient"))
	for address in recipients.split(", "):
		frappe.utils.validate_email_address(address, throw=True)
	account = portal_share._outgoing_account(INSTALLATION)
	if not account:
		frappe.throw(
			_("No mailbox is set up to send from. In ERPNext, open Email Account, add the company's mailbox "
			  "with Enable Outgoing and Default Outgoing ticked, then try again."),
			title=_("Email Not Set Up"),
		)
	file_name, pdf = completion_print.render(inst, letterhead=letterhead)
	make(
		doctype=INSTALLATION, name=inst.name, content=portal_share._as_html(message), subject=subject,
		recipients=recipients, cc=cc or None, sender=account.email_id, sender_full_name=account.get("name"),
		send_email=True, attachments=[{"fname": file_name, "fcontent": pdf}], now=True,
	)
	inst = _job(installation, "write")
	_complete(inst, _("{0}: the completion report data emailed to {1}.").format(_get_stage(inst, SERIALS).stage_name, recipients),
		sent_to=recipients)
	return state(installation)


@frappe.whitelist(methods=["POST"])
def mark_complete(installation, note=None):
	"""Complete the task when the data went another way - WhatsApp, or by hand."""
	inst = _job(installation, "write")
	row = _get_stage(inst, SERIALS)
	if note:
		row.remarks = "\n".join(p for p in (row.remarks, note.strip()) if p)
	_complete(inst, _("{0}: marked complete{1}.").format(row.stage_name, ": " + note.strip() if note else ""),
		sent_to=(note or "").strip() or None)
	return state(installation)
