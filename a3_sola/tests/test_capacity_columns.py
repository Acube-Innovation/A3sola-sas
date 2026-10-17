# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A panel's, inverter's and battery's size has its own Capacity column - on the proposal's
Design Comparison and the quotation's BOM tab - and is no longer repeated in its description.
The quotation's PDF and option preview keep the specification as it was."""

import re

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import print_cover, proposal_comparison
from a3_sola.tests.fixtures import make_consumer, make_estimate, package


class TestCapacityColumns(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_each_units_size(self):
		cap = proposal_comparison.unit_capacity
		self.assertEqual(cap("panels", frappe._dict(panel_capacity_wp=550)), "550 Wp")
		self.assertEqual(cap("inverters", frappe._dict(inverter_capacity_kw=3)), "3 kW")
		self.assertEqual(cap("batteries", frappe._dict(battery_voltage=48, battery_capacity_ah=100)), "4.8 kWh")
		self.assertEqual(cap("inverters", frappe._dict(inverter_capacity_kw=0)), "")

	def test_the_description_leaves_the_size_to_its_column(self):
		panel = frappe._dict(panel_capacity_wp=550, panel_type="DCR")
		inverter = frappe._dict(inverter_capacity_kw=3, inverter_phase="Single Phase")
		self.assertEqual(proposal_comparison._describe("panels", panel), "DCR")
		self.assertEqual(proposal_comparison._describe("inverters", inverter), "Single Phase")

	def options(self, count):
		consumer = make_consumer()
		estimates = [make_estimate(consumer, solar_package=package("3Kw 1PH", consumer.company)) for _ in range(count)]
		if not all(any(not r.is_option for r in e.panels) and any(not r.is_option for r in e.inverters) for e in estimates):
			self.skipTest("the package fills no panel or inverter on this site")
		return consumer, estimates

	def test_the_comparison_has_a_capacity_column(self):
		_consumer, estimates = self.options(1)
		summary = proposal_comparison.estimate_summary(estimates[0].name)
		panel = summary["main"]["panels"][0]
		row = next(r for r in estimates[0].panels if not r.is_option)
		self.assertEqual(panel["capacity"], "{0:g} Wp".format(row.panel_capacity_wp))
		self.assertNotIn("Wp", panel["description"])
		html = proposal_comparison.render([e.name for e in estimates])
		self.assertIn(">Capacity<", html)
		self.assertIn(">{0}<".format(panel["capacity"]), html)
		# Every row fills the six columns: a cell is 1 wide unless it spans more.
		for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
			cells = re.findall(r"<t[dh](?:\s+[^>]*)?>", tr)
			width = sum(int((re.search(r'colspan="(\d+)"', c) or [None, 1])[1]) for c in cells)
			self.assertEqual(width, 6, tr)

	def test_an_option_differing_only_in_inverter_size_is_a_change(self):
		_consumer, estimates = self.options(2)
		row = next(r for r in estimates[1].inverters if not r.is_option)
		frappe.db.set_value("Design Estimate Inverter", row.name, "inverter_capacity_kw", (row.inverter_capacity_kw or 1) + 2)
		data = proposal_comparison.comparison([e.name for e in estimates])
		self.assertIn("Inverter", [c["component"] for c in data["variants"][0]["changes"]])

	def test_the_bom_rows_carry_the_size_and_the_pdf_spec_is_as_before(self):
		consumer, estimates = self.options(1)
		doc = frappe._dict(company=consumer.company, solar_design_estimate=estimates[0].name, design_estimates=[])
		rows = print_cover.print_components(doc)["rows"]
		panel = next(r for r in rows if r["item"] == "Solar Panels")
		inverter = next(r for r in rows if r["item"] in ("Solar PV Inverter", "Solar PV Hybrid Inverter"))
		self.assertTrue(panel["capacity"].endswith(" Wp") and inverter["capacity"].endswith(" kW"))
		self.assertTrue(panel["spec"].startswith(panel["capacity"].replace(" ", "")))
		self.assertNotIn("Wp", panel["spec_detail"])
		self.assertTrue(inverter["spec"].startswith(inverter["capacity"]))
		self.assertNotIn(inverter["capacity"], inverter["spec_detail"])
		self.assertNotIn("capacity", next(r for r in rows if r["item"] == "DCDB"))

	def test_a_battery_without_a_rating_is_not_zero_volts(self):
		consumer, estimates = self.options(1)
		est = estimates[0]
		est.append("batteries", {"nos": 1})
		est.batteries[-1].db_insert()
		doc = frappe._dict(company=consumer.company, solar_design_estimate=est.name, design_estimates=[])
		battery = next(r for r in print_cover.print_components(doc)["rows"] if r["item"] == "Battery")
		self.assertNotIn("0V", battery["spec"])
		self.assertEqual(battery["capacity"], "")
