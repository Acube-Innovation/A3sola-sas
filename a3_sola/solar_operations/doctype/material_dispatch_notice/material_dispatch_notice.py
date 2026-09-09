# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What went to site, told to the electrical contractor.

The contractor writes the completion certificate from the module and inverter serials, so
they are sent the serials in the exact format the certificate is written from. The serials
are a snapshot on this notice: the register may grow later, but what was mailed is what was
mailed.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, today

from a3_sola.api import documents
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_value

LINKS = (
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
	("solar_contractor", "Solar Contractor"),
	("delivery_note", "Delivery Note"),
)


class MaterialDispatchNotice(Document):
	def autoname(self):
		set_name(self, "material_dispatch_notice_series_prefix", ".YYYY.-.#####", fallback="SOL-MDN")

	def validate(self):
		self.company = frappe.db.get_value("Solar Installation", self.solar_installation, "company")
		assert_same_company(self, LINKS)
		if not self.assigned_by:
			self.assigned_by = frappe.session.user
		if not self.assigned_on:
			self.assigned_on = today()
		if not self.contractor_email and self.solar_contractor:
			self.contractor_email = frappe.db.get_value("Solar Contractor", self.solar_contractor, "email_id")
		if self.sent_on and self.status not in ("Completed", "Skipped"):
			self.status = "Completed"

	def before_submit(self):
		if self.status == "Skipped":
			return
		if not self.sent_on:
			frappe.throw(_("Send the details to the contractor before submitting."), title=_("Not Sent"))


def _load(notice):
	doc = frappe.get_doc("Material Dispatch Notice", notice)
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def pull_serials(notice):
	"""Snapshot the installation's serials; pull them from the delivery notes first if empty."""
	from a3_sola.api import serials

	doc = _load(notice)
	installation = frappe.get_doc("Solar Installation", doc.solar_installation)
	if not installation.serials:
		serials.pull_serials_from_delivery_note(installation.name)
		installation.reload()
	doc.set(
		"serials",
		[
			{
				"component_type": r.component_type, "serial_no": r.serial_no, "item": r.item,
				"manufacturer": r.manufacturer, "model_number": r.model_number, "wattage": r.wattage,
				"dcr_certificate_no": r.dcr_certificate_no, "delivery_note": r.delivery_note,
			}
			for r in installation.serials
		],
	)
	if doc.status == "Pending":
		doc.status = "In Progress"
	doc.save()
	return len(doc.serials)


@frappe.whitelist()
def generate(notice):
	"""The data sheet, from this notice's serial snapshot."""
	doc = _load(notice)
	if not doc.serials:
		pull_serials(notice)
		doc.reload()
	result = documents.generate_document(
		doc.solar_installation, "COMPLETION-REPORT-DATA",
		source_doctype=doc.doctype, source_name=doc.name,
	)
	row = next((r for r in doc.generated if r.template_code == result["template_code"]), None) or doc.append(
		"generated", {"template_code": result["template_code"]}
	)
	row.update(
		{
			"solar_document_template": result["template_name"], "document_name": result["template"],
			"file": result["file_url"], "template_version": result["template_version"],
			"generated_on": now_datetime(), "generated_by": frappe.session.user, "status": "Generated",
		}
	)
	doc.completion_data_sheet = result["file_url"]
	if doc.status == "Pending":
		doc.status = "In Progress"
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()
	return result


@frappe.whitelist()
def send(notice, message=None):
	"""Mail the data sheet to the contractor, record it, and complete the task.

	Refuses without serials, an address or a data sheet. Refuses without an outgoing email
	account too - except under test, where the Communication is recorded unsent.
	"""
	from frappe.core.doctype.communication.email import make

	doc = _load(notice)
	if doc.docstatus != 0:
		frappe.throw(_("{0} has already been sent and submitted.").format(doc.name))
	if not doc.serials:
		frappe.throw(_("Pull the serial numbers first; there is nothing to send."), title=_("No Serials"))
	if not doc.contractor_email:
		frappe.throw(_("The contractor has no email address."), title=_("No Address"))
	if not doc.completion_data_sheet:
		generate(notice)
		doc.reload()

	account = frappe.db.get_value("Email Account", {"enable_outgoing": 1}, "name")
	if not account and not frappe.flags.in_test:
		frappe.throw(
			_("No outgoing Email Account is enabled on this site, so nothing can be sent."),
			title=_("Email Not Configured"),
		)

	context = {"consumer_name": doc.consumer_name or "", "company": doc.company, "contractor": doc.solar_contractor}
	subject = (get_value("completion_data_email_subject") or "Material and serial details - {consumer_name}").format(**context)
	body = message or (get_value("completion_data_email_body")
	                   or "Please find attached the material and serial number details.").format(**context)
	attachments = frappe.get_all(
		"File", filters={"file_url": doc.completion_data_sheet, "attached_to_name": doc.name}, pluck="name", limit=1
	)
	result = make(
		doctype=doc.doctype, name=doc.name, content=body, subject=subject,
		recipients=doc.contractor_email, cc=doc.cc_emails or None,
		send_email=bool(account), attachments=attachments or None,
	)
	doc.sent_on = now_datetime()
	doc.sent_to = doc.contractor_email
	doc.sent_by = frappe.session.user
	doc.communication = result.get("name") if isinstance(result, dict) else None
	doc.status = "Completed"
	doc.save()
	doc.submit()
	return doc.name
