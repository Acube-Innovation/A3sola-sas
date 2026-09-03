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
| Platform | Razorpay payments, e-mandates, invoicing, dunning, reconciliation | Phase 5 |
| Platform | Tenant provisioning: registry, blueprints, orchestrator, isolation verification | Phase 6 |
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

### Payments

Phase 5 collects money. It is the part of the app where a bug costs a customer rather than
an afternoon, so a few principles are load-bearing and are worth stating before the map.

**The webhook is the truth.** A checkout callback tells us what the customer's browser
claims happened; a webhook tells us what the gateway says happened. Both are verified by
signature, both are accepted, and both converge on the same state — but the webhook is the
one that arrives even when the browser is closed, the laptop is shut, or the network drops
between the payment and the redirect. Every handler is idempotent because at-least-once
delivery guarantees duplicates in production, and the webhook endpoint stores and commits
the raw event *before* processing it, so an event is never lost to a handler crash.

**Charge the snapshot, never a fresh calculation.** A Subscription Signup stores what the
applicant was shown. `payments.py` contains no price calculation at all — if marketing
changes a plan between signup and payment, the customer pays what they agreed to.

**Amounts are integers at the boundary.** `tax.to_paise()` converts through `Decimal`, and
nothing sends a float to a gateway.

**Nothing about a card is ever stored.** The checkout page has no card fields; payment
happens in the gateway's hosted flow. `razorpay_client.redact()` strips card numbers,
contacts, tokens and secrets from every payload before it reaches storage or a log, and
`test_payment_security` re-reads all stored blobs with a Luhn check to prove it.

**Collection routing is a compliance decision, not a preference.** See below.

| Module | What it owns |
|---|---|
| `api/payments.py` | Order creation from a snapshot, checkout verification, applying a payment, mandate registration, the mock completion endpoint |
| `api/webhooks.py` | Signature verification, replay defence, the handler registry, order-level locking, retry |
| `api/billing_engine.py` | The daily recurring collection — five idempotent passes |
| `api/dunning.py` | Retry policy, transient/permanent error classification, escalation |
| `api/tax.py` | Subscription GST, GSTIN validation, place of supply, rupee/paise conversion |
| `api/accounting_payments.py` | Ledger postings, all gated and all reversible |
| `api/billing_portal.py` | What a subscribed customer may see and do about their own billing |
| `api/reconciliation.py` | Settlement import, matching, unmatched alerting, gateway health |
| `api/admin_actions.py` | The recovery actions an operator presses when a payment goes wrong |
| `api/audit.py` | The permanent record of every consequential money action |
| `api/gateways/razorpay_client.py` | The HTTP wrapper, the mock, and redaction |

**The RBI e-mandate rules, and how they land in code.** Under the Digital Payments
E-mandate Framework an automatic debit above a ceiling (₹15,000 by default, configurable)
needs Additional Factor of Authentication from the customer at each debit, which no
unattended job can supply. So `payments.classify_collection()` routes on the amount:

| Amount and cycle | Route | Why |
|---|---|---|
| Monthly, at or under the ceiling | **Auto Debit** | Within the no-AFA allowance |
| Monthly, above the ceiling | **Payment Link** | AFA is needed, so a human must be present |
| Annual, any amount | **Assisted Renewal** | An annual figure is over the ceiling in every realistic case |

Two details in that logic caused real bugs and are now fixed and tested. The ceiling is
measured on the **tax-inclusive** amount, because that is what the bank debits — a
₹13,600 subtotal is a ₹16,048 debit and does not qualify. And the recurring route is
decided on the **recurring** amount, with the one-off implementation fee excluded: letting
a fee the customer will never pay twice push them into assisted renewal for five years
would be wrong.

Two more framework obligations are enforced rather than documented: a pre-debit notice at
least 24 hours ahead (`_notice_blocker()` hard-blocks the debit if it is missing or late,
and the settings field refuses a value under 24), a post-debit confirmation after every
collection, and customer-initiated cancellation at any time from `/billing`.

