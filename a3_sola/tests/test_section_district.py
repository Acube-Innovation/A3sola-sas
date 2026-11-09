# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The DISCOM Section list offers only the sections in the district of the connection: on a
customer, the installation site's district when the site is not the permanent address."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_fields


class TestSectionDistrict(FrappeTestCase):
	def test_the_connections_district(self):
		cd = portal_fields.connection_district
		self.assertEqual(cd({"permanent_address_same": "Yes", "permanent_district": "Thrissur, Kerala",
			"site_district": "Ernakulam, Kerala"}), "Thrissur, Kerala")
		self.assertEqual(cd({"permanent_address_same": "No", "permanent_district": "Thrissur, Kerala",
			"site_district": "Ernakulam, Kerala"}), "Ernakulam, Kerala")
		# Not answered yet: the permanent address's.
		self.assertEqual(cd({"permanent_address_same": "", "permanent_district": "Thrissur, Kerala"}), "Thrissur, Kerala")
		# A lead or a survey: its District.
		self.assertEqual(cd({"district": "Kollam, Kerala"}), "Kollam, Kerala")
		self.assertIsNone(cd({"permanent_address_same": "No", "permanent_district": "Thrissur, Kerala"}))

	def test_the_list_follows_the_installation_site(self):
		district = frappe.db.get_value("Indian District", {"district_name": "Thrissur"}, ["name", "district_name"], as_dict=True)
		if not district:
			self.skipTest("Kerala's districts are not on this site.")
		filters = portal_fields._also_filters("discom_section", {"permanent_address_same": "No",
			"site_district": district.name, "permanent_district": "Elsewhere"})
		self.assertEqual(filters, [["district", "=", "Thrissur"]])
		self.assertEqual(portal_fields._also_filters("discom_section", {}), [])
		self.assertEqual(portal_fields._also_filters("district", {"district": district.name}), [])
		discom = frappe.db.get_value("DISCOM Section", {"district": "Thrissur", "section_code": ["is", "set"]}, "discom")
		if not discom:
			self.skipTest("No Thrissur sections on this site.")
		choices = portal_fields.dependent_options("Solar Consumer", "discom_section", discom,
			frappe.as_json({"permanent_address_same": "No", "site_district": district.name}))["choices"]
		self.assertTrue(choices)
		self.assertTrue(all("(Thrissur)" in c["label"] for c in choices))


class TestUncodedSection(FrappeTestCase):
	"""A bill's section on file without its code (from before KSEB's directory) is one the form's
	list cannot show: it is offered to be added - which gives it the bill's code - and its
	district is the site's when the bill's address names none."""

	def test_the_bill_offers_it_and_takes_its_district(self):
		from a3_sola.api import kseb_bill

		discom = kseb_bill.kseb_discom()
		district = frappe.db.get_value("Indian District", {"district_name": "Thrissur"}, "name")
		if not (discom and district):
			self.skipTest("No KSEB DISCOM or Kerala districts on this site.")
		name = "Zzuncoded Test Office"
		frappe.get_doc({"doctype": "DISCOM Section", "section_name": name, "discom": discom, "district": "Thrissur",
			"company": frappe.db.get_value("DISCOM Section", {"discom": discom}, "company")}).insert(ignore_permissions=True)
		parsed = {"section_code": "9991", "section_name": name, "consumer_number": "1", "name": "TEST",
			"address": "SOME HOUSE, SOME ROAD P.O."}
		with patch.object(kseb_bill, "extract_text", return_value=("", "pdf-text")), \
				patch.object(kseb_bill, "parse", return_value=parsed):
			out = kseb_bill.read_content(b"", "bill.pdf", "Solar Consumer")
		self.assertNotIn("discom_section", out["fields"])
		self.assertEqual(out["fields"]["site_district"], district)
		self.assertEqual(out["missing_section"], {"code": "9991", "name": name, "district": "Thrissur"})
		row = portal_fields.add_discom_section(discom=discom, section_name=name, section_code="9991",
			district=district, doctype="Solar Consumer")
		self.assertEqual(frappe.db.get_value("DISCOM Section", row["value"], "section_code"), "9991")
		self.assertEqual(frappe.db.count("DISCOM Section", {"section_name": name}), 1)
