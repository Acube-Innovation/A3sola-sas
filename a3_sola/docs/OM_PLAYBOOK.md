# O&M playbook — Solar Projects

The five-year obligation is not a service line the client sells. It is a condition of
staying registered as a vendor, and the ministry's grievance framework permits temporary
deactivation of a vendor that fails to address consumer complaints or rectify defects. This
playbook describes what the software does, and what the team has to do.

## What the client actually promised

Straight from the scope of work in their own proposal:

> Free inspection for five years (three visits a year) and maintenance if required.
> Washing of solar panels is not included and is arranged by the client.
> Training will be provided.

and, on the customer's side:

> Periodic cleaning of solar panels after completion of system installation, and water for
> cleaning.

Every one of those sentences is a row in the contract's coverage table. Module washing is
**Chargeable**, not Excluded and not Included — the client will do it, and will invoice for
it, and the customer supplies the water. Grid faults are **Excluded**; they are the DISCOM's.

## What happens automatically at commissioning

Submitting a Commissioning Report runs the Phase 2 extension point
`stages.on_commissioning_submitted`, which:

1. creates the **Project**, carrying the whole solar context across;
2. creates the **Solar Billing Plan** from the matching milestone template;
3. backfills **Statutory Fee Recovery** records for fees already paid;
4. creates the **Solar OM Contract** — five years from the warranty start date;
5. builds the **visit plan** — 15 visits, three a year, spaced and pushed clear of the
   monsoon;
6. reads the **warranty terms from Component Make**, per site;
7. **accrues the O&M provision** against the project.

None of it is retyped and none of it is a constant.

## Warranty terms come from the make, never from a house figure

Rayzon is 15-year product and 30-year performance. Vikram and Renewsys are 12/30. Solinteg
inverters are 10 years, SolarEdge 8, Hoymiles 12, Polycab 7. A Rayzon roof and a Vikram roof
next door expire three years apart.

`om.compute_warranty_terms()` reads every one of those from the **Component Make** master.
A warranty claim's expiry is computed from *that* make's term and *this* contract's start
date. If someone edits a make's term, new claims follow it; existing claims keep what was
computed when they were raised.

## The visit calendar

* Three preventive visits a year, 15 across the term.
* The first visit of each year is an **Annual Health Check**; the others are **Preventive**.
* Visits that would land in the Kerala monsoon (June–September) are pushed to just after it.
  A cleaning visit in the middle of the monsoon is wasted labour.
* A visit whose scheduled date passes without a visit record is marked **Missed** by the
  daily scheduler. It is not silently rescheduled.

**Preventive Visit Compliance** reports against what has actually fallen due, not against
the full 15 — a contract three months old is not 93% non-compliant.

## Recording a visit

The 12-point checklist is fixed and comes from `om.VISIT_CHECKLIST`. Each row is **OK**,
**Attention Required** or **Defect**.

* A **Defect** raises a Phase 2 **Installation Snag** automatically, with source "O&M Visit".
  Safety and Earthing defects are Critical by default.
* Visit cost is the crew's own hourly rate (from the employee's CTC), plus materials, plus
  travel at `travel_cost_per_km`. It draws down the O&M provision and rolls into project cost
  under the `O&M` category.
* A chargeable visit (module washing, customer-caused damage) can raise a draft invoice.
  Nothing is auto-submitted.

## Service tickets and the SLA clock

Response and resolution windows come from the **contract**, not from a global default:

| Severity | Response | Resolution |
|---|---|---|
| Critical | `critical_response_hours` | `critical_resolution_hours` |
| Major | `major_response_hours` | `major_resolution_hours` |
| Minor | `major_response_hours` | `minor_resolution_days` × 24 |

`sla.hourly_sla_scan()` runs every hour and escalates at 75%, 100% and 150% of the
resolution window — to the assignee, then the O&M manager, then the escalation role. Each
rung fires **once**. Every escalation writes a ToDo and a timeline comment, so the
compliance record is on the document itself.

If a role has no holder the audience widens automatically rather than escalating into thin
air, and if nobody at all can be found that fact is written to the Error Log. An escalation
that reaches nobody is not an escalation.

A ticket reopened `ticket_reopen_escalation_threshold` times (default 2) escalates straight
to the top: something is not actually fixed.