**Recovery actions.** When a payment goes wrong the alternative to deliberate actions is
somebody editing rows, so `api/admin_actions.py` provides the buttons, each role-guarded
and each audited:

| Action | Where | Guard |
|---|---|---|
| Fetch status from the gateway | Payment Order | Offered first — settles a disagreement with evidence. Never reverses a payment we already hold |
| Mark paid by hand | Payment Order | Platform Admin only; needs a reason and an external reference; refuses while a gateway order exists |
| Reissue payment link | Payment Order | The old link is left live so a customer mid-payment is not interrupted |
| Reprocess a webhook | Payment Webhook Log | Refuses any event that failed signature verification |
| Request a new mandate | Platform Subscription | Cancels the old one and drops to assisted renewal until the customer re-authorises |
| Cancel a mandate for a customer | Platform Subscription | Requires a reason in the operator's own words |
| Re-match a settlement range | Settlement Reconciliation | Matching is pure, so re-running only improves the picture |

**The audit trail.** Every refund, manual override, credential change, reconciliation and
ledger posting writes a **Platform Audit Entry**. Entries cannot be edited or deleted by
any role including Administrator, and each carries a SHA-256 over its own content chained
to the entry before it — so a row altered directly in the database breaks the chain and is
found by the daily check or the "Verify the Chain" button. A credential change records
*that* it changed and by whom, never the value. Writing the trail can never block the
action it describes: if the trail fails, the refund still goes through and the failure is
logged loudly.

**The mock gateway.** Set `gateway_mode` to `Mock` in A3 Sola Settings and the whole funnel
— checkout, capture, mandate registration, invoicing — runs end to end with no Razorpay
account. `get_client()` is the only way to obtain a client and returns the mock under tests
and in Mock mode, so no test can reach the live API and no demo can charge a real card. The
simulated-payment endpoint behaves as though it does not exist on a Live site.

**A trap worth knowing about.** Frappe commits only on POST, PUT and DELETE. The emailed
verification link is a GET, so any endpoint that writes during a GET must set
`frappe.flags.commit = True` or its work is rolled back at the end of the request.
`test_routes.py` guards this.

### Provisioning

Phase 6 turns a confirmed first payment into a working workspace, with no human involved.
It is the most dangerous code in the product, because it runs privileged operations —
creating a Company, creating Users, assigning Roles — triggered by an inbound webhook. Four
properties shape every decision in it.

**Exactly once.** Webhook delivery is at-least-once, so `trigger_provisioning` will be
called again. The idempotency key is derived from the **subscription**, not the event, so
every repeat finds the same Provisioning Job. Concurrent calls serialise on a redis lock;
the loser returns the in-flight job rather than proceeding in parallel.

**Ordering by reversibility, not fake atomicity.** ERPNext cannot cleanly delete a Company
that has transactions, and creating a User mutates auth state, so a blanket "roll back on
failure" is a lie that corrupts data. Instead there is a line:

| | Steps | On failure |
|---|---|---|
| Before the line | 01 validate · 02 reserve identifier · 03 create tenant · 04 resolve blueprint · 05 create company · 06 create structures · 07 seed masters · 08 apply entitlements | Roll back in reverse, leave the system as it was |
| **Point of no return** | **09 create admin user** | — |
| After the line | 10 assign permissions · 11 create invitations · 12 verify isolation · 13 send welcome · 14 activate | Stop, record what exists, tell a human. **Never** a destructive cleanup |

A half-built tenant somebody is told about is far safer than an automated cleanup that
deletes the wrong company.

**No privilege escalation from input.** The applicant supplies an organisation name and an
email. Nothing they type reaches a role, a permission, an account name or a naming series.
The tenant code is *derived* by an allowlist — lowercase letters, digits and hyphens — and
everything structural is built from the derived code rather than the original string.
Entitlements come from the Subscription Plan and nowhere else.

