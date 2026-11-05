# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Step two's popups ask what the desk rows hold: a panel is added or changed with its Item -
the module bought, as the package's Solar Panel row names it - and a row's mandatory fields
are filled before it is applied. Ticking Option alone is not held up, and a panel the package
fills carries the package's Item."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_estimate
from a3_sola.tests.fixtures import make_consumer, make_estimate, package


def a_module_item():
	return next((c["value"] for c in portal_estimate.panel_item_choices()), None)


class TestEstimatePopupItems(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		consumer = make_consumer()
		pkg = package("3Kw 1PH", consumer.company)
		if not pkg:
			self.skipTest("no 3Kw 1PH package on this site")
		# Built as the portal builds it: one option row on the package, which fills the panels.
		self.estimate = make_estimate(consumer, with_default_options=False, sizing_options=[{"is_recommended": 1,
			"solar_package": pkg, "connection_type": "Single Phase", "system_type": "On-Grid", "subsidy_option": "With Subsidy"}])
		if not self.estimate.panels:
			self.skipTest("the package filled no panel")
		self.panel = {"panel_type": "DCR", "panel_capacity_wp": "550", "panel_variant": self.estimate.panels[0].panel_variant,
			"panel_make": "", "is_option": "1", "rate": ""}

	def tearDown(self):
		frappe.db.rollback()

	def state(self, *changes):
		return portal_estimate.tab_state(self.estimate.name, ops=frappe.as_json(list(changes)))

	def test_a_panel_is_added_with_its_item(self):
		with self.assertRaises(frappe.ValidationError):
			self.state({"section": "panels", "values": {**self.panel, "panel_item": ""}})
		item = a_module_item()
		if not item:
			self.skipTest("no Item in the Modules group on this site")
		state = self.state({"section": "panels", "values": {**self.panel, "panel_item": item}})
		panels = next(s for s in state["state"]["sections"] if s["key"] == "panels")
		self.assertIn(item, [r["values"].get("panel_item") for r in panels["rows"]])

	def test_ticking_option_alone_is_not_held_up(self):
		row = self.estimate.panels[0]
		self.state({"section": "panels", "row": row.name, "values": {"is_option": "0"}})

	def test_a_mandatory_field_is_asked_before_the_row_is_applied(self):
		with self.assertRaises(frappe.ValidationError):
			self.state({"section": "kseb_expenses", "values": {"particulars": "", "amount": "100"}})

	def test_a_package_panel_carries_the_package_item(self):
		module = next((m for m in frappe.get_doc("Solar Package", self.estimate.solar_package).modules if m.module_item), None)
		if not module:
			self.skipTest("the estimate's package names no panel Item")
		self.assertIn(module.module_item, [r.panel_item for r in self.estimate.panels])
