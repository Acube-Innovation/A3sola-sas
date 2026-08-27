### A3 Sola

Solar EPC business application for ERPNext: Solar CRM, Solar Operations, Solar Projects and Platform

One app, four modules. Everything a module contributes — doctypes, doc events, permission
hooks, schedulers, fixtures — is declared in its own file under `a3_sola/registry/` and
merged into `hooks.py`, which stays thin. There is exactly one settings singleton,
**A3 Sola Settings**, with a tab per module.

| Module | What it covers | Status |
|---|---|---|
| Solar CRM | Leads, consumers, surveys, design estimates, eligibility, proposals, packages | Phase 1 |
| Solar Operations | The 19-stage execution chain, documents, serials, statutory fees, subsidy claims, loans, commissioning | Phase 2 |
| Solar Projects | Costing, milestone billing, GST, accounting, O&M contracts, visits, tickets, warranty, performance | Phase 3 |
| Platform | Public marketing site, pricing, signup funnel | Phase 4 |
| Platform | Razorpay payments and invoicing | Phase 5 |
| Platform | Tenant provisioning | Phase 6 |
| Platform | Subscription lifecycle | Phase 7 |
| — | Security, performance and go-live | Phase 8 |

### The public site

The marketing site, pricing and signup funnel are served by Frappe's website framework
from `a3_sola/www/`, with the design tokens in `a3_sola/public/css/platform.css`. There is
no separate frontend, no build step and no CDN dependency beyond one font stylesheet.

**Nothing on the site is written into a template.** Every feature, solution, statistic,
integration, plan price and FAQ answer comes from a record in the desk, so marketing can
change the site without a deploy. See
[`docs/CONTENT_GUIDE.md`](a3_sola/docs/CONTENT_GUIDE.md) for which doctype drives which
section.

| Route | What it is |
|---|---|
| `/` | Homepage — eleven sections, all data-driven |
| `/features`, `/features/<slug>` | Feature index and detail pages |
| `/solutions`, `/solutions/<slug>` | Solution index and detail pages |
| `/pricing` | Pricing with the comparison table and the FAQ |
| `/get-started` | Four-step signup, pre-selected from the pricing CTA |
| `/get-started/check-email` | Verification sent, with a rate-limited resend |
| `/verify-email` | Consumes the verification token |
| `/get-started/summary` | Order summary after verification |
| `/thank-you` | Where a demo request lands |
| `/legal/privacy`, `/legal/terms`, `/legal/refund-policy` | Editable legal text |
| `/solar` | The customer portal (Phase 3) — login required |
| `/robots.txt`, `/sitemap.xml` | Generated; signup routes excluded from both |

**Design tokens** are extracted from the reference product and defined once at the top of
`a3_sola/public/css/platform.css`. Change a token there and it changes everywhere.

### The Phase 5 contract

Phase 5 implements `a3_sola.api.signup.initiate_payment(signup_reference, token)`, which
today raises `NotImplementedError` with the contract in its docstring. Three things matter:

1. **Charge the snapshot.** A Subscription Signup stores `base_amount`,
   `additional_user_amount`, `implementation_fee`, `subtotal`, `tax_amount`,
   `total_amount` and `currency` as they were when the applicant signed up. Phase 5 must
   charge those fields and must **never** call `calculate_plan_total` again — marketing
   may have changed the price since, and the applicant agreed to what they were shown.
2. **Prove the caller.** Resolve the signup with `_authorised_signup(reference, token)`,
   the same summary-key check every other mutating endpoint uses.
3. **Own these transitions**, each through `doc.set_status(...)` so the event log is
   written: `Verified → Awaiting Payment`, then `→ Paid` (writing `razorpay_payment_id`
   and `payment_completed_on`) or `→ Payment Failed` with a reason.

Phase 4 owns everything up to `Verified`. Phase 6 provisions from the plan's entitlements
and writes back `provisioned_company`, `provisioned_site` and `admin_user`.

### Analytics events

Pushed to `dataLayer` when analytics is enabled: `pricing_toggle`, `plan_selected`,
`signup_started`, `signup_step_completed`, `signup_submitted`, `email_verified`,
`payment_initiated`, `demo_requested`. Payloads are documented in
[`docs/CONTENT_GUIDE.md`](a3_sola/docs/CONTENT_GUIDE.md).

### Platform records are not tenant records

