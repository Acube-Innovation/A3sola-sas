# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The audit trail, and the recovery actions that write to it.

What is worth proving here is not that entries get written - that is easy - but the three
properties that make the trail worth having at all:

* An entry cannot be edited or deleted, by anyone, through the application.
* Editing the table underneath the application is detectable.
* A credential change is recorded without recording the credential.

Plus the guardrails on the recovery actions, which are the part most likely to be relaxed
by a later change made in a hurry: a manual override needs a reason, needs a reference,
and refuses to run while the gateway can still be asked.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from a3_sola.api import admin_actions, audit
from a3_sola.platform.doctype.platform_audit_entry import platform_audit_entry as audit_doc

DOCTYPE = "Platform Audit Entry"


class AuditTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.flags.mock_gateway_behaviour = "success"

	def tearDown(self):
		frappe.flags.mock_gateway_behaviour = None
		frappe.set_user("Administrator")

	def _subscription(self, **kwargs):
		plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		values = {
			"doctype": "Platform Subscription",
			"organisation_name": "Audit Test EPC",
			"primary_contact_email": "audit@testepc.example",
			"subscription_plan": plan,
			"billing_cycle": "Monthly",
			"included_users": 5,
			"subtotal": 3000,
			"tax_amount": 540,
			"currency": "INR",
			"start_date": today(),
			"current_period_start": today(),
			"current_period_end": add_days(today(), 30),
			"next_billing_date": today(),
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def _order(self, **kwargs):
		subscription = kwargs.pop("subscription", None) or self._subscription()
		values = {
			"doctype": "Payment Order",
			"reference_doctype": "Platform Subscription",
			"reference_name": subscription.name,
			"platform_subscription": subscription.name,
			"customer_name": "Audit Test EPC",
			"customer_email": "audit@testepc.example",
			"order_type": "Renewal",
			"billing_cycle": "Monthly",
			"collection_mode": "Payment Link",
			"period_start": today(),
			"period_end": add_days(today(), 30),
			"subtotal": 3000,
			"tax_amount": 540,
			"total_amount": 3540,
			"amount_in_paise": 354000,
			"currency": "INR",
			"customer_state_code": "32",
			"status": "Pending",
			"idempotency_key": frappe.generate_hash(length=32),
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True)
		return doc


class TestEntriesArePermanent(AuditTestCase):
	def test_an_entry_cannot_be_edited(self):
		name = audit.record("Manual Payment Override", "A thing that happened")
		self.assertTrue(name)
		entry = frappe.get_doc(DOCTYPE, name)
		entry.subject = "Something else entirely"
		with self.assertRaises(frappe.ValidationError):
			entry.save(ignore_permissions=True)

	def test_an_entry_cannot_be_deleted(self):
		name = audit.record("Manual Payment Override", "A thing that happened")
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc(DOCTYPE, name, force=True, ignore_permissions=True)
		self.assertTrue(frappe.db.exists(DOCTYPE, name))

	def test_no_role_at_all_may_write_to_the_trail(self):
		meta = frappe.get_meta(DOCTYPE)
		for perm in meta.permissions:
			self.assertFalse(perm.get("write"), f"{perm.role} may write audit entries")
			self.assertFalse(perm.get("create"), f"{perm.role} may create audit entries")
			self.assertFalse(perm.get("delete"), f"{perm.role} may delete audit entries")

	def test_every_entry_records_who_and_when(self):
		name = audit.record("Refund Approved", "Approved something")
		entry = frappe.get_doc(DOCTYPE, name)
		self.assertEqual(entry.actor, frappe.session.user)
		self.assertTrue(entry.occurred_on)
		self.assertIn("System Manager", entry.actor_roles or "")


class TestTheHashChain(AuditTestCase):
	def test_entries_chain_to_the_one_before(self):
		first = frappe.get_doc(DOCTYPE, audit.record("Refund Requested", "One"))
		second = frappe.get_doc(DOCTYPE, audit.record("Refund Approved", "Two"))
		self.assertEqual(second.previous_entry, first.name)
		self.assertEqual(second.chain_index, first.chain_index + 1)
		self.assertTrue(second.entry_hash)
		self.assertNotEqual(first.entry_hash, second.entry_hash)

	def test_an_intact_chain_verifies(self):
		audit.record("Refund Requested", "Chain check A")
		audit.record("Refund Processed", "Chain check B")
		result = audit_doc.verify_chain()
		self.assertTrue(result["intact"], f"broken at {result['first_break']}")

	def test_editing_the_table_underneath_is_detected(self):
		name = audit.record("Manual Payment Override", "Original wording")
		# Straight past the controller, exactly as a database edit would.
		frappe.db.sql(
			"UPDATE `tabPlatform Audit Entry` SET subject = %s WHERE name = %s",
			("Rewritten wording", name),
		)
		result = audit_doc.verify_chain()
		self.assertFalse(result["intact"])
		self.assertIn(name, result["broken"])
		# Put it back so later tests in the same database start from a clean chain.
		frappe.db.sql(
			"UPDATE `tabPlatform Audit Entry` SET subject = %s WHERE name = %s",
			("Original wording", name),
		)
		self.assertTrue(audit_doc.verify_chain()["intact"])


class TestSecretsNeverEnterTheTrail(AuditTestCase):
	def test_a_credential_change_is_recorded_without_the_credential(self):
		settings = frappe.get_single("A3 Sola Settings")
		before = frappe.db.count(DOCTYPE)
		settings.razorpay_key_id = "AUDIT-CHECK-VALUE-NOT-A-REAL-KEY"
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)

		self.assertGreater(frappe.db.count(DOCTYPE), before)
		entry = frappe.get_all(
			DOCTYPE,
			filters={"entry_type": "Gateway Credentials Changed"},
			fields=["name", "value_before", "value_after", "detail", "subject"],
			order_by="creation desc",
			limit_page_length=1,
		)[0]
		blob = " ".join(str(entry.get(field) or "") for field in entry)
		self.assertNotIn("AUDIT-CHECK-VALUE-NOT-A-REAL-KEY", blob)
		self.assertIn("set", (entry.value_after or "").lower())

	def test_a_compliance_setting_change_is_recorded_with_both_values(self):
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)
		frappe.db.commit()
		settings = frappe.get_single("A3 Sola Settings")
		settings.afa_free_debit_ceiling = 12000
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)

		entry = frappe.get_all(
			DOCTYPE,
			filters={"changed_field": "afa_free_debit_ceiling"},
			fields=["value_before", "value_after"],
			order_by="creation desc",
			limit_page_length=1,
		)[0]
		self.assertIn("15000", entry.value_before)
		self.assertIn("12000", entry.value_after)
		frappe.db.set_single_value("A3 Sola Settings", "afa_free_debit_ceiling", 15000)


