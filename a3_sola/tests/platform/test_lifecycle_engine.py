# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The policy engine, the state machine and the nightly run.

These test the things that are expensive when they are wrong rather than the happy path:
that an illegal move is refused, that the log cannot be edited, that the shipped settings
really do change nothing, and that every guard between "this customer is overdue" and
"this customer is switched off" actually holds.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from a3_sola.api.lifecycle import engine, events, policy, state_machine
from a3_sola.api.settings import get_value
from a3_sola.tests.platform import lifecycle_fixtures as fx

PREFIX = "lcengine"


class LifecycleTestCase(FrappeTestCase):
	"""Phase 7 commits - the engine commits after every subscription, deliberately, so one
	failure cannot roll back a night's work. `FrappeTestCase`'s transaction rollback
	therefore undoes none of it, and the suite has to clean up after itself."""

	@classmethod
	def tearDownClass(cls):
		fx.purge(PREFIX)
		fx.settings(**fx.INERT)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		fx.settings(**fx.INERT)
		self.plan = fx.a_plan()


class TestPlatformRegistry(FrappeTestCase):
	"""Every Platform doctype is declared in the registry.

	The three solar modules each have this guard; Platform did not, and Phase 7 is what
	made the absence matter - it added nine doctypes, and an undeclared one silently
	misses the permission hooks, the fixtures and the guest allowlist test that walks the
	registry. Written to cover the whole module rather than only Phase 7, because the next
	phase will add more.
	"""

	def test_every_platform_doctype_is_registered(self):
		from a3_sola.registry import platform as registry

		on_disk = set(frappe.get_all("DocType", filters={"module": "Platform"}, pluck="name"))
		declared = set(registry.DOCTYPES)
		self.assertEqual(
			sorted(on_disk - declared), [],
			"doctypes exist in the Platform module that the registry does not declare",
		)

	def test_the_registry_declares_nothing_that_does_not_exist(self):
		from a3_sola.registry import platform as registry

		missing = [d for d in registry.DOCTYPES if not frappe.db.exists("DocType", d)]
		self.assertEqual(missing, [], f"the registry names doctypes that are not there: {missing}")

	def test_every_phase_seven_doctype_is_in_the_lifecycle_group(self):
		from a3_sola.registry import platform as registry

		for doctype in (
			"Subscription Policy", "Policy Stage", "Subscription Event",
			"Access Suspension", "Suspended User Snapshot", "Plan Change Request",
			"Proration Line", "Seat Change Request", "Cancellation Request",
		):
			self.assertIn(doctype, registry.LIFECYCLE_DOCTYPES)

	def test_guest_holds_no_permission_on_any_lifecycle_doctype(self):
		"""A Subscription Event readable by a logged-out visitor would publish which
		customers are behind on payment; an Access Suspension would publish their staff."""
		from a3_sola.registry import platform as registry

		exposed = []
		for doctype in registry.LIFECYCLE_DOCTYPES:
			for perm in frappe.get_meta(doctype).permissions:
				if perm.role == "Guest":
					exposed.append(doctype)
		self.assertEqual(exposed, [], f"guest can reach {exposed}")


