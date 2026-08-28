# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Running the steps, exactly once, in order, and knowing what to do when one fails.

Three properties this file exists to guarantee:

**Exactly once.** Webhook delivery is at-least-once, so `run_provisioning` will be called
again for a subscription that is already provisioned. The idempotency key is derived from
the subscription rather than from the event, so every one of those calls finds the same
Provisioning Job. Concurrent calls serialise on a named lock; the loser does not proceed
in parallel, it returns the job the winner is running.

**Resume, not restart.** A job that failed at step 7 resumes at step 7. Restarting from
step 1 would re-run a completed Company creation, which is precisely the bug the
idempotency key exists to prevent - it would just move it one level down.

**Rollback before the line, never after it.** Steps are ordered so everything reversible
happens first. A failure before the point of no return unwinds the completed reversible
steps in reverse and leaves the system as it was. A failure after it stops, records what
exists, and tells a human. It does not try to clean up: a half-built tenant somebody is
told about is far safer than an automated cleanup that deletes the wrong company.
"""

import time

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from a3_sola.api.provisioning import steps as step_module
from a3_sola.api.provisioning.context import ProvisioningContext
from a3_sola.api.settings import get_int, get_value

LOCK_TIMEOUT = 900
TERMINAL_STATUSES = ("Completed", "Cancelled")


# --------------------------------------------------------------------- entry
def run_provisioning(subscription_name, triggered_by="Payment Webhook", force=False):
	"""Provision one subscription. Safe to call any number of times.

	Returns the Provisioning Job name in every case - including the cases where it did
	nothing, because the caller usually wants to link to the job rather than know whether
	this particular call was the one that did the work.
	"""
	with _subscription_lock(subscription_name) as acquired:
		if not acquired:
			existing = _job_for(subscription_name)
			if existing:
				return existing
			# Another worker holds the lock but has not written its job yet. Returning
			# None is honest: this call did nothing and there is nothing to point at.
			return None

		subscription = frappe.get_doc("Platform Subscription", subscription_name)
		job_name = _job_for(subscription_name)
		if job_name:
			job = frappe.get_doc("Provisioning Job", job_name)
			if job.status == "Completed" and not force:
				return job.name
			if job.status == "Running" and not force:
				return job.name
			if job.status == "Queued" and _mode() == "Manual Approval" and not force:
				return job.name
			if job.status in ("Failed", "Failed Past Point of No Return", "Rolled Back"):
				if not force and cint(job.attempt_number) >= _max_retries():
					return job.name
				job.db_set("attempt_number", cint(job.attempt_number) + 1, update_modified=False)
		else:
			job = _create_job(subscription, triggered_by)
			if _mode() == "Manual Approval" and not force:
				job.db_set("status", "Queued", update_modified=False)
				job.db_set(
					"failure_summary",
					_("Waiting for an administrator to approve provisioning."),
					update_modified=False,
				)
				frappe.db.commit()
				return job.name

		return _execute(job, subscription, triggered_by)


@frappe.whitelist()
def enqueue_provisioning(subscription_name, triggered_by="Manual"):
	"""Queue a run. This is what everything outside the worker calls."""
	from a3_sola.api.permissions import require_role

	if triggered_by != "Payment Webhook":
		require_role(
			("Platform Provisioning Operator", "Platform Tenant Manager", "Platform Admin",
			 "System Manager"),
			_("Starting provisioning"),
		)
	return enqueue(subscription_name, triggered_by)


def enqueue(subscription_name, triggered_by="Payment Webhook", force=False):
	"""Hand the work to a background job. Provisioning never runs in a web request.

	Under test the work runs inline: the suite needs the result, and Frappe's `enqueue`
	reaches redis even in tests, which hands the job to whatever worker happens to be up
	and makes the outcome depend on the developer's bench rather than on the code.
	"""
	if frappe.flags.in_test or frappe.flags.in_provisioning_inline:
		return run_provisioning(subscription_name, triggered_by, force=force)
	frappe.enqueue(
		"a3_sola.api.provisioning.orchestrator.run_provisioning",
		queue=get_value("provisioning_queue") or "long",
		timeout=(get_int("provisioning_timeout_minutes", 15) or 15) * 60,
		job_name=f"a3s-provision-{subscription_name}",
		subscription_name=subscription_name,
		triggered_by=triggered_by,
		force=force,
		enqueue_after_commit=True,
	)
	return _job_for(subscription_name)


# ------------------------------------------------------------------ execution
def _execute(job, subscription, triggered_by):
	from a3_sola.api.provisioning.strategies import get_strategy

	started = time.monotonic()
	job.db_set(
		{
			"status": "Running",
			"started_on": now_datetime(),
			"triggered_by": triggered_by,
			"failure_summary": None,
		},
		update_modified=False,
	)
	frappe.db.commit()

	context = ProvisioningContext(subscription, job=job, triggered_by=triggered_by)
	if job.tenant and frappe.db.exists("Tenant", job.tenant):
		context.tenant = frappe.get_doc("Tenant", job.tenant)
		context.company = context.tenant.company
		context.artefacts["tenant_code"] = context.tenant.tenant_code
		if context.tenant.subscription_plan:
			context.snapshot_entitlements(
				context.tenant.subscription_plan, context.tenant.additional_users
			)
	# The strategy comes from the tenant's snapshot when one exists, so a later change to
	# the site-wide setting cannot reclassify a tenant mid-run.
	context.strategy = get_strategy(
		context.tenant.tenancy_strategy if context.tenant else (get_value("tenancy_strategy") or "Multi Company")
	)
	job.db_set("tenancy_strategy", context.strategy.name, update_modified=False)

	# --- the loop
	completed = {row.step_code for row in job.steps if row.status == "Completed"}
	total = len(step_module.ORDER)
	for index, step in enumerate(step_module.steps(), start=1):
		if step.step_code in completed:
			continue
		log = _step_log(job, step)
		if step.is_point_of_no_return and not cint(job.point_of_no_return_passed):
			job.db_set("point_of_no_return_passed", 1, update_modified=False)
			frappe.db.commit()

		job.db_set(
			{"current_step": step.step_code, "progress_percent": round((index - 1) * 100.0 / total, 1)},
			update_modified=False,
		)
		_set_log(job, log, {"status": "Running", "started_on": now_datetime(),
		                    "attempt_number": cint(job.attempt_number) or 1})
		frappe.db.commit()

		step_started = time.monotonic()
		try:
			result = step.execute(context) or {}
		except Exception as exception:
			frappe.db.rollback()
			job.reload()
			log = _step_log(job, step)
			_set_log(
				job, log,
				{
					"status": "Failed",
					"completed_on": now_datetime(),
					"duration_seconds": round(time.monotonic() - step_started, 3),
					"error_message": str(exception)[:500],
					"error_traceback": frappe.get_traceback(),
				},
			)
			frappe.db.commit()
			return _handle_failure(job, context, step, exception, started)

		_set_log(
			job, log,
			{
				"status": "Completed",
				"completed_on": now_datetime(),
				"duration_seconds": round(time.monotonic() - step_started, 3),
				"created_doctype": (result or {}).get("created_doctype"),
				"created_name": (result or {}).get("created_name"),
				"remarks": (result or {}).get("remarks"),
			},
		)
		# Committed after every step, so a crash leaves an accurate picture of where it
		# stopped rather than an empty job and a half-built company.
		frappe.db.commit()

	job.db_set(
		{
			"status": "Completed",
			"current_step": None,
			"progress_percent": 100,
			"completed_on": now_datetime(),
			"duration_seconds": round(time.monotonic() - started, 3),
			"requires_manual_intervention": 0,
			"failure_summary": None,
		},
		update_modified=False,
	)
	if context.warnings:
		job.db_set("intervention_notes", "\n".join(context.warnings)[:2000], update_modified=False)
	frappe.db.commit()
	return job.name


def _handle_failure(job, context, step, exception, started):
	summary = f"{step.step_code}: {exception}"[:500]
	past_the_line = cint(job.point_of_no_return_passed)

	if past_the_line:
		# Deliberately no cleanup. See the module docstring.
		job.db_set(
			{
				"status": "Failed Past Point of No Return",
				"requires_manual_intervention": 1,
				"failure_summary": summary,
				"completed_on": now_datetime(),
				"duration_seconds": round(time.monotonic() - started, 3),
			},
			update_modified=False,
		)
		if context.tenant:
			frappe.db.set_value(
				"Tenant", context.tenant.name,
				{"status": "Provisioned with Errors", "status_reason": summary},
				update_modified=False,
			)
		frappe.db.commit()
		_alert_failure(job, context, step, exception, destructive_cleanup_skipped=True)
		return job.name

	rolled_back = _rollback(job, context)
	job.db_set(
		{
			"status": "Rolled Back" if rolled_back else "Failed",
			"failure_summary": summary,
			"requires_manual_intervention": 0 if rolled_back else 1,
			"completed_on": now_datetime(),
			"duration_seconds": round(time.monotonic() - started, 3),
		},
		update_modified=False,
	)
	frappe.db.commit()
	_alert_failure(job, context, step, exception, destructive_cleanup_skipped=False)
	return job.name


def _rollback(job, context):
	"""Unwind the completed reversible steps, newest first. Returns True if all unwound."""
	job.reload()
	clean = True
	done = [row for row in job.steps if row.status == "Completed"]
	for row in sorted(done, key=lambda r: cint(r.sequence), reverse=True):
		step = step_module.step_for(row.step_code)
		if not step or not step.is_reversible:
			continue
		try:
			step.rollback(context, row)
			frappe.db.set_value(
				"Provisioning Step Log", row.name, "status", "Rolled Back", update_modified=False
			)
			frappe.db.commit()
		except Exception:
			clean = False
			frappe.db.rollback()
			frappe.db.set_value(
				"Provisioning Step Log", row.name,
				{"status": "Failed", "error_message": _("Rollback failed - see the Error Log.")[:500]},
				update_modified=False,
			)
			frappe.db.commit()
			frappe.log_error(
				title="a3_sola: provisioning rollback failed",
				message=f"Job {job.name} step {row.step_code}\n\n{frappe.get_traceback()}",
			)
	return clean


# ----------------------------------------------------------------- job records
def idempotency_key(subscription_name):
	"""Derived from the subscription, not the event.

	Keying on the webhook event would give every redelivery its own key and defeat the
	whole purpose. One subscription gets one provisioning run, forever.
	"""
	return f"provision::{subscription_name}"


def _job_for(subscription_name):
	return frappe.db.get_value(
		"Provisioning Job", {"idempotency_key": idempotency_key(subscription_name)}, "name"
	)


def _create_job(subscription, triggered_by):
	order = frappe.db.get_value(
		"Payment Order",
		{"platform_subscription": subscription.name, "status": "Paid"},
		"name",
		order_by="paid_on asc",
	)
	job = frappe.new_doc("Provisioning Job")
	job.update(
		{
			"platform_subscription": subscription.name,
			"payment_order": order,
			"subscription_signup": subscription.subscription_signup,
			"idempotency_key": idempotency_key(subscription.name),
			"triggered_by": triggered_by,
			"triggered_on": now_datetime(),
			"status": "Queued",
			"attempt_number": 1,
			"tenancy_strategy": get_value("tenancy_strategy") or "Multi Company",
		}
	)
	for step in step_module.steps():
		job.append(
			"steps",
			{
				"step_code": step.step_code,
				"step_name": step.step_name,
				"sequence": step.sequence,
				"is_reversible": cint(step.is_reversible),
				"status": "Pending",
			},
		)
	job.flags.ignore_permissions = True
	job.insert(ignore_permissions=True)
	job.submit()
	frappe.db.commit()
	return job


def _step_log(job, step):
	for row in job.steps:
		if row.step_code == step.step_code:
			return row
	row = job.append(
		"steps",
		{
			"step_code": step.step_code,
			"step_name": step.step_name,
			"sequence": step.sequence,
			"is_reversible": cint(step.is_reversible),
			"status": "Pending",
		},
	)
	job.flags.ignore_validate_update_after_submit = True
	job.save(ignore_permissions=True)
	return row


def _set_log(job, row, values):
	frappe.db.set_value("Provisioning Step Log", row.name, values, update_modified=False)
	for key, value in values.items():
		setattr(row, key, value)


# ---------------------------------------------------------------------- locking
class _subscription_lock:
	"""One provisioning run per subscription at a time.

	Redis `SET NX` rather than a database row: the lock has to hold across a transaction
	rollback, and a row-based lock would be released by the very rollback a failing step
	triggers.
	"""

	def __init__(self, subscription_name):
		self.key = f"a3s-provision-lock::{subscription_name}"
		self.conn = None
		self.held = False

	def __enter__(self):
		try:
			self.conn = frappe.cache()
			self.held = bool(
				self.conn.set(self.conn.make_key(self.key), "1", nx=True, ex=LOCK_TIMEOUT)
			)
		except Exception:
			# A cache outage must not stop a paid customer being provisioned. The
			# idempotency key is still enforced by a unique constraint underneath, so the
			# worst case is a second call finding the job already there.
			frappe.log_error(
				title="a3_sola: provisioning lock unavailable",
				message=frappe.get_traceback(),
			)
			self.conn = None
			self.held = True
		return self.held

	def __exit__(self, *exc):
		if self.conn and self.held:
			try:
				self.conn.delete_value(self.key)
			except Exception:
				pass
		return False


def _mode():
	return get_value("provisioning_mode") or "Automatic"


def _max_retries():
	return get_int("max_provisioning_retries", 3) or 3


# ------------------------------------------------------------------- watchdog
def watchdog():
	"""Scheduled. A job that stopped without saying so is worse than one that failed."""
	timeout = get_int("provisioning_timeout_minutes", 15) or 15
	cutoff = add_to_date(now_datetime(), minutes=-timeout)
	stuck = frappe.get_all(
		"Provisioning Job",
		filters={"status": "Running", "started_on": ["<", cutoff]},
		fields=["name", "current_step", "started_on", "tenant"],
	)
	for row in stuck:
		frappe.db.set_value(
			"Provisioning Job", row.name,
			{
				"status": "Failed",
				"requires_manual_intervention": 1,
				"failure_summary": _("Timed out after {0} minutes at step {1}.").format(
					timeout, row.current_step or "?"
				),
				"completed_on": now_datetime(),
			},
			update_modified=False,
		)
		if row.tenant:
			frappe.db.set_value(
				"Tenant", row.tenant,
				{"status": "Provisioned with Errors",
				 "status_reason": _("Provisioning timed out.")},
				update_modified=False,
			)
		frappe.log_error(
			title="a3_sola: provisioning timed out",
			message=(
				f"Job {row.name} was still Running {timeout} minutes after it started, at "
				f"step {row.current_step}. It has been marked Failed and needs a human."
			),
		)
	frappe.db.commit()
	return {"timed_out": len(stuck)}


def alert_on_open_interventions():
	"""Daily. Anything waiting on a human for too long should be said out loud."""
	hours = get_int("provisioning_failure_alert_age_hours", 24) or 24
	cutoff = add_to_date(now_datetime(), hours=-hours)
	open_jobs = frappe.get_all(
		"Provisioning Job",
		filters={"requires_manual_intervention": 1, "resolved_on": ["is", "not set"],
		         "modified": ["<", cutoff]},
		fields=["name", "tenant", "current_step", "failure_summary", "modified"],
	)
	if not open_jobs:
		return {"open": 0}
	lines = [
		f"{row.name} ({row.tenant or 'no tenant'}) stuck at {row.current_step}: {row.failure_summary}"
		for row in open_jobs
	]
	frappe.log_error(
		title="a3_sola: provisioning needs a human",
		message=(
			f"{len(open_jobs)} provisioning job(s) have been waiting for intervention for "
			f"more than {hours} hours.\n\n" + "\n".join(lines)
		),
	)
	return {"open": len(open_jobs)}


def _alert_failure(job, context, step, exception, destructive_cleanup_skipped):
	tenant = context.tenant.name if context.tenant else "(none)"
	artefacts = "\n".join(
		f"  {code}: " + ", ".join(f"{a['doctype']} {a['name']}" for a in items)
		for code, items in context.artefacts.items()
		if isinstance(items, list)
	)
	message = (
		f"Provisioning job {job.name} failed at {step.step_code} ({step.step_name}).\n"
		f"Subscription: {job.platform_subscription}\nTenant: {tenant}\n\n"
		f"Error: {exception}\n\n"
	)
	if destructive_cleanup_skipped:
		message += (
			"This failure is PAST THE POINT OF NO RETURN. Nothing has been rolled back, "
			"deliberately. What exists now:\n"
			f"{artefacts or '  (nothing recorded)'}\n\n"
			"See docs/PROVISIONING_RUNBOOK.md before touching anything.\n\n"
		)
	else:
		message += "Everything before the failure was rolled back.\n\n"
	message += frappe.get_traceback()
	frappe.log_error(title=f"a3_sola: provisioning failed ({step.step_code})", message=message)
	_notify_role(job, step, exception, destructive_cleanup_skipped)


def _notify_role(job, step, exception, urgent):
	role = get_value("notify_on_failure_role")
	if not role or frappe.flags.in_test or frappe.flags.in_demo:
		return
	recipients = frappe.get_all(
		"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"
	)
	recipients = [r for r in recipients if frappe.db.get_value("User", r, "enabled")]
	if not recipients:
		return
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=_("Provisioning {0}: {1}").format(
				_("needs a human") if urgent else _("rolled back"), job.name
			),
			message=(
				f"<p>Provisioning job <b>{job.name}</b> failed at <b>{step.step_name}</b>.</p>"
				f"<p>{frappe.utils.escape_html(str(exception))}</p>"
				+ ("<p><b>This one is past the point of no return - nothing was rolled back. "
				   "Read docs/PROVISIONING_RUNBOOK.md before acting.</b></p>" if urgent else "")
			),
			reference_doctype="Provisioning Job",
			reference_name=job.name,
			now=False,
		)
	except Exception:
		frappe.log_error(
			title="a3_sola: provisioning alert not sent", message=frappe.get_traceback()
		)
