# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Inverters come from the master price list: each model's price, warranty and its
extension, the SolarEdge optimizer and the Hoymiles kit. A package is priced on its model;
an estimate on another model is priced by the difference."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.setup.inverter_models import INVERTER_MODELS, extension_years
from a3_sola.solar_crm.doctype.inverter_model import inverter_model
from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import model_difference


def model(name):
	if not frappe.db.exists("Inverter Model", name):
		raise AssertionError(f"{name} is not seeded")
	return name


class TestInverterModels(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_the_sheet_is_seeded_as_given(self):
		self.assertEqual(len(INVERTER_MODELS), 41)
		for row in INVERTER_MODELS:
			self.assertTrue(frappe.db.exists("Inverter Model", {"model_name": row[1], "capacity_kw": row[4]}), row[1])
		se = frappe.get_doc("Inverter Model", model("SE3000H-1PH-3kW"))
		self.assertEqual((se.rate, se.optimizer_model, se.optimizer_price, se.optimizer_qty, se.optimizer_total),
			(7908, "S1000", 1932, 6, 11592))
		self.assertEqual(inverter_model.price(se.name, True), 19500)  # the sheet's Total Price
		self.assertEqual(inverter_model.price(se.name, False), 7908)

	def test_the_extension_is_the_years_added_or_up_to_the_year_given(self):
		self.assertEqual(extension_years(12, 25), 13)  # a micro kit: 13th to 25th year
		self.assertEqual(extension_years(5, 5), 5)  # a hybrid: 5 more years
		self.assertEqual(inverter_model.extension(model("MHS-8K-30-1PH-8kW")),
			("Warranty Extension for Inverter – 6th Year to 10th year", 14046.5))
		self.assertEqual(inverter_model.extension(model("HM-1000-1PH-3kW"))[0],
			"Warranty Extension for Inverter – 13th Year to 25th year")
		self.assertIsNone(inverter_model.extension(model("OGS-5K-1PH-5kW")))

	def test_a_micro_kit_fills_its_row_and_prints_its_contents(self):
		row = frappe._dict(with_optimizer=0)
		row.set = row.__setitem__
		self.assertTrue(inverter_model.fill_row(row, model("HM-1000-3PH-4kW"), "unit_rate"))
		self.assertEqual((row.inverter_capacity_kw, row.inverter_count, row.inverter_phase, row.unit_rate),
			(1, 4, "Three Phase", 8500))
		self.assertTrue(inverter_model.specification("HM-1000-3PH-4kW").startswith("HM-1000 microinverter × 4 units"))

	def test_another_model_is_priced_by_the_difference(self):
		row = frappe._dict(inverter_model=model("SE5000H-1PH-5kW"), with_optimizer=1,
			package_model=model("SE3000H-1PH-3kW"), package_with_optimizer=1)
		self.assertEqual(model_difference(row), 32500 - 19500)
		row.with_optimizer = 0  # the optimizer taken off
		self.assertEqual(model_difference(row), 15112 - 19500)
		self.assertEqual(model_difference(frappe._dict(inverter_model=row.inverter_model)), 0)

	def test_the_estimate_prices_and_warrants_its_model(self):
		from a3_sola.tests.fixtures import make_consumer, make_estimate

		pkg = frappe.db.get_value("Solar Package Inverter", {"inverter_model": "OGS-3.3K 02GS-1PH-3.3kW", "is_default": 1}, "parent")
		if not pkg:
			self.skipTest("no package on the OGS-3.3K")
		consumer = make_consumer()
		frappe.db.set_value("Solar Consumer", consumer.name, "connection_type", "Single Phase")
		est = make_estimate(consumer, with_default_options=False, solar_package=pkg, connection_type="Single Phase")
		priced = next(r for r in est.inverters if not r.is_option)
		if priced.inverter_model != "OGS-3.3K 02GS-1PH-3.3kW":
			self.skipTest("the estimate is not priced on the OGS-3.3K")
		base = est.package_price()
		# Neither has an extension: none is offered.
		self.assertNotIn("Warranty Extension", [r.add_on_type for r in est.optional_add_ons])
		priced.inverter_model = model("OGS-5K-1PH-5kW")
		est.flags.ignore_links = True
		est.save(ignore_permissions=True)
		priced = next(r for r in est.inverters if not r.is_option)
		self.assertEqual((priced.inverter_capacity_kw, priced.package_model), (5, "OGS-3.3K 02GS-1PH-3.3kW"))
		self.assertEqual(est.package_price(), base + 30500 - 16800)
		self.assertEqual(est.inverter_warranty_years(priced.inverter_make), 10)
