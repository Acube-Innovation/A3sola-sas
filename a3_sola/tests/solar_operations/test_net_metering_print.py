# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Accept Customer is a financed job's second PM Surya Ghar task, and generates the portal's
Net Metering Agreement (NET.pdf) from the job - four pages, the consumer filled in."""

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import net_metering_print, portal_tasks
from a3_sola.setup import seed_stages
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.www.a3solaportal import collections, project_overview


class TestAcceptCustomerTask(FrappeTestCase):
	def test_it_is_second_in_the_pm_surya_ghar_column_on_financed_jobs_only(self):
		scheme = [t["code"] for t in seed_stages.TASKS if t["activity_scope"] == seed_stages.SCHEME]
		self.assertEqual(scheme[:3], ["NPA", "ACPT", "DAL"])
		task = next(t for t in seed_stages.TASKS if t["code"] == "ACPT")
		self.assertEqual(task["applicability"], "Financed Sales Only")
		self.assertEqual(task["documents"][0][2], net_metering_print.CODE)
		self.assertIn("ACPT", project_overview.FINANCED_ONLY_TASKS)


class TestNetMeteringPrint(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def test_the_agreement_is_the_jobs(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		f = net_metering_print.context(inst)
		self.assertEqual(f.consumer_number, inst.consumer_number)
		self.assertEqual(f.place, f.address)
		self.assertTrue(f.capacity)
		html = " ".join(net_metering_print.html(inst).split())
		# assertTrue, not assertIn: a failure would print the embedded font.
		self.assertTrue("This agreement stands valid upto my sanctioned electrical load capacity." in html)

	def test_it_prints_on_four_flowing_pages(self):
		name, pdf = net_metering_print.render(self.installation.name)
		self.assertTrue(name.startswith("Net Metering Agreement - "))
		reader = PdfReader(BytesIO(pdf))
		self.assertGreaterEqual(len(reader.pages), 3)
		text = " ".join(" ".join(p.extract_text() for p in reader.pages).split())
		self.assertIn("automatic agreement to the terms", text)

	def test_the_task_offers_view_and_download(self):
		links = portal_tasks._prints(frappe._dict(stage_code="ACPT"), self.installation.name)[net_metering_print.CODE]
		self.assertEqual([p["label"] for p in links], ["View Net Metering Agreement", "Download Net Metering Agreement"])
		# On the task's own form too, before and after it is created.
		form = collections.task_downloads(self.installation.name, "ACPT")
		self.assertEqual([p["label"] for p in form], ["View Net Metering Agreement", "Download Net Metering Agreement"])

	def test_it_is_set_as_the_portal_prints_it(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		html = net_metering_print.html(inst)
		self.assertTrue('font-family: "Agreement Sans", Helvetica' in html)
		self.assertTrue(f"Consumer No&nbsp;<u>{inst.consumer_number}</u>" in html)
		reader = PdfReader(BytesIO(net_metering_print.render(inst)[1]))
		fonts = {f["/BaseFont"] for p in reader.pages for f in (p["/Resources"].get("/Font") or {}).values()}
		self.assertTrue(any("LiberationSans" in str(f) for f in fonts))
