# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Customer portal isolation.

The portal's whole security model is that ownership is re-derived from the session on
every request and never taken from a parameter. These tests attack it the way an actual
customer would: by editing the id in the URL.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal
from a3_sola.tests.solar_projects.fixtures import (
	commissioned_project,
	installation_with_customer,
	make_visit,
	om_contract,
)


def portal_user(prefix, customer):
	"""A customer login, linked the way ERPNext links one: through a Contact.

	One login can legitimately own several systems - a society, or a customer with two
	roofs - so the address is tied to the customer rather than shared across fixtures.
	"""
	email = f"{prefix}.{frappe.scrub(customer)}@example.com"
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"user_type": "Website User",
			}
		).insert(ignore_permissions=True)

	contact = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": email.split("@")[0],
			"links": [{"link_doctype": "Customer", "link_name": customer}],
			"email_ids": [{"email_id": email, "is_primary": 1}],
		}
	)
	contact.flags.ignore_permissions = True
	contact.flags.ignore_mandatory = True
	contact.insert(ignore_permissions=True)
	return email


class TestPortalIsolation(FrappeTestCase):
	def setUp(self):
		self.project_a, self.installation_a, _ = commissioned_project()
		self.project_b, self.installation_b, _ = commissioned_project(
			installation=installation_with_customer()
		)
		self.user_a = portal_user("customer.a", self.installation_a.customer)
		self.user_b = portal_user("customer.b", self.installation_b.customer)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_customer_sees_their_own_system(self):
		frappe.set_user(self.user_a)
		names = {system["name"] for system in portal.systems()}
		self.assertEqual(names, {self.installation_a.name})

	def test_a_customer_never_sees_another_system(self):
		frappe.set_user(self.user_a)
		names = {system["name"] for system in portal.systems()}
		self.assertNotIn(self.installation_b.name, names)

	def test_editing_the_id_in_the_url_is_refused(self):
		"""The obvious attack: change the installation in the query string."""
		frappe.set_user(self.user_a)
		for call in (portal.generation_history, portal.service_history, portal.documents, portal.invoices):
			with self.assertRaises(frappe.DoesNotExistError, msg=f"{call.__name__} leaked"):
				call(self.installation_b.name)

	def test_a_nonexistent_id_looks_the_same_as_someone_elses(self):
		"""A different error would confirm the other record exists."""
		frappe.set_user(self.user_a)
		with self.assertRaises(frappe.DoesNotExistError):
			portal.documents("SOL-INST-NOT-REAL")
		with self.assertRaises(frappe.DoesNotExistError):
			portal.documents(self.installation_b.name)

	def test_a_guest_sees_nothing(self):
		frappe.set_user("Guest")
		self.assertEqual(portal.systems(), [])

	def test_a_user_with_no_linked_customer_sees_nothing(self):
		email = "unlinked.person@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Unlinked",
					"send_welcome_email": 0,
					"user_type": "Website User",
				}
			).insert(ignore_permissions=True)
		frappe.set_user(email)
		self.assertEqual(portal.systems(), [])

	def test_a_customer_cannot_raise_a_ticket_on_another_system(self):
		frappe.set_user(self.user_a)
		with self.assertRaises(frappe.DoesNotExistError):
			portal.raise_ticket(self.installation_b.name, "Low Generation", "Not my system.")

	def test_a_customer_can_raise_a_ticket_on_their_own(self):
		frappe.set_user(self.user_a)
		name = portal.raise_ticket(
			self.installation_a.name, "Low Generation", "Output looks low this month."
		)
		frappe.set_user("Administrator")
		ticket = frappe.get_doc("Service Ticket", name)
		self.assertEqual(ticket.reported_via, "Portal")
		self.assertEqual(
			ticket.om_contract, om_contract(self.project_a).name
		)

	def test_a_ticket_needs_an_actual_description(self):
		frappe.set_user(self.user_a)
		with self.assertRaises(frappe.ValidationError):
			portal.raise_ticket(self.installation_a.name, "Low Generation", "   ")

	def test_a_document_url_is_never_resolved_for_another_customer(self):
		frappe.set_user("Administrator")
		installation = frappe.get_doc("Solar Installation", self.installation_b.name)
		template = frappe.db.get_value(
			"Solar Document Template", {"recipient": "Consumer"}, "name"
		)
		self.assertTrue(template, "no customer-facing document template seeded")
		installation.append(
			"generated_documents",
			{
				"solar_document_template": template,
				"document_name": "Commissioning Certificate",
				"status": "Generated",
				"file": "/private/files/someone-elses.pdf",
				"generated_on": frappe.utils.now_datetime(),
			},
		)
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
		row = installation.generated_documents[-1].name

		frappe.set_user(self.user_a)
		with self.assertRaises(frappe.DoesNotExistError):
			portal.download(row)

	def test_the_document_list_carries_no_file_url(self):
		"""Nothing to copy out of the page source."""
		frappe.set_user(self.user_a)
		for document in portal.documents(self.installation_a.name):
			self.assertNotIn("file", document)
			self.assertNotIn("file_url", document)


class TestPortalExposesNothingFinancial(FrappeTestCase):
	def setUp(self):
		self.project, self.installation, _ = commissioned_project()
		self.user = portal_user("customer.money", self.installation.customer)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_no_cost_margin_or_provision_reaches_the_customer(self):
		frappe.set_user(self.user)
		forbidden = (
			"total_cost", "gross_margin_amount", "gross_margin_percent", "cost_per_kw",
			"om_provision_amount", "om_provision_allocated", "subsidy_receivable_amount",
			"material_cost", "labour_cost", "rework_cost", "gross_contract_value",
		)
		for system in portal.systems():
			for key in forbidden:
				self.assertNotIn(key, system, f"{key} reached the customer portal")

	def test_service_history_carries_no_visit_cost(self):
		frappe.set_user("Administrator")
		contract = om_contract(self.project)
		visit = make_visit(contract, checklist=[])
		visit.submit()

		frappe.set_user(self.user)
		history = portal.service_history(self.installation.name)
		for row in history["visits"]:
			for key in ("labour_cost", "material_cost", "travel_cost", "total_visit_cost"):
				self.assertNotIn(key, row, f"{key} reached the customer portal")

	def test_tickets_carry_no_chargeable_amount(self):
		frappe.set_user(self.user)
		portal.raise_ticket(self.installation.name, "Low Generation", "Looks low.")
		history = portal.service_history(self.installation.name)
		for row in history["tickets"]:
			self.assertNotIn("chargeable_amount", row)

	def test_invoices_are_the_only_money_shown(self):
		frappe.set_user(self.user)
		fields = set()
		for invoice in portal.invoices(self.installation.name):
			fields |= set(invoice.keys())
		self.assertEqual(
			fields - {"name", "posting_date", "due_date", "grand_total", "outstanding_amount", "status"},
			set(),
		)
