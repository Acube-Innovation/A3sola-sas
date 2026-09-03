# Monitoring

Every check, its cadence, its threshold, where it goes, **how often it should fire**, and
what to do when it does.

The frequency column is the important one. An on-call channel that fires twenty times a day
is a channel nobody reads, and the one alert that mattered will be the one missed. Anything
expected more than about twice a week is a dashboard row here, not an alert.

---

## The failure this is mostly for

A scheduler stopping silently. No error, no alert — billing simply does not happen,
renewals are not chased, access is not evaluated. It is found weeks later during a revenue
review.

So the watchdog alerts on **absence**, not on error. Error at least logs something.

### How heartbeats work

Every scheduled job stamps one automatically. Nothing was added to the jobs themselves —
Frappe fires `before_job` and `after_job` around each scheduled call and the heartbeat is
recorded from there. Fifteen decorators on fifteen functions would be fifteen chances for
the sixteenth job to be added without one, and the sixteenth job is exactly the one that
stops quietly.

The heartbeat records when the job ran, how long it took, and any counts it returned — so
"billing ran" becomes "billing ran and collected 14".

**30 jobs are watched**, read from the module registries. A job added in a later release is
watched without anybody editing this document.

### Tolerance

A job is late when it has not run within **2.2×** its own cadence. Not 1×: a daily job
whose window slipped by an hour is not an incident, and an alert that fires on ordinary
jitter gets muted — after which it is no longer an alert.

| Cadence | Alerts after |
|---|---|
| Hourly | 2.2 hours |
| Daily | ~2.2 days |
| Weekly | ~15 days |
| Monthly | ~66 days |

---

## The checks

### Liveness

| Check | Cadence | Threshold | Severity | Expected | On firing |
|---|---|---|---|---|---|
| **Job watchdog** | hourly | any job past 2.2× its cadence | CRITICAL | **never** | `bench doctor`; check the supervisor process for the scheduler |
| **Health endpoint** | external, 60 s | `down` | CRITICAL | never | See the decision tree in `ON_CALL.md` |
| Watchdog's own heartbeat | hourly | — | — | — | A watchdog that dies is caught by the external check on `/api/method/a3_sola.api.health.check` |

### Business

Each is `a3_sola.api.monitoring.alerts`, run daily, routed by severity.

| Code | What it means | Severity | Expected at 50 tenants | On firing |
|---|---|---|---|---|
| `isolation_audit` | The audit found a cross-tenant leak | **CRITICAL** | **never** | Sev-1. `ON_CALL.md`, then `PROVISIONING_RUNBOOK.md` |
| `scheduler_stopped` | Background jobs are not running | **CRITICAL** | never | As above |
| `stuck_provisioning` | A job needs a person for over 4 h | **CRITICAL** | rare | A customer has paid and cannot log in. `PROVISIONING_RUNBOOK.md` |
| `circuit_breaker` | The lifecycle breaker halted a run | **CRITICAL** | never | Nobody was suspended. Almost always a gateway outage — `LIFECYCLE_RUNBOOK.md` |
| `webhook_signature_failures` | >20 bad signatures in 6 h | HIGH | never, normally | Check the webhook secret first; then consider a probe |
| `payment_success_rate` | Below 85% over 7 days | HIGH | a few times a year | Gateway status and the mandate register before assuming customers stopped paying |
| `unmatched_settlements` | Money arrived that is unattributed | NORMAL / HIGH over 20 | weekly | Reconciliation queue |
| `mandate_rejections` | Mandates rejected this week | NORMAL | a few a month | Each is a renewal that will fail |
| `tenants_over_quota` | Active users past the seat quota | NORMAL | a few a month | Usually a plan change never applied |
| `signup_drought` | No signups in 7 days | NORMAL | only when the funnel breaks | **Off until `expect_signups` is set** — otherwise it fires every week before launch and gets muted |

### Deliberately not alerts

These are numbers on the console, checked when somebody looks:

- open provisioning interventions under 4 hours old
- failed webhooks in the last 24 hours
- suspensions pending approval — the queue *is* the interface
- revenue at risk
- tenants by state

