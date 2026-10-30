# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A panel is sold at its Wp times its rate per watt: the module Item of its make, Wp and
technology carries that price, and a design estimate's panel row no package covers takes it."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import structure_bom


class TestPanelPrice(FrappeTestCase):
	def test_a_makes_brand_drops_its_dcr_and_technology_words(self):
		self.assertEqual(structure_bom.make_brand("Vikram TOPCon"), "Vikram")
		self.assertEqual(structure_bom.make_brand("Rayzon Non-DCR Mono PERC"), "Rayzon")
		self.assertEqual(structure_bom.make_brand("Renewsys"), "Renewsys")

	def test_the_item_of_the_panels_technology_is_preferred(self):
		found = [frappe._dict(name="MOD-GG", item_name="Testpanel 615 Wp DCR Glass-Glass Module", is_dcr=1),
			frappe._dict(name="MOD-TC", item_name="Testpanel 615 Wp DCR TOPCon Module", is_dcr=1),
			frappe._dict(name="MOD-ND", item_name="Testpanel 615 Wp Non-DCR TOPCon Module", is_dcr=0)]
		with patch.object(frappe, "get_all", return_value=found):
			self.assertEqual(structure_bom.panel_item("Testpanel", 615, True, "TOPCon Bifacial"), "MOD-TC")
			self.assertEqual(structure_bom.panel_item("Testpanel Non-DCR", 615, False, "TOPCon Bifacial"), "MOD-ND")

	def test_the_rate_is_the_selling_price(self):
		with patch.object(structure_bom, "panel_item", return_value="MOD-TC"), \
				patch.object(frappe.db, "get_value", return_value=15313.5):
			self.assertEqual(structure_bom.panel_rate("Renewsys", 615, True), 15313.5)

	def test_an_estimate_panel_without_a_rate_takes_it(self):
		est = frappe.new_doc("Solar Design Estimate")
		est.append("panels", {"panel_make": "MAKE", "panel_capacity_wp": 615, "panel_type": "DCR"})
		est.append("panels", {"panel_make": "MAKE", "panel_capacity_wp": 615, "panel_type": "DCR", "rate": 9999})
		with patch("a3_sola.api.structure_bom.panel_rate", return_value=15313.5):
			est.price_panels_from_list()
		self.assertEqual([r.rate for r in est.panels], [15313.5, 9999])