class TestTheTrailNeverBlocksTheAction(AuditTestCase):
	def test_a_failed_entry_returns_none_rather_than_raising(self):
		# An entry type outside the Select list is refused by validation, which stands in
		# for any reason the trail might fail.
		result = audit.record("Not A Real Entry Type", "Should not raise")
		self.assertIsNone(result)


class TestManualOverride(AuditTestCase):
	def test_it_refuses_without_a_reason(self):
		order = self._order()
		with self.assertRaises(frappe.ValidationError):
			admin_actions.mark_paid_manually(order.name, reason="ok", external_reference="UTR1")

	def test_it_refuses_without_an_external_reference(self):
		order = self._order()
		with self.assertRaises(frappe.ValidationError):
			admin_actions.mark_paid_manually(
				order.name, reason="Customer paid by NEFT on Tuesday.", external_reference=""
			)

	def test_it_refuses_while_the_gateway_can_still_be_asked(self):
		order = self._order(gateway_order_id="order_MockAudit001")
		with self.assertRaises(frappe.ValidationError):
			admin_actions.mark_paid_manually(
				order.name,
				reason="Customer says the money left their account.",
				external_reference="UTR2",
			)

	def test_a_proper_override_marks_it_paid_and_records_the_reason(self):
		order = self._order()
		admin_actions.mark_paid_manually(
			order.name,
			reason="Customer transferred by NEFT outside the gateway on 12 August.",
			external_reference="UTR-2026-0812-991",
		)
		order.reload()
		self.assertEqual(order.status, "Paid")

		entry = frappe.get_all(
			DOCTYPE,
			filters={"entry_type": "Manual Payment Override", "reference_name": order.name},
			fields=["reason", "detail", "amount"],
			limit_page_length=1,
		)[0]
		self.assertIn("NEFT", entry.reason)
		self.assertIn("UTR-2026-0812-991", entry.detail)
		self.assertEqual(entry.amount, 3540)

	def test_it_refuses_a_second_time(self):
		order = self._order()
		admin_actions.mark_paid_manually(
			order.name,
			reason="Cheque banked and cleared, confirmed with the bank.",
			external_reference="CHQ-4471",
		)
		with self.assertRaises(frappe.ValidationError):
			admin_actions.mark_paid_manually(
				order.name,
				reason="Cheque banked and cleared, confirmed with the bank.",
				external_reference="CHQ-4471",
			)

	def test_a_billing_executive_may_not_override(self):
		order = self._order()
		user = _user_with_role("Platform Billing Executive", "audit.executive@example.com")
		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				admin_actions.mark_paid_manually(
					order.name,
					reason="Trying it on as a user who should not be able to.",
					external_reference="UTR3",
				)
		finally:
			frappe.set_user("Administrator")


