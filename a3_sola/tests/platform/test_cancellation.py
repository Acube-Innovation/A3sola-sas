# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Cancellation, the data export, and coming back.

The positions being tested are the ones that cost something: that a customer who cancels
keeps the access they paid for, that their data is generated for them before it ends, and
that reactivation puts them back exactly as they were rather than approximately.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from a3_sola.api.entitlements import TENANT_FIELD
from a3_sola.api.lifecycle import access, cancellation, state_machine
from a3_sola.tests.platform import lifecycle_fixtures as fx

PREFIX = "lccancel"


class CancellationTestCase(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		fx.purge(PREFIX)
		fx.settings(**fx.INERT)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		fx.settings(**fx.LIVE)
		self.plan = fx.a_plan()


class TestCancellingIsHonest(CancellationTestCase):
	def test_it_defaults_to_the_end_of_the_period_they_paid_for(self):
		sub = fx.a_subscription(f"{PREFIX}end", days_into_period=5)
		name = cancellation.request_cancellation(sub, "Too Expensive")
		doc = frappe.get_doc("Cancellation Request", name)
		self.assertEqual(doc.cancellation_type, "End of Period")
		self.assertEqual(getdate(doc.effective_date), getdate(sub.current_period_end))

	def test_access_is_not_cut_on_the_day_they_cancel(self):
		sub = fx.a_subscription(f"{PREFIX}keep", days_into_period=5)
		tenant = fx.a_tenant(f"{PREFIX}keep", sub, users=2)
		cancellation.request_cancellation(sub, "Switching Provider")

		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Cancelling")
		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "access_gate"), "Full")
		self.assertTrue(all(row["enabled"] for row in frappe.get_all(
			"User", filters={TENANT_FIELD: tenant.name}, fields=["enabled"])))

	def test_a_customer_cannot_demand_an_immediate_cancellation(self):
		"""It may involve a refund, so it is an internal decision."""
		sub = fx.a_subscription(f"{PREFIX}imm")
		with self.assertRaises(frappe.ValidationError) as caught:
			cancellation.request_cancellation(
				sub, "Business Closed", cancellation_type="Immediate",
				requested_by="Tenant Self Service")
		self.assertIn("recorded for the end of the period", str(caught.exception))

	def test_asking_twice_returns_the_same_request(self):
		sub = fx.a_subscription(f"{PREFIX}twice")
		first = cancellation.request_cancellation(sub, "Too Expensive")
		second = cancellation.request_cancellation(sub, "Too Expensive")
		self.assertEqual(first, second)

	def test_the_mandate_is_cancelled_as_the_rbi_requires(self):
		sub = fx.a_subscription(f"{PREFIX}mand")
		mandate = frappe.get_doc({
			"doctype": "Payment Mandate",
			"platform_subscription": sub.name,
			"customer_name": sub.organisation_name,
			"customer_email": sub.primary_contact_email,
			"mandate_type": "Card e-Mandate",
			"recurring_debit_amount": 3540,
			"registered_max_amount": 5000,
			"registered_on": today(),
			"valid_until": add_days(today(), 300),
		})
		mandate.flags.ignore_permissions = True
		mandate.flags.ignore_mandatory = True
		mandate.insert(ignore_permissions=True)
		sub.db_set("payment_mandate", mandate.name, update_modified=False)
		sub.reload()

		cancellation.request_cancellation(sub, "Business Closed")

		self.assertEqual(frappe.db.get_value("Payment Mandate", mandate.name, "status"),
		                 "Cancelled")

	def test_the_retention_step_never_blocks_the_customer(self):
		"""It is a step somebody chooses to take, not a maze the customer walks."""
		sub = fx.a_subscription(f"{PREFIX}ret")
		name = cancellation.request_cancellation(sub, "Poor Support")
		doc = frappe.get_doc("Cancellation Request", name)
		self.assertEqual(doc.status, "Retention In Progress")
		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Cancelling", "the cancellation was recorded regardless")


class TestTheirData(CancellationTestCase):
	def test_the_export_is_generated_before_access_ends(self):
		sub = fx.a_subscription(f"{PREFIX}exp")
		tenant = fx.a_tenant(f"{PREFIX}exp", sub, users=1)
		company = frappe.db.get_value("Company", {}, "name")
		frappe.db.set_value("Tenant", tenant.name, "company", company,
		                    update_modified=False)

		name = cancellation.request_cancellation(sub, "Switching Provider")
		doc = frappe.get_doc("Cancellation Request", name)

		self.assertTrue(doc.data_export_generated_on,
		                "the export was not generated while they still had access")
		self.assertTrue(doc.data_export_file)

	def test_the_retention_window_is_recorded_so_nothing_is_deleted_by_surprise(self):
		sub = fx.a_subscription(f"{PREFIX}win")
		name = cancellation.request_cancellation(sub, "Temporary Pause")
		doc = frappe.get_doc("Cancellation Request", name)
		self.assertTrue(doc.reactivation_deadline)
		self.assertTrue(doc.retention_expiry_date)
		self.assertGreater(getdate(doc.retention_expiry_date),
		                   getdate(doc.reactivation_deadline))

	def test_nothing_is_ever_auto_terminated(self):
		sub = fx.a_subscription(f"{PREFIX}term")
		name = cancellation.request_cancellation(sub, "Business Closed")
		frappe.db.set_value("Cancellation Request", name, {
			"status": "Cancelled", "retention_expiry_date": add_days(today(), -1),
		}, update_modified=False)

		flagged = cancellation.flag_for_termination_review()

		self.assertGreaterEqual(flagged, 1)
		self.assertEqual(frappe.db.get_value("Cancellation Request", name, "status"),
		                 "Cancelled", "a retention window expiring terminated something")


