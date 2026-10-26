# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer's site survey is assigned first - a to-do on the customer - and only the person
it is assigned to creates it; the survey names them its surveyor and closes the to-do."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import survey_assignment as sa
from a3_sola.tests.fixtures import make_consumer

ROLE = "Solar Survey Engineer"


def surveyor(email):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0,
			"user_type": "System User", "roles": [{"role": ROLE}]})
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
	return email


class TestSurveyAssignment(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		self.one = surveyor("survey.one@a3sola.test")
		self.two = surveyor("survey.two@a3sola.test")

	def tearDown(self):
		frappe.set_user("Administrator")

	def survey(self, as_user):
		frappe.set_user(as_user)
		doc = frappe.new_doc("Site Survey")
		doc.solar_consumer = self.consumer.name
		return doc

	def test_it_is_unassigned_until_someone_is_given_it(self):
		state = sa.state(self.consumer)
		self.assertIsNone(state.assignee)
		self.assertTrue(state.can_assign)

	def test_assigning_makes_a_to_do_on_the_customer(self):
		sa.assign(consumer=self.consumer.name, user=self.one, comment="Bring the ladder")
		todo = frappe.get_all("ToDo", filters={"reference_type": "Solar Consumer", "reference_name": self.consumer.name,
			"status": "Open"}, fields=["allocated_to", "description"])
		self.assertEqual([t.allocated_to for t in todo], [self.one])
		self.assertIn(sa.MARKER, todo[0].description)
		self.assertEqual(sa.assignee(self.consumer.name), self.one)

	def test_reassigning_hands_it_over(self):
		sa.assign(consumer=self.consumer.name, user=self.one)
		sa.assign(consumer=self.consumer.name, user=self.two)
		self.assertEqual(sa.assignee(self.consumer.name), self.two)
		self.assertEqual(frappe.db.get_value("ToDo", {"reference_name": self.consumer.name, "allocated_to": self.one}, "status"),
			"Cancelled")

	def test_only_someone_who_can_survey_is_assigned(self):
		with self.assertRaises(frappe.ValidationError):
			sa.assign(consumer=self.consumer.name, user="Guest")

	def test_only_the_assignee_creates_the_survey(self):
		with self.assertRaises(frappe.ValidationError):
			sa.check_create(self.survey(self.one))  # not assigned yet
		frappe.set_user("Administrator")
		sa.assign(consumer=self.consumer.name, user=self.one)
		with self.assertRaises(frappe.ValidationError):
			sa.check_create(self.survey(self.two))
		doc = self.survey(self.one)
		sa.check_create(doc)
		self.assertEqual(doc.surveyor, self.one)

	def test_the_survey_made_closes_the_to_do(self):
		sa.assign(consumer=self.consumer.name, user=self.one)
		sa.close_on_create(frappe._dict(solar_consumer=self.consumer.name))
		self.assertIsNone(sa.assignee(self.consumer.name))

	def test_the_system_is_not_held_to_it(self):
		doc = self.survey(self.two)
		doc.flags.ignore_permissions = True
		sa.check_create(doc)  # no error: starter data, imports, fixtures

	def test_a_survey_the_system_makes_still_names_the_assignee(self):
		sa.assign(consumer=self.consumer.name, user=self.one)
		doc = self.survey("Administrator")
		sa.check_create(doc)
		self.assertEqual(doc.surveyor, self.one)

	def test_the_form_offers_the_assignee_as_surveyor(self):
		from a3_sola.api import record_links

		sa.assign(consumer=self.consumer.name, user=self.one)
		self.assertEqual(record_links.prefill("Site Survey", solar_consumer=self.consumer.name).get("surveyor"), self.one)

	def test_the_assignee_stays_the_surveyor_after_the_to_do_closes(self):
		sa.assign(consumer=self.consumer.name, user=self.one)
		sa.close_on_create(frappe._dict(solar_consumer=self.consumer.name))
		self.assertEqual(sa.assigned_surveyor(self.consumer.name), self.one)
		doc = self.survey("Administrator")
		from a3_sola.api import record_links

		record_links.fill_survey(doc)
		self.assertEqual(doc.surveyor, self.one)