**Isolation verified, not assumed.** See below.

**Adding a step** is one class and one entry in `steps.ORDER` — never an edit to a long
function, because a long function is how the ordering quietly stops matching the ordering
somebody documented. A test asserts no reversible step ever runs after an irreversible one.

| Module | What it owns |
|---|---|
| `api/provisioning/orchestrator.py` | Locking, idempotency, resume, rollback, the watchdog |
| `api/provisioning/steps.py` | The fourteen steps and the order they run in |
| `api/provisioning/identifiers.py` | Deriving a safe tenant code and company abbreviation |
| `api/provisioning/blueprint.py` | Resolving a blueprint and substituting its tokens safely |
| `api/provisioning/strategies/` | Multi-company (implemented) and multi-site (not) |
| `api/entitlements.py` | Seat quota and module gating |
| `api/tenant_users.py` | Admin creation and the company User Permission |
| `api/invitations.py` | Seats offered, accepted, revoked |
| `api/isolation.py` | The gating proof that a tenant cannot see anyone else's data |
| `api/tenant_admin.py` | Export, termination, the refund path |
| `api/onboarding.py` | The welcome and the checklist provisioning deliberately did not guess |

### The entitlement snapshot

A Tenant's `user_quota`, `enabled_modules`, `max_companies` and `storage_limit_gb` are
copied from the plan **once**, at provisioning, and enforcement reads them and never the
live plan. If Starter becomes eight users next quarter, existing Starter tenants keep the
five they bought until somebody deliberately changes their plan and re-snapshots. Reading
the plan at enforcement time would let a marketing decision silently change what every
existing customer is entitled to, in both directions.

Seat enforcement is a **hard block** at the moment a user is created, invited or re-enabled
— not a nightly report, because a report tells you about the problem after the customer has
built their process around it. It never blocks the Administrator, a user with no tenant
stamp (your own staff), a *disable* operation, or the tenant's own admin account: a quota
bug that locks a tenant out of their own workspace turns a billing feature into an outage.

### Isolation verification

Step 12 is the one people skip. It runs as the newly created tenant admin, via
`frappe.set_user` with a guaranteed restore, and checks:

* every company-scoped doctype in all four modules, enumerated **from the registry** so a
  doctype added in a later phase is covered without anyone remembering;
* every report in the Solar modules;
* every Platform doctype holding your own business data — payments, signups, tenants,
  provisioning jobs, the audit trail, the settings singleton and its gateway credentials;
* link-field searches, and whether the tenant admin can elevate their own roles.

Failure sets the tenant to Provisioned with Errors, alerts, and **blocks activation**. A
monthly sweep re-runs it across every active tenant, because a regression introduced by a
later phase should be caught by us rather than by a customer.

Two things it does not do, both deliberate: it never uses `frappe.get_all` (which sets
`ignore_permissions=True` and would make every check pass on an instance with no isolation
at all), and it does not trust that the User Permission was created — it deletes-and-checks
in the test suite to prove the check can actually fail.

**It found two real leaks while Phase 6 was being built.** Thirty reports took a `company`
filter and trusted it, three of them building raw SQL from it — a tenant admin editing the
filter in a URL would have read a competitor's ledger. And master seeding checked existence
without a company, so the second tenant provisioned got no roof types at all while seeding
reported success. Both are fixed, and both have tests.

### The tenancy model

Multi Company: one Frappe site, one Company per tenant, isolation enforced by permission
hooks. The alternative — one site per tenant, isolation structural — is designed for behind
the same `TenancyStrategy` interface but not implemented; `MultiSiteStrategy` refuses
loudly and documents the privileged runner it would need. The setting refuses to change
once any tenant exists, and every tenant snapshots the strategy it was built under. See
[`docs/TENANCY_MODEL.md`](a3_sola/docs/TENANCY_MODEL.md) for the comparison, what would
trigger a migration, and what migrating would involve.

