# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's Optional Add-ons - one more of its panel later, the inverter warranty taken to
25 years - are priced on the package and printed in the proposal's 3.3.3, in no total."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import package_items, portal_packages, print_cover
from a3_sola.solar_crm.doctype.solar_package.solar_package import default_add_ons, extra_panel_item
from a3_sola.tests.fixtures import default_company, make_consumer, make_estimate, package


def item_group(name, parent="All Item Groups", is_group=0):
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": parent,
			"is_group": is_group}).insert(ignore_permissions=True)
	return name


def add_on_item(code, group):
	if not frappe.db.exists("Item", code):
		frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": group,
			"stock_uom": "Nos", "is_stock_item": 0}).insert(ignore_permissions=True)
	return code


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


class TestAddOnRows(FrappeTestCase):
	"""A package add-on's Item is of an add-on group - Optional Add-ons, or any group set under
	another - and the row is priced at its Rate x Quantity."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.top = item_group("Add-on Test Kit", is_group=1)
		self.sub = item_group("Add-on Test Kit Spares", parent=self.top)
		self.loose = item_group("Add-on Test Loose")
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", default_company()))
		self.kept = [r.as_dict() for r in self.pkg.optional_add_ons]

	def tearDown(self):
		frappe.set_user("Administrator")
		pkg = frappe.get_doc("Solar Package", self.pkg.name)
		pkg.set("optional_add_ons", [{k: r.get(k) for k in ("add_on_type", "item_code", "item", "rate", "qty", "amount")}
			for r in self.kept])
		pkg.save()

	def mine(self):
		return [r for r in self.pkg.optional_add_ons if r.add_on_type == "Other"]

	def test_the_groups_are_optional_add_ons_then_every_group_under_another(self):
		groups = package_items.add_on_groups()
		self.assertEqual(groups[0], "Optional Add-ons")
		self.assertIn(self.sub, groups)
		self.assertFalse({self.top, self.loose, "All Item Groups"} & set(groups))

	def test_a_row_is_its_rate_times_its_quantity_in_its_items_group(self):
		fuse = add_on_item("Add-on Test Spare Fuse", self.sub)
		self.pkg.set("optional_add_ons", [
			{"add_on_type": "Other", "item_code": fuse, "item": "Two spare fuses", "rate": 450, "qty": 2},
			# A row from before Rate and Quantity keeps its Amount.
			{"add_on_type": "Other", "item": "Monitoring", "amount": 500},
		])
		self.pkg.save()
		self.assertEqual([flt(r.amount) for r in self.mine()], [900, 500])
		self.assertEqual(self.mine()[0].item_group, self.sub)

	def test_an_item_of_a_top_level_group_is_refused(self):
		box = add_on_item("Add-on Test Loose Box", self.loose)
		self.pkg.set("optional_add_ons", [{"add_on_type": "Other", "item_code": box, "item": "A box", "rate": 100, "qty": 1}])
		self.assertRaises(frappe.ValidationError, self.pkg.save)

	def test_the_page_offers_the_groups_and_each_groups_items(self):
		fuse = add_on_item("Add-on Test Spare Fuse", self.sub)
		choices = portal_packages._choices()
		self.assertEqual([g["value"] for g in choices["item_groups"]["Optional Add-ons"]], package_items.add_on_groups())
		offered = {o["value"]: o["group"] for o in choices["items"]["Optional Add-ons"]}
		self.assertEqual(offered.get(fuse), self.sub)
		self.assertTrue(set(offered.values()) <= set(package_items.add_on_groups()))


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

	def test_an_extra_panel_takes_its_quantity_at_the_same_amount(self):
		frappe.get_doc({"doctype": "Solar Package Add-on", "parent": self.pkg, "parenttype": "Solar Package",
			"parentfield": "optional_add_ons", "idx": 2, "add_on_type": "Extra Panel", "item": "Two more panels",
			"rate": 17500, "qty": 2, "amount": 35000}).db_insert()
		frappe.clear_document_cache("Solar Package", self.pkg)
		est = make_estimate(self.consumer, solar_package=self.pkg)
		row = next(r for r in est.optional_add_ons if r.add_on_type == "Extra Panel")
		self.assertEqual((row.panel_count, flt(row.rate), flt(row.amount)), (2, 17500, 35000))

	def test_the_proposal_prints_the_estimates_own(self):
		est = make_estimate(self.consumer, solar_package=self.pkg)
		est.optional_add_ons[0].item = "Monitoring for 5 years"
		est.save()
		self.assertEqual([r["item_html"] for r in print_cover.add_on_rows([est])], ["Monitoring for 5 years"])

	def test_the_builder_shows_them_after_the_charges_as_the_package_asks_them(self):
		from a3_sola.api import portal_estimate

		est = make_estimate(self.consumer, solar_package=self.pkg)
		# After the charges, and before the BOM tabs that close the list (test_estimate_boms).
		section = portal_estimate._sections(est)[-4]
		self.assertEqual(section["key"], "optional_add_ons")
		# As the package's add-on row: the group first, then an Item of it, the description it
		# fills, the rate and the quantity; no type asked, no panel fields.
		self.assertEqual([f["fieldname"] for f in section["fields"]], ["item_group", "item_code", "item", "rate", "panel_count", "is_option"])
		item = next(f for f in section["fields"] if f["fieldname"] == "item_code")
		self.assertEqual((item["filter_by"], item["fills"]), ("item_group", {"item": "text"}))

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


class TestAdminOnlyTabs(FrappeTestCase):
	"""Special Discount and Optional Add-ons are an admin's: hidden from anyone else, and
	refused on the server even when asked for directly."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		self.est = make_estimate(self.consumer, solar_package=package("3Kw 1PH", self.consumer.company))
		email = "estimate.designer@a3sola.test"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Designer", "send_welcome_email": 0,
				"user_type": "System User", "roles": [{"role": "Solar Design Engineer"}]}).insert(ignore_permissions=True)
		self.designer = email

	def tearDown(self):
		frappe.set_user("Administrator")

	def keys(self):
		from a3_sola.api import portal_estimate

		return [s["key"] for s in portal_estimate._sections(self.est)]

	def test_an_admin_sees_both(self):
		self.assertIn("special_discount", self.keys())
		self.assertEqual(self.keys()[-4:], ["optional_add_ons", "material_bom", "structure_bom", "bom_expenses"])

	def test_anyone_else_sees_neither_and_cannot_change_them(self):
		from a3_sola.api import portal_estimate

		frappe.set_user(self.designer)
		self.assertFalse({"special_discount", "optional_add_ons"} & set(self.keys()))
		with self.assertRaises(frappe.PermissionError):
			portal_estimate._apply_change(self.est, {"section": "optional_add_ons", "values": {"add_on_type": "Other"}})
		with self.assertRaises(frappe.PermissionError):
			portal_estimate.save_linked_row(self.est.name, "special_discount", "{}")
