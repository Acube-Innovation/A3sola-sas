# Lifecycle runbook

What to do, in order, on an ordinary morning — and what to do on the mornings that are not
ordinary.

---

## The daily rhythm

**1. Revenue at Risk.** Open this first. It is sorted by lifetime value, not by how overdue
the account is, because ten days late on your largest customer matters more than thirty
days late on your smallest. Anything near the top with a `Next Change` date this week is a
phone call today.

**2. The approval queue** — Access Suspension, filtered to Pending Approval. Each row
carries what you need to decide in about ten seconds: outstanding amount, days overdue,
dunning history, lifetime value, last payment, and whether the warning was sent in time.
Approve, or reject with a reason. **Doing nothing is a valid answer** — nothing is ever
suspended because a date passed.

**3. Engagement Signals**, once a week. The tenants at the top have not logged in for a
month. They are going to cancel; you just have not been told yet. This is a better
predictor of churn than payment status and it gives you far more warning.

**4. Trial Pipeline**, if you run trials. The rows saying "nobody has ever signed in" are
the ones to call today.

---

## "Why was I suspended?"

One search. Open **Lifecycle Decision Audit**, filter by the tenant, and read down. Every
state change, policy evaluation and access change is there with its reason, its trigger,
who or what did it, and whether it was a dry run.

The event log is append-only, so what it says is what happened — nothing has been tidied
up afterwards. If you need to correct the record, write a new event; the original stays.

---

## Reversing a suspension you should not have made

**Restore first, investigate second.** Restoration needs no approval and takes seconds.

    Access Suspension -> the record -> Restore

Or from the Tenant, or from the payment webhook — all three reach the same function. Each
user goes back to the state they were recorded in, which is not the same as "everybody
enabled": somebody the customer had disabled before the suspension stays disabled.

Then reject or annotate the suspension so the audit trail says what happened and why.

---

## A gateway outage

This is the scenario the circuit breaker exists for. Payments are failing for a reason
that has nothing to do with your customers.

**If the engine has not run yet:**

1. Pull the kill switch, with a reason:
   `bench --site <site> execute a3_sola.api.lifecycle.admin.kill_switch --kwargs "{'on': 1, 'reason': 'Acquirer outage'}"`
   Evaluation and logging carry on; nothing changes state.
2. Fix the outage.
3. Turn it off.

**If the engine already ran and suspended people:**

1. Kill switch on, so it does not happen again tonight.
2. `bulk_restore` with the tenant list and a reason. One event per tenant, never one for
   the batch.
3. `bulk_extend_grace` for everyone the outage pushed towards suspension, so they are not
   suspended again tomorrow for a failure that was yours.

**If the circuit breaker already halted the run** — which is what should happen — nobody
was suspended and you have an alert naming everyone who would have been. Read the list. If
it is the outage, extend grace and carry on. Nothing needs undoing.

---

## Extending grace

    Platform Subscription -> Extend Grace

Mandatory reason, capped at 30 days. For one customer who has told you the payment is
coming, or in bulk after an incident. Every extension writes its own event, so the customer
who asks "why did I get an extra fortnight" has an answer.

---

## A disputed cancellation

1. Open the Cancellation Request. It carries the reason, their own words, whether a
   competitor was named and whether they said they would reconsider.
2. If they are still inside the reactivation window, reactivation is one action and
   restores their exact prior state — the same users, enabled exactly as they were.
3. Past the window it is an internal operation rather than self-service, but nothing has
   been deleted. **Nothing is ever auto-terminated.** After the retention window a tenant
   is flagged for review, and termination stays the guarded Phase 6 flow, which archives
   and disables a Company but never removes it.
4. If they dispute the cancellation itself, `withdraw` puts them back to Active and records
   the retention outcome.

---

## The engine has stopped

The most likely way this whole area fails is not a wrong decision — it is the job quietly
not running, for weeks, with nothing visibly broken.

`alert_on_missing_heartbeat` runs daily and alerts if the last run was two or more days
ago. If that alert fires:

1. Check the scheduler is running at all: `bench --site <site> doctor`.
2. Look in Scheduled Job Log for `run_lifecycle`.
3. Run it by hand to see the error:
   `bench --site <site> execute a3_sola.api.lifecycle.engine.run_lifecycle`.

The heartbeat streak also gates the pre-flight check, so an engine that has been down
cannot have automatic suspension switched on until it has been up for a week again.

---

## Before switching automatic suspension on

    bench --site <site> execute a3_sola.api.lifecycle.admin.run_simulation

Read every line. Then:

    bench --site <site> execute a3_sola.api.lifecycle.admin.preflight

Each check reports pass or fail and names what is missing. When they all pass, enabling
still requires typing `SUSPEND CUSTOMERS` — because from that point the engine can block a
paying customer's access with nobody watching.

---

## The commands, in one place

| Task | Command |
|------|---------|
| Run the engine now | `a3_sola.api.lifecycle.engine.run_lifecycle` |
| Simulate, writing nothing | `a3_sola.api.lifecycle.admin.run_simulation` |
| Pre-flight check | `a3_sola.api.lifecycle.admin.preflight` |
| Kill switch on/off | `a3_sola.api.lifecycle.admin.kill_switch` |
| Restore one tenant | `a3_sola.api.lifecycle.suspension.restore` |
| Bulk restore | `a3_sola.api.lifecycle.admin.bulk_restore` |
| Bulk extend grace | `a3_sola.api.lifecycle.admin.bulk_extend_grace` |
| One page for a tenant | `a3_sola.api.lifecycle.admin.tenant_360` |
| Rebuild the demo | `a3_sola.demo.generate_lifecycle_demo.run` |
