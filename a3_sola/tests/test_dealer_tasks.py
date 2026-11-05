# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A dealer's lead is the dealer's to run: he owns it, and the lead owner's tasks on its
project - asking for the advance, the customer review - are his to do (api/payment_tasks,
api/payment_followup, api/tasks, api/partner_scope)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import partner_scope, payment_tasks, task_assignees, tasks

DEALER = "test-task-dealer@example.com"


def _dealer():
	if not frappe.db.exists("User", DEALER):
		frappe.get_doc({"doctype": "User", "email": DEALER, "first_name": "Task Dealer", "send_welcome_email": 0,
			"role_profile_name": "Solar Dealer"}).insert(ignore_permissions=True)
	return DEALER


class TestDealerRunsHisLeads(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.dealer = _dealer()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_a_lead_a_dealer_creates_is_his(self):
		frappe.set_user(self.dealer)
		lead = frappe.get_doc({"doctype": "Lead", "lead_name": "Dealer Made Lead", "loan_required": "No"}).insert()
		self.assertEqual((lead.lead_owner, lead.a3s_dealer), (self.dealer, self.dealer))

	def _job_with(self, *codes):
		for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
			inst = frappe.get_doc("Solar Installation", name)
			have = {r.stage_code: r for r in inst.stages}
			if not (inst.lead or inst.solar_consumer):
				continue
			if all(c in have and have[c].status not in ("Completed", "Skipped") for c in codes):
				# The dealer's sale: through its lead, or its customer (api/partner_scope).
				if inst.lead:
					frappe.db.set_value("Lead", inst.lead, "a3s_dealer", self.dealer)
				else:
					frappe.db.set_value("Solar Consumer", inst.solar_consumer, "dealer", self.dealer)
				for c in codes:
					task_assignees.put(inst, c, [self.dealer])
				inst.flags.ignore_validate_update_after_submit = True
				inst.flags.ignore_mandatory = True
				inst.save(ignore_permissions=True)
				return inst
		self.skipTest("No open project with tasks {0}.".format(", ".join(codes)))

	def test_the_dealer_opens_and_completes_his_task_but_no_other(self):
		inst = self._job_with("REVIEW")
		other = next((r.stage_code for r in inst.stages if r.stage_code != "REVIEW"
			and r.status not in ("Completed", "Skipped") and not task_assignees.holds(inst, r.stage_code, self.dealer)), None)
		frappe.set_user(self.dealer)
		self.assertTrue(partner_scope.may_open_task(inst.name, "REVIEW"))
		# The 50%-paid gate is the project's own rule, not who may complete: set aside here.
		with patch.object(tasks, "_half_paid"):
			tasks.complete_from_board(inst.name, "REVIEW", remarks="Review collected on WhatsApp", confirmed=1)
		self.assertEqual(frappe.db.get_value("Installation Stage Log", {"parent": inst.name, "stage_code": "REVIEW"}, "status"),
			"Completed")
		if other:
			self.assertFalse(partner_scope.may_open_task(inst.name, other))
			with self.assertRaises(frappe.PermissionError), patch.object(tasks, "_half_paid"):
				tasks.complete_from_board(inst.name, other, remarks="not mine", confirmed=1)

	def test_the_dealer_sees_and_asks_for_the_advance_but_records_no_money(self):
		inst = self._job_with("ADV")
		frappe.set_user(self.dealer)
		state = payment_tasks.state(inst.name, "ADV")
		self.assertFalse(state["can_mark"])
		self.assertFalse(state["can_confirm"])
		# Another payment task stays closed to him.
		other = next((r.stage_code for r in inst.stages if payment_tasks.is_payment_task(r.stage_code) and r.stage_code != "ADV"), None)
		if other:
			with self.assertRaises(frappe.PermissionError):
				payment_tasks.state(inst.name, other)
