# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A customer's Contact and address dropdowns offer only its own contacts and addresses, each
address in full: a typed installation site becomes an Address record, selected; with the
permanent address the same, it is selected there too, unless another is chosen."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api.portal_fields import edit_spec
from a3_sola.solar_crm.doctype.solar_consumer import solar_consumer as module
from a3_sola.tests.fixtures import make_address, make_consumer

SITE = {"site_address_line1": "Rose Villa", "site_address_line2": "Temple Road", "site_city": "Chalakudy",
	"site_pincode": "680307"}


class TestConsumerAddressChoices(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def typed(self, **kwargs):
		return frappe.get_doc("Solar Consumer", make_consumer(installation_address=None, **SITE, **kwargs).name)

	def spec(self, doc, fieldname):
		return edit_spec(doc.meta.get_field(fieldname), doc.get(fieldname), doc)

	def test_a_typed_site_becomes_its_address_record_selected(self):
		doc = self.typed()
		self.assertTrue(doc.installation_address)
		self.assertEqual(doc.permanent_address_record, doc.installation_address)
		self.assertEqual(module.address_line(doc.installation_address), "Rose Villa, Temple Road, Chalakudy, Kerala - 680307")

	def test_the_address_dropdowns_offer_only_its_own_addresses_in_full(self):
		doc = self.typed()
		make_address()  # someone else's
		spec = self.spec(doc, "installation_address")
		self.assertEqual([c["value"] for c in spec["choices"]], [doc.installation_address])
		self.assertEqual(spec["choices"][0]["label"], module.address_line(doc.installation_address))
		self.assertEqual(self.spec(doc, "permanent_address_record")["value"], doc.installation_address)

	def test_the_contact_dropdown_offers_only_its_own_contacts(self):
		doc = self.typed()
		ours = frappe.get_doc({"doctype": "Contact", "first_name": "Own Contact",
			"links": [{"link_doctype": "Solar Consumer", "link_name": doc.name}]}).insert(ignore_permissions=True)
		theirs = frappe.get_doc({"doctype": "Contact", "first_name": "Someone Else"}).insert(ignore_permissions=True)
		values = [c["value"] for c in self.spec(doc, "contact_person")["choices"]]
		self.assertIn(ours.name, values)
		self.assertNotIn(theirs.name, values)

	def test_another_address_chosen_fills_the_site_and_the_permanent_follows(self):
		doc = self.typed()
		other = frappe.get_doc({"doctype": "Address", "address_title": "Second Home", "address_type": "Billing",
			"address_line1": "Lake View", "city": "Aluva", "pincode": "683101", "country": "India",
			"gst_category": "Unregistered", "links": [{"link_doctype": "Solar Consumer", "link_name": doc.name}]}
			).insert(ignore_permissions=True)
		doc.permanent_address_record = other.name
		doc.save(ignore_permissions=True)
		self.assertEqual((doc.permanent_address_line1, doc.permanent_city), ("Lake View", "Aluva"))
		self.assertEqual(doc.site_address_line1, "Rose Villa")
		doc.installation_address = other.name
		doc.save(ignore_permissions=True)
		self.assertEqual((doc.site_address_line1, doc.site_city), ("Lake View", "Aluva"))

	def test_the_patch_gives_an_older_customer_its_record(self):
		from a3_sola.patches.v1_2 import consumer_address_records

		doc = self.typed()
		frappe.db.set_value("Solar Consumer", doc.name, {"installation_address": None, "permanent_address_record": None})
		consumer_address_records.execute()
		self.assertTrue(frappe.db.get_value("Solar Consumer", doc.name, "installation_address"))


class TestConsumerConnection(FrappeTestCase):
	"""A customer is LT-I (Domestic) unless said otherwise, its connection date and survey
	number are not asked, and it is an ERPNext Customer from the day it is created."""

	def setUp(self):
		frappe.set_user("Administrator")

	def test_the_tariff_is_lt1_domestic_by_default(self):
		self.assertEqual(frappe.get_meta("Solar Consumer").get_field("tariff_category").default, "LT-I")
		if frappe.db.exists("KSEB Tariff Category", "LT-I"):
			self.assertEqual(make_consumer(tariff_category=None).tariff_category, "LT-I")

	def test_connection_date_and_survey_number_are_hidden(self):
		meta = frappe.get_meta("Solar Consumer")
		self.assertTrue(meta.get_field("connection_date").hidden)
		self.assertTrue(meta.get_field("survey_number").hidden)

	def test_a_new_customer_is_an_erpnext_customer_at_once(self):
		doc = frappe.get_doc("Solar Consumer", make_consumer(installation_address=None, **SITE).name)
		self.assertTrue(doc.customer)
		customer = frappe.get_doc("Customer", doc.customer)
		self.assertEqual(customer.customer_name, doc.consumer_name)
		self.assertTrue(frappe.db.exists("Dynamic Link", {"parent": doc.installation_address, "link_doctype": "Customer",
			"link_name": customer.name}))
