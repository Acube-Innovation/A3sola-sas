# UAT — Phase 3 (Solar Projects)

Each case traces to the prompt that specified it. Run against a site with demo data:
`bench --site <site> execute a3_sola.demo.generate_demo_data.run`

Most of these are automated; `bench --site <site> run-tests --app a3_sola` runs the whole
suite across all three phases. Cases marked **manual** need a human at the screen.

## Handover from Operations (P3-A3S-001)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-01 | Submit a Commissioning Report | One Project, created from the installation | `test_project_creation` |
| U3-02 | Re-run the handover on the same report | Returns the existing project; no second one | `test_project_creation` |
| U3-03 | Inspect the project's Solar Details tab | Capacity, package, scheme, DISCOM and warranty dates all carried across | `test_project_creation` |
| U3-04 | Open the installation | Its Project field now points back | `test_project_creation` |
| U3-05 | Commission two jobs for the same consumer | Both projects created; names distinguished by consumer number | `test_project_creation` |
| U3-06 | Check the project name on the list view | Reads as "Consumer - 3 kWp (consumer number)" | **manual** |

## Costing (P3-A3S-002)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-07 | Submit a work order with 10 crew hours at a 520,000 CTC | Labour cost 2,500 — the crew's own rate, not a global default | `test_costing` |
| U3-08 | Recalculate costs four times | Identical total and identical entry count every time | `test_costing` |
| U3-09 | Raise a snag with a rectification work order | Rework appears on its own line | `test_costing` |
| U3-10 | Check the labour figure after U3-09 | Rectification hours are **not** also in Labour | `test_costing` |
| U3-11 | Record a statutory fee paid by the company | Shown as pass-through; total direct cost unchanged | `test_costing` |
| U3-12 | Record a fee the customer paid directly | Pass-through stays zero — the company's money never moved | `test_costing` |
| U3-13 | Set overhead recovery to 10% | Overhead is 10% of direct cost; total cost includes it | `test_costing` |
| U3-14 | Open any cost entry row | Names a real source document that can be opened | `test_costing` |
| U3-15 | Check margin against billed revenue | Margin equals billed (or contract value) less total cost | `test_costing` |
| U3-16 | Open the Costing tab as a non-manager | Costing and commercial fields hidden — permlevel 1 | **manual** |

## Billing (P3-A3S-003)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-17 | Check the seeded milestone templates | The client's three: 70:20:10 purchased meter, 70:20:10 DISCOM meter, financed 70:30 | `test_billing` |
| U3-18 | Check every template's percentages | Each totals exactly 100% | `test_billing` |
| U3-19 | Create a financed job | Resolves the Jan Samarth 70:30 template | `test_billing` |
| U3-20 | Create a job with a DISCOM rental meter | Last milestone triggers on completion documents, not on the meter | `test_billing` |
| U3-21 | Inspect a plan's amounts | 70/20/10 of contract value, to the rupee | `test_billing` |
| U3-22 | Check net payable | Contract value less expected subsidy | `test_billing` |
| U3-23 | Record a statutory fee against the job | Tracked on the plan, outside contract value | `test_billing` |
| U3-24 | Try to build a plan for a company with no template | Refused with a clear message — never an invented split | `test_billing` |
| U3-25 | Complete the INST stage | The mapped milestone is marked triggered | **manual** |
| U3-26 | Invoice a milestone out of sequence as an executive | Refused, naming the untriggered predecessor | **manual** |
| U3-27 | Invoice out of sequence as an Accounts Manager | Allowed, with a comment recording who did it and why it was out of order | **manual** |
| U3-28 | Create a milestone invoice | A **draft** Sales Invoice. Nothing is auto-submitted | **manual** |

## The subsidy rule (P3-A3S-003)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-29 | Add an invoice item named "PM Surya Ghar Subsidy" | Refused | `test_billing` |
| U3-30 | Add an item whose description says "less subsidy" | Refused | `test_billing` |
| U3-31 | Add a tax row described "Subsidy adjustment" | Refused | `test_billing` |
| U3-32 | Raise an ordinary solar invoice | Passes | `test_billing` |

