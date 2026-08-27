# Where each figure came from

The client supplied a folder of live operating documents. This maps each to the part of the
app that now carries it, and lists every discrepancy found, so the client can confirm
nothing was misread.

## Documents read

| Source document | What it now drives |
|---|---|
| Project Proposal 3kW / 5kW 1-Ph / 5kW 3-Ph / 8kW 3-Ph | Proposal print format section order; specification table; KSEBL expenses; 70:20:10 payment terms; delivery schedule; scope-of-work split; general terms |
| 10kWp_3PH_NDCR.docx | Multi-option quoting (string / optimiser / microinverter at ₹4.80L / ₹4.90L / ₹5.10L); non-DCR TopCon package; per-make warranty matrix; daily generation band |
| Master Data.xlsx | Proposal register: fiscal-year series `RENC-PROP-YY-YY-nnn`, sequence, salutation, name, mobile, capacity, location, generated file name |
| Master Data Macro.xlsm (Sheet2) | The 26-field Solar Package master, including two side-by-side inverter options and the statutory block |
| Renewcore_Solar_Lead_Tracker_Master_v2.xlsx | Lead outreach: call status, four-step cadence, lead status, follow-up due logic, and the dashboard's headline numbers and breakdowns |
| Greeting message with quotation.docx | The "Proposal Sent" outreach template, with WhatsApp bold markers preserved and the signature and eight social links held in Settings |
| KSEB: forms, covering letters, agreement, CHECKLIST.xlsx | DISCOM Section as correspondence data; consumer connection, tariff category, connected load in watts, bank block, local body / village / survey number; SPIN. The document pack itself is Phase 2 |
| BANK: covering letters, Vendor Feasibility Report, RTS EHS checklist, Completion Report, PMSGY Vendor Agreement | The EHS checklist on Site Survey (verbatim question text); feasibility status and installable capacity; the financed-sale fields on Quotation; the registered-vendor / EPC / payee split on Company |

## Figures taken directly

- Subsidy slabs: 1 kW ₹30,000, 2 kW ₹60,000, 3 kW+ ₹78,000 capped, 10 kW ceiling.
- Roof area: 250 sq ft (3 kW), 350 (5 kW), 400 (8 kW), 800 (10 kW) → 80 sq ft/kW default.
- Daily generation: 12–15 units (3 kW), 20–25 (5 kW), 40–50 (10 kW) → 4.0–5.0 units/kWp/day.
- Warranty by make: Rayzon 15/30, Vikram 12/30, Renewsys 12/30, Solinteg 10, SolarEdge 8,
  Hoymiles 12; system warranty 5 years.
- Package specification codes: 3Kw 1PH, 3Kw 1PH Micro, 5KW 1PH, 5KW 3PH, 5KW 1PH Micro,
  5KW 3PH Micro, 5KW 1PH Hybrid, 5KW 1PH Hybrid with 3Kwp, 8KW 3PH, 10KW 3PH Non-DCR.
- DISCOM sections: Athani, Vennala, Vazhakkala, Kodakara, Koovappady, Vellangallur,
  Angamaly, Aluva, Perumbavoor, Chalakudy, Irinjalakuda, Muvattupuzha, Kothamangalam,
  North Paravoor, Kakkanad, Fort Kochi, Kodungallur, Cherthala, Changanassery.
- Payment terms: 70% advance with PO, 20% after delivery and installation, 10% after
  commissioning — with the variant that where the net meter is availed from KSEBL the final
  10% follows submission of the completion documents.
- Preventive service: free inspection for five years, three visits a year; panel washing
  excluded and arranged by the customer. (Consumed in Phase 3.)
- Performance ratio ≥ 75% at commissioning, maintained for five years, measured with a
  NABL-calibrated radiation sensor. (Consumed in Phases 2 and 3.)

## Discrepancies found — please confirm

### 1. Statutory fee figures contradict each other (highest priority)

| Template | Registration charged | Refundable stated | Derivable? |
|---|---|---|---|
| 3 kW | ₹3,540 | ₹2,400 | ✅ ₹1,000/kW + 18% GST, 80% of base |
| 5 kW | ₹8,288 | ₹4,000 | ❌ ₹8,288 follows no rule; ₹4,000 = 80% of ₹5,000 ✅ |
| 8 kW | ₹8,288 | ₹4,000 | ❌ both |
| 10 kW | ₹11,800 | ₹4,000 | ✅ charged / ❌ refund should be ₹8,000 |

The app implements the 3 kW rule and computes everything from it. A regression test asserts
the 3 kW figures exactly and asserts the 10 kW refund is ₹8,000 and not ₹4,000.

### 2. Application fee shown two ways

₹1,000 on the 3 kW and 10 kW templates, ₹1,180 on the 5 kW and 8 kW. Modelled as one base
of ₹1,000 with a GST-applicable flag, so both figures are the same record rendered net or
gross. Confirm which the customer should see.

### 3. The 8 kW template's cost line says 5 kWp

`Project Proposal_8kW_3Phase.docx` states a capacity of 8 kWp in the executive summary but
its cost line reads "5kWp Three Phase". A copy-paste error in the template; the app derives
the description from the capacity so it cannot recur.

### 4. Panel cleaning: agreement vs proposal

The PM Surya Ghar vendor agreement makes O&M comprehensive for five years. The proposals
exclude panel washing and put water and periodic cleaning on the customer. Both are seeded
in Phase 3 coverage as *included inspection* plus *chargeable washing*. Confirm the position
you want to take with customers.

### 5. Module performance warranty: 25 years or 30

Older proposals state 25 years with 90%/80% floors; the most recent states 30. Both are
representable per make. Confirm against current supplier certificates.