class TestRefetchStatus(AuditTestCase):
	def test_it_applies_a_payment_the_gateway_confirms(self):
		order = self._order(gateway_order_id="order_MockRefetch01", collection_mode="Checkout")
		outcome = admin_actions.refetch_payment_status(order.name)
		order.reload()
		self.assertTrue(outcome["gateway_says_paid"])
		self.assertEqual(order.status, "Paid")
		self.assertTrue(outcome["changed"])

	def test_it_never_reverses_a_payment_we_already_hold(self):
		order = self._order(
			gateway_order_id="order_MockRefetch02", status="Paid", amount_paid=3540
		)
		frappe.flags.mock_gateway_behaviour = "pending"
		outcome = admin_actions.refetch_payment_status(order.name)
		order.reload()
		self.assertEqual(order.status, "Paid")
		self.assertTrue(outcome["discrepancy"])

	def test_it_refuses_when_the_order_never_reached_the_gateway(self):
		order = self._order()
		with self.assertRaises(frappe.ValidationError):
			admin_actions.refetch_payment_status(order.name)

	def test_every_fetch_is_recorded(self):
		order = self._order(gateway_order_id="order_MockRefetch03")
		before = frappe.db.count(DOCTYPE, {"entry_type": "Payment Status Refetched"})
		admin_actions.refetch_payment_status(order.name)
		self.assertEqual(
			frappe.db.count(DOCTYPE, {"entry_type": "Payment Status Refetched"}), before + 1
		)


class TestMandateActions(AuditTestCase):
	def test_re_registration_drops_the_subscription_to_assisted_renewal(self):
		subscription = self._subscription(collection_route="Auto Debit")
		admin_actions.reregister_mandate(
			subscription.name, reason="Card expired and the bank refused the token."
		)
		subscription.reload()
		self.assertEqual(subscription.collection_route, "Assisted Renewal")
		self.assertFalse(subscription.payment_mandate)
		self.assertTrue(
			frappe.db.exists(
				DOCTYPE,
				{"entry_type": "Mandate Re-registered", "reference_name": subscription.name},
			)
		)

	def test_cancelling_for_a_customer_needs_a_reason(self):
		subscription = self._subscription()
		with self.assertRaises(frappe.ValidationError):
			admin_actions.cancel_mandate_as_operator(subscription.name, reason="no")


class TestWebhookReprocess(AuditTestCase):
	def _log(self, verified=1):
		doc = frappe.get_doc(
			{
				"doctype": "Payment Webhook Log",
				"event_id": f"evt_audit_{frappe.generate_hash(length=8)}",
				"event_type": "payment.captured",
				"gateway": "Razorpay",
				"received_on": frappe.utils.now_datetime(),
				"signature_verified": verified,
				"processing_status": "Failed",
				"raw_payload": frappe.as_json({"event": "payment.captured", "payload": {}}),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def test_an_unverified_event_is_never_reprocessed(self):
		log = self._log(verified=0)
		with self.assertRaises(frappe.ValidationError):
			admin_actions.reprocess_webhook(log.name)

	def test_a_verified_event_can_be_reprocessed_and_is_recorded(self):
		log = self._log()
		admin_actions.reprocess_webhook(log.name, reason="Handler failed on a transient error.")
		self.assertTrue(
			frappe.db.exists(
				DOCTYPE, {"entry_type": "Webhook Reprocessed", "reference_name": log.name}
			)
		)


class TestAdminActionsAreRoleGuarded(AuditTestCase):
	"""Every whitelisted action in the module must check a role before doing anything."""

	def test_no_admin_action_is_reachable_by_a_plain_user(self):
		import inspect

		user = _user_with_role("Platform Sales", "audit.sales@example.com")
		exposed = [
			name
			for name, fn in vars(admin_actions).items()
			if callable(fn) and fn in frappe.whitelisted
		]
		self.assertGreaterEqual(len(exposed), 6)
		frappe.set_user(user)
		try:
			for name in exposed:
				if name == "audit_trail":
					continue  # guarded by document permission, tested separately
				fn = getattr(admin_actions, name)
				arguments = {
					parameter: "x"
					for parameter in inspect.signature(fn).parameters
				}
				with self.assertRaises(
					(frappe.PermissionError, frappe.ValidationError),
					msg=f"{name} did not refuse a Platform Sales user",
				):
					fn(**arguments)
		finally:
			frappe.set_user("Administrator")


def _user_with_role(role, email):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": role,
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		)
		user.flags.ignore_permissions = True
		user.insert(ignore_permissions=True)
	return email