class TestReactivation(CancellationTestCase):
	def test_it_restores_each_user_to_their_recorded_prior_state(self):
		sub = fx.a_subscription(f"{PREFIX}re", status="Grace")
		tenant = fx.a_tenant(f"{PREFIX}re", sub, users=2)
		theirs = fx.stamp_user(f"{PREFIX}.gone@lifecycle.example", tenant.name,
		                       first_name="Gone", enabled=0,
		                       roles=("Solar Sales Executive",))
		suspension = frappe.get_doc({
			"doctype": "Access Suspension", "tenant": tenant.name,
			"platform_subscription": sub.name, "suspension_type": "Non Payment",
			"reason": "unpaid", "requested_by": "Scheduler",
			"approval_status": "Not Required", "status": "Scheduled",
		})
		suspension.flags.ignore_permissions = True
		suspension.insert(ignore_permissions=True)
		suspension.submit()
		access.suspend_tenant_access(tenant.name, suspension)
		state_machine.transition(sub, "Suspended", "unpaid", "Internal User",
		                         access_effect="None")
		state_machine.transition(sub, "Cancelled", "gave up", "Internal User",
		                         access_effect="None")
		sub.db_set("reactivation_deadline", add_days(today(), 20), update_modified=False)
		sub.reload()

		cancellation.reactivate_subscription(sub, trigger="Internal User")

		self.assertEqual(frappe.db.get_value("User", theirs, "enabled"), 0,
		                 "reactivation enabled somebody the tenant had disabled")
		others = frappe.get_all("User", filters={TENANT_FIELD: tenant.name,
		                                         "name": ["!=", theirs]},
		                        fields=["name", "enabled"])
		self.assertTrue(all(row["enabled"] for row in others))
		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Active")

	def test_the_billing_schedule_restarts_from_today(self):
		"""They are not charged for the months they were away."""
		sub = fx.a_subscription(f"{PREFIX}sched", status="Cancelled")
		sub.db_set("reactivation_deadline", add_days(today(), 20), update_modified=False)
		sub.reload()
		cancellation.reactivate_subscription(sub, trigger="Internal User")
		sub.reload()
		self.assertEqual(getdate(sub.current_period_start), getdate(today()))

	def test_reactivating_twice_is_harmless(self):
		sub = fx.a_subscription(f"{PREFIX}re2", status="Cancelled")
		sub.db_set("reactivation_deadline", add_days(today(), 20), update_modified=False)
		sub.reload()
		cancellation.reactivate_subscription(sub, trigger="Internal User")
		cancellation.reactivate_subscription(sub, trigger="Internal User")
		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Active")

	def test_past_the_window_self_service_stops_but_the_door_does_not_close(self):
		sub = fx.a_subscription(f"{PREFIX}late", status="Cancelled")
		sub.db_set("reactivation_deadline", add_days(today(), -5), update_modified=False)
		sub.reload()

		with self.assertRaises(frappe.ValidationError) as caught:
			cancellation.reactivate_subscription(sub, trigger="Tenant Self Service")
		self.assertIn("get in touch", str(caught.exception))

		# An internal user can still do it.
		cancellation.reactivate_subscription(sub, trigger="Internal User")
		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Active")

	def test_an_outstanding_balance_blocks_self_service_reactivation(self):
		sub = fx.a_subscription(f"{PREFIX}owe", status="Cancelled")
		fx.overdue_invoice(sub, days=5)
		sub.db_set({"reactivation_deadline": add_days(today(), 20),
		            "policy": "Standard Non-Payment Policy"}, update_modified=False)
		sub.reload()
		with self.assertRaises(frappe.ValidationError) as caught:
			cancellation.reactivate_subscription(sub, trigger="Tenant Self Service")
		self.assertIn("outstanding", str(caught.exception).lower())


class TestWithdrawing(CancellationTestCase):
	def test_a_withdrawn_cancellation_returns_them_to_active(self):
		sub = fx.a_subscription(f"{PREFIX}wd")
		name = cancellation.request_cancellation(sub, "Too Expensive")
		cancellation.withdraw(name, "Agreed a 15% discount for twelve months.")

		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Active")
		doc = frappe.get_doc("Cancellation Request", name)
		self.assertEqual(doc.status, "Withdrawn")
		self.assertEqual(doc.retention_outcome, "Accepted")
