# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Proration, plan changes, seat changes and trials.

The proration tests are worked by hand in the comments and asserted to the paisa. That is
the point of them: a proration engine that is only tested against itself will agree with
itself while being wrong, and the customer is the one who notices.

The mandate tests are the other half. Phase 5 decides how a subscription is collected by
comparing the tax-inclusive recurring amount against a registered mandate maximum and the
RBI ceiling. A plan change that crosses either and says nothing produces a declined debit
next month, which is the most damaging thing this area can ship - so both boundaries are
tested a paisa either side.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, flt, getdate, today

from a3_sola.api.lifecycle import plan_change, proration, seats
from a3_sola.api.settings import get_float
from a3_sola.tests.platform import lifecycle_fixtures as fx

PREFIX = "lcplan"


class PlanTestCase(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		fx.purge(PREFIX)
		fx.settings(**fx.INERT)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		fx.settings(**fx.INERT)
		# Starter at 3000/month, Growth at 6000/month, both with 500/seat/month.
		self.starter = fx.a_plan(f"{PREFIX} Starter", monthly=3000, annual=30000,
		                         included=5, per_seat_monthly=500, per_seat_annual=5000)
		self.growth = fx.a_plan(f"{PREFIX} Growth", monthly=6000, annual=60000,
		                        included=15, per_seat_monthly=500, per_seat_annual=5000)


class TestTheDayCountConvention(PlanTestCase):
	def test_a_period_is_inclusive_of_both_ends(self):
		# 1 September to 30 September is 30 days, not 29.
		self.assertEqual(proration.period_days("2026-09-01", "2026-09-30"), 30)

	def test_february_is_prorated_over_february(self):
		self.assertEqual(proration.period_days("2026-02-01", "2026-02-28"), 28)

	def test_a_leap_february_has_twenty_nine(self):
		self.assertEqual(proration.period_days("2028-02-01", "2028-02-29"), 29)

	def test_day_ten_of_a_thirty_day_period_has_used_nine(self):
		self.assertEqual(proration.days_used("2026-09-01", "2026-09-10"), 9)


class TestProrationByHand(PlanTestCase):
	def test_a_mid_month_upgrade_charges_the_difference_to_the_paisa(self):
		"""Worked by hand:

		    Period      1 Sep - 30 Sep, 30 days
		    Change on   day 11, so 10 used and 20 remaining
		    Starter     3000/30 = 100.00/day  ->  credit 20 x 100.00 = 2000.00
		    Growth      6000/30 = 200.00/day  ->  charge 20 x 200.00 = 4000.00
		    Net         2000.00, tax at 18% = 360.00, payable 2360.00
		"""
		sub = fx.a_subscription(f"{PREFIX}up", plan=self.starter, days_into_period=10)
		result = proration.calculate_proration(sub, "Upgrade", new_plan=self.growth)

		self.assertEqual(result["period_days"], 30)
		self.assertEqual(result["days_used"], 10)
		self.assertEqual(result["days_remaining"], 20)

		credit = _line(result, "Unused Credit")
		charge = _line(result, "New Charge")
		self.assertEqual(flt(credit["prorated_amount"], 2), -2000.00)
		self.assertEqual(flt(charge["prorated_amount"], 2), 4000.00)
		self.assertEqual(flt(result["net_before_tax"], 2), 2000.00)
		self.assertEqual(flt(result["tax"]["total_tax"], 2), 360.00)
		self.assertEqual(flt(result["net_amount_payable"], 2), 2360.00)

	def test_a_seat_added_on_day_twenty_three_costs_eight_days(self):
		"""Worked by hand:

		    Period      30 days, change on day 23, so 22 used and 8 remaining
		    Seat        500/30 = 16.666.../day  ->  8 days = 133.33 (rounded once, at the line)
		    Tax 18%     24.00     Payable 157.33
		"""
		sub = fx.a_subscription(f"{PREFIX}seat", plan=self.starter, days_into_period=22)
		result = proration.calculate_proration(sub, "Add Seats", seat_delta=1)

		self.assertEqual(result["days_remaining"], 8)
		self.assertEqual(flt(_line(result, "Seat Charge")["prorated_amount"], 2), 133.33)
		self.assertEqual(flt(result["net_amount_payable"], 2), 157.33)

	def test_two_seats_cost_exactly_twice_one(self):
		sub = fx.a_subscription(f"{PREFIX}seat2", plan=self.starter, days_into_period=22)
		one = proration.calculate_proration(sub, "Add Seats", seat_delta=1)
		two = proration.calculate_proration(sub, "Add Seats", seat_delta=2)
		self.assertEqual(flt(_line(two, "Seat Charge")["prorated_amount"], 2), 266.67)
		self.assertGreater(flt(two["net_amount_payable"]), flt(one["net_amount_payable"]))

	def test_a_downgrade_charges_nothing_and_refunds_nothing(self):
		"""The customer keeps the plan they paid for until the period ends."""
		sub = fx.a_subscription(f"{PREFIX}down", plan=self.growth, days_into_period=10)
		result = proration.calculate_proration(sub, "Downgrade", new_plan=self.starter)
		self.assertEqual(flt(result["net_amount_payable"], 2), 0.00)
		self.assertEqual(flt(result["credit_carried_forward"], 2), 0.00)

	def test_the_lines_add_up_to_the_total(self):
		"""A breakdown that does not sum to its own total is worse than no breakdown."""
		sub = fx.a_subscription(f"{PREFIX}sum", plan=self.starter, days_into_period=13)
		result = proration.calculate_proration(sub, "Upgrade", new_plan=self.growth)
		total = sum(flt(line["prorated_amount"]) for line in result["lines"])
		self.assertEqual(flt(total, 2), flt(result["net_amount_payable"], 2))

	def test_a_february_period_prorates_over_twenty_eight_days(self):
		sub = fx.a_subscription(f"{PREFIX}feb", plan=self.starter)
		sub.db_set({"current_period_start": "2026-02-01",
		            "current_period_end": "2026-02-28"}, update_modified=False)
		sub.reload()
		result = proration.calculate_proration(
			sub, "Upgrade", new_plan=self.growth, effective_date="2026-02-15")
		self.assertEqual(result["period_days"], 28)
		self.assertEqual(result["days_remaining"], 14)
		# 3000/28 = 107.142857/day; 14 days = 1500.00. Growth 6000/28 x 14 = 3000.00.
		self.assertEqual(flt(_line(result, "Unused Credit")["prorated_amount"], 2), -1500.00)
		self.assertEqual(flt(_line(result, "New Charge")["prorated_amount"], 2), 3000.00)


class TestWhenChangesTakeEffect(PlanTestCase):
	def test_an_upgrade_takes_effect_immediately(self):
		sub = fx.a_subscription(f"{PREFIX}eff1", plan=self.starter, days_into_period=10)
		name = plan_change.request_change(sub, new_plan=self.growth)
		doc = frappe.get_doc("Plan Change Request", name)
		self.assertEqual(doc.effective_type, "Immediate")
		self.assertEqual(getdate(doc.effective_date), getdate(today()))

	def test_a_downgrade_takes_effect_at_the_boundary(self):
		sub = fx.a_subscription(f"{PREFIX}eff2", plan=self.growth, days_into_period=10)
		name = plan_change.request_change(sub, new_plan=self.starter)
		doc = frappe.get_doc("Plan Change Request", name)
		self.assertEqual(doc.effective_type, "Next Period")
		self.assertEqual(getdate(doc.effective_date),
		                 getdate(add_days(sub.current_period_end, 1)))

	def test_a_change_that_changes_nothing_is_refused(self):
		sub = fx.a_subscription(f"{PREFIX}eff3", plan=self.starter)
		with self.assertRaises(frappe.ValidationError):
			plan_change.request_change(sub, new_plan=self.starter)


class TestTheMandateTrap(PlanTestCase):
	"""Both boundaries, a paisa either side. A change that silently breaks next month's
	collection is the most damaging bug in this area."""

	def test_a_new_amount_above_the_registered_maximum_is_detected(self):
		sub = fx.a_subscription(f"{PREFIX}mand", plan=self.starter)
		mandate = _a_mandate(sub, registered_max=4000)
		sub.db_set("payment_mandate", mandate, update_modified=False)
		sub.reload()

		impact, detail, _route = proration.assess_mandate_impact(sub, 5000)

		self.assertEqual(impact, "Requires New Maximum")
		self.assertIn("declined by the bank", detail)

	def test_an_amount_within_the_maximum_needs_nothing(self):
		sub = fx.a_subscription(f"{PREFIX}mand2", plan=self.starter)
		mandate = _a_mandate(sub, registered_max=8000)
		sub.db_set({"payment_mandate": mandate, "collection_route": "Auto Debit"},
		           update_modified=False)
		sub.reload()
		impact, _detail, _route = proration.assess_mandate_impact(sub, 5000)
		self.assertEqual(impact, "None")

	def test_crossing_the_afa_ceiling_forces_a_route_change(self):
		ceiling = flt(get_float("afa_free_debit_ceiling", 15000.0))
		sub = fx.a_subscription(f"{PREFIX}afa", plan=self.starter)
		sub.db_set({"collection_route": "Auto Debit",
		            "payment_mandate": _a_mandate(sub, registered_max=ceiling * 3)},
		           update_modified=False)
		sub.reload()

		impact, detail, route = proration.assess_mandate_impact(sub, ceiling + 0.01)

		self.assertEqual(impact, "Requires Route Change")
		self.assertEqual(route, "Assisted Renewal")
		self.assertIn("Assisted Renewal", detail)

	def test_exactly_at_the_ceiling_still_auto_debits(self):
		"""On the boundary, not over it. One paisa decides this."""
		ceiling = flt(get_float("afa_free_debit_ceiling", 15000.0))
		sub = fx.a_subscription(f"{PREFIX}afa2", plan=self.starter)
		sub.db_set({"collection_route": "Auto Debit",
		            "payment_mandate": _a_mandate(sub, registered_max=ceiling * 3)},
		           update_modified=False)
		sub.reload()
		_impact, _detail, route = proration.assess_mandate_impact(sub, ceiling)
		self.assertEqual(route, "Auto Debit")

	def test_an_annual_cycle_always_routes_to_assisted_renewal(self):
		sub = fx.a_subscription(f"{PREFIX}ann", plan=self.starter, cycle="Annual")
		sub.db_set("collection_route", "Auto Debit", update_modified=False)
		sub.reload()
		_impact, _detail, route = proration.assess_mandate_impact(sub, 100)
		self.assertEqual(route, "Assisted Renewal")


class TestDowngradeBlockers(PlanTestCase):
	def test_too_many_users_blocks_the_downgrade_and_names_the_number(self):
		sub = fx.a_subscription(f"{PREFIX}block", plan=self.growth)
		tenant = fx.a_tenant(f"{PREFIX}block", sub, users=3, quota=15)
		blockers = plan_change.downgrade_blockers(sub, _tiny_plan())
		self.assertTrue(blockers)
		self.assertIn("have to be disabled first", blockers[0])
		self.assertIn("you choose which", blockers[0])

	def test_nobody_is_ever_picked_algorithmically(self):
		"""The software must not choose who loses their account."""
		sub = fx.a_subscription(f"{PREFIX}pick", plan=self.growth)
		tenant = fx.a_tenant(f"{PREFIX}pick", sub, users=3, quota=15)
		enabled_before = _enabled(tenant.name)
		name = plan_change.request_change(sub, new_plan=_tiny_plan())
		doc = frappe.get_doc("Plan Change Request", name)
		self.assertEqual(doc.status, "Awaiting User Reduction")
		self.assertEqual(_enabled(tenant.name), enabled_before,
		                 "somebody was disabled without being chosen")

	def test_uncleared_blockers_at_the_boundary_keep_the_higher_plan(self):
		"""The correct failure mode is 'you keep paying more', never 'your data became
		unreachable'."""
		sub = fx.a_subscription(f"{PREFIX}defer", plan=self.growth)
		tenant = fx.a_tenant(f"{PREFIX}defer", sub, users=3, quota=15)
		name = plan_change.request_change(sub, new_plan=_tiny_plan())
		frappe.db.set_value("Plan Change Request", name, "effective_date", today(),
		                    update_modified=False)

		plan_change.apply_plan_change(name)

		self.assertEqual(
			frappe.db.get_value("Platform Subscription", sub.name, "subscription_plan"),
			self.growth, "the downgrade was applied over its blockers")
		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "access_gate"), "Full")
		self.assertNotEqual(
			frappe.db.get_value("Plan Change Request", name, "status"), "Applied")


