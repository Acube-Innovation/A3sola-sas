# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Commissioning creates the Project, the billing plan and the O&M contract."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_years, getdate

from a3_sola.api import om
from a3_sola.tests.solar_projects.fixtures import (
	billing_plan,
	commission,
	commissioned_project,
	om_contract,
)


class TestProjectFromCommissioning(FrappeTestCase):
	def test_commissioning_creates_the_project(self):
		project, installation, report = commissioned_project()
		self.assertTrue(project.name)
		self.assertEqual(project.solar_installation, installation.name)
		self.assertEqual(getdate(project.commissioning_date), getdate(report.commissioning_date))

	def test_solar_context_carried_onto_the_project(self):
		project, installation, _report = commissioned_project()
		self.assertEqual(project.capacity_kw, installation.capacity_kw)
		self.assertEqual(project.solar_package, installation.solar_package)
		self.assertEqual(project.subsidy_scheme, installation.subsidy_scheme)
		self.assertEqual(project.discom, installation.discom)
		self.assertEqual(getdate(project.warranty_start_date), getdate(installation.warranty_start_date))
		self.assertEqual(getdate(project.warranty_end_date), getdate(installation.warranty_end_date))

	def test_installation_links_back(self):
		project, installation, _ = commissioned_project()
		installation.reload()
		self.assertEqual(installation.project, project.name)

	def test_creation_is_idempotent(self):
		project, _installation, report = commissioned_project()
		again = om.create_project_from_commissioning(report)
		self.assertEqual(again, project.name)
		self.assertEqual(frappe.db.count("Project", {"solar_installation": report.solar_installation}), 1)

	def test_billing_plan_created_with_the_clients_terms(self):
		project, _installation, _report = commissioned_project()
		plan = billing_plan(project)
		self.assertTrue(plan, "no billing plan created")
		percentages = [row.percentage for row in plan.milestones]
		self.assertEqual(percentages, [70, 20, 10])
		self.assertEqual(plan.total_planned, plan.gross_contract_value)

	def test_om_contract_created_for_five_years(self):
		project, installation, _report = commissioned_project()
		contract = om_contract(project)
		self.assertTrue(contract, "no O&M contract created")
		self.assertEqual(getdate(contract.start_date), getdate(installation.warranty_start_date))
		self.assertEqual(getdate(contract.end_date), add_years(getdate(contract.start_date), 5))
		self.assertEqual(contract.duration_years, 5)
		self.assertEqual(contract.contract_type, "Comprehensive (Scheme Mandated)")
		self.assertTrue(contract.is_scheme_mandated)

	def test_visit_plan_is_three_visits_a_year(self):
		"""The client offers free inspection for five years, three visits a year."""
		project, _installation, _report = commissioned_project()
		contract = om_contract(project)
		self.assertEqual(contract.preventive_visits_per_year, 3)
		self.assertEqual(len(contract.visit_plan), 15)
		dates = [row.scheduled_date for row in contract.visit_plan]
		self.assertEqual(dates, sorted(dates))

	def test_coverage_reflects_the_actual_scope(self):
		"""Inspection included; module washing chargeable, with the customer providing water."""
		project, _installation, _report = commissioned_project()
		contract = om_contract(project)
		coverage = {row.coverage_item: row.coverage_type for row in contract.coverage}
		self.assertEqual(coverage["Preventive inspection visits"], "Included")
		self.assertEqual(coverage["Workmanship rectification"], "Included")
		self.assertEqual(coverage["Module washing"], "Chargeable")
		self.assertEqual(coverage["Grid faults"], "Excluded")

	def test_warranty_terms_read_from_the_make_master(self):
		"""Rayzon modules are 15/30 and Solinteg inverters 10 - never a constant."""
		project, _installation, _report = commissioned_project()
		contract = om_contract(project)
		self.assertEqual(contract.module_product_warranty_years, 15)
		self.assertEqual(contract.module_performance_warranty_years, 30)
		self.assertEqual(contract.inverter_warranty_years, 10)
		self.assertIn("Rayzon", contract.warranty_summary)
		self.assertIn("Solinteg", contract.warranty_summary)

	def test_performance_obligation_carried_from_commissioning(self):
		project, _installation, report = commissioned_project()
		contract = om_contract(project)
		self.assertEqual(contract.contractual_performance_ratio_percent, 75)
		self.assertEqual(
			contract.performance_ratio_at_commissioning, report.performance_ratio_at_commissioning
		)

	def test_provision_accrued_at_commissioning(self):
		project, _installation, _report = commissioned_project()
		contract = om_contract(project)
		self.assertGreater(contract.om_provision_allocated, 0)
		project.reload()
		self.assertEqual(project.om_provision_amount, contract.om_provision_allocated)
