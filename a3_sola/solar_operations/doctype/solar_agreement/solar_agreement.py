# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The stamp-paper net-metering agreement for one installation.

Two things happen here that happen nowhere else. The stamp paper is recorded - that is the
whole of the STMP stage, a status and a serial number, no evidence to upload. And once it
is recorded the body text is generated from the chain, so what goes on the paper is the
consumer record itself and not somebody's retyping of it.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, today

from a3_sola.api import agreement as builder
from a3_sola.api import documents
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_value

LINKS = (
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
	("site_survey", "Site Survey"),
	("solar_design_estimate", "Solar Design Estimate"),
	("commissioning_report", "Commissioning Report"),
)


class SolarAgreement(Document):
	def autoname(self):
		set_name(self, "solar_agreement_series_prefix", ".YYYY.-.#####", fallback="SOL-AGR")

	def validate(self):
		builder.pull_sources(self)
		assert_same_company(self, LINKS)
		self.validate_stamp_paper()
		self.validate_one_active()
		self.validate_wheeling()
		self.set_defaults()
		self.flag_edits()

	def set_defaults(self):
		if not self.validity_years:
			self.validity_years = 25
		if not self.stamp_paper_value:
			self.stamp_paper_value = get_value("stamp_paper_denomination")
		if not self.place_of_execution and self.electrical_section:
			self.place_of_execution = self.electrical_section
		self.agreement_title = builder.TITLE

	def validate_stamp_paper(self):
		"""The stamp paper is the STMP stage's only output, so it must be complete or absent."""
		if self.stamp_paper_status != "Purchased":
			return
		if not self.stamp_paper_purchased_on:
			self.stamp_paper_purchased_on = today()
		if getdate(self.stamp_paper_purchased_on) > getdate(today()):
			frappe.throw(_("Stamp paper cannot be purchased on a future date."))
		if self.agreement_date and getdate(self.stamp_paper_purchased_on) > getdate(self.agreement_date):
			frappe.throw(
				_("The stamp paper was bought on {0}, after the agreement date {1}. An agreement "
				  "cannot be written on paper that did not exist yet.").format(
					frappe.format(self.stamp_paper_purchased_on, "Date"),
					frappe.format(self.agreement_date, "Date"),
				)
			)

	def validate_one_active(self):
		"""One live agreement per installation. A terminated one does not compete."""
		if self.is_terminated:
			return
		existing = frappe.db.get_value(
			"Solar Agreement",
			{
				"solar_installation": self.solar_installation,
				"name": ["!=", self.name],
				"docstatus": 1,
				"is_terminated": 0,
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Installation {0} already has an executed agreement, {1}. Terminate it before executing another.").format(
					self.solar_installation,
					frappe.utils.get_link_to_form("Solar Agreement", existing),
				)
			)

	def validate_wheeling(self):
		"""Excess over 500 units is wheeled to the consumer's other premises, in order."""
		own = frappe.db.get_value("Solar Consumer", self.solar_consumer, "consumer_number")
		seen = set()
		for row in self.wheeling_preferences:
			if own and row.consumer_number == own:
				frappe.throw(
					_("Preference {0} points at this installation's own consumer number. "
					  "Wheeling is to other premises.").format(row.preference_order)
				)
			if row.preference_order in seen:
				frappe.throw(_("Duplicate preference order {0}.").format(row.preference_order))
			seen.add(row.preference_order)

	def flag_edits(self):
		"""`is_edited` is what makes a regenerate ask before discarding someone's wording."""
		if not self.agreement_text:
			self.is_edited = 0
			return
		self.is_edited = 1 if builder.is_edited(self) else 0

	def before_submit(self):
		if self.stamp_paper_status != "Purchased":
			frappe.throw(
				_("Record the stamp paper before executing the agreement."),
				title=_("Stamp Paper Not Purchased"),
			)
		if not self.agreement_text:
			frappe.throw(
				_("Generate the agreement text before executing. There is nothing to sign."),
				title=_("No Agreement Text"),
			)
		if not self.spin:
			frappe.throw(
				_("The Solar Plant Identification Number (SPIN) is allotted by the DISCOM on "
				  "execution and is the identifier every later document uses. Record it first."),
				title=_("SPIN Required"),
			)

	def on_submit(self):
		frappe.db.set_value(
			"Solar Installation", self.solar_installation, "spin", self.spin, update_modified=False
		)
		if self.solar_consumer:
			frappe.db.set_value(
				"Solar Consumer", self.solar_consumer, "spin", self.spin, update_modified=False
			)


