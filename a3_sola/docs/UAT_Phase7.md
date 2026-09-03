# UAT — Phase 7: subscription lifecycle and access control

Cases traced to P7-A3S-001 through 004. Each one names what to do, what should happen, and
— where it matters — why the expected result is what it is rather than something more
obvious.

Sign in as a user holding **Platform Admin** unless a case says otherwise.

**Before you start**, put the settings back to shipped defaults:
`dry_run_mode` on, `enable_automatic_suspension` off,
`require_manual_approval_for_suspension` on.

---

## P7-A3S-001 — Policy engine, state machine, scheduler

### 1.1 An illegal transition is refused and names both states
Run `a3_sola.api.lifecycle.state_machine.transition` on an Active subscription with
`to_state="Suspended"`.
**Expect:** refused, naming Active and Suspended, and listing the legal moves.
**Why:** a customer reaches Suspended through the policy stages, having been warned at
each — or not at all.

### 1.2 The event log cannot be edited
Open any Subscription Event as Administrator, change the reason, save.
**Expect:** "A subscription event cannot be changed once it is written."
Then try to delete it. **Expect:** refused.

### 1.3 Shipped defaults change nothing
With dry run on, run `engine.run_lifecycle` against the whole base.
**Expect:** events written for every decision; **no** access state changed anywhere; no
user disabled. Check `Tenant.access_gate` on every tenant is still Full.

### 1.4 Automatic suspension off still evaluates
Turn dry run off, leave automatic suspension off. Run the engine against an overdue tenant.
**Expect:** an event recorded saying the decision was made and not acted on; access
untouched.

### 1.5 Minimum tenure protects a new tenant
Take a tenant three days old, twenty days overdue, with everything switched on.
**Expect:** not suspended; an event naming the minimum tenure.

### 1.6 The circuit breaker halts the run
Set `max_suspensions_per_run` to 2 and arrange four suspendable tenants.
**Expect:** the whole pass halts, **zero** suspensions performed, an alert naming the
count and listing every tenant, and one Policy Evaluated event recording the halt.

### 1.7 Past Due leaves access full
Move a subscription to Past Due.
**Expect:** `access_state` is Full and the tenant's gate is Full.
**Why:** a deliberate product decision. A failed debit is usually a bank problem, not a
refusal to pay, and restricting work over one loses the account.

### 1.8 Policy resolution prefers the specific
Create a policy bound to one plan. A subscription on that plan resolves to it; one on
another plan resolves to the default.

### 1.9 The stage reached is the latest passed
A subscription twenty days overdue under the standard policy resolves to `SUSPEND`
(day 15), not to `PASTDUE` (day 0).

### 1.10 A healthy subscription matches no stage
A subscription owing nothing has no policy stage and no `days_overdue`.
**Why:** day 0 means "the payment failed today", not "always". Conflating the two told 200
healthy customers their payment had failed.

### 1.11 The heartbeat
Run the engine. `lifecycle_heartbeat_on` updates. Set it five days back and run
`alert_on_missing_heartbeat`. **Expect:** it reports unhealthy and alerts.

---

## P7-A3S-002 — Access control

### 2.1 Who is never disabled
For each, confirm the user is excluded and the reason names them:
- the Administrator
- a user with no tenant stamp (internal staff)
- a holder of any internal Platform role
- a user belonging to a different tenant

### 2.2 An unresolvable set abandons the whole suspension
Suspend a tenant with no users.
**Expect:** refused, nothing disabled, the suspension marked Failed, an alert sent.
**Why:** fail closed. Disabling nobody and shouting is always recoverable.

### 2.3 The snapshot is written before anybody is disabled
Suspend a tenant with three users. Inspect the Access Suspension.
**Expect:** three rows in Affected Users, each with `was_enabled` recorded, committed
before any user was touched.

### 2.4 The round trip is exact
Record every user's enabled flag, roles and user permissions. Suspend. Restore. Compare.
**Expect:** byte-identical.

### 2.5 A previously disabled user stays disabled
Disable one user yourself. Suspend the tenant. Restore.
**Expect:** that user is still disabled.
**Why:** restoring them would hand access back to somebody the customer deliberately
removed. This is the detail that gets missed.

### 2.6 Nothing is ever deleted
Confirm no code path deletes a User, a Role, a Role Profile or a User Permission:
`grep -rn "delete_doc(\"User\"\|delete_doc(\"Role" a3_sola/api/lifecycle/` returns nothing.

### 2.7 Sessions are terminated
Suspend a tenant with an open session. **Expect:** the session is gone — suspension takes
effect now, not at next login.

### 2.8 A suspended tenant can always pay
As a user of a suspended tenant, confirm each of these separately:
- `/billing` is reachable
- the payment endpoint is reachable
- the payment webhook is reachable
- password reset is reachable
- login is reachable
- the desk is **not** reachable, and the refusal names the billing page

**Why:** locking a customer out of the page that ends their suspension is the worst bug
this phase could ship.

### 2.9 Read Only blocks writing and nothing else
Set a tenant to Read Only. **Expect:** open, search, report and print all work; submit and
cancel are refused with an explanation.

