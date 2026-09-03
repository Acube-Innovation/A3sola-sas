# Designing a subscription policy

A policy decides when a customer who has not paid is warned, restricted and eventually
switched off. Every number in it is a row in a record — nobody needs a developer to change
one.

This guide is about what each number *costs you*, because the trade-off is real and it does
not have a right answer that applies to every client.

---

## The two failure modes

**Too lax.** A tenant runs for four months past non-payment. Nothing visibly breaks, no
alert fires, and it is found during a year-end review. This is the more common failure by a
wide margin, because nothing about it looks wrong from the inside.

**Too aggressive.** A tenant is locked out over a bank glitch on the morning they were
commissioning a customer's plant. You lose the account, and the referral, and they tell
people. This failure is rarer and much more expensive per occurrence.

The recommended policy leans away from aggression, deliberately. You can always suspend
somebody manually a week early. You cannot un-lock-out a customer on the morning that
mattered.

---

## The stages, and what each one costs

| Day | Stage | Access | What the customer sees | What it costs you to move it |
|-----|-------|--------|------------------------|------------------------------|
| 0 | `PASTDUE` | Full | An email saying the payment failed | Moving it later means a customer whose card expired is not told for days. There is no reason to move it later. |
| 7 | `GRACE` | Banner Only | A persistent banner with the amount and a pay-now link | Earlier feels aggressive for a bank problem. Later and the banner has no time to work before day 15. |
| 12 | `WARN` | Banner Only | The final warning, naming the exact date and time | This must be at least `notify_before_suspension_days` before suspension, or the suspension is refused outright. |
| 15 | `SUSPEND` | Blocked | Everyone signed out, an email explaining how to get back | The expensive one. Every day earlier converts a few more bank glitches into lockouts; every day later is another day of unpaid service. |
| 60 | `CANCEL` | Blocked | The subscription ends, the data export is generated | Earlier and you lose recoverable accounts. Later and your MRR figure is fiction. |

### Access effects, in the customer's terms

- **None** — they cannot tell anything has happened. Correct for Past Due: a failed debit
  is usually the bank, not a decision.
- **Banner Only** — a notice they cannot dismiss. It does not obstruct a single click.
  This is the setting that recovers most accounts, because it is seen by whoever is
  actually using the software rather than by whoever reads the billing mailbox.
- **Read Only** — they can open, search, report and print everything, and change nothing.
  Useful for a client who wants a middle step. Be aware it is confusing in a way a banner
  is not: a person mid-task hits a wall they did not expect.
- **Blocked** — signed out. Nothing is deleted, no role is removed, no permission is
  touched, and paying reverses it in seconds.

---

## Choosing your thresholds

**A client billing large annual contracts to established firms** can afford to be slower:
grace at 14, suspension at 30. The accounts are worth chasing by phone and the payment
methods fail for boring reasons.

**A client billing small monthly amounts to a long tail** needs to be quicker or the
unpaid tail grows without limit: grace at 5, suspension at 12. Keep the warning gap.

**Never set `min_days_active_before_suspension` below about 14.** A brand-new tenant whose
first payment fails is almost always a card-setup problem, and switching them off in their
first fortnight loses a customer you had already won.

**Keep `max_suspensions_per_run` low** — ten is generous for most books. It is not a
throughput limit, it is a bug detector. Ten customers deciding to stop paying on the same
night does not happen; a gateway outage does.

---

## Two policies, not one

The policy record takes an `applicable_plan` and an `applicable_cycle`, and the most
specific active policy wins. That is usually enough for the split that actually matters:

- **Annual customers** paid up front and are not in arrears in the same sense. Give them a
  longer grace and a much later suspension.
- **Monthly customers** on a small plan are where the tail accumulates.

---

## Before you switch it on

Automatic suspension ships **off**, and the pre-flight check refuses to turn it on until:

- a default policy exists and has stages
- every stage that notifies has a template
- the circuit-breaker limit is set
- somebody actually holds the approval role
- the engine has run daily for at least a week
- the simulation has been run

Run the simulation and **read every line**. It reports exactly what the engine would do,
writing nothing. If a customer appears in that list who should not, the policy is wrong,
and it is much cheaper to find that out on a screen than in their inbox.
