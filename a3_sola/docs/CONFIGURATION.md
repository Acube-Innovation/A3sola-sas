# Configuration before go-live

Everything a new tenant must set or verify. The app seeds working defaults so it is usable
on day one, but several of them are **indicative** and must be confirmed against a current
source before a customer sees them.

## 1. Statutory fees — the one to check first

Open **Statutory Fee Schedule → KSEB 2026-27**.

The figures printed on the client's existing proposal templates disagree with each other,
so the app implements the only rule their own arithmetic satisfies:

> Registration fee = ₹1,000 per kW + 18% GST. 80% of the **base** (ex-GST) is refunded
> after commissioning. Application fee = ₹1,000 + 18% GST.

| Capacity | Client template says | This rule computes |
|---|---|---|
| 3 kW | ₹3,540 charged, ₹2,400 refundable | ₹3,540 / ₹2,400 ✅ consistent |
| 5 kW | ₹8,288 charged | ₹5,900 — the template figure is not derivable from any rule |
| 8 kW | ₹8,288 charged | ₹9,440 |
| 10 kW | ₹11,800 charged, ₹4,000 refundable | ₹11,800 ✅ / ₹8,000 — the template's refund is wrong |
| Application fee | ₹1,000 on some templates, ₹1,180 on others | one base of ₹1,000, rendered net or gross |

**Confirm with the client**, then update the schedule:

- the registration fee per kW and its GST rate
- whether the refund is computed on the base or the gross amount
- the monthly rental for a net meter availed from the DISCOM (seeded as 0)
- the net meter allocation lead time (seeded as 21 days)

Nothing in the app prints a fee that did not come from this schedule.

## 2. Grid Regulation Rule

Open **Grid Regulation Rule → KSERC-3PH-ABOVE-3KW**.

Seeded as: plants above 3 kW must be three-phase, notified 06.11.2025, stayed by the High
Court until 22.05.2026.

**Check the current position of the stay.** While a stay is in force the rule does not fail
a single-phase quotation; once it lapses, it does. The sentence that prints on the proposal
comes from this record's *Customer Facing Clause*, so correcting the record corrects every
future proposal.

## 3. Electricity Tariff

Open **Electricity Tariff → KSEB Domestic Bimonthly**. The seeded telescopic slabs are
**indicative**. Verify every slab against the current KSERC tariff order before quoting
savings — savings are computed slab by slab, so a wrong slab is a wrong payback on every
proposal.

## 4. Subsidy Scheme

Open **Subsidy Scheme → PM Surya Ghar: Muft Bijli Yojana**. Verify the slabs
(1 kW ₹30,000, 2 kW ₹60,000, 3 kW and above ₹78,000 capped) and the 10 kW eligibility
ceiling against current MNRE guidelines.

## 5. Component Make — warranty terms

Warranty terms are **per make** and come from this master, seeded from the client's current
proposals:

| Make | Component | Product | Performance |
|---|---|---|---|
| Rayzon | Module | 15 years | 30 years |
| Vikram | Module | 12 years | 30 years |
| Renewsys | Module | 12 years | 30 years |
| Solinteg | Inverter (string) | 10 years | — |
| SolarEdge | Inverter (optimiser) | 8 years | — |
| Hoymiles | Microinverter | 12 years | — |

Confirm each against the supplier's current warranty certificate. Older proposals in the
client's set state a 25-year module performance warranty with floors of 90% at 10 years and
80% at 25; newer ones state 30 years. Both shapes are representable — record what the
supplier currently certifies.

## 6. Solar Package pricing

Ten packages are seeded with the client's own specification codes, component lists and both
inverter options. **Costs are left at zero** — their workbook holds the live pricing and it
is commercially sensitive. Populate `cost_option_1` and `cost_option_2` per package before
quoting.

## 7. Company — the three entity roles

Open **Company** and complete all three blocks. They are not the same entity:

- **Registered Portal Vendor** — the entity registered on the national portal and named on
  DISCOM and bank paperwork.
- **Executing EPC** — the entity that issues the proposal and signs it.
- **Payee Bank** — where the money lands, printed on every proposal and bank letter.

A partly filled block is rejected on save: a half-filled bank block on a covering letter is
a payment sent to nowhere. Where a tenant plays all three roles, use **Copy from Company**.

## 8. Proposal text and outreach

Open **A3 Sola Settings**:

- **Proposal tab** — covering letter, About Us, terms and conditions, delivery schedule,
  subsidy note, GST note, scope of work, offer validity. Every fixed sentence on the
  proposal comes from here.
- **Outreach** — the four cadence steps and their day offsets, the signature block, and the
  brand's website and social links. The seeded links are the client's own; a second tenant
  must replace them before sending anything.

