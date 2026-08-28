# UAT — Phase 5 (Payments)

Each case traces to the prompt that specified it. Run against a site with demo data:
`bench --site <site> execute a3_sola.demo.generate_demo_data.run`

The site ships in **Mock** gateway mode, so the whole funnel including payment can be
walked without a Razorpay account. Cases marked **manual** need a human at the screen.

## Foundations and the snapshot (P5-A3S-001)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U5-01 | Create an order from a verified signup | Amounts copied from the signup snapshot | `test_payments_core` |
| U5-02 | Edit the plan price, then pay | The charge does not move | `test_payments_core` |
| U5-03 | Search `payments.py` for a price calculation | None — it charges the snapshot | `test_payments_core` |
| U5-04 | Double-click Pay | One order, one gateway order | `test_payments_core` |
| U5-05 | Derive the key for the same period twice | Identical; a different period differs | `test_payments_core` |
| U5-06 | Convert 3540.00, 70800.00, 13924.80 to paise | Exact integers, no drift | `test_payments_core` |
| U5-07 | Round-trip rupees → paise → rupees | Lossless | `test_payments_core` |
| U5-08 | Invoice a Kerala customer | CGST + SGST, halves adding back to the total | `test_payments_core` |
| U5-09 | Invoice a Karnataka customer | IGST | `test_payments_core` |
| U5-10 | Enter a GSTIN whose state contradicts the address | Refused, naming both | `test_payments_core` |
| U5-11 | Check the GST rate in code | Read from Settings; no constant | `test_payments_core` |
| U5-12 | Classify ₹7,080 monthly | Auto Debit | `test_payments_core` |
| U5-13 | Classify ₹70,800 monthly, and ₹15,001 | Payment Link both | `test_payments_core` |
| U5-14 | Classify any annual amount | Assisted Renewal, always | `test_payments_core` |
| U5-15 | Classify a recurring subtotal of ₹13,600 | Payment Link — GST takes it over the ceiling | `test_payments_core` |
| U5-16 | Check the one-off implementation fee | Excluded from the recurring route | `test_payments_core` |
| U5-17 | Change the ceiling setting | Classification follows it | `test_payments_core` |
| U5-18 | Verify a tampered checkout signature | Rejected | `test_payments_core` |
| U5-19 | Replay a checkout callback | Nothing changes; no second transaction | `test_payments_core` |
| U5-20 | Pay without the token, with a wrong token, or unverified | Refused each time | `test_payments_core` |
| U5-21 | Inspect the checkout response | No key secret, no verification token, no record | `test_payments_core` |
| U5-22 | Take the gateway offline mid-order | Clean failure; no half-state, no gateway id | `test_payments_core` |
| U5-23 | Check which client the tests use | The mock, always | `test_payments_core` |

## Webhooks (P5-A3S-002)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U5-24 | Post a webhook with a valid signature | Logged, verified, queued | `test_webhooks_recurring` |
| U5-25 | Post a tampered body | Rejected; the body is **not** stored | `test_webhooks_recurring` |
| U5-26 | Post with a wrong secret | Still returns 200 — no oracle | `test_webhooks_recurring` |
| U5-27 | Look for a way to disable verification | There is none | `test_webhooks_recurring` |
| U5-28 | Check the order of operations | Raw body read before parsing | `test_webhooks_recurring` |
| U5-29 | Replay an event id | Processed once | `test_webhooks_recurring` |
| U5-30 | Send captured before order.paid | Converges to Paid | `test_webhooks_recurring` |
| U5-31 | Send a failure after a success | Does not undo the success | `test_webhooks_recurring` |
| U5-32 | Send an event for an unknown order | Logged, not crashed | `test_webhooks_recurring` |
| U5-33 | Send an event we do not subscribe to | Recorded as Ignored | `test_webhooks_recurring` |
| U5-34 | Check the endpoint returns before processing | Work is enqueued | `test_webhooks_recurring` |
| U5-35 | Fire one event 50 times | One log, one transaction, one invoice | `test_payment_security` |
| U5-36 | Reprocess a failed log from the desk | Runs the handler again safely | **manual** |

## Mandates and recurring collection (P5-A3S-002)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U5-37 | Register a mandate for ₹3,540 | Maximum carries headroom (₹4,300) | `test_webhooks_recurring` |
| U5-38 | Register at ₹14,999 and ₹15,001 | AFA not needed, then needed | `test_webhooks_recurring` |
| U5-39 | Change the ceiling, reopen an old mandate | Its snapshot does not move | `test_webhooks_recurring` |
| U5-40 | Read the classification reason | Plain English, no field names | `test_webhooks_recurring` |
| U5-41 | Reject a mandate | Status Rejected, alert raised | `test_webhooks_recurring` |
| U5-42 | Create a ₹3,540 monthly subscription | Auto Debit | `test_webhooks_recurring` |
| U5-43 | Create any annual subscription | Assisted Renewal | `test_webhooks_recurring` |
| U5-44 | Create a ₹14,000 + GST monthly | Assisted Renewal — tax counts | `test_webhooks_recurring` |
| U5-45 | Sign up monthly and pay | A mandate is registered in the same interaction | `test_webhooks_recurring` |
| U5-46 | Sign up annually and pay | No mandate registered | `test_webhooks_recurring` |
| U5-47 | Cancel a mandate as the customer | Immediate; route switches to assisted | `test_webhooks_recurring` |
| U5-48 | Cancel with someone else's key | Refused | `test_webhooks_recurring` |
| U5-49 | Run the debit pass with no notice sent | **Refused and alerted** | `test_webhooks_recurring` |
| U5-50 | Send the notice 2 hours before | Still refused — 24 hours required | `test_webhooks_recurring` |
| U5-51 | Send it 25 hours before | Allowed | `test_webhooks_recurring` |
| U5-52 | Set the notice period below 24 hours | Refused at Settings | `test_payments_core` |
| U5-53 | Run the daily job twice | No double charge | `test_webhooks_recurring` |
| U5-54 | Collect successfully | Post-debit confirmation sent | **manual** |

