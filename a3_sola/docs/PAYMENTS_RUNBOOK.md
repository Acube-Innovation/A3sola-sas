# Payments runbook

What to do when money misbehaves. Every procedure here assumes you have Platform Billing
Manager or Platform Admin.

## The one principle

**The webhook is truth; the browser callback is a hint.** If the two disagree, the webhook
is right. Before concluding a payment did not happen, check **Payment Webhook Log** — the
customer may well have paid and the callback simply never came back.

---

## The recovery actions, and which to reach for

Every one of these is a button on the record itself, not a console command, and every one
writes a permanent audit entry. They are listed in the order you should consider them.

| Situation | Action | Where |
|---|---|---|
| Our status and the customer's disagree | **Fetch Status from Gateway** | Payment Order |
| A webhook's handler crashed | **Reprocess** | Payment Webhook Log |
| The customer never got the link, or it expired | **Reissue Payment Link** | Payment Order |
| A settlement arrived out of order | **Match Again** | Settlement Reconciliation |
| The card expired or the bank pulled the token | **Request New Mandate** | Platform Subscription |
| The customer rang up to cancel | **Cancel Mandate** | Platform Subscription |
| Money arrived outside the gateway entirely | **Mark Paid by Hand** | Payment Order |

**Always try Fetch Status first.** It settles the question with the gateway's own record
rather than anyone's judgement, and it resolves most disagreements on its own. It will
move an order from Pending to Paid. It will never move one out of Paid: if we hold a
payment the gateway does not, that is a discrepancy for a person to investigate against
the settlement report, and the action says so rather than quietly reversing anything.

**Mark Paid by Hand is the last resort, not the quick fix.** It asserts a payment that no
system has verified, so it needs Platform Admin, a bank reference or UTR, and a sentence
saying why — and it refuses to run at all while a gateway order exists, because in that
state Fetch Status is the correct action and this one is not. What you type goes on the
permanent record with your name against it.

---

## Reading the audit trail

**Platform Audit Entry** holds every refund, manual override, credential change,
reconciliation and ledger posting. Open any Payment Order and press **Audit Trail** to see
what has been done to that one record; open the doctype list to see everything.

Nothing on it can be edited or deleted, by any role, including Administrator. Each entry
also carries a hash of its own content chained to the entry before it, so a row changed
directly in the database breaks the chain. Press **Verify the Chain** on any entry to check
it; a scheduled job does the same every night and raises an Error Log if it finds a break.

**If the chain reports a break**, do not assume a bug. It means rows were changed outside
the application. Find out who has database access, when the change was made, and what the
row now says versus what the surrounding entries imply it should say. The break points at
the first altered row.

**A correcting entry, never an edit.** If something was recorded wrongly, the fix is to
perform the correcting action — which writes its own entry — not to change the original.
Both stay visible, and that is the point.

---

## A webhook failed to process

**Symptom:** a Payment Webhook Log row with status `Failed`, or a customer who paid whose
order still says Pending.

1. Open the log row. `error_traceback` holds what went wrong.
2. Fix the cause if it is a data problem — a missing plan, a deleted order.
3. Use the **Reprocess** action. It re-runs the handler; every handler is idempotent, so
   reprocessing something that partly succeeded is safe.
4. Failed logs are retried automatically each day up to five attempts, then alerted on.

**If the log does not exist at all**, the event never arrived. Check the gateway's webhook
configuration and the signature secret. The **gateway health check** runs hourly and alerts
when nothing has arrived in 24 hours — silence is the failure mode that goes unnoticed.

## Signature failures

A burst of `signature_verified = 0` rows means either a rotated secret nobody updated, or
somebody probing the endpoint.

1. Compare `razorpay_webhook_secret` in Settings against the gateway dashboard.
2. If they match, the traffic is not from the gateway. The endpoint already returns 200 and
   processes nothing, so nothing is at risk — but the source is worth blocking upstream.

**Never disable signature verification to "get things moving".** There is no setting for
it, deliberately.

## A settlement does not match

