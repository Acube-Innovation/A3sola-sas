# Operations runbook

The daily operating rhythm for the Solar Operations module.

## Every morning, in this order

1. **Installation Pipeline Status** — every open job, the stage it is on, who owns that
   stage, days in stage against SLA. This is the standup report.
2. **Document Pack Status** — what is missing before the next external step. A job with an
   outstanding mandatory document cannot advance, so this is the real blocker list.
3. **External Dependency Ageing** — where working capital is trapped, grouped by the party
   holding it up and the section office. Take this to the DISCOM; it is the evidence.

Weekly: **Bank Disbursement Tracker**, **Statutory Fee and Refund Register**,
**Snag Register and Closure**.

## Handling a DISCOM query

1. Record it on the Portal Application as a query row with its date and text. The mapped
   installation stage blocks automatically, and the block reason carries the query.
2. Answer it, record the response and tick **Resolved**. The stage unblocks.
3. Query cycles are counted on the application. If a job has three or more, escalate — the
   application is probably wrong, not slow.

## When a stage breaches its SLA

The daily escalation job raises one ToDo per breach per reminder window (three days by
default) and addresses it to the **named Assistant Engineer** on the DISCOM Section record,
not to a generic address. If that name is missing, fix the section master — a chase without
a name does not get answered.

## Re-baselining SLAs from real data

After six months, open **Stage Cycle Time Analysis**. It reports the average, median and
90th percentile against the current SLA and suggests a new one covering 90% of observed
reality. Edit the Installation Stage Template; do not edit individual jobs.

Seventy-five days at feasibility is normal in Kerala. If your template says 45 and your
90th percentile says 78, the template is wrong, not the DISCOM.

## When a serial is rejected by the portal

The ministry rejects submissions containing a repeated module or inverter serial.

1. Open **Serial Traceability Register** and search the serial. It shows which installation
   already carries it, with its purchase receipt and delivery note.
2. If it was captured on the wrong job, remove it there first — the app refuses two
   installations holding the same serial.
3. If the manufacturer genuinely shipped a duplicate, record it and take it up with them;
   do not work around the guard.
4. Re-export the manifest and resubmit.

## Reissuing a stale document

A generated document goes **stale** when a fact it printed changes — a corrected consumer
number, a capacity change, a new bank account.

- Not yet issued: regenerate and carry on.
- Already issued: the app warns before regeneration. The copy you sent is still out there.
  Regenerate, then send the corrected document with a covering note. Do not silently
  replace it.

## The KSEB submission order

Documents go to the Assistant Engineer as one pack at the KTST stage:

1. Covering letter (it names every enclosure)
2. Annexure / Form 2 signed
3. Annexure / Form 3 for completion, with the panel and inverter datasheets and BIS
   certificates, the test-cum-completion certificate with the single line diagram and the
   serial numbers, the installation checklist and the solar meter calibration certificate
4. Solar agreement on stamp paper, signed

Generate the pack, print it, check it, then submit. The app produces it; a human submits it.

## Chasing a registration fee refund

80% of the registration base is refundable after commissioning. The app marks the refund
**Due** fifteen days after the COMM stage completes and raises a ToDo.

1. Generate the refund request. It carries the consumer's bank block and names the cancelled
   cheque as an enclosure — the DISCOM returns the request without one.
2. File it and record the claim date.
3. The escalation job chases anything outstanding beyond thirty days.
4. Record what actually arrived. A short receipt is flagged as **Short Received** with the
   variance, rather than being quietly closed.

## Chasing a bank balance disbursement

Financed jobs pay in two tranches. The balance follows the completion report.

1. At BCOM, generate the completion report and the balance covering letter.
2. Record the tranche on the Loan Application when it lands. The outstanding figure updates
   and the BCOM stage advances.
3. **Bank Disbursement Tracker** is grouped by lender and branch, because that is how the
   chasing is actually done.

## Commissioning: what will get you refused

The Assistant Engineer refuses on the inverter protection settings more than anything else.
Before booking the inspection, confirm every one of the seven functions has a recorded value
**and** documentary proof — an HMI screenshot, an OEM or NABL certificate naming the
inverter serial, or an on-site test report witnessed by the DISCOM. The app blocks
submission without them, which is cheaper than a second site visit.

The performance ratio must be at least 75% at commissioning, measured with a
NABL-calibrated radiation sensor whose certificate is valid on the day. Below that, only an
operations manager can proceed, and only with a recorded reason. It is a clause in a signed
agreement.

## What this module does not do

It posts nothing to the ledger. Subsidy receivables, statutory fee reimbursement, refund
settlement and O&M provisioning are all Phase 3, through the five extension points in
`a3_sola/api/stages.py`. If you are looking for a journal entry here, it is by design.
