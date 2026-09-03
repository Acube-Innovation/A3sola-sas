# Backup and disaster recovery

Not a strategy document. A restore was **performed**, verified and timed, and it found a
defect that would have cost the client every payment they take.

---

## The finding that matters

> **Encrypted secrets do not survive a restore unless you carry the encryption key across,
> and nothing warns you.**

`bench backup` writes `<timestamp>-<site>-site_config_backup.json`, which **does** contain
the site's `encryption_key`. `bench restore` **does not apply it**. A site restored into a
new bench generates its own key, so every `Password` field is ciphertext nobody can read.

Measured on the restored copy before the fix:

| Field | Source | Restored |
|---|---|---|
| `razorpay_webhook_secret` | decrypts | **fails** |

Everything else looked perfect — 66 doctypes with matching row counts, byte-identical
sample documents, all 83 private files present. A restored system that appears completely
healthy and **cannot verify a single webhook signature**, so no payment is ever confirmed
and no renewal is ever collected. This is exactly the failure that is only ever found by
actually restoring.

**The remedy, verified:** copy `encryption_key` from the backed-up site config into the new
site's `site_config.json`, then clear the cache. Re-verified afterwards — the secret
decrypts and the comparison is clean.

```bash
python3 - <<'PY'
import json
backup = json.load(open("sites/<site>/private/backups/<stamp>-<site>-site_config_backup.json"))
target = json.load(open("sites/<new-site>/site_config.json"))
target["encryption_key"] = backup["encryption_key"]
json.dump(target, open("sites/<new-site>/site_config.json", "w"), indent=1)
PY
bench --site <new-site> clear-cache
```

**Put the site config backup wherever the database backup goes.** Without it the database
is only mostly restorable.

---

## The second finding

The scheduled backup already running on this bench produced **database only** — no
`files.tar`, no `private-files.tar`. Every commissioning certificate, signed net-metering
agreement and uploaded receipt lives in private files. A database-only backup loses all of
them and, again, says nothing.

**Backups must use `--with-files`.** Both were present in the manual backup taken for this
drill; the automatic one at 06:00 the same morning had neither.

---

## Measured figures

Taken on the development host: 8 vCPU class, MariaDB 10.11, site of 329 MB with 8,084
business records across 66 doctypes and 85 files.

| Step | Measured |
|---|---|
| `bench backup --with-files` | **8.1 s** |
| Backup size | 17.8 MB database (gzip) + 3.3 MB private files + 10 KB public |
| Create a clean site | **33.9 s** |
| `bench restore` with both file sets | **55.1 s** |
| Apply the encryption key and clear cache | ~2 s |
| **Total measured RTO** | **≈ 91 seconds** |

### RTO and RPO

**RTO — 91 seconds measured**, at this data size, on this hardware, with the backup already
on the machine. That is the honest floor. What it does **not** include, and what the client
must add:

- retrieving the backup from off-site storage (network-bound; at 20 MB it is seconds, and
  at 20 GB it is not)
- provisioning a host if the original is gone
- DNS and TLS
- somebody noticing and deciding to act

**A realistic RTO for a full-host loss is measured in hours, and it is dominated by the
human decision and the host, not by the restore.** Quote 4 hours, and hold the 91 seconds
as evidence that the technical step is not the bottleneck.

**RPO — the backup interval, which is currently daily.** Up to 24 hours of payments,
commissioning records and service tickets. For a system taking money, daily is too coarse:
move to hourly database backups with daily full-plus-files, giving an RPO of one hour at a
cost of roughly 18 MB an hour at present size.

---

## Restore verification, and how to repeat it

Everything below was scripted and run against the restored copy, comparing it to a
fingerprint taken from the source beforehand.

| Check | Result |
|---|---|
| Row counts, all 66 registered doctypes | **0 mismatches** |
| Sample documents across all four modules, SHA-256 of every field | **7 of 7 identical** |
| Private files present in the database | **83 of 83** |
| Private files actually present on disk | **0 missing** |
| Password fields decrypt | **fails before the key fix, passes after** |
| `a3_sola` scheduled jobs | **27 of 27** |
| Users / Companies | **56 / 42, both match** |
| Adversarial isolation suite on the restored copy | **5,871 attempts, 0 successful** |
| Isolation negative control on the restored copy | **66 leaks detected as expected** |

Repeat it with:

```bash
bench --site <source> execute a3_sola._dr.fingerprint     # before
bench --site <restored> execute a3_sola._dr.verify        # after
bench --site <restored> run-tests --module a3_sola.tests.security.test_isolation_attacks
```

*(the fingerprint helper is a drill script, not shipped app code — see this document's
appendix in the repository history if it has been removed.)*

---

## Configuration to put in place

