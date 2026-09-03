# Finance — billing, GST and profitability

---

## Before anything posts to your ledger

**Two switches, and both are off until you say otherwise.**

| Switch | Requires |
|---|---|
| `enable_accounting_postings` | Your account mappings filled in, and your CA's confirmation |
| `gst_treatment_confirmed_by_ca` | That confirmation **in writing** |

Until then the app records everything — invoices, costs, subsidy receivable, settlements —
and posts **nothing** to the general ledger. You can run every report and reconcile every
figure before a single journal entry exists.

**This is deliberate.** A wrong posting at scale is far harder to unwind than a delayed one.

### The GST question you must answer

Solar EPC is a composite supply. The industry commonly applies a 70:30 goods-to-services
valuation, with the goods rate having moved to 5% in the September 2025 reform. Published
sources still disagree, some EPCs bill goods and services on separate lines for input-credit
clarity, and the right answer depends on how your contracts are written.

**The app refuses to guess.** Set the valuation rule, attach the item tax templates, record
the confirmation, then switch postings on.

---

## Milestone billing

**Solar Billing Plan**, created automatically when a job commissions. Milestones come from a
template you can edit — typically advance, on dispatch, on installation, on commissioning.

A milestone is **triggered** when its event happens, then invoiced. The invoice is created
as a **draft, never submitted automatically**. Somebody looks at it first.

**Predecessors are enforced.** You cannot invoice the commissioning milestone before the
installation one.

## The subsidy — the rule that matters most

**The subsidy never appears on an invoice.** Not as a line, not as a tax, not as a discount.

It is a government transfer to the customer's bank account after commissioning. The customer
owes you the full contract value; the subsidy is between them and the government.

The app refuses any invoice or quotation that treats it otherwise.

**Where it does appear:** if your company fronted the subsidy gap — you charged the customer
the net and are waiting for the government — that is a **Subsidy Claim** with
`claim_model = Company Funded Gap`, and it is a receivable you should be ageing.

**Subsidy Receivable Ageing** is the report for that. Anything past ninety days needs a call.

## Statutory fees

Application fees, registration fees and net meter charges are a **reimbursement, not
revenue**. They print in their own block.

If you paid them on the customer's behalf, **Statutory Fee Recovery** tracks what is owed
back and what has been recovered. The registration fee is also refundable by KSEB after
commissioning — that is a separate claim and the RFND stage is where it is chased.

## Project profitability

**Project Profitability** — quoted value against actual cost, per job.

Costs come from work order crew hours, materials issued and the extras captured at survey.
This is the number that tells you whether your quoting is right, and it is only as good as
the work orders your site team fills in.

**Cost Overrun Analysis** shows where the estimate and the reality diverged, and it is worth
reading monthly rather than at year end.

## Reconciliation

**Settlement Reconciliation** — the gateway's settlement file against what you recorded.

Every line should match. An unmatched line is money that arrived and is not attributed, and
until it is, your revenue figures are wrong in a way nobody can see. It alerts weekly.

---

## Your monthly rhythm

1. **Billing vs Collection** — what was invoiced against what arrived
2. **Subsidy Receivable Ageing** — anything past ninety days
3. **Statutory Recovery Register** — fees fronted and not recovered
4. **Project Profitability** — jobs closed this month
5. **Settlement Reconciliation** — every line matched

## Things that trip people up

- **The subsidy is not revenue and not a discount.** It is the customer's money from the
  government.
- **Statutory fees are not revenue.** They pass through.
- **Invoices are drafts.** Somebody submits them; the app never does.
- **Postings off does not mean nothing is recorded.** Everything is. It simply has not
  reached the ledger yet.
