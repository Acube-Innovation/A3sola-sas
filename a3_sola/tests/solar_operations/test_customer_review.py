# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One review per job; the Google review rides on it and never hangs."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.solar_operations.doctype.customer_review import customer_review as ctl
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_tasks import task_row


def make_review(installation, **kwargs):
	values = {"doctype": "Customer Review", "solar_installation": installation.name}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


class TestCustomerReview(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		frappe.db.set_value("Company", self.installation.company, "google_review_url", "https://g.page/r/test-review", update_modified=False)

	def test_opening_the_review_starts_the_task_and_there_is_one_per_job(self):
		review = make_review(self.installation)
		row, _doc = task_row(self.installation, "REVIEW")
		self.assertEqual((row.status, row.task_document), ("In Progress", review.name))
		with self.assertRaises(frappe.ValidationError):
			make_review(self.installation)

	def test_a_review_needs_words_or_pictures_to_complete(self):
		review = make_review(self.installation)
		with self.assertRaises(frappe.ValidationError):
			ctl.complete(review.name)
		review.reload()
		review.review_text = "Neat work, finished on the day promised."
		review.rating = 1.0
		review.save(ignore_permissions=True)
		ctl.complete(review.name)
		row, _doc = task_row(self.installation, "REVIEW")
		self.assertEqual(row.status, "Completed")

	def test_the_review_link_is_one_tap_away_and_the_ask_is_recorded(self):
		frappe.db.set_value("Solar Consumer", self.installation.solar_consumer, "mobile_no", "9876543210", update_modified=False)
		review = make_review(self.installation)
		result = ctl.request_review(review.name, via="WhatsApp")
		self.assertTrue(result["link"].startswith("https://wa.me/919876543210?text="))
		self.assertIn("g.page", result["message"])
		review.reload()
		self.assertEqual((review.google_review_status, review.requested_via), ("Requested", "WhatsApp"))

	def test_no_company_link_no_request(self):
		frappe.db.set_value("Company", self.installation.company, "google_review_url", None, update_modified=False)
		review = make_review(self.installation)
		with self.assertRaises(frappe.ValidationError):
			ctl.request_review(review.name)

	def test_posted_completes_the_google_task_after_submit(self):
		review = make_review(self.installation, review_text="Great team.")
		ctl.complete(review.name)
		row, _doc = task_row(self.installation, "GREV")
		self.assertEqual(row.status, "In Progress")
		ctl.mark_posted(review.name, link="https://maps.app.goo.gl/abc")
		row, _doc = task_row(self.installation, "GREV")
		self.assertEqual(row.status, "Completed")

	def test_declined_skips_the_google_task(self):
		review = make_review(self.installation, review_text="Fine.")
		ctl.complete(review.name)
		ctl.mark_declined(review.name, "Does not use Google")
		row, _doc = task_row(self.installation, "GREV")
		self.assertEqual(row.status, "Skipped")
