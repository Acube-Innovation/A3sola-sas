# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The reporting layer, the pre-flight check and the bulk operations.

The MRR reconciliation test is the one that matters: an MRR bridge that does not tie gets
quoted in a board pack and then quietly disbelieved, which is worse than not having one.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from a3_sola.api.lifecycle import admin, engine
from a3_sola.tests.platform import lifecycle_fixtures as fx

PREFIX = "lcreport"

REPORTS = (
	"Subscription Health", "Revenue at Risk", "Churn Analysis", "Cohort Retention",
	"MRR Movement", "Lifecycle Decision Audit", "Suspension Register",
	"Plan Change Register", "Trial Pipeline", "Engagement Signals",
)


class ReportTestCase(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		fx.purge(PREFIX)
		fx.settings(**fx.INERT)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		fx.settings(**fx.INERT)


class TestEveryReportRuns(ReportTestCase):
	def test_all_ten_execute_and_return_columns(self):
		for name in REPORTS:
			with self.subTest(report=name):
				columns, data = frappe.get_doc("Report", name).execute_script_report(
					frappe._dict())[:2]
				self.assertTrue(columns, f"{name} returned no columns")
				self.assertIsInstance(data, list)

	def test_none_of_them_take_an_unchecked_company_filter(self):
		"""Phase 7's reports are platform-level. If one ever grows a company filter it
		has to go through the guard, like every other report in the app."""
		import os

		base = frappe.get_app_path("a3_sola", "platform", "report")
		offenders = []
		for name in REPORTS:
			folder = name.lower().replace(" ", "_")
			path = os.path.join(base, folder, folder + ".py")
			source = open(path).read()
			if "filters.company" in source and "resolve_report_company" not in source:
				offenders.append(name)
		self.assertEqual(offenders, [])


class TestTheMrrBridgeTies(ReportTestCase):
	def test_every_month_reconciles_opening_to_closing(self):
		columns, rows = frappe.get_doc("Report", "MRR Movement").execute_script_report(
			frappe._dict())[:2]
		self.assertTrue(rows)
		for row in rows:
			expected = flt(
				flt(row["opening"]) + flt(row["new"]) + flt(row["expansion"])
				- flt(row["contraction"]) - flt(row["churned"]) + flt(row["reactivated"]),
				2,
			)
			self.assertAlmostEqual(
				expected, flt(row["closing"], 2), places=2,
				msg=f"{row['month']} does not reconcile: "
				    f"opening {row['opening']} + movement != closing {row['closing']}",
			)

	def test_each_month_opens_where_the_last_one_closed(self):
		_columns, rows = frappe.get_doc("Report", "MRR Movement").execute_script_report(
			frappe._dict())[:2]
		for previous, current in zip(rows, rows[1:]):
			self.assertAlmostEqual(
				flt(previous["closing"], 2), flt(current["opening"], 2), places=2,
				msg=f"{current['month']} opens at {current['opening']} but "
				    f"{previous['month']} closed at {previous['closing']}",
			)

	def test_the_report_says_so_itself(self):
		"""The reconciliation is stated per row, not only asserted here, so anybody
		reading the report can see that it holds."""
		_columns, rows = frappe.get_doc("Report", "MRR Movement").execute_script_report(
			frappe._dict())[:2]
		self.assertTrue(all(row["reconciles"] == "yes" for row in rows))


class TestHealthScoring(ReportTestCase):
	def test_the_score_always_shows_its_working(self):
		"""A bare number nobody can decompose gets ignored within a month."""
		_columns, rows = frappe.get_doc("Report", "Subscription Health").execute_script_report(
			frappe._dict())[:2]
		for row in rows:
			self.assertIn("health_reason", row)
			self.assertTrue(row["health_reason"], f"{row['tenant']} has a score with no reasons")

	def test_a_suspended_tenant_scores_worse_than_an_active_one(self):
		from a3_sola.platform.report.subscription_health.subscription_health import _score

		healthy, _why = _score(frappe._dict(status="Active"), 5, 4, 1, 0)
		blocked, _why = _score(frappe._dict(status="Suspended"), 5, 4, 1, 0)
		self.assertGreater(healthy, blocked)


class TestPreflight(ReportTestCase):
	def test_it_reports_every_precondition(self):
		result = admin.preflight()
		codes = {c["code"] for c in result["checks"]}
		self.assertEqual(codes, {"default_policy", "notification_templates",
		                         "circuit_breaker", "approval_role", "heartbeat",
		                         "simulation"})

	def test_a_missing_default_policy_fails_the_check(self):
		fx.settings(default_subscription_policy=None)
		try:
			result = admin.preflight()
			policy = [c for c in result["checks"] if c["code"] == "default_policy"][0]
			self.assertFalse(policy["passed"])
			self.assertIn("nothing to apply", policy["detail"])
			self.assertFalse(result["ready"])
		finally:
			fx.settings(default_subscription_policy="Standard Non-Payment Policy")

	def test_no_circuit_breaker_limit_fails_the_check(self):
		fx.settings(max_suspensions_per_run=0)
		try:
			result = admin.preflight()
			breaker = [c for c in result["checks"] if c["code"] == "circuit_breaker"][0]
			self.assertFalse(breaker["passed"])
			self.assertIn("every customer", breaker["detail"])
		finally:
			fx.settings(max_suspensions_per_run=10)

	def test_an_engine_that_has_never_run_fails_the_check(self):
		before = frappe.db.get_single_value("A3 Sola Settings", "lifecycle_heartbeat_on")
		fx.settings(lifecycle_heartbeat_on=None, lifecycle_heartbeat_streak_days=0)
		try:
			heartbeat = [c for c in admin.preflight()["checks"]
			             if c["code"] == "heartbeat"][0]
			self.assertFalse(heartbeat["passed"])
			self.assertIn("never run", heartbeat["detail"])
		finally:
			fx.settings(lifecycle_heartbeat_on=before)

	def test_turning_it_on_is_refused_while_anything_is_missing(self):
		fx.settings(lifecycle_simulation_last_run=None, max_suspensions_per_run=0)
		try:
			with self.assertRaises(frappe.ValidationError) as caught:
				admin.enable_automatic_suspension(confirm="SUSPEND CUSTOMERS")
			self.assertIn("Still to do", str(caught.exception))
		finally:
			fx.settings(max_suspensions_per_run=10)

	def test_the_simulation_records_that_it_was_run(self):
		fx.settings(lifecycle_simulation_last_run=None)
		admin.run_simulation()
		self.assertIsNotNone(
			frappe.db.get_single_value("A3 Sola Settings", "lifecycle_simulation_last_run"))


class TestTheKillSwitch(ReportTestCase):
	def test_pulling_it_needs_a_reason(self):
		with self.assertRaises(frappe.ValidationError):
			admin.kill_switch(on=1)

	def test_it_stops_state_changes_and_leaves_evaluation_running(self):
		sub = fx.a_subscription(f"{PREFIX}kill", status="Grace", overdue_days=20)
		fx.overdue_invoice(sub, days=20)
		fx.settings(**fx.LIVE)
		admin.kill_switch(on=1, reason="Gateway outage at the acquirer")
		try:
			summary = engine.run_lifecycle()
			self.assertTrue(summary["halted"])
			self.assertEqual(
				frappe.db.get_value("Platform Subscription", sub.name, "status"), "Grace")
		finally:
			admin.kill_switch(on=0)


class TestBulkOperations(ReportTestCase):
	def test_bulk_operations_demand_a_typed_confirmation(self):
		sub = fx.a_subscription(f"{PREFIX}bulk")
		with self.assertRaises(frappe.ValidationError) as caught:
			admin.bulk_extend_grace([sub.name], 5, "outage")
		self.assertIn("Type", str(caught.exception))

	def test_bulk_extend_writes_one_event_per_subscription(self):
		"""Never one event for the batch. The question asked later is about one customer."""
		subs = [fx.a_subscription(f"{PREFIX}b{i}", status="Grace") for i in range(3)]
		names = [s.name for s in subs]
		admin.bulk_extend_grace(names, 5, "Acquirer outage on 1 September",
		                        confirm="EXTEND")
		for name in names:
			events = frappe.get_all("Subscription Event",
			                        filters={"platform_subscription": name,
			                                 "event_type": "Manual Override"})
			self.assertEqual(len(events), 1, f"{name} did not get its own event")

	def test_bulk_extend_refuses_an_absurd_extension(self):
		sub = fx.a_subscription(f"{PREFIX}absurd")
		with self.assertRaises(frappe.ValidationError):
			admin.bulk_extend_grace([sub.name], 400, "why not", confirm="EXTEND")

	def test_bulk_reassign_records_the_policy_it_moved_from(self):
		sub = fx.a_subscription(f"{PREFIX}reassign")
		admin.bulk_reassign_policy([sub.name], "Standard Non-Payment Policy",
		                           "Standardising after the pilot", confirm="REASSIGN")
		reasons = frappe.get_all("Subscription Event",
		                         filters={"platform_subscription": sub.name},
		                         pluck="reason")
		self.assertTrue(any("Policy changed from" in r for r in reasons))


class TestTenant360(ReportTestCase):
	def test_it_answers_the_questions_support_actually_asks(self):
		sub = fx.a_subscription(f"{PREFIX}360")
		tenant = fx.a_tenant(f"{PREFIX}360", sub, users=2)
		view = admin.tenant_360(tenant.name)
		for section in ("tenant", "subscription", "seats", "users", "invoices",
		                "suspensions", "changes", "events", "onboarding"):
			self.assertIn(section, view)
		self.assertEqual(len(view["users"]), 2)
		self.assertEqual(view["subscription"]["name"], sub.name)