## Invoicing, refunds and dunning (P5-A3S-003)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U5-55 | Invoice a Kerala and a Karnataka customer | Correct split each way | `test_invoicing_dunning` |
| U5-56 | Check the invoice lines | Built from the order's breakdown | `test_invoicing_dunning` |
| U5-57 | Submit with a contradictory GSTIN | Refused | `test_invoicing_dunning` |
| U5-58 | Raise three invoices | Sequential, gapless, fiscal-year numbered | `test_invoicing_dunning` |
| U5-59 | Delete a submitted invoice | Refused — cancel only | `test_invoicing_dunning` |
| U5-60 | Submit with postings off | Nothing reaches the ledger | `test_invoicing_dunning` |
| U5-61 | Map another company's account | Refused | `test_invoicing_dunning` |
| U5-62 | Check the posting functions | Role checked at function level | `test_invoicing_dunning` |
| U5-63 | Refund more than was collected | Refused | `test_invoicing_dunning` |
| U5-64 | Refund twice beyond the remainder | Refused | `test_invoicing_dunning` |
| U5-65 | Refund above the threshold | Waits for approval; cannot submit | `test_invoicing_dunning` |
| U5-66 | Refund below the threshold | Approved automatically | `test_invoicing_dunning` |
| U5-67 | Check the default dunning policy | Six steps at 0, 1, 3, 7, 10 days | `test_invoicing_dunning` |
| U5-68 | Classify insufficient_funds | Transient — retried | `test_invoicing_dunning` |
| U5-69 | Classify card_expired | Permanent — not retried; re-registration prompted | `test_invoicing_dunning` |
| U5-70 | Add a new gateway code to the policy | Classified without a deploy | `test_invoicing_dunning` |
| U5-71 | Open /billing as customer A | Only their own subscription | `test_invoicing_dunning` |
| U5-72 | Ask for customer B's invoices by name | Refused | `test_invoicing_dunning` |
| U5-73 | Cancel or pay B's subscription as A | Refused | `test_invoicing_dunning` |
| U5-74 | Inspect what the portal returns | No mandate id, no gateway id, no lifetime value | `test_invoicing_dunning` |

## Reconciliation, security and operations (P5-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U5-75 | Import a settlement CSV | Lines matched to transactions | **manual** |
| U5-76 | Include a line matching no payment | Flagged Unmatched and alerted | **manual** |
| U5-77 | Submit a reconciliation with unmatched lines | Refused | **manual** |
| U5-78 | Open Unreconciled Payments | Both directions, each explained | **manual** |
| U5-79 | Scan stored payloads for secrets | None found | `test_payment_security` |
| U5-80 | Scan stored payloads for card numbers | None found (Luhn-checked) | `test_payment_security` |
| U5-81 | Scan the Error Log for secrets | None found | `test_payment_security` |
| U5-82 | Check the checkout page for card fields | None — the gateway's hosted flow | `test_payment_security` |
| U5-83 | Check guest permissions on every payment doctype | None at all | `test_payment_security` |
| U5-84 | List a payment doctype as a guest | PermissionError | `test_payment_security` |
| U5-85 | Check the gateway credential fields | Password type, permlevel 1, Platform Admin only | `test_payment_security` |
| U5-86 | Check every public payment endpoint | All rate limited | `test_payment_security` |
| U5-87 | Check a Billing Executive can approve a refund | They cannot | `test_payment_security` |
| U5-88 | Run all sixteen Platform reports | All return columns | **manual** |
| U5-89 | Open AFA Exposure | Every subscription against the ceiling | **manual** |
| U5-90 | Open Mandate Health | The under-covered mandate is flagged first | **manual** |

## The mock gateway

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U5-91 | Open /checkout in Mock mode | Says plainly that nothing is charged | **manual** |
| U5-92 | Press "simulate a successful payment" | Order Paid, invoice raised, mandate created | `test_payments_core` |
| U5-93 | Press "simulate a declined payment" | Signup moves to Payment Failed | `test_payments_core` |
| U5-94 | Call the simulated endpoint on a Live site | Behaves as though it does not exist | `test_payments_core` |
| U5-95 | Call it with the wrong key | Refused | `test_payments_core` |
| U5-96 | Check it uses the real code path | Same apply/record functions as a live payment | `test_payments_core` |
| U5-97 | Switch to Live without credentials | Refused at Settings | `test_payments_core` |

## The GET-commit trap

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U5-98 | Open a verification link in a browser | The verification persists past the request | `test_routes` |
| U5-99 | Check the endpoint sets the commit flag | It does — Frappe commits only on POST/PUT/DELETE | `test_routes` |
