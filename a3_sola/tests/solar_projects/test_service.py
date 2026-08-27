# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Service tickets, SLA escalation and the two kinds of underperformance."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_to_date, flt, get_datetime, getdate, now_datetime, today

from a3_sola.api import sla
from a3_sola.tests.solar_projects.fixtures import (
	commissioned_project,
	make_reading,
	make_ticket,
	om_contract,
)


class TestServiceTicketSLA(FrappeTestCase):
	def setUp(self):
		project, self.installation, _ = commissioned_project()
		self.project = project
		self.contract = om_contract(project)

	def test_sla_due_times_come_from_the_contract(self):
		ticket = make_ticket(self.contract, severity="Critical")
		expected = add_to_date(
			get_datetime(ticket.reported_on), hours=int(self.contract.critical_response_hours)
		)
		self.assertEqual(get_datetime(ticket.response_due_by), expected)

	def test_a_critical_ticket_is_due_sooner_than_a_major_one(self):
		critical = make_ticket(self.contract, severity="Critical")
		major = make_ticket(self.contract, severity="Major")
		self.assertLess(
			get_datetime(critical.resolution_due_by), get_datetime(major.resolution_due_by)
		)

	def test_resolution_within_the_window_meets_the_sla(self):
		ticket = make_ticket(self.contract, severity="Critical")
		ticket.status = "Resolved"
		ticket.resolution_description = "Loose DC connector reterminated."
		ticket.root_cause = "Workmanship"
		ticket.flags.ignore_validate_update_after_submit = True
		ticket.save(ignore_permissions=True)
		ticket.reload()
		self.assertTrue(ticket.resolution_sla_met)
		self.assertIsNotNone(ticket.resolved_on)

	def test_a_late_resolution_is_recorded_as_a_breach(self):
		ticket = make_ticket(self.contract, severity="Critical")
		frappe.db.set_value(
			"Service Ticket",
			ticket.name,
			"resolution_due_by",
			add_to_date(now_datetime(), hours=-1),
			update_modified=False,
		)
		ticket.reload()
		ticket.status = "Resolved"
		ticket.resolution_description = "Inverter replaced under warranty."
		ticket.root_cause = "Component Failure"
		ticket.flags.ignore_validate_update_after_submit = True
		ticket.save(ignore_permissions=True)
		ticket.reload()
		self.assertFalse(ticket.resolution_sla_met)

	def test_a_breached_ticket_escalates(self):
		"""A missed complaint SLA is a registration risk, so it cannot pass quietly."""
		ticket = make_ticket(
			self.contract, severity="Critical", reported_on=add_to_date(now_datetime(), hours=-200)
		)
		summary = sla.hourly_sla_scan()
		self.assertGreaterEqual(sum(summary.values()), 1)
		ticket.reload()
		self.assertGreater(ticket.escalation_level, 0)
		self.assertTrue(
			frappe.db.exists("ToDo", {"reference_type": "Service Ticket", "reference_name": ticket.name}),
			"escalation raised no to-do for anyone",
		)

	def test_escalation_does_not_repeat_at_the_same_rung(self):
		"""Approaching the SLA warns once. A second scan must not warn again."""
		ticket = make_ticket(
			self.contract, severity="Critical", reported_on=add_to_date(now_datetime(), hours=-60)
		)
		sla.hourly_sla_scan()
		ticket.reload()
		self.assertEqual(ticket.escalation_level, 1)

		self.assertEqual(sum(sla.hourly_sla_scan().values()), 0)
		ticket.reload()
		self.assertEqual(ticket.escalation_level, 1)

	def test_escalation_climbs_as_the_breach_widens(self):
		ticket = make_ticket(
			self.contract, severity="Critical", reported_on=add_to_date(now_datetime(), hours=-60)
		)
		sla.hourly_sla_scan()
		ticket.reload()
		first = ticket.escalation_level

		# The SLA window itself is unchanged; time simply ran past it.
		frappe.db.set_value(
			"Service Ticket",
			ticket.name,
			{
				"reported_on": add_to_date(now_datetime(), hours=-200),
				"resolution_due_by": add_to_date(now_datetime(), hours=-50),
			},
			update_modified=False,
		)
		sla.hourly_sla_scan()
		ticket.reload()
		self.assertGreater(ticket.escalation_level, first)

	def test_a_resolved_ticket_is_not_escalated(self):
		ticket = make_ticket(self.contract, severity="Critical")
		ticket.status = "Resolved"
		ticket.resolution_description = "Done."
		ticket.root_cause = "Workmanship"
		ticket.flags.ignore_validate_update_after_submit = True
		ticket.save(ignore_permissions=True)
		frappe.db.set_value(
			"Service Ticket",
			ticket.name,
			"resolution_due_by",
			add_to_date(now_datetime(), hours=-100),
			update_modified=False,
		)
		sla.hourly_sla_scan()
		ticket.reload()
		self.assertEqual(ticket.escalation_level or 0, 0)

	def test_reopening_restarts_the_clock(self):
		ticket = make_ticket(self.contract, severity="Major")
		ticket.status = "Resolved"
		ticket.resolution_description = "Cleaned the array."
		ticket.root_cause = "Soiling"
		ticket.flags.ignore_validate_update_after_submit = True
		ticket.save(ignore_permissions=True)

		ticket.reload()
		ticket.status = "Reopened"
		ticket.flags.ignore_validate_update_after_submit = True
		ticket.save(ignore_permissions=True)
		ticket.reload()
		self.assertEqual(ticket.reopen_count, 1)
		self.assertIsNone(ticket.resolved_on)
		self.assertGreater(get_datetime(ticket.resolution_due_by), get_datetime(ticket.reported_on))


