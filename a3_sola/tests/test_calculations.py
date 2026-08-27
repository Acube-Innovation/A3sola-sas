# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Subsidy, telescopic billing, generation and cashflow."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import calculations
from a3_sola.tests.fixtures import scheme, tariff


class TestSubsidy(FrappeTestCase):
	def test_slab_boundary_exactly_on_threshold(self):
		"""3.0 kW sits exactly on the boundary of the top slab and must take it."""
		self.assertEqual(calculations.get_subsidy_amount(scheme(), 3.0, "Residential")["subsidy_amount"], 78000)
		self.assertEqual(calculations.get_subsidy_amount(scheme(), 2.99, "Residential")["subsidy_amount"], 60000)
		self.assertEqual(calculations.get_subsidy_amount(scheme(), 1.0, "Residential")["subsidy_amount"], 30000)

	def test_capacity_above_top_slab_caps(self):
		result = calculations.get_subsidy_amount(scheme(), 25, "Residential")
		self.assertEqual(result["subsidy_amount"], 78000)
		self.assertTrue(result["capped"])
		self.assertIn("ceiling", result["message"])

	def test_five_kw_residential_is_the_documented_case(self):
		result = calculations.get_subsidy_amount(scheme(), 5, "Residential")
		self.assertEqual(result["subsidy_amount"], 78000)

	def test_non_residential_category_returns_zero_not_an_error(self):
		"""A commercial enquiry against a residential scheme is a sales situation, not a bug."""
		result = calculations.get_subsidy_amount(scheme(), 5, "Commercial")
		self.assertEqual(result["subsidy_amount"], 0)
		self.assertIn("Residential", result["message"])

	def test_missing_scheme_raises(self):
		with self.assertRaises(frappe.ValidationError):
			calculations.get_subsidy_amount("No Such Scheme", 5, "Residential")


class TestTelescopicBilling(FrappeTestCase):
	def test_zero_consumption(self):
		bill = calculations.calculate_bill(tariff(), 0)
		self.assertEqual(bill["energy_charge"], 0)
		self.assertEqual(bill["effective_rate_per_unit"], 0)

	def test_slabs_accumulate_upward(self):
		"""Units in each slab are charged at that slab's rate, not one flat rate."""
		bill = calculations.calculate_bill(tariff(), 250)
		billed = sum(row["units_billed"] for row in bill["slab_breakdown"])
		self.assertEqual(billed, 250)
		rates = [row["rate_per_unit"] for row in bill["slab_breakdown"]]
		self.assertEqual(rates, sorted(rates), "telescopic slabs must ascend")

	def test_saving_per_unit_exceeds_average_rate(self):
		"""The whole point of modelling the tariff telescopically.

		The units a solar system removes are the most expensive ones, so the saving per
		unit is higher than the average rate. A flat-rate model understates the saving and
		undersells the system.
		"""
		bill = calculations.calculate_bill(tariff(), 500)
		savings = calculations.calculate_savings(tariff(), 500, 200)
		self.assertGreater(savings["effective_saving_per_unit"], bill["effective_rate_per_unit"])
		self.assertEqual(savings["units_saved"], 300)

	def test_missing_tariff_raises(self):
		with self.assertRaises(frappe.ValidationError):
			calculations.calculate_bill("No Such Tariff", 100)


class TestGeneration(FrappeTestCase):
	def test_generation_derated_for_shading(self):
		clear = calculations.estimate_generation(5, 1500, 0)
		shaded = calculations.estimate_generation(5, 1500, 20)
		self.assertEqual(clear["annual_generation_kwh"], 7500)
		self.assertEqual(shaded["annual_generation_kwh"], 6000)
		self.assertEqual(shaded["derate_factor"], 0.8)

	def test_daily_band_matches_the_quoted_ranges(self):
		"""The client's proposals quote 12-15 units for 3 kW and 40-50 for 10 kW."""
		three = calculations.estimate_daily_generation_band(3)
		ten = calculations.estimate_daily_generation_band(10)
		self.assertEqual((three["low_units_per_day"], three["high_units_per_day"]), (12.0, 15.0))
		self.assertEqual((ten["low_units_per_day"], ten["high_units_per_day"]), (40.0, 50.0))


class TestSizingAndCashflow(FrappeTestCase):
	def test_binding_constraint_is_named(self):
		by_roof = calculations.recommend_capacity(15000, 3.0, 10.0, 1500)
		self.assertEqual(by_roof["binding_constraint"], "Usable Roof Area")
		self.assertEqual(by_roof["recommended_kw"], 3.0)

		by_load = calculations.recommend_capacity(15000, 20.0, 4.0, 1500)
		self.assertEqual(by_load["binding_constraint"], "Sanctioned Load")

		by_use = calculations.recommend_capacity(3000, 20.0, 20.0, 1500)
		self.assertEqual(by_use["binding_constraint"], "Annual Consumption")
		self.assertEqual(by_use["recommended_kw"], 2.0)

	def test_payback_is_interpolated_not_rounded(self):
		flow = calculations.build_cashflow(200000, 78000, 4500, 30000, years=25)
		self.assertGreater(flow["simple_payback_years"], 0)
		self.assertNotEqual(flow["simple_payback_years"], int(flow["simple_payback_years"]))
		self.assertEqual(len(flow["rows"]), 25)
		self.assertEqual(flow["net_outflow"], 122000)

	def test_generation_degrades_and_savings_escalate(self):
		flow = calculations.build_cashflow(200000, 0, 10000, 50000, years=5)
		rows = flow["rows"]
		self.assertLess(rows[-1]["generation_kwh"], rows[0]["generation_kwh"])
		self.assertGreater(rows[-1]["savings_amount"], rows[0]["savings_amount"])