## GST (P3-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-33 | Search `api/gst.py` for a rate | No rate constant anywhere; the test reads the source and fails if one appears | `test_billing` |
| U3-34 | Check the seeded valuation rule | Present but **inactive**, percentages blank | `test_billing` |
| U3-35 | Try to value an invoice with no active rule | Refused with a clear error — never a silent default | `test_billing` |
| U3-36 | Enable postings but leave the CA confirmation off | Postings still blocked | `test_billing` |
| U3-37 | Tick the CA confirmation but disable postings | Postings still blocked | `test_billing` |
| U3-38 | Check both switches on a fresh install | Both off | `test_billing` |
| U3-39 | Build a reimbursement item | Carries the receipt reference; mentions no subsidy | `test_billing` |
| U3-40 | Activate a Separate Line Items rule and invoice a milestone | Two rows, goods and services, each with its own tax template | **manual** |

## Accounting (P3-A3S-005)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-41 | Record a statutory fee with the gates shut | No Journal Entry created | `test_accounting` |
| U3-42 | Open only the postings gate | Still no Journal Entry | `test_accounting` |
| U3-43 | Record a fee with the gates shut | Returns cleanly; operations unaffected | `test_accounting` |
| U3-44 | Resolve an account for an unmapped company | Refused | `test_accounting` |
| U3-45 | Map another company's account and resolve it | Refused, naming both companies | `test_accounting` |
| U3-46 | Blank a mapped account and resolve it | Refused — never defaulted | `test_accounting` |
| U3-47 | Open both gates and record a fee | Balanced Journal Entry for the fee amount | `test_accounting` |
| U3-48 | Post the same fee twice | Same entry returned; no duplicate | `test_accounting` |
| U3-49 | Record a fee the customer paid directly | Nothing posted | `test_accounting` |
| U3-50 | Open a posted entry | Carries source doctype, source document and posting purpose | `test_accounting` |
| U3-51 | Cancel and repost a corrected entry | Old entry cancelled, new one posted, both traceable | **manual** |

## O&M contract (P3-A3S-006)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-52 | Inspect a new contract | Five years from the warranty start date | `test_project_creation` |
| U3-53 | Count the visit plan | 15 visits, three a year, in date order | `test_project_creation` |
| U3-54 | Check visit months | None in June–September | `test_om` |
| U3-55 | Check the plan's span | Inside the contract term at both ends | `test_om` |
| U3-56 | Read the coverage table | Inspection Included, workmanship Included, module washing **Chargeable**, grid faults Excluded | `test_project_creation` |
| U3-57 | Read the washing row's note | Says the customer provides the water | `test_om` |
| U3-58 | Check warranty terms on a Rayzon/Solinteg job | 15/30 modules, 10 inverter, read from Component Make | `test_project_creation` |
| U3-59 | Check the performance obligation | 75% floor, with the commissioning ratio recorded | `test_project_creation` |
| U3-60 | Try to cancel a scheme-mandated contract as an executive | Refused — it is a registration condition | **manual** |

## Visits (P3-A3S-006)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-61 | Submit a visit with all 12 checks OK | 12 counted OK, none as defect | `test_om` |
| U3-62 | Mark one check as a Defect | Counted as a defect; an Installation Snag is raised | `test_om` |
| U3-63 | Submit a visit with crew hours and travel | Cost rolls into the project's O&M category | `test_om` |
| U3-64 | Check the provision after a visit | Balance drawn down by the visit cost | `test_om` |
| U3-65 | Let a scheduled visit date pass | Marked **Missed** by the daily job | `test_om` |
| U3-66 | Record a chargeable washing visit | Draft invoice raised; nothing submitted | **manual** |

## Service tickets and SLA (P3-A3S-007)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-67 | Raise a Critical ticket | Due times computed from the contract's own hours | `test_service` |
| U3-68 | Compare Critical and Major | Critical is due sooner | `test_service` |
| U3-69 | Resolve inside the window | SLA marked met; resolved timestamp set | `test_service` |
| U3-70 | Resolve after the window | Recorded as a breach | `test_service` |
| U3-71 | Leave a ticket past its window and run the hourly scan | Escalated; a to-do is raised for a real person | `test_service` |
| U3-72 | Run the scan twice at the same breach level | No second escalation at the same rung | `test_service` |
| U3-73 | Let the breach widen and scan again | Escalates to the next rung | `test_service` |
| U3-74 | Scan with a resolved ticket present | Not escalated | `test_service` |
| U3-75 | Reopen a resolved ticket | Reopen counted, clock restarted, resolution cleared | `test_service` |
| U3-76 | Reopen twice | Escalated to the top — something is not actually fixed | **manual** |
| U3-77 | Remove every holder of the O&M manager role, then breach a ticket | Audience widens; if nobody is found it is written to the Error Log | **manual** |

