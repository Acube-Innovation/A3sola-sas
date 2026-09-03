# On call

Severity, escalation, and a decision tree for the five incidents most likely to happen.

---

## Severity

| | Meaning | Response | Examples |
|---|---|---|---|
| **Sev-1** | Customer data exposed, or money moving wrongly | **Immediately, any hour** | Cross-tenant leak; duplicate charging; mass suspension |
| **Sev-2** | Customers cannot work, or cannot pay | Within 1 hour, working hours; immediately if widespread | Site down; every payment failing; a tenant wrongly suspended |
| **Sev-3** | Something is broken but nobody is blocked | Same working day | Scheduler stopped; provisioning stuck; settlements unmatched |
| **Sev-4** | Wrong but harmless | Next working day | A report is slow; an alert is noisy |

**Two rules.**

*Restore first, investigate second.* Restoration needs no approval and takes seconds. Get
the customer working, then find out why.

*If you are not sure whether it is Sev-1, it is Sev-1.* The cost of over-reacting to a
suspected data leak is an hour. The cost of under-reacting is the client's business.

---

## Escalation

1. **On-call engineer** — everything starts here
2. **Platform Admin** — any Sev-1 or Sev-2, or anything unresolved after 30 minutes
3. **Acube engineering lead** — Sev-1, always, immediately
4. **The client** — any Sev-1 touching their data, and any Sev-2 lasting over an hour.
   Tell them before they tell you.

For a suspected cross-tenant exposure, **notify at step 3 before you finish diagnosing.**
It may be a notifiable breach and that clock is not yours to start late.

---

## 1. Cross-tenant exposure — Sev-1

*Trigger: `isolation_audit` alert, or a customer says they can see somebody else's data.*

```
Can you reproduce it?
├─ NO  → Do not close. Run the audit against that tenant:
│         bench --site <site> execute a3_sola.api.security.audit.run_isolation_audit
│         Clean → record it and keep the ticket open a week.
│
└─ YES → STOP. Do not "just fix it".
          1. Capture evidence: the exact URL, user, record, timestamp.
          2. Escalate to the engineering lead NOW. Do not finish diagnosing first.
          3. Contain: suspend the ACCOUNT that can see too much — not the tenant
             whose data is exposed. Their access is not the problem.
          4. Diagnose: almost always a missing User Permission on one user.
                 bench --site <site> execute a3_sola.api.isolation.rerun --args "['<tenant>']"
          5. Fix, then re-run the full attack suite and record the zero.
          6. Work out who else was affected before deciding what to tell whom.
```

**Do not** delete the offending records — they are the evidence.

---

## 2. A scheduler has stopped — Sev-3, Sev-2 after 24 hours

*Trigger: `scheduler_stopped`, or the health endpoint reports degraded.*

```
bench --site <site> execute a3_sola.api.monitoring.heartbeat.status

Is the scheduler running at all?
├─ NO  → bench doctor; restart the supervisor scheduler process.
│         Then confirm: enable_scheduler in System Settings.
│
└─ YES → One job, or all of them?
          ├─ ALL → redis queue is down, or the workers died. Check
          │         /api/method/a3_sola.api.health.detail → queues.
          └─ ONE → It is erroring. Find it:
                    Error Log, filtered to that method.
                    Run it by hand to see the failure.
```

**Nothing catches up on its own.** After the scheduler is back, run the missed jobs
manually — particularly `run_daily_billing`, which will otherwise skip a day of renewals.
It is idempotent; running it twice is safe.

---

## 3. The gateway is down — Sev-2

*Trigger: `payment_success_rate` or `webhook_signature_failures`.*

```
Is it Razorpay, or is it us?
├─ Razorpay status page says outage
│    1. Kill switch ON, with a reason:
│         a3_sola.api.lifecycle.admin.kill_switch  {"on": 1, "reason": "..."}
│       Nothing gets suspended for a failure that is not the customer's.
│    2. Wait. Billing is idempotent and will re-attempt.
│    3. When it returns: kill switch OFF, then bulk_extend_grace for everyone
│       the outage pushed towards suspension.
│
└─ Only OUR requests fail
     → The webhook secret or the API key has changed. Check both.
       Every signature failing is nearly always a secret mismatch, and after a
       RESTORE it is nearly always the encryption key — see BACKUP_AND_DR.md.
```

**If the circuit breaker already halted a run, it worked.** Nobody was suspended. Read the
list it alerted with, extend grace, carry on.

---

## 4. Mass suspension risk — Sev-1 if it has happened, Sev-2 if imminent

*Trigger: `circuit_breaker`, or several customers reporting lockout at once.*

```
Has anybody actually been suspended?
├─ NO (breaker halted) → It worked. Find the cause — usually a gateway outage.
│                         Extend grace, then release.
│
└─ YES → 1. Kill switch ON immediately. Stop it happening again tonight.
          2. RESTORE FIRST. No approval needed, seconds each:
               a3_sola.api.lifecycle.admin.bulk_restore
             Each user goes back to their recorded prior state, including
             anyone the customer had themselves disabled.
          3. Tell the affected customers before they tell you.
          4. Then find out why: Lifecycle Decision Audit, filtered to the window.
          5. bulk_extend_grace so tomorrow's run does not repeat it.
```

---

## 5. Provisioning is stuck — Sev-2

*Trigger: `stuck_provisioning`. A customer has paid and has nothing to log into.*

```
Which step did it stop at?  (open the Provisioning Job)
├─ Before step 09 (CREATE_ADMIN_USER)
│    → Reversible. Roll back and retry:
│        a3_sola.api.provisioning.orchestrator.run_provisioning  (resumes)
│
└─ At or after step 09 — past the point of no return
     → Do NOT retry blindly; you will create a second company.
       Resume from the failed step. See PROVISIONING_RUNBOOK.md,
       which lists every failure state and its specific action.
```

**Always tell the customer.** They have paid. A holding message within the hour is worth
more than a fix within the day.

---

## Before you go off shift

- Every Sev-1 and Sev-2 has a written timeline, even if resolved
- Anything left open is handed over by name, not left in a queue
- The kill switch is **off** unless you deliberately left it on — and if you did, say so
  loudly, because it silently stops all lifecycle enforcement

## The commands worth memorising

```bash
# What is wrong right now
bench --site <site> execute a3_sola.api.monitoring.alerts.current

# Are the jobs running
bench --site <site> execute a3_sola.api.monitoring.heartbeat.status

# Full health
bench --site <site> execute a3_sola.api.health.detail

# Stop all lifecycle action
bench --site <site> execute a3_sola.api.lifecycle.admin.kill_switch --kwargs "{'on': 1, 'reason': '...'}"

# Put a customer back
bench --site <site> execute a3_sola.api.lifecycle.suspension.restore --kwargs "{'tenant': 'TNT-...'}"

# Prove isolation still holds
bench --site <site> execute a3_sola.api.security.audit.run_isolation_audit
```