---

## The health endpoint

`/api/method/a3_sola.api.health.check` — **public**, rate limited at 120/hour per IP.

Returns exactly:

```json
{"status": "ok", "time": "2026-09-01 11:09:22"}
```

**Nothing else, on purpose.** Not the queue depths, not the versions, not which dependency
is down — an unauthenticated attacker would like every one of those. There is a test that
fails if the word "redis", "queue", "disk", "database", "scheduler", "tenant", "razorpay",
"version" or "error" ever appears in that response.

`/api/method/a3_sola.api.health.detail` — **authenticated**, Platform Admin / Lifecycle
Operator / System Manager. Everything:

| Check | `down` when | `degraded` when |
|---|---|---|
| database | unreachable | — |
| redis cache / queue | — | unreachable (the app degrades: rate limits fail open, the gate falls back to a query) |
| scheduler | — | disabled, or never run |
| background jobs | **all** stopped | some stopped |
| queues | depth > 5,000 | depth > 500, or oldest job > 15 min |
| disk | free < 5% | free < 15% |
| gateway | — | signature failures outnumber verified deliveries in 6 h |
| modes | never | never — a mode is a fact, not a fault |

**Point the uptime monitor at the shallow one, every 60 seconds, alerting on two
consecutive failures.**

---

## Error tracking

Errors are captured with context and **redacted before anything leaves**. A stack trace
containing a GSTIN or a payment reference in an external error service is a data leak, and
it is the kind nobody notices because the trace looks like a trace.

Redacted: GSTIN, PAN, Aadhaar, Razorpay order/payment/mandate references, Razorpay keys,
KSEB consumer numbers, IFSC, bank accounts, email addresses, phone numbers, and anything
labelled password/secret/token/api_key.

Demonstrated:

```
before: customer 32AABCU9603R1ZM paid via order_MkL9x2QaBcDeFg for consumer
        1156500000001, contact ravi@example.com / 9847012345, ifsc ICIC0000289,
        and a quoted password= assignment
after : customer [GSTIN] paid via [GATEWAY-REF] for consumer [CONSUMER-NO],
        contact [EMAIL] / [PHONE], ifsc [IFSC], password='[REDACTED]'
```

The user is **hashed, not named**: knowing one user hits an error a hundred times is the
useful part; knowing which person rarely is.

**Grouping.** Errors are fingerprinted on the exception type and the last few stack frames
— not line numbers, which move on every edit, and not the message, which carries the very
identifiers that make each occurrence look unique. One recurring failure repeated four
thousand times otherwise drowns the one that happened once, and the one that happened once
is usually the interesting one.

**Before pointing an external service at this site**, run
`a3_sola.api.monitoring.errors.scrub_existing` — traces written before the redactor existed
still carry whatever was in them.

**Retention.** Error Log has none by default and reached **165 MB on this bench, half the
database**. `purge_error_log` now runs daily at `error_log_retention_days` (30).

---

## Audit and observability

`Platform Audit` — one report across all four trails, filterable by tenant, actor, date and
source:

| Source | What it carries |
|---|---|
| Platform Audit Entry | Refunds, manual payment overrides, credential and mode changes, support sessions — hash-chained |
| Subscription Event | Every access and state change — append-only |
| Access Suspension | Who was suspended, who approved, how many users, what restored it |
| Plan / Seat Change Request | Every entitlement change |

This is what you produce when a customer asks what happened to their account, or an auditor
asks how a figure arose.

---

## What is not monitored

Stated so nobody assumes otherwise:

- **Nothing routes anywhere yet.** Alerts go to `lifecycle_alert_role` by email and to the
  Error Log. There is no Slack, PagerDuty or Sentry integration — configure one before
  go-live and put the address of a channel somebody actually reads.
- **No external uptime monitor is configured.** The endpoint exists; nothing polls it.
- **No APM.** Per-request latency is measured by the Phase 8 harness on demand, not
  continuously.
- **Certificate expiry, DNS and host metrics** are the deployment platform's, not this
  app's.