## Performance (P3-A3S-007)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-78 | Post two monthly readings | Ratio computed against the prorated design expectation | `test_service` |
| U3-79 | Post four healthy readings | Obligation "Meeting"; counter at zero | `test_service` |
| U3-80 | Post three readings at 78% | Counter reaches 3; a **Major** ticket is raised | `test_service` |
| U3-81 | Post one reading at 60% | Obligation "Breached"; a **Critical** ticket is raised immediately | `test_service` |
| U3-82 | Keep posting low readings | Still one open Critical ticket — the queue is not spammed | `test_service` |
| U3-83 | Post a healthy reading after two low ones | Counter resets to zero | `test_service` |
| U3-84 | Check the contract's performance log | One row per month, no duplicates | `test_service` |

## Warranty claims (P3-A3S-008)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-85 | Claim on a Rayzon module | 15-year term, expiry from the contract start | `test_om` |
| U3-86 | Claim on a performance basis | 30-year term | `test_om` |
| U3-87 | Claim with a failure date past expiry | Flagged as outside warranty | `test_om` |
| U3-88 | Claim using another installation's serial | Refused, naming where the serial actually belongs | `test_om` |
| U3-89 | Claim using an unregistered serial | Refused | `test_om` |
| U3-90 | Record a claim value and a partial recovery | Cost borne by the company is the balance | `test_om` |
| U3-91 | Mark a claim Replaced with a new serial | Old row flagged replaced; new serial appended carrying the DCR certificate | `test_om` |
| U3-92 | Check the installation's timeline after U3-91 | A comment records the swap | **manual** |

## Renewals (P3-A3S-008)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-93 | Bring a contract inside the renewal window | An Opportunity is raised with the service history | `test_om` |
| U3-94 | Run renewal detection twice | Still one opportunity | `test_om` |
| U3-95 | Run it for a contract with no party | Skipped and logged, not created against nobody | **manual** |

## Reports (P3-A3S-009)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-96 | Check every Phase 3 report is installed | All 14, in the Solar Projects module | `test_reports` |
| U3-97 | Run each report | All return columns without error | `test_reports` |
| U3-98 | Check every column against its rows | No column names a field the rows do not carry | `test_reports` |
| U3-99 | Open Project Profitability | Statutory pass-through in its own column, not in cost | `test_reports` |
| U3-100 | Open the O&M Contract Register | Each row shows that make's own warranty years | `test_reports` |
| U3-101 | Open Preventive Visit Compliance | Measured against visits that have fallen due | `test_reports` |
| U3-102 | Open Root Cause Analysis | Grouped by cause and category | `test_reports` |
| U3-103 | Open the Renewal Pipeline | Only contracts inside the window | `test_reports` |
| U3-104 | Miss a visit, then open Scheme Obligation Compliance | Flagged at risk, missed visit counted | `test_reports` |

## Roles and permlevel (P3-A3S-010)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-113 | Check every Currency field in the module | All at permlevel 1 | `test_permissions` |
| U3-114 | Check the Project costing fields | Contract value, cost, margin and provision all at permlevel 1 | `test_permissions` |
| U3-115 | Check who holds level 1 | Only O&M Manager, Project Manager, Accounts Executive, Accounts Manager, System Manager | `test_permissions` |
| U3-116 | Check the technician | Never granted level 1 anywhere | `test_permissions` |
| U3-117 | Check the coordinator | Never granted level 1 — read-only on financials means not at level 1 | `test_permissions` |
| U3-118 | Check ordinary Project access after the grant | Level-0 roles intact; adding a Custom DocPerm must not discard the standard ones | `test_permissions` |
| U3-119 | List Projects with a permlevel-0 field | The field is returned, not silently dropped | `test_permissions` |
| U3-120 | Call a posting function as a technician | Refused at function level, not only by doctype permission | `test_permissions` |
| U3-121 | Open a Project as a Solar Service Technician | Costing and Commercials tabs invisible | **manual** |
| U3-122 | Open an O&M Contract as a technician | Provision and contract value invisible; coverage and visits visible | **manual** |

