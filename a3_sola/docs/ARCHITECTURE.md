# Architecture

Written for the next developer, on their first day.

---

## What this is

One Frappe app, `a3_sola`, doing two jobs at once:

1. **A solar EPC business application** — a Kerala rooftop-solar company's entire
   operation, from a WhatsApp enquiry to the fifth year of an O&M contract.
2. **A SaaS platform that sells it** — public site, signup, Razorpay payments, automated
   tenant provisioning and subscription lifecycle.

Both live in the same app because they share the same records. A tenant's Solar Consumer is
the same doctype whether the tenant is the client themselves or a customer of theirs.

## One app, four modules

```
a3_sola/
├── solar_crm/          enquiry → consumer → survey → design → eligibility → proposal
├── solar_operations/   order → 19 stages → statutory → subsidy → commissioning
├── solar_projects/     costing → milestone billing → O&M → service → warranty
└── platform/           public site → signup → payments → provisioning → lifecycle
```

**Never a fifth module and never a second app.** Every phase has been asked for one and the
answer has been no each time — Frappe's module boundary is a permissions and fixtures
boundary, not an architectural one, and splitting the app would split the registry, the
settings singleton and the permission model with it.

## The registry pattern

Everything a module declares lives in `a3_sola/registry/<module>.py`:

```python
DOCTYPES              = [...]   # every doctype this module owns
PERMISSION_DOCTYPES   = [...]   # those needing company isolation
DOC_EVENTS            = {...}   # hooks
SCHEDULER_EVENTS      = {...}   # background jobs and cadence
FIXTURES              = [...]
WEBSITE_ROUTE_RULES   = [...]
```

`registry/__init__.py` merges them; `hooks.py` reads the merge. **Nothing is registered in
`hooks.py` directly.**

Why it matters, and why you should keep it: every cross-cutting mechanism in this app walks
the registry rather than a hand-written list — the isolation checker, the Phase 8 attack
suite, the permission matrix, the heartbeat watchdog, the tenant data export. Add a doctype
to a registry and it is automatically isolated, attacked, audited and watched. Add it
anywhere else and it is none of those, and nothing tells you.

## One settings singleton

**A3 Sola Settings**, with a tab per phase: General, CRM, Operations, Projects, Platform,
Payments, Provisioning, Lifecycle, Monitoring. Read through `api/settings.py`
(`get_value`, `get_int`, `get_float`), never with a bare `get_single_value`.

There is exactly one. Nothing may create a second.

---

## The tenancy model

**Multi-company on one site.** One Frappe site, one database; each tenant is an ERPNext
Company, and isolation is a User Permission on Company plus permission-query hooks.

The whole of the boundary is that User Permission record. Without it a tenant's user reads
the entire instance and **nothing throws an error** — it looks like a working tenant. That
is why provisioning verifies isolation before handing a tenant over, and why the Phase 8
suite attacks it from 34 directions every time the tests run.

**What would force a migration to multi-site:** a customer contractually requiring physical
separation, a tenant large enough to need its own database, or a regulator requiring
per-tenant encryption keys. See `TENANCY_MODEL.md` for what that migration would involve.

---

## The extension-point map

Each phase deliberately stopped at the edge of a decision the next phase owned. All are now
implemented, and the seams remain seams.

| Extension point | Left by | Filled in | Delegates to |
|---|---|---|---|
| `signup.trigger_provisioning` | 5 | **6** | `api.provisioning.orchestrator` |
| `payment_refund.on_initial_payment_refunded` | 5 | **6** | Tenant suspension; deletes nothing |
| `tenant.set_tenant_access_state` | 6 | **7** | `api.lifecycle.access` |
| `entitlements.add_seats` | 6 | **7** | `api.lifecycle.seats` |
| `platform_subscription.on_subscription_activated` | 5 | **7** | `api.lifecycle.handlers` |
| `platform_subscription.on_billing_cycle_completed` | 5 | **7** | `api.lifecycle.handlers` |
| `platform_subscription.on_payment_failed_final` | 5 | **7** | `api.lifecycle.handlers` |
| `dunning.on_dunning_exhausted` | 5 | **7** | `api.lifecycle.handlers` |

The pattern is worth preserving: **collection never decides what a failed payment costs a
customer, and provisioning never decides when a tenant is switched off.** Those are policy
decisions and they live in one place.

---

## Data model — the spine

```
Lead
 └─ Solar Consumer ──────────────────────────────────┐
     ├─ Site Survey → Solar Design Estimate          │
     │                 ├─ Subsidy Eligibility Check  │
     │                 └─ Solar Proposal → Quotation │
     │                                     └─ Sales Order
     └─────────────────────────────── Solar Installation
          ├─ Installation Work Order → Installation Snag
          ├─ Portal Application → Statutory Fee Payment → Statutory Fee Recovery
          ├─ Loan Application, Subsidy Claim
          ├─ Commissioning Report → Net Metering Agreement
          └─ Project
              ├─ Solar Billing Plan → Sales Invoice
              └─ Solar OM Contract
                  ├─ Solar OM Visit → Service Ticket → Solar Warranty Claim
                  └─ Generation Reading

Subscription Signup
 ├─ Payment Order → Payment Transaction, Subscription Invoice
 ├─ Platform Subscription → Payment Mandate
 │    ├─ Subscription Event  (append-only)
 │    ├─ Access Suspension → Suspended User Snapshot
 │    └─ Plan / Seat / Cancellation Request
 └─ Provisioning Job → Tenant → Tenant Invitation
```