### Extension points, and where each one was filled

These are called at the right moments and each was left doing the minimum until the phase
that owned the decision arrived. **Phase 7 filled the last six.** The seams remain seams:
collection still refuses to decide what a failed payment costs a customer, and provisioning
still refuses to decide when a tenant is switched off — each hands over to the lifecycle
policy, which has the guards.

| Function | Called when | Implemented in | Hands over to |
|---|---|---|---|
| `signup.trigger_provisioning` | Initial payment captured | 6 | `api.provisioning.orchestrator` |
| `payment_refund.on_initial_payment_refunded` | The first payment is refunded | 6 | Tenant suspension; deletes nothing |
| `tenant.set_tenant_access_state(tenant, state, reason)` | Any access change after provisioning | **7** | `api.lifecycle.access` |
| `entitlements.add_seats(tenant, count)` | A customer buys seats mid-cycle | **7** | `api.lifecycle.seats` |
| `platform_subscription.on_billing_cycle_completed` | A cycle collects and the period rolls | **7** | `api.lifecycle.handlers` |
| `platform_subscription.on_payment_failed_final` | Dunning is spent and it is still unpaid | **7** | `api.lifecycle.handlers` |
| `platform_subscription.on_subscription_activated` | A subscription first reaches Active | **7** | `api.lifecycle.handlers` |
| `dunning.on_dunning_exhausted` | Every dunning step is spent | **7** | `api.lifecycle.handlers` |

### The subscription lifecycle

**The governing rule: suspension is never a side effect.** Every access change is a
deliberate, logged, individually reversible transition produced by a named policy, carrying
a reason a human can read. Nothing changes access as a consequence of doing something else,
and nothing changes access without writing a Subscription Event first.

#### The state machine

| State | Access | Billing | Enters from | Exits to |
|---|---|---|---|---|
| Trialing | Full | none | Draft, Pending Payment | Active, Pending Payment, Cancelled |
| Active | Full | charging | Trialing, Past Due, Grace, Suspended, Cancelled | Past Due, Cancelling, Cancelled |
| Past Due | **Full** | dunning | Active, Pending Payment, Grace | Active, Grace, Cancelling, Cancelled |
| Grace | Banner | dunning | Past Due | Active, Past Due, **Suspended**, Cancelling, Cancelled |
| Suspended | Blocked | halted | Grace only | Active, Cancelled |
| Cancelling | Full | final period | Active, Past Due, Grace | Active, Cancelled |
| Cancelled | Blocked | none | Cancelling, Suspended, Trialing, Active | Active (inside the window), Terminated |
| Terminated | Blocked | none | Cancelled | — |

Two absences are deliberate and are each covered by a test:

- **There is no Active → Suspended move.** A customer reaches Suspended through Past Due
  and Grace, having been warned at each, or not at all.
- **There is no Trialing → Suspended move.** A trial that never had a payment method is
  cancelled, not suspended. There is nothing to suspend them over.

And **Past Due leaves access Full**, on purpose. A failed debit is usually a bank problem
rather than a refusal to pay; restricting a customer's work over one loses the account.
Restriction starts at Grace, as a banner that does not obstruct anything.

#### Policy is data, not code

A client who wants 21 days of grace edits a Subscription Policy row. They do not commission
a change. Each stage names its day offset, the state it moves to, the access effect, whether
it needs approval and whether it notifies. See `docs/POLICY_GUIDE.md` for what moving each
number costs you.

#### The reversibility guarantee

Suspension disables access **without destroying state**. It never deletes a User, never
removes a Role or Role Profile, never deletes a User Permission and never touches tenant
business data. What it changes is `User.enabled`, and what each user was before is
snapshotted and committed *first*. Restoration puts every user back to its recorded prior
state — which is not "everybody enabled": somebody the customer had themselves disabled
stays disabled.