**Symptom:** Settlement Reconciliation with `unmatched_count` above zero, or the
Unreconciled Payments report showing rows.

Two directions, meaning different things:

- **Captured payment, no settlement line.** Usually just timing — gateways settle on a
  cycle. Beyond about five days, raise it with the gateway.
- **Settlement line, no payment.** More serious. Money moved that this system has no record
  of: a webhook that never arrived, or a payment taken outside the product. Trace the
  gateway payment id in the gateway dashboard before posting anything.

A reconciliation with unmatched lines **cannot be submitted**. That is deliberate.

## A mandate was rejected

**Symptom:** Payment Mandate status `Rejected`, and an alert.

Their next collection will fail. Act now, not at renewal:

1. Contact the customer — the rejection reason usually says why.
2. Send them to `/billing` to set up a new payment method.
3. Until they do, the subscription needs an assisted renewal; the route switches
   automatically when a mandate is cancelled, but a *rejected* one needs re-registration.

Run **Mandate Health** weekly. The "Covers Current Amount" column catches mandates whose
registered maximum has fallen below what is now being charged — a silent future failure.

## A customer disputes a charge

1. Open the Payment Order. **Payment Transaction** rows give the full attempt history,
   including the instrument's last four and the exact time.
2. The **Subscription Invoice** shows what they were billed and the tax split.
3. The signup's **event log** shows what they agreed to and when, including the price
   snapshot at the moment they signed up.
4. If a refund is due, raise a **Payment Refund**. Above the approval threshold it needs a
   billing manager; the approver and time are recorded.

## The customer was charged twice

The duplicate detector runs daily and logs any two paid orders sharing an idempotency key.
If a customer reports it first:

1. Find both Payment Orders by customer and date.
2. Raise a Payment Refund of type **Duplicate Payment** against the later one.
3. Refund the full amount. Do not net it against a future invoice unless they ask.

## The gateway is down

Symptoms: `GatewayNetworkError` in the error log, or the hourly health check failing.

- **Nothing is lost.** `initiate_payment` fails cleanly, the customer is told nothing has
  been charged, and no half-state is left — the order stays `Created` with no gateway id.
- The daily billing run skips what it cannot charge and retries next run; the idempotency
  key prevents any double charge when it recovers.
- If it is prolonged, tell customers whose renewal falls in the window before their service
  lapses.

## Rotating gateway keys

1. Generate the new keys in the gateway dashboard, keeping the old ones active.
2. Update `razorpay_key_id`, `razorpay_key_secret` and `razorpay_webhook_secret` in
   **A3 Sola Settings → Payments**.
3. Run the health check.
4. Take one real payment end to end.
5. Only then revoke the old keys.

**Never put a key in a config file, a commit, or a chat message.** They are Password fields
so they are encrypted at rest, and no code path logs or returns them.

## The RBI changes the AFA threshold

See `docs/COMPLIANCE_NOTES.md`. In short: change `afa_free_debit_ceiling`, run the **AFA
Exposure** report, and contact the customers whose route changes. Existing mandates keep
the ceiling they were registered under.

## A debit was blocked for want of notice

**Symptom:** `a3_sola: debit blocked, no notice` in the error log.

This is the compliance guard working. The engine refused to debit because the pre-debit
notice was not sent, or not sent early enough.

1. Check why the notification pass did not run — usually a mail failure.
2. Fix the mail problem. The notice goes out on the next run and the debit follows a day
   later.

**Do not work around it by debiting manually.** Debiting without the required notice is a
breach of the framework.

## Switching from Mock to Live

The site ships in **Mock** mode: a simulated gateway that takes no money and needs no
credentials, so the whole funnel can be walked before an account exists.

Mock mode is obvious on screen — the checkout page says so and offers "simulate success"
and "simulate failure" buttons. Before go-live:

1. Set `gateway_mode` to **Live** and fill in all three credentials. Live mode refuses to
   save without them.
2. Confirm the webhook URL and secret in the gateway dashboard.
3. Take one real transaction and reconcile it.

A production site left in Mock mode collects nothing while appearing to work.
