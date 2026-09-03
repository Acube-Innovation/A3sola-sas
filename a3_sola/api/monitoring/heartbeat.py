# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every background job says when it last ran, and a watchdog notices when one stops.

TWO DESIGN DECISIONS WORTH STATING

*No new doctype.* The heartbeats live in one JSON field on the settings singleton. A
doctype would be tidier and would also be a table that grows forever and needs its own
retention policy, for data whose entire content is "fifteen jobs, when each last ran".

*Nothing is added to the jobs themselves.* Frappe fires `before_job` and `after_job` around
every scheduled call, so the heartbeat is recorded from there. Fifteen decorators on
fifteen functions is fifteen chances for the sixteenth job to be added without one - and
the sixteenth job is exactly the one that will stop silently.

WHAT THE WATCHDOG ACTUALLY CHECKS

Not "did the job error" - Frappe already logs that. It checks whether each job has run
*at all* within a multiple of its own cadence, which is the failure nobody notices.
"""

import json

import frappe
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

FIELD = "job_heartbeats"

#: How far past its cadence a job may drift before it counts as missing.
#:
#: Two, not one: a daily job whose window slipped by an hour is not an incident, and an
#: alert that fires on ordinary jitter is an alert that gets muted.
TOLERANCE = 2.2

CADENCE_SECONDS = {
	"all": 300,
	"hourly": 3600,
	"hourly_long": 3600,
	"daily": 86400,
	"daily_long": 86400,
	"weekly": 604800,
	"weekly_long": 604800,
	"monthly": 2592000,
	"monthly_long": 2592000,
	"cron": 86400,
}


def expected_jobs():
	"""{method path: cadence} for every job this app registers, from the registry.

	Read from the registry rather than listed, so a job added in a later release is
	watched without anybody remembering to add it here - which is the whole point.
	"""
	from a3_sola import registry

	out = {}
	for cadence, methods in (registry.merged_scheduler_events() or {}).items():
		if isinstance(methods, dict):
			for _cron, entries in methods.items():
				for method in entries:
					out[method] = "cron"
			continue
		for method in methods:
			out[method] = cadence
	return out


def _load():
	raw = frappe.db.get_single_value("A3 Sola Settings", FIELD)
	if not raw:
		return {}
	try:
		return json.loads(raw)
	except (ValueError, TypeError):
		return {}


def _save(data):
	frappe.db.set_single_value("A3 Sola Settings", FIELD,
	                           json.dumps(data, default=str)[:100000])


def record(method, outcome="ok", counts=None, seconds=None, error=None):
	"""Stamp that `method` ran, and what it did.

	Written with `set_single_value` rather than a document save so it cannot be rolled back
	by whatever the job itself does - a job that fails and rolls back must still leave
	evidence that it ran, otherwise the watchdog reports it as missing and the real error
	is buried under a false one.
	"""
	if not method or not str(method).startswith("a3_sola."):
		return None
	data = _load()
	data[method] = {
		"last_run": str(now_datetime()),
		"outcome": outcome,
		"counts": counts or {},
		"seconds": round(seconds, 2) if seconds is not None else None,
		"error": (str(error)[:300] if error else None),
	}
	_save(data)
	return data[method]


def on_job_start(method=None, **kwargs):
	"""`before_job`. Remembers when this one began so the duration is real."""
	if method and str(method).startswith("a3_sola."):
		frappe.local._a3s_job_started = now_datetime()
		frappe.local._a3s_job_method = method


def on_job_end(method=None, result=None, **kwargs):
	"""`after_job`. One heartbeat per job, whatever the job returned.

	The counts come from the job's own return value when it returns a dict, which most of
	them do. That is how "billing ran" becomes "billing ran and collected 14", which is
	the difference between a liveness check and something worth reading.
	"""
	if not method or not str(method).startswith("a3_sola."):
		return
	started = getattr(frappe.local, "_a3s_job_started", None)
	seconds = (now_datetime() - started).total_seconds() if started else None
	counts = {}
	if isinstance(result, dict):
		counts = {
			key: value for key, value in result.items()
			if isinstance(value, int | float) and not isinstance(value, bool)
		}
	try:
		record(method, outcome="ok", counts=counts, seconds=seconds)
		frappe.db.commit()
	except Exception:
		# A monitoring failure must never take down the thing being monitored.
		frappe.log_error(frappe.get_traceback(), "a3_sola: heartbeat could not be recorded")


def status():
	"""Per job: when it last ran, whether that is within its cadence, and what it did."""
	beats = _load()
	now = now_datetime()
	# Frappe's own record of the last execution, which exists even for a job that has
	# never reached our after_job hook - a job that errors before starting, for instance.
	framework = {
		row.method: row.last_execution
		for row in frappe.get_all("Scheduled Job Type",
		                          filters={"method": ["like", "a3_sola.%"]},
		                          fields=["method", "last_execution"])
	}
	out = []
	for method, cadence in sorted(expected_jobs().items()):
		beat = beats.get(method) or {}
		last = beat.get("last_run") or framework.get(method)
		window = CADENCE_SECONDS.get(cadence, 86400) * TOLERANCE
		age = None
		if last:
			try:
				age = (now - get_datetime(last)).total_seconds()
			except Exception:
				age = None
		out.append({
			"method": method,
			"cadence": cadence,
			"last_run": str(last) if last else None,
			"age_seconds": round(age) if age is not None else None,
			"expected_within_seconds": round(window),
			"healthy": bool(last and age is not None and age <= window),
			"never_run": not last,
			"outcome": beat.get("outcome"),
			"counts": beat.get("counts") or {},
			"seconds": beat.get("seconds"),
		})
	return out


def missing():
	"""The jobs that have stopped, or never started."""
	return [row for row in status() if not row["healthy"]]


def watchdog():
	"""Scheduled frequently. Alerts on ABSENCE, which is the failure nobody notices.

	Also stamps its own heartbeat, so a watchdog that dies is itself detectable - one
	level up, by the external uptime check pointed at the health endpoint.
	"""
	from a3_sola.api.lifecycle import notify

	stopped = missing()
	record("a3_sola.api.monitoring.heartbeat.watchdog", outcome="ok",
	       counts={"watched": len(expected_jobs()), "missing": len(stopped)})
	frappe.db.commit()
	if not stopped:
		return {"watched": len(expected_jobs()), "missing": 0}

	never = [row for row in stopped if row["never_run"]]
	late = [row for row in stopped if not row["never_run"]]
	body = ["These background jobs are not running.\n"]
	if late:
		body.append("STOPPED - last ran, but not recently enough:")
		for row in late:
			body.append(
				f"  {row['method']}\n"
				f"      cadence {row['cadence']}, last run {row['last_run']}, "
				f"{round((row['age_seconds'] or 0) / 3600, 1)} hours ago"
			)
	if never:
		body.append("\nNEVER RUN:")
		for row in never:
			body.append(f"  {row['method']} ({row['cadence']})")
	body.append(
		"\nNothing errors when a scheduler stops. Billing simply does not happen, "
		"renewals are not chased and access is not evaluated. Check `bench doctor` and "
		"the supervisor process for the scheduler."
	)
	notify.alert_internal("a3_sola: background jobs have stopped", "\n".join(body))
	return {"watched": len(expected_jobs()), "missing": len(stopped),
	        "methods": [row["method"] for row in stopped]}
