# Compliance notes — subscriptions

Two regulatory regimes touch Phase 5, and neither is a developer's call. This document
states what the implementation does, and what must be re-verified before go-live.

> **The values in A3 Sola Settings reflect the frameworks as understood at build time.
> They must be re-verified against current RBI and CBIC guidance before go-live.** The RBI
> in particular has revised the e-mandate threshold repeatedly — ₹2,000, then ₹5,000, then
> ₹15,000 — and will revise it again.

## RBI e-mandate framework

### What the framework requires, and where each is implemented

| Obligation | How this implementation meets it |
|---|---|
| **AFA at registration and first transaction** | The mandate is registered in the same customer interaction as the first payment — `register_mandate_with_first_payment()`. The customer authenticates once, for both. |
| **No-AFA ceiling on recurring debits** | `afa_free_debit_ceiling`, default ₹15,000. Every subscription's route is derived from it by `classify_collection()`. |
| **Pre-debit notification** | `pre_debit_notification_pass()` sends it, records `notice_sent_on` against the cycle, and **`auto_debit_pass()` refuses to debit a cycle whose notice was not sent in time.** That refusal is a hard block. |
| **Notice timing** | `pre_debit_notice_hours`, default 24, with a validation that refuses anything lower. |
| **Notice content** | Amount, debit date, plan, period, mandate reference and how to cancel — `templates/emails/pre_debit_notice.html`. |
| **Post-debit confirmation** | `post_debit_confirmation_pass()`, controlled by `send_post_debit_confirmation`, default on. |
| **Customer cancellation at any time** | `payments.cancel_mandate()` and the billing page's own control. Honoured immediately, not queued as a request. |

### The ceiling applies to the debit, not the price

This is the detail most easily got wrong, and it is worth stating plainly: the threshold
is measured on **the total amount debited, including GST**.

A Starter plan with two extra users is ₹13,600 — under a ₹15,000 ceiling. With 18% GST the
actual debit is **₹16,048**, which is over it. Classifying on the sticker price would
promise the customer an automatic debit their bank would decline.

`classify_collection()` is therefore always given the tax-inclusive figure, and there is a
test asserting exactly this boundary case.

### Why the higher ceiling does not apply

The ₹1,00,000 no-AFA ceiling covers insurance premiums, mutual fund subscriptions and
credit card bills. **A SaaS subscription does not qualify.** The configured default is the
general ₹15,000 figure, and it should not be raised to ₹1,00,000 on the reasoning that
some recurring payments enjoy it.

### Consequence for this pricing

| Plan | Cycle | Debit with GST | Route |
|---|---|---|---|
| Starter | Monthly | ₹3,540 | Auto Debit |
| Growth | Monthly | ₹7,080 | Auto Debit |
| Starter | Annual | ₹35,400 | Assisted Renewal |
| Growth | Annual | ₹70,800 | Assisted Renewal |
| Any | Monthly with enough extra users | above ₹15,000 | Assisted Renewal |

**Every annual plan routes to assisted renewal regardless of amount.** Two reasons: annual
amounts under this pricing exceed the ceiling anyway, and a mandate asked to fire twelve
months later has a high failure rate at the bank. Pretending otherwise loses renewals.

### When the RBI revises the threshold

1. Change `afa_free_debit_ceiling` in **A3 Sola Settings → Payments**.
2. Run the **AFA Exposure** report. It lists every subscription against the new ceiling and
   flags those within 15% of it.
3. Contact the customers whose route changes — a customer moving from auto-debit to
   assisted renewal must be told before their next cycle, not discovered by them.

Existing mandates are **not** reclassified: each one snapshots
`afa_ceiling_at_registration`, so a customer keeps the terms they actually authorised.

## GST on the subscription supply

**Distinct from Phase 3.** Phase 3's GST work concerns the tenant's own solar EPC
contracts — a composite supply with a contested valuation. This is the client selling a
software subscription: a service, taxed at the standard services rate, place of supply
determined by where the recipient is.

