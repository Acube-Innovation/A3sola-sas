# UAT — Phase 2 (Solar Operations)

Each case traces to the prompt that specified it. Run against a site with demo data:
`bench --site <site> execute a3_sola.demo.generate_demo_data.run`

83 of these are automated; `bench --site <site> run-tests --app a3_sola` runs 186 across
both phases. Cases marked **manual** need a human at the screen or a printed document.

## Stage engine (P2-A3S-001)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U2-01 | Submit a Sales Order from a Phase 1 solar quotation | One Solar Installation, submitted, with the resolved chain | `test_handoff` |
| U2-02 | Re-run the handoff on the same order | Returns the existing installation; no second job | `test_handoff` |
| U2-03 | Inspect a financed residential job | 19 stages, none skipped for finance | `test_installation` |
| U2-04 | Inspect a self-funded job | VFR, LOAN and BCOM marked **Skipped** with "Self-funded sale" as the reason | `test_installation` |
| U2-05 | Inspect an unsubsidised job | PCR and DBT skipped | `test_installation` |
| U2-06 | Inspect a 3 kW job | CEIG skipped — below the capacity threshold | `test_installation` |
| U2-07 | Advance a stage with no evidence attached | Blocked, naming each missing document | `test_installation` |
| U2-08 | Attach evidence but do not verify it, then advance | Blocked, naming it as unverified | `test_installation` |
| U2-09 | Attach and verify, then advance | Stage completes, next stage starts | `test_installation` |
| U2-10 | Block a stage without a reason | Refused | `test_installation` |
| U2-11 | Block, then unblock | Status returns to In Progress | `test_installation` |
| U2-12 | Skip a mandatory stage as an Operations Executive | Refused — manager only | `test_installation` |
| U2-13 | Revert to an earlier stage | That stage and everything after it clears | `test_installation` |
| U2-14 | Reach a DISCOM-owned stage | Status becomes Awaiting External; blocking party named | `test_installation` |
| U2-15 | Open the stage chain on the form | Coloured chips, skipped stages struck through with the reason on hover | **manual** |

## Document engine (P2-A3S-001)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U2-16 | Generate the consumer-vendor agreement | PDF attached, logged, filed into the ORD checklist row | `test_documents` |
| U2-17 | Generate it again | Replaces the file; one log row, not two | `test_documents` |
| U2-18 | Generate the whole pack | One result per template; a failure reports per document and does not abort the pack | `test_documents` |
| U2-19 | Compare the consumer number on the bank letter and the KSEB annexure | Identical — one context builder | `test_documents` |
| U2-20 | Edit the consumer number after generating | Affected documents marked stale; a banner appears on the form | `test_documents` |
| U2-21 | Regenerate a document that has been issued | Warns that the issued copy has left the building | **manual** |
| U2-22 | Check every seeded template has a source note | All 18 record the client document they reproduce | `test_documents` |
| U2-23 | Check the covering letter's enclosures | Eight enclosures, including the stamp-paper agreement | `test_documents` |
| U2-24 | Print each generated document and compare with the client's own form | Visually equivalent, field for field | **manual — do this before go-live** |

## External applications and finance (P2-A3S-002)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U2-25 | File a feasibility application, raise a query | Mapped stage blocks with the query as its reason | **manual** |
| U2-26 | Resolve the query | Stage unblocks | **manual** |
| U2-27 | Approve the application | Stage advances; the approval letter files into the checklist automatically | **manual** |
| U2-28 | Enter a malformed portal ID | Warns, does not block — the format is the ministry's to change | **manual** |
| U2-29 | Create a loan application with an EHS-blocked survey | Refused | `test_claims` (guard) |
| U2-30 | Record the advance tranche | LOAN advances; outstanding recalculates | **manual** |
| U2-31 | Record the balance tranche | BCOM advances | **manual** |
| U2-32 | Generate the vendor feasibility report | Every field comes from the Phase 1 survey; nothing re-entered | **manual** |

