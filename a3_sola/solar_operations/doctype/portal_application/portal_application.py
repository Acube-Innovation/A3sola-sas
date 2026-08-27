# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""External applications, mirrored - never scraped.

There is no public API for the national portal or the DISCOM, so their numbers, dates and
statuses are recorded here by a human. Do not attempt any portal automation.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, today

from a3_sola.api import documents, stages
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (("solar_installation", "Solar Installation"), ("solar_consumer", "Solar Consumer"))

#: Which installation stage each application type gates. Held here, not in the controller
#: body, so a scheme change is an edit rather than a rewrite.
STAGE_MAP = {
	"National Portal": "NPA",
	"DISCOM Feasibility": "FEAS",
	"Net Meter Application": "NMTR",
	"Electrical Inspectorate": "CEIG",
	"Subsidy Redemption": "DBT",
	"Registration Fee Refund": "RFND",
}
DOCUMENT_MAP = {
	"National Portal": "NP-APPLICATION",
	"Net Meter Application": "KSEB-NETMETER-REQUEST",
	"Registration Fee Refund": "KSEB-REFUND-REQUEST",
}


class PortalApplication(Document):
	def autoname(self):
		set_name(self, "portal_application_series_prefix", ".YYYY.-.#####", fallback="SOL-APP")

	def validate(self):
		assert_same_company(self, LINKS)
		self.validate_unique_number()
		self.validate_portal_id()
		self.compute_ageing()
		self.write_back_identifiers()

	def validate_unique_number(self):
		existing = frappe.db.get_value(
			"Portal Application",
			{
				"application_number": self.application_number,
				"application_type": self.application_type,
				"company": self.company,
				"name": ["!=", self.name],
				"docstatus": ["<", 2],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("{0} application {1} already exists as {2}.").format(
					self.application_type,
					frappe.bold(self.application_number),
					frappe.utils.get_link_to_form("Portal Application", existing),
				)
			)

	def validate_portal_id(self):
		"""Warn, never block - the format is the ministry's to change."""
		if not (self.national_portal_application_id and self.discom):
			return
		pattern = frappe.db.get_value("DISCOM", self.discom, "portal_id_regex")
		if not pattern:
			return
		try:
			matches = re.match(pattern, self.national_portal_application_id)
		except re.error:
			return
		if not matches:
			frappe.msgprint(
				_("Portal ID {0} does not match the expected pattern for {1}. Confirm it is correct.").format(
					frappe.bold(self.national_portal_application_id), self.discom
				),
				title=_("Check Portal ID"),
				indicator="orange",
			)

	def compute_ageing(self):
		self.query_count = len(self.queries)
		if self.application_date:
			self.days_pending = date_diff(today(), getdate(self.application_date))
		if not self.expected_response_date:
			self.expected_response_date = self._expected_response()
		self.is_overdue = (
			1
			if self.expected_response_date
			and self.application_status in ("Submitted", "Under Review", "Query Raised")
			and getdate(self.expected_response_date) < getdate(today())
			else 0
		)

	def _expected_response(self):
		"""From the SLA of the stage this application gates."""
		stage_code = STAGE_MAP.get(self.application_type)
		if not (stage_code and self.solar_installation and self.application_date):
			return None
		sla = frappe.db.get_value(
			"Installation Stage Log",
			{"parent": self.solar_installation, "stage_code": stage_code},
			"sla_days",
		)
		return frappe.utils.add_days(getdate(self.application_date), int(sla or 30))

	def write_back_identifiers(self):
		"""One copy of each identifier, on the installation, for every document to read."""
		if not self.solar_installation:
			return
		updates = {
			field: self.get(field)
			for field in ("national_portal_application_id", "discom_id", "spin")
			if self.get(field)
		}
		if updates:
			frappe.db.set_value("Solar Installation", self.solar_installation, updates, update_modified=False)

	def before_update_after_submit(self):
		"""Queries and approvals arrive over weeks; recompute the ageing before the write."""
		self.compute_ageing()

	def on_update_after_submit(self):
		self.write_back_identifiers()
		self.handle_status_change()

	def on_submit(self):
		self.generate_letter()

	def generate_letter(self):
		template_code = DOCUMENT_MAP.get(self.application_type)
		if not template_code or not self.solar_installation:
			return
		if self.application_type == "Registration Fee Refund":
			consumer = frappe.get_doc("Solar Consumer", self.solar_consumer)
			if not consumer.cancelled_cheque:
				frappe.msgprint(
					_("The refund request encloses a cancelled cheque, and none is attached to {0}. "
					  "The DISCOM will return the request without it.").format(consumer.name),
					title=_("Missing Enclosure"),
					indicator="orange",
				)
		try:
			documents.generate_document(self.solar_installation, template_code)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: letter for {self.name}")

	def handle_status_change(self):
		"""Approval offers to advance the stage; a query blocks it."""
		stage_code = STAGE_MAP.get(self.application_type)
		if not (stage_code and self.solar_installation):
			return

		if self.application_status == "Query Raised":
			open_query = next((q for q in self.queries if not q.is_resolved), None)
			if open_query:
				try:
					stages.block_stage(
						self.solar_installation,
						stage_code,
						_("Query on {0}: {1}").format(self.name, open_query.query_description),
					)
				except frappe.ValidationError:
					pass
		elif self.application_status in ("Approved", "Under Review"):
			status = frappe.db.get_value(
				"Installation Stage Log",
				{"parent": self.solar_installation, "stage_code": stage_code},
				"status",
			)
			if status == "Blocked":
				stages.unblock_stage(
					self.solar_installation, stage_code, _("Query resolved on {0}").format(self.name)
				)


@frappe.whitelist()
def approve_and_advance(portal_application):
	"""Approve the application, file its letter and advance the mapped stage."""
	doc = frappe.get_doc("Portal Application", portal_application)
	doc.check_permission("write")

	stage_code = STAGE_MAP.get(doc.application_type)
	if not stage_code:
		frappe.throw(_("No installation stage is mapped to {0}.").format(doc.application_type))

	if doc.approval_attachment:
		_file_approval(doc, stage_code)

	doc.db_set("application_status", "Approved", update_modified=False)
	doc.db_set("status_updated_on", today(), update_modified=False)
	return stages.advance_stage(
		doc.solar_installation,
		stage_code,
		actual_date=doc.approval_date or today(),
		external_reference=doc.approval_number or doc.application_number,
		remarks=_("Approved via {0}").format(doc.name),
	)


def _file_approval(application, stage_code):
	"""Land the approval letter in the checklist automatically."""
	installation = frappe.get_doc("Solar Installation", application.solar_installation)
	for row in installation.documents:
		if row.stage_code == stage_code and not row.attachment:
			row.attachment = application.approval_attachment
			row.document_reference_no = application.approval_number
			row.document_date = application.approval_date
			row.is_verified = 1
			row.verified_by = frappe.session.user
			row.verified_on = frappe.utils.now_datetime()
			break
	installation.flags.ignore_validate_update_after_submit = True
	installation.save(ignore_permissions=True)
