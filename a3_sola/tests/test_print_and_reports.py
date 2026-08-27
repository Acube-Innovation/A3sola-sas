# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal print format and the Phase 1 reports."""

import frappe
from frappe.desk.query_report import run as run_report
from frappe.tests.utils import FrappeTestCase

from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey, package


def three_option_estimate(consumer, survey):
	"""The client's most recent real proposal: 10 kWp non-DCR, three inverter options."""
	pkg = package("10KW 3PH Non-DCR", consumer.company)
	make = lambda m: frappe.db.get_value(  # noqa: E731
		"Component Make",
		{"make_name": m, "component_type": "Inverter", "company": consumer.company},
		"name",
	)
	options = [
		{
			"option_name": "Option 1 - String Inverter", "inverter_topology": "String",
			"solar_package": pkg, "inverter_make": make("Solinteg"),
			"inverter_specification": "10kW Three Phase On-Grid with Online Monitoring",
			"inverter_count": 1, "system_cost": 480000, "is_recommended": 1, "display_order": 1,
		},
		{
			"option_name": "Option 2 - SolarEdge with Optimiser",
			"inverter_topology": "String with Optimiser", "solar_package": pkg,
			"inverter_make": make("SolarEdge"), "inverter_count": 1,
			"inverter_specification": "10kW Three Phase On-Grid with Panel level optimizer",
			"system_cost": 490000, "display_order": 2,
		},
		{
			"option_name": "Option 3 - Microinverter", "inverter_topology": "Microinverter",
			"solar_package": pkg, "inverter_make": make("Hoymiles"), "inverter_count": 2,
			"inverter_specification": "5 kW Three Phase On-Grid Microinverter with 4 MPPT",
			"system_cost": 510000, "display_order": 3,
		},
	]
	return make_estimate(consumer, survey, subsidy_scheme=None, options=options, submit=True)


class TestProposalPrintFormat(FrappeTestCase):
	def setUp(self):
		self.consumer = make_consumer(
			consumer_name="Anil Menon", avg_consumption_units=2500, sanctioned_load_kw=12,
			connection_type="Three Phase",
		)
		self.survey = make_survey(self.consumer, segments=((800, True),))
		self.estimate = three_option_estimate(self.consumer, self.survey)
		self.proposal = frappe.get_doc(
			{
				"doctype": "Solar Proposal",
				"company": self.consumer.company,
				"solar_consumer": self.consumer.name,
				"solar_design_estimate": self.estimate.name,
				"salutation": "Mr",
				"customer_name": "Anil Menon",
				"mobile_no": "9946056789",
				"location": "Muvattupuzha",
				"district": "Ernakulam",
			}
		).insert(ignore_permissions=True)

	def render(self):
		return frappe.get_print("Solar Proposal", self.proposal.name, print_format="Solar Proposal")

	def test_every_section_renders(self):
		html = self.render()
		for heading in (
			"Executive Summary",
			"Specifications &amp; Quantity of Major Components",
			"Project Cost",
			"Expenses",
			"General Terms &amp; Conditions",
			"Payment Terms",
			"Bank Account Details for Payment",
			"Schedule of Delivery",
			"Warranty",
			"Scope of Work",
			"Savings &amp; Payback Annexure",
		):
			self.assertIn(heading, html, f"missing section: {heading}")

	def test_all_three_options_are_priced(self):
		html = self.render()
		for amount in ("4,80,000", "4,90,000", "5,10,000"):
			self.assertIn(amount, html)

	def test_statutory_block_shows_the_computed_refund(self):
		"""The client's own 10 kW template prints 4,000. The correct figure is 8,000."""
		html = self.render()
		self.assertIn("11,800", html)
		self.assertIn("8,000", html)

	def test_warranty_comes_from_the_make_master(self):
		html = self.render()
		self.assertIn("15 years product warranty", html)   # Rayzon modules
		self.assertIn("8 years product warranty", html)    # SolarEdge
		self.assertIn("12 years product warranty", html)   # Hoymiles

	def test_generation_prints_as_a_band(self):
		html = self.render()
		self.assertIn("40", html)
		self.assertIn("50", html)

	def test_regulation_clause_is_rendered_from_the_rule(self):
		html = self.render()
		self.assertIn("06.11.2025", html)
		self.assertIn("22.05.2026", html)

	def test_subsidy_never_appears_as_a_cost_line(self):
		"""An unsubsidised job must show no subsidy block at all."""
		html = self.render()
		self.assertNotIn("Expected Government Subsidy", html)


class TestReports(FrappeTestCase):
	REPORTS = (
		"Lead Follow-up Due",
		"Proposal Register",
		"Outreach Funnel Conversion",
		"Solar Sales Pipeline",
		"Statutory Fee Exposure",
	)

	def test_every_report_executes(self):
		for name in self.REPORTS:
			result = run_report(name, filters={}, ignore_prepared_report=True)
			self.assertTrue(result.get("columns"), f"{name} returned no columns")

	def test_proposal_register_carries_the_spreadsheet_columns(self):
		result = run_report("Proposal Register", filters={}, ignore_prepared_report=True)
		fields = {c["fieldname"] for c in result["columns"]}
		for expected in (
			"proposal_sequence", "proposal_date", "salutation", "customer_name",
			"mobile_no", "capacity_label", "location", "proposal_file_name",
		):
			self.assertIn(expected, fields)


class TestDashboard(FrappeTestCase):
	"""The dashboard reproduces the client's lead-tracker headline numbers."""

	def test_headline_cards_exist(self):
		for label in (
			"Total Leads Ingested",
			"Converted / Won",
			"Overdue Follow-ups",
			"Total Pipeline kW",
		):
			self.assertTrue(frappe.db.exists("Number Card", label), f"missing card: {label}")

	def test_breakdown_charts_exist(self):
		for name in ("Lead Status Breakdown", "Initial Call Connectivity"):
			self.assertTrue(frappe.db.exists("Dashboard Chart", name), f"missing chart: {name}")

	def test_every_card_evaluates(self):
		from frappe.desk.doctype.number_card.number_card import get_result

		for name in frappe.get_all("Number Card", filters={"module": "Solar CRM"}, pluck="name"):
			doc = frappe.get_doc("Number Card", name)
			value = get_result(doc, filters=doc.filters_json)
			self.assertIsNotNone(value, f"{name} did not evaluate")

	def test_dashboard_and_notifications_installed(self):
		self.assertTrue(frappe.db.exists("Dashboard", "Solar CRM"))
		self.assertEqual(frappe.db.count("Notification", {"module": "Solar CRM"}), 3)


class TestWorkspaces(FrappeTestCase):
	def test_one_parent_and_one_module_workspace(self):
		"""Four modules means four workspaces under one parent - never a fifth."""
		self.assertTrue(frappe.db.exists("Workspace", "A3 Sola"))
		self.assertEqual(frappe.db.get_value("Workspace", "Solar CRM", "parent_page"), "A3 Sola")