### 2.10 Suspension is refused without a warning
Approve a suspension whose warning was not sent, or was sent today.
**Expect:** refused, loudly, naming how many days' notice is required.

### 2.11 The approval queue
- Rejecting requires a reason and writes an event.
- A scheduled date passing produces a **reminder**, never an automatic apply.
- The queue row carries outstanding amount, days overdue, dunning history, lifetime value
  and last payment.

### 2.12 Restoration is fast
Restore from the payment webhook, from the engine and from the admin button.
**Expect:** all three work, none needs an approval, none needs a scheduler run.

---

## P7-A3S-003 — Plan changes, seats, proration

### 3.1 Hand-worked proration
Starter 3000/month, Growth 6000/month, 30-day period, change on day 11:

| Line | Expected |
|------|----------|
| Unused credit | −2000.00 |
| New charge | 4000.00 |
| Net | 2000.00 |
| Tax at 18% | 360.00 |
| **Payable** | **2360.00** |

### 3.2 A seat on day 23
Eight days remaining at 500/month: **133.33**, tax 24.00, payable **157.33**.

### 3.3 February
A February period prorates over 28 days, not 30. A leap February over 29.

### 3.4 The lines add up
Every breakdown sums to its own total.

### 3.5 Effective dates
An upgrade takes effect immediately. A downgrade takes effect at the **next period
boundary** and refunds nothing.

### 3.6 The mandate maximum
New recurring amount above the mandate's registered maximum.
**Expect:** `Requires New Maximum`, and the detail says the next debit would be declined.

### 3.7 The AFA ceiling, a paisa either side
- At the ceiling exactly: still Auto Debit.
- One paisa over: `Requires Route Change` to Assisted Renewal.

### 3.8 Downgrade blockers
A tenant on 12 users downgrading to a 5-seat plan.
**Expect:** blockers listing the number to remove and saying "you choose which"; status
`Awaiting User Reduction`; **nobody disabled**.

### 3.9 Blockers uncleared at the boundary
**Expect:** the downgrade is **not** applied, nobody is suspended, the tenant stays on the
higher plan for another period, and both sides are notified.
**Why:** the correct failure mode is "you keep paying more", never "your data became
unreachable".

### 3.10 The entitlement snapshot
Applying a change re-snapshots the Tenant's quota and modules, and enforcement honours the
new quota immediately.

### 3.11 Idempotent and resumable
Applying twice changes nothing the second time. A partly applied change resumes.

### 3.12 Seats, self-service
A long-tenured tenant with no failed payments gets a seat immediately. A new tenant, or one
with failures, does not. Removing seats below the active user count is blocked with the
same "you choose which" wording.

### 3.13 Trials
A trial has full access, no charge and a countdown. A trial with no payment method is
**cancelled**, never suspended — the state machine has no Trialing → Suspended move at all.

---

## P7-A3S-004 — Cancellation, reporting, console

### 4.1 End of period by default
**Expect:** the customer keeps full access until the period they paid for expires. Nothing
is cut on the day they cancel.

### 4.2 Immediate cancellation is internal
A customer asking for immediate cancellation is told it has been recorded for the end of
the period and to ask if they need it sooner.

### 4.3 The data export
**Expect:** generated **before** access ends, the customer notified, the download recorded.

### 4.4 Nothing is auto-terminated
A retention window expiring flags for review and alerts. It terminates nothing and deletes
nothing.

### 4.5 The mandate is cancelled
As the RBI requires, and the cancellation is confirmed and recorded.

### 4.6 Reactivation restores the exact prior state
Including leaving a previously disabled user disabled. The billing schedule restarts from
today — they are not charged for the months they were away.

### 4.7 Past the window
Self-service reactivation stops and says to get in touch. An internal user can still do it.

### 4.8 Every report runs
All ten return columns and data without error.

### 4.9 The MRR bridge reconciles
Every month: opening + new + expansion − contraction − churned + reactivated = closing, and
each month opens where the last closed. The report says so itself in a column.

### 4.10 The pre-flight check refuses on each missing precondition
Demonstrate each refusal separately: no default policy, no circuit-breaker limit, no
approval role holder, an engine that has never run, no simulation run.

On a fresh site the first three checks pass out of the box — the default policy, its five
stage emails and the breaker limit all ship. The two that do not are the ones only you can
satisfy: **somebody has to hold the approval role**, and **the engine has to have run daily
for a week**. That is deliberate; both are evidence that a person is watching.

### 4.11 The kill switch
Pulling it needs a reason. With it on, the engine evaluates and logs and changes no state.

### 4.12 Bulk operations
Each needs a typed confirmation and a mandatory reason, and writes **one event per
subscription** — never one for the batch.

### 4.13 Tenant 360
One page carrying subscription state, seats, users, invoices, suspensions, plan changes,
events and onboarding.

---

## The acceptance run

With shipped defaults, run the engine against the full demo base:

    bench --site <site> execute a3_sola.api.lifecycle.engine.run_lifecycle

**Expect:** every subscription evaluated, every decision written down, and **zero access
changes anywhere**. Confirm by comparing `Tenant.access_gate` and every `User.enabled`
before and after.
