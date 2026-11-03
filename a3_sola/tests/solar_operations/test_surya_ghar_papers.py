# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""PM Surya Ghar Portal Registration asks for a pre-installation site photo and the quotation in
the RIM format - printed from the job's quotation, loan or no loan."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import loan_print, portal_tasks
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestSuryaGharPapers(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()

	def test_the_registration_expects_the_photo_and_the_rim_quotation(self):
		expected = {r.document_name: r for r in frappe.get_doc("Solar Installation", self.installation.name).documents
			if r.stage_code == "NPA"}
		self.assertIn("Pre-installation site photo", expected)
		self.assertTrue(expected["Pre-installation site photo"].is_mandatory)
		quotation = expected["Quotation (RIM format)"]
		self.assertEqual(frappe.db.get_value("Solar Document Template", quotation.solar_document_template, "template_code"),
			loan_print.QUOTATION)

	def test_the_rim_quotation_prints_only_once_there_is_a_quotation(self):
		frappe.db.set_value("Solar Installation", self.installation.name, {"quotation": None, "solar_design_estimate": None})
		row = frappe._dict(stage_code="NPA")
		self.assertEqual(portal_tasks._prints(row, self.installation.name), {})
		with self.assertRaises(frappe.ValidationError):
			loan_print.quotation(self.installation.name)
		quotation = frappe.db.get_value("Quotation", {"docstatus": ["<", 2]}, "name")
		if not quotation:
			self.skipTest("no quotation on this site")
		frappe.db.set_value("Solar Installation", self.installation.name, "quotation", quotation)
		prints = portal_tasks._prints(row, self.installation.name)[loan_print.QUOTATION]
		self.assertTrue(prints[0]["url"].endswith("installation=" + frappe.utils.quote(self.installation.name)))
		self.assertTrue(prints[0]["signable"])

	def test_with_no_quotation_it_is_priced_from_the_design_estimate(self):
		estimate = frappe.db.get_value("Solar Design Estimate", {"solar_package": ["is", "set"], "docstatus": ["<", 2]}, "name")
		if not estimate:
			self.skipTest("no design estimate with a package on this site")
		frappe.db.set_value("Solar Installation", self.installation.name, {"quotation": None, "solar_design_estimate": estimate})
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		q = loan_print.quotation_doc(inst)
		self.assertEqual(q.name, estimate)
		self.assertTrue(q.items and q.grand_total > 0)
		self.assertFalse(frappe.db.exists("Quotation", {"solar_design_estimate": estimate, "creation": [">", frappe.utils.add_to_date(None, minutes=-5)]}))
		self.assertIn(loan_print.QUOTATION, portal_tasks._prints(frappe._dict(stage_code="NPA"), self.installation.name))
