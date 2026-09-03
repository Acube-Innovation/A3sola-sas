# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The health endpoint, in two modes.

THE SHALLOW ONE LEAKS NOTHING, AND THAT IS THE WHOLE DESIGN.

An uptime monitor needs one word. An attacker probing an unauthenticated endpoint would
love the queue depths, the version numbers, the tenant count and which dependency is
currently down - so the public mode returns a status and a timestamp and refuses to say
anything else, including *why* it is degraded. The detailed mode needs a role.

`ok` / `degraded` / `down`:

* **ok** - everything the app needs is reachable and every background job is within its
  cadence.
* **degraded** - it will serve requests, but something is wrong that a person should look
  at: a stopped scheduler, a queue backing up, a dependency flapping.
* **down** - it cannot do its job. The database is unreachable, or every background job
  has stopped.
"""

import time

import frappe
from frappe.utils import cint, now_datetime

OK, DEGRADED, DOWN = "ok", "degraded", "down"

#: Queue depth beyond which something is wrong rather than merely busy.
QUEUE_WARN = 500
QUEUE_CRITICAL = 5000

#: Oldest queued job, in seconds, before the queue counts as stuck.
QUEUE_AGE_WARN = 900

#: Free disk below which to complain.
DISK_WARN_PERCENT = 15
DISK_CRITICAL_PERCENT = 5


@frappe.whitelist(allow_guest=True)
def check():
	"""Public. One word, a timestamp, and nothing else.

	Reachable without logging in because that is what an uptime monitor is, and rate
	limited because that is what an unauthenticated endpoint is.
	"""
	from a3_sola.api import ratelimit

	ratelimit.enforce("health", ratelimit.client_ip(), "health_rate_limit", 120,
	                  window_seconds=3600)
	try:
		state = _overall(_collect(shallow=True))
	except Exception:
		# If working out the answer fails, the answer is down.
		state = DOWN
	return {"status": state, "time": str(now_datetime())}


@frappe.whitelist()
def detail():
	"""Authenticated. Everything, for a human or a dashboard."""
	from a3_sola.api import permissions

	permissions.require_role(
		("Platform Admin", "Platform Lifecycle Operator", "System Manager"),
		action="read the detailed health status",
	)
	checks = _collect(shallow=False)
	return {
		"status": _overall(checks),
		"time": str(now_datetime()),
		"checks": checks,
	}


def _collect(shallow=False):
	"""Every dependency and every background job, each with its own verdict."""
	checks = {}
	checks["database"] = _database()
	checks["redis_cache"] = _redis("cache")
	checks["redis_queue"] = _redis("queue")
	checks["scheduler"] = _scheduler()
	checks["background_jobs"] = _jobs()
	if shallow:
		return checks
	checks["queues"] = _queues()
	checks["disk"] = _disk()
	checks["gateway"] = _gateway()
	checks["modes"] = _modes()
	return checks


def _verdict(state, **detail):
	return {"state": state, **detail}


def _database():
	started = time.perf_counter()
	try:
		frappe.db.sql("select 1")
		return _verdict(OK, latency_ms=round((time.perf_counter() - started) * 1000, 1))
	except Exception as exception:
		return _verdict(DOWN, error=type(exception).__name__)


def _redis(which):
	try:
		if which == "cache":
			frappe.cache().set_value("a3s_health_probe", "1", expires_in_sec=30)
			frappe.cache().get_value("a3s_health_probe")
		else:
			from frappe.utils.background_jobs import get_redis_conn

			get_redis_conn().ping()
		return _verdict(OK)
	except Exception as exception:
		# The app degrades rather than dies without redis: rate limits fail open and the
		# access gate falls back to a database read.
		return _verdict(DEGRADED, error=type(exception).__name__)


def _scheduler():
	try:
		# `enable_scheduler`, not `disable_scheduler` - reading a field that does not
		# exist raises, and the whole health check then reports the site as degraded for
		# a reason that has nothing to do with the site.
		enabled = cint(frappe.db.get_single_value("System Settings", "enable_scheduler"))
		disabled = not enabled
		last = frappe.db.get_value(
			"Scheduled Job Type", {"method": ["like", "a3_sola.%"]}, "last_execution",
			order_by="last_execution desc")
		if disabled:
			return _verdict(DEGRADED, reason="the scheduler is disabled", last_run=str(last))
		return _verdict(OK if last else DEGRADED, last_run=str(last) if last else None)
	except Exception as exception:
		return _verdict(DEGRADED, error=type(exception).__name__)


def _jobs():
	"""Per-module heartbeat freshness. The check that catches a silent stop."""
	from a3_sola.api.monitoring import heartbeat

	try:
		rows = heartbeat.status()
		stopped = [r for r in rows if not r["healthy"]]
		if not rows:
			return _verdict(DEGRADED, reason="no jobs are registered")
		if len(stopped) == len(rows):
			return _verdict(DOWN, watched=len(rows), stopped=len(stopped),
			                reason="every background job has stopped")
		if stopped:
			return _verdict(DEGRADED, watched=len(rows), stopped=len(stopped),
			                methods=[r["method"] for r in stopped][:10])
		return _verdict(OK, watched=len(rows), stopped=0)
	except Exception as exception:
		return _verdict(DEGRADED, error=type(exception).__name__)


def _queues():
	try:
		from frappe.utils.background_jobs import get_queue

		out, worst = {}, OK
		for name in ("short", "default", "long"):
			queue = get_queue(name)
			depth = len(queue)
			oldest = 0
			if depth:
				jobs = queue.jobs[:1]
				if jobs and jobs[0].enqueued_at:
					oldest = (now_datetime() - jobs[0].enqueued_at.replace(tzinfo=None)
					          ).total_seconds()
			state = OK
			if depth > QUEUE_CRITICAL:
				state = DOWN
			elif depth > QUEUE_WARN or oldest > QUEUE_AGE_WARN:
				state = DEGRADED
			out[name] = {"depth": depth, "oldest_seconds": round(oldest), "state": state}
			worst = _worse(worst, state)
		return _verdict(worst, **out)
	except Exception as exception:
		return _verdict(DEGRADED, error=type(exception).__name__)


def _disk():
	try:
		import shutil

		usage = shutil.disk_usage(frappe.get_site_path())
		free_percent = round(usage.free * 100.0 / usage.total, 1)
		state = OK
		if free_percent < DISK_CRITICAL_PERCENT:
			state = DOWN
		elif free_percent < DISK_WARN_PERCENT:
			state = DEGRADED
		return _verdict(state, free_percent=free_percent,
		                free_gb=round(usage.free / 1024 ** 3, 1))
	except Exception as exception:
		return _verdict(DEGRADED, error=type(exception).__name__)


def _gateway():
	"""Reachability, not a transaction. Reported from the recent webhook and payment
	record rather than by calling out, because a health check that makes an outbound
	request on every poll is its own denial of service."""
	try:
		from frappe.utils import add_to_date

		since = add_to_date(now_datetime(), hours=-6)
		verified = frappe.db.count("Payment Webhook Log",
		                           {"received_on": [">", since], "signature_verified": 1})
		unverified = frappe.db.count("Payment Webhook Log",
		                             {"received_on": [">", since], "signature_verified": 0})
		if unverified and unverified > max(5, verified):
			return _verdict(DEGRADED, verified=verified, unverified=unverified,
			                reason="signature failures outnumber verified deliveries")
		return _verdict(OK, verified_6h=verified, unverified_6h=unverified)
	except Exception as exception:
		return _verdict(DEGRADED, error=type(exception).__name__)


def _modes():
	"""The switches somebody will forget production is in.

	Not a health state - it is never wrong to have postings off - but it belongs on the
	page a person opens at 3am, because "why is nothing posting" has this answer more
	often than any other.
	"""
	from a3_sola.api.settings import get_value

	return _verdict(OK, **{
		"accounting_postings": bool(cint(get_value("enable_accounting_postings", 0))),
		"payment_postings": bool(cint(get_value("enable_payment_postings", 0))),
		"automatic_suspension": bool(cint(get_value("enable_automatic_suspension", 0))),
		"lifecycle_dry_run": bool(cint(get_value("dry_run_mode", 1))),
		"lifecycle_kill_switch": bool(cint(get_value("lifecycle_kill_switch", 0))),
		"provisioning_mode": get_value("provisioning_mode"),
		"maintenance_mode": bool(cint(get_value("maintenance_mode", 0))),
	})


ORDER = {OK: 0, DEGRADED: 1, DOWN: 2}


def _worse(a, b):
	return a if ORDER.get(a, 0) >= ORDER.get(b, 0) else b


def _overall(checks):
	state = OK
	for name, check in checks.items():
		if name == "modes":
			continue  # a mode is a fact, not a fault
		state = _worse(state, check.get("state", OK))
	return state
