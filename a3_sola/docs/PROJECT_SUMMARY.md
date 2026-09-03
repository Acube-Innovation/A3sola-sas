# A3 Sola — project summary

For the client's leadership. Not a sales document: this is the one you would want to
inherit.

---

## What was built

One Frappe application, `a3_sola`, doing two jobs:

**A solar EPC business application** — a Kerala rooftop-solar company's whole operation,
from a WhatsApp enquiry to the fifth year of an O&M contract. The nineteen-stage execution
chain with its evidence gates, eighteen generated statutory documents, subsidy eligibility
and claims, DCR serial traceability, milestone billing, project profitability, and a
five-year service obligation with SLAs and warranty.

**A SaaS platform that sells it** — public marketing site, self-service signup, Razorpay
payments with RBI e-mandate handling, fully automated tenant provisioning, and an automated
subscription lifecycle that decides daily who still has access.

Delivered across eight phases. **972 tests across 53 modules, all passing in 54 minutes. 127 doctypes, four modules, one app.**

## Architecture in one page

```
                     ┌──────────────── one Frappe site ────────────────┐
   public visitor ──▶│  www/a3sola/   marketing, pricing, signup       │
                     │       │                                          │
                     │       ▼                                          │
                     │  Platform module                                 │
                     │    signup → Razorpay → provisioning → lifecycle  │
                     │       │                                          │
                     │       ▼ creates                                  │
                     │  Tenant = one ERPNext Company                    │
                     │       │                                          │
                     │       ├── Solar CRM        enquiry → proposal    │
   tenant user ─────▶│       ├── Solar Operations order → commissioning │
                     │       └── Solar Projects   costing → O&M         │
                     └──────────────────────────────────────────────────┘

  Isolation = one User Permission per user + permission-query hooks.
  Everything cross-cutting walks the module registries, so a doctype added
  later is automatically isolated, attacked, audited and monitored.
```

Detail in `ARCHITECTURE.md`.

---

## What is production-ready

| Area | Evidence |
|---|---|
| **Tenant isolation** | 5,871 adversarial attempts across 34 vectors and 254 doctypes/endpoints, **0 successful**. A negative control proves the suite detects a real breach (66 leaks when the boundary is removed) |
| **Application security** | 0 Blockers, 0 High. 3 Medium found and fixed. Secret scan, card/PII scan and password-encryption scan all clean. 133 endpoints inventoried; a guard test fails the build if a new unauthenticated one appears |
| **Permissions** | 127 doctypes × 29 roles, 5 rules asserted, 0 violations |
| **Payments** | Idempotent by construction. 8 simultaneous renewals produce **exactly one** order, under real concurrency |
| **Provisioning** | 8 simultaneous triggers, **exactly one** proceeds. Isolation verified before a tenant is handed over |
| **Subscription lifecycle** | Ships inert. 405 subscriptions evaluated, every decision logged, **zero access changes** |
| **Reversibility** | Suspend/restore round trip byte-identical, including a user the customer had disabled themselves |
| **Disaster recovery** | Restore performed and verified. **91 s measured RTO** |
| **Performance** | Every figure measured. Six N+1 patterns fixed — the worst went from 563 queries to 10 |
| **Monitoring** | 30 jobs heartbeat automatically; the watchdog alerts on **absence** |

## What is deliberately switched off, and why

| Switch | State | Why | Opens when |
|---|---|---|---|
| Accounting postings | **OFF** | A wrong posting at scale is far harder to unwind than a delayed one | The CA confirms the GST treatment **in writing** |
| Payment postings | **OFF** | As above | The same |
| GST valuation rule | **inactive** | Solar EPC is a composite supply and the sources disagree. The app refuses to guess | The CA answers |
| Automatic suspension | **OFF** | It can block a paying customer with nobody watching | The pre-flight passes and a full cycle of simulated decisions has been read |
| Lifecycle dry run | **ON** | The engine decides and logs, and changes nothing | As above |
| Public signup | **closed** | | Stage 3 |
| Provisioning | **Automatic** — set to Manual for pilot | A person should watch the first ones | The failure rate justifies it |

**Everything is still recorded while these are off.** You can run every report and reconcile
every figure before a single journal entry exists.

---

## Known limitations and deferrals

### Not built, by decision

- **Multi-site tenancy.** Multi-company on one site. `TENANCY_MODEL.md` states what would
  force a migration and what it would cost.
- **KSEB / national portal integration.** No scraping, no unofficial API. Documents are
  generated for a human to submit.
- **A customer mobile app.** The portal is responsive; there is no native app.
- **Automated cash refunds.** Every refund routes through an approval.