class TestPerformanceMonitoring(FrappeTestCase):
	def setUp(self):
		project, self.installation, _ = commissioned_project()
		self.project = project
		self.contract = om_contract(project)
		self._lifetime, self._date = 0.0, today()

	def _readings(self, ratios):
		"""Post monthly readings that land on the requested performance ratios.

		The meter is cumulative, so this carries the lifetime figure and the date forward
		across calls exactly as a real inverter portal would.
		"""
		from a3_sola.api import calculations

		annual = calculations.estimate_generation(self.installation.capacity_kw)[
			"annual_generation_kwh"
		]
		readings = []
		for ratio in ratios:
			self._date = add_days(self._date, 30)
			self._lifetime += (annual * 30 / 365.0) * ratio / 100.0
			readings.append(make_reading(self.installation, self._lifetime, reading_date=self._date))
		return readings

	def test_a_reading_computes_its_own_performance_ratio(self):
		reading = self._readings([100.0, 90.0])[-1]
		self.assertAlmostEqual(flt(reading.performance_ratio_percent), 90.0, delta=1.0)
		self.assertEqual(reading.days_since_last_reading, 30)

	def test_healthy_generation_raises_nothing(self):
		self._readings([100.0, 100.0, 100.0, 100.0])
		self.contract.reload()
		self.assertEqual(self.contract.performance_obligation_status, "Meeting")
		self.assertEqual(self.contract.consecutive_underperforming_readings, 0)

	def test_sustained_underperformance_raises_a_major_ticket(self):
		"""Below the operational threshold, but still above the contractual floor."""
		self._readings([100.0, 78.0, 78.0, 78.0])
		self.contract.reload()
		self.assertGreaterEqual(self.contract.consecutive_underperforming_readings, 3)
		ticket = frappe.db.get_value(
			"Service Ticket",
			{"om_contract": self.contract.name, "category": "Low Generation", "severity": "Major"},
			"name",
		)
		self.assertTrue(ticket, "no Major ticket raised for sustained underperformance")

	def test_breaching_the_contractual_floor_is_critical_immediately(self):
		"""75% is a clause in a signed agreement, not a service observation."""
		self._readings([100.0, 60.0])
		self.contract.reload()
		self.assertEqual(self.contract.performance_obligation_status, "Breached")
		ticket = frappe.db.get_value(
			"Service Ticket",
			{"om_contract": self.contract.name, "category": "Low Generation", "severity": "Critical"},
			"name",
		)
		self.assertTrue(ticket, "the contractual floor was breached with no Critical ticket")

	def test_the_queue_is_not_spammed(self):
		self._readings([100.0, 60.0, 60.0, 60.0, 60.0])
		count = frappe.db.count(
			"Service Ticket",
			{
				"om_contract": self.contract.name,
				"category": "Low Generation",
				"severity": "Critical",
				"status": ["not in", ["Resolved", "Closed"]],
			},
		)
		self.assertEqual(count, 1)

	def test_recovery_clears_the_counter(self):
		self._readings([100.0, 78.0, 78.0])
		self.contract.reload()
		self.assertEqual(self.contract.consecutive_underperforming_readings, 2)
		self._readings([100.0])
		self.contract.reload()
		self.assertEqual(self.contract.consecutive_underperforming_readings, 0)

	def test_the_period_log_holds_one_row_per_month(self):
		self._readings([100.0, 90.0, 85.0])
		self.contract.reload()
		periods = [row.period for row in self.contract.performance_log]
		self.assertEqual(len(periods), len(set(periods)))


