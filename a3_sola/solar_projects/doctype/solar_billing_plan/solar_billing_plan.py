# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Milestone billing plan."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api import billing, gst
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import precision

LINKS = (
	("project", "Project"),
	("solar_installation", "Solar Installation"),
	("sales_order", "Sales Order"),
	("gst_valuation_rule", "Solar GST Valuation Rule"),
	("milestone_template", "Billing Milestone Template"),
)


class SolarBillingPlan(Document):
	def autoname(self):
		set_name(self, "billing_plan_series_prefix", ".YYYY.-.#####", fallback="SOL-BPL")

	def validate(self):
		assert_same_company(self, LINKS)
		self.validate_one_per_project()
		self.resolve_gst_rule()
		billing.build_plan(self)
		self.validate_total()
		billing.recompute_summary(self)

	def validate_one_per_project(self):
		existing = frappe.db.get_value(
			"Solar Billing Plan",
			{"project": self.project, "name": ["!=", self.name], "docstatus": ["<", 2]},
			"name",
		)
		if existing:
			frappe.throw(
				_("Project {0} already has billing plan {1}.").format(
					self.project, frappe.utils.get_link_to_form("Solar Billing Plan", existing)
				)
			)

	def resolve_gst_rule(self):
		if self.gst_valuation_rule:
			return
		try:
			self.gst_valuation_rule = gst.resolve_valuation(self.company, self.consumer_category)
		except frappe.ValidationError:
			# A plan can be built for tracking before the CA has confirmed the treatment;
			# invoicing is what actually needs the rule.
			pass

	def validate_total(self):
		"""Milestones must total the contract value within the rounding precision."""
		total = sum(flt(row.milestone_amount) for row in self.milestones)
		contract = flt(self.gross_contract_value)
		if abs(total - contract) > (10 ** -precision()) * len(self.milestones) + 1:
			frappe.throw(
				_("Milestones total {0} but the contract value is {1}. They must agree.").format(
					frappe.utils.fmt_money(total, currency="INR"),
					frappe.utils.fmt_money(contract, currency="INR"),
				),
				title=_("Milestones Do Not Total"),
			)

	def before_update_after_submit(self):
		billing.recompute_summary(self)


@frappe.whitelist()
def trigger_milestone(billing_plan, milestone_name):
	"""Manual and On Date triggers."""
	plan = frappe.get_doc("Solar Billing Plan", billing_plan)
	plan.check_permission("write")
	row = next((r for r in plan.milestones if r.milestone_name == milestone_name), None)
	if not row:
		frappe.throw(_("Milestone {0} is not on this plan.").format(milestone_name))
	if row.is_triggered:
		frappe.throw(_("Milestone {0} is already triggered.").format(milestone_name))

	row.is_triggered = 1
	row.triggered_on = frappe.utils.today()
	billing.recompute_summary(plan)
	plan.flags.ignore_validate_update_after_submit = True
	plan.save(ignore_permissions=True)
	plan.add_comment("Comment", _("Milestone {0} triggered manually.").format(milestone_name))
	return row.milestone_name
