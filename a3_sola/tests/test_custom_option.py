# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A Custom option is not a package: its panel, inverter and battery are chosen from every
make - a DCR panel with subsidy - and the estimate starts from them, the rest of the system
added by hand. Choosing Custom drops the kit a package filled."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_estimate
from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import custom_components
from a3_sola.tests.fixtures import make_consumer, make_estimate, package


def a_make(component_type, company, **filters):
	return frappe.db.get_value("Component Make", {"component_type": component_type, "is_active": 1, "company": company, **filters})


class TestCustomOption(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		company = self.consumer.company
		# A DCR panel make with a Wp to go on (custom_panel_wp), so its row can be seeded.
		used = set(frappe.get_all("Solar Package Module", filters={"parenttype": "Solar Package", "module_wattage": [">", 0]},
			pluck="module_make"))
		self.dcr = a_make("Module", company, is_dcr=1, name=["in", list(used) or [""]])
		self.non_dcr = a_make("Module", company, is_dcr=0)
		# An inverter make with a single phase On-Grid model (custom_inverter_model).
		modelled = set(frappe.get_all("Inverter Model", filters={"is_active": 1, "inverter_phase": "Single Phase",
			"category": "On-Grid"}, pluck="inverter_make"))
		self.inverter = a_make("Inverter", company, name=["in", list(modelled) or [""]])
		if not (self.dcr and self.inverter):
			self.skipTest("no DCR module make or inverter make on this site")

	def tearDown(self):
		frappe.db.rollback()

	def custom_row(self, **values):
		return {"is_recommended": 1, "is_custom": 1, "connection_type": "Single Phase", "system_type": "On-Grid",
			"subsidy_option": "With Subsidy", "panel_make": self.dcr, "inverter_make": self.inverter, **values}

	def test_the_choices_are_every_make_and_say_what_they_suit(self):
		choices = custom_components(self.consumer.company)
		self.assertIn(self.dcr, [p["value"] for p in choices["panels"]])
		self.assertTrue(all("dcr" in p for p in choices["panels"]))
		self.assertIn(self.inverter, [i["value"] for i in choices["inverters"]])

	def test_a_custom_estimate_keeps_its_makes_and_starts_from_them(self):
		doc = make_estimate(self.consumer, with_default_options=False, sizing_options=[self.custom_row()])
		row = doc.sizing_options[0]
		self.assertEqual((row.is_custom, row.solar_package, row.panel_make, row.inverter_make),
			(1, None, self.dcr, self.inverter))
		self.assertFalse(doc.solar_package)
		self.assertEqual([r.panel_make for r in doc.panels], [self.dcr])
		self.assertEqual([r.panel_type for r in doc.panels], ["DCR"])
		self.assertEqual([r.inverter_make for r in doc.inverters], [self.inverter])
		self.assertTrue(portal_estimate.is_custom(doc))

	def test_with_subsidy_a_custom_panel_must_be_dcr(self):
		if not self.non_dcr:
			self.non_dcr = frappe.get_doc({"doctype": "Component Make", "make_name": "Test Non-DCR Panel", "component_type": "Module",
				"is_dcr": 0, "is_active": 1, "company": self.consumer.company}).insert(ignore_permissions=True).name
		with self.assertRaises(frappe.ValidationError):
			make_estimate(self.consumer, with_default_options=False, sizing_options=[self.custom_row(panel_make=self.non_dcr)])
		doc = make_estimate(self.consumer, with_default_options=False,
			sizing_options=[self.custom_row(panel_make=self.non_dcr, subsidy_option="Without Subsidy")])
		self.assertEqual(doc.sizing_options[0].panel_make, self.non_dcr)

	def test_turning_custom_drops_the_package_kit(self):
		pkg = package("3Kw 1PH", self.consumer.company)
		if not pkg:
			self.skipTest("no 3Kw 1PH package on this site")
		doc = make_estimate(self.consumer, with_default_options=False, sizing_options=[{"is_recommended": 1,
			"solar_package": pkg, "connection_type": "Single Phase", "system_type": "On-Grid", "subsidy_option": "With Subsidy"}])
		self.assertTrue(doc.equipment_package)
		doc.sizing_options[0].update({"solar_package": None, "is_custom": 1, "panel_make": self.dcr, "inverter_make": self.inverter})
		doc.solar_package = None
		doc.save(ignore_permissions=True)
		self.assertFalse(doc.equipment_package)
		self.assertEqual([r.panel_make for r in doc.panels], [self.dcr])
		self.assertEqual([r.inverter_make for r in doc.inverters], [self.inverter])

	def test_the_portal_posts_custom_as_no_package(self):
		doc = make_estimate(self.consumer, with_default_options=False, sizing_options=[self.custom_row()])
		row = {**self.custom_row(), "solar_package": portal_estimate.CUSTOM, "name": doc.sizing_options[0].name}
		portal_estimate.save_details(frappe.as_json({}), name=doc.name, sizing_options=frappe.as_json([row]))
		doc.reload()
		self.assertEqual((doc.sizing_options[0].is_custom, doc.sizing_options[0].solar_package), (1, None))
		# Shown back on step one as Custom.
		shown = portal_estimate.option_rows(doc, [{"fieldname": "solar_package"}])
		self.assertEqual(shown[0]["values"]["solar_package"], portal_estimate.CUSTOM)
