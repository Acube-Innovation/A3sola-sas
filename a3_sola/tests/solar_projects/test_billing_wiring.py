# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The billing plan lives from the order, and tasks are what trigger its milestones."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from a3_sola.api import billing, tasks
from a3_sola.setup import seed_stages
from a3_sola.setup.install_projects import MILESTONE_TEMPLATES
from a3_sola.tests.solar_projects.fixtures import commissioned_project, installation_with_customer


def plan_for(installation):
	name = frappe.db.get_value("Solar Billing Plan", {"solar_installation": installation.name, "docstatus": ["<", 2]}, "name")
	return frappe.get_doc("Solar Billing Plan", name) if name else None


class TestPlanFromTheOrder(FrappeTestCase):
	def test_the_plan_is_created_once_per_installation_without_a_project(self):
		installation = installation_with_customer()
		name = billing.ensure_plan_for_installation(installation.name, replay=False)
		self.assertTrue(name)
		self.assertEqual(billing.ensure_plan_for_installation(installation.name), name)
		plan = frappe.get_doc("Solar Billing Plan", name)
		self.assertFalse(plan.project)
		self.assertEqual(plan.docstatus, 1)
		self.assertEqual(len(plan.milestones), 3)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Solar Billing Plan", "company": installation.company,
				 "solar_installation": installation.name, "customer": installation.customer,
				 "gross_contract_value": installation.gross_contract_value}
			).insert(ignore_permissions=True)

	def test_a_job_without_a_customer_or_value_gets_no_plan_yet(self):
		installation = installation_with_customer(gross_contract_value=0)
		self.assertIsNone(billing.ensure_plan_for_installation(installation.name))

	def test_the_order_triggers_the_advance_by_implication(self):
		installation = installation_with_customer()
		billing.ensure_plan_for_installation(installation.name, replay=False)
		billing.on_stage_completed(installation.name, "ORD")
		plan = plan_for(installation)
		advance = next(r for r in plan.milestones if r.trigger_type == "On Order")
		self.assertTrue(advance.is_triggered)
		self.assertEqual(flt(plan.total_triggered), flt(advance.milestone_amount))

	def test_completing_the_installation_work_order_task_triggers_its_milestone(self):
		installation = installation_with_customer()
		billing.ensure_plan_for_installation(installation.name, replay=False)
		tasks.complete_task(installation.name, "IWOI")  # not silent: completion is what notifies billing
		plan = plan_for(installation)
		row = next(r for r in plan.milestones if r.trigger_stage_code == "IWOI")
		self.assertTrue(row.is_triggered)
		self.assertTrue(frappe.db.exists("ToDo", {"reference_type": "Solar Billing Plan", "reference_name": plan.name}))

	def test_a_replay_fires_what_already_happened_without_raising_todos(self):
		installation = installation_with_customer()
		tasks.complete_task(installation.name, "IWOI")  # no plan yet: nothing to fire
		name = billing.ensure_plan_for_installation(installation.name, replay=True)
		plan = frappe.get_doc("Solar Billing Plan", name)
		row = next(r for r in plan.milestones if r.trigger_stage_code == "IWOI")
		self.assertTrue(row.is_triggered)
		self.assertFalse(frappe.db.exists("ToDo", {"reference_type": "Solar Billing Plan", "reference_name": name}))

	def test_commissioning_attaches_the_project_to_the_plan_that_already_exists(self):
		installation = installation_with_customer()
		name = billing.ensure_plan_for_installation(installation.name, replay=False)
		project, installation, _report = commissioned_project(installation)
		plans = frappe.get_all("Solar Billing Plan", filters={"solar_installation": installation.name, "docstatus": ["<", 2]}, pluck="name")
		self.assertEqual(plans, [name])
		self.assertEqual(frappe.db.get_value("Solar Billing Plan", name, "project"), project.name)

	def test_a_bank_funded_advance_settles_the_lender_milestone(self):
		installation = installation_with_customer(is_financed=1)
		name = billing.ensure_plan_for_installation(installation.name, replay=False)
		plan = frappe.get_doc("Solar Billing Plan", name)
		lender = [r for r in plan.milestones if r.funding_source == "Lender"]
		self.assertTrue(lender, "the financed template has lender-funded milestones")
		task = frappe.get_doc(
			{
				"doctype": "Installation Task", "solar_installation": installation.name, "task_code": "ADV",
				"status": "Completed", "payer": "Bank", "amount": lender[0].milestone_amount, "paid_on": today(),
				"payment_mode": "Loan Disbursement", "payment_reference": "UTR-ADV-0001",
			}
		)
		task.flags.ignore_permissions = True
		task.insert(ignore_permissions=True)
		task.submit()
		plan.reload()
		first = next(r for r in plan.milestones if r.funding_source == "Lender")
		self.assertEqual((first.is_triggered, first.matched_disbursement), (1, "UTR-ADV-0001"))

	def test_every_seeded_trigger_code_is_a_task(self):
		for spec in MILESTONE_TEMPLATES:
			for name, _trigger, code, *_rest in spec["milestones"]:
				if code:
					self.assertIn(code, seed_stages.TASK_CODES, f"{spec['template_name']}: {name} keys to {code}")
		for old, new in billing.TRIGGER_CODE_MAP.items():
			self.assertIn(new, seed_stages.TASK_CODES, f"{old} -> {new}")