class TestApplyingAPlanChange(PlanTestCase):
	def test_the_entitlement_snapshot_is_updated_and_enforced_at_once(self):
		"""Phase 6's rule: enforcement reads the snapshot, so the snapshot IS the change."""
		sub = fx.a_subscription(f"{PREFIX}snap", plan=self.starter)
		tenant = fx.a_tenant(f"{PREFIX}snap", sub, users=1, quota=5)
		name = plan_change.request_change(sub, new_plan=self.growth)

		plan_change.apply_plan_change(name)

		self.assertEqual(
			frappe.db.get_value("Tenant", tenant.name, "subscription_plan"), self.growth)
		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "user_quota"), 15)

	def test_applying_twice_changes_nothing_the_second_time(self):
		sub = fx.a_subscription(f"{PREFIX}idem", plan=self.starter)
		fx.a_tenant(f"{PREFIX}idem", sub, users=1)
		name = plan_change.request_change(sub, new_plan=self.growth)
		plan_change.apply_plan_change(name)
		applied_on = frappe.db.get_value("Plan Change Request", name, "applied_on")

		plan_change.apply_plan_change(name)

		self.assertEqual(frappe.db.get_value("Plan Change Request", name, "applied_on"),
		                 applied_on)

	def test_a_partly_applied_change_resumes_rather_than_restarts(self):
		sub = fx.a_subscription(f"{PREFIX}resume", plan=self.starter)
		tenant = fx.a_tenant(f"{PREFIX}resume", sub, users=1)
		name = plan_change.request_change(sub, new_plan=self.growth)
		# Step 1 done by hand, the rest not.
		frappe.db.set_value("Tenant", tenant.name, "subscription_plan", self.growth,
		                    update_modified=False)

		plan_change.apply_plan_change(name)

		self.assertEqual(frappe.db.get_value("Plan Change Request", name, "status"),
		                 "Applied")
		self.assertEqual(
			frappe.db.get_value("Platform Subscription", sub.name, "subscription_plan"),
			self.growth)

	def test_an_event_records_the_full_before_and_after(self):
		sub = fx.a_subscription(f"{PREFIX}event", plan=self.starter)
		fx.a_tenant(f"{PREFIX}event", sub, users=1)
		name = plan_change.request_change(sub, new_plan=self.growth)
		plan_change.apply_plan_change(name)

		event = frappe.db.get_value("Plan Change Request", name, "subscription_event")
		doc = frappe.get_doc("Subscription Event", event)
		self.assertEqual(doc.event_type, "Plan Upgraded")
		self.assertIn("before", doc.reason_detail)
		self.assertIn("after", doc.reason_detail)