Phase 4's doctypes — Platform Feature, Subscription Plan, Subscription Signup and the
rest — belong to the product, not to a customer. A Subscription Signup exists before any
tenant does. **They therefore carry no `company` field and are not registered for company
isolation**, and that is deliberate: binding public marketing content to a company filter
would render it to nobody.

They are isolated the way that matters for them instead: a guest can read published
marketing content and nothing else, enforced by a test that enumerates every doctype in
the app. A later phase must not "fix" this by adding a company field.

### Before go-live

Two things ship deliberately switched off and must be settled by the client, not guessed at
in code:

- **GST valuation.** There is no rate constant anywhere in this app. The seeded
  Solar GST Valuation Rule is inactive until a CA confirms the treatment.
- **Accounting postings.** Gated on both `enable_accounting_postings` and
  `gst_treatment_confirmed_by_ca`. With either shut, nothing reaches a ledger and
  operations carry on unaffected.

And one rule with no exception: **the subsidy never appears on an invoice** — not as an
item, a tax, a discount or a description. It is a government transfer to the customer,
never the company's revenue.

And the public surface has its own list: turn captcha on, have a lawyer review the three
legal pages, and run the guest permission audit. See
[`a3_sola/docs/SECURITY_NOTES.md`](a3_sola/docs/SECURITY_NOTES.md).

Read [`a3_sola/docs/ACCOUNTING_TREATMENT.md`](a3_sola/docs/ACCOUNTING_TREATMENT.md) and
[`a3_sola/docs/CONFIGURATION.md`](a3_sola/docs/CONFIGURATION.md) before enabling either.

### Documentation

| Document | What it covers |
|---|---|
| `docs/CONFIGURATION.md` | Everything to set before go-live |
| `docs/ACCOUNTING_TREATMENT.md` | GST, the subsidy rule, pass-through fees, the posting gates |
| `docs/OM_PLAYBOOK.md` | The five-year obligation, visits, SLAs, warranty, renewals |
| `docs/OPERATIONS_RUNBOOK.md` | Running the execution chain day to day |
| `docs/DOCUMENT_CATALOGUE.md` | The 18 generated documents and their sources |
| `docs/DOCUMENT_SOURCES.md` | Which client document each template reproduces |
| `docs/SECURITY_NOTES.md` | The public attack surface, rate limits, retention, go-live checklist |
| `docs/CONTENT_GUIDE.md` | Editing the marketing site without a developer |
| `docs/UAT_Phase1.md` … `UAT_Phase4.md` | Acceptance cases, and which test automates each |

### Customer portal

`/solar` — read-only, login required. A customer sees their own system, warranty end dates
by component and make, generation against both the design expectation and the daily band
their proposal quoted, their next visit, past service reports, their own documents and
their own invoices, and can raise a service ticket.

Ownership is re-derived from the session on every request and never read from a URL
parameter; document URLs are resolved per click rather than rendered into the page. Nothing
financial beyond their own invoices reaches it. `test_portal` attacks it the way a customer
would — by editing the id in the request.

### Demo data

One entry point builds the whole chain — leads through to a serviced, billed and maintained
book of delivered projects:

```bash
bench --site $SITE execute a3_sola.demo.generate_demo_data.run
bench --site $SITE execute a3_sola.demo.generate_demo_data.teardown
```

### Tests

```bash
bench --site $SITE run-tests --app a3_sola
```

### Role matrix

One app means one permission surface, so this is the whole of it. A role acquires nothing
by being defined in an earlier phase: a Solar Sales Executive from Phase 1 has no Phase 3
financial access, and it is this table that says so.

