# Go-live

Staged, not big-bang. Each stage has entry criteria, what to watch, exit criteria and a
specific rollback.

---

## Stage 0 — internal only

Acube's own team uses the platform as a tenant, for a full billing cycle.

**Entry:** all security findings closed · isolation audit clean · restore proven ·
monitoring alerting somewhere real · staging matches production.

**Configuration:** postings **off**, automatic suspension **off**, dry run **on**,
provisioning **Manual Approval**, public signup **closed**.

**Watch:** the lifecycle engine's decisions daily — it changes nothing, and reading a
cycle's worth is the point. Scheduler heartbeats. Every generated document against real
paperwork.

**Exit:** one full cycle with no Blocker · **every document signed off line by line** by
the client's own team (`UAT_MASTER.md`) · S1 executed for real, signup through to
provisioning, with live keys.

**Rollback:** stop using it. Nothing external depends on it yet.

---

## Stage 1 — two or three friendly pilot tenants

**Entry:** Stage 0 exit met · pilot tenants briefed that they are pilots · support process
defined and staffed.

**Configuration:** unchanged from Stage 0. Provisioning **Manual Approval** — a person
approves each one and watches it run.

**Watch:** provisioning failure rate · the lifecycle engine's decisions against real unpaid
accounts · payment success rate · isolation audit weekly rather than monthly.

**Exit:** three tenants provisioned without intervention · a full billing cycle collected ·
no cross-tenant finding · pilots say it is usable.

**Rollback:** the tenants are real and have paid. **Rollback means forward-fixing.** You can
revert code; you cannot un-provision a customer. Refund and migrate them off manually if it
comes to that.

---

## Stage 2 — postings on

**Entry:** Stage 1 exit met · **the CA's written GST confirmation for both the solar EPC
composite supply and the SaaS subscription** · account mappings complete · the staging
reconciliation ties (below).

**Configuration:** `enable_accounting_postings` and `enable_payment_postings` **on**,
`gst_treatment_confirmed_by_ca` **on**. Automatic suspension still **off**.

**Watch:** every posting for the first week · project profitability against the ledger ·
subscription revenue against the mapped accounts · settlement reconciliation daily.

**Exit:** one month posted and reconciled to the rupee.

**Rollback:** switch postings off. **Entries already made must be reversed by journal, not
deleted.** This is the least reversible stage, which is why the reconciliation comes first.

---

## Stage 3 — public signup

**Entry:** Stage 2 exit met · captcha enabled · legal pages reviewed by a lawyer · refund
and cancellation policy published · support able to absorb the volume.

**Configuration:** public signup **open**. Provisioning stays **Manual Approval** until the
Stage 1–2 failure rate justifies otherwise, then **Automatic**.

**Watch:** signup-to-payment conversion · provisioning failure rate · webhook signature
failures (a spike is a probe) · the first automatic provisioning, closely.

**Exit:** ten self-service signups provisioned automatically with no intervention.

**Rollback:** close signup — one setting, immediate. Anybody already provisioned stays.

---

## Stage 4 — automatic suspension

The last thing to arm, and the one with the most ways to go wrong.

**Entry:** all of the above · **the pre-flight check passes every item** · the simulation
reviewed for a **full cycle** and every line read · the approval role held by somebody who
reads it · the circuit breaker limit set deliberately.

```bash
bench --site <site> execute a3_sola.api.lifecycle.admin.run_simulation
bench --site <site> execute a3_sola.api.lifecycle.admin.preflight
```

**Configuration:** `dry_run_mode` **off**, `enable_automatic_suspension` **on**. Keep
`require_manual_approval_for_suspension` **on** for at least the first cycle.

Enabling requires typing `SUSPEND CUSTOMERS`. That is intentional.

**Watch:** every suspension for the first month · time from payment to restoration, which
should be minutes · the circuit breaker.

**Exit:** one cycle with no wrongful suspension.

**Rollback:** the **kill switch** — immediate, halts every state change while evaluation and
logging continue. Then `bulk_restore` anyone affected.

---

## What is reversible, and what is not

