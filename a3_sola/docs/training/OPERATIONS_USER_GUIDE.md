# Operations — order to commissioning

The longest part of the job and the part with the most paperwork. The app carries the
paperwork; you carry the site.

---

## The list you open first

**Solar Operations → Installation Stage Ageing.** Every live job with how long it has sat
in its current stage and whether it has breached its SLA. **Anything red is somebody
waiting on you or on the DISCOM.**

---

## The stage chain

Submitting a Sales Order opens a **Solar Installation** with its stage chain already
resolved. Which chain you get depends on three things: the subsidy scheme, the system type,
and the consumer category. A residential subsidised job and a commercial non-subsidised one
do **not** follow the same stages, and the app knows the difference.

The standard residential subsidised chain:

| Code | Stage | Waiting on |
|---|---|---|
| ORD | Order confirmed | You |
| NPA | National portal application | The portal |
| FEAS | DISCOM feasibility | KSEB |
| VFR | Vendor feasibility report | You |
| DSGN | Design finalised | You |
| PROC | Procurement | Your supplier |
| DISP | Dispatch | Logistics |
| INST | Installation | Your crew |
| KREG | KSEB registration fee | The customer |
| NMTR | Net meter | KSEB |
| KTST | KSEB inspection and testing | KSEB |
| AGMT | Net metering agreement | Both |
| PCR | Plant commissioning report | You |
| RFND | Registration fee refund | KSEB |

**A stage will not advance without its evidence.** That is the point: the evidence is what
you need at the counter later, and collecting it at the time is the only way it exists.

A stage that does not apply is **skipped with a reason** — a 3 kW job skips the electrical
inspector stage automatically, because it is under the threshold.

## Evidence and the document pack

Each stage names what it needs. Upload it there and it becomes part of the job's document
pack.

**Eighteen documents are generated for you** — the consumer-vendor agreement, the portal
application, the feasibility report, the EHS checklist, the KSEB forms, the net metering
agreement, the completion reports, the PCR. See `docs/DOCUMENT_CATALOGUE.md` for which form
is produced at which stage and what it is submitted against.

**Check the first one of each against your current paperwork.** A form that is subtly wrong
is rejected at a counter weeks later.

## Serial capture and DCR

**Installation → Serials.** Every module and inverter, with make, model, wattage and the
DCR certificate number.

**Why it matters and why you cannot skip it:** the subsidy requires domestically
manufactured content. At claim time you must prove which panels went on which roof. A serial
register filled in at installation takes ten minutes; reconstructed a year later it is
guesswork, and a rejected claim is the customer's money.

It is also what makes a warranty claim possible — you know exactly which module failed and
when it was installed.

## Work orders

**Installation → Installation Work Order.** Who is doing what, when, and for how many hours.
Structure erection, module mounting, DC and AC wiring, earthing, commissioning.

The same technician cannot be booked twice over the same dates — the app refuses, and that
refusal has saved a scheduling clash.

## Portal applications and statutory fees

**Portal Application** tracks the national portal submission and any query raised against
it. A query sitting unanswered is the commonest reason a job stalls, and it shows on the
ageing report.

**Statutory Fee Payment** records what was paid, by whom, and whether it is refundable. If
your company fronted it, that becomes a **Statutory Fee Recovery** against the project so
it is chased rather than forgotten.

## Snags

**Installation Snag** — anything found at QC or reported from site. Severity matters:

- **Critical or Major** — blocks commissioning. Deliberately.
- **Minor** — recorded, scheduled, does not block

Link a snag to the work order that will rectify it. If it recurs after the job is live, it
becomes a Service Ticket and the history follows it.

## Commissioning

**Commissioning Report** is the big one: the inspection, the protection settings with proof
for each, first-day generation against measured irradiance, and the customer handover.

Submitting it **opens the Project, the billing plan and the O&M contract automatically**.
That is the handover from Operations to Projects.

---

## Your daily rhythm

1. **Installation Stage Ageing** — what is stuck
2. **Portal Application** queries — what is waiting on an answer
3. **Document Pack Status** — which jobs are missing evidence
4. Your crew's work orders for today

## Things that trip people up

- **You cannot skip a stage to catch up.** The evidence gate is the product.
- **Serials at installation, not later.** A claim without them is refused.
- **A major snag blocks commissioning.** Close it or downgrade it with a reason.
- **The refund stage is real money.** The registration fee comes back; RFND is how you
  remember to claim it.