- Supplier in Kerala + customer in Kerala → **CGST + SGST**
- Supplier in Kerala + customer anywhere else → **IGST**

The rate comes from `subscription_gst_rate` in Settings. Nothing is hardcoded, and there is
a test asserting the module contains no rate constant.

The customer's GSTIN carries its state in the first two characters. Where that contradicts
the address, the invoice is **refused** rather than guessed at — a mismatch breaks the
customer's input tax credit, and they will find out at their next return.

Invoice numbering is gapless per company per fiscal year (April–March). A submitted invoice
can be cancelled but never deleted.

### e-invoicing

Implemented behind `enable_einvoicing`, **off by default**. It becomes mandatory above the
prevailing turnover threshold. **Check current CBIC guidance before go-live** rather than
assuming the threshold from this code.

## The audit trail

Nothing in the framework names a technology, but every part of it assumes someone can be
asked afterwards *who did that, and why*. **Platform Audit Entry** is the answer to that
question. It records every refund, every manual payment override, every gateway credential
change, every reconciliation and every ledger posting, with the actor, the roles they held
at the time, the source IP, and — for anything a person decided rather than a system
computed — the reason in their own words.

Three properties make it worth relying on:

* **It cannot be written to.** No role has create, write or delete permission, and the
  controller refuses an update or a delete regardless. Entries are inserted only through
  `api/audit.py`.
* **Alteration is detectable.** Each entry hashes its own content together with the hash of
  the entry before it. A row changed directly in the database no longer matches, and a
  nightly job re-hashes the whole chain and raises an Error Log when it does not.
* **It holds no secrets.** A credential change records that the value moved and by whom.
  The value itself, old or new, is never stored — not truncated, not masked, not at all.

One deliberate limit, stated plainly because the opposite would be a false claim: the chain
does not make the trail unforgeable. Somebody with database access could rewrite an entry
and every hash after it. What the chain does is turn silent tampering into work that leaves
traces, and give an auditor a check they can run themselves.

Writing an entry can never block the action it describes. If the trail fails, the refund
still completes and the failure is logged. An audit mechanism that can stop payments is one
that gets switched off during the first incident.

## Pre-go-live checklist

- [ ] **The client's CA confirms the GST treatment in writing** — the rate, the place-of-
      supply rule, and the HSN/SAC. Record who confirmed it and when.
- [ ] **Verify the current RBI no-AFA threshold** against `afa_free_debit_ceiling`.
- [ ] **A lawyer reviews the refund and cancellation policy** at `/legal/refund-policy` and
      the terms, then records the review on the Platform Legal Page so the draft banner
      clears.
- [ ] Confirm `pre_debit_notice_hours` is at least 24 and that the notice template carries
      every required element.
- [ ] Confirm `send_post_debit_confirmation` is on.
- [ ] Check the e-invoicing turnover threshold against the client's actual turnover.
- [ ] Set `company_gstin` and `company_state_code` correctly — the tax split is wrong for
      every customer if the supplier state is wrong.
- [ ] Switch `gateway_mode` from **Mock** to **Live** and configure the credentials. Mock
      mode takes no money; leaving a production site in it means collecting nothing.
- [ ] Run one real ₹1 transaction end to end and reconcile it.
- [ ] Run **Verify the Chain** on Platform Audit Entry and confirm it reports intact.
- [ ] Confirm gateway credentials are held by Platform Admin alone, and that a Platform
      Billing Manager cannot read them.

## What is deliberately not automated

- **Suspension after dunning.** Phase 5 stops at Past Due and hands to Phase 7. Cutting a
  customer off is a policy decision, not a billing one.
- **De-provisioning after a refund.** The contract is declared
  (`on_initial_payment_refunded`) and Phase 6 implements it. Until then a refund logs
  loudly that a tenant is provisioned and unpaid.
- **Writing off an unrecoverable receivable.** A person decides that, never an ageing rule.
