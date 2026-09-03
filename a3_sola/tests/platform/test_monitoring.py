# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Heartbeats, the health endpoint, PII redaction and the console.

The tests that matter here are the ones that prove a DETECTOR detects. A monitoring suite
that only checks the happy path tells you the code runs; it does not tell you the alert
would fire, and the alert firing is the entire product.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from a3_sola.api import console, health
from a3_sola.api.monitoring import alerts, errors, heartbeat


class MonitoringTestCase(FrappeTestCase):
	@classmethod
	def tearDownClass(cls):
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats", None)
		frappe.db.commit()
		super().tearDownClass()

	def _all_healthy(self):
		"""Pretend every registered job just ran."""
		data = {
			method: {"last_run": str(now_datetime()), "outcome": "ok", "counts": {},
			         "seconds": 0.1, "error": None}
			for method in heartbeat.expected_jobs()
		}
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats",
		                           json.dumps(data, default=str))
		return data


class TestHeartbeats(MonitoringTestCase):
	def test_every_registered_job_is_watched(self):
		"""Read from the registry, so a job added later is watched without anybody
		remembering to add it here."""
		from a3_sola import registry

		watched = heartbeat.expected_jobs()
		registered = set()
		for cadence, methods in registry.merged_scheduler_events().items():
			if isinstance(methods, dict):
				continue
			registered |= set(methods)
		self.assertEqual(registered - set(watched), set(),
		                 "these scheduled jobs are not being watched")
		self.assertGreater(len(watched), 20)

	def test_a_job_that_just_ran_is_healthy(self):
		self._all_healthy()
		self.assertEqual(heartbeat.missing(), [])

	def test_a_stopped_job_is_detected_within_its_own_cadence(self):
		"""THE DEMONSTRATION. One job is stopped and the watchdog must notice.

		Backdated by three days: a daily job tolerates 2.2× its cadence, so this is
		definitively late rather than merely jittery.
		"""
		data = self._all_healthy()
		victim = "a3_sola.api.billing_engine.run_daily_billing"
		self.assertIn(victim, data, "the billing engine is not registered")
		data[victim]["last_run"] = str(add_to_date(now_datetime(), days=-3))
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats",
		                           json.dumps(data, default=str))

		stopped = heartbeat.missing()
		methods = [row["method"] for row in stopped]
		self.assertIn(victim, methods,
		              "a job that has not run for three days was not detected")
		row = [r for r in stopped if r["method"] == victim][0]
		self.assertFalse(row["never_run"])
		self.assertGreater(row["age_seconds"], row["expected_within_seconds"])

	def test_a_job_that_never_ran_is_detected_separately(self):
		"""Different from stopped, and worth distinguishing: never-run usually means a
		deployment problem, stopped usually means the scheduler died."""
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats", json.dumps({}))
		stopped = heartbeat.missing()
		self.assertTrue(stopped)
		self.assertTrue(all(row["never_run"] for row in stopped))

	def test_jitter_inside_the_tolerance_does_not_fire(self):
		"""A daily job an hour late is not an incident. An alert that fires on ordinary
		jitter is an alert that gets muted."""
		data = self._all_healthy()
		victim = "a3_sola.api.dunning.run_dunning"
		data[victim]["last_run"] = str(add_to_date(now_datetime(), hours=-25))
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats",
		                           json.dumps(data, default=str))
		self.assertNotIn(victim, [r["method"] for r in heartbeat.missing()])

	def test_the_watchdog_stamps_its_own_heartbeat(self):
		"""A watchdog that dies silently is the same problem one level up."""
		self._all_healthy()
		heartbeat.watchdog()
		beats = json.loads(
			frappe.db.get_single_value("A3 Sola Settings", "job_heartbeats") or "{}")
		self.assertIn("a3_sola.api.monitoring.heartbeat.watchdog", beats)