Currently **not configured** on this bench, and each is the client's to do:

| Setting | Status | What to do |
|---|---|---|
| Database backup schedule | daily, **without files** | add `--with-files` |
| Off-site destination | **none** | S3-compatible bucket in a different region |
| Encryption at rest | **none** | server-side encryption on the bucket |
| Retention | bench default | 7 daily, 4 weekly, 12 monthly |
| Site config backup stored with the database | **the file is produced but nothing collects it** | ship it with the dump — see the finding above |
| Restore rehearsal | performed once, here | schedule quarterly and record the RTO each time |

---

## Failure drills

Each was run. What happened, whether it recovered, and what a human must do.

### The gateway outage — the circuit breaker drill

The scenario Phase 7's breaker exists for. Run on the restored copy with the engine armed
exactly as a client would arm it after go-live: dry run off, automatic suspension on,
approval not required, breaker limit 10.

25 subscriptions were pushed to 25 days unpaid at once, as a gateway outage would.

| Step | Observed |
|---|---|
| Nightly run | **halted** — "27 suspensions exceeds the limit of 10" |
| Tenants suspended | **0** |
| Access gates changed | **none** |
| Users disabled | **0** |
| Alert raised | yes — `a3_sola: lifecycle run HALTED by the circuit breaker` |

**Nothing was switched off and a human was told.** That is the entire design intent, and it
held under the conditions it was designed for.

### The kill switch

Same conditions, breaker limit raised to 100 so it would not fire, kill switch on:

| Step | Observed |
|---|---|
| Nightly run | **halted** — reason "kill switch" |
| Tenants suspended | **0** |
| Access gates changed | **none** |
| Evaluation and logging | still ran |

### Releasing both

Breaker raised, kill switch off, so the engine is free to act. It evaluated 479
subscriptions and reported **1 error**, which was the access controller **refusing** to
suspend a tenant with no resolvable users:

> Refusing to suspend TNT-…: No users are stamped with tenant TNT-…

That is fail-closed behaviour working. Disabling nobody and saying so is always
recoverable; disabling the wrong people is not.

**A defect was found and fixed during this drill.** The engine was planning transitions the
state machine forbids from the subscription's current state — a cancelled tenant reaching
the policy's day-60 stage. Each attempt was correctly refused, but it wrote an error every
night for every such subscription, and an error log full of expected failures is an error
log nobody reads. The engine now records the decision and does not attempt the move.
Errors in the drill fell from 3 to 1.

### A worker dying mid-run

Not simulated by killing a process. What is asserted instead, by test rather than by drill:
the lifecycle engine commits after every subscription and is idempotent, so a resumed run
re-evaluates and reaches the same state; the billing engine's idempotency key is unique in
the database, and eight simultaneous renewal attempts produce **exactly one** Payment Order
(`tests/security/test_concurrency.py`).

**Not tested:** an actual `SIGKILL` mid-transaction. Recommended before go-live, on
staging, during the Stage 0 internal period.

### Not tested at all

Stated so nobody assumes otherwise:

- **Database unavailable mid-transaction.** Requires stopping MariaDB under load.
- **Disk filling up.** Requires a constrained volume.
- **Razorpay unreachable for an hour during billing.** The mock gateway can simulate
  failures, but a true hour-long outage across a real billing run has not been staged.
- **Webhook flood.** The per-IP cap added in Phase 8 (finding M1) bounds the log growth,
  but the throughput ceiling has not been measured.

---

## Restoring one tenant without disturbing the others

The hard case, and the honest answer is that **it is a manual operation and it is not
clean**.

What exists: Phase 6's termination export and Phase 7's cancellation export both produce a
manifest of everything held for a tenant, and the isolation model means a tenant's data is
identifiable by its `company`.

The procedure:

1. Restore the backup to a **scratch site** (91 seconds, proven above). Never restore over
   the live site to recover one tenant.
2. Identify the tenant's company on the scratch site.
3. Export the affected doctypes filtered to that company.
4. Re-import into the live site.

**What this does not recover, and you must say so to the customer:**

- **Document names.** A re-imported record gets a new name from the naming series unless
  the original name is free. Anything that referenced the old name by string — an email
  already sent, a printed form — now points at nothing.
- **Submitted documents' docstatus history.** A re-imported submitted document is a new
  document that was submitted today.
- **Attachments** unless the private files are re-imported alongside, which the export
  manifest lists but does not itself carry.
- **Ledger postings**, which if enabled must be reversed and re-made rather than restored.

**Recommendation:** for anything beyond a handful of records, restore the whole site to a
scratch instance, let the customer confirm what they need from it, and copy that forward
deliberately. Treat a full per-tenant restore as a several-hour operation with a person on
it, not as a button.
