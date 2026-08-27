# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Site survey, including the lender's EHS block.

The EHS block exists because every bank-financed job needs a signed vendor feasibility
report and an environmental, health and safety checklist before the first disbursement.
The surveyor answers it once, on site; Phase 2 prints both documents from it, so nobody
fills a separate form.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_float
from a3_sola.setup.ehs_checklist import EHS_QUESTIONS

LINKS = (
	("solar_consumer", "Solar Consumer"),
	("discom", "DISCOM"),
	("discom_section", "DISCOM Section"),
	("roof_type", "Roof Type"),
)


class SiteSurvey(Document):
	def autoname(self):
		set_name(self, "survey_series_prefix", ".YYYY.-.#####", fallback="SOL-SRV")

	def before_insert(self):
		self.seed_ehs_checklist()

	def validate(self):
		assert_same_company(self, LINKS)
		self.seed_ehs_checklist()
		self.compute_roof_capacity()
		self.compute_shading()
		self.compute_ehs_status()

	def seed_ehs_checklist(self):
		"""Populate the checklist from the fixture when empty, preserving answers."""
		if self.ehs_checklist:
			return
		for question in EHS_QUESTIONS:
			self.append(
				"ehs_checklist",
				{
					"question_code": question["code"],
					"phase": question["phase"],
					"question_text": question["text"],
					"expected_response": question["expected"],
					"is_blocking": 1 if question.get("blocking") else 0,
				},
			)

	def area_per_kw(self):
		"""Roof type overrides the app default; the app default is itself configurable."""
		if self.roof_type:
			override = flt(frappe.db.get_value("Roof Type", self.roof_type, "area_per_kw_sqft"))
			if override:
				return override
		return get_float("default_area_per_kw_sqft", 80.0)

	def compute_roof_capacity(self):
		per_kw = self.area_per_kw() or 80.0
		usable_area = 0.0
		usable_kw = 0.0
		for row in self.roof_segments:
			if row.is_usable:
				usable_area += flt(row.area_sqft)
				row.usable_kw = flt(flt(row.area_sqft) / per_kw, 3)
				usable_kw += row.usable_kw
			else:
				row.usable_kw = 0.0
		self.total_usable_area_sqft = flt(usable_area, 2)
		self.total_usable_kw = flt(usable_kw, 3)

	def compute_shading(self):
		readings = [flt(r.shading_percent) for r in self.shadow_observations]
		self.average_shading_percent = flt(sum(readings) / len(readings), 2) if readings else 0.0

	def compute_ehs_status(self):
		"""Blocked on a failed go/no-go, Cleared with Conditions on missing evidence.

		Asbestos is the hard one: broken or dilapidated asbestos roofing is a lender
		go/no-go, and the client's own feasibility report answers it first.
		"""
		if self.asbestos_present:
			for row in self.ehs_checklist:
				if row.question_code == "EHS-GNG-01":
					row.response = "No"
		blocked = []
		conditions = []
		for row in self.ehs_checklist:
			if not row.response:
				continue
			if row.is_blocking and row.expected_response and row.response != row.expected_response:
				blocked.append(row.question_code)
			elif row.response == "Yes" and row.phase == "Proposal Appraisal" and not row.evidence_attachment:
				conditions.append(row.question_code)

		if self.asbestos_present:
			blocked.append("EHS-GNG-01")

		if blocked:
			self.ehs_overall_status = "Blocked"
			self.ehs_conditions = _("Go/no-go failure on: {0}").format(", ".join(sorted(set(blocked))))
		elif conditions:
			self.ehs_overall_status = "Cleared with Conditions"
			self.ehs_conditions = _("Evidence outstanding for: {0}").format(", ".join(sorted(set(conditions))))
		else:
			self.ehs_overall_status = "Cleared"
			self.ehs_conditions = None

	def before_submit(self):
		if self.asbestos_present or self.ehs_overall_status == "Blocked":
			frappe.throw(
				_(
					"This survey fails a lender go/no-go criterion and cannot be submitted: {0}. "
					"A roof with broken or dilapidated asbestos makes the job unfinanceable, and on a "
					"financed job unbuildable."
				).format(self.ehs_conditions or _("asbestos roofing present")),
				title=_("EHS Blocked"),
			)

	def on_submit(self):
		consumer = frappe.get_doc("Solar Consumer", self.solar_consumer)
		consumer.set_status("Surveyed")
		if not flt(consumer.approx_roof_area_sqft) and flt(self.total_roof_area_sqft):
			consumer.db_set("approx_roof_area_sqft", flt(self.total_roof_area_sqft), update_modified=False)