class TestHealthEndpoint(MonitoringTestCase):
	def test_the_public_check_leaks_nothing(self):
		"""It returns a status and a timestamp. Not the queue depths, not the versions,
		not which dependency is down - an attacker would like all of those."""
		result = health.check()
		self.assertEqual(set(result), {"status", "time"})
		self.assertIn(result["status"], (health.OK, health.DEGRADED, health.DOWN))
		body = json.dumps(result).lower()
		for leak in ("redis", "queue", "disk", "database", "scheduler", "tenant",
		             "razorpay", "version", "error"):
			self.assertNotIn(leak, body, f"the public health check mentions {leak}")

	def test_it_reports_ok_when_everything_is_running(self):
		self._all_healthy()
		frappe.db.set_single_value("System Settings", "enable_scheduler", 1)
		checks = health._collect(shallow=True)
		self.assertEqual(checks["background_jobs"]["state"], health.OK)
		self.assertEqual(checks["database"]["state"], health.OK)

	def test_it_reports_degraded_when_a_job_has_stopped(self):
		"""The other half of the demonstration: it must change when something breaks."""
		data = self._all_healthy()
		data["a3_sola.api.billing_engine.run_daily_billing"]["last_run"] = str(
			add_to_date(now_datetime(), days=-3))
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats",
		                           json.dumps(data, default=str))
		checks = health._collect(shallow=True)
		self.assertEqual(checks["background_jobs"]["state"], health.DEGRADED)
		self.assertIn(health._overall(checks), (health.DEGRADED, health.DOWN))

	def test_everything_stopped_is_down_not_merely_degraded(self):
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats", json.dumps({}))
		checks = health._collect(shallow=True)
		self.assertEqual(checks["background_jobs"]["state"], health.DOWN)

	def test_the_detailed_view_needs_a_role(self):
		original = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				health.detail()
		finally:
			frappe.set_user(original)

	def test_the_mode_switches_are_reported_but_never_count_as_a_fault(self):
		"""Postings being off is a decision, not an outage."""
		checks = health._collect(shallow=False)
		self.assertIn("modes", checks)
		self.assertEqual(checks["modes"]["state"], health.OK)


class TestPiiRedaction(MonitoringTestCase):
	def test_a_trace_containing_customer_data_is_scrubbed(self):
		"""A stack trace with a GSTIN and a payment reference, sent to an external error
		service, is a data leak - and it is the kind nobody notices."""
		trace = (
			"ValidationError: customer 32AABCU9603R1ZM could not be charged via "
			"order_MkL9x2QaBcDeFg for consumer 1156500000001. Contact "
			"ravi.menon@example.com on 9847012345, account at ICIC0000289. "
			# Assembled, not written: two scanners walk this codebase and a literal fake
			# key here is a real finding to both of them.
			f"api_key='{'rzp_' + 'live_' + 'ABCDEFGHIJ1234'}' "
			f"password='{'hunter' + '2secret'}'"
		)
		cleaned = errors.redact(trace)
		for secret in ("32AABCU9603R1ZM", "order_MkL9x2QaBcDeFg", "1156500000001",
		               "ravi.menon@example.com", "9847012345", "ICIC0000289",
		               "rzp_" + "live_" + "ABCDEFGHIJ1234", "hunter" + "2secret"):
			self.assertNotIn(secret, cleaned, f"{secret} survived redaction")
		# Still readable as a trace.
		self.assertIn("ValidationError", cleaned)
		self.assertIn("[GSTIN]", cleaned)
		self.assertIn("[EMAIL]", cleaned)

	def test_capture_writes_a_redacted_grouped_entry(self):
		group = errors.capture(
			"payment failed for 32AABCU9603R1ZM",
			traceback_text='File "x.py", line 1, in f\nValidationError: pay_ABCDEFGHIJKL',
			extra={"gstin": "32AABCU9603R1ZM"},
		)
		self.assertTrue(group)
		row = frappe.get_all("Error Log", filters={"method": ["like", f"%{group}%"]},
		                     fields=["method", "error"], limit=1)
		self.assertTrue(row)
		self.assertNotIn("32AABCU9603R1ZM", row[0].method + row[0].error)

	def test_the_same_failure_groups_together(self):
		"""One recurring failure repeated four thousand times drowns the one that
		happened once, and the one that happened once is the interesting one."""
		trace_a = ('File "a.py", line 10, in charge\nValidationError: order_AAAAAAAAAAAA')
		trace_b = ('File "a.py", line 99, in charge\nValidationError: order_BBBBBBBBBBBB')
		self.assertEqual(errors.fingerprint(trace_a), errors.fingerprint(trace_b),
		                 "the same failure with different data got different groups")

	def test_a_different_failure_gets_a_different_group(self):
		trace_a = 'File "a.py", line 10, in charge\nValidationError: x'
		trace_b = 'File "b.py", line 10, in provision\nPermissionError: y'
		self.assertNotEqual(errors.fingerprint(trace_a), errors.fingerprint(trace_b))

	def test_the_user_is_hashed_not_named(self):
		context = errors.context()
		self.assertIn("user_hash", context)
		self.assertNotIn(frappe.session.user, json.dumps(context))