class TestTransitionTable(LifecycleTestCase):
	def test_active_cannot_jump_straight_to_suspended(self):
		"""The move that must never exist. A customer reaches Suspended through the policy
		stages, having been warned at each - or not at all."""
		sub = fx.a_subscription(f"{PREFIX}jump")
		with self.assertRaises(frappe.ValidationError) as caught:
			state_machine.transition(sub, "Suspended", "because", "Scheduler")
		message = str(caught.exception)
		self.assertIn("Active", message)
		self.assertIn("Suspended", message)

	def test_the_error_names_the_legal_moves(self):
		sub = fx.a_subscription(f"{PREFIX}legal")
		with self.assertRaises(frappe.ValidationError) as caught:
			state_machine.transition(sub, "Terminated", "because", "Scheduler")
		self.assertIn("Past Due", str(caught.exception))

	def test_a_transition_needs_a_reason(self):
		sub = fx.a_subscription(f"{PREFIX}reason")
		with self.assertRaises(frappe.ValidationError):
			state_machine.transition(sub, "Past Due", "   ", "Scheduler")

	def test_a_scheduler_may_never_force(self):
		"""Forcing is a person taking responsibility for leaving the state machine."""
		sub = fx.a_subscription(f"{PREFIX}force")
		with self.assertRaises(frappe.ValidationError) as caught:
			state_machine.transition(sub, "Terminated", "because", "Scheduler", force=True)
		self.assertIn("scheduler", str(caught.exception).lower())

	def test_asking_for_the_state_it_is_already_in_does_nothing(self):
		"""The nightly job asks for this every night for as long as a state lasts."""
		sub = fx.a_subscription(f"{PREFIX}same")
		self.assertIsNone(state_machine.transition(sub, "Active", "no change", "Scheduler"))

	def test_restoration_is_legal_from_every_restricted_state(self):
		for state in ("Past Due", "Grace", "Suspended"):
			self.assertIsNotNone(
				state_machine.legal(state, "Active"),
				f"a customer in {state} who pays must be able to reach Active",
			)


class TestEventLogIsImmutable(LifecycleTestCase):
	def test_an_event_cannot_be_updated_even_by_system_manager(self):
		sub = fx.a_subscription(f"{PREFIX}imm")
		event = events.record(sub, "Policy Evaluated", "first write", triggered_by="Scheduler")
		frappe.set_user("Administrator")
		doc = frappe.get_doc("Subscription Event", event.name)
		doc.reason = "rewritten"
		with self.assertRaises(frappe.ValidationError) as caught:
			doc.save(ignore_permissions=True)
		self.assertIn("cannot be changed", str(caught.exception))

	def test_an_event_cannot_be_deleted(self):
		sub = fx.a_subscription(f"{PREFIX}del")
		event = events.record(sub, "Policy Evaluated", "written", triggered_by="Scheduler")
		with self.assertRaises(frappe.ValidationError) as caught:
			frappe.delete_doc("Subscription Event", event.name, ignore_permissions=True)
		self.assertIn("cannot be deleted", str(caught.exception))

	def test_no_role_holds_write_or_delete_on_the_event(self):
		"""Belt and braces: the controller refuses anyway, but the permission grid should
		say so too, so nobody has to read the controller to find out."""
		meta = frappe.get_meta("Subscription Event")
		for perm in meta.permissions:
			self.assertFalse(perm.write, f"{perm.role} has write on Subscription Event")
			self.assertFalse(perm.delete, f"{perm.role} has delete on Subscription Event")


class TestShippedDefaultsChangeNothing(LifecycleTestCase):
	def test_dry_run_computes_and_logs_but_touches_no_access(self):
		sub = fx.a_subscription(f"{PREFIX}dry", status="Grace", overdue_days=20)
		fx.overdue_invoice(sub, days=20)
		tenant = fx.a_tenant(f"{PREFIX}dry", sub)
		before = _enabled_map(tenant.name)
		fx.settings(dry_run_mode=1, enable_automatic_suspension=1,
		            require_manual_approval_for_suspension=0)

		summary = engine.run_lifecycle()

		self.assertTrue(summary["dry_run"])
		self.assertEqual(_enabled_map(tenant.name), before,
		                 "dry run disabled somebody")
		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "access_gate"), "Full")
		self.assertTrue(
			frappe.db.count("Subscription Event", {"platform_subscription": sub.name}),
			"dry run must still write down what it decided",
		)

	def test_the_kill_switch_halts_every_state_change(self):
		sub = fx.a_subscription(f"{PREFIX}kill", status="Grace", overdue_days=20)
		fx.overdue_invoice(sub, days=20)
		fx.settings(**fx.LIVE)
		fx.settings(lifecycle_kill_switch=1)
		summary = engine.run_lifecycle()
		self.assertTrue(summary["halted"])
		self.assertEqual(summary["halt_reason"], "kill switch")
		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Grace")

	def test_automatic_suspension_off_still_evaluates_and_logs(self):
		sub = fx.a_subscription(f"{PREFIX}off", status="Grace", overdue_days=20)
		fx.overdue_invoice(sub, days=20)
		tenant = fx.a_tenant(f"{PREFIX}off", sub)
		fx.settings(dry_run_mode=0, enable_automatic_suspension=0,
		            require_manual_approval_for_suspension=0)

		engine.run_lifecycle()

		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "access_gate"), "Full")
		reasons = frappe.get_all(
			"Subscription Event", filters={"platform_subscription": sub.name},
			pluck="reason",
		)
		self.assertTrue(any("switched off" in r for r in reasons),
		                f"the decision was not recorded: {reasons}")