@frappe.whitelist()
def record_stamp_paper(agreement, purchased_on=None, serial_no=None, value=None, vendor=None):
	"""The stamp-paper task in full: mark the paper bought. The task row completes itself.

	Status only - no document is uploaded here. Saving with `stamp_paper_status` Purchased
	is what `tasks.sync_from_document` reads as STMP complete.
	"""
	doc = frappe.get_doc("Solar Agreement", agreement)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(
			_("This agreement has already been executed. The stamp paper it was written on "
			  "cannot be recorded afterwards.")
		)
	if doc.stamp_paper_status == "Purchased":
		frappe.throw(_("The stamp paper is already recorded as purchased."))

	doc.stamp_paper_status = "Purchased"
	doc.stamp_paper_purchased_on = purchased_on or today()
	if serial_no:
		doc.stamp_paper_serial = serial_no
	if value:
		doc.stamp_paper_value = value
	if vendor:
		doc.stamp_paper_vendor = vendor
	doc.save()
	doc.add_comment(
		"Comment",
		_("Stamp paper recorded as purchased on {0}.").format(
			frappe.format(doc.stamp_paper_purchased_on, "Date")
		),
	)
	return doc.name


@frappe.whitelist()
def create_for_installation(installation):
	"""Open the agreement for an installation, or return the one that already exists."""
	existing = frappe.db.get_value(
		"Solar Agreement", {"solar_installation": installation, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		return existing
	doc = frappe.new_doc("Solar Agreement")
	doc.solar_installation = installation
	doc.agreement_date = today()
	doc.insert()
	return doc.name


@frappe.whitelist()
def generate_stamp_paper_data(agreement):
	"""The sheet the treasury writes the paper from: parties, purpose, value.

	Works on a draft before the paper is bought - that is when it is needed - and again on
	an executed agreement for the record. Registers on the job under the stamp-paper task.
	"""
	doc = frappe.get_doc("Solar Agreement", agreement)
	doc.check_permission("write")
	result = documents.generate_document(
		doc.solar_installation, "STAMP-PAPER-DATA", force=True,
		source_doctype=doc.doctype, source_name=doc.name,
	)
	doc.db_set("stamp_paper_data_sheet", result["file_url"], update_modified=False)
	return result


@frappe.whitelist()
def terminate(agreement, terminated_by=None, reason=None):
	"""Either party may terminate on thirty days' notice. Record it; never delete.

	Manager-only: a terminated agreement lets another be executed for the same premises,
	which is not an executive's call.
	"""
	from a3_sola.api.stages import _require_manager

	_require_manager(_("terminate an agreement"))
	if terminated_by not in ("Consumer", "DISCOM"):
		frappe.throw(_("Say which party terminated: Consumer or DISCOM."))
	if not (reason or "").strip():
		frappe.throw(_("A reason is mandatory when terminating an agreement."))
	doc = frappe.get_doc("Solar Agreement", agreement)
	doc.check_permission("write")
	if doc.docstatus != 1:
		frappe.throw(_("Only an executed agreement can be terminated; delete or cancel a draft."))
	if doc.is_terminated:
		frappe.throw(_("{0} is already terminated.").format(doc.name))
	doc.db_set("is_terminated", 1, update_modified=False)
	doc.db_set("terminated_on", today(), update_modified=False)
	doc.db_set("terminated_by", terminated_by, update_modified=False)
	doc.db_set("termination_reason", reason.strip(), update_modified=False)
	doc.add_comment("Comment", _("Agreement terminated by {0}: {1}").format(terminated_by, reason.strip()))
	return True
