# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Data for Completion Report prints from the Serials to Electrical Contractor task, on
the letterhead or on plain paper."""

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import completion_print, portal_tasks
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestCompletionReportPrint(FrappeTestCase):
	def setUp(self):
		self.job = make_installation()
		self.job.append("serials", {"component_type": "Module", "serial_no": "AS2609112B0720"}).db_insert()
		self.job.append("serials", {"component_type": "Inverter", "serial_no": "SJ4923-07B1332FE-BE"}).db_insert()

	def text(self, letterhead):
		completion_print.pdf(self.job.name, letterhead=letterhead)
		content = frappe.local.response.filecontent
		self.assertTrue(content.startswith(b"%PDF"))
		return " ".join(PdfReader(BytesIO(content)).pages[0].extract_text().split())

	def test_it_prints_with_and_without_the_letterhead(self):
		consumer = frappe.db.get_value("Solar Consumer", self.job.solar_consumer, "consumer_name").upper()
		for letterhead in (1, 0):
			text = self.text(letterhead)
			for expected in ("DATA FOR COMPLETION REPORT", consumer, "AS2609112B0720", "SJ4923-07B1332FE-BE"):
				self.assertIn(expected, text)

	def test_the_task_offers_both_prints(self):
		panel = portal_tasks.task_documents(self.job.name, "MATL")
		prints = [p for d in panel["documents"] for p in d.get("prints") or []]
		self.assertEqual({p["url"].split("letterhead=")[-1] for p in prints if "completion_print" in p["url"]}, {"0", "1"})