class TestGuards(LifecycleTestCase):
	def test_a_brand_new_tenant_is_protected_from_a_first_payment_hiccup(self):
		sub = fx.a_subscription(f"{PREFIX}new", status="Grace", overdue_days=20,
		                        days_active=3)
		fx.overdue_invoice(sub, days=20)
		tenant = fx.a_tenant(f"{PREFIX}new", sub)
		fx.settings(**fx.LIVE)

		engine.run_lifecycle()

		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "access_gate"), "Full")
		reasons = " ".join(frappe.get_all(
			"Subscription Event", filters={"platform_subscription": sub.name}, pluck="reason"))
		self.assertIn("minimum tenure", reasons.lower())

	def test_the_circuit_breaker_halts_the_run_and_suspends_nobody(self):
		"""A gateway outage must never lock out the customer base."""
		subs = []
		for index in range(4):
			sub = fx.a_subscription(f"{PREFIX}cb{index}", status="Grace", overdue_days=20)
			fx.overdue_invoice(sub, days=20)
			fx.a_tenant(f"{PREFIX}cb{index}", sub)
			subs.append(sub)
		fx.settings(**fx.LIVE)
		fx.settings(max_suspensions_per_run=2)

		summary = engine.run_lifecycle()

		self.assertTrue(summary["halted"])
		self.assertIn("exceeds the limit", summary["halt_reason"])
		self.assertEqual(summary["suspended"], 0)
		for sub in subs:
			self.assertEqual(
				frappe.db.get_value("Platform Subscription", sub.name, "status"), "Grace",
				"the breaker halted but something was still suspended",
			)

	def test_past_due_leaves_access_completely_untouched(self):
		"""A deliberate product decision, asserted explicitly because a later refactor
		will be tempted to 'fix' it. A failed payment is usually the bank."""
		self.assertEqual(state_machine.ACCESS_BY_STATE["Past Due"], "None")
		sub = fx.a_subscription(f"{PREFIX}pd", overdue_days=2)
		fx.overdue_invoice(sub, days=2)
		tenant = fx.a_tenant(f"{PREFIX}pd", sub)
		fx.settings(**fx.LIVE)

		state_machine.transition(sub, "Past Due", "collection failed", "Webhook")

		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "access_state"),
		                 "Full")
		self.assertEqual(frappe.db.get_value("Tenant", tenant.name, "access_gate"), "Full")


class TestRestoration(LifecycleTestCase):
	def test_a_cleared_balance_restores_in_the_same_run_without_approval(self):
		sub = fx.a_subscription(f"{PREFIX}rest", status="Suspended", overdue_days=20)
		tenant = fx.a_tenant(f"{PREFIX}rest", sub)
		# Nothing outstanding: no unpaid invoice, no consecutive failures.
		fx.settings(**fx.LIVE)
		fx.settings(require_manual_approval_for_suspension=1)

		summary = engine.run_lifecycle()

		self.assertGreaterEqual(summary["restored"], 1)
		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Active")