## Serials (P2-A3S-002)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U2-33 | Enter the same serial twice on one job | Rejected | `test_serials` |
| U2-34 | Enter a serial already on another job | Rejected, naming the first installation | `test_serials` |
| U2-35 | Capture 6 of 6 modules and an inverter | Capture marked complete | `test_serials` |
| U2-36 | Capture 3 of 6 | Incomplete; commissioning blocked with the count | `test_serials` |
| U2-37 | Export the manifest | Carries consumer number, serial, DCR certificate and capacity | `test_serials` |
| U2-38 | Compare completion report data with the register | Identical | `test_serials` |
| U2-39 | Submit a Delivery Note carrying a duplicate serial | Rejected at dispatch, not weeks later at the portal | **manual** |

## Commissioning (P2-A3S-003)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U2-40 | Open a new Commissioning Report | Administrative block fetched; seven protection functions seeded | `test_commissioning` |
| U2-41 | Submit without protection proof | Blocked, naming each gap | `test_commissioning` |
| U2-42 | Submit without earthing verification | Blocked | `test_commissioning` |
| U2-43 | Submit with an expired sensor calibration | Blocked | `test_commissioning` |
| U2-44 | Submit below a 75% performance ratio | Blocked without a recorded reason | `test_commissioning` |
| U2-45 | Same, with a manager's reason | Allowed; the reason is written to the timeline | `test_commissioning` |
| U2-46 | Submit a valid report | Warranty window written; PR carried to the installation; COMM advances | `test_commissioning` |
| U2-47 | Generate the DISCOM testing checklist | Complete, and visually equivalent to the client's spreadsheet | **manual** |
| U2-48 | Execute the net metering agreement without a SPIN | Blocked | **manual** |
| U2-49 | Print the agreement | Stamp paper flagged, full schedule including wheeling preferences | **manual** |

## Snags, claims and fees (P2-A3S-003)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U2-50 | Raise a Safety-category snag with no severity | Defaults to Critical | `test_claims` |
| U2-51 | Raise a critical snag | Target closure at 3 days; escalation role notified | `test_claims` |
| U2-52 | Try to advance PCR with an open major snag | Blocked, naming the snags | `test_claims` |
| U2-53 | Resolve it, then advance | PCR completes | `test_claims` |
| U2-54 | Record PCR before commissioning | Blocked | `test_claims` |
| U2-55 | Track a company-funded gap through partial recovery | Outstanding and status track correctly | `test_claims` |
| U2-56 | Try to type a statutory fee amount | Overwritten by the computed figure | `test_claims` |
| U2-57 | Submit a company-paid fee with no receipt | Blocked — no receipt, no reimbursement | `test_claims` |
| U2-58 | Record a short refund | Flagged Short Received with the variance | `test_claims` |
| U2-59 | Grep the module for accounting entries | None — Operations posts nothing | `test_claims` |

## Isolation and reporting (P2-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U2-60 | Run the registry guard | Every Operations doctype registered, every company-bearing one isolated | `test_tenancy` |
| U2-61 | Open a Company B installation as a Company A user | Denied | `test_tenancy` |
| U2-62 | Link a Company B installation from a Company A application | Rejected, naming both | `test_tenancy` |
| U2-63 | Check each tenant's masters | Each has its own stage chain and document templates | `test_tenancy` |
| U2-64 | Check the five extension points | Present, documented, inert | `test_tenancy` |
| U2-65 | Run all ten Operations reports | All execute | **manual / smoke** |
| U2-66 | Log in as a Solar Technician | No contract value, no subsidy figure, no consumer bank account, no Subsidy Claim | **manual** |
| U2-67 | Complete a job end to end as a Documentation Officer | Possible without a manager and without retyping a field | **manual** |

## Known manual gaps

U2-15, U2-21, U2-24 through U2-32, U2-39, U2-47 through U2-49, U2-65 through U2-67 need a
browser, a second user or a printed document. **U2-24 is the one that matters most before
go-live**: print every generated document and compare it, field for field, with the form
the client uses today.