## 9. Yield and area defaults

Seeded from the client's own proposals (250 sq ft for 3 kW, 350 for 5 kW, 800 for 10 kW;
12–15, 20–25 and 40–50 units a day):

- specific yield 1,500 kWh/kWp/year
- 80 sq ft per kW, overridable per roof type
- daily band 4.0–5.0 units per kWp, overridable per DISCOM Section

Adjust per district as real generation data arrives.

## 10. GST

The client's proposals quote a single all-inclusive figure and state no valuation basis.
Phase 1 only prints a configurable note. The actual treatment — 70:30 composite supply,
split-line or single-rate — is settled against a recorded CA confirmation, and ledger
postings are gated on it.

Installation seeds one **Solar GST Valuation Rule**, **inactive**, with the percentages
blank. It stays that way until a CA has answered the five questions in
[ACCOUNTING_TREATMENT.md](ACCOUNTING_TREATMENT.md). There is no rate constant anywhere in
the code, and a test fails the build if one appears.

## 11. Accounting postings

Both switches in **A3 Sola Settings → Projects** ship **off**, and both must be on before
anything reaches a ledger:

- `enable_accounting_postings` — the client has decided this app may post at all
- `gst_treatment_confirmed_by_ca` — a named CA has confirmed the valuation in writing

Before turning them on, fill in **Solar Company Account Mapping** for every company. A
posting whose account belongs to another company is refused, not posted quietly.

See [ACCOUNTING_TREATMENT.md](ACCOUNTING_TREATMENT.md) for what each posting does and why
the subsidy never appears on an invoice.

## 12. Billing milestone templates

Three are seeded from the client's own terms:

| Template | Applies to | Split |
|---|---|---|
| Standard 70:20:10 - Net Meter Purchased | Self funded, customer buys the meter | 70 / 20 / 10 |
| Standard 70:20:10 - Net Meter from DISCOM | Self funded, meter rented from the DISCOM | 70 / 20 / 10, last on completion documents |
| Financed (Jan Samarth) 70:30 | Financed | 70 on sanction / 30 on completion report |

Adjust the credit days and the trigger stage codes to match what the client actually
agrees. Every template must total 100% — a test enforces it.

## 13. Cost categories and the pass-through

Fifteen categories are seeded. **Statutory Fees** is flagged `is_pass_through`, so it is
reported separately and never enters cost or margin. Do not un-flag it: DISCOM fees are
reimbursed against receipts and booking them as cost understates margin on every job.

## 14. O&M provision and service levels

In **A3 Sola Settings → Projects**:

- `om_provision_percent` (default 2%) — provided at commissioning against the five-year
  obligation
- `travel_cost_per_km` (default 12) — leave it at zero and every site visit looks free
- `default_labour_cost_per_hour` — only a fallback; the crew member's own CTC is used first
- `underperformance_threshold_percent` (80) and `underperformance_consecutive_readings` (3)
  — the operational signal
- `contract_expiry_window_days` (90) — when a contract becomes a renewal opportunity

Response and resolution hours live on each **Solar OM Contract**, not globally, because
they are what that customer was actually promised. See
[OM_PLAYBOOK.md](OM_PLAYBOOK.md).

## 15. Payments — the gateway

In **A3 Sola Settings → Payments**:

- `payment_gateway` — Razorpay is the only implementation today
- `gateway_mode` — **Mock**, Test or Live. A fresh site ships in Mock: the whole funnel
  works, nothing is charged, and no account is needed. Live is refused until the
  credentials below are filled in, because a Live site without them fails at checkout,
  which is the worst possible moment to discover it.
- `razorpay_key_id`, `razorpay_key_secret`, `razorpay_webhook_secret` — permlevel 1,
  visible to **Platform Admin** alone. Changing any of them writes a Platform Audit Entry
  recording who and when, never the value.
- `razorpay_account_id` — for the settlement API
- `auto_capture_payments` — capture at authorisation rather than in a second step. Leave
  it on unless the client's risk process says otherwise.

The webhook endpoint is `/api/method/a3_sola.api.webhooks.receive`. Subscribe at least to
`payment.captured`, `payment.failed`, `payment.authorized`, `order.paid`,
`payment_link.paid`, `payment_link.expired`, and the four `token.*` events. Copy the
webhook secret Razorpay generates into `razorpay_webhook_secret` — an event signed with a
different secret is discarded, silently and correctly.

## 16. Payments — compliance windows

- `afa_free_debit_ceiling` (default 15000) — the RBI no-AFA ceiling. It decides whether a
  monthly subscription can auto-debit or must be collected through a link. Verify the
  current figure before go-live; see [COMPLIANCE_NOTES.md](COMPLIANCE_NOTES.md).