## Performance: two thresholds that mean different things

They are not interchangeable and the software does not treat them as such.

**The operational threshold** (`underperformance_threshold_percent`, default 80%) is a
service signal. `underperformance_consecutive_readings` (default 3) readings below it raise
a **Major** ticket — the system is not producing what it was designed to.

**The contractual floor** (`contractual_performance_ratio_percent`, default 75%) is a clause
in a signed agreement. A single reading below it sets the contract's obligation status to
**Breached** and raises a **Critical** ticket. This is a contractual exposure, not an
observation.

One open performance ticket per contract — the queue is not spammed.

## Warranty claims

* Every claim must name a serial that is in **this installation's** serial register. A
  serial from another installation is refused, and the error names where it actually
  belongs.
* Expiry is computed from the make's term and the claim basis (Product or Performance).
* A claim marked **Replaced** updates the serial register: the old row is flagged replaced,
  the new serial is appended carrying the DCR certificate number across. Traceability has to
  survive the swap or the DCR manifest goes stale.
* A **Rejected** claim leaves the cost with the company. That figure appears in the register
  and on the project's cost.

## Recording generation

Almost nobody keys readings in. Every client exports a CSV from SolarEdge, Solinteg or
Hoymiles, so the Generation Reading list carries **Import from Portal Export**: paste the
export, name the installation, and rows already on file are skipped rather than duplicated.
A line that cannot be read is reported by line number; the rest of the file still imports.

For a site with no portal, **Capture Reading** on a submitted O&M Visit records the meter
while the technician is still on the roof. A reading taken a week later against a
remembered number is worse than no reading.

The O&M Contract form charts expected against actual by month. The question that answers —
"is it getting worse" — is not one a table of readings answers.

## Renewals

A contract inside `contract_expiry_window_days` (default 90) becomes an **Opportunity** in
Solar CRM, once, carrying the visit compliance percentage, the open ticket count and the
performance history. The site is known and the relationship exists — it is the warmest lead
on the book.

If the contract has no party the opportunity is skipped and logged rather than created
against nobody.

**Renew Contract** on a live contract raises the successor: type **AMC (Paid Renewal)**,
starting the day after the predecessor ends, with the coverage and service levels the
customer is already used to carried across unchanged. The predecessor is marked **Renewed**
and linked in both directions, so the service history stays continuous across the join. The
only thing the renewal cannot infer is the price.

**Expansion** is a report, not an automatic opportunity. **System Expansion Candidates**
lists consumers whose consumption has grown past what the array offsets, and roofs the
Phase 1 survey said would take more than was installed. Consumption grows for all sorts of
reasons — a new tenant, a bad summer, a faulty meter — and raising a sales opportunity off
a number the customer has not discussed puts the client in front of them with the wrong
conversation. A human makes the call.

## What the customer sees

The portal at `/solar` is read-only and login-gated. It shows a customer their own system
details, commissioning date, SPIN and net meter, warranty end dates **by component and
make**, generation against both the design expectation and the daily band their proposal
quoted, the next visit date, past service reports, their own documents and their own
invoices — plus a form to raise a ticket.

Ownership is re-derived from the session on every request and never taken from a URL
parameter, and a document's file URL is resolved only when the customer clicks, so there
is no URL in the page to share or to guess at. Nothing financial beyond their own invoices
reaches it: no cost, no margin, no provision, no subsidy receivable, not even a visit's
labour cost.

## Daily and hourly jobs

| When | What |
|---|---|
| Hourly | `sla.hourly_sla_scan` — escalate breaching tickets |
| Daily | `om.mark_due_and_missed_visits` — mark visits due and missed |
| Daily | `om.detect_renewals` — raise renewal opportunities |
| Daily (long) | `costing.nightly_cost_refresh` — rebuild project costs |
| Daily (long) | `billing.refresh_billing_summaries` — rebuild billing summaries |

## The reports to read, and in what order

1. **Scheme Obligation Compliance** — anything at risk of the client's registration.
2. **Service Ticket SLA Compliance** — what is breaching now.
3. **Preventive Visit Compliance** — what was promised and not done.
4. **System Performance Ranking** — worst headroom first.
5. **O&M Provision Movement** — is the provision being consumed in step with the term.
6. **Renewal Pipeline** — what to sell next.