Restoration needs no approval, no scheduler and no queue. A tenant who pays at 11pm is
working at 11:01pm.

**A suspended tenant can always reach the billing portal and pay.** Locking a customer out
of the page that ends their suspension would be the worst bug in this area, so the gate's
allowlist covers billing, the payment endpoints, the webhook, password reset and login —
each with its own test.

#### The circuit breaker and the kill switch

Before applying any suspension the nightly run counts how many it would perform. Over
`max_suspensions_per_run` it **halts the entire pass, performs none of them, and alerts**.
A gateway outage or a date-arithmetic bug must never lock out the customer base, and a
halted run somebody investigates in the morning is always cheaper than mass suspension.

The kill switch halts every state change at once while leaving evaluation and logging
running — for use during an incident. See `docs/LIFECYCLE_RUNBOOK.md`.

#### It ships inert

`dry_run_mode` on, `enable_automatic_suspension` off. The engine evaluates every
subscription every night, writes down every decision, and changes nothing. Turning it on
is gated behind a pre-flight check that refuses until a default policy exists, notification
templates are present, the breaker limit is set, somebody holds the approval role, the
engine has run daily for a week and the simulation has been run — and then still requires
typing `SUSPEND CUSTOMERS`.

The policy, its five stage emails and the breaker limit all ship, so three of those six
pass on a fresh site. The two that cannot are the two that are evidence of a person
watching: somebody holding the approval role, and a week of daily runs behind you.

#### Proration

One function, `api/lifecycle/proration.py`, and deliberately no second one. Calendar days,
inclusive of both period ends; money rounded once, at the line. An upgrade charges the
difference immediately; a downgrade takes effect at the next boundary and refunds nothing.

Every plan and seat change recomputes **both** the mandate's registered maximum and the RBI
AFA ceiling, and acts on either being crossed. A change that silently breaks next month's
collection is the most damaging thing this area could ship.

#### Downgrades collide with usage, and that is handled honestly

A tenant on 12 users moving to a 5-seat plan has a problem the software cannot solve. It
does not try: the blockers are listed, the tenant chooses who to remove, and if they have
not by the boundary the downgrade **does not apply** and they stay on the higher plan for
another period. The correct failure mode is "you keep paying more", never "your data became
unreachable".

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

Provisioning adds three more. Decide `provisioning_mode` — **Manual Approval** is worth
using for the first few tenants, so a human sees what the pipeline builds before a customer
does. Leave `run_isolation_test_on_provision` on; switching it off needs a written
justification and the form enforces that. And on a site that will provision many tenants,
raise `throttle_user_limit` in the site config — Frappe blocks user creation past sixty a
minute site-wide, and a provisioning run that trips it leaves a tenant half-built for a
reason that has nothing to do with the tenant.

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
| `docs/COMPLIANCE_NOTES.md` | The RBI e-mandate framework, what it requires, and where each rule is enforced |
| `docs/PAYMENTS_RUNBOOK.md` | Running collections: failures, webhooks, reconciliation, recovery actions |
| `docs/TENANCY_MODEL.md` | Multi-company versus multi-site, why this choice, and what migrating would involve |
| `docs/PROVISIONING_RUNBOOK.md` | Every provisioning failure state, and the Sev-1 procedure for a suspected cross-tenant leak |
| `docs/LIFECYCLE_RUNBOOK.md` | The daily rhythm, handling a gateway outage without suspending anyone, answering "why was I suspended", the kill-switch procedure |
| `docs/POLICY_GUIDE.md` | Designing a subscription policy, and what each threshold costs you when it is too lax and when it is too aggressive |
| `docs/UAT_Phase1.md` … `UAT_Phase7.md` | Acceptance cases per phase |
| **`docs/UAT_MASTER.md`** | **All acceptance cases grouped by business process, the end-to-end scenarios and their results, and the client sign-off pack** |
| **`docs/ARCHITECTURE.md`** | **The definitive technical document. Read this first** |
| **`docs/PROJECT_SUMMARY.md`** | **For leadership: what was built, what is switched off and why, every risk that remains** |
| `docs/security/ISOLATION_AUDIT.md` | The adversarial suite, its vectors and the zero-success evidence |
| `docs/security/ENDPOINT_INVENTORY.md` | Every whitelisted method, generated from the code |
| `docs/security/PERMISSION_MATRIX.md` | Every doctype against every role, generated |
| `docs/security/FINDINGS.md` | Security findings, severity-ranked, with what was fixed |
| `docs/ops/PERFORMANCE_BASELINE.md` | Every measured figure, before and after each fix, plus sizing |
| `docs/ops/BACKUP_AND_DR.md` | The measured restore, RTO and RPO, and the drill outcomes |
| `docs/ops/MONITORING.md` | Every check, threshold, channel and expected frequency |
| `docs/ops/ON_CALL.md` | Severity, escalation, and a decision tree per incident |
| `docs/ops/ADMIN_CONSOLE.md` | The console, and who should use what |
| `docs/ops/DEPLOYMENT.md` | The reproducible build and the smoke test |
| `docs/ops/GO_LIVE.md` | The five stages, their rollbacks, and the launch checklist |
| `docs/training/*.md` | Role-based guides: tenant admin, sales, operations, finance, service, platform operator, FAQ |

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
# Five of everything, across all six phases - the usual way to fill a demo site
bench --site $SITE execute a3_sola.demo.generate_demo_data.run_sample

