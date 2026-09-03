# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Business alerting, and the discipline that keeps it worth reading.

THE FATIGUE RULE, APPLIED HERE RATHER THAN STATED

Every alert below carries its expected frequency at 50 tenants. Anything expected more
than about twice a week is not an alert - it is a dashboard row - and is marked
`channel="dashboard"` so it never pages anybody. An on-call channel that fires twenty times
a day is a channel nobody reads, and the one that mattered is the one missed.

Severity routes differently on purpose: a cross-tenant isolation failure and a slow report
must not arrive the same way.
"""

import frappe
from frappe.utils import add_days, add_to_date, cint, flt, now_datetime, today

from a3_sola.api.settings import get_float, get_int, get_value

#: severity -> where it goes.
CRITICAL = "critical"   # wake somebody
HIGH = "high"           # same working day
NORMAL = "normal"       # the daily queue
DASHBOARD = "dashboard" # never alerts; it is a number on a page


class Alert:
	__slots__ = ("code", "severity", "title", "detail", "value", "threshold", "expected")

	def __init__(self, code, severity, title, detail, value=None, threshold=None,
	             expected=""):
		self.code = code
		self.severity = severity
		self.title = title
		self.detail = detail
		self.value = value
		self.threshold = threshold
		self.expected = expected

	def as_dict(self):
		return {"code": self.code, "severity": self.severity, "title": self.title,
		        "detail": self.detail, "value": self.value, "threshold": self.threshold,
		        "expected_frequency": self.expected}


# --------------------------------------------------------------------- checks
def payment_success_rate():
	"""Expected: rarely. A drop below the floor is a gateway or a mandate problem."""
	since = add_days(today(), -7)
	captured = frappe.db.count("Payment Transaction",
	                           {"status": "Captured", "creation": [">", since]})
	failed = frappe.db.count("Payment Transaction",
	                         {"status": ["in", ["Failed", "Declined"]],
	                          "creation": [">", since]})
	total = captured + failed
	if total < 10:
		return None  # too few to mean anything; saying so beats a false alarm
	rate = round(captured * 100.0 / total, 1)
	floor = get_float("alert_payment_success_floor", 85.0)
	if rate >= floor:
		return None
	return Alert("payment_success_rate", HIGH,
	             f"Payment success rate is {rate}%",
	             f"{captured} captured and {failed} failed in the last 7 days, against a "
	             f"floor of {floor}%. Check the gateway status and the mandate register "
	             f"before assuming customers stopped paying.",
	             value=rate, threshold=floor, expected="a few times a year")


def webhook_signature_failures():
	"""Expected: never in normal operation. A spike is a misconfigured secret or a probe."""
	since = add_to_date(now_datetime(), hours=-6)
	failures = frappe.db.count("Payment Webhook Log",
	                           {"signature_verified": 0, "received_on": [">", since]})
	limit = get_int("alert_webhook_failure_limit", 20)
	if failures <= limit:
		return None
	return Alert("webhook_signature_failures", HIGH,
	             f"{failures} webhook signature failures in 6 hours",
	             "Either the webhook secret no longer matches what Razorpay is signing "
	             "with - in which case no payment is being confirmed - or somebody is "
	             "probing the endpoint. Check the secret first.",
	             value=failures, threshold=limit, expected="never, in normal operation")


def unmatched_settlements():
	"""Expected: weekly at most. Money that arrived and cannot be attributed."""
	if not frappe.db.exists("DocType", "Settlement Line"):
		return None
	unmatched = frappe.db.count("Settlement Line",
	                            {"match_status": ["!=", "Matched"]})
	if not unmatched:
		return None
	severity = NORMAL if unmatched < 20 else HIGH
	return Alert("unmatched_settlements", severity,
	             f"{unmatched} settlement line(s) unmatched",
	             "Money the bank says arrived that is not attributed to a payment. Until "
	             "it is, the revenue figures are wrong in a way nobody can see.",
	             value=unmatched, expected="weekly")


def stuck_provisioning():
	"""Expected: rare. Every one of these is a paying customer with nothing to log into."""
	hours = get_int("provisioning_failure_alert_age_hours", 4)
	cutoff = add_to_date(now_datetime(), hours=-hours)
	stuck = frappe.get_all("Provisioning Job",
	                       filters={"requires_manual_intervention": 1,
	                                "modified": ["<", cutoff]},
	                       fields=["name", "tenant", "status"], limit=20)
	if not stuck:
		return None
	return Alert("stuck_provisioning", CRITICAL,
	             f"{len(stuck)} provisioning job(s) waiting for a person",
	             "A customer has paid and has nothing to sign into. See "
	             "docs/PROVISIONING_RUNBOOK.md.\n"
	             + "\n".join(f"  {j.name} ({j.tenant}) - {j.status}" for j in stuck),
	             value=len(stuck), threshold=0, expected="rare")


def circuit_breaker_tripped():
	"""Expected: never, unless something is wrong. That is the point of it."""
	since = add_to_date(now_datetime(), hours=-26)
	tripped = frappe.get_all(
		"Subscription Event",
		filters={"event_type": "Policy Evaluated", "event_time": [">", since],
		         "reason": ["like", "%Circuit breaker halted%"]},
		fields=["name", "reason"], limit=5)
	if not tripped:
		return None
	return Alert("circuit_breaker", CRITICAL,
	             "The lifecycle circuit breaker halted a run",
	             "Nobody was suspended, which is correct - but the engine wanted to "
	             "suspend more customers in one night than the limit allows. That is "
	             "almost always a gateway outage or a date bug, not customers deciding "
	             "to stop paying together.\n" + (tripped[0].reason or ""),
	             value=len(tripped), expected="never")


def tenants_over_quota():
	"""Expected: occasionally. A tenant past its seats is a billing conversation."""
	over = frappe.get_all("Tenant",
	                      filters={"status": "Active"},
	                      fields=["name", "user_quota", "active_users"], limit=200)
	breached = [t for t in over if cint(t.active_users) > cint(t.user_quota) > 0]
	if not breached:
		return None
	return Alert("tenants_over_quota", NORMAL,
	             f"{len(breached)} tenant(s) over their seat quota",
	             "The enforcement layer blocks the next user; these are already past. "
	             "Usually a plan change that was never applied.\n"
	             + "\n".join(f"  {t.name}: {t.active_users} of {t.user_quota}"
	                         for t in breached[:10]),
	             value=len(breached), expected="a few times a month")


def mandate_rejections():
	"""Expected: a few a month. Each is a renewal that will fail."""
	since = add_days(today(), -7)
	rejected = frappe.db.count("Payment Mandate",
	                           {"status": ["in", ["Rejected", "Cancelled by Bank"]],
	                            "modified": [">", since]})
	if not rejected:
		return None
	return Alert("mandate_rejections", NORMAL,
	             f"{rejected} mandate(s) rejected this week",
	             "Each is a customer whose next auto-debit will not happen. They need a "
	             "new mandate or a switch to assisted renewal.",
	             value=rejected, expected="a few a month")


def isolation_audit_failed():
	"""Expected: NEVER. This is the one that wakes people."""
	since = add_days(today(), -35)
	failures = frappe.db.count("Error Log",
	                           {"method": ["like", "%isolation audit FAILED%"],
	                            "creation": [">", since]})
	if not failures:
		return None
	return Alert("isolation_audit", CRITICAL,
	             "The isolation audit found a cross-tenant leak",
	             "One customer can read another's data. Treat as Sev-1: see "
	             "docs/ops/ON_CALL.md and docs/PROVISIONING_RUNBOOK.md.",
	             value=failures, threshold=0, expected="never")


def signup_drought():
	"""Expected: only if the funnel breaks. Zero signups where signups are expected."""
	days = get_int("alert_signup_drought_days", 7)
	if not cint(get_value("expect_signups", 0)):
		return None  # off until the client says the funnel is live
	recent = frappe.db.count("Subscription Signup",
	                         {"creation": [">", add_days(today(), -days)]})
	if recent:
		return None
	return Alert("signup_drought", NORMAL,
	             f"No signups in {days} days",
	             "Either demand stopped or the funnel is broken. Check the public site "
	             "renders, the form submits and the verification email sends.",
	             value=0, expected="only when the funnel breaks")


def scheduler_stopped():
	"""Expected: never. Delegated to the watchdog, surfaced here so one call sees all."""
	from a3_sola.api.monitoring import heartbeat

	stopped = heartbeat.missing()
	if not stopped:
		return None
	return Alert("scheduler_stopped", CRITICAL,
	             f"{len(stopped)} background job(s) are not running",
	             "Nothing errors when a scheduler stops. Billing does not happen and "
	             "access is not evaluated.\n"
	             + "\n".join(f"  {r['method']} ({r['cadence']})" for r in stopped[:10]),
	             value=len(stopped), threshold=0, expected="never")


#: Every check, in the order a person would want to read them.
CHECKS = (
	isolation_audit_failed,
	scheduler_stopped,
	stuck_provisioning,
	circuit_breaker_tripped,
	webhook_signature_failures,
	payment_success_rate,
	unmatched_settlements,
	mandate_rejections,
	tenants_over_quota,
	signup_drought,
)


def evaluate():
	"""Run every check. Returns the alerts that fired, worst first."""
	fired = []
	for check in CHECKS:
		try:
			alert = check()
		except Exception:
			frappe.log_error(frappe.get_traceback(),
			                 f"a3_sola: alert check {check.__name__} failed")
			continue
		if alert:
			fired.append(alert)
	order = {CRITICAL: 0, HIGH: 1, NORMAL: 2, DASHBOARD: 3}
	fired.sort(key=lambda a: order.get(a.severity, 9))
	return fired


def run_business_alerts():
	"""Scheduled daily. Routes by severity - the critical ones do not arrive as a digest."""
	from a3_sola.api.lifecycle import notify

	fired = evaluate()
	if not fired:
		return {"fired": 0}

	critical = [a for a in fired if a.severity == CRITICAL]
	for alert in critical:
		notify.alert_internal(f"a3_sola [CRITICAL]: {alert.title}", alert.detail)

	rest = [a for a in fired if a.severity != CRITICAL]
	if rest:
		body = "\n\n".join(
			f"[{a.severity.upper()}] {a.title}\n{a.detail}" for a in rest
		)
		notify.alert_internal(f"a3_sola: {len(rest)} thing(s) to look at today", body)

	return {"fired": len(fired), "critical": len(critical),
	        "codes": [a.code for a in fired]}


@frappe.whitelist()
def current():
	"""What is wrong right now, for the console."""
	from a3_sola.api import permissions

	permissions.require_role(
		("Platform Admin", "Platform Lifecycle Operator", "System Manager"),
		action="read the alert status",
	)
	return [alert.as_dict() for alert in evaluate()]
