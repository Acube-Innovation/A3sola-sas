# UAT master

Every acceptance case across all eight phases, grouped by **business process** rather than
by build order — because testers think in processes, and nobody outside the build team
knows what "Phase 5" contains.

**How to use this.** Each group names the document holding the detailed steps. This is the
index, the ID scheme and the sign-off record; the phase documents are the scripts.

## Test case IDs

`UAT-<GROUP>-<nn>` — stable, and never reused even if a case is retired.

| Group | Covers | Detail in | Originating prompts |
|---|---|---|---|
| **SO** | Sales to Order | `UAT_Phase1.md` | P1-A3S-001…004 |
| **EX** | Execution to Commissioning | `UAT_Phase2.md` | P2-A3S-001…004 |
| **PF** | Project Finance | `UAT_Phase3.md` | P3-A3S-001…004 |
| **OM** | O&M and Service | `UAT_Phase3.md` | P3-A3S-003, 004 |
| **PP** | Public Portal and Signup | `UAT_Phase4.md` | P4-A3S-001…004 |
| **PB** | Payments and Billing | `UAT_Phase5.md` | P5-A3S-001…004 |
| **PR** | Provisioning | `UAT_Phase6.md` | P6-A3S-001…004 |
| **SL** | Subscription Lifecycle | `UAT_Phase7.md` | P7-A3S-001…004 |
| **SI** | Security and Isolation | `docs/security/` | P8-A3S-001 |
| **E2E** | End-to-end journeys | this document | P8-A3S-004 |

---

## The document check — not optional

> Carry **one residential, financed, subsidised job** end to end, and have somebody from
> the client's own team check **every generated document line by line** against the
> paperwork they use today.

Enquiry → outreach cadence → proposal → order → consumer-vendor agreement → national portal
application → DISCOM feasibility → vendor feasibility report and EHS checklist → loan
sanction and advance → installation → KSEB registration fee → net meter request → KSEB
inspection and testing checklist → net metering agreement on stamp paper → commissioning →
completion reports to KSEB and to the lender → balance disbursement → PCR → DBT → the
registration fee refund.

A form that is subtly wrong is rejected at a counter weeks later, and that is exactly the
failure this product exists to prevent. **Sign off per document.**

| # | Document | Checked against | Checked by | Date | Pass |
|---|---|---|---|---|---|
| 1 | Proposal | | | | ☐ |
| 2 | Consumer-vendor agreement | | | | ☐ |
| 3 | National portal application | | | | ☐ |
| 4 | DISCOM feasibility application | | | | ☐ |
| 5 | Vendor feasibility report | | | | ☐ |
| 6 | EHS checklist | | | | ☐ |
| 7 | Loan application pack | | | | ☐ |
| 8 | KSEB registration fee receipt | | | | ☐ |
| 9 | Net meter request | | | | ☐ |
| 10 | KSEB inspection and testing checklist | | | | ☐ |
| 11 | Net metering agreement (stamp paper) | | | | ☐ |
| 12 | Commissioning report | | | | ☐ |
| 13 | Completion report — KSEB | | | | ☐ |
| 14 | Completion report — lender | | | | ☐ |
| 15 | PCR submission | | | | ☐ |
| 16 | Subsidy claim / DBT | | | | ☐ |
| 17 | Registration fee refund claim | | | | ☐ |
| 18 | Tax invoice | | | | ☐ |

**This has not been done.** It requires the client's own paperwork and their own people. It
is the single largest open item before go-live.

---

## End-to-end scenarios

Six journeys crossing every phase, because integration bugs live in the seams and no
phase's own tests find them.

### Executed, with results

**S2 — seat limit, self-service seat, mid-cycle upgrade, mandate re-checked** ✅

| Step | Expected | Actual |
|---|---|---|
| Tenant at its seat limit | 4 of 5 | 4 of 5 |
| Seat quote on day 23 of a 30-day period | 133.33 prorated | **133.33** |
| Payable including 18% tax | 157.33 | **157.33** |
| Self-serve the seat | quota rises to 6 | **6** |
| Upgrade to Growth mid-cycle | takes effect Immediately | **Immediate** |
| Recurring amount exactly at the AFA ceiling | still Auto Debit | **Auto Debit** |
| One paisa over the ceiling | re-routed | **Assisted Renewal** |

**S3 — failure, dunning, grace, warning, suspension, pay while suspended, restore** ✅

