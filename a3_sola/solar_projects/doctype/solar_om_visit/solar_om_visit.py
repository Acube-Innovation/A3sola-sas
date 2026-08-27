# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A preventive or corrective maintenance visit.

Reuses the Phase 2 child doctype "Work Order Crew" - it was designed standalone for exactly
this. Defects found on a visit become Phase 2 Installation Snags, using the "O&M Visit"
source value that already exists on that doctype.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, time_diff_in_hours

from a3_sola.api import costing, om
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_float, get_value

LINKS = (
	("om_contract", "Solar OM Contract"),
	("project", "Project"),
	("solar_installation", "Solar Installation"),
)
#: A defect in these categories is a safety issue, so it is Critical by default.
CRITICAL_CATEGORIES = ("Safety", "Earthing")
SNAG_CATEGORY = {
	"Module": "Module",
	"Inverter": "Inverter",
	"Structure": "Mounting Structure",
	"Cabling": "Cabling",
	"Earthing": "Earthing & Surge Protection",
	"Meter": "Net Meter",
	"Safety": "Safety",
	"Housekeeping": "Aesthetic",
}


class SolarOMVisit(Document):
	def autoname(self):
		set_name(self, "om_visit_series_prefix", ".YYYY.-.#####", fallback="SOL-VST")

	def validate(self):
		assert_same_company(self, LINKS)
		self.pull_context()
		self.compute_duration()
		self.count_checklist()
		self.compute_cost()

	def pull_context(self):
		contract = frappe.get_cached_doc("Solar OM Contract", self.om_contract)
		self.project = contract.project
		self.solar_installation = contract.solar_installation
		self.customer = contract.customer
		self.site_address = contract.installation_address

	def compute_duration(self):
		if self.time_in and self.time_out:
			self.duration_hours = flt(time_diff_in_hours(self.time_out, self.time_in), 2)

	def count_checklist(self):
		self.items_ok = len([r for r in self.checklist if r.result == "OK"])
		self.items_attention = len([r for r in self.checklist if r.result == "Attention Required"])
		self.items_defect = len([r for r in self.checklist if r.result == "Defect"])

	def compute_cost(self):
		"""Valued the same way installation labour is: the crew's own cost rate first.

		Falling straight to a settings default that nobody has filled in would make every
		visit look free, and the O&M provision would never draw down.
		"""
		fallback = get_float("default_labour_cost_per_hour", 0.0)
		self.labour_cost = flt(
			flt(self.duration_hours) * (costing.employee_rate(self.technician) or fallback)
			+ sum(
				flt(r.actual_hours) * (costing.employee_rate(r.technician) or fallback)
				for r in self.additional_crew
			),
			2,
		)
		self.material_cost = flt(sum(flt(r.amount) for r in self.materials_consumed), 2)
		self.travel_cost = flt(flt(self.travel_km) * get_float("travel_cost_per_km", 0.0), 2)
		self.total_visit_cost = flt(
			flt(self.labour_cost) + flt(self.material_cost) + flt(self.travel_cost), 2
		)

	def on_submit(self):
		self.close_visit_plan_row()
		self.raise_snags_for_defects()
		self.release_provision()
		self.refresh_project_cost()
		if self.is_chargeable and flt(self.chargeable_amount):
			self.create_chargeable_invoice()

	def close_visit_plan_row(self):
		contract = frappe.get_doc("Solar OM Contract", self.om_contract)
		row = None
		if self.visit_plan_row:
			row = next((r for r in contract.visit_plan if r.name == self.visit_plan_row), None)
		if not row:
			row = next(
				(r for r in contract.visit_plan if r.status in ("Scheduled", "Due")), None
			)
		if row:
			row.status = "Completed"
			row.completed_date = self.visit_date
			row.om_visit = self.name
			self.db_set("visit_plan_row", row.name, update_modified=False)

		om.refresh_contract_compliance(contract)
		om.refresh_contract_financials(contract)
		contract.flags.ignore_validate_update_after_submit = True
		contract.save(ignore_permissions=True)

	def raise_snags_for_defects(self):
		"""Every Defect row becomes a Phase 2 snag, with the photograph attached."""
		for row in self.checklist:
			if row.result != "Defect" or row.snag_created:
				continue
			severity = "Critical" if row.category in CRITICAL_CATEGORIES else "Major"
			snag = frappe.get_doc(
				{
					"doctype": "Installation Snag",
					"company": self.company,
					"solar_installation": self.solar_installation,
					"reported_on": self.visit_date,
					"reported_by": frappe.session.user,
					"source": "O&M Visit",
					"category": SNAG_CATEGORY.get(row.category, "Aesthetic"),
					"severity": severity,
					"description": _("Found on visit {0}: {1}. {2}").format(
						self.name, row.checklist_item, row.remarks or ""
					),
				}
			)
			snag.flags.ignore_permissions = True
			snag.insert(ignore_permissions=True)
			row.db_set("snag_created", snag.name, update_modified=False)

	def release_provision(self):
		if get_value("release_provision_on") != "Per Visit":
			return
		if not flt(self.total_visit_cost):
			return
		om.release_om_provision(self.project, self.total_visit_cost, self.name)

	def refresh_project_cost(self):
		try:
			costing.recalculate_project_costs(self.project)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: cost refresh from {self.name}")

	def create_chargeable_invoice(self):
		"""A DRAFT invoice - accounts review before anything is sent."""
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": self.company,
				"customer": self.customer,
				"posting_date": self.visit_date,
				"project": self.project,
				"items": [
					{
						"item_name": _("Chargeable maintenance visit"),
						"description": _("{0} on {1} - visit {2}").format(
							self.visit_type, self.visit_date, self.name
						),
						"qty": 1,
						"rate": flt(self.chargeable_amount),
					}
				],
			}
		)
		invoice.flags.ignore_permissions = True
		invoice.insert(ignore_permissions=True)
		self.db_set("sales_invoice", invoice.name, update_modified=False)
		return invoice.name