| Role | Phase | Reads | Writes | Level 1 (money) |
|---|---|---|---|---|
| Solar Sales Executive | 1 | CRM masters, own leads and consumers | Lead, Solar Consumer, Site Survey, Solar Design Estimate, Solar Proposal | **No** |
| Solar Sales Manager | 1 | All CRM | CRM, proposal approval, package pricing | **No** |
| Solar Survey Engineer | 1 | Consumers, surveys | Site Survey | **No** |
| Solar Design Engineer | 1 | Surveys, packages, estimates | Solar Design Estimate | **No** |
| Solar CRM Manager | 1 | All CRM | All CRM including masters and settings CRM tab | **No** |
| Solar Operations Executive | 2 | Installations, documents, stages | Solar Installation, work orders, documents, serials | **No** |
| Solar Site Engineer | 2 | Own work orders, snags | Installation Work Order, Installation Snag, Commissioning Report | **No** |
| Solar Documentation Officer | 2 | Document templates and packs | Generated documents, checklists | **No** |
| Solar Liaison Officer | 2 | Portal and DISCOM applications | Portal Application, Statutory Fee Payment | **No** |
| Solar Operations Manager | 2 | All Operations | Stage overrides, skips, blocks, Operations settings | **No** |
| Solar Service Technician | 3 | O&M Contract, non-financial only | Solar OM Visit, Generation Reading, ticket updates | **No — by design** |
| Solar Service Coordinator | 3 | All service documents; financials read-only | Service Ticket, visit scheduling, Solar Warranty Claim | **No** |
| Solar O&M Manager | 3 | All O&M | Contract cancellation, SLA overrides, provision review | **Yes** |
| Solar Project Manager | 3 | All Project and billing | Project, costing, Solar Billing Plan | **Yes** (cannot post journals) |
| Solar Accounts Executive | 3 | Operational documents read-only | Solar Billing Plan, invoicing, subsidy and warranty recovery | **Yes** |
| Accounts Manager | ERPNext | — | — | **Yes**, and the only role that may post |
| Platform Marketing Manager | 4 | Marketing content and FAQs | Platform Feature, Solution, Integration, Stat, FAQ, Legal Page | **No** |
| Platform Sales | 4 | Subscription Signup, Demo Request | Both, including status and assignment. Cannot edit plans | **No — cannot see an applicant's IP or token** |
| Platform Admin | 4 | All of the above plus plans and settings | Subscription Plan, A3 Sola Settings, everything Marketing and Sales can | **Yes**, on Signup and Demo Request personal data |

**Cross-module grants, and why each exists**

- *Solar Operations Manager* reads Phase 1 estimates and packages — a stage cannot be
  validated against a design it cannot see.
- *Solar Accounts Executive* reads Phase 2 statutory fee payments and subsidy claims —
  reimbursement and recovery are billed from them.
- *Solar Sales Manager* reads Phase 3 O&M contracts — the renewal pipeline is a sales
  conversation about a service history.
- *Platform Sales* reads Subscription Plan so it can quote correctly, and cannot edit it.
- Nothing else crosses. In particular no Phase 1 or Phase 2 role holds permlevel 1
  anywhere in Phase 3, and no Solar role holds anything at all in Platform: a Solar Sales
  Executive cannot read a Subscription Signup, and a Platform Sales user cannot read a
  Solar Installation.

**The permlevel rule.** Every Currency field in Solar Projects sits at permlevel 1, and
level 1 is granted only to the four financial roles above. A technician on a roof never
sees contract value, margin, provision or what a warranty claim was worth. `test_permissions`
enforces both halves: that no Currency field is left unguarded, and that no other role
holds the key.

Posting to the ledger is checked **again inside the posting functions themselves**, not
only through doctype permissions — see `_require_accounts_manager()` in
`a3_sola/api/accounting.py`.

### Doctype inventory

Naming series prefixes are configurable in **A3 Sola Settings**; the defaults are shown in
`docs/CONFIGURATION.md`. Child tables are listed separately because they carry no
permissions of their own.

**Solar CRM**

| Doctype | Kind |
|---|---|
| A3 Sola Settings | Single |
| Component Make | Master |
| DISCOM | Master |
| DISCOM Section | Master |
| Electricity Tariff | Master |
| Grid Regulation Rule | Master |
| Outreach Message Template | Master |
| Roof Type | Master |
| Site Survey | Submittable |
| Solar Consumer | Master |
| Solar Design Estimate | Submittable |
| Solar Package | Master |
| Solar Proposal | Submittable |
| Statutory Fee Schedule | Master |
| Subsidy Eligibility Check | Submittable |
| Subsidy Scheme | Master |

Child tables: Brand Link, Cashflow Projection, Design Estimate Option, EHS Checklist Item, Eligibility Rule Result, Net Meter Charge, Outreach Cadence Step, Outreach Log, Roof Segment, Scope Of Work Item, Shadow Observation, Solar Package Component, Subsidy Slab, Survey Image, Tariff Slab.

**Solar Operations**

| Doctype | Kind |
|---|---|
| Commissioning Report | Submittable |
| Document Checklist Template | Master |
| Document Template Set | Master |
| Installation Snag | Submittable |
| Installation Stage Template | Master |
| Installation Work Order | Submittable |
| Loan Application | Submittable |
| Net Metering Agreement | Submittable |
| Portal Application | Submittable |
| Solar Document Template | Master |
| Solar Installation | Submittable |
| Statutory Fee Payment | Submittable |
| Subsidy Claim | Submittable |