class TestSeatSelfService(PlanTestCase):
	def test_a_trusted_tenant_gets_the_seat_at_once(self):
		sub = fx.a_subscription(f"{PREFIX}trust", plan=self.starter, days_active=400)
		tenant = fx.a_tenant(f"{PREFIX}trust", sub, users=1, quota=5)
		ok, why = seats.trusted(tenant.name)
		self.assertTrue(ok, why)

		seats.request_seats(tenant.name, 1)

		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "user_quota"), 6)

	def test_a_new_tenant_is_not_trusted(self):
		sub = fx.a_subscription(f"{PREFIX}untrust", plan=self.starter, days_active=10)
		tenant = fx.a_tenant(f"{PREFIX}untrust", sub, users=1)
		ok, why = seats.trusted(tenant.name)
		self.assertFalse(ok)
		self.assertIn("required", why)

	def test_a_tenant_with_a_failed_payment_is_not_trusted(self):
		sub = fx.a_subscription(f"{PREFIX}failed", plan=self.starter, days_active=400)
		sub.db_set("failed_payments", 2, update_modified=False)
		tenant = fx.a_tenant(f"{PREFIX}failed", sub, users=1)
		ok, why = seats.trusted(tenant.name)
		self.assertFalse(ok)
		self.assertIn("failed payments", why)

	def test_removing_seats_below_the_active_user_count_is_blocked(self):
		sub = fx.a_subscription(f"{PREFIX}rm", plan=self.starter, days_active=400)
		tenant = fx.a_tenant(f"{PREFIX}rm", sub, users=4, quota=5)
		name = seats.request_seats(tenant.name, -3)
		doc = frappe.get_doc("Seat Change Request", name)
		self.assertEqual(doc.status, "Awaiting User Reduction")
		self.assertIn("you choose which", doc.removal_blockers)

	def test_add_seats_is_the_phase_six_extension_point(self):
		from a3_sola.api import entitlements

		sub = fx.a_subscription(f"{PREFIX}ext", plan=self.starter, days_active=400)
		tenant = fx.a_tenant(f"{PREFIX}ext", sub, users=1, quota=5)
		entitlements.add_seats(tenant.name, 2)
		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "user_quota"), 7)