| Reversible in seconds | Reversible with work | **Not reversible** |
|---|---|---|
| Feature flags, kill switch | A code deployment | Money collected |
| Suspension → restore | Postings (reverse by journal) | Emails sent |
| Closing public signup | A tenant migrated off | A tenant provisioned |
| Provisioning mode | | Data a customer has seen |

**Once a real customer has paid and been provisioned, rollback is forward-fixing.** Plan
each stage on that basis.

---

## The staging reconciliation — do not skip it

In **staging**, with the CA confirmation recorded, switch postings on and run a full month
of activity. Then reconcile:

| Reconcile | To |
|---|---|
| Project profitability | The general ledger |
| Subscription revenue | The mapped accounts |
| Subsidy receivable | Its account |
| Settlements | The bank |

**Report it to the rupee.** Do not recommend enabling postings in production until it ties.

> **Status: not done.** It needs a month of staging activity with the CA's confirmation in
> place, and neither exists yet. This is a hard gate on Stage 2.

---

## Launch checklist

Every item binary. Marked honestly.

| # | Item | Status |
|---|---|---|
| 1 | Security findings closed | ✅ 0 Blockers, 0 High; 3 Medium fixed |
| 2 | Isolation audit clean | ✅ 5,871 attempts, 0 successful |
| 3 | Adversarial suite in CI | ✅ fails the build on any success |
| 4 | Secret and PII scans clean | ✅ 0 / 0 / 0 |
| 5 | Dependency audit reviewed | ✅ reported; none reachable from a request |
| 6 | Backups running with files | ⬜ **currently database-only** |
| 7 | Off-site backup destination | ⬜ **none configured** |
| 8 | Restore proven | ✅ 91 s measured, verified |
| 9 | Encryption key stored with backups | ⬜ **procedure documented, not automated** |
| 10 | Monitoring alerting to a real channel | ⬜ **email only; no Slack/PagerDuty** |
| 11 | External uptime check on the health endpoint | ⬜ **not configured** |
| 12 | On-call defined | ⬜ **document written, rota not staffed** |
| 13 | Support process defined | ⬜ client |
| 14 | Captcha on public forms | ⬜ **key not configured** |
| 15 | Legal pages reviewed by a lawyer | ⬜ **not done** |
| 16 | Refund and cancellation policy published | ⬜ **not done** |
| 17 | **GST confirmed in writing — solar EPC** | ⬜ **not done. Gates postings** |
| 18 | **GST confirmed in writing — SaaS** | ⬜ **not done. Gates postings** |
| 19 | RBI AFA threshold verified against current framework | ⬜ **assumed ₹15,000** |
| 20 | Account mappings complete | ⬜ client, with their accountant |
| 21 | Tariff verified against a real bill | ⬜ client |
| 22 | Razorpay live keys configured | ⬜ **test/mock only** |
| 23 | Webhook registered and verified | ⬜ **not against live** |
| 24 | Staging reconciliation ties | ⬜ **not done. Gates Stage 2** |
| 25 | UAT signed off | ⬜ **not done** |
| 26 | **Every generated document checked line by line** | ⬜ **not done. The largest open item** |
| 27 | Starter dataset removed or its password changed | ⬜ **ships with a known password** |

**5 of 27 complete.** Everything ticked is engineering evidence. Everything open needs the
client, their CA, their lawyer, or live credentials — which is the correct division, and
none of it can be closed from here.

---

## The first 30 days

**Week 1, daily:** payment success rate · provisioning failures · scheduler heartbeats ·
Revenue at Risk · every generated document a customer received.

**Weeks 2–4, weekly:** the above · churn reasons · engagement signals (the earliest churn
indicator you have) · settlement reconciliation · isolation audit.

**Early warning, in order of how much notice it gives you:**

1. **Engagement signals** — weeks of warning. A tenant not logging in is leaving
2. **Payment success rate** — days. A dip is the gateway or the mandates
3. **Provisioning failure rate** — immediate. Paid customers unable to start
4. **Scheduler heartbeats** — immediate, and silent without them
5. **Ticket volume by category** — tells you what is confusing rather than broken

**Day 30 review:** the checklist above re-marked · every defect triaged · the staging
reconciliation re-run against production · a decision on Stage 4 if not already taken.
