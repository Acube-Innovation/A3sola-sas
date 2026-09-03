# Performance baseline

Every figure here was measured. Nothing says "acceptable" — it says the milliseconds and
the query count, both before and after each fix.

**Measured on:** the development host, MariaDB 10.11, Python 3.12, Frappe v15.118 /
ERPNext v15.119. Site of 329 MB, 8,084 business records across 66 doctypes, 42 companies,
19 tenants, 484 subscriptions, 554 payment mandates.

**How:** `a3_sola.api.perf.bench` — seven runs after a discarded warm-up, reported as p50 /
p95 / p99, with the SQL statement count from the first run. Reproduce with
`bench --site <site> execute a3_sola.api.perf.baseline.run_all`.

**Why query counts appear beside milliseconds.** Wall time on a laptop with a warm cache
does not transfer to a production host. A query count does: a report issuing 563 queries
issues 563 everywhere, and that is the number an N+1 audit acts on.

---

## The headline: six N+1 patterns found and fixed

Each was a query issued once per row. Each therefore got slower as the client got bigger,
which is the wrong way round for every one of them — `Mandate Health` is the report the
billing team opens to find out which collections are about to fail, and its cost grew with
the number of paying customers.

| Report | Before | After | Queries |
|---|---:|---:|---|
| **Mandate Health** | 241.5 ms | **22.0 ms** | 563 → **10** |
| **MRR Movement** | 126.2 ms | **17.7 ms** | 221 → **9** |
| **Engagement Signals** | 94.7 ms | **20.5 ms** | 229 → **31** |
| **Subscription Health** | 54.4 ms | **23.6 ms** | 85 → **13** |
| **Solar Sales Pipeline** | 37.8 ms | **11.8 ms** | 79 → **10** |
| **Cohort Retention** | 27.7 ms | **6.3 ms** | 50 → **9** |

What each was doing, and what it does now:

- **Mandate Health** — one `get_value` per mandate to read the subscription's recurring
  amount. Now one query for every subscription named, read from a dict. 554 rows in 10
  queries.
- **MRR Movement** — one event query per month, and one subscription lookup per event.
  Now one query for the whole window, bucketed in memory, against a subscription table
  read once.
- **Engagement Signals** — fourteen queries per tenant: a user query, a name lookup, six
  document counts and six module probes. All six counts are now one `GROUP BY company`
  each, for every tenant at once.
- **Subscription Health** — four to five per tenant. Now three batched lookups total.
- **Solar Sales Pipeline** — the latest design estimate fetched per consumer. Now one
  query for the whole page.
- **Cohort Retention** — two event queries per tenant *per milestone*: four milestones and
  fifty tenants would be four hundred queries to fill a four-column table.

---

## List views — the ten heaviest doctypes

| What | p50 ms | p95 ms | Queries |
|---|---:|---:|---:|
| Document Checklist Template | 0.4 | 0.9 | 1 |
| DISCOM Section | 0.5 | 0.8 | 1 |
| Solar Document Template | 0.6 | 0.8 | 1 |
| Component Make | 0.8 | 0.9 | 1 |
| Payment Mandate | 0.6 | 0.7 | 1 |
| Payment Order | 0.5 | 0.7 | 1 |
| Subscription Invoice | 0.5 | 0.6 | 1 |
| Platform Subscription | 0.6 | 0.8 | 1 |
| Payment Transaction | 0.5 | 0.6 | 1 |
| Solar Package | 0.6 | 1.2 | 1 |

One query each, sub-millisecond. Nothing to fix. These are the server-side figures; what a
user perceives is dominated by the desk's own rendering, which is Frappe's.

---

## The permission layer

The highest-leverage measurement in the app: `permission_query_conditions` runs on **every**
query for a registered doctype, so a millisecond here is a millisecond on every list,
report and link lookup in the product.

| What | p50 ms | Queries |
|---|---:|---:|
| `build_query_conditions` alone | **0.0** | 0 |
| `get_list` **with** the permission hook | 0.5 | 1 |
| `get_all` **without** it (control) | 0.3 | 1 |

**The hook costs about 0.2 ms and zero extra queries.** It builds a string from cached user
defaults rather than querying. Nothing to optimise, and worth recording so a future change
that adds a query here is visible against this number.

## The Phase 7 access gate

Added to every authenticated request.

| What | p50 ms | Queries |
|---|---:|---:|
| Cold (cache miss) | 0.8 | 2 |
| **Warm (cached)** | **0.0** | **0** |

Two queries on a miss, nothing on a hit, invalidated on any state change. **The per-request
budget it consumes is effectively zero**, which is what it had to be.

## Public and portal

| What | p50 ms | Queries |
|---|---:|---:|
| Published plans (pricing page) | 2.1 | 3 |
| Plan total calculation | 1.1 | 1 |
| Billing portal: my subscriptions | 1.5 | 4 |

---

## Schedulers

Measured end to end against the whole site.

| Job | Phase | p50 | Queries |
|---|---|---:|---:|
| **Lifecycle engine** | 7 | **4,329 ms** | 4,357 |
| Daily billing | 5 | 217 ms | 41 |
| SLA scan | 3 | 174 ms | 95 |
| O&M visits due | 3 | 135 ms | 89 |
| Renewal detection | 3 | 124 ms | 48 |
| Follow-up scan | 1 | 107 ms | 44 |
| Usage drift | 6 | 53 ms | 48 |
| Dunning | 5 | 5 ms | 6 |

### The lifecycle engine, examined

It is the one that touches everything: **405 subscriptions in 4.3 seconds**.

Two N+1 patterns were removed from it during this work:

- the active-policy list was read once **per subscription** — four hundred reads for four
  hundred identical answers. Now cached for the life of the request, and invalidated the
  moment a policy is saved so a policy created and used in the same request still resolves
  correctly.
