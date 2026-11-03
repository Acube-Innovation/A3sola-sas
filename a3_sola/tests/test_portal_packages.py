# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's Packages page: only an admin manages packages; a package saved whole from the
page keeps its rows - their hidden `source` too - and is priced by the doctype's own rules;
one the records name is set to Draft, not deleted (api/portal_packages)."""

import json
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_packages as pp
from a3_sola.api import portal_users as pu


def _posted(data, **values):
	"""The package as the page posts it back."""
	return {"name": data["name"], "modified": data["modified"], "values": {**data["values"], **values},
		"tables": {f: t["rows"] for f, t in data["tables"].items()}}


class TestPortalPackages(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.source = frappe.db.get_value("Solar Package", {"name": ["in", frappe.get_all("Solar Package Module",
			filters={"parenttype": "Solar Package"}, pluck="parent")]})
		if not self.source:
			raise unittest.SkipTest("No package with a solar panel row to copy.")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def copy(self, code="PP-TEST-PKG"):
		data = pp.package(copy_from=self.source)
		self.assertIsNone(data["name"])
		self.assertFalse(data["values"]["item"] or data["values"]["bom"])
		return pp.save_package(json.dumps(_posted(data, specification_code=code), default=str))

	def test_only_an_admin_manages_packages(self):
		pu.save_user({"type": "Employee", "first_name": "Test", "last_name": "Manager", "email": "pp-manager@example.com",
			"mobile_no": "", "profile": "Solar Sales Management"})
		pu.save_user({"type": "Dealer", "first_name": "Test", "last_name": "Dealer", "email": "pp-dealer@example.com",
			"mobile_no": ""})
		for who in ("pp-manager@example.com", "pp-dealer@example.com"):
			frappe.set_user(who)
			for call in (pp.packages, lambda: pp.package(self.source), lambda: pp.set_status(self.source, "Active"),
					lambda: pp.delete_package(self.source), lambda: pp.save_package({"name": self.source})):
				with self.assertRaises(frappe.PermissionError):
					call()
		# A sales manager still reads packages - estimates offer them - but no longer changes them.
		frappe.set_user("pp-manager@example.com")
		self.assertTrue(frappe.has_permission("Solar Package", "read"))
		self.assertFalse(frappe.has_permission("Solar Package", "write"))
		self.assertFalse(frappe.has_permission("Solar Package", "create"))

	def test_a_copy_saves_and_is_priced(self):
		saved = self.copy()
		self.assertTrue(saved["name"])
		source = frappe.get_doc("Solar Package", self.source)
		self.assertEqual(len(saved["tables"]["modules"]["rows"]), len(source.modules))
		self.assertEqual(len(saved["tables"]["inverters"]["rows"]), len(source.inverters))
		# Priced as the source is: its inverter options carry the price (solar_package.price_for).
		from a3_sola.solar_crm.doctype.solar_package.solar_package import default_price

		self.assertEqual(default_price(frappe.get_doc("Solar Package", saved["name"])).system_cost,
			default_price(source).system_cost)

	def test_saving_again_keeps_rows_in_place_and_adds_no_computed_rows(self):
		saved = self.copy()
		doc = frappe.get_doc("Solar Package", saved["name"])
		before = {f: [(r.name, r.get("source")) for r in doc.get(f)] for f in ("kseb_expenses", "mounting_expenses", "modules")}
		rows = saved["tables"]["modules"]["rows"]
		rows[0]["module_count"] = (rows[0]["module_count"] or 0) + 1
		again = pp.save_package(json.dumps(_posted(saved), default=str))
		doc.reload()
		after = {f: [(r.name, r.get("source")) for r in doc.get(f)] for f in before}
		self.assertEqual(after, before)
		self.assertEqual(doc.modules[0].module_count, rows[0]["module_count"])
		self.assertEqual(again["tables"]["modules"]["rows"][0]["module_count"], rows[0]["module_count"])

	def test_a_stale_page_and_a_wrong_category_item_are_refused(self):
		saved = self.copy()
		stale = _posted(saved)
		pp.save_package(json.dumps(_posted(saved), default=str))
		with self.assertRaises(frappe.ValidationError):
			pp.save_package(json.dumps(stale, default=str))
		fresh = pp.package(saved["name"])
		inverter = frappe.db.get_value("Item", {"item_group": ["in", ["On-Grid Inverters", "Hybrid Inverters"]]})
		if inverter:
			posted = _posted(fresh)
			posted["tables"]["modules"][0]["module_item"] = inverter
			with self.assertRaises(frappe.ValidationError):
				pp.save_package(json.dumps(posted, default=str))

	def test_status_and_delete(self):
		saved = self.copy()
		pp.set_status(saved["name"], "Active")
		self.assertEqual(frappe.db.get_value("Solar Package", saved["name"], ["status", "is_active"]), ("Active", 1))
		pp.set_status(saved["name"], "Draft")
		self.assertEqual(frappe.db.get_value("Solar Package", saved["name"], ["status", "is_active"]), ("Draft", 0))
		self.assertEqual(pp.delete_package(saved["name"])["deleted"], 1)
		self.assertFalse(frappe.db.exists("Solar Package", saved["name"]))

	def test_a_package_in_use_goes_to_draft_not_away(self):
		used = frappe.db.get_value("Solar Design Estimate", {"solar_package": ["is", "set"]}, "solar_package")
		if not used:
			raise unittest.SkipTest("No estimate names a package.")
		result = pp.delete_package(used)
		self.assertEqual((result["deleted"], result["draft"]), (0, 1))
		self.assertEqual(frappe.db.get_value("Solar Package", used, "status"), "Draft")

	def test_the_menu_shows_packages_to_admins_only(self):
		from a3_sola.www.a3solaportal import nav_groups

		routes = lambda: {i["route"] for g in nav_groups() for i in g["items"]}
		self.assertIn("/a3solaportal/packages", routes())
		pu.save_user({"type": "Employee", "first_name": "Test", "last_name": "Sales", "email": "pp-sales@example.com",
			"mobile_no": "", "profile": "Solar Sales"})
		frappe.set_user("pp-sales@example.com")
		self.assertNotIn("/a3solaportal/packages", routes())