| Step | Expected | Actual |
|---|---|---|
| Collection fails → Past Due | access stays **Full** | **Full** |
| Day 7 → Grace | access **Banner** | **Banner** |
| Approve a suspension with no warning sent | refused, loudly | *"No suspension warning has been sent. 3 days' notice is required."* |
| Warning given → approve | allowed | allowed |
| Suspend | gate Blocked | **Blocked** |
| **Suspended tenant reaches the billing page** | yes | **yes** |
| Restore on payment | gate Full | **Full** |
| Every user back to their exact prior state | identical | **identical** |
| The user the customer had themselves disabled | **stays disabled** | **still disabled** |

**S4 — cancel, data export, reactivate** ✅

| Step | Expected | Actual |
|---|---|---|
| Cancel | End of Period | **End of Period** |
| Access during the paid period | Full | **Full** |
| Data export generated **before** access ends | a file | `/private/files/a3sola-export-TNT-…json` |
| Reactivation deadline recorded | a date | **2026-10-08** |
| Reactivate inside the window | Active | **Active** |

**S6 — isolation re-checked after all of the above** ✅

662 cross-tenant attempts, **0 successful**. The full suite separately: 5,871 attempts, 0
successful, with a negative control detecting 66 leaks when the boundary is removed.

**23 of 23 steps behaved as expected. No discrepancies.**

### The full suite

`bench --site <site> run-tests --app a3_sola`, run module by module:

| | |
|---|---|
| Modules | **53** |
| Tests | **972** |
| Failures | **0** |
| Skipped | 1 |
| Runtime | **54 minutes** |

The one skip is in `test_provisioning_users` and is deliberate — it needs an SMTP server.

### Not executed

**S1 — the full journey from public signup to first O&M visit.** Every *segment* is
covered: the starter dataset builds Lead → … → O&M contract with visits and readings
(`docs/STARTER_DATASET.md`, 42 documents across 34 doctypes), and provisioning is proven
end to end in `test_provisioning_*`. What has **not** been run as one continuous journey is
a real signup paying through a live gateway and provisioning from that payment, because
that needs live Razorpay credentials. **Do this in Stage 0.**

**S5 — a full five-year O&M year.** The components are covered by
`tests/solar_projects/test_om.py` and `test_service.py`, and the demo generator builds
visits, tickets, warranty claims and generation readings. A twelve-month simulated run with
date advancement has not been executed. **Recommended during Stage 1.**

---

## Defect triage from this phase

| Ref | Severity | Finding | Owner | Status |
|---|---|---|---|---|
| M1 | Medium | Unverified webhooks could grow the log table without bound | Phase 5 | **Fixed** |
| M2 | Medium | Control characters survived into stored text | Phase 4 / 7 | **Fixed** |
| M3 | Medium | Pricing endpoint unauthenticated and uncapped | Phase 4 | **Fixed** |
| DR1 | **High** | Encrypted secrets do not survive a restore | Ops | **Documented + procedure proven** |
| DR2 | Medium | Scheduled backup was database-only | Ops | **Documented** |
| P1 | Medium | Six N+1 patterns in reports | Phases 1, 5, 7 | **Fixed** |
| P2 | Low | Lifecycle engine planned illegal transitions, filling the error log nightly | Phase 7 | **Fixed** |
| L2 | Low | One raw-SQL interpolation site | Phase 4 | Reviewed, accepted |
| L4 | Low | Starter dataset password in source | — | Accepted, the client's decision |
| E1 | Low | Dependency advisories in the bench and framework toolchain | Vendor | Reported, not applied |

No Blockers. No High severity in the application itself.

---

## Client sign-off pack

For a functional consultant to execute, not a developer.

### Before you start

1. A site with `a3_sola` installed and migrated
2. The starter dataset present — it installs itself on deploy
   (`docs/STARTER_DATASET.md`)
3. Sign in as `starter.engineer@example.com` / `a3sola-starter`
4. **Change that password** or run the teardown before the site holds real data
5. Have your current paperwork to hand for the document check above

### How to record a result

| Case | Steps | Expected | Actual | Pass | Tester | Date |
|---|---|---|---|---|---|---|
| UAT-SO-01 | See `UAT_Phase1.md` §1.1 | | | ☐ | | |

Copy that row per case from each phase document. **Record what actually happened, not
"pass"** — "pass" is not evidence, and the difference matters when somebody re-reads this
in six months.

### Sign-off

| | Name | Role | Signature | Date |
|---|---|---|---|---|
| Functional lead | | | | |
| Finance / CA | | | | |
| Operations lead | | | | |
| Acube delivery | | | | |

**The finance signature is not a formality.** It covers the GST treatment for both the
solar EPC composite supply and the SaaS subscription, and the accounting postings stay
switched off until it is given in writing.
