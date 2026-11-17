# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Delete on a lead or customer takes every record made for them, or nothing
(api/cascade_delete)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import cascade_delete
from a3_sola.tests.fixtures import make_consumer, make_estimate, make_lead, make_survey


def _gone(test, found):
	left = {dt: [n for n in names if frappe.db.exists(dt, n)] for dt, names in found.items()}
	test.assertEqual({dt: n for dt, n in left.items() if n}, {})


class TestCascadeDelete(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer(consumer_name="Cascade Customer")
		self.survey = make_survey(self.consumer)
		self.estimate = make_estimate(self.consumer, self.survey)

	def file(self, doctype, name):
		return frappe.get_doc({"doctype": "File", "file_name": "kyc.txt", "content": b"kyc " + name.encode(),
			"is_private": 1, "attached_to_doctype": doctype, "attached_to_name": name}).insert(ignore_permissions=True)

	def test_the_customer_and_its_chain_go(self):
		f = self.file("Solar Consumer", self.consumer.name)
		plan = cascade_delete.collect("Solar Consumer", self.consumer.name)
		found = plan["found"]
		self.assertIn(self.survey.name, found["Site Survey"])
		self.assertIn(self.estimate.name, found["Solar Design Estimate"])
		self.assertIn(self.consumer.lead, found["Lead"])
		self.assertTrue(found.get("Customer"))

		out = cascade_delete.delete("Solar Consumer", self.consumer.name, confirm=self.consumer.name)
		self.assertEqual(out["redirect"], "/a3solaportal/consumers")
		_gone(self, found)
		self.assertFalse(frappe.db.exists("File", f.name))
		# Each one is in Deleted Documents, where it can be restored.
		self.assertTrue(frappe.db.exists("Deleted Document", {"deleted_doctype": "Site Survey", "deleted_name": self.survey.name}))

	def test_from_the_lead_the_customer_goes_too(self):
		found = cascade_delete.collect("Lead", self.consumer.lead)["found"]
		self.assertIn(self.consumer.name, found["Solar Consumer"])
		cascade_delete.delete("Lead", self.consumer.lead, confirm=self.consumer.lead)
		_gone(self, found)

	def test_a_lead_on_its_own(self):
		lead = make_lead(lead_name="Lone Lead")
		out = cascade_delete.preview("Lead", lead)
		self.assertEqual([c["doctype"] for c in out["counts"] if c["doctype"] not in ("Contact", "Address")], ["Lead"])
		cascade_delete.delete("Lead", lead, confirm=lead)
		self.assertFalse(frappe.db.exists("Lead", lead))

	def test_the_name_must_be_typed(self):
		with self.assertRaises(frappe.ValidationError):
			cascade_delete.delete("Solar Consumer", self.consumer.name, confirm="yes")
		self.assertTrue(frappe.db.exists("Solar Consumer", self.consumer.name))

	def test_a_submitted_invoice_refuses_and_nothing_goes(self):
		customer = frappe.db.get_value("Solar Consumer", self.consumer.name, "customer")
		# Written straight in: the refusal reads the invoice's docstatus, not its ledger.
		invoice = frappe.get_doc({"doctype": "Sales Invoice", "name": "ACC-SINV-CASCADE-1", "customer": customer,
			"company": self.consumer.company, "docstatus": 1})
		invoice.db_insert()
		preview = cascade_delete.preview("Solar Consumer", self.consumer.name)
		self.assertEqual([(b["doctype"], b["name"]) for b in preview["blockers"]], [("Sales Invoice", invoice.name)])
		with self.assertRaises(frappe.ValidationError):
			cascade_delete.delete("Solar Consumer", self.consumer.name, confirm=self.consumer.name)
		self.assertTrue(frappe.db.exists("Solar Consumer", self.consumer.name))
		self.assertTrue(frappe.db.exists("Site Survey", self.survey.name))

	def test_a_draft_invoice_goes_with_the_customer(self):
		customer = frappe.db.get_value("Solar Consumer", self.consumer.name, "customer")
		invoice = frappe.get_doc({"doctype": "Sales Invoice", "name": "ACC-SINV-CASCADE-2", "customer": customer,
			"company": self.consumer.company, "docstatus": 0})
		invoice.db_insert()
		self.assertIn(invoice.name, cascade_delete.collect("Solar Consumer", self.consumer.name)["found"]["Sales Invoice"])
		cascade_delete.delete("Solar Consumer", self.consumer.name, confirm=self.consumer.name)
		self.assertFalse(frappe.db.exists("Sales Invoice", invoice.name))

	def test_a_contact_shared_with_another_lead_stays(self):
		other = make_lead(lead_name="Someone Else")
		contact = frappe.get_doc({"doctype": "Contact", "first_name": "Shared",
			"links": [{"link_doctype": "Solar Consumer", "link_name": self.consumer.name},
				{"link_doctype": "Lead", "link_name": other}]}).insert(ignore_permissions=True)
		cascade_delete.delete("Solar Consumer", self.consumer.name, confirm=self.consumer.name)
		links = frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "parent": contact.name},
			fields=["link_doctype", "link_name"])
		self.assertEqual([(l.link_doctype, l.link_name) for l in links], [("Lead", other)])

	def test_only_managers_and_admins_may(self):
		email = "cascade-exec@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Exec", "send_welcome_email": 0,
				"roles": [{"role": "Solar Sales Executive"}]}).insert(ignore_permissions=True)
		self.assertFalse(cascade_delete.can_delete(email))
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				cascade_delete.preview("Solar Consumer", self.consumer.name)
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Solar Consumer", self.consumer.name))
