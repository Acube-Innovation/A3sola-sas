# The tenancy model

One decision, made once, that everything else in Phase 6 hangs off. It is written down
here because the reasoning is easy to lose and expensive to reconstruct.

## What was chosen

**Multi Company.** Every tenant is an ERPNext Company inside one Frappe site, isolated by a
User Permission on Company plus the permission hooks built across Phases 1 to 5.

`tenancy_strategy` in A3 Sola Settings holds it, and the setting refuses to change once any
Tenant exists — see `A3SolaSettings.validate_tenancy_strategy`. Every Tenant also snapshots
the strategy it was built under, so even an override could not silently reclassify an
existing workspace.

## The comparison

| | Multi Company | Multi Site |
|---|---|---|
| Provisioning action | Create Company + User Permissions | `bench new-site`, install the app, create Company |
| Time to provision | Seconds — measured at 12s end to end | Minutes |
| Runs where | An ordinary background worker | A privileged OS-level runner outside the web process |
| Isolation | Enforced by permission hooks — correct, and revocable by one bad query | Structural: separate databases |
| Cross-tenant reporting | A query | Aggregation infrastructure |
| Upgrades | One `bench migrate` | One per site |
| Operational cost | Low | Meaningfully higher |
| Blast radius of a bug | Every tenant | One tenant |

## Why Multi Company, for now

The honest version: it lets the product ship, and for the first twenty to fifty tenants the
risk it carries is manageable **provided the isolation is actually verified rather than
assumed**. That proviso is why step 12 exists and why it is a gating step rather than a
warning. Without it, multi-company tenancy is a promise nobody has checked.

Two findings from building Phase 6 are worth recording, because both were exactly the class
of bug this model exposes and neither was visible from the code:

* Thirty reports took a `company` filter and trusted it. Three built raw SQL from it. A
  tenant admin who edited the filter in the URL would have read a competitor's ledger, and
  nothing would have thrown. Fixed by `permissions.resolve_report_company`, which every
  report now goes through, with a test that enumerates them.
* Master seeding checked "does this record exist" without a company. Once one tenant had a
  roof type called `RCC Flat Roof`, no later tenant got one — and seeding reported success,
  because from its point of view the record did exist.

Neither would have been possible under multi-site. Both were found by the isolation test and
the seeding verification, which is the argument for having them.

## What would trigger a migration

Any one of these, on its own:

* **One tenant's data loss would end the business.** Shared-database recovery means
  restoring everybody to restore one, or a selective export-and-replay that nobody has
  rehearsed.
* **One tenant's data volume degrades everyone else's queries.** A single customer with
  fifty thousand installations makes every other customer's list view slow.
* **A customer contractually requires their data in a separate database.** Some enterprise
  and government buyers do, and it is not negotiable when they do.
* **A cross-tenant leak reaches production.** Not a near-miss caught by the isolation test —
  an actual one. At that point the enforced model has failed its own premise.

## What migrating would involve

Not a rewrite, deliberately — that is what the strategy interface bought. But not small
either:

1. Implement `MultiSiteStrategy` and the privileged runner it needs. See
   `api/provisioning/strategies/multi_site.py`, which documents the required shape: a queue
   table the web process writes to, a supervised worker under its own account with an
   audited command allowlist, and site names derived from the validated `tenant_code` and
   nothing else. The web process must never shell out.
2. Per-tenant data extraction and load. Every doctype is already company-scoped, so the
   extraction is mechanical — `tenant_admin.export_tenant_data` already walks the registry
   and produces it — but the load has to preserve link integrity and naming series
   positions.
3. Rework anything that reads across tenants: the Platform module's own reports, the
   billing engine's daily sweep, the dunning run. These currently work because every tenant
   is one query away.
4. Per-site migration in the deployment pipeline, and a way to tell when one site is behind.
5. Re-point the isolation test: under multi-site it asserts the database is genuinely
   separate and that no cross-site connection string is reachable from tenant code.

Existing tenants would stay multi-company unless individually migrated. Both models can run
side by side because the strategy is snapshotted per tenant rather than read globally —
that was the point of snapshotting it.
