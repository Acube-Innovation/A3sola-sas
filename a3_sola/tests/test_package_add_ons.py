# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's Optional Add-ons - one more of its panel later, the inverter warranty taken to
25 years - are priced on the package and printed in the proposal's 3.3.3, in no total."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import print_cover
from a3_sola.solar_crm.doctype.solar_package.solar_package import default_add_ons, extra_panel_item
from a3_sola.tests.fixtures import make_consumer, make_estimate, package


class TestPackageAddOns(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_the_extra_panel_is_one_of_the_packages_own(self):
		doc = frappe.get_doc({"doctype": "Solar Package", "modules": [{"module_wattage": 560, "is_default": 1}]})
		self.assertEqual(extra_panel_item(doc), "Supply and Installation of 1X560Wp Solar Panel")
		rows = default_add_ons(doc)
		self.assertEqual([(r["add_on_type"], r["amount"]) for r in rows], [("Extra Panel", 17500), ("Warranty Extension", 10000)])
		self.assertIn("13th Year to 25th year", rows[1]["item"])

	def test_a_new_package_offers_the_usual_add_ons_and_keeps_its_own(self):
		doc = frappe.get_doc({"doctype": "Solar Package"})
		doc.before_insert()
		self.assertEqual(len(doc.optional_add_ons), 2)
		own = frappe.get_doc({"doctype": "Solar Package", "optional_add_ons": [{"add_on_type": "Other", "item": "Monitoring", "amount": 500}]})
		own.before_insert()
		self.assertEqual([r.item for r in own.optional_add_ons], ["Monitoring"])

	def test_a_blank_extra_panel_row_is_named_from_the_panel(self):
		doc = frappe.get_doc({"doctype": "Solar Package", "modules": [{"module_wattage": 550, "is_default": 1}],
			"optional_add_ons": [{"add_on_type": "Extra Panel", "item": "", "amount": 17500}]})
		doc.name_extra_panel_add_ons()
		self.assertEqual(doc.optional_add_ons[0].item, "Supply and Installation of 1X550Wp Solar Panel")

	def test_the_proposal_lists_each_add_on_once_with_ordinals_raised(self):
		consumer = make_consumer()
		pkg = package("3Kw 1PH", consumer.company)
		frappe.db.delete("Solar Package Add-on", {"parent": pkg})
		for idx, (item, amount) in enumerate((("Warranty Extension for Inverter - 13th Year to 25th year", 10000),), 1):
			frappe.get_doc({"doctype": "Solar Package Add-on", "parent": pkg, "parenttype": "Solar Package",
				"parentfield": "optional_add_ons", "idx": idx, "item": item, "amount": amount}).db_insert()
		estimates = [make_estimate(consumer, solar_package=pkg) for _ in range(2)]
		rows = print_cover.add_on_rows(estimates)
		self.assertEqual(len(rows), 1)
		self.assertIn("13<sup>th</sup> Year to 25<sup>th</sup> year", rows[0]["item_html"])
		self.assertEqual(rows[0]["amount_text"], "10,000")

	def test_the_add_ons_follow_the_kseb_expenses_or_turn_the_page(self):
		short = [{"label": "", "rows": [{"item": "Plant"}]}]
		self.assertEqual(print_cover.cost_pages(short, 3, False, 2)[-1], {"options": short, "kseb": True, "add_ons": True})
		long = [{"label": "Option {0}".format(i), "rows": [{"item": "x" * 170}] * 4} for i in range(3)]
		pages = print_cover.cost_pages(long, 3, True, 2)
		self.assertEqual(pages[-1], {"options": [], "kseb": False, "add_ons": True})
		self.assertTrue(pages[-2]["kseb"])
		self.assertFalse(print_cover.cost_pages(short, 3, False, 0)[-1]["add_ons"])


class TestEstimateAddOns(FrappeTestCase):
	"""A design estimate takes its package's optional add-ons, changed per estimate, and its
	proposal prints the estimate's own - never added to the commercials."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		self.pkg = package("3Kw 1PH", self.consumer.company)
		frappe.db.delete("Solar Package Add-on", {"parent": self.pkg})
		frappe.get_doc({"doctype": "Solar Package Add-on", "parent": self.pkg, "parenttype": "Solar Package",
			"parentfield": "optional_add_ons", "idx": 1, "add_on_type": "Other", "item": "Monitoring", "amount": 500}).db_insert()
		frappe.clear_document_cache("Solar Package", self.pkg)

	def test_the_estimate_takes_its_packages_add_ons(self):
		est = make_estimate(self.consumer, solar_package=self.pkg)
		self.assertEqual([(r.item, r.amount) for r in est.optional_add_ons], [("Monitoring", 500)])
		self.assertNotIn("optional_add_ons", [line["key"] for line in est.commercials()["lines"]])

	def test_the_proposal_prints_the_estimates_own(self):
		est = make_estimate(self.consumer, solar_package=self.pkg)
		est.optional_add_ons[0].item = "Monitoring for 5 years"
		est.save()
		self.assertEqual([r["item_html"] for r in print_cover.add_on_rows([est])], ["Monitoring for 5 years"])

	def test_the_builder_shows_them_after_the_charges_with_the_panel_fields(self):
		from a3_sola.api import portal_estimate

		est = make_estimate(self.consumer, solar_package=self.pkg)
		section = portal_estimate._sections(est)[-1]
		self.assertEqual(section["key"], "optional_add_ons")
		fields = {f["fieldname"] for f in section["fields"]}
		panel = {f["fieldname"] for f in portal_estimate.SECTION_BY_KEY["panels"]["fields"]}
		self.assertLessEqual(panel, fields)
		self.assertTrue({"add_on_type", "item"} <= fields)

	def test_an_add_on_taken_is_added_to_the_commercials(self):
		est = make_estimate(self.consumer, solar_package=self.pkg)
		est.append("optional_add_ons", {"add_on_type": "Extra Panel", "panel_capacity_wp": 620, "panel_count": 2,
			"rate": 17500, "is_option": 0})
		est.save()
		row = est.optional_add_ons[-1]
		self.assertEqual((row.nos, row.amount), (2, 35000))
		self.assertEqual(row.item, "Supply and Installation of 2X620Wp Solar Panel")
		line = next(line for line in est.commercials()["lines"] if line["key"] == "optional_add_ons")
		self.assertEqual(line["amount"], 35000)
		# Taken, it is in the price: the proposal lists only those still offered.
		self.assertEqual([r["item_html"] for r in print_cover.add_on_rows([est])], ["Monitoring"])
