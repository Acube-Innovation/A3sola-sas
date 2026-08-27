# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Milestone billing, the client's 70:20:10 terms, and the one rule with no exception."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from a3_sola.api import billing, gst
from a3_sola.tests.fixtures import default_company, make_company
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_projects.fixtures import (
	billing_plan,
	commissioned_project,
	make_statutory_fee,
)


class TestMilestoneTemplates(FrappeTestCase):
	def test_the_clients_three_templates_are_seeded(self):
		names = frappe.get_all(
			"Billing Milestone Template",
			filters={"company": default_company()},
			pluck="template_name",
		)
		self.assertIn("Standard 70:20:10 - Net Meter Purchased", names)
		self.assertIn("Standard 70:20:10 - Net Meter from DISCOM", names)
		self.assertIn("Financed (Jan Samarth) 70:30", names)

	def test_every_template_totals_a_hundred_percent(self):
		for name in frappe.get_all("Billing Milestone Template", pluck="name"):
			doc = frappe.get_doc("Billing Milestone Template", name)
			self.assertEqual(
				flt(sum(flt(r.percentage) for r in doc.milestones), 2),
				100.00,
				f"{doc.template_name} does not total 100%",
			)

	def test_financed_job_gets_the_lender_template(self):
		name = billing.resolve_template(default_company(), is_financed=True)
		self.assertEqual(
			frappe.db.get_value("Billing Milestone Template", name, "template_name"),
			"Financed (Jan Samarth) 70:30",
		)

	def test_discom_rented_meter_defers_the_last_slice_to_documents(self):
		"""With a DISCOM meter there is no purchase to invoice against at commissioning."""
		name = billing.resolve_template(
			default_company(), net_meter_mode="Availed from DISCOM on Rental"
		)
		doc = frappe.get_doc("Billing Milestone Template", name)
		self.assertEqual(doc.template_name, "Standard 70:20:10 - Net Meter from DISCOM")
		self.assertEqual(doc.milestones[-1].trigger_stage_code, "KTST")

	def test_self_funded_purchased_meter_is_the_default(self):
		name = billing.resolve_template(
			default_company(), net_meter_mode="Purchased by Customer", is_financed=False
		)
		self.assertEqual(
			frappe.db.get_value("Billing Milestone Template", name, "template_name"),
			"Standard 70:20:10 - Net Meter Purchased",
		)


class TestBillingPlan(FrappeTestCase):
	def test_milestone_amounts_follow_the_contract_value(self):
		project, _installation, _ = commissioned_project()
		plan = billing_plan(project)
		contract = flt(plan.gross_contract_value)
		self.assertEqual(flt(plan.milestones[0].milestone_amount, 2), flt(contract * 0.70, 2))
		self.assertEqual(flt(plan.milestones[1].milestone_amount, 2), flt(contract * 0.20, 2))
		self.assertEqual(flt(plan.milestones[2].milestone_amount, 2), flt(contract * 0.10, 2))

	def test_net_payable_excludes_the_subsidy(self):
		project, _installation, _ = commissioned_project()
		plan = billing_plan(project)
		self.assertEqual(
			flt(plan.net_payable_by_customer, 2),
			flt(plan.gross_contract_value - plan.expected_subsidy_amount, 2),
		)

	def test_statutory_fees_are_tracked_outside_the_contract(self):
		project, installation, _ = commissioned_project()
		make_statutory_fee(installation, amount=1180.0)
		plan = billing_plan(project)
		billing.recompute_summary(plan)
		self.assertEqual(flt(plan.statutory_fees_paid_by_company, 2), 1180.00)
		self.assertEqual(flt(plan.statutory_outstanding, 2), 1180.00)
		self.assertEqual(flt(plan.total_planned, 2), flt(plan.gross_contract_value, 2))

	def test_a_plan_without_a_template_is_refused_not_guessed(self):
		"""A company with no template gets a clear error, never an invented split."""
		company = make_company("Templateless Solar Co", "TSC", seed=False)
		plan = frappe.new_doc("Solar Billing Plan")
		plan.company = company
		plan.gross_contract_value = 100000
		plan.consumer_category = "Residential"
		plan.net_meter_mode = "Purchased by Customer"
		with self.assertRaises(frappe.ValidationError):
			billing.build_plan(plan)