class TestPolicyResolution(LifecycleTestCase):
	def test_a_plan_specific_policy_beats_the_default(self):
		# Its own plan, deliberately: binding a policy to the plan every other test uses
		# would silently govern all of them.
		plan = fx.a_plan(f"{PREFIX} Policy Plan")
		name = f"{PREFIX} Plan Policy"
		if frappe.db.exists("Subscription Policy", name):
			frappe.delete_doc("Subscription Policy", name, force=True,
			                  ignore_permissions=True, ignore_on_trash=True)
		frappe.get_doc({
			"doctype": "Subscription Policy", "policy_name": name,
			"applicable_plan": plan, "applicable_cycle": "All",
			"is_active": 1, "grace_period_days": 3, "suspension_after_days": 9,
			"cancellation_after_days": 30,
			"stages": [{"stage_code": "PD", "trigger_type": "Days After Due Date",
			            "day_offset": 0, "from_state": "Active", "to_state": "Past Due",
			            "access_effect": "None"}],
		}).insert(ignore_permissions=True)
		sub = fx.a_subscription(f"{PREFIX}pol", plan=plan)
		self.assertEqual(policy.resolve(sub), name)

	def test_a_healthy_subscription_matches_no_stage_at_all(self):
		"""The bug this exists to prevent: a day-0 stage firing for a customer who owes
		nothing, telling them their payment failed."""
		sub = fx.a_subscription(f"{PREFIX}healthy")
		self.assertIsNone(policy.days_overdue(sub))
		_name, stage, overdue = policy.stage_for(sub)
		self.assertIsNone(stage)
		self.assertIsNone(overdue)

	def test_the_stage_reached_is_the_latest_passed_not_the_next(self):
		"""A subscription 20 days unpaid lands on the day-15 stage, not on day 0."""
		sub = fx.a_subscription(f"{PREFIX}stage", status="Grace", overdue_days=20)
		fx.overdue_invoice(sub, days=20)
		_name, stage, overdue = policy.stage_for(sub)
		self.assertEqual(overdue, 20)
		self.assertEqual(stage.stage_code, "SUSPEND")

	def test_next_change_is_computed_so_support_can_see_what_happens_when(self):
		sub = fx.a_subscription(f"{PREFIX}next", status="Past Due", overdue_days=8)
		fx.overdue_invoice(sub, days=8)
		when, to_state = policy.next_change(sub)
		self.assertIsNotNone(when)
		self.assertEqual(to_state, "Grace")
		self.assertEqual(getdate(when), getdate(add_days(today(), 4)),
		                 "day 12 is four days after day 8")


class TestHeartbeat(LifecycleTestCase):
	def test_every_run_stamps_a_heartbeat(self):
		frappe.db.set_single_value("A3 Sola Settings", {"lifecycle_heartbeat_on": None})
		engine.run_lifecycle()
		self.assertIsNotNone(get_value("lifecycle_heartbeat_on"),
		                     "a run that leaves no heartbeat cannot be seen to have stopped")

	def test_a_stopped_engine_is_detectable(self):
		frappe.db.set_single_value(
			"A3 Sola Settings", {"lifecycle_heartbeat_on": add_days(today(), -5)})
		self.assertFalse(engine.alert_on_missing_heartbeat())

	def test_a_running_engine_reports_healthy(self):
		engine.heartbeat()
		self.assertTrue(engine.alert_on_missing_heartbeat())


class TestSimulation(LifecycleTestCase):
	def test_simulation_writes_absolutely_nothing(self):
		sub = fx.a_subscription(f"{PREFIX}sim", status="Grace", overdue_days=20)
		fx.overdue_invoice(sub, days=20)
		fx.settings(**fx.LIVE)
		before = frappe.db.count("Subscription Event")

		summary = engine.simulate()

		self.assertTrue(summary["simulated"])
		self.assertEqual(frappe.db.count("Subscription Event"), before)
		self.assertEqual(frappe.db.get_value("Platform Subscription", sub.name, "status"),
		                 "Grace")

	def test_simulation_still_reports_the_decisions_it_would_make(self):
		sub = fx.a_subscription(f"{PREFIX}sim2", status="Grace", overdue_days=20)
		fx.overdue_invoice(sub, days=20)
		fx.settings(**fx.LIVE)
		summary = engine.simulate()
		mine = [d for d in summary["decisions"] if d["subscription"] == sub.name]
		self.assertTrue(mine, "the simulation reported nothing for an overdue subscription")
		self.assertEqual(mine[0]["to_state"], "Suspended")


def _enabled_map(tenant):
	from a3_sola.api.entitlements import TENANT_FIELD

	return {
		row["name"]: row["enabled"]
		for row in frappe.get_all("User", filters={TENANT_FIELD: tenant},
		                          fields=["name", "enabled"])
	}