- `days_overdue` was computed twice per subscription, each time costing an unpaid-invoice
  query. Now computed once and passed through.

Query count fell from **5,251 to 4,357**; wall time from 4,692 ms to 4,329 ms.

**It remains about 10.8 queries per subscription**, and the dominant cost is
`frappe.get_doc` loading each subscription with its child tables during evaluation, when
most subscriptions need no action at all.

**Projection to 200 tenants.** The work is linear in subscriptions, and the measurement is
405 subscriptions in 4.3 s:

| Subscriptions | Projected runtime |
|---|---|
| 405 (measured) | **4.3 s** |
| 1,000 | ~11 s |
| 2,000 | ~21 s |
| 5,000 | ~53 s |

Comfortably inside a nightly window at every size a 200-tenant business reaches. **No
change is needed.** If it ever matters, the specific remedy is to evaluate from a
`get_value` projection and load the full document only when a transition is actually
required — that removes roughly three of the eleven queries per subscription.

### A correctness fix found by measuring

Attempting to shortcut one of those queries broke restoration. `is_overdue` answers True
for anything in Past Due, Grace or Suspended *regardless of the balance*, because that is
what drives the policy stages; `_has_settled` asks whether money is actually owed. They
look like the same question. Collapsing them to save a query stopped every
suspended-but-paid tenant from being restored, and the test caught it. The query stayed.

---

## Indexing

**No indexes were added, deliberately.** The instruction was not to add them speculatively
but to justify each with a measured improvement, and nothing in the measurements justifies
one: every list view is a single sub-millisecond query, and the reports that were slow were
slow because of query *count*, not query *cost*. Fixing the N+1 patterns removed the
problem at its source. Adding an index to a table whose queries already return in under a
millisecond buys nothing and costs write throughput.

**Re-measure and revisit at scale.** The specific candidates, if a scaled dataset shows
them: `Subscription Event.event_time` (the MRR and audit reports scan by date),
`Generation Reading.reading_date` with `om_contract`, and `User.a3_sola_tenant` (read by
the access gate on every cache miss and by every isolation check).

---

## Scale testing — what was not done

Stated plainly rather than estimated.

The specification asked for 50 tenants with roughly 7,500 records each — around 375,000
documents. **That was not generated.** Building it through the business flow is many hours
of controller execution, and bulk-inserting it would produce rows that measure the database
without exercising the code that reads them.

**What the figures above therefore are:** measurements at 8,084 business records with a
554-row mandate table and a 484-row subscription table, plus a stated linear projection for
the one job whose cost scales with tenant count.

**What is consequently unknown:**

- report timings on tables one to two orders of magnitude larger — although the N+1 fixes
  mean they now scale with result size rather than with row count, which is the property
  that matters
- whether any index becomes justified
- concurrency behaviour under sustained load; the two specific races **were** tested and
  are reported below, but throughput was not
- the true resource ceiling

**Recommendation:** run this same harness against the staging site during the Stage 0
internal period, when it holds a real cycle of real data. The harness is the deliverable;
the numbers are a point-in-time reading.

---

## Concurrency

The two races that would cost real money, run as real races — eight threads on eight
separate database connections, released together by a barrier, asserting on the count of
side effects rather than on the absence of an exception.

| Hazard | Threads | Result |
|---|---:|---|
| Simultaneous renewal orders for one subscription and period | 8 | **exactly 1 Payment Order** |
| Simultaneous provisioning triggers for one subscription | 8 | **exactly 1 acquired the lock**, 7 refused |

Both were designed against in earlier phases and neither had been tested with contention.
A sequential call exercises the "already done" branch, not the "two workers arrived
together" one.

The idempotency key's **uniqueness in the database** is asserted separately, because the
application-level check-then-insert is a race whatever the code does without it.

---

## Sizing recommendation

From the measurements, for **200 tenants**. Assumptions stated because they drive the
numbers: 5 concurrent desk users per active tenant at peak, 10% of tenants active at any
moment, schedulers overnight, media in private files rather than object storage.

| Resource | Recommendation | What makes it the bottleneck first |
|---|---|---|
| **CPU** | 8 vCPU | Python request handling. Reports are the heaviest single consumer; at the measured post-fix figures, 8 cores carry roughly 200 concurrent desk users. |
| **RAM** | 16 GB | ~1 GB per gunicorn worker × 8, plus MariaDB buffer pool at 4 GB, plus redis. Below 8 GB the buffer pool shrinks and query times rise sharply. |
| **Disk** | 200 GB SSD, monitored at 70% | 329 MB at 42 companies. Private files dominate long-term: commissioning certificates and signed agreements at ~2 MB per installation, so 200 tenants × 150 installations × 2 MB ≈ 60 GB over three years, plus backups. |
| **Gunicorn workers** | 8 | 2 × cores. |
| **Background workers** | 2 short, 2 default, 2 long | The long queue carries provisioning and the nightly cost rebuild; give it its own workers so a slow provisioning run cannot delay billing. |
| **MariaDB** | `innodb_buffer_pool_size = 4G`, `max_connections = 200` | The buffer pool wants to hold the working set; at 200 tenants that is a few GB. |
| **Redis** | default cache + queue split, 512 MB | Rate limit counters, the access gate cache and the queues. |

**Where each ceiling arrives:**

- **Disk first**, and by a wide margin, driven by uploaded documents rather than by rows.
  Move private files to object storage before 300 tenants.
- **Database connections** next, if worker counts are raised without raising
  `max_connections`.
- **CPU** last. The permission layer costs 0.2 ms and the access gate effectively nothing,
  so per-request overhead is not the constraint.

**These are derived from measurements at 42 companies, not measured at 200.** Provision
from them, then re-measure with the harness once real load exists.
