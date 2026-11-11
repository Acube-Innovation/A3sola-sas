# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Solar Design Proposal: one page for the design and the offer. Its list is the proposals,
with the design estimates not yet made into one beside them; a proposal is made on the
estimate's builder, from its saved options (api/portal_proposal), and edited there; an
estimate's commercials are the package's price, the KSEB fees and GST; its add-ons and BOM
tabs take rows as the package's do (api/portal_estimate, package_kits)."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import portal_estimate, portal_proposal
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey, package
from a3_sola.tests.test_package_kits import bundle, part, selling_price
from a3_sola.www.a3solaportal import NAV_GROUPS
from a3_sola.www.a3solaportal.collections import edit_route


class TestDesignProposal(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		self.pkg = package("3Kw 1PH", self.consumer.company)
		if not self.pkg:
			self.skipTest("no 3Kw 1PH package on this site")
		self.survey = make_survey(self.consumer)
		# Built as the portal builds it: one option row on the package, the estimate itself.
		self.root = make_estimate(self.consumer, self.survey, with_default_options=False, sizing_options=[{"is_recommended": 1,
			"solar_package": self.pkg, "connection_type": "Single Phase", "system_type": "On-Grid", "subsidy_option": "With Subsidy"}])

	def tearDown(self):
		frappe.db.rollback()

	def make(self, **values):
		return portal_proposal.save_from_estimate(self.root.name, frappe.as_json({"customer_name": "Shiju", "location": "Chalakudy", **values}))

	# ------------------------------------------------------------ the list
	def test_the_menu_has_one_page_for_the_design_and_the_offer(self):
		items = {i["route"]: i["title"] for g in NAV_GROUPS for i in g["items"]}
		self.assertEqual(items["/a3solaportal/proposals"], "Solar Design Proposal")
		self.assertNotIn("/a3solaportal/design-estimates", items)

	def test_an_estimate_without_a_proposal_is_listed_until_one_is_made(self):
		names = [e["name"] for e in portal_proposal.unproposed_estimates(limit=500)]
		self.assertIn(self.root.name, names)
		self.assertEqual(next(e for e in portal_proposal.unproposed_estimates(limit=500) if e["name"] == self.root.name)["route"],
			portal_estimate.design_route(self.root.name))
		self.make()
		self.assertNotIn(self.root.name, [e["name"] for e in portal_proposal.unproposed_estimates(limit=500)])

	# ------------------------------------------------------------ the Proposal tab
	def test_the_proposal_tab_shows_who_it_is_for_from_the_estimate(self):
		state = portal_proposal.proposal_state(self.root)
		self.assertIsNone(state["existing"])
		self.assertTrue(state["can_write"])
		fields = {f["fieldname"]: f for s in state["sections"] for f in s["fields"]}
		self.assertTrue(fields["lead"]["locked"])
		self.assertEqual(fields["lead"]["value"], self.consumer.lead)
		self.assertEqual(fields["solar_consumer"]["value"], self.consumer.name)
		self.assertEqual(fields["customer_name"]["value"], self.consumer.consumer_name)
		self.assertFalse(fields["customer_name"].get("locked"))
		self.assertEqual([o["estimate"] for o in state["options"]], [self.root.name])
		self.assertEqual(state["unsaved"], [])
		# The builder sends the tab's state with every payload, so it follows each save.
		payload = frappe.parse_json(portal_estimate.page_json(self.root))
		self.assertEqual(payload["proposal"]["options"][0]["estimate"], self.root.name)
		self.assertNotIn("proposal_action", payload["state"])
		self.assertTrue(payload["state"]["pdf_view_route"].startswith("/api/method/a3_sola.api.portal_estimate.download_pdf?view=1"))

	def test_the_proposal_is_made_of_the_saved_options_and_opens(self):
		result = self.make(remarks="Two points\nto make")
		doc = frappe.get_doc("Solar Proposal", result["name"])
		self.assertEqual(result["route"], "/a3solaportal/proposals/" + frappe.utils.quote(doc.name))
		self.assertEqual(doc.lead, self.consumer.lead)
		self.assertEqual(doc.solar_consumer, self.consumer.name)
		self.assertEqual([r.solar_design_estimate for r in doc.design_estimates], [self.root.name])
		self.assertEqual((doc.solar_design_estimate, doc.customer_name, doc.location, doc.remarks),
			(self.root.name, "Shiju", "Chalakudy", "Two points\nto make"))
		# From then on the tab shows it, and it is edited in the estimate's builder.
		state = portal_proposal.proposal_state(frappe.get_doc("Solar Design Estimate", self.root.name))
		self.assertEqual(state["existing"]["name"], doc.name)
		self.assertEqual(portal_proposal.design_route_of(doc.name), portal_estimate.design_route(self.root.name))
		self.assertEqual(edit_route("proposals", doc.name), portal_estimate.design_route(self.root.name))

	def test_saving_again_keeps_the_one_proposal(self):
		first = self.make()["name"]
		second = self.make(customer_name="Shiju Thomas")["name"]
		self.assertEqual(first, second)
		doc = frappe.get_doc("Solar Proposal", first)
		self.assertEqual(doc.customer_name, "Shiju Thomas")
		self.assertEqual(len(doc.design_estimates), 1)

	def test_an_option_not_saved_holds_the_proposal(self):
		other = next((r.inverter_make for r in frappe.get_doc("Solar Package", self.pkg).inverters if not r.is_default), None)
		if not other:
			self.skipTest("the package offers one inverter only")
		root = frappe.get_doc("Solar Design Estimate", self.root.name)
		root.append("sizing_options", {"solar_package": self.pkg, "connection_type": "Single Phase", "system_type": "On-Grid",
			"subsidy_option": "With Subsidy", "inverter_make": other})
		root.save()
		state = portal_proposal.proposal_state(root)
		self.assertEqual(state["unsaved"], [2])
		self.assertEqual([o["recommended"] for o in state["options"]], [True, False])
		with self.assertRaises(frappe.ValidationError):
			self.make()

	# ------------------------------------------------------------ the commercials
	def test_the_commercials_are_the_package_the_kseb_fees_and_gst(self):
		commercials = frappe.get_doc("Solar Design Estimate", self.root.name).commercials()
		keys = [line["key"] for line in commercials["lines"]]
		self.assertEqual(keys[:2], ["package", "kseb_expenses"])
		for covered in ("panels", "inverters", "bos_items", "mounting_expenses", "installation_expenses"):
			self.assertNotIn(covered, keys)
		kseb = next(line["amount"] for line in commercials["lines"] if line["key"] == "kseb_expenses")
		self.assertEqual(commercials["taxable"], flt(commercials["subtotal"] - kseb, 2))

	# ------------------------------------------------------------ rows as the package's
	def test_an_add_on_is_chosen_by_group_then_item(self):
		item = part("DP Test Add-on", group="Optional Add-ons" if frappe.db.exists("Item Group", "Optional Add-ons") else "Kit Test Parts")
		state = portal_estimate.tab_state(self.root.name, ops=frappe.as_json([{"section": "optional_add_ons", "values": {
			"item_group": frappe.db.get_value("Item", item, "item_group"), "item_code": item, "item": "", "rate": "500", "panel_count": "2", "is_option": "0"}}]))
		section = next(s for s in state["state"]["sections"] if s["key"] == "optional_add_ons")
		self.assertEqual([f["fieldname"] for f in section["fields"]], ["item_group", "item_code", "item", "rate", "panel_count", "is_option"])
		row = next(r for r in section["rows"] if r["values"].get("item_code") == item)
		self.assertEqual((row["values"]["item"], row["values"]["nos"], flt(row["values"]["amount"])), ("DP Test Add-on as described", 2, 1000))
		self.assertEqual(next(l["amount"] for l in state["state"]["commercials"]["lines"] if l["key"] == "optional_add_ons"), 1000)

	def test_a_bundle_on_the_materials_tab_opens_into_its_items(self):
		cable, lug = part("DP Test Cable"), part("DP Test Lug")
		selling_price(cable, 40)
		kit = bundle("DP Test Cable Set", [(cable, 30), (lug, 2)])
		state = portal_estimate.tab_state(self.root.name, ops=frappe.as_json([{"section": "material_bom", "values": {
			"category": "", "item": kit, "description": "", "uom": "", "qty": "2", "rate": ""}}]))
		section = next(s for s in state["state"]["sections"] if s["key"] == "material_bom")
		self.assertEqual(section["label"], "Materials")
		self.assertEqual([f["fieldname"] for f in section["fields"]], ["category", "item", "description", "uom", "qty", "rate"])
		rows = {r["values"]["item"]: r["values"] for r in section["rows"]}
		self.assertNotIn(kit, rows)
		self.assertEqual((flt(rows[cable]["qty"]), flt(rows[cable]["rate"]), rows[cable]["description"]), (60, 40, "DP Test Cable as described"))
		self.assertEqual(flt(rows[lug]["qty"]), 4)
