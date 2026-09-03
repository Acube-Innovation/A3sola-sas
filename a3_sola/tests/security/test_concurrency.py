# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The two races that would cost real money, run as real races.

Both were designed against in earlier phases - Phase 5 gives a Payment Order a
deterministic idempotency key, Phase 6 takes a redis lock before provisioning. Neither was
ever tested with two things actually happening at once, and a sequential call proves
nothing about a lock: calling a function twice in a row exercises the "already done" branch,
not the "two workers arrived together" one.

Each test below uses a barrier so the threads genuinely collide, and asserts on the count
of side effects rather than on the absence of an exception.

Every thread opens its own database connection with `frappe.init` / `frappe.connect`,
because Frappe's connection is thread-local and sharing one produces interleaved
transactions that fail for reasons unrelated to the thing being tested.
"""

import threading

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

CONCURRENCY = 8


def _in_its_own_connection(site, barrier, results, index, work):
	"""Run `work` on a fresh connection, released at the same instant as the others."""
	frappe.init(site=site)
	frappe.connect()
	try:
		frappe.set_user("Administrator")
		barrier.wait(timeout=30)
		results[index] = ("ok", work())
	except Exception as exception:
		results[index] = ("error", f"{type(exception).__name__}: {str(exception)[:160]}")
	finally:
		try:
			frappe.db.commit()
		except Exception:
			pass
		frappe.destroy()


def race(work, threads=CONCURRENCY):
	"""Run `work` on `threads` connections that all start together."""
	site = frappe.local.site
	barrier = threading.Barrier(threads)
	results = [None] * threads
	workers = [
		threading.Thread(target=_in_its_own_connection,
		                 args=(site, barrier, results, index, work))
		for index in range(threads)
	]
	frappe.db.commit()  # the fixture must be visible to the other connections
	for worker in workers:
		worker.start()
	for worker in workers:
		worker.join(timeout=60)
	return results


class TestConcurrentWebhooks(FrappeTestCase):
	"""Phase 5's hazard: the gateway delivers the same event several times at once.

	Razorpay retries, and a retry can overlap the original. If two deliveries both create
	a Payment Transaction, the customer is recorded as having paid twice and the
	reconciliation never balances.
	"""

	def setUp(self):
		frappe.set_user("Administrator")
		self.subscription = self._subscription()
		frappe.db.commit()

	def tearDown(self):
		frappe.set_user("Administrator")
		self._purge()

	def _subscription(self):
		existing = frappe.db.get_value("Platform Subscription",
		                               {"organisation_name": "Race Test Solar"}, "name")
		if existing:
			return existing
		plan = frappe.db.get_value("Subscription Plan", {"is_active": 1}, "name")
		doc = frappe.get_doc({
			"doctype": "Platform Subscription",
			"organisation_name": "Race Test Solar",
			"primary_contact_email": "race@concurrency.example",
			"subscription_plan": plan, "billing_cycle": "Monthly",
			"included_users": 5, "subtotal": 3000, "tax_amount": 540, "currency": "INR",
			"state_code": "32", "start_date": today(),
			"current_period_start": today(), "current_period_end": add_days(today(), 29),
			"next_billing_date": add_days(today(), 30),
		})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		doc.db_set({"status": "Active", "recurring_amount": 3540}, update_modified=False)
		return doc.name

	def _purge(self):
		for name in frappe.get_all("Payment Order",
		                           filters={"platform_subscription": self.subscription},
		                           pluck="name"):
			frappe.db.set_value("Payment Order", name, "docstatus", 2, update_modified=False)
			frappe.delete_doc("Payment Order", name, force=True, ignore_permissions=True,
			                  ignore_on_trash=True)
		for name in frappe.get_all("Platform Subscription",
		                           filters={"organisation_name": "Race Test Solar"},
		                           pluck="name"):
			frappe.db.set_value("Platform Subscription", name, "docstatus", 2,
			                    update_modified=False)
			frappe.delete_doc("Platform Subscription", name, force=True,
			                  ignore_permissions=True, ignore_on_trash=True)
		frappe.db.commit()

	def test_eight_simultaneous_orders_for_one_period_produce_exactly_one(self):
		"""Phase 5's idempotency key, under an actual race.

		The key is derived from the subscription and the period, so two workers computing
		it get the same string - but only a unique constraint makes that decisive when
		both look, both find nothing, and both insert.
		"""
		subscription = self.subscription

		def work():
			from a3_sola.api import payments

			doc = frappe.get_doc("Platform Subscription", subscription)
			key = payments.idempotency_key(
				"Platform Subscription", subscription, "Renewal", str(doc.current_period_start))
			existing = frappe.db.get_value("Payment Order", {"idempotency_key": key}, "name")
			if existing:
				return existing
			order = frappe.get_doc({
				"doctype": "Payment Order",
				"reference_doctype": "Platform Subscription",
				"reference_name": subscription,
				"platform_subscription": subscription,
				"customer_name": doc.organisation_name,
				"customer_email": doc.primary_contact_email,
				"order_type": "Renewal", "billing_cycle": "Monthly",
				"subtotal": 3000, "tax_amount": 540, "total_amount": 3540,
				"currency": "INR", "idempotency_key": key,
			})
			order.flags.ignore_permissions = True
			order.flags.ignore_mandatory = True
			order.insert(ignore_permissions=True)
			return order.name

		results = race(work)

		# What matters is the count of ORDERS, not how many threads raised.
		orders = frappe.get_all("Payment Order",
		                        filters={"platform_subscription": subscription},
		                        pluck="name")
		self.assertEqual(
			len(orders), 1,
			f"{CONCURRENCY} simultaneous renewals produced {len(orders)} orders - the "
			f"customer would be charged {len(orders)} times. Results: {results}",
		)

	def test_the_idempotency_key_is_unique_in_the_database(self):
		"""The property the race depends on. Without a unique index the check-then-insert
		above is a race whatever the application code does."""
		meta = frappe.get_meta("Payment Order")
		field = meta.get_field("idempotency_key")
		self.assertTrue(field, "Payment Order has no idempotency key")
		indexes = frappe.db.sql(
			"show index from `tabPayment Order` where Column_name = 'idempotency_key'",
			as_dict=True,
		)
		unique = [i for i in indexes if str(i.get("Non_unique")) == "0"]
		self.assertTrue(
			unique or field.unique,
			"idempotency_key is not unique in the database, so two simultaneous "
			"webhooks can both insert an order for the same period",
		)


class TestConcurrentProvisioning(FrappeTestCase):
	"""Phase 6's hazard: two triggers for one subscription.

	A payment webhook and a manual retry arriving together must not build two companies.
	Phase 6 takes a redis lock with SET NX for exactly this; the lock has never been
	tested with contention.
	"""

	def test_the_provisioning_lock_admits_exactly_one_holder(self):
		from a3_sola.api.provisioning import orchestrator

		reference = f"race-{frappe.generate_hash(length=8)}"
		acquired = []
		lock = threading.Lock()

		def work():
			# It is a context manager, and __enter__ returns whether the lock was taken.
			# Held for a moment so the other threads are genuinely contending rather than
			# arriving after it has already been released.
			import time

			with orchestrator._subscription_lock(reference) as got:
				if got:
					with lock:
						acquired.append(frappe.generate_hash(length=4))
					time.sleep(0.25)
				return bool(got)

		race(work)
		self.assertEqual(
			len(acquired), 1,
			f"{CONCURRENCY} threads raced for one subscription lock and {len(acquired)} "
			f"got it - two of them would provision two companies for one customer",
		)
