# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Solar Consumer, Site Survey and Solar Design Estimate."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.tests.fixtures import make_consumer, make_estimate, make_survey, package


class TestSolarConsumer(FrappeTestCase):
	def test_consumer_number_unique_per_discom(self):
		first = make_consumer(consumer_number="1156540029528")
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_consumer(consumer_number="1156540029528")
		self.assertIn(first.name, str(ctx.exception))

	def test_annual_consumption_derived_from_billing_frequency(self):
		bimonthly = make_consumer(avg_consumption_units=500, billing_frequency="Bimonthly")
		monthly = make_consumer(avg_consumption_units=500, billing_frequency="Monthly")
		self.assertEqual(bimonthly.annual_consumption_units, 3000)
		self.assertEqual(monthly.annual_consumption_units, 6000)

	def test_invalid_ifsc_is_rejected(self):
		"""A wrong IFSC is a failed Direct Benefit Transfer discovered weeks later."""
		with self.assertRaises(frappe.ValidationError):
			make_consumer(bank_ifsc_code="ICICI000289")

	def test_gps_composed_from_coordinates(self):
		consumer = make_consumer(latitude=10.1632, longitude=76.3922)
		self.assertEqual(consumer.gps_coordinates, "10.1632, 76.3922")


class TestSiteSurvey(FrappeTestCase):
	def test_usable_capacity_from_roof_type_area(self):
		"""RCC Flat is seeded at 80 sq ft/kW, so 400 usable sq ft is 5 kW."""
		consumer = make_consumer()
		survey = make_survey(consumer, segments=((400, True), (160, False)))
		self.assertEqual(survey.total_usable_area_sqft, 400)
		self.assertEqual(survey.total_usable_kw, 5.0)

	def test_shading_averaged(self):
		consumer = make_consumer()
		survey = make_survey(consumer, shading=20)
		self.assertEqual(survey.average_shading_percent, 20)

	def test_ehs_checklist_seeded_from_the_lender_form(self):
		consumer = make_consumer()
		survey = make_survey(consumer, submit=False)
		codes = {row.question_code for row in survey.ehs_checklist}
		self.assertIn("EHS-GNG-01", codes)
		self.assertGreaterEqual(len(survey.ehs_checklist), 14)
		blocking = [r for r in survey.ehs_checklist if r.is_blocking]
		self.assertEqual([r.question_code for r in blocking], ["EHS-GNG-01"])

	def test_asbestos_blocks_submission(self):
		"""Broken or dilapidated asbestos roofing is a lender go/no-go."""
		consumer = make_consumer()
		survey = make_survey(consumer, submit=False, asbestos_present=1)
		self.assertEqual(survey.ehs_overall_status, "Blocked")
		with self.assertRaises(frappe.ValidationError) as ctx:
			survey.submit()
		self.assertIn("go/no-go", str(ctx.exception).lower())

	def test_submit_advances_consumer_status(self):
		consumer = make_consumer()
		make_survey(consumer)
		self.assertEqual(frappe.db.get_value("Solar Consumer", consumer.name, "status"), "Surveyed")