- `pre_debit_notice_hours` (default 24) — **the settings form refuses anything under 24**,
  and the billing engine refuses a debit whose notice was late or missing. This is not a
  preference.
- `send_post_debit_confirmation` — leave on. It is required, not courteous.
- `subscription_gst_rate` (18) and `company_state_code` — the tax split is wrong for every
  customer if the supplier state is wrong.
- `refund_approval_threshold` — refunds above it wait for a billing manager and cannot be
  submitted until approved.

## 17. Payments — accounting

`enable_payment_postings` gates every subscription posting, independently of the project
gate in section 11. With it shut, invoices and payments are recorded and reported but
nothing reaches a ledger, which is the right state until the accounts are mapped.

Map the accounts in **Platform Payment Account Mapping**, one row per company:
subscription receivable, subscription revenue, deferred revenue, gateway clearing, gateway
charges, and the GST output heads. A mapping that names another company's account is
refused at save.

## 18. The audit trail

Nothing to configure — it is on. Worth knowing: **Platform Audit Entry** records every
refund, manual override, credential change, reconciliation and posting, cannot be edited or
deleted by anyone, and is hash-chained so alteration in the database is detectable. Run
**Verify the Chain** from any entry, or read the nightly check's Error Log. See
[COMPLIANCE_NOTES.md](COMPLIANCE_NOTES.md).

## 19. Provisioning — the tenancy strategy

In **A3 Sola Settings → Provisioning**:

- `tenancy_strategy` — **Multi Company** or Multi Site. This is architecture, not a
  preference, and the form refuses to change it once any Tenant exists. Multi Site is
  designed for but not implemented; see [TENANCY_MODEL.md](TENANCY_MODEL.md).
- `reserved_tenant_codes` — codes a tenant may never take. `admin`, `api`, `www` and the
  rest are seeded; add anything else that would be confusing as a company abbreviation or,
  under multi-site, as a subdomain. A built-in list backs this up, because an emptied
  blocklist is the kind of mistake nobody notices until somebody registers `admin`.
- `tenant_series_prefix`, `provisioning_job_series_prefix`, `invitation_series_prefix` —
  naming, as everywhere else in this app.

## 20. Provisioning — what a new company gets

- `provisioning_default_country` (India), `provisioning_default_currency` (INR),
  `default_chart_of_accounts` (Standard), `default_fiscal_year_start` (04-01).
- `company_abbr_length` (4) — ERPNext appends this to every account, warehouse and cost
  centre it creates, so short and stable is right. It is derived from the tenant code, never
  from what the applicant typed.
- `create_default_warehouses` and `create_default_cost_centers` — leave both on. Without the
  warehouses, the Phase 2 material flow fails on the tenant's first work order; without a
  cost centre, every Profit and Loss posting fails at submit.

## 21. Provisioning — the admin and their team

- `admin_role_profile_fallback` — used when the plan names no role profile. Seeded to
  **Solar Tenant Administrator**.
- `provisioning_send_welcome_email` and `welcome_email_template` — the built-in template is
  used when none is named.
- `password_link_expiry_hours` (72) — no password is ever set by the system, for anyone. The
  admin gets a single-use reset link and sets their own.
- `force_password_reset`, `enable_two_factor_for_admins` — the second is off by default;
  turn it on for tenants who ask.
- `invitation_expiry_days` (14) and `max_pending_invitations_multiplier` (1.5) — the
  multiplier lets a tenant invite a little beyond their seat count to cover non-responders.
  The quota still binds at acceptance.
- `invite_rate_limit` (30/hour per admin) and `invite_accept_rate_limit` (20/hour per IP).

## 22. Provisioning — behaviour and the isolation gate

- `provisioning_mode` — **Automatic** or **Manual Approval**. Manual Approval queues the job
  and waits for a human, which is worth using for the first few tenants.
- `provisioning_queue` (long), `provisioning_timeout_minutes` (15),
  `max_provisioning_retries` (3), `notify_on_failure_role` (Platform Tenant Manager).
- `provisioning_failure_alert_age_hours` (24) — how long an intervention may sit before the
  daily job says so out loud.
- `run_isolation_test_on_provision` — **leave this on.** It is the last thing standing
  between a new tenant and another customer's data, and unchecking it demands a written
  justification that the form will not let you skip.
- `isolation_recheck_monthly` — re-verifies every active tenant. A regression introduced by
  a later phase should be found by us, not by a customer.

**Site config, not settings:** on an instance that will provision many tenants, raise
`throttle_user_limit` in `site_config.json`. Frappe blocks user creation past sixty a minute
across the whole site, and a provisioning run that trips it leaves a tenant half-built for a
reason unrelated to the tenant.