class TestReadingCapture(FrappeTestCase):
	def setUp(self):
		project, self.installation, _ = commissioned_project()
		self.project = project
		self.contract = om_contract(project)

	def _csv(self, rows):
		body = "reading_date,inverter_lifetime_kwh\n"
		return body + "".join(f"{date},{value}\n" for date, value in rows)

	def test_a_portal_export_imports(self):
		result = sla.import_readings(
			self.installation.name,
			self._csv([(add_days(today(), -60), 1200), (add_days(today(), -30), 1620)]),
		)
		self.assertEqual(len(result["created"]), 2)
		self.assertEqual(result["failed"], [])
		self.assertEqual(
			frappe.db.count("Generation Reading", {"solar_installation": self.installation.name}), 2
		)

	def test_a_date_already_on_file_is_skipped_not_duplicated(self):
		rows = [(add_days(today(), -30), 1620)]
		sla.import_readings(self.installation.name, self._csv(rows))
		result = sla.import_readings(self.installation.name, self._csv(rows))
		self.assertEqual(result["created"], [])
		self.assertEqual(len(result["skipped"]), 1)

	def test_one_bad_line_does_not_lose_the_file(self):
		body = "reading_date,inverter_lifetime_kwh\n"
		body += f"{add_days(today(), -60)},1200\n"
		body += "not-a-date,1500\n"
		body += f"{add_days(today(), -30)},1620\n"
		result = sla.import_readings(self.installation.name, body)
		self.assertEqual(len(result["created"]), 2)
		self.assertEqual(len(result["failed"]), 1)
		# Line 1 is the header, so the unreadable row is line 3 - and it is named, because
		# "the import failed" is useless to whoever has to fix the file.
		self.assertEqual(result["failed"][0]["line"], 3)
		self.assertIn("not-a-date", result["failed"][0]["reason"])

	def test_a_file_without_a_date_column_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			sla.import_readings(self.installation.name, "lifetime\n1200\n")

	def test_a_file_with_no_reading_column_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			sla.import_readings(self.installation.name, f"reading_date\n{today()}\n")

	def test_an_empty_file_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			sla.import_readings(self.installation.name, "")

	def test_a_visit_can_capture_the_meter_on_the_roof(self):
		from a3_sola.tests.solar_projects.fixtures import make_visit

		visit = make_visit(self.contract)
		visit.submit()
		name = sla.capture_reading(visit.name, inverter_lifetime_kwh=1450)
		reading = frappe.get_doc("Generation Reading", name)
		self.assertEqual(reading.reading_source, "O&M Visit")
		self.assertEqual(flt(reading.inverter_lifetime_kwh), 1450.0)
		self.assertEqual(getdate(reading.reading_date), getdate(visit.visit_date))

	def test_capturing_twice_on_one_visit_returns_the_same_reading(self):
		from a3_sola.tests.solar_projects.fixtures import make_visit

		visit = make_visit(self.contract)
		visit.submit()
		first = sla.capture_reading(visit.name, inverter_lifetime_kwh=1450)
		second = sla.capture_reading(visit.name, inverter_lifetime_kwh=1460)
		self.assertEqual(first, second)
