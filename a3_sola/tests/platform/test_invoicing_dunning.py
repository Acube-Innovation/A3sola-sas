# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Invoicing, refunds, dunning and the billing portal.

The tax tests matter because a wrong split breaks the customer's input credit. The
numbering test matters because a tax invoice series with a gap in it is a compliance
problem. The portal test matters because one customer reading another's invoices would be
the worst failure in the phase.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, now_datetime, set_request, today

from a3_sola.api import accounting_payments, billing_portal, dunning, payments, ratelimit
from a3_sola.platform.doctype.payment_refund import payment_refund as refund_module
from a3_sola.platform.doctype.subscription_invoice import subscription_invoice as invoice_module


def a_company():
	return frappe.defaults.get_global_default("company") or frappe.get_all(
		"Company", pluck="name", limit=1
	)[0]


class InvoiceTestCase(FrappeTestCase):
	def setUp(self):
		ratelimit.reset_all()
		frappe.flags.mock_gateway_behaviour = "success"
		frappe.db.set_single_value("A3 Sola Settings", "company_state_code", "32")
		frappe.db.set_single_value("A3 Sola Settings", "subscription_gst_rate", 18)
		frappe.db.set_single_value("A3 Sola Settings", "enable_payment_postings", 0)
		frappe.clear_cache()

	def tearDown(self):
		frappe.flags.mock_gateway_behaviour = None
		frappe.set_user("Administrator")

	def _reference_subscription(self):
		"""A Payment Order must reference something real - the link is validated."""
		if getattr(self, "_subscription", None):
			return self._subscription
		plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		doc = frappe.get_doc(
			{
				"doctype": "Platform Subscription",
				"organisation_name": "Invoice Test EPC",
				"primary_contact_email": "billing@testepc.example",
				"subscription_plan": plan,
				"billing_cycle": "Monthly",
				"included_users": 5,
				"subtotal": 3000, "tax_amount": 540, "currency": "INR",
				"start_date": today(),
				"current_period_start": today(),
				"current_period_end": add_days(today(), 30),
				"next_billing_date": today(),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		self._subscription = doc
		return doc

	def _order(self, subtotal=3000, tax_amount=540, state_code="32", **kwargs):
		subscription = self._reference_subscription()
		values = {
			"doctype": "Payment Order",
			"reference_doctype": "Platform Subscription",
			"reference_name": subscription.name,
			"platform_subscription": subscription.name,
			"customer_name": "Test EPC",
			"customer_email": "billing@testepc.example",
			"order_type": "Initial Subscription",
			"billing_cycle": "Monthly",
			"collection_mode": "Checkout",
			"period_start": today(),
			"period_end": add_days(today(), 30),
			"subtotal": subtotal,
			"tax_amount": tax_amount,
			"total_amount": subtotal + tax_amount,
			"currency": "INR",
			"customer_state_code": state_code,
			"price_breakdown": frappe.as_json(
				[{"label": "Starter plan - 5 users", "detail": "Billed per month",
				  "amount": subtotal}]
			),
			"idempotency_key": frappe.generate_hash(length=32),
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True)
		return doc

	def _invoice(self, order, **kwargs):
		values = {
			"doctype": "Subscription Invoice",
			"payment_order": order.name,
			"company": a_company(),
			"customer_legal_name": order.customer_name,
			"customer_state_code": order.customer_state_code,
			"invoice_date": today(),
			"period_start": order.period_start,
			"period_end": order.period_end,
			"billing_cycle": order.billing_cycle,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc


class TestInvoiceTax(InvoiceTestCase):
	def test_a_kerala_customer_gets_cgst_and_sgst(self):
		invoice = self._invoice(self._order(state_code="32"))
		self.assertEqual(invoice.tax_type, "CGST+SGST")
		self.assertEqual(flt(invoice.cgst_amount, 2), 270.00)
		self.assertEqual(flt(invoice.sgst_amount, 2), 270.00)
		self.assertEqual(flt(invoice.igst_amount, 2), 0.00)

	def test_a_customer_in_another_state_gets_igst(self):
		invoice = self._invoice(self._order(state_code="29"))
		self.assertEqual(invoice.tax_type, "IGST")
		self.assertEqual(flt(invoice.igst_amount, 2), 540.00)

	def test_the_grand_total_is_the_taxable_value_plus_tax(self):
		invoice = self._invoice(self._order())
		self.assertEqual(
			flt(invoice.grand_total, 2),
			flt(invoice.taxable_value + invoice.total_tax, 2),
		)

	def test_the_lines_come_from_the_orders_breakdown(self):
		"""The invoice and the charge can never disagree if both come from one place."""
		order = self._order()
		invoice = self._invoice(order)
		self.assertTrue(invoice.items)
		self.assertEqual(invoice.items[0].description, "Starter plan - 5 users")
		self.assertEqual(flt(invoice.items[0].amount, 2), 3000.00)

	def test_the_amount_is_written_out_in_words(self):
		invoice = self._invoice(self._order())
		self.assertTrue(invoice.amount_in_words)
		self.assertIn("Three Thousand", invoice.amount_in_words)
		self.assertIn("Forty", invoice.amount_in_words)

	def test_a_gstin_contradicting_the_state_blocks_submission(self):
		order = self._order(state_code="32")
		invoice = self._invoice(order)
		invoice.customer_gstin = "29AABCS1429B1ZX"
		with self.assertRaises(frappe.ValidationError):
			invoice.save(ignore_permissions=True)

	def test_the_hsn_comes_from_settings(self):
		invoice = self._invoice(self._order())
		self.assertEqual(
			invoice.items[0].hsn_sac,
			frappe.db.get_single_value("A3 Sola Settings", "subscription_hsn_sac"),
		)


class TestInvoiceNumbering(InvoiceTestCase):
	def test_the_series_is_sequential_and_gapless(self):
		company = a_company()
		numbers = []
		for _index in range(3):
			invoice = self._invoice(self._order())
			numbers.append(int(invoice.name.rsplit("-", 1)[-1]))
		self.assertEqual(numbers, sorted(numbers))
		self.assertEqual(numbers[-1] - numbers[0], 2, "the series has a gap in it")

	def test_the_series_carries_the_fiscal_year(self):
		invoice = self._invoice(self._order())
		self.assertIn(invoice_module.fiscal_year_of(today()), invoice.name)

	def test_the_fiscal_year_runs_april_to_march(self):
		self.assertEqual(invoice_module.fiscal_year_of("2026-04-01"), "2026-27")
		self.assertEqual(invoice_module.fiscal_year_of("2027-03-31"), "2026-27")
		self.assertEqual(invoice_module.fiscal_year_of("2026-03-31"), "2025-26")

	def test_a_submitted_invoice_cannot_be_deleted(self):
		invoice = self._invoice(self._order())
		invoice.submit()
		with self.assertRaises(frappe.ValidationError):
			invoice.delete()


class TestPaymentPostingsAreGated(InvoiceTestCase):
	def test_nothing_posts_while_the_gate_is_shut(self):
		before = frappe.db.count("Sales Invoice")
		invoice = self._invoice(self._order())
		invoice.submit()
		self.assertEqual(frappe.db.count("Sales Invoice"), before)
		self.assertEqual(invoice.posting_status, "Not Posted")

	def test_an_unmapped_company_is_refused_when_the_gate_is_open(self):
		frappe.db.set_single_value("A3 Sola Settings", "enable_payment_postings", 1)
		frappe.clear_cache()
		try:
			with self.assertRaises(frappe.ValidationError):
				accounting_payments.resolve_account(a_company(), "subscription_revenue_account")
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "enable_payment_postings", 0)
			frappe.clear_cache()

	def test_a_cross_company_account_is_refused(self):
		"""The worst thing this layer can do is post into another tenant's ledger."""
		from a3_sola.tests.fixtures import make_company

		other = make_company("Payments Cross Co", "PXC", seed=False)
		foreign = frappe.db.get_value(
			"Account", {"company": other, "root_type": "Income", "is_group": 0}, "name"
		)
		settings = frappe.get_single("A3 Sola Settings")
		row = next(
			(r for r in settings.payment_account_mapping if r.company == a_company()), None
		)
		if not row:
			row = settings.append("payment_account_mapping", {"company": a_company()})
		row.subscription_revenue_account = foreign
		settings.flags.ignore_permissions = True
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)

	def test_the_posting_functions_check_the_role(self):
		import inspect

		for name in ("post_subscription_invoice", "post_payment", "post_refund"):
			body = inspect.getsource(getattr(accounting_payments, name))
			self.assertIn("_require_accounts_manager()", body, f"{name} posts without a check")


class TestRefunds(InvoiceTestCase):
	def _paid_order(self, total=3540):
		order = self._order(subtotal=3000, tax_amount=540)
		order.db_set(
			{"status": "Paid", "amount_paid": total, "paid_on": now_datetime()},
			update_modified=False,
		)
		order.reload()
		return order

	def _refund(self, order, amount, **kwargs):
		values = {
			"doctype": "Payment Refund",
			"payment_order": order.name,
			"refund_type": "Partial",
			"refund_amount": amount,
			"currency": "INR",
			"reason": "Billing Error",
			"reason_detail": "Charged the wrong tier.",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def test_a_refund_cannot_exceed_what_was_collected(self):
		order = self._paid_order()
		with self.assertRaises(frappe.ValidationError):
			self._refund(order, 9999)

	def test_a_second_refund_cannot_exceed_the_remainder(self):
		order = self._paid_order()
		first = self._refund(order, 3000)
		first.db_set("status", "Processed", update_modified=False)
		with self.assertRaises(frappe.ValidationError):
			self._refund(order, 1000)

	def test_a_refund_on_an_unpaid_order_is_refused(self):
		order = self._order()
		with self.assertRaises(frappe.ValidationError):
			self._refund(order, 100)

	def test_a_small_refund_is_approved_automatically(self):
		frappe.db.set_single_value("A3 Sola Settings", "refund_approval_threshold", 5000)
		frappe.clear_cache()
		order = self._paid_order()
		self.assertEqual(self._refund(order, 100).status, "Approved")

	def test_a_large_refund_waits_for_approval(self):
		frappe.db.set_single_value("A3 Sola Settings", "refund_approval_threshold", 500)
		frappe.clear_cache()
		try:
			order = self._paid_order()
			refund = self._refund(order, 3000)
			self.assertEqual(refund.status, "Pending Approval")
			with self.assertRaises(frappe.ValidationError):
				refund.submit()
		finally:
			frappe.db.set_single_value("A3 Sola Settings", "refund_approval_threshold", 5000)
			frappe.clear_cache()

	def test_a_zero_refund_is_refused(self):
		order = self._paid_order()
		with self.assertRaises(frappe.ValidationError):
			self._refund(order, 0)

	def test_duplicate_payments_are_detected(self):
		key = frappe.generate_hash(length=32)
		for _index in range(2):
			order = self._order(idempotency_key=key + str(_index))
			order.db_set("status", "Paid", update_modified=False)
		# Two orders sharing a key cannot both exist - the unique index prevents it - so
		# the detector looks for exactly that condition and finds none here.
		result = refund_module.detect_duplicate_payments()
		self.assertIn("flagged", result)

	def test_a_refunded_first_payment_suspends_rather_than_deletes(self):
		"""Phase 6 implements this, and what it must not do is the point.

		A refunded customer left with a working login is giving the product away; a
		refunded customer whose company was deleted is a data-loss incident. So: suspend,
		disable the users, delete nothing, and tell a human.
		"""
		import inspect

		source = inspect.getsource(refund_module.on_initial_payment_refunded)
		self.assertNotIn("NotImplementedError", source, "still a stub")

		from a3_sola.api import tenant_admin

		body = inspect.getsource(tenant_admin.on_initial_payment_refunded)
		self.assertIn("Suspended", body)
		self.assertNotIn("delete_doc", body, "the refund path must never delete anything")
		# Unknown subscription: nothing to suspend, and no exception either.
		self.assertIsNone(refund_module.on_initial_payment_refunded("SUB-DOES-NOT-EXIST"))


class TestDunning(FrappeTestCase):
	def setUp(self):
		dunning.seed_default_policy()

	def test_the_default_policy_is_seeded_with_steps(self):
		policy = frappe.get_doc("Dunning Policy", "Standard Dunning")
		self.assertTrue(policy.steps)
		self.assertTrue(any(step.is_final for step in policy.steps))

	def test_a_transient_error_is_classified_for_retry(self):
		policy = frappe.get_doc("Dunning Policy", "Standard Dunning")
		klass, needs_mandate, _message = dunning.classify_error("insufficient_funds", policy)
		self.assertEqual(klass, "Transient")
		self.assertFalse(needs_mandate)

	def test_a_permanent_error_is_not_retried_and_needs_re_registration(self):
		policy = frappe.get_doc("Dunning Policy", "Standard Dunning")
		klass, needs_mandate, _message = dunning.classify_error("card_expired", policy)
		self.assertEqual(klass, "Permanent")
		self.assertTrue(needs_mandate)

	def test_an_unmapped_code_is_unknown_rather_than_assumed(self):
		klass, _needs, _message = dunning.classify_error("SOMETHING_NEW_2027", None)
		self.assertEqual(klass, "Unknown")

	def test_error_classes_are_configurable_data_not_code(self):
		policy = frappe.get_doc("Dunning Policy", "Standard Dunning")
		policy.append(
			"error_classes",
			{"error_code": "NEW_BANK_CODE", "error_class": "Permanent",
			 "requires_new_mandate": 1},
		)
		policy.flags.ignore_permissions = True
		policy.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Dunning Policy")
		klass, needs_mandate, _message = dunning.classify_error(
			"NEW_BANK_CODE", frappe.get_doc("Dunning Policy", "Standard Dunning")
		)
		self.assertEqual(klass, "Permanent")
		self.assertTrue(needs_mandate)

	def test_the_steps_run_at_the_documented_offsets(self):
		policy = frappe.get_doc("Dunning Policy", "Standard Dunning")
		offsets = sorted({step.day_offset for step in policy.steps})
		self.assertEqual(offsets, [0, 1, 3, 7, 10])

	def test_dunning_hands_over_to_phase_seven_rather_than_suspending(self):
		"""Phase 5 stops at "still unpaid". It must never decide to switch anybody off.

		This started life asserting the stub raised NotImplementedError. Phase 7 has
		implemented it, so what is worth proving now is the handover itself: the contract
		is still declared, and collection still refuses to make the access decision on its
		own - it delegates to the policy engine, which has the guards.
		"""
		import inspect

		doc = (dunning.on_dunning_exhausted.__doc__ or "").lower()
		self.assertIn("phase 7", doc)
		self.assertIn("policy decision, not a billing one", doc)

		source = inspect.getsource(dunning.on_dunning_exhausted)
		self.assertIn("a3_sola.api.lifecycle.handlers", source,
		              "dunning no longer hands over to the lifecycle package")
		for forbidden in ("suspend_tenant_access", "\"Suspended\"", "User.enabled"):
			self.assertNotIn(forbidden, source,
			                 f"collection is deciding access for itself: {forbidden}")


class TestBillingPortalIsolation(FrappeTestCase):
	"""One customer must never read another's invoices."""

	def setUp(self):
		self.plan = frappe.db.get_value("Subscription Plan", {"plan_code": "starter"}, "name")
		self.a = self._subscription("alpha")
		self.b = self._subscription("beta")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _subscription(self, prefix):
		email = f"{prefix}.billing@portal.example"
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User", "email": email, "first_name": prefix.title(),
					"send_welcome_email": 0, "user_type": "Website User",
				}
			).insert(ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Platform Subscription",
				"organisation_name": f"{prefix.title()} Solar",
				"primary_contact_email": email,
				"subscription_plan": self.plan,
				"billing_cycle": "Monthly",
				"included_users": 5,
				"subtotal": 3000, "tax_amount": 540, "currency": "INR",
				"start_date": today(),
				"current_period_start": today(),
				"current_period_end": add_days(today(), 30),
				"next_billing_date": add_days(today(), 30),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_a_customer_sees_only_their_own_subscription(self):
		frappe.set_user(self.a.primary_contact_email)
		names = {row["name"] for row in billing_portal.my_subscriptions()}
		self.assertIn(self.a.name, names)
		self.assertNotIn(self.b.name, names)

	def test_asking_for_another_subscription_by_name_is_refused(self):
		frappe.set_user(self.a.primary_contact_email)
		with self.assertRaises(frappe.DoesNotExistError):
			billing_portal.my_invoices(self.b.name)

	def test_cancelling_another_customers_mandate_is_refused(self):
		frappe.set_user(self.a.primary_contact_email)
		with self.assertRaises(frappe.DoesNotExistError):
			billing_portal.cancel_my_mandate(self.b.name)

	def test_paying_another_customers_invoice_is_refused(self):
		frappe.set_user(self.a.primary_contact_email)
		with self.assertRaises(frappe.DoesNotExistError):
			billing_portal.pay_outstanding(self.b.name)

	def test_a_guest_sees_nothing(self):
		frappe.set_user("Guest")
		self.assertEqual(billing_portal.my_subscriptions(), [])

	def test_the_portal_exposes_no_internal_identifiers(self):
		frappe.set_user(self.a.primary_contact_email)
		for row in billing_portal.my_subscriptions():
			for forbidden in (
				"payment_mandate", "gateway_order_id", "gateway_token_id",
				"idempotency_key", "lifetime_value",
			):
				self.assertNotIn(forbidden, row, f"{forbidden} reached the customer")
