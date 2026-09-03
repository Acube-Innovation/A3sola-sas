# Platform operator — for Acube's own team

You run the platform. Your customers run their solar businesses on it.

---

## Your morning, in order

### 1. Revenue at Risk

Sorted by **lifetime value**, not by how overdue. Ten days late on your largest customer
matters more than thirty days on your smallest. Anything near the top with a *Next Change*
this week is a call today.

### 2. The approval queue

**Access Suspension**, filtered to Pending Approval. Each row carries what you need to
decide in ten seconds: outstanding amount, days overdue, dunning history, lifetime value,
last payment, and whether the warning was sent in time.

Approve, or reject with a reason. **Doing nothing is a valid answer** — nothing is ever
suspended because a date passed.

### 3. Provisioning interventions

A customer has paid and has nothing to log into. Treat these as urgent — see
`PROVISIONING_RUNBOOK.md`, which lists every failure state and its specific action.

**Tell the customer.** A holding message within the hour beats a fix within the day.

### 4. The console

**Platform workspace → Operations console.** Tenants by state, MRR, revenue at risk, what
needs attention, scheduler health, and **the current mode switches**.

Check the modes. Somebody always forgets which mode production is in.

### Weekly

- **Engagement Signals** — tenants who have not logged in for a month are going to cancel;
  you have not been told yet. This gives you more warning than payment status ever will
- **Trial Pipeline** — "nobody has ever signed in" is a call today
- **Settlement Reconciliation** — every line matched
- **Churn Analysis** — read the reasons, not just the count

---

## Suspension decisions

**The rule: restore first, investigate second.** Restoration needs no approval and takes
seconds.

Before approving one, ask:

1. Is this the customer, or is it the gateway? A spike of failures across many customers is
   never a coincidence — check the gateway before suspending anybody
2. Was the warning actually sent? The app refuses without it, and that refusal is correct
3. How much are they worth? A large customer gets a phone call, not a suspension

**If several suspensions come up at once, stop.** That is what the circuit breaker exists
for, and if it has not fired you should still be suspicious.

## Refunds

Never automatic. They route through the Phase 5 approval with a threshold. Every one is
hash-chain audited. An immediate cancellation with a refund due is an internal decision, not
a customer-facing button.

## Reconciliation

The gateway settlement file against what you recorded. An unmatched line is money you cannot
attribute. It alerts weekly, and it should be at zero.

## Support sessions

If you need to see what a customer sees:

**Console → Tenant 360 → Impersonate.** You must give a real reason, the session lasts 30
minutes, every action is audited, and **the customer is emailed that it happened**.

That last part is not negotiable. Looking at somebody's account without telling them is a
trust violation, whatever the reason.

---

## When to escalate

| Situation | To whom | When |
|---|---|---|
| A customer can see another's data | Engineering lead | **Immediately, before finishing diagnosis** |
| Several customers suspended at once | Platform Admin | Immediately |
| A provisioning job stuck over 4 hours | Platform Admin | Same day |
| The circuit breaker fired | Platform Admin | Same day — nobody was suspended, but find out why |
| A scheduler stopped | Engineering | Same day |
| A refund over the approval threshold | Billing Manager | Before approving |

`ops/ON_CALL.md` has the decision tree for each.

---

## What you must not do

- **Do not switch on automatic suspension** until the pre-flight passes and you have read a
  full cycle of simulated decisions
- **Do not switch on accounting postings** until the CA's confirmation is recorded
- **Do not leave the kill switch on.** It silently halts all lifecycle enforcement, and
  nothing will remind you
- **Do not delete anything to fix a problem.** Suspension, cancellation and termination all
  preserve data on purpose
