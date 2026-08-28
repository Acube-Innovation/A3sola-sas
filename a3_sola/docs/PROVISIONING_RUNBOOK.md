# Provisioning runbook

What to do when a tenant does not come out the other end. Every procedure assumes Platform
Provisioning Operator or Platform Tenant Manager.

## The one principle

**Nothing here deletes a customer's company, and nothing here deletes their data.** Not
rollback, not termination, not the refund path. If a procedure below seems to be missing a
"and then remove it" step, that is deliberate: erasure is a separate, deliberate operation
that needs a documented request from the customer, and it is not in this runbook.

---

## Reading a Provisioning Job

The step log is the account of what happened. Three things tell you where you stand:

* **`point_of_no_return_passed`** — the single most important field. Before it, a failure
  rolls back and leaves nothing behind. After it, a user account exists and nothing is
  undone automatically.
* **`current_step`** — where it stopped.
* **`requires_manual_intervention`** — somebody has to act; it will not resolve itself.

| Job status | What it means | What to do |
|---|---|---|
| Queued | Manual Approval mode, waiting for a human | Press **Resume** |
| Running | In flight | Wait. The watchdog marks it Failed after the timeout |
| Completed | Tenant is live | Nothing |
| Rolled Back | Failed before the line; everything was undone | Fix the cause, press **Resume** |
| Failed | Failed before the line but the rollback itself did not complete | Read the Error Log, tidy up, then **Resume** |
| Failed Past Point of No Return | A half-built tenant exists | Work through the section below |

---

## A job is stuck Past the Point of No Return

This is the state that matters. Something exists — a company, masters, possibly a user —
and nothing was cleaned up.

1. **Read `failure_summary` and the failing step's traceback.** They name what broke.
2. **Look at what exists.** The step log's `created_name` column lists every artefact, in
   order. The alert email repeats it.
3. **Fix the cause, then press Resume.** Resume continues from the first step that is not
   Completed — it does not re-run the company creation, and re-running a completed step is
   exactly the bug the step log prevents.
4. **If one step cannot succeed and is not mandatory**, use **Skip Step** with a reason. It
   refuses mandatory steps outright: a skipped `CREATE_COMPANY` gives you a tenant with no
   workspace and a green job, which is the worst combination available.
5. **When it is done**, press **Mark Resolved** and write down what you did. The next person
   to open the job needs to know.

**Do not** use Roll Back here. It is unavailable on purpose, and the button explains why.

---

## A duplicate email signed up

Step 09 fails with "A user account already exists for …" and flags manual intervention.
That is correct behaviour, not a bug: silently attaching an existing account to a new tenant
gives one login access to two tenants, and nobody audits that afterwards.

Two ways forward, and it is a decision rather than a fix:

* **Different address.** Ask the customer for another administrator address, change
  `primary_contact_email` on the Tenant, press **Resume**. This is almost always right.
* **Move the existing account.** Only when the same person genuinely runs both, and only
  after checking what that account can already see. Add the company User Permission, stamp
  `a3_sola_tenant`, then Resume from step 10. Write down why in the intervention notes.

---

## A tenant needs more seats now

`add_seats` is Phase 7's, and it does the commercially correct thing — re-snapshot and bill
prorated. Until then, manually:

1. Set `additional_users` on the Tenant. `user_quota` recomputes on save.
2. Run **Recalculate Usage**.
3. Raise the billing separately. The quota is a snapshot, so changing it does not invoice
   anybody — which is exactly why this is a stopgap and not the procedure.

---

## A tenant is over quota

The nightly job reports it in the Error Log, and Seat Utilisation shows it. Being over quota
means enforcement was bypassed — a user created with `ignore_permissions` outside the hooks,
or a quota reduced after the fact.

Disable the excess users, or sell them the seats. Do not raise the quota quietly to make the
report go away: the report is the only thing that would tell you it happened again.

---

## Re-running the isolation test

Press **Re-run Isolation Test** on the Tenant. It runs every check as that tenant's own
administrator and writes the results back. It is safe at any time and takes a couple of
seconds.

