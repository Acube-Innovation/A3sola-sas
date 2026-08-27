# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every Solar Projects report runs, and runs on real data.

A report that only works against an empty table is not tested at all, so these execute
against a fully commissioned project with costs, a visit, a ticket and a claim behind it.
"""

import frappe
from frappe.desk.query_report import run
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from a3_sola.api import costing, om
from a3_sola.tests.fixtures import default_company
from a3_sola.tests.solar_projects.fixtures import (
	commissioned_project,
	make_statutory_fee,
	make_ticket,
	make_visit,
	make_work_order,
	om_contract,
)

REPORTS = (
	"Project Profitability",
	"Cost Overrun Analysis",
	"Billing vs Collection",
	"Subsidy Receivable Ageing",
	"Solar OM Provision Movement",
	"Statutory Recovery Register",
	"Solar OM Contract Register",
	"Preventive Visit Compliance",
	"Service Ticket SLA Compliance",
	"Root Cause Analysis",
	"System Performance Ranking",
	"Warranty Claim Register",
	"Renewal Pipeline",
	"Scheme Obligation Compliance",
	"System Expansion Candidates",
)


class TestProjectsReports(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = default_company()

	def setUp(self):
		self.project, self.installation, _ = commissioned_project()
		self.contract = om_contract(self.project)
		make_work_order(self.installation, hours=8.0, ctc=520000)
		make_statutory_fee(self.installation, amount=1180.0)
		costing.recalculate_project_costs(self.project.name)

		visit = make_visit(
			self.contract,
			checklist=[(item, category, "OK") for item, category in om.VISIT_CHECKLIST],
		)
		visit.submit()

		ticket = make_ticket(self.contract, severity="Critical")
		ticket.status = "Resolved"
		ticket.root_cause = "Workmanship"
		ticket.resolution_description = "Reterminated the DC connector."
		ticket.flags.ignore_validate_update_after_submit = True
		ticket.save(ignore_permissions=True)

	def test_every_report_is_registered(self):
		for name in REPORTS:
			self.assertTrue(frappe.db.exists("Report", name), f"{name} is not installed")
			self.assertEqual(
				frappe.db.get_value("Report", name, "module"),
				"Solar Projects",
				f"{name} is not in the Solar Projects module",
			)

	def test_every_report_runs_and_returns_its_columns(self):
		for name in REPORTS:
			with self.subTest(report=name):
				result = run(name, filters={"company": self.company}, ignore_prepared_report=True)
				self.assertTrue(result.get("columns"), f"{name} returned no columns")

	def test_every_report_column_names_a_real_field(self):
		"""A column pointing at a field that does not exist renders as a blank column."""
		for name in REPORTS:
			with self.subTest(report=name):
				result = run(name, filters={"company": self.company}, ignore_prepared_report=True)
				fieldnames = {column["fieldname"] for column in result["columns"]}
				for row in result.get("result") or []:
					if not isinstance(row, dict):
						continue
					missing = fieldnames - set(row.keys())
					self.assertEqual(
						missing, set(), f"{name} declares columns absent from its rows: {missing}"
					)

	def test_profitability_reports_the_commissioned_project(self):
		result = run(
			"Project Profitability", filters={"company": self.company}, ignore_prepared_report=True
		)
		names = {row["name"] for row in result["result"]}
		self.assertIn(self.project.name, names)

	def test_statutory_pass_through_is_reported_separately_from_cost(self):
		result = run(
			"Project Profitability", filters={"company": self.company}, ignore_prepared_report=True
		)
		row = next(r for r in result["result"] if r["name"] == self.project.name)
		self.assertEqual(flt(row["statutory_pass_through"], 2), 1180.00)
		self.assertNotIn(1180.00, [flt(row["total_cost"], 2)])

	def test_contract_register_carries_the_makes_own_terms(self):
		result = run(
			"Solar OM Contract Register", filters={"company": self.company}, ignore_prepared_report=True
		)
		row = next(r for r in result["result"] if r["name"] == self.contract.name)
		self.assertEqual(row["module_product_warranty_years"], 15)
		self.assertEqual(row["inverter_warranty_years"], 10)

	def test_visit_compliance_counts_only_what_has_fallen_due(self):
		result = run(
			"Preventive Visit Compliance",
			filters={"company": self.company},
			ignore_prepared_report=True,
		)
		row = next(r for r in result["result"] if r["name"] == self.contract.name)
		self.assertEqual(row["planned"], 15)
		self.assertLessEqual(row["compliance_percent"], 100)

	def test_sla_report_shows_the_resolved_ticket(self):
		result = run(
			"Service Ticket SLA Compliance",
			filters={"company": self.company},
			ignore_prepared_report=True,
		)
		rows = [r for r in result["result"] if r["om_contract"] == self.contract.name]
		self.assertTrue(rows, "the ticket is missing from the SLA report")
		self.assertTrue(any(r["status"] == "Resolved" for r in rows))

	def test_root_cause_groups_by_cause_and_category(self):
		result = run(
			"Root Cause Analysis", filters={"company": self.company}, ignore_prepared_report=True
		)
		row = next(
			(r for r in result["result"] if r["root_cause"] == "Workmanship"), None
		)
		self.assertTrue(row, "the workmanship cause is not grouped")
		self.assertGreaterEqual(row["tickets"], 1)

	def test_renewal_pipeline_only_shows_contracts_inside_the_window(self):
		result = run(
			"Renewal Pipeline", filters={"company": self.company}, ignore_prepared_report=True
		)
		self.assertNotIn(
			self.contract.name,
			{row["name"] for row in result["result"]},
			"a contract with five years left is in the renewal pipeline",
		)

		window = frappe.db.get_single_value("A3 Sola Settings", "contract_expiry_window_days") or 90
		frappe.db.set_value(
			"Solar OM Contract", self.contract.name, "end_date",
			add_days(today(), int(window) - 1), update_modified=False,
		)
		result = run(
			"Renewal Pipeline", filters={"company": self.company}, ignore_prepared_report=True
		)
		self.assertIn(self.contract.name, {row["name"] for row in result["result"]})

	def test_scheme_compliance_flags_a_missed_visit(self):
		row_name = self.contract.visit_plan[0].name
		frappe.db.set_value(
			"Solar OM Visit Plan", row_name, {"scheduled_date": add_days(today(), -60), "status": "Missed"},
			update_modified=False,
		)
		result = run(
			"Scheme Obligation Compliance",
			filters={"company": self.company},
			ignore_prepared_report=True,
		)
		row = next(r for r in result["result"] if r["name"] == self.contract.name)
		self.assertGreaterEqual(row["missed_visits"], 1)
		self.assertTrue(row["at_risk"])