# The full hand-written set, if you want pagination and charts with a shape
bench --site $SITE execute a3_sola.demo.generate_demo_data.run

bench --site $SITE execute a3_sola.demo.generate_demo_data.teardown
```

`run_sample` caps every list at five: five leads, five consumers, five surveys, five
estimates, five proposals, five signups, five subscriptions with their orders, invoices and
mandates, five tenants with their provisioning jobs. Pass a different number to
`--kwargs '{"count": 20}'`.

Operations and Projects are not capped, deliberately. They do not build N of one thing —
they build a scenario: a job stuck at DISCOM feasibility past its SLA, a financed one
awaiting sanction, one waiting on a net meter, one with a breached service ticket, one
whose generation is sliding month on month. Capping that to a number would keep whichever
states happened to sort first and drop the rest, which is the opposite of useful. They
produce five to seven jobs regardless.

### Tests

```bash
bench --site $SITE run-tests --app a3_sola
```

The payment suites are worth knowing by name, because each exists to stop a specific
class of incident:

| Module | Proves |
|---|---|
| `tests/platform/test_payments_core` | Snapshot pricing, paise conversion, GST splits, collection routing, checkout verification |
| `tests/platform/test_webhooks_recurring` | Signature verification, replay defence, out-of-order events, mandates, the notice rule |
| `tests/platform/test_invoicing_dunning` | Tax invoices, gapless numbering, refund limits, dunning classification, portal isolation |
| `tests/platform/test_payment_security` | No secret and no card number in any stored blob, log or response; no guest permission anywhere in the payment domain |
| `tests/platform/test_audit_admin` | The audit trail is unwritable and tamper-evident; every recovery action is role-guarded |
| `tests/platform/test_provisioning_core` | Idempotency, concurrency, resume, rollback, step ordering, the entitlement snapshot |
| `tests/platform/test_provisioning_company` | The workspace a tenant gets, hostile names, and that no code path force-deletes a Company |
| `tests/platform/test_provisioning_users` | Admin creation with no password, the company User Permission, and the seat quota from both sides |
| `tests/platform/test_provisioning_isolation` | That the isolation checker can actually fail, and that every report is company-scoped |
| `tests/platform/test_routes` | Page controllers actually load, and GET endpoints that write actually commit |

**A trap the provisioning tests had to solve.** Provisioning commits after every step —
deliberately, so a crash mid-pipeline leaves an accurate record of where it stopped. The
consequence is that `FrappeTestCase`'s transaction rollback undoes **nothing** these tests
create: each one leaves a Company with a full chart of accounts and about a hundred seeded
masters behind, permanently. Left alone the suite poisons its own database — every later
test lists against tables thousands of rows deeper, and a run that took eight minutes took
eight hours. So `ProvisioningTestCase` tears its tenants down in `tearDownClass`, via
`tests/platform/provisioning_cleanup.py`, which refuses on any company that has acquired a
real transaction. If a dev site has already become slow, sweep it:

```bash
bench --site $SITE execute a3_sola.tests.platform.provisioning_cleanup.purge_all_test_residue
```

Any future test that provisions must go through `ProvisioningTestCase` and call
`self.remember(tenant)` for anything it builds outside the base helpers.

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
| Platform Admin | 4 | All of the above plus plans and settings | Subscription Plan, A3 Sola Settings, everything Marketing and Sales can | **Yes**, on Signup and Demo Request personal data, and the gateway credentials |
| Platform Billing Executive | 5 | Orders, transactions, invoices, subscriptions | Raise a refund request, chase a failed payment | **No — cannot approve a refund** |
| Platform Billing Manager | 5 | All payment records | Refund approval, reconciliation, mandate management, all recovery actions | **Yes** |
| Platform Provisioning Operator | 6 | Tenants, jobs, blueprints, invitations | Resume, retry and skip a provisioning step; re-run isolation | **No — cannot terminate a tenant** |
| Platform Tenant Manager | 6 | All of the above | Entitlement changes, roll back, export, termination with typed confirmation | **Yes** |

**Cross-module grants, and why each exists**

- *Solar Operations Manager* reads Phase 1 estimates and packages — a stage cannot be
  validated against a design it cannot see.
- *Solar Accounts Executive* reads Phase 2 statutory fee payments and subsidy claims —
  reimbursement and recovery are billed from them.
- *Solar Sales Manager* reads Phase 3 O&M contracts — the renewal pipeline is a sales
  conversation about a service history.
- *Platform Sales* reads Subscription Plan so it can quote correctly, and cannot edit it.
- *Platform Billing Manager* reads Subscription Plan and Signup — a billing question is
  usually a question about what was sold.
- Gateway credentials sit at permlevel 1 on A3 Sola Settings and are held by Platform
  Admin alone. A billing manager runs collections without ever seeing a key.
- **A3 Sola Settings itself is reachable by no customer role at all.** It is a site-wide
  singleton: one tenant editing it would change behaviour for every other tenant on the
  instance. The app reads it through helpers that bypass permissions, so nothing
  functional depends on a customer opening it, and the isolation test asserts they cannot.
  The one thing a tenant legitimately needs in there — their own ledger account mapping —
  has a scoped surface at `/account-mapping` that derives the company from the session and
  refuses any account outside it.
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
| Subscription Policy | Master |
| Policy Stage | Child |
| Subscription Event | Transaction (append-only) |
| Access Suspension | Transaction |
| Suspended User Snapshot | Child |
| Plan Change Request | Transaction |
| Proration Line | Child |
| Seat Change Request | Transaction |
| Cancellation Request | Transaction |

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
| Daily | Platform | `a3_sola.api.lifecycle.engine.run_lifecycle` | Evaluates every subscription against its policy. Ships inert — dry run on, automatic suspension off |
| Daily | Platform | `a3_sola.api.lifecycle.engine.alert_on_missing_heartbeat` | Alerts if the engine has not run for two days. The single most likely failure is silence, not a wrong decision |
| Daily | Platform | `a3_sola.api.lifecycle.suspension.remind_pending` | Reminds about suspensions awaiting a decision. Inaction never applies one |
| Daily (long) | Solar Projects | `a3_sola.api.billing.refresh_billing_summaries` | Rebuilds billing plan summaries from invoices and payments |
| Hourly | Platform | `a3_sola.api.reconciliation.gateway_health_check` | Alerts when the gateway stops answering or webhooks stop arriving |
| Daily | Platform | `a3_sola.api.billing_engine.run_daily_billing` | The five collection passes: notice, auto debit, assisted renewal, confirmation, close-out |
| Daily | Platform | `a3_sola.api.webhooks.retry_failed_webhooks` | Re-runs events whose handler failed |
| Daily | Platform | `a3_sola.api.dunning.run_dunning` | Advances each overdue subscription one step through its policy |
| Daily | Platform | `a3_sola.platform.doctype.payment_refund.payment_refund.detect_duplicate_payments` | Flags a customer charged twice for the same period |
| Daily | Platform | `a3_sola.api.reconciliation.alert_on_unreconciled` | Raises payments and settlement lines nobody has explained |
| Daily | Platform | `a3_sola.platform.doctype.platform_audit_entry.platform_audit_entry.alert_on_broken_audit_chain` | Re-hashes the audit trail and alerts if a row was altered outside the app |
| Daily | Platform | `a3_sola.api.provisioning.orchestrator.watchdog` | Marks a provisioning job stuck Running as Failed and alerts |
| Daily | Platform | `a3_sola.api.provisioning.orchestrator.alert_on_open_interventions` | Raises provisioning jobs that have been waiting on a human too long |
| Daily | Platform | `a3_sola.api.entitlements.recalculate_all_usage` | Corrects seat-count drift and reports any tenant over quota |
| Daily | Platform | `a3_sola.api.invitations.expire_stale_invitations` | Retires invitations past their date |
| Monthly | Platform | `a3_sola.api.accounting_payments.release_deferred_revenue` | Recognises the month's share of annual subscriptions collected up front |
| Monthly | Platform | `a3_sola.api.isolation.monthly_isolation_sweep` | Re-verifies isolation across every active tenant |

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

**Subscription money** is gated separately, on `enable_payment_postings`, so the platform
side can be switched on without touching project accounting:

- **An invoice is raised.** Debit Subscription Receivable, credit Subscription Revenue and
  the GST output accounts. An annual invoice credits Deferred Revenue instead, and a
  monthly job releases one twelfth at a time.
- **A payment lands.** Debit Gateway Clearing, credit Subscription Receivable. The money
  is not in the bank yet — it is with the gateway.
- **The gateway takes its fee.** Debit Payment Gateway Charges and its input GST, credit
  Gateway Clearing.
- **A settlement arrives.** Debit Bank, credit Gateway Clearing. When clearing does not
  come back to zero, the reconciliation says so rather than absorbing the difference.
- **A refund is processed.** The original entries are reversed, never edited.

Every account is resolved through Platform Payment Account Mapping, which refuses a
mapping that names another company's account.

Every entry carries the document that caused it, so reposting returns the existing entry
rather than duplicating it.

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app a3_sola
```

**Complete ERPNext's setup wizard first.** The app seeds its masters *against a company* —
tariffs, subsidy schemes, packages, fee schedules and the rest are all company-scoped — so
installing onto a site with no company leaves it seeded with nothing. A site that has not
been through the wizard is also missing the ERPNext defaults every accounting path needs.
If tests or postings fail on a fresh site, check these before looking at the app:

| Missing | Symptom |
|---|---|
| A Company | Every fixture lookup returns nothing; `IndexError` on `Company` |
| Fiscal Year covering today | `Date … is not in any active Fiscal Year` |
| A default Cost Center on the Company | `Cost Center is required for 'Profit and Loss' account` |
| Standard Selling / Standard Buying price lists | Quotation refuses to save: `selling_price_list` |
| Country fixtures (address templates, UOMs, groups) | `Could not find Address Template` on any address |

Seeding is idempotent, so after fixing the environment just run `bench --site $SITE
migrate` — the `after_migrate` hook re-seeds what is missing and leaves what is there.

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
