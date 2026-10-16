# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Serials to Electrical Contractor is worked on its own page: the contractor, the job's
serials, the Data for Completion Report - and sending it, which completes the task."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_share, serials_task, tasks
from a3_sola.tests.solar_operations.fixtures import capture_serials, make_installation
from a3_sola.tests.solar_operations.test_contractor_and_work_orders import make_contractor
from a3_sola.tests.solar_operations.test_tasks import task_row

PDF = ("Data for Completion Report.pdf", b"%PDF-1.4 test")
ACCOUNT = frappe._dict(email_id="projects@renewcore.in", name="Renewcore")


class TestSerialsTask(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()
		self.contractor = make_contractor(company=self.installation.company, mobile_no="9000022222")
		frappe.db.set_value("Solar Installation", self.installation.name, "electrical_contractor", self.contractor.name)

	def test_the_task_opens_its_own_page(self):
		target = tasks.open_task(self.installation.name, "MATL", create_draft=0)
		self.assertTrue(target["url"].endswith("/tasks/MATL"))
		self.assertIsNone(target["doctype"])

	def test_the_page_shows_the_contractor_and_the_serials(self):
		capture_serials(self.installation, modules=6, inverters=1)
		state = serials_task.state(self.installation.name)
		self.assertEqual(state["contractor"]["contractor_name"], self.contractor.contractor_name)
		self.assertEqual((len(state["serials"]["Module"]), len(state["serials"]["Inverter"])), (6, 1))
		self.assertEqual(state["email"]["to"], "sparks@example.com")
		self.assertTrue(state["whatsapp"].startswith("https://wa.me/919000022222"))
		self.assertEqual([p["label"] for p in state["prints"]], ["On letterhead", "Without letterhead"])
		self.assertTrue(state["prints"][1]["download"].endswith("letterhead=0&download=1"))

	def test_nothing_to_send_without_serials(self):
		state = serials_task.state(self.installation.name)
		self.assertFalse(state["ready"])
		self.assertEqual(state["whatsapp"], "")
		with self.assertRaises(frappe.ValidationError):
			serials_task.send_email(self.installation.name, "sparks@example.com", "S", "M")

	def test_typed_serials_start_the_task(self):
		state = serials_task.save(self.installation.name, module_serials="A1\nA2\na2", inverter_serials="I1")
		self.assertEqual((state["serials"]["Module"], state["serials"]["Inverter"]), (["A1", "A2"], ["I1"]))
		self.assertEqual(state["task"]["status"], "In Progress")

	def test_emailing_the_sheet_completes_the_task(self):
		capture_serials(self.installation, modules=2, inverters=1)
		with patch.object(portal_share, "_outgoing_account", return_value=ACCOUNT), \
				patch("a3_sola.api.completion_print.render", return_value=PDF), \
				patch("frappe.core.doctype.communication.email.make") as make:
			state = serials_task.send_email(self.installation.name, "sparks@example.com", "Serials", "Attached", letterhead=0)
		kwargs = make.call_args.kwargs
		self.assertEqual((kwargs["doctype"], kwargs["name"], kwargs["recipients"]),
			("Solar Installation", self.installation.name, "sparks@example.com"))
		self.assertEqual(kwargs["attachments"][0]["fname"], PDF[0])
		self.assertEqual((state["task"]["status"], state["task"]["sent_to"]), ("Completed", "sparks@example.com"))
		row, _doc = task_row(self.installation, "MATL")
		self.assertEqual(row.status, "Completed")

	def test_mark_complete_after_whatsapp(self):
		capture_serials(self.installation, modules=1, inverters=1)
		state = serials_task.mark_complete(self.installation.name, note="Sent on WhatsApp")
		self.assertEqual(state["task"]["status"], "Completed")
		with self.assertRaises(frappe.ValidationError):
			serials_task.mark_complete(self.installation.name)

	def test_the_whatsapp_link_opens_the_sheet_for_this_job_only(self):
		capture_serials(self.installation, modules=1, inverters=1)
		key = portal_share.share_key("Solar Installation", self.installation.name)
		with patch("a3_sola.api.completion_print.render", return_value=PDF):
			portal_share.shared_pdf("Solar Installation", self.installation.name, key)
		self.assertEqual(frappe.local.response.filecontent, PDF[1])
		other = make_installation()
		with self.assertRaises(frappe.PermissionError):
			portal_share.shared_pdf("Solar Installation", other.name, key)
