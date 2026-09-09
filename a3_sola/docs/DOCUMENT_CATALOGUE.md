# Document catalogue

Every document the app generates, the client form it reproduces, and what it reads. Review
each against your current paperwork before go-live — a form that is subtly wrong is
rejected at a counter weeks later, and that is the failure this engine exists to prevent.

All eighteen render from **one** context builder,
`a3_sola.api.documents.get_document_context`. That is why the consumer number on the bank
letter and the consumer number on the KSEB annexure cannot differ: they are the same value.

## How it works

1. A **Solar Document Template** holds the body as Jinja, its category, the stage it is due
   at, its recipient, whether it needs stamp paper and who signs it. The template is data —
   a KSEB circular changing a form is an edit, not a deployment.
2. A **Document Template Set** groups templates for a job type (financed, self-funded,
   commercial).
3. **Generate Document Pack** on Solar Installation renders everything due at the current
   stage, files each into the document checklist, and logs what was generated, from which
   template version, by whom and when.
4. Editing a watched source field (consumer number, capacity, an identifier, the payee bank
   block) marks the affected documents **stale**. A stale document that has already been
   issued warns loudly before regeneration — it has left the building.

## The catalogue

| Code | Document | Generated from | Task | Source file | Signed by | Stamp paper |
|---|---|---|---|---|---|---|
| `MNRE-CONSUMER-VENDOR-AGREEMENT` | Consumer-Vendor Agreement (PM Surya Ghar) | Solar Installation | ORD | 05_PMSGY Vendor Agreement.docx | Both | — |
| `NP-APPLICATION` | National Portal Application Data Sheet | Portal Application | NPA | Data sheet for keying into pmsuryaghar.gov.in. Never automate the portal. | — | — |
| `NP-COMPLETION-REPORT` | Project Completion Report (National Portal) | Subsidy Claim | SUBREQ | the PCR data the client uploads after commissioning. | Both | — |
| `BANK-COVERING-LOAN` | Bank Covering Letter - Loan Application | Loan Application | LOAN | 01_Bank Covering Letter_Loan.docx | — | — |
| `BANK-VENDOR-FEASIBILITY` | Residential Rooftop Solar Vendor Feasibility Report | Loan Application | LOAN | 02_Vendor Feasiility Report.docx | Authorised Signatory | — |
| `BANK-EHS-CHECKLIST` | EHS Guidance Checklist | Loan Application | LOAN | RTS Vendor Feasibility Report PG 2.docx. Rendered from the Phase 1 site survey. | Authorised Signatory | — |
| `BANK-COMPLETION-REPORT` | Project Completion Report (Bank) | Document Pack | BCOM | 03_Completion Report for Bank.docx and 06_DATA FOR COMPLETION REPORT.docx | Authorised Signatory | — |
| `BANK-COVERING-COMPLETION` | Bank Covering Letter - Balance Transfer | Document Pack | BCOM | 04_Bank Covering Letter_Completion.docx | — | — |
| `KSEB-COVERING-COMPLETION` | Covering Letter to the Assistant Engineer - Registration and Completion | Document Pack | KFORMS | To The Asst. Engineer-Covering Letter.docx | Consumer | — |
| `KSEB-NETMETER-REQUEST` | Request for Allocation of Bidirectional Meter | Document Pack | KFORMS | To The Asst. Engineer-Net Meter.docx | Consumer | — |
| `KSEB-REFUND-REQUEST` | Request for Refund of Registration Fee | Document Pack | CFILE | To The Asst. Engineer_Refund.docx | Consumer | — |
| `KSEB-FORM-1` | Annexure / Form 1 | Installation Task | FRM1 | KSEBL Form 1.docx | Consumer | — |
| `KSEB-FORM-2` | Annexure / Form 2 | Document Pack | KFORMS | KSEBL Form 2.docx | Consumer | — |
| `KSEB-FORM-3` | Annexure / Form 3 | Document Pack | KFORMS | KSEBL Form 3.docx | Consumer | — |
| `KSEB-TESTING-CHECKLIST` | Installation and Inverter Testing Checklist | Document Pack | KFORMS | KSEB/CHECKLIST.xlsx - the form the Assistant Engineer inspects against. | Consumer | — |
| `KSEB-NETMETER-AGREEMENT` | Net Metering Agreement (Stamp Paper) | Solar Agreement | KFORMS | KSEB Agreement.docx, including the full schedule. | Consumer and Two Witnesses | **Yes** |
| `CUST-COMMISSIONING-CERTIFICATE` | Commissioning Certificate | Commissioning Report | COMM | Customer-facing certificate issued at handover. | Authorised Signatory | — |
| `CUST-HANDOVER-PACK` | Customer Handover Pack | Document Pack | CFILE | Warranty by make, net meter details and the O&M contact. | Both | — |
| `COMPLETION-REPORT-DATA` | Data for Completion Report | Material Dispatch Notice | MATL | 06_DATA FOR COMPLETION REPORT.docx / DATA FOR COMPLETION REPORT.pdf | — | — |
| `STAMP-PAPER-DATA` | Data for Stamp Paper | Solar Agreement | STMP | Data for Stamp Paper_rAJAGOPALAN.pdf | — | — |
| `WARRANTY-CERTIFICATE` | Warranty Certificate | Document Pack | CFILE | Terms come from Component Make and the package | Authorised Signatory | — |
| `CUSTOMER-CONTACTS` | Whom to Contact | Document Pack | CFILE | Support contacts come from the Company record | — | — |
| `CUSTOMER-STATEMENT` | Statement of Account | Document Pack | CFILE | Invoices and allocated payments from ERPNext | — | — |
| `BOM-SUMMARY` | Bill of Materials | Installation Task | DSGN | The design freeze: what goes to site, exploded from the package to the installed capacity. | — | — |