## Renewals and expansion (P3-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-123 | Renew a contract for two years | A paid AMC successor, linked back to its predecessor | `test_om` |
| U3-124 | Check the successor's start date | The day after the predecessor ends | `test_om` |
| U3-125 | Compare coverage and service levels | Carried across unchanged; nobody retypes twelve rows | `test_om` |
| U3-126 | Check the predecessor after renewal | Marked Renewed, linked forward | `test_om` |
| U3-127 | Renew twice | The same successor is returned | `test_om` |
| U3-128 | Check the successor's visit plan | Its own calendar, sized to its term | `test_om` |
| U3-129 | Try to renew a draft contract | Refused | `test_om` |
| U3-130 | Press "Renew Contract" on a live contract | Dialog asks for term and value only | **manual** |
| U3-131 | Open System Expansion Candidates | Lists grown consumption and unused surveyed roof — a report, never an automatic opportunity | `test_reports` |

## Generation capture (P3-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-132 | Import a portal CSV export | Readings created, one per date | `test_service` |
| U3-133 | Import the same file again | Every row skipped; nothing duplicated | `test_service` |
| U3-134 | Import a file with one unreadable date | The rest still import; the bad line is named | `test_service` |
| U3-135 | Import a file with no date column | Refused with a clear message | `test_service` |
| U3-136 | Import a file with no reading column | Refused | `test_service` |
| U3-137 | Import an empty file | Refused | `test_service` |
| U3-138 | Press "Capture Reading" on a submitted visit | A reading sourced "O&M Visit", dated the visit | `test_service` |
| U3-139 | Press it twice | The same reading is returned | `test_service` |
| U3-140 | Open an O&M Contract | Chart shows expected against actual by month | **manual** |

## Customer portal (P3-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-141 | Log in as a customer and open /solar | Their own system, warranty, generation, service history, documents and invoices | `test_portal` |
| U3-142 | Check another customer's system is absent | Not listed | `test_portal` |
| U3-143 | Edit the installation id in the request | Refused on every endpoint | `test_portal` |
| U3-144 | Compare a made-up id with someone else's | Identical error — a different one would confirm the other record exists | `test_portal` |
| U3-145 | Open the page as a guest | Nothing returned | `test_portal` |
| U3-146 | Log in as a user with no linked customer | Nothing returned | `test_portal` |
| U3-147 | Raise a ticket against another customer's system | Refused | `test_portal` |
| U3-148 | Raise a ticket against your own | Created, sourced "Portal", on the right contract | `test_portal` |
| U3-149 | Submit an empty description | Refused | `test_portal` |
| U3-150 | Request another customer's document by id | Refused | `test_portal` |
| U3-151 | View the page source | No file URL anywhere — URLs are resolved per click | `test_portal` |
| U3-152 | Search the page data for cost, margin or provision | Absent; invoices are the only money shown | `test_portal` |
| U3-153 | Check a visit row on the portal | No labour, material, travel or visit cost | `test_portal` |
| U3-154 | Compare quoted band against actual units a day | Both shown side by side | **manual** |

## Tenancy and structure (P3-A3S-010)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-105 | Check the registry against the module | Every Solar Projects doctype is registered | `test_tenancy` |
| U3-106 | Check every doctype with a company field | All are isolated, with both permission hooks | `test_tenancy` |
| U3-107 | Resolve every scheduler and doc-event target | All callable | `test_tenancy` |
| U3-108 | Check modules.txt | Still exactly three modules — Phase 3 added doctypes, not modules | `test_tenancy` |
| U3-109 | Check the singletons | Still exactly one, A3 Sola Settings | `test_tenancy` |
| U3-110 | Create a second company | Its own milestone templates, cost categories and account mapping row | `test_tenancy` |
| U3-111 | Link a ticket to another tenant's contract | Refused, naming the owning company | `test_tenancy` |
| U3-112 | Open the Solar Projects workspace as an O&M user | Only the cards their roles allow | **manual** |

## Subsidy write-off (P3-A3S-005)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U3-155 | Write off more than is outstanding | Refused | `test_accounting` |
| U3-156 | Write off on a "Customer Claims Directly" claim | Refused — nothing was funded | `test_accounting` |
| U3-157 | Write off with the gates shut | Nothing posted | `test_accounting` |
| U3-158 | Write off with the gates open | Debit Write Off, credit Subsidy Receivable | `test_accounting` |
| U3-159 | Write off the same claim twice | The same entry is returned | `test_accounting` |
| U3-160 | Re-open Subsidy Receivable Ageing | The written-off amount has left the report | **manual** |