Child tables: Application Query, Document Checklist Template Item, Document Template Set Item, Generated Document Log, Installation Document, Installation Serial Register, Installation Stage Log, Installation Stage Template Detail, Inverter Protection Setting, Loan Disbursement, Test Reading, Wheeling Preference, Work Log, Work Order Crew.

**Solar Projects**

| Doctype | Kind |
|---|---|
| Billing Milestone Template | Master |
| Generation Reading | Submittable |
| Service Ticket | Submittable |
| Solar Billing Plan | Submittable |
| Solar GST Valuation Rule | Master |
| Solar OM Contract | Submittable |
| Solar OM Visit | Submittable |
| Solar Warranty Claim | Submittable |
| Statutory Fee Recovery | Submittable |

Child tables: Billing Milestone Entry, Billing Milestone Template Detail, Cost Category Config, Performance Log, Project Cost Entry, Solar Company Account Mapping, Solar OM Coverage Item, Solar OM Visit Plan, Visit Checklist Item, Visit Material.

**Platform**

| Doctype | Kind |
|---|---|
| Demo Request | Master |
| Platform FAQ | Master |
| Platform Feature | Master |
| Platform Integration | Master |
| Platform Legal Page | Master |
| Platform Solution | Master |
| Platform Stat | Master |
| Subscription Plan | Master |
| Subscription Signup | Submittable |

Child tables: Plan Feature, Plan Module, Platform Bullet, Platform Detail Section, Signup Event Log.

Platform doctypes carry no `company` field by design — see above.

### Schedulers

| Cadence | Module | Job | What it does |
|---|---|---|---|
| Hourly | Solar Projects | `a3_sola.api.sla.hourly_sla_scan` | Escalates service tickets breaching their resolution window |
| Daily | Platform | `a3_sola.api.funnel_jobs.chase_and_abandon_signups` | One reminder, then abandons unverified signups |
| Daily | Platform | `a3_sola.api.funnel_jobs.purge_personal_data` | Purges IP, user agent and spent tokens past retention |
| Weekly | Platform | `a3_sola.api.funnel_jobs.weekly_funnel_summary` | Emails sales the week's funnel |
| Daily | Solar CRM | `a3_sola.api.outreach.daily_followup_scan` | Raises lead follow-ups that have fallen due |
| Daily | Solar Operations | `a3_sola.api.escalation.daily_escalation` | Escalates installations stalled against their stage SLA |
| Daily | Solar Projects | `a3_sola.api.om.mark_due_and_missed_visits` | Marks preventive visits due, and missed once the date passes |
| Daily | Solar Projects | `a3_sola.api.om.detect_renewals` | Raises a renewal Opportunity for contracts nearing expiry |
| Daily (long) | Solar Projects | `a3_sola.api.costing.nightly_cost_refresh` | Rebuilds project costs from source documents |
| Daily (long) | Solar Projects | `a3_sola.api.billing.refresh_billing_summaries` | Rebuilds billing plan summaries from invoices and payments |

Every one iterates companies explicitly. None issues an unfiltered query.

### The accounting model, in plain English

Nothing below happens until **both** gates in A3 Sola Settings are open — see
`docs/ACCOUNTING_TREATMENT.md`.

- **The company fronts the subsidy gap.** Debit Subsidy Receivable, credit Subsidy Recovery
  Income. When the customer passes their DBT over: debit Bank, credit Subsidy Receivable.
  Where the customer claims directly the company funded nothing, so nothing is posted.
- **A statutory fee is paid on the customer's behalf.** Debit Statutory Fee Receivable,
  credit Bank. When the DISCOM refunds the registration fee: debit Bank, credit Statutory
  Refund Receivable. A fee the customer paid directly posts nothing.
- **The five-year obligation is provided for at commissioning.** Debit O&M Expense, credit
  O&M Provision. As visits consume it: debit O&M Provision, credit O&M Expense.
- **A milestone falls due.** A *draft* Sales Invoice is created and a human submits it.
  Nothing is auto-submitted, and no invoice may ever carry a subsidy line.
- **A funded subsidy gap is given up on.** Debit Write Off, credit Subsidy Receivable.
  Only ever on a person's instruction — there is no automatic ageing rule that writes off.

Every entry carries the document that caused it, so reposting returns the existing entry
rather than duplicating it.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app a3_sola
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/a3_sola
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
