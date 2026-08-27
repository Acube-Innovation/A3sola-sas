# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Somebody who wants to be shown the product.

Deliberately does NOT create a CRM Lead by default. A public form that writes into the
sales pipeline is a public form that fills the sales pipeline with spam, so the Lead is
created only when `create_lead_from_demo_request` is switched on in Settings, and only
after the record has survived the honeypot and the rate limit.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from a3_sola.api import platform
from a3_sola.api.naming import set_name


class DemoRequest(Document):
	def autoname(self):
		set_name(self, "demo_request_series_prefix", ".YYYY.-.#####", fallback="DEM")

	def validate(self):
		self.work_email = (self.work_email or "").strip().lower()
		self.full_name = (self.full_name or "").strip()
		self.organisation_name = (self.organisation_name or "").strip()
		if self.status != "New" and not self.first_contacted_on:
			self.first_contacted_on = frappe.utils.now_datetime()

	def after_insert(self):
		self.maybe_create_lead()
		self.notify_sales()

	def maybe_create_lead(self):
		from a3_sola.api.settings import get_value

		if not get_value("create_lead_from_demo_request"):
			return
		if not frappe.db.exists("DocType", "Lead"):
			return
		try:
			lead = frappe.get_doc(
				{
					"doctype": "Lead",
					"lead_name": self.full_name,
					"company_name": self.organisation_name,
					"email_id": self.work_email,
					"mobile_no": self.phone,
					"source": "Website",
					"notes": [{"note": self.message}] if self.message else [],
				}
			)
			lead.flags.ignore_permissions = True
			lead.flags.ignore_mandatory = True
			lead.insert(ignore_permissions=True)
			self.db_set("converted_lead", lead.name, update_modified=False)
		except Exception:
			# A demo request must never be lost because the CRM refused a Lead.
			frappe.log_error(frappe.get_traceback(), f"a3_sola: lead from {self.name}")

	def notify_sales(self):
		from a3_sola.api.settings import get_value

		if frappe.flags.in_demo or frappe.flags.in_test:
			return
		recipient = get_value("sales_email")
		if not recipient:
			return
		try:
			frappe.sendmail(
				recipients=[recipient],
				subject=_("Demo request from {0}").format(self.organisation_name),
				message=frappe.render_template(
					"a3_sola/templates/emails/demo_request_internal.html",
					platform.email_context({"doc": self}),
				),
				reference_doctype=self.doctype,
				reference_name=self.name,
				now=False,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: demo notification {self.name}")
