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
Lead ─────────────────────────────┐
 └─ Solar Consumer ───────────────┼──────────────────┐
     ├─ Site Survey → Solar Design Estimate          │
     │                 ├─ Subsidy Eligibility Check  │
     │                 └─ Solar Proposal → Quotation │
     │                     (versions)      └─ Sales Order
     └─────────────────────────────── Solar Installation   (thirty tasks, one row each)
          ├─ Installation Task          (status tasks: Form 1, advance, design, certificate,
          │                              portal update, DISCOM test, meter, balance)
          ├─ Installation Work Order → Installation Snag      (structure / installation, geo photos)
          ├─ Purchase Order → Delivery Note → Material Dispatch Notice (serials to the contractor)
          ├─ Portal Application → Statutory Fee Payment → Statutory Fee Recovery
          ├─ Loan Application, Subsidy Claim (request / correction / disbursement)
          ├─ Solar Agreement            (stamp paper; body generated, never typed; the KSEB agreement)
          ├─ Document Pack              (KSEB submission · bank completion pack · customer file)
          ├─ Commissioning Report, Customer Review (and the Google review)
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

A Solar Design Estimate is raised against a **Lead or a Solar Consumer**. Early in the
funnel there is no consumer yet, and an enquiry already carries the DISCOM, the category and
a rough bill - enough to size a system and put a number in front of somebody. The consumer
arrives with the survey, and brings the sanctioned load and the billing cycle with it.

A lead has **exactly one Solar Proposal**. Re-quoting opens a new version inside it rather
than raising a second document, because the customer experiences it as the same offer
changing. Each version records what it quoted, the PDF that went out, how and when it was
sent, and what the customer said back. Marking a version **Accepted** is what makes the
commercial Quotation available; the proposal is the offer, the Quotation books it.

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

## The task engine

A Solar Installation carries the **Installation Stage Template** of thirty tasks (see
`setup/seed_stages.TASKS`) - one document, shared by every company; the checklists and
document templates it draws on stay per company. Tasks are independent: there is no next stage to advance to, a
task can be skipped with a reason, and a job's applicability rules pre-skip what it does
not need (no loan tasks on a self-funded job, no inspectorate task under 10 kW).

- **Each task is executed in a document.** The template row names the doctype; the
  installation's row records the executing document's id, assignee, due date and cost.
  Similar tasks share a doctype: eight status-plus-evidence tasks are one `Installation
  Task`; the three packs are one `Document Pack`; a Subsidy Claim answers for three rows.
- **One doc_event drives every row.** `api/tasks.sync_from_document` is bound to
  `on_update / on_submit / on_update_after_submit / on_cancel` of every executing doctype
  through the registry. `TASK_DOCTYPES` says, per doctype, which task codes it owns and
  when it counts as Completed, Blocked or Skipped. Controllers no longer advance stages.
- **The Task button** on the installation (`api/tasks.open_task`) opens the linked document,
  or an existing unlinked one for the job, or a new one with the links pre-filled.
- **The register is not a gate.** Expected documents are created per task from the
  checklist; generation and uploads happen in the task documents and are registered on the
  job with their source. Gates live in each document's `before_submit`.
- **Completion has one extension point**, `api/tasks.notify_task_completed`: billing
  milestones (`billing.on_stage_completed`) and the Form 2 window fire from there, wrapped
  so the money layer can never undo an operations user's work.
- **A row never points at nothing.** Deleting a task document releases its row
  (`on_trash` is one of the sync events); a document that vanishes behind the engine's
  back - a purge, a raw delete - is let go of the next time the installation saves, with a
  comment naming it. A document filed under another company never drives a job's rows,
  even when its own validation was skipped.
- **Gotcha:** patches run before `after_migrate` seeding, so a patch that needs the task
  template must seed it itself (`retire_two_stage_templates_for_one` does).

## Where the important logic lives

| Concern | Module | Why there |
|---|---|---|
| Tenant isolation | `api/permissions.py` | One implementation, used by every module |
| Money | `api/payments.py`, `billing_engine.py`, `accounting*.py` | Postings gated behind two switches and the CA's confirmation |
| Access control | `api/lifecycle/access.py` | Suspension is never a side effect |
| Proration | `api/lifecycle/proration.py` | **One function.** There is deliberately no second |
| Task engine | `api/stages.py` (resolve, build, recompute), `api/tasks.py` (transitions, `sync_from_document`) | Tasks are an independent set, not a chain; each task's document drives its row through one doc_event |
| Document register | `api/documents.py` (`register_document`, `generate_document(source=…)`) | One write path; every generated or uploaded file names the task document it came from |
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