class TestTrials(PlanTestCase):
	def test_a_trial_starts_with_full_access_and_no_charge(self):
		from a3_sola.api.lifecycle import handlers

		plan = fx.a_plan(f"{PREFIX} Trial Plan", trial_days=14)
		sub = fx.a_subscription(f"{PREFIX}trial", plan=plan, status="Pending Payment")
		fx.settings(dry_run_mode=0)

		handlers.on_subscription_activated(sub)
		sub.reload()

		self.assertEqual(sub.status, "Trialing")
		self.assertEqual(sub.access_state, "Full")
		self.assertEqual(getdate(sub.trial_end_date), getdate(add_days(today(), 14)))

	def test_a_trial_with_no_payment_method_is_cancelled_not_suspended(self):
		"""There is nothing to suspend them over: they never owed anything."""
		from a3_sola.api.lifecycle import engine, state_machine

		plan = fx.a_plan(f"{PREFIX} Trial Plan", trial_days=14)
		sub = fx.a_subscription(f"{PREFIX}trialend", plan=plan, status="Trialing")
		sub.db_set("trial_end_date", add_days(today(), -1), update_modified=False)
		sub.reload()
		self.assertIsNone(state_machine.legal("Trialing", "Suspended"),
		                  "a trial must not be able to reach Suspended at all")
		self.assertIsNotNone(state_machine.legal("Trialing", "Cancelled"))


