# The admin console

One place for Acube's own team to see and operate the platform. Built entirely on existing
data — no new doctypes, and every action routes to the function that already owns it,
because a console that reimplements suspension is a second implementation that will drift
from the first.

**Where:** the **Platform** workspace → *Operations console*, *Lifecycle* and
*Lifecycle reports* cards.

---

## Platform overview

`a3_sola.api.console.overview`

| Section | What it answers |
|---|---|
| Tenants by state | How many customers, and how many are in trouble |
| Subscriptions by state | Trialing / Active / Past Due / Grace / Suspended / Cancelling |
| Revenue | MRR, ARR, revenue at risk, average per tenant |
| Users across all tenants | How many people actually use it |
| Needs attention | Provisioning interventions, suspensions pending approval, unmatched settlements, failed webhooks, open alerts |
| Health | Jobs watched, jobs stopped, and which |
| **Modes** | Every master switch and its current state |

### Why the modes are shown prominently

*"Why is nothing posting?"* has this answer more often than any other, and somebody always
forgets which mode production is in.

| Switch | What it costs to be wrong |
|---|---|
| `enable_accounting_postings` | Off: nothing reaches the ledger. On without the CA's confirmation: wrong postings at scale |
| `enable_payment_postings` | As above, for subscription revenue |
| `gst_treatment_confirmed_by_ca` | The gate both sit behind |
| `enable_automatic_suspension` | On: the engine can block a paying customer with nobody watching |
| `dry_run_mode` | On: the engine decides and logs but changes nothing |
| `lifecycle_kill_switch` | On: **all** lifecycle enforcement is halted. Easy to leave on by accident |
| `provisioning_mode` | Automatic vs Manual Approval |
| `maintenance_mode` | The public site shows a holding page |

Each shows **who last changed it and when**, read from the settings Version history.

---

## Tenant operations

**Cross-tenant search** → `a3_sola.api.console.search_tenants`
**Tenant 360** → `a3_sola.api.lifecycle.admin.tenant_360`

One page per tenant: subscription state, seats, users with last activity, invoices,
suspensions, plan changes, the event history and onboarding progress — so support answers a
question without opening six doctypes.

Quick actions route to their owning functions, never reimplemented:

| Action | Goes to |
|---|---|
| Restore access | `lifecycle.suspension.restore` |
| Extend grace | `lifecycle.admin.bulk_extend_grace` |
| Change plan / add seats | `lifecycle.plan_change` / `lifecycle.seats` |
| Cancel / reactivate | `lifecycle.cancellation` |
| Approve or reject a suspension | `lifecycle.suspension.approve` / `.reject` |

**There is deliberately no Suspend button.** A customer is suspended by the policy, through
the approval queue, having been warned — not because somebody on this page decided to.

---

## Impersonation

`start_impersonation` / `end_impersonation`

Support sometimes has to see what the customer sees. Built with four properties, and any
one missing makes it a problem rather than a tool:

1. **Reason-gated** — at least fifteen characters, and it is shown to the customer
2. **Time-limited** — 30 minutes by default, capped at 120, expires on its own
3. **Audited** — into the hash-chained Platform Audit Entry, which cannot be edited away
4. **Notified** — the tenant is emailed that a session happened, why, and when it ends

The operator sees a banner naming the tenant, the expiry, and the fact the customer was
told.

> **Impersonation without notification is a trust violation.**
> `notify_tenant_on_impersonation` exists because a client will ask to turn it off. It
> defaults to **on**, and it should stay on: the person asking to disable it is not the
> person whose account it is. If it is ever turned off, the fact is logged on every session.

---

## Bulk operations

Each requires a **typed confirmation** and a **mandatory reason**, and writes **one event
per subscription** — never one for the batch, because the question asked six months later
is about one customer and a batch record does not answer it.

| Operation | For | Confirm |
|---|---|---|
| `bulk_extend_grace` | A gateway outage — push everybody's next change out | `EXTEND` |
| `bulk_restore` | After an incident — put everybody back | `RESTORE` |
| `bulk_reassign_policy` | Standardising after a pilot | `REASSIGN` |

---

## Safety rails

| Tool | What it does |
|---|---|
| `admin.run_simulation` | Every decision the engine would make, writing nothing |
| `admin.preflight` | Six preconditions, each pass/fail with what is missing |
| `admin.enable_automatic_suspension` | Refuses until pre-flight passes, then still requires typing `SUSPEND CUSTOMERS` |
| `admin.kill_switch` | Halts all state changes; evaluation and logging carry on |

---

## Who should use what

| Role | Sees | Can do |
|---|---|---|
| **Platform Admin** | Everything | Everything, including modes, pre-flight and bulk operations |
| **Platform Lifecycle Operator** | Overview, Tenant 360, queues | Extend grace, restore, run the simulation. **Not** suspend, **not** cancel |
| **Platform Retention Manager** | Cancellations, plan changes | Retention offers, plan and seat changes |
| **Platform Tenant Manager** | Tenants, provisioning | Tenant management, impersonation, termination with typed confirmation |
| **Platform Billing Manager** | Payments, refunds, reconciliation | Refund approval, mandate management |

Separated on purpose: the person who can suspend a customer and the person who can refund
them should not be the same person by default.

---

## What this console is not

- **Not a customer-facing surface.** Every endpoint requires an internal Platform role.
- **Not a replacement for the doctype list views.** It is a starting point that routes into
  them.
- **Not a metrics dashboard.** Charts live in the reports; this answers "is anything
  wrong right now".