Run it after any change to permissions, roles, reports or the registry — and note that a
monthly sweep runs it across every active tenant, because a regression introduced by a later
phase should be found by us rather than by a customer.

---

## SEV-1: a tenant reports seeing data that is not theirs

Treat this as an active breach until proven otherwise. The first ten minutes matter, so this
is written as a sequence rather than advice.

**Minute 0 — contain.**

1. Disable the reporting tenant's users. Access off first; investigate second. It is
   reversible, and every minute of exposure is not.
2. Note exactly what they saw: which screen, which record, which company. Screenshot if
   they have one.

**Minute 5 — establish scope.**

3. Run **Re-run Isolation Test** on the reporting tenant. It names the failing check.
4. Run it on every other active tenant:
   `bench --site <site> execute a3_sola.api.isolation.monthly_isolation_sweep`. If one
   tenant is affected the others probably are, and you need to know before anyone asks.
5. Check the obvious cause first: is the company User Permission missing?
   `frappe.get_all("User Permission", {"user": <email>, "allow": "Company"})`. That single
   record is the whole of the isolation in this model, and its absence is silent.

**Minute 15 — find the mechanism.**

6. If the User Permission is intact, the leak is in a query that bypasses the permission
   layer. The two known ways in this codebase:
   * `frappe.get_all` instead of `frappe.get_list` — `get_all` sets
     `ignore_permissions=True`.
   * A report building SQL from `filters.company` without `resolve_report_company`.
   Both have tests; check whether the test was weakened rather than the code broken.
7. Check the Error Log around the reported time.

**Then — obligations.**

8. Record what was exposed, to whom, and for how long. Under India's DPDP Act a personal
   data breach is notifiable to the Data Protection Board and to affected principals, and
   the clock starts when you become aware. Get that assessment started in parallel with the
   fix, not after it.
9. Only restore access once the isolation test passes for the affected tenant.

Do not repair by granting narrower permissions to the affected user and moving on. Find the
query.

---

## Terminating a tenant

Manager only, and it asks you to type the tenant code because the row above and the row
below in that list are other people's businesses.

It exports the tenant's data to a private file, disables every one of their users, and marks
the Tenant Terminated. **It does not delete the company and it does not delete any data.**

Do this before terminating: check for unpaid invoices and open refunds. Termination stops
access, not billing — Phase 7 owns the subscription side.

---

## A first payment was refunded

`on_initial_payment_refunded` suspends the tenant automatically: users disabled, tenant
Suspended, nothing deleted, and an Error Log entry saying a human has to decide what
happens next.

Reinstating is a matter of re-enabling the users and setting the Tenant back to Active.
Terminating uses the flow above. Neither is automatic, deliberately — a refund can be a
mistake, a dispute or a genuine cancellation, and those end differently.

---

## Provisioning has stopped happening at all

Symptom: paid signups, no Provisioning Jobs.

1. Check `provisioning_mode` in Settings. **Manual Approval** queues jobs and waits — which
   is a supported mode and an easy thing to forget was switched on.
2. Check the background worker is running: `bench doctor`. Provisioning is enqueued, never
   run in the web request.
3. Check the payment actually reached webhook confirmation. Provisioning deliberately
   refuses a browser-callback-only payment; the job's failure summary says so in those
   words.
4. Check the Error Log for `a3_sola: provisioning`.

---

## Useful commands

```bash
# Provision one subscription by hand (idempotent - finds the existing job)
bench --site <site> execute a3_sola.api.provisioning.orchestrator.run_provisioning \
      --kwargs '{"subscription_name": "SUB-2026-00001", "triggered_by": "Manual"}'

# Everything waiting on a human
bench --site <site> execute a3_sola.platform.doctype.provisioning_job.provisioning_job.health

# Mark stuck jobs failed (the watchdog, run early)
bench --site <site> execute a3_sola.api.provisioning.orchestrator.watchdog

# Correct usage counters across every tenant
bench --site <site> execute a3_sola.api.entitlements.recalculate_all_usage

# Isolation across every active tenant
bench --site <site> execute a3_sola.api.isolation.monthly_isolation_sweep
```