### Not tested, and stated as such

- **A 50-tenant scale dataset.** Figures are at 8,084 records with a stated linear
  projection. The measurement harness is the deliverable; re-run it against staging.
- **A sustained load test.** The two specific concurrency hazards *were* tested under real
  threads; throughput was not.
- **S1 end to end with live payments.** Every segment is proven; the continuous journey
  needs live Razorpay credentials. **Do this in Stage 0.**
- **A twelve-month O&M simulation.** Components covered; the year has not been run.
- **`SIGKILL` mid-transaction**, disk exhaustion, and a real hour-long gateway outage.
- **A fresh site built from `DEPLOYMENT.md` alone by somebody else.** The document records
  the five non-obvious steps found while building this one.

### Open risks

| Risk | Severity | Mitigation |
|---|---|---|
| **Encrypted secrets are lost on restore unless the key is carried across** | **High** | Procedure documented and proven. **Automate it** — it is a manual step today and the failure is silent |
| Backups are database-only and not off-site | **High** | Configure `--with-files` and an off-site destination before any real customer |
| GST treatment unconfirmed | **High** commercially | Postings stay off. The app enforces this |
| RBI AFA ceiling assumed at ₹15,000 | Medium | Verify against the current framework. It is a setting, not a constant |
| Alerts go to email only | Medium | Route to a channel somebody reads |
| No external uptime check | Medium | Point one at the health endpoint |
| Starter dataset ships a known password | Medium | Change it or run the teardown on first deploy |
| Error Log had no retention (165 MB, half the database) | Low | Fixed — daily purge at 30 days |
| Dependency advisories in bench/framework tooling | Low | Reported; none reachable from a request. The vendor's to fix |

### Assumptions that must be verified before go-live

1. **GST treatment** for the solar EPC composite supply — *the CA, in writing*
2. **GST treatment** for the SaaS subscription — *the CA*
3. **KSEB tariff slabs** — check against a recent real bill; every savings figure depends on them
4. **Subsidy scheme slabs and caps** — verify against the current PM Surya Ghar notification
5. **RBI AFA ceiling** — ₹15,000 assumed
6. **Statutory fee schedule** — application, registration, net meter charges
7. **Legal text** — terms, privacy, refund and cancellation policy, *reviewed by a lawyer*
8. **Every generated document**, checked line by line against current paperwork

**Number 8 is the largest open item.** A form that is subtly wrong is rejected at a counter
weeks later, and that is precisely the failure this product exists to prevent. It needs the
client's own paperwork and their own people; it cannot be done from here.

---

## Recommended next steps

**Before go-live** — in order:

1. The CA's GST confirmation, in writing, for both treatments
2. The document check, line by line, by the client's own team
3. Backups: `--with-files`, off-site, **and the encryption key stored with them**
4. Account mappings, with the client's accountant
5. Alerts routed to a channel somebody reads, plus an external uptime check
6. Live Razorpay keys and a verified webhook
7. Legal pages reviewed
8. Then Stage 0 — `ops/GO_LIVE.md`

**First 90 days after launch:**

- Automate carrying the encryption key into a restore. It is the one High risk with a
  manual mitigation
- Re-run the performance harness against real data and revisit indexing then
- Run the load test the scale dataset was meant to support
- A quarterly restore rehearsal, recording the RTO each time

**Roadmap, in the order it will pay:**

1. **Move private files to object storage.** Disk is the first ceiling and it is documents,
   not rows
2. **A mobile-first site visit flow.** Surveyors and technicians are the heaviest users and
   they are outdoors
3. **WhatsApp Business API.** The outreach cadence is built; the channel is manual
4. **Customer self-service portal depth** — track your own installation, download your own
   documents. Every ticket avoided is margin
5. **Tenant-level analytics.** The data is there; the reports are Acube's, not the tenants'

---

## An honest closing statement

**What we are confident about.** Isolation, and we can show you 5,871 attempts. Money
handling, because it is idempotent by construction and tested under real concurrency.
Reversibility, because a suspension round trip is byte-identical. That nothing switches
itself on: the dangerous behaviours ship off and are gated behind checks that refuse.

**What we are not confident about, and you should not be either.** Behaviour at fifty times
this data volume — the harness is there and the measurement is not. Anything requiring
someone's professional sign-off: the GST treatment, the legal text, the accuracy of every
generated form against a counter clerk's expectations. And the first real customer, because
no amount of testing substitutes for one.

**The largest single risk is not technical.** It is that the app goes live with a GST
treatment nobody has confirmed, or a statutory form that is subtly wrong. Both are gated,
deliberately and inconveniently, and **the gates should not be lifted to hit a date.**
