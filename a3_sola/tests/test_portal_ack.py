# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The National Portal's acknowledgement read into the Portal Registration task (api/portal_ack),
and the task's Applied By starting as the person it is assigned to."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_ack

# The acknowledgement's text as the PDF reader gives it, made-up applicant.
ACK = """                   Acknowledgement for Submission of Rooftop Solar Application
Sh/Smt T TESTER                                                                                       Date: 28-10-2026
1. Your application for installation of Rooftop Solar Plant under Pradhan Mantri Surya Ghar: Muft Bijli
     Yojana is successfully submitted with Application Reference Number – NP-KLSEB26-10000001 and
     Applied Capacity – 3.000 kWp
1          Application Reference Number/ Date                    NP-KLSEB26-10000001 / 28-10-2026
2          Name of Applicant                                     T TESTER
5          Consumer Account Number in Discom                     1155000000001
"""


class TestPortalAck(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_the_number_and_date_are_read(self):
		found = portal_ack.parse(ACK)
		self.assertTrue(portal_ack.is_acknowledgement(ACK))
		self.assertEqual((found["application_number"], found["application_date"], found["name"], found["consumer_number"], found["capacity_kw"]),
			("NP-KLSEB26-10000001", "2026-10-28", "T TESTER", "1155000000001", 3.0))
		self.assertEqual(portal_ack.fields_of(found), {"application_number": "NP-KLSEB26-10000001",
			"national_portal_application_id": "NP-KLSEB26-10000001", "application_date": "2026-10-28"})

	def test_another_document_is_not_read(self):
		self.assertFalse(portal_ack.is_acknowledgement("Digital Sanction for your application"))

	def test_applied_by_starts_as_the_tasks_assignee(self):
		from a3_sola.www.a3solaportal.collections import task_source

		inst = frappe.db.get_value("Installation Stage Log", {"stage_code": "NPA", "parenttype": "Solar Installation",
			"task_document": ["is", "not set"]}, "parent")
		if not inst:
			self.skipTest("No project with an open NPA task.")
		someone = frappe.db.get_value("User", {"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]})
		frappe.db.delete("Installation Task Assignee", {"parent": inst, "stage_code": "NPA"})
		frappe.get_doc({"doctype": "Installation Task Assignee", "parent": inst, "parenttype": "Solar Installation",
			"parentfield": "task_assignees", "stage_code": "NPA", "user": someone, "idx": 99}).db_insert()
		self.assertEqual(task_source("portal-applications", inst, "NPA").get("applied_by"), someone)
		# Nobody assigned: the one filling it in.
		frappe.db.delete("Installation Task Assignee", {"parent": inst, "stage_code": "NPA"})
		frappe.db.set_value("Installation Stage Log", {"parent": inst, "stage_code": "NPA"}, "assigned_to", None)
		self.assertEqual(task_source("portal-applications", inst, "NPA").get("applied_by"), "Administrator")
