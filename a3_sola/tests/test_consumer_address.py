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


#: An address as the Aadhaar card gives it - where the customer lives.
HOME = {"address_line1": "Kizhakkethil House", "address_line2": "Temple Road", "city": "Aluva", "pincode": "683101"}
#: An address as the KSEB bill gives it - where the connection is.
SITE = {"address_line1": "Plot 12", "address_line2": "Industrial Estate", "city": "Kalamassery", "pincode": "683104"}


def parts(prefix, address):
	return {f"{prefix}_{k}": v for k, v in address.items()}


class TestPermanentAddressFirst(FrappeTestCase):
	"""The permanent address comes first, read from the Aadhaar card; the installation site is the
	same place unless the customer says it is not."""

	def setUp(self):
		frappe.set_user("Administrator")

	def site(self, doc):
		return {k: doc.get(f"site_{k}") for k in SITE}

	def test_same_site_is_the_permanent_address(self):
		doc = make_consumer(installation_address=None, permanent_address_same="Yes", **parts("permanent", HOME))
		self.assertEqual(self.site(doc), HOME)
		self.assertEqual(doc.permanent_address_line1, HOME["address_line1"])
		self.assertIn("Aluva", doc.installation_site_address)

	def test_answering_yes_keeps_the_address(self):
		"""Read from the Aadhaar with No, then changed to Yes: nothing vanishes - the site is the
		permanent address."""
		doc = make_consumer(installation_address=None, permanent_address_same="No",
			**parts("permanent", HOME), **parts("site", SITE))
		self.assertEqual(self.site(doc), SITE)
		doc.permanent_address_same = "Yes"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.permanent_city, "Aluva")
		self.assertEqual(self.site(doc), HOME)
		self.assertIn("Aluva", doc.permanent_address)
		self.assertIn("Aluva", doc.installation_site_address)
		# The site's Address record moved with it.
		self.assertEqual(frappe.db.get_value("Address", doc.installation_address, "city"), "Aluva")
		self.assertEqual(doc.permanent_address_record, doc.installation_address)

	def test_a_site_elsewhere_keeps_its_own(self):
		doc = make_consumer(installation_address=None, permanent_address_same="No",
			**parts("permanent", HOME), **parts("site", SITE))
		self.assertEqual(self.site(doc), SITE)
		self.assertEqual(doc.permanent_city, "Aluva")

	def test_a_site_known_before_the_permanent_address_fills_it(self):
		"""A customer with only its site (from its lead, or an Address record): the permanent
		address is the site until the Aadhaar card is read."""
		doc = make_consumer(installation_address=None, **parts("site", SITE))
		self.assertEqual(doc.permanent_city, "Kalamassery")
		self.assertEqual(self.site(doc), SITE)