class TestSubsidyNeverOnAnInvoice(FrappeTestCase):
	"""THE ABSOLUTE RULE. Every route in has to be closed."""

	def _invoice(self, **kwargs):
		project, _installation, _ = commissioned_project()
		invoice = frappe.new_doc("Sales Invoice")
		invoice.company = project.company
		invoice.customer = frappe.db.get_value("Project", project.name, "customer")
		invoice.posting_date = today()
		invoice.project = project.name
		return invoice

	def test_subsidy_as_an_item_name_is_refused(self):
		invoice = self._invoice()
		invoice.append("items", {"item_name": "PM Surya Ghar Subsidy", "qty": 1, "rate": 78000})
		with self.assertRaises(frappe.ValidationError):
			billing.reject_subsidy_on_invoice(invoice)

	def test_subsidy_in_a_description_is_refused(self):
		invoice = self._invoice()
		invoice.append(
			"items",
			{"item_name": "Solar plant", "description": "Less subsidy receivable", "qty": 1, "rate": 1},
		)
		with self.assertRaises(frappe.ValidationError):
			billing.reject_subsidy_on_invoice(invoice)

	def test_subsidy_as_a_tax_row_is_refused(self):
		invoice = self._invoice()
		invoice.append("items", {"item_name": "Solar plant", "qty": 1, "rate": 1})
		invoice.append(
			"taxes",
			{
				"charge_type": "Actual",
				"description": "Subsidy adjustment",
				"account_head": frappe.db.get_value("Account", {"company": invoice.company}, "name"),
				"tax_amount": -78000,
			},
		)
		with self.assertRaises(frappe.ValidationError):
			billing.reject_subsidy_on_invoice(invoice)

	def test_an_ordinary_invoice_passes(self):
		invoice = self._invoice()
		invoice.append(
			"items",
			{
				"item_name": "Grid connected rooftop solar power plant",
				"description": "3 kWp",
				"qty": 1,
				"rate": 195000,
			},
		)
		billing.reject_subsidy_on_invoice(invoice)


class TestGSTValuation(FrappeTestCase):
	def test_no_rate_is_hardcoded_anywhere_in_the_module(self):
		"""If a rate ever appears in code it stops being the CA's decision."""
		import inspect

		source = inspect.getsource(gst)
		for forbidden in ("0.7", "0.3", "13.8", "70 *", "* 70", "= 70", "= 30", "12 %", "18 %"):
			self.assertNotIn(forbidden, source, f"{forbidden!r} looks like a hardcoded rate")

	def test_the_seeded_rule_is_inactive_until_a_ca_confirms(self):
		rules = frappe.get_all(
			"Solar GST Valuation Rule",
			filters={"company": default_company()},
			fields=["name", "is_active"],
		)
		self.assertTrue(rules, "no rule seeded")
		self.assertTrue(all(not r.is_active for r in rules), "a GST rule was seeded active")

	def test_billing_without_an_active_rule_is_refused_not_guessed(self):
		with self.assertRaises(frappe.ValidationError):
			gst.resolve_valuation(default_company(), "Residential")

	def test_postings_need_both_gates(self):
		frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 1)
		frappe.db.set_single_value("A3 Sola Settings", "gst_treatment_confirmed_by_ca", 0)
		self.assertFalse(gst.postings_enabled())

		frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 0)
		frappe.db.set_single_value("A3 Sola Settings", "gst_treatment_confirmed_by_ca", 1)
		self.assertFalse(gst.postings_enabled())

		frappe.db.set_single_value("A3 Sola Settings", "enable_accounting_postings", 1)
		self.assertTrue(gst.postings_enabled())

	def test_both_gates_are_off_out_of_the_box(self):
		settings = frappe.get_single("A3 Sola Settings")
		self.assertFalse(
			settings.meta.get_field("enable_accounting_postings").default in ("1", 1),
			"accounting postings must not default on",
		)
		self.assertFalse(
			settings.meta.get_field("gst_treatment_confirmed_by_ca").default in ("1", 1),
			"the CA confirmation must never be pre-ticked",
		)

	def test_reimbursement_item_carries_the_receipt(self):
		item = gst.build_reimbursement_item(1180.0, "KSEB-REC-99")
		self.assertEqual(flt(item["rate"], 2), 1180.00)
		self.assertIn("KSEB-REC-99", item["description"])
		self.assertNotIn("subsidy", item["description"].lower())