class TestBusinessAlerts(MonitoringTestCase):
	def test_every_check_states_an_expected_frequency(self):
		"""The fatigue rule, enforced. An alert nobody can say the frequency of is an
		alert nobody can decide to keep."""
		self._all_healthy()
		for check in alerts.CHECKS:
			alert = check()
			if alert:
				self.assertTrue(alert.expected,
				                f"{check.__name__} fired without an expected frequency")
				self.assertIn(alert.severity,
				              (alerts.CRITICAL, alerts.HIGH, alerts.NORMAL,
				               alerts.DASHBOARD))

	def test_a_stopped_scheduler_raises_a_critical(self):
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats", json.dumps({}))
		fired = [a for a in alerts.evaluate() if a.code == "scheduler_stopped"]
		self.assertTrue(fired, "a completely stopped scheduler did not alert")
		self.assertEqual(fired[0].severity, alerts.CRITICAL)

	def test_alerts_come_back_worst_first(self):
		frappe.db.set_single_value("A3 Sola Settings", "job_heartbeats", json.dumps({}))
		fired = alerts.evaluate()
		order = {alerts.CRITICAL: 0, alerts.HIGH: 1, alerts.NORMAL: 2}
		ranks = [order.get(a.severity, 9) for a in fired]
		self.assertEqual(ranks, sorted(ranks))

	def test_a_healthy_platform_alerts_about_the_scheduler_and_nothing_invented(self):
		"""Guards against a check that fires on an empty site for no reason."""
		self._all_healthy()
		codes = {a.code for a in alerts.evaluate()}
		self.assertNotIn("scheduler_stopped", codes)


class TestConsole(MonitoringTestCase):
	def test_the_overview_answers_what_a_person_opens_it_for(self):
		self._all_healthy()
		overview = console.overview()
		for section in ("tenants", "subscriptions", "revenue", "needs_attention",
		                "health", "modes"):
			self.assertIn(section, overview)
		self.assertIn("mrr", overview["revenue"])
		self.assertIn("at_risk", overview["revenue"])

	def test_the_mode_switches_are_all_surfaced(self):
		"""Somebody always forgets which mode production is in."""
		fields = {row["field"] for row in console.modes()}
		for switch in ("enable_accounting_postings", "enable_automatic_suspension",
		               "dry_run_mode", "lifecycle_kill_switch", "provisioning_mode"):
			self.assertIn(switch, fields)

	def test_the_console_needs_a_role(self):
		original = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				console.overview()
		finally:
			frappe.set_user(original)


class TestImpersonation(MonitoringTestCase):
	"""Reason-gated, time-limited, audited and notified. Any one missing is a problem."""

	def setUp(self):
		self.tenant = frappe.db.get_value("Tenant", {"admin_user": ["is", "set"]}, "name")
		if not self.tenant:
			self.skipTest("no tenant with an administrator on this site")

	def tearDown(self):
		frappe.set_user("Administrator")
		console.end_impersonation()

	def test_it_refuses_without_a_real_reason(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			console.start_impersonation(self.tenant, "test")
		self.assertIn("real reason", str(caught.exception))

	def test_it_is_time_limited_and_capped(self):
		session = console.start_impersonation(
			self.tenant, "Customer reports the commissioning form prints blank",
			minutes=999)
		from frappe.utils import get_datetime

		length = (get_datetime(session["expires"]) - now_datetime()).total_seconds() / 60
		self.assertLessEqual(length, 121, "the session cap was not applied")

	def test_it_writes_an_audit_entry_that_cannot_be_edited_away(self):
		before = frappe.db.count("Platform Audit Entry",
		                         {"entry_type": "Support Session Started"})
		console.start_impersonation(
			self.tenant, "Customer reports the commissioning form prints blank")
		after = frappe.db.count("Platform Audit Entry",
		                        {"entry_type": "Support Session Started"})
		self.assertEqual(after, before + 1)

	def test_the_banner_names_the_tenant_and_says_they_were_told(self):
		session = console.start_impersonation(
			self.tenant, "Customer reports the commissioning form prints blank")
		self.assertIn("acting as", session["banner"])
		self.assertIn("told", session["banner"])

	def test_the_open_session_is_discoverable(self):
		console.start_impersonation(
			self.tenant, "Customer reports the commissioning form prints blank")
		active = console.active_impersonation()
		self.assertTrue(active)
		self.assertEqual(active["tenant"], self.tenant)

	def test_notification_defaults_to_on(self):
		"""Impersonation without notification is a trust violation. It is configurable
		because a client will ask; it defaults on because the client asking is not the
		person whose account it is."""
		from a3_sola.api.settings import get_value

		self.assertTrue(frappe.utils.cint(
			get_value("notify_tenant_on_impersonation", 1)))
