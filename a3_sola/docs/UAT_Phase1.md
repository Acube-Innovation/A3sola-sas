# UAT — Phase 1 (Solar CRM)

Each case traces to the prompt that specified it. Run against a site with demo data:
`bench --site <site> execute a3_sola.demo.generate_demo_data.run`

Automated coverage is noted per case; `bench --site <site> run-tests --app a3_sola` runs
87 tests. Cases marked **manual** need a human at the screen.

| ID | Traces to | Precondition | Steps | Expected | Automated |
|---|---|---|---|---|---|
| U1-01 | P1-CRM-001 | Fresh site | `bench install-app a3_sola` | 31 doctypes under Solar CRM; exactly one settings singleton named "A3 Sola Settings"; all masters seeded | — |
| U1-02 | P1-CRM-001 | Masters seeded | Open Statutory Fee Schedule "KSEB 2026-27" | Application ₹1,000 + 18%; registration ₹1,000/kW + 18%; refund 80% of base; four net-meter rows; the discrepancy note is present | — |
| U1-03 | P1-CRM-001 | — | Call `get_statutory_fees("KSEB","Single Phase",3,"Purchased by Customer")` | 1180 gross application, 3540 gross registration, 2400 refundable — matching the client's 3 kW proposal exactly | `test_statutory` |
| U1-04 | P1-CRM-001 | — | Same for 10 kW three phase | 11800 gross, **8000** refundable (the client's template says 4000) | `test_statutory` |
| U1-05 | P1-CRM-001 | — | `get_subsidy_amount(scheme, 5, "Residential")` | 78000, capped | `test_calculations` |
| U1-06 | P1-CRM-001 | — | Subsidy at 1.0 / 2.99 / 3.0 kW | 30000 / 60000 / 78000 — boundary exactly on the threshold takes the upper slab | `test_calculations` |
| U1-07 | P1-CRM-001 | — | Commercial enquiry against the residential scheme | Zero with an explanatory message, not an exception | `test_calculations` |
| U1-08 | P1-CRM-001 | — | `check_connection_type(5,"Single Phase","KSEB")` on 2026-01-15 then 2026-06-01 | Compliant (stay named) then non-compliant requiring three phase | `test_regulation` |
| U1-09 | P1-CRM-001 | — | Bill 500 units, then savings 500→200 | Saving per unit exceeds the average rate — telescopic, not flat | `test_calculations` |
| U1-10 | P1-CRM-001 | — | Daily band for 3 / 5 / 10 kW | 12–15, 20–25, 40–50 units — the ranges the client quotes | `test_calculations` |
| U1-11 | P1-CRM-002 | — | Create two consumers with the same number on one DISCOM | Rejected, naming the existing record | `test_transactions` |
| U1-12 | P1-CRM-002 | — | Enter an invalid IFSC | Rejected — a wrong IFSC is a failed DBT weeks later | `test_transactions` |
| U1-13 | P1-CRM-002 | — | Survey with 400 usable sq ft on RCC Flat | 5.0 usable kW (80 sq ft/kW from the roof type) | `test_transactions` |
| U1-14 | P1-CRM-002 | — | Open a new Site Survey | EHS checklist pre-populated with 15 questions in the lender's own wording; exactly one blocking | `test_transactions` |
| U1-15 | P1-CRM-002 | — | Tick "Asbestos Roofing Present" and submit | Blocked, naming the go/no-go criterion | `test_transactions` |
| U1-16 | P1-CRM-002 | — | Estimates bound by consumption / roof / sanctioned load in turn | Binding constraint named in each case | `test_transactions` |
| U1-17 | P1-CRM-002 | — | Override capacity above the roof limit | Rejected naming the survey | `test_transactions` |
| U1-18 | P1-CRM-002 | — | Try to type a registration fee onto an estimate | Overwritten by the computed figure | `test_transactions` |
| U1-19 | P1-CRM-002 | — | Switch net meter mode to "Availed from DISCOM on Rental" | Charge becomes 0 and a 21-day allocation lead time appears | `test_transactions` |
| U1-20 | P1-CRM-002 | — | Flag two options as recommended | Rejected | `test_transactions` |
| U1-21 | P1-CRM-002 | — | Non-DCR package under a DCR-requiring scheme; then with no scheme | Blocked, then allowed — a non-DCR job is legitimate when unsubsidised | `test_transactions` |
| U1-22 | P1-CRM-002 | — | Eligibility check on a complete job | 11 rule rows | `test_eligibility` |
| U1-23 | P1-CRM-002 | — | Consumer with a prior subsidy | ELG-02 fails; overall Not Eligible | `test_eligibility` |
| U1-24 | P1-CRM-002 | — | Consumer with no bank details | ELG-09 fails — no DBT and no refund without them | `test_eligibility` |
| U1-25 | P1-CRM-002 | — | Back-date a check into the stay, then after it | ELG-08 Not Applicable, then Fail | `test_eligibility` |
| U1-26 | P1-CRM-002 | Manager role | Waive ELG-02 with a reason | Overall becomes Eligible with Conditions; waiver stamped and survives a re-save | `test_eligibility` |
| U1-27 | P1-CRM-002 | — | Edit a rule result by hand and save | Overwritten from the registry | `test_eligibility` |
| U1-28 | P1-CRM-002 | — | Raise two proposals in one financial year | Sequence increments; name is `RENC-PROP-26-27-nnnn` | `test_proposal` |
| U1-29 | P1-CRM-002 | — | Check the generated file name | `<seq>-<series>-<date>-<capacity>-<customer>` — the client's existing convention | `test_proposal` |
| U1-30 | P1-CRM-003 | Lead with a DISCOM | Click "Create Solar Consumer" | Consumer created and linked back | **manual** |
| U1-31 | P1-CRM-003 | Any lead | "Log Outreach" → Connected, Step 2 | Cadence advances, next follow-up date set without typing a date | **manual** |
| U1-32 | P1-CRM-003 | — | Render the "Proposal Sent" template | WhatsApp asterisks preserved; signature and social links from Settings | `test_proposal` |
| U1-33 | P1-CRM-003 | Three-option estimate | Generate the proposal | All 11 sections render; three priced options; warranty per make; regulation clause from the rule | `test_print_and_reports` |
| U1-34 | P1-CRM-003 | Same | Check the KSEBL expenses block | Computed, with the refundable amount named in the row | `test_print_and_reports` |
| U1-35 | P1-CRM-003 | Quotation with a solar package | Add an item described "Less: Government subsidy" | Rejected | `test_quotation` |
| U1-36 | P1-CRM-003 | Quotation, no eligibility check | Submit | Blocked, naming what to create | `test_quotation` |
| U1-37 | P1-CRM-003 | Not Eligible check | Submit the quotation | Blocked | `test_quotation` |
| U1-38 | P1-CRM-003 | Estimate with 3 options | Create a quotation without choosing one | Blocked | `test_quotation` |
| U1-39 | P1-CRM-003 | Submitted quotation | Check the subsidy figure vs the total | Subsidy shown, total unaffected | `test_quotation` |
| U1-40 | P1-CRM-004 | Demo data | Open "Lead Follow-up Due" | Three overdue leads with days overdue | `test_print_and_reports` |
| U1-41 | P1-CRM-004 | Demo data | Open "Proposal Register" | Same columns as the client's spreadsheet; exports cleanly | `test_print_and_reports` |
| U1-42 | P1-CRM-004 | Demo data | Open the Solar CRM dashboard | Four headline cards non-zero; lead status and call connectivity breakdowns present | `test_print_and_reports` |
| U1-43 | P1-CRM-004 | Two companies | Log in as a user permitted only on Company A | Zero Company B rows in every report; Company B document not openable by URL | `test_tenancy` |
| U1-44 | P1-CRM-004 | Two companies | Link a Company B consumer from a Company A survey | Rejected, naming the link and both companies | `test_tenancy` |
| U1-45 | P1-CRM-004 | — | Run the registry guard test | Every registered doctype has both permission hooks and a company field | `test_tenancy` |
| U1-46 | P1-CRM-004 | Survey Engineer login | Open a Design Estimate | No cost field visible anywhere; EHS block editable | **manual** |
| U1-47 | P1-CRM-004 | — | `export-fixtures` then reimport on a fresh site | Module-scoped, no cross-module bleed | **manual** |

## Known manual gaps

U1-30, U1-31, U1-46 and U1-47 need a browser or a second site and are not covered by the
automated suite.
