# Accounting treatment — Solar Projects

This document exists because two of the decisions in Phase 3 are not the developer's to
make. They belong to the client's chartered accountant, and the software is built so that
nothing reaches a ledger until that person has said so in writing.

Read this before enabling accounting postings on a live site.

## The two gates

Every posting in `a3_sola.api.accounting` is gated on **both** of these, in
**A3 Sola Settings → Projects**:

| Setting | Meaning | Ships as |
|---|---|---|
| `enable_accounting_postings` | The client has decided this app may write to the ledger at all | Off |
| `gst_treatment_confirmed_by_ca` | A named CA has confirmed the GST valuation in writing | Off |

With either gate shut, `postings_enabled()` returns false and every posting function logs
what it *would* have posted and returns `None`. Operations is unaffected — a user can
commission a plant, record a fee and close a ticket exactly as before. Nothing is queued
for later replay either: when the gates open, `cancel_and_repost()` is the deliberate way
to bring history onto the books.

**Do not** work around these gates in code. They are the whole control.

## GST: why there is no rate anywhere in this app

Solar EPC in India is a composite supply. The prevailing approach applies a 70:30
valuation — 70% goods, 30% services — each at its own rate. But:

* published sources still disagree on the split and on the rates that attach to it;
* some EPCs bill on separate lines for input-credit clarity, others bill a single blended
  line, and the correct answer depends on how the contract is written;
* the client's own proposals quote a single all-inclusive figure and state no basis at all.

So `a3_sola/api/gst.py` contains **no rate constant**. There is a test that reads the
module's source and fails if one appears. Everything comes from a **Solar GST Valuation
Rule** record, which carries:

* `valuation_mode` — `Blended Single Rate`, `Separate Line Items`, or `Single Rate`
* `goods_value_percent` / `services_value_percent`
* the item, HSN/SAC code and **Item Tax Template** for each side
* `effective_from` / `effective_to`, so a change in position is dated rather than retro-fitted
* `applicable_consumer_category`, because a residential and a commercial supply may differ

Installation seeds **one rule, inactive, with the percentages blank**. That is deliberate.
An inactive rule cannot be resolved, and `resolve_valuation()` throws a clear error rather
than inventing a default. An invoice that cannot be valued correctly should not be raised.

### What the CA needs to decide

1. Is the supply valued 70:30, or on some other basis?
2. Is it billed as one blended line or two lines?
3. Which HSN and which SAC?
4. Which Item Tax Template attaches to each?
5. From what date does this position apply?

Record the answers on the Solar GST Valuation Rule, activate it, tick
`gst_treatment_confirmed_by_ca`, and note who confirmed it and when in the settings' CA
reference field.

## The subsidy: the one rule with no exception

**The subsidy never appears on an invoice.** Not as an item, not as a tax row, not as a
discount, not in a description.

Under PM Surya Ghar the subsidy is a government transfer paid to *the customer's* bank
account after commissioning. It is not the company's revenue, not its liability, and not a
price reduction it granted. An invoice that shows it is wrong in law and misstates output
tax.

This is enforced in `billing.reject_subsidy_on_invoice`, wired to Sales Invoice `validate`,
which scans item names, descriptions, item codes and tax row descriptions. Four tests cover
the four routes in.

Where the customer cannot fund the gap and the company fronts it, that is a **receivable
from the customer** — never a reduction of contract value:

```
DEBIT   Subsidy Receivable
CREDIT  Subsidy Recovery Income
```

and on recovery:

```
DEBIT   Bank
CREDIT  Subsidy Receivable
```

Under the "Customer Claims Directly" model the company has funded nothing, so **no entry is
required and none is made**. That absence is deliberate. It is not a missing feature.

## Statutory fees: pass-through, not cost and not revenue

The client's proposals say it plainly — DISCOM application, registration and net meter
charges are reimbursed against receipts. So:

* they are **excluded from project cost** (the `Statutory Fees` cost category is flagged
  `is_pass_through`) and therefore never touch margin;
* they are reported in their own column, `statutory_pass_through`, on every costing view;
* they are billed on a **separate reimbursement invoice**, outside the composite supply,
  built by `gst.build_reimbursement_item()` — which carries the receipt reference and no
  tax template;
* the registration fee is refundable, so what was paid, what was reimbursed by the customer
  and what came back from the DISCOM are three separate figures.

Postings, when the gates are open:

```
Fee paid on the customer's behalf
DEBIT   Statutory Fee Receivable
CREDIT  Bank

Refund received from the DISCOM
DEBIT   Bank
CREDIT  Statutory Refund Receivable
```

A fee the customer paid directly posts nothing — the company's money never moved.

## The O&M provision

The five-year obligation is a liability from the day of commissioning, not a cost that
appears when a van is dispatched. A percentage of contract value (`om_provision_percent`,
default 2%) is provided at commissioning and drawn down as visits happen:

```
At commissioning
DEBIT   O&M Expense
CREDIT  O&M Provision (liability)

As visits consume it
DEBIT   O&M Provision
CREDIT  O&M Expense
```

The **O&M Provision Movement** report shows consumption against elapsed term. A contract
two years in with an untouched provision usually means visits are not happening — which is
a compliance problem before it is an accounting one.

## Writing off a subsidy the customer will not repay

Where the company funded the gap and the customer will not pass their DBT over, the
receivable has to be recognised as a loss rather than aged forever:

```
DEBIT   Write Off
CREDIT  Subsidy Receivable
```

`write_off_subsidy_recovery()` is only ever called by a person — there is no ageing rule
that writes off automatically, because that is a management decision, not arithmetic. It
refuses to write off more than is outstanding, and refuses entirely on a claim where the
customer claimed directly (nothing was funded, so there is nothing to give up). Once
written off, the amount leaves the **Subsidy Receivable Ageing** report: a receivable
nobody intends to collect overstates what is actually recoverable.

## Account mapping is per company, and crossing is refused

`Solar Company Account Mapping` holds one row per company. `resolve_account()` throws if:

* the company has no mapping row;
* the requested account is not mapped;
* **the mapped account belongs to a different company.**

That last check is the important one. In a multi-tenant install, a posting that reaches
another tenant's ledger is the worst thing this layer can do, so it is refused loudly
rather than posted quietly. There is a test for exactly that.

## Idempotency

Every journal entry carries `a3s_source_doctype`, `a3s_source_document` and `a3s_purpose`.
Before posting, `_existing_entry()` looks for a submitted entry with the same three values
and returns it instead of posting again. Reposting is therefore safe, and
`cancel_and_repost()` is the supported way to correct one.

## Nothing is auto-submitted

`create_milestone_invoice()` creates a **draft** Sales Invoice and stops. A human reviews
and submits it. Milestone triggering is automatic because site progress is a fact; invoicing
is a decision.
