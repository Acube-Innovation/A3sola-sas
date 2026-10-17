# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer's address is not required: saved without one, it is filled in when known. A
PIN code given is still checked."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.tests.fixtures import make_consumer


class TestConsumerAddress(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_saved_without_an_address(self):
		doc = make_consumer(installation_address=None)
		self.assertFalse(doc.installation_site_address)
		self.assertEqual(doc.permanent_address_same, "Yes")

	def test_a_permanent_address_elsewhere_may_be_left_blank(self):
		doc = make_consumer(installation_address=None, permanent_address_same="No")
		self.assertFalse(doc.permanent_address)

	def test_the_address_parts_are_not_mandatory(self):
		meta = frappe.get_meta("Solar Consumer")
		for prefix in ("site", "permanent"):
			for part in ("address_line1", "city", "state", "district", "pincode"):
				df = meta.get_field(f"{prefix}_{part}")
				self.assertFalse(df.reqd or df.mandatory_depends_on, df.fieldname)

	def test_a_pin_code_given_is_still_checked(self):
		with self.assertRaises(frappe.ValidationError):
			make_consumer(installation_address=None, site_pincode="12AB")