## What each template reads

Every template receives the same context object:

| Key | Contents |
|---|---|
| `installation` | Solar Installation, including all five external identifiers |
| `consumer` | Solar Consumer — connection, tariff, connected load, bank block, local body, survey number |
| `company` | Company — registered portal vendor, executing EPC and payee bank blocks |
| `estimate`, `survey`, `package` | Phase 1 design, site survey (with the EHS answers) and package |
| `section` | DISCOM Section — division, subdivision, Assistant Engineer, office address |
| `loan`, `commissioning`, `agreement` | The Phase 2 records, where they exist (`agreement` is the executed Solar Agreement) |
| `task`, `source` | The task document a template is generated from - the pack, the notice, the agreement, the task |
| `contractor`, `completion_data` | The electrical contractor and the serial data set the completion reports print |
| `warranty`, `contacts`, `statement`, `bom_items` | Warranty terms from Component Make, the company's support contacts, the customer's ledger, the bill of materials |
| `meter`, `work_orders`, `google_review_url` | The meter task's particulars, the job's work orders, the review link |
| `serials`, `module_serials`, `inverter_serials` | The serial register, ready for the completion reports |
| `ehs` | The lender's checklist answers, in the lender's own question wording |
| `address_text`, `discom_name`, `today`, `fmt_money` | Rendering helpers |

## The two completion reports

`BANK-COMPLETION-REPORT` and `NP-COMPLETION-REPORT` both render from
`a3_sola.api.serials.get_completion_report_data`, so they cannot disagree with each other
or with the serial register. That function returns exactly the field set the client fills
by hand today: consumer name, address, consumer number, electrical section, service
connection type, plant capacity and type, module make and wattage, every module serial
number, and the inverter make, capacity and serial number.

## Editing a template

Edit `body_template` on the Solar Document Template. The version increments, and previously
generated documents keep the version they were rendered from. Do **not** paraphrase the
fixed wording: these are read at a counter by someone comparing them to a form they know.