Every link above is navigable in the desk: each doctype carries a Connections panel with a
**+** that creates the next document already linked back.

## Doctype inventory

127 doctypes across the four modules. The full list with naming series is in the README's
*Doctype inventory* section, generated from the registries.

---

## Schedulers

| Cadence | Job | What it does |
|---|---|---|
| hourly | `api.sla.hourly_sla_scan` | Escalates tickets breaching their window |
| hourly | `api.reconciliation.gateway_health_check` | Gateway reachability |
| **hourly** | `api.monitoring.heartbeat.watchdog` | **Alerts on a job that has stopped** |
| daily | `api.billing_engine.run_daily_billing` | Recurring collection |
| daily | `api.dunning.run_dunning` | Chases failures |
| daily | `api.lifecycle.engine.run_lifecycle` | Evaluates every subscription against its policy |
| daily | `api.lifecycle.engine.alert_on_missing_heartbeat` | The engine's own liveness |
| daily | `api.lifecycle.suspension.remind_pending` | Suspensions awaiting a decision |
| daily | `api.monitoring.alerts.run_business_alerts` | Business anomalies, routed by severity |
| daily | `api.monitoring.jobs.purge_error_log` | Error Log retention |
| daily | `api.escalation.daily_escalation` | Installations stalled against stage SLA |
| daily | `api.om.mark_due_and_missed_visits` / `detect_renewals` | O&M obligations |
| daily | `api.outreach.daily_followup_scan` | Lead follow-ups falling due |
| daily | `api.entitlements.recalculate_all_usage` | Seat drift |
| daily | `api.funnel_jobs.*` | Signup chasing, personal-data purge |
| daily (long) | `api.costing.nightly_cost_refresh` | Rebuilds project costs |
| weekly | `api.funnel_jobs.weekly_funnel_summary` | Funnel digest to sales |
| monthly | `api.accounting_payments.release_deferred_revenue` | Revenue recognition |
| monthly | `api.isolation.monthly_isolation_sweep` | Per-tenant isolation re-check |
| monthly | `api.security.audit.monthly_isolation_audit` | The adversarial suite against live data |

**Every one writes a heartbeat automatically** via the `before_job`/`after_job` hooks. The
watchdog alerts on absence — the failure mode nobody notices.

---

## Integrations

| What | Where | Notes |
|---|---|---|
| **Razorpay** | `api/gateways/` | Behind an interface with a mock implementation. Webhooks are HMAC-verified, idempotent on event id, and always answer 200 |
| **Email** | Frappe | Templates are records, not code |
| **KSEB / national portal** | none | Deliberately. Documents are generated for a human to submit; no scraping, no unofficial API |

---

## Where the important logic lives

| Concern | Module | Why there |
|---|---|---|
| Tenant isolation | `api/permissions.py` | One implementation, used by every module |
| Money | `api/payments.py`, `billing_engine.py`, `accounting*.py` | Postings gated behind two switches and the CA's confirmation |
| Access control | `api/lifecycle/access.py` | Suspension is never a side effect |
| Proration | `api/lifecycle/proration.py` | **One function.** There is deliberately no second |
| Stage chain | `api/stages.py` | Templates are data; a scheme change is a record, not a deploy |
| GST | `api/gst.py`, `api/tax.py` | Refuses to guess a valuation basis |
| Security evidence | `api/security/` | Walks the registries, so it cannot go stale |

---

## Conventions worth keeping

- **Registry, never `hooks.py`.**
- **`get_list`, never `get_all`,** wherever a permission must apply — `get_all` sets
  `ignore_permissions=True`.
- **Read the snapshot, never the live plan.** Entitlement enforcement reads the Tenant's
  snapshot; the snapshot changes only on an explicit commercial event.
- **Commit after each unit in a long job,** so a crash leaves an accurate picture.
- **Append-only means append-only.** Subscription Event and Platform Audit Entry refuse
  update and delete for everyone, System Manager included.
- **Nothing deletes a customer's Company.** Termination archives and disables.
- **A refusal is better than a guess** — the GST rule, the isolation check and the
  suspension guards all fail closed and say why.

## Things that will bite you

- `frappe.get_all` ignores permissions. `frappe.get_list` does not.
- `frappe.only_for` is a **no-op under test**. Use `api.permissions.require_role`.
- `frappe.flags.in_import = True` skips `_set_defaults`, so `enabled` arrives as `None`.
- Frappe **never re-runs a patch** already in `tabPatch Log`. Editing a shipped patch does
  nothing; rename the module.
- Workspaces render from `content`, not `links`. A card missing from `content` is invisible.
- `frappe.whitelist()` appends to a module-level list; it sets **no attribute** on the
  function.
- MariaDB compares strings case-insensitively — `Company` and `company` collide as
  DefaultValue keys.
- A restored site gets a **new encryption key**. Every Password field breaks silently. See
  `ops/BACKUP_AND_DR.md`.
