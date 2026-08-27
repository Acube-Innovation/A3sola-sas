# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Project costing: re-derived from source, never accumulated."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import costing
from a3_sola.tests.solar_projects.fixtures import (
	commissioned_project,
	make_snag,
	make_statutory_fee,
	make_work_order,
)


class TestProjectCosting(FrappeTestCase):
	def test_labour_cost_from_crew_hours(self):
		project, installation, _ = commissioned_project()
		make_work_order(installation, hours=10.0, ctc=520000)
		costing.recalculate_project_costs(project.name)
		project.reload()
		# 520000 / 2080 = 250 an hour.
		self.assertEqual(flt(project.labour_cost, 2), 2500.00)
		self.assertGreater(project.total_direct_cost, 0)

	def test_costs_are_rederived_not_accumulated(self):
		"""Running it twice must not double anything. This is the whole design."""
		project, installation, _ = commissioned_project()
		make_work_order(installation, hours=10.0, ctc=520000)
		costing.recalculate_project_costs(project.name)
		project.reload()
		first_cost, first_entries = project.total_direct_cost, len(project.cost_entries)

		for _ in range(3):
			costing.recalculate_project_costs(project.name)
		project.reload()
		self.assertEqual(project.total_direct_cost, first_cost)
		self.assertEqual(len(project.cost_entries), first_entries)

	def test_rework_is_isolated_from_installation_labour(self):
		"""Rectification must be visible on its own line, not buried in labour."""
		project, installation, _ = commissioned_project()
		make_work_order(installation, hours=10.0, ctc=520000)
		rectification = make_work_order(
			installation, hours=4.0, ctc=520000, work_order_type="Rectification"
		)
		make_snag(installation, work_order=rectification.name)
		costing.recalculate_project_costs(project.name)
		project.reload()
		# 4 hours at 250 an hour, and not a rupee of it in Labour.
		self.assertEqual(flt(project.rework_cost, 2), 1000.00)
		self.assertEqual(flt(project.labour_cost, 2), 2500.00)
		categories = {row.cost_category for row in project.cost_entries}
		self.assertIn("Rework", categories)
		self.assertIn("Labour", categories)

	def test_statutory_fees_never_touch_margin(self):
		"""Pass-through by definition: paid on the customer's behalf, reimbursed at cost."""
		project, installation, _ = commissioned_project()
		make_statutory_fee(installation, amount=1180.0)
		costing.recalculate_project_costs(project.name)
		project.reload()
		self.assertEqual(flt(project.statutory_pass_through, 2), 1180.00)
		self.assertNotIn(
			"Statutory Fees", {row.cost_category for row in project.cost_entries}
		)
		self.assertEqual(project.total_direct_cost, 0)

	def test_pass_through_categories_come_from_settings(self):
		self.assertIn("Statutory Fees", costing.pass_through_categories())

	def test_customer_paid_fees_are_not_pass_through(self):
		"""If the customer paid the DISCOM directly the company funded nothing."""
		project, installation, _ = commissioned_project()
		make_statutory_fee(installation, amount=1180.0, paid_by="Customer Directly")
		costing.recalculate_project_costs(project.name)
		project.reload()
		self.assertEqual(flt(project.statutory_pass_through, 2), 0.0)

	def test_overhead_applied_at_the_configured_rate(self):
		project, installation, _ = commissioned_project()
		frappe.db.set_single_value("A3 Sola Settings", "overhead_recovery_percent", 10)
		make_work_order(installation, hours=10.0, ctc=520000)
		costing.recalculate_project_costs(project.name)
		project.reload()
		self.assertEqual(flt(project.overhead_allocated, 2), 250.00)
		self.assertEqual(flt(project.total_cost, 2), 2750.00)

	def test_margin_measured_against_billed_revenue(self):
		project, installation, _ = commissioned_project()
		frappe.db.set_single_value("A3 Sola Settings", "overhead_recovery_percent", 0)
		make_work_order(installation, hours=10.0, ctc=520000)
		costing.recalculate_project_costs(project.name)
		project.reload()
		revenue = flt(project.total_billed_amount) or flt(project.gross_contract_value)
		self.assertEqual(
			flt(project.gross_margin_amount, 2), flt(revenue - project.total_cost, 2)
		)
		self.assertEqual(
			flt(project.gross_margin_percent, 2),
			flt(project.gross_margin_amount * 100.0 / revenue, 2),
		)

	def test_per_kw_figures_use_actual_capacity(self):
		project, installation, _ = commissioned_project()
		make_work_order(installation, hours=10.0, ctc=520000)
		costing.recalculate_project_costs(project.name)
		project.reload()
		self.assertEqual(
			flt(project.cost_per_kw, 2), flt(project.total_cost / project.capacity_kw, 2)
		)

	def test_every_entry_carries_a_traceable_source(self):
		project, installation, _ = commissioned_project()
		make_work_order(installation, hours=10.0, ctc=520000)
		costing.recalculate_project_costs(project.name)
		project.reload()
		for row in project.cost_entries:
			self.assertTrue(row.source_doctype)
			self.assertTrue(row.source_document)
			self.assertTrue(frappe.db.exists(row.source_doctype, row.source_document))

	def test_recalculation_returns_a_summary(self):
		project, installation, _ = commissioned_project()
		make_work_order(installation, hours=10.0, ctc=520000)
		result = costing.recalculate_project_costs(project.name)
		self.assertEqual(result["entries"], 1)
		self.assertGreater(result["total_cost"], 0)
