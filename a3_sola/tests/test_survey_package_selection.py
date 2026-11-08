# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The site survey answers what a design estimate's package is chosen by - the system, the
phase found on site, the subsidy and the size - and a new estimate starts from them."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.solar_crm.doctype.site_survey.site_survey import estimate_answers
from a3_sola.tests.fixtures import make_consumer, make_survey


class TestSurveyAnswers(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		frappe.db.set_value("Solar Consumer", self.consumer.name, "connection_type", "Single Phase")

	def test_the_answers_an_estimate_starts_from(self):
		survey = make_survey(self.consumer, system_type="On-Grid", connection_type="Three Phase",
			subsidy_option="Without Subsidy", recommended_capacity_kw=5, capacity_applied_kw=3)
		self.assertEqual(estimate_answers(survey.name), {"system_type": "On-Grid", "connection_type": "Three Phase",
			"subsidy_option": "Without Subsidy", "override_capacity_kw": 5})

	def test_batteries_make_it_hybrid_and_the_applied_size_stands_in(self):
		survey = make_survey(self.consumer, batteries_in_scope=1, capacity_applied_kw=4)
		answers = estimate_answers(survey.name)
		self.assertEqual((answers["system_type"], answers["override_capacity_kw"]), ("Hybrid", 4))
		# Not answered, not said: the estimate keeps its own subsidy.
		self.assertNotIn("subsidy_option", answers)

	def test_the_phase_starts_as_the_customers_and_the_surveyors_is_kept(self):
		self.assertEqual(make_survey(self.consumer).connection_type, "Single Phase")
		survey = make_survey(self.consumer, connection_type="Three Phase", submit=False)
		survey.save()
		self.assertEqual(survey.connection_type, "Three Phase")

	def test_a_new_estimate_takes_the_surveys_answers(self):
		from a3_sola.api.portal_estimate import estimate_prefill

		survey = make_survey(self.consumer, system_type="Hybrid", connection_type="Three Phase",
			subsidy_option="With Subsidy", recommended_capacity_kw=5)
		# Raised from the customer: its survey is found, and the phase found on site wins.
		values = estimate_prefill({"solar_consumer": self.consumer.name})
		self.assertEqual(values["site_survey"], survey.name)
		self.assertEqual((values["system_type"], values["connection_type"], values["subsidy_option"],
			values["override_capacity_kw"]), ("Hybrid", "Three Phase", "With Subsidy", "5"))

	def test_step_one_knows_each_surveys_answers_and_each_packages_status(self):
		from a3_sola.api.portal_estimate import detail_columns

		survey = make_survey(self.consumer, system_type="On-Grid", connection_type="Three Phase", recommended_capacity_kw=5)
		columns = detail_columns(prefill={"solar_consumer": self.consumer.name})
		surveys = next(f for f in columns[0]["fields"] if f["fieldname"] == "site_survey")["options"]
		mine = next(o for o in surveys if o["value"] == survey.name)
		self.assertEqual((mine["system_type"], mine["phase"], mine["capacity"]), ("On-Grid", "Three Phase", "5"))
		packages = next(f for f in columns[1]["fields"] if f["fieldname"] == "solar_package")["options"]
		self.assertTrue(all(o.get("status") in ("Active", "Draft", "") for o in packages if o["value"]))

	def test_the_old_spelling_of_the_system_is_brought_in_line(self):
		from a3_sola.patches.v1_2 import survey_system_type_spelling

		survey = make_survey(self.consumer)
		frappe.db.set_value("Site Survey", survey.name, "system_type", "On-grid")
		survey_system_type_spelling.execute()
		self.assertEqual(frappe.db.get_value("Site Survey", survey.name, "system_type"), "On-Grid")
