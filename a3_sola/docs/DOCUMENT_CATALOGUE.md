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

| Code | Document | Source document | Stage | Signed by | Stamp paper |
|---|---|---|---|---|---|
| `MNRE-CONSUMER-VENDOR-AGREEMENT` | Consumer-Vendor Agreement (PM Surya Ghar) | 05_PMSGY Vendor Agreement.docx | ORD | Both | — |
| `NP-APPLICATION` | National Portal Application Data Sheet | portal submission fields | NPA | — | — |
| `NP-COMPLETION-REPORT` | Project Completion Report (National Portal) | PCR upload data | PCR | Both | — |
| `BANK-VENDOR-FEASIBILITY` | Residential Rooftop Solar Vendor Feasibility Report | 02_Vendor Feasiility Report.docx | VFR | Authorised Signatory | — |
| `BANK-EHS-CHECKLIST` | EHS Guidance Checklist | RTS Vendor Feasibility Report PG 2.docx | VFR | Authorised Signatory | — |
| `BANK-COVERING-LOAN` | Bank Covering Letter — Loan Application | 01_Bank Covering Letter_Loan.docx | LOAN | — | — |
| `BANK-COMPLETION-REPORT` | Project Completion Report (Bank) | 03_Completion Report for Bank.docx + 06_DATA FOR COMPLETION REPORT.docx | BCOM | Authorised Signatory | — |
| `BANK-COVERING-COMPLETION` | Bank Covering Letter — Balance Transfer | 04_Bank Covering Letter_Completion.docx | BCOM | — | — |
| `KSEB-FORM-1` | Annexure / Form 1 | KSEBL Form 1.docx | KTST | Consumer | — |
| `KSEB-FORM-2` | Annexure / Form 2 | KSEBL Form 2.docx | KTST | Consumer | — |
| `KSEB-FORM-3` | Annexure / Form 3 | KSEBL Form 3.docx | KTST | Consumer | — |
| `KSEB-COVERING-COMPLETION` | Covering Letter to the Assistant Engineer | To The Asst. Engineer-Covering Letter.docx | KTST | Consumer | — |
| `KSEB-TESTING-CHECKLIST` | Installation and Inverter Testing Checklist | KSEB/CHECKLIST.xlsx | KTST | Consumer | — |
| `KSEB-NETMETER-REQUEST` | Request for Allocation of Bidirectional Meter | To The Asst. Engineer-Net Meter.docx | NMTR | Consumer | — |
| `KSEB-NETMETER-AGREEMENT` | Net Metering Agreement | KSEB Agreement.docx (with full schedule) | AGMT | Consumer + 2 witnesses | **Yes** |
| `KSEB-REFUND-REQUEST` | Request for Refund of Registration Fee | To The Asst. Engineer_Refund.docx | RFND | Consumer | — |
| `CUST-COMMISSIONING-CERTIFICATE` | Commissioning Certificate | customer-facing | COMM | Authorised Signatory | — |
| `CUST-HANDOVER-PACK` | Customer Handover Pack | customer-facing | COMM | Both | — |

## What each template reads

Every template receives the same context object:

| Key | Contents |
|---|---|
| `installation` | Solar Installation, including all five external identifiers |
| `consumer` | Solar Consumer — connection, tariff, connected load, bank block, local body, survey number |
| `company` | Company — registered portal vendor, executing EPC and payee bank blocks |
| `estimate`, `survey`, `package` | Phase 1 design, site survey (with the EHS answers) and package |
| `section` | DISCOM Section — division, subdivision, Assistant Engineer, office address |
| `loan`, `commissioning`, `agreement` | The Phase 2 records, where they exist |
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