class TestTenantSelfService(PlanTestCase):
	"""The portal. Reading your own history is the point; an ordinary user of yours
	changing the plan is not."""

	def setUp(self):
		super().setUp()
		self.sub = fx.a_subscription(f"{PREFIX}portal", plan=self.starter, days_active=400)
		self.tenant = fx.a_tenant(f"{PREFIX}portal", self.sub, users=2, quota=5)
		# "Solar Tenant Administrator" is a Role PROFILE, not a role - passing it as a
		# role fails link validation, which is how the portal guard's own mistake was found.
		self.admin_email = fx.stamp_user(
			f"{PREFIX}.admin@lifecycle.example", self.tenant.name, first_name="TAdmin",
			roles=("Solar Sales Executive",),
		)
		frappe.db.set_value("Tenant", self.tenant.name, "admin_user", self.admin_email,
		                    update_modified=False)
		# Named, not "whichever the query returns first". An unordered pick can land on a
		# user another test promoted, and the permission assertion then passes or fails for
		# reasons that have nothing to do with the code.
		self.ordinary = fx.stamp_user(
			f"{PREFIX}.ordinary@lifecycle.example", self.tenant.name,
			first_name="Ordinary", roles=("Solar Sales Executive",),
		)
		frappe.db.set_value("User", self.ordinary, "role_profile_name", None,
		                    update_modified=False)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_an_ordinary_tenant_user_cannot_change_the_plan(self):
		from a3_sola.api import billing_portal

		frappe.set_user(self.ordinary)
		with self.assertRaises(frappe.PermissionError) as caught:
			billing_portal.change_my_plan(self.sub.name, new_plan=self.growth)
		self.assertIn("administrator", str(caught.exception).lower())

	def test_an_ordinary_tenant_user_cannot_buy_seats(self):
		from a3_sola.api import billing_portal

		frappe.set_user(self.ordinary)
		with self.assertRaises(frappe.PermissionError):
			billing_portal.change_my_seats(self.sub.name, 1)

	def test_an_ordinary_tenant_user_cannot_cancel(self):
		from a3_sola.api import billing_portal

		frappe.set_user(self.ordinary)
		with self.assertRaises(frappe.PermissionError):
			billing_portal.cancel_my_subscription(self.sub.name, "Too Expensive")

	def test_the_tenant_admin_can(self):
		from a3_sola.api import billing_portal

		frappe.set_user(self.admin_email)
		name = billing_portal.change_my_plan(self.sub.name, new_plan=self.growth)
		self.assertTrue(frappe.db.exists("Plan Change Request", name))

	def test_a_user_carrying_the_admin_role_profile_can_too(self):
		"""The second path: somebody the tenant made an administrator after provisioning."""
		from a3_sola.api import billing_portal

		profile = frappe.db.get_value("Tenant", self.tenant.name, "assigned_role_profile")
		if not profile:
			# The fixture builds a tenant directly rather than provisioning one, so give it
			# the profile a provisioned tenant would carry. Skipping instead would leave
			# the second admin path untested, which is the path a real customer uses after
			# they promote somebody.
			profile = frappe.db.get_value("Role Profile", {"name": "Solar Tenant Administrator"})
			if not profile:
				profile = frappe.db.get_value("Role Profile", {}, "name")
			self.assertTrue(profile, "no role profile exists on this site")
			frappe.db.set_value("Tenant", self.tenant.name, "assigned_role_profile", profile,
			                    update_modified=False)
		# A user of its own, not `self.ordinary`. Promoting the shared one leaks: the code
		# under test commits, so the next test finds its "ordinary" user is an
		# administrator and its permission assertion passes for the wrong reason.
		promoted = fx.stamp_user(
			f"{PREFIX}.promoted@lifecycle.example", self.tenant.name,
			first_name="Promoted", roles=("Solar Sales Executive",),
		)
		frappe.db.set_value("User", promoted, "role_profile_name", profile,
		                    update_modified=False)
		frappe.set_user(promoted)
		self.assertEqual(billing_portal._assert_tenant_admin(self.sub.name), self.tenant.name)

	def test_the_proration_preview_is_available_before_committing(self):
		from a3_sola.api import billing_portal

		frappe.set_user(self.ordinary)
		quote = billing_portal.preview_plan_change(self.sub.name, new_plan=self.growth)
		self.assertIn("net_amount_payable", quote)
		self.assertIn("mandate_impact", quote)

	def test_the_history_is_readable_and_carries_no_internal_detail(self):
		from a3_sola.api import billing_portal
		from a3_sola.api.lifecycle import events

		events.record(self.sub, "Policy Evaluated", "internal noise",
		              triggered_by="Scheduler", was_dry_run=1)
		events.record(self.sub, "Renewed", "Your subscription renewed.",
		              triggered_by="Webhook")

		frappe.set_user(self.ordinary)
		history = billing_portal.my_history(self.sub.name)

		self.assertTrue(history)
		for row in history:
			self.assertEqual(set(row), {"when", "what", "why"})
			self.assertNotEqual(row["what"], "Policy Evaluated")

	def test_a_customer_cannot_read_another_customers_subscription(self):
		from a3_sola.api import billing_portal

		other = fx.a_subscription(f"{PREFIX}other", plan=self.starter)
		frappe.set_user(self.ordinary)
		with self.assertRaises(frappe.DoesNotExistError):
			billing_portal.my_plan(other.name)

	def test_the_team_list_carries_last_activity_for_a_downgrade_decision(self):
		from a3_sola.api import billing_portal

		frappe.set_user(self.ordinary)
		team = billing_portal.my_team(self.sub.name)
		self.assertTrue(team)
		for row in team:
			self.assertIn("last_active", row)
			self.assertIn("enabled", row)


def _line(result, line_type):
	for line in result["lines"]:
		if line["line_type"] == line_type:
			return line
	raise AssertionError(f"no {line_type} line in {[l['line_type'] for l in result['lines']]}")


def _a_mandate(subscription, registered_max):
	doc = frappe.get_doc({
		"doctype": "Payment Mandate",
		"platform_subscription": subscription.name,
		"customer_name": subscription.organisation_name,
		"customer_email": subscription.primary_contact_email,
		"mandate_type": "Card e-Mandate",
		"recurring_debit_amount": flt(subscription.recurring_amount),
		"registered_max_amount": flt(registered_max),
		"registered_on": today(),
		"valid_until": add_months(today(), 24),
	})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _tiny_plan():
	return fx.a_plan(f"{PREFIX} Tiny", monthly=1000, annual=10000, included=2,
	                 per_seat_monthly=500, per_seat_annual=5000)


def _enabled(tenant):
	from a3_sola.api.entitlements import TENANT_FIELD

	return {
		row["name"]: row["enabled"]
		for row in frappe.get_all("User", filters={TENANT_FIELD: tenant},
		                          fields=["name", "enabled"])
	}