class TestDesignEstimate(FrappeTestCase):
	def test_sizing_bound_by_roof(self):
		consumer = make_consumer(avg_consumption_units=3000, sanctioned_load_kw=20)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey)
		self.assertEqual(estimate.binding_constraint, "Usable Roof Area")
		self.assertEqual(estimate.final_capacity_kw, 3.0)

	def test_sizing_bound_by_sanctioned_load(self):
		consumer = make_consumer(avg_consumption_units=3000, sanctioned_load_kw=2)
		survey = make_survey(consumer, segments=((800, True),))
		estimate = make_estimate(consumer, survey)
		self.assertEqual(estimate.binding_constraint, "Sanctioned Load")
		self.assertEqual(estimate.final_capacity_kw, 2.0)

	def test_sizing_bound_by_consumption(self):
		consumer = make_consumer(avg_consumption_units=500, sanctioned_load_kw=20)
		survey = make_survey(consumer, segments=((1600, True),))
		estimate = make_estimate(consumer, survey)
		self.assertEqual(estimate.binding_constraint, "Annual Consumption")
		self.assertEqual(estimate.final_capacity_kw, 2.0)

	def test_override_above_roof_limit_is_rejected(self):
		consumer = make_consumer()
		survey = make_survey(consumer, segments=((240, True),))
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_estimate(consumer, survey, override_capacity_kw=10)
		self.assertIn("roof", str(ctx.exception).lower())

	def test_statutory_fees_resolved_never_typed(self):
		consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey, kseb_registration_fee=999999)
		self.assertEqual(estimate.final_capacity_kw, 3.0)
		self.assertEqual(estimate.kseb_registration_fee, 3540)
		self.assertEqual(estimate.kseb_registration_refundable, 2400)
		self.assertEqual(estimate.kseb_application_fee, 1180)

	def test_net_meter_mode_changes_the_statutory_block(self):
		consumer = make_consumer()
		survey = make_survey(consumer, segments=((240, True),))
		purchased = make_estimate(consumer, survey)
		rental = make_estimate(consumer, survey, net_meter_mode="Availed from DISCOM on Rental")
		self.assertEqual(purchased.net_meter_charge, 5000)
		self.assertEqual(rental.net_meter_charge, 0)
		self.assertEqual(rental.net_meter_allocation_lead_days, 21)

	def test_cashflow_and_payback_populated(self):
		consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey)
		self.assertEqual(len(estimate.cashflow), 25)
		self.assertGreater(estimate.simple_payback_years, 0)
		self.assertGreater(estimate.estimated_annual_savings, 0)
		self.assertEqual(estimate.applicable_subsidy_amount, 78000)

	def test_daily_band_printed_not_a_single_figure(self):
		consumer = make_consumer(avg_consumption_units=750, sanctioned_load_kw=5)
		survey = make_survey(consumer, segments=((240, True),))
		estimate = make_estimate(consumer, survey)
		self.assertEqual(estimate.expected_daily_units_low, 12.0)
		self.assertEqual(estimate.expected_daily_units_high, 15.0)

	def test_multiple_recommended_options_rejected(self):
		consumer = make_consumer()
		survey = make_survey(consumer, segments=((240, True),))
		options = [
			{"option_name": "A", "inverter_topology": "String", "system_cost": 1, "is_recommended": 1},
			{"option_name": "B", "inverter_topology": "Microinverter", "system_cost": 2, "is_recommended": 1},
		]
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_estimate(consumer, survey, options=options)
		self.assertIn("recommended", str(ctx.exception).lower())

	def test_dcr_mismatch_blocked_only_when_the_scheme_requires_it(self):
		"""A non-DCR package is legitimate for an unsubsidised job."""
		consumer = make_consumer()
		survey = make_survey(consumer, segments=((800, True),))
		non_dcr = package("10KW 3PH Non-DCR")
		options = [
			{
				"option_name": "Option 1",
				"inverter_topology": "String",
				"solar_package": non_dcr,
				"system_cost": 480000,
				"is_recommended": 1,
			}
		]
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_estimate(consumer, survey, options=options)
		self.assertIn("DCR", str(ctx.exception))

		# Same package, no subsidy scheme attached - allowed.
		estimate = make_estimate(consumer, survey, subsidy_scheme=None, options=options)
		self.assertTrue(estimate.name)

	def test_option_warranty_fetched_from_the_make(self):
		"""Rayzon is 15 years and SolarEdge 8 - both read from Component Make, never typed."""
		consumer = make_consumer()
		survey = make_survey(consumer, segments=((240, True),))
		solaredge = frappe.db.get_value("Component Make", {"make_name": "SolarEdge", "component_type": "Inverter"}, "name")
		options = [
			{
				"option_name": "Option 2 - Optimiser",
				"inverter_topology": "String with Optimiser",
				"solar_package": package("3Kw 1PH"),
				"inverter_make": solaredge,
				"system_cost": 225000,
				"is_recommended": 1,
			}
		]
		estimate = make_estimate(consumer, survey, options=options)
		self.assertEqual(estimate.options[0].inverter_warranty_years, 8)
