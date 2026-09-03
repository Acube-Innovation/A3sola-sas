# Deployment

A reproducible build. Every step that was actually needed to stand this app up, including
the ones that are easy to forget.

---

## Prerequisites

| | Version | Note |
|---|---|---|
| Python | 3.10+ | 3.12 used here |
| Node | 18+ | for the asset build |
| MariaDB | 10.6+ | 10.11 used here. Frappe warns above 10.8; it works |
| Redis | 6+ | two instances, cache and queue |
| wkhtmltopdf | 0.12.6 **with patched Qt** | Unpatched renders page breaks wrongly, and every generated PDF in this app is multi-page |
| Frappe | v15 | pinned in `pyproject.toml` |
| ERPNext | v15 | pinned |

`a3_sola` declares **no Python or JavaScript dependencies of its own.**

## Build

```bash
bench init a3sola-bench --frappe-branch version-15
cd a3sola-bench
bench get-app erpnext --branch version-15
bench get-app https://github.com/<org>/a3_sola.git

bench new-site <site> --db-root-password <pw> --admin-password <pw>
bench --site <site> install-app erpnext
bench --site <site> install-app a3_sola      # runs after_install; seeds everything
bench --site <site> migrate
```

`install-app` seeds roles, role profiles, masters, marketing content, the tenant blueprint,
the default subscription policy and its stage emails. **No manual fixture import is
required** — the app seeds itself and the seeding is idempotent.

### Verify the install

```bash
bench --site <site> execute a3_sola.api.health.detail
bench --site <site> run-tests --app a3_sola
```

---

## Configuration before first use

### Must be set — the app will not work correctly without these

| Where | What |
|---|---|
| A3 Sola Settings → General | Company details, GSTIN, state code, letterhead |
| → CRM | DISCOM, sections, tariff — **check the tariff against a real bill** |
| → Operations | Stage templates per scheme, document template set |
| → Projects | **Account mappings** — every one. Nothing posts until these are filled |
| → Payments | Razorpay key id, key secret, webhook secret, AFA ceiling |
| → Provisioning | Tenancy strategy, blueprint, admin role profile |
| → Lifecycle | Default policy, approval role, alert role |
| → Monitoring | Alert thresholds, error log retention |

### Must be decided — by a person, not by the app

| Decision | Who | Gates |
|---|---|---|
| GST valuation basis for solar EPC | **The client's CA, in writing** | `enable_accounting_postings` |
| GST treatment for the SaaS subscription | The client's CA | `enable_payment_postings` |
| Suspension thresholds | The client | `docs/POLICY_GUIDE.md` |
| RBI AFA ceiling | Verify against the current framework | `afa_free_debit_ceiling` |

### Razorpay

1. Live keys into Settings → Payments
2. Register the webhook: `https://<site>/api/method/a3_sola.api.webhooks.receive`
3. Subscribe to `payment.captured`, `payment.failed`, `refund.processed`,
   `subscription.charged`
4. Copy the webhook secret into Settings
5. **Send a test event and confirm `signature_verified` is 1** in Payment Webhook Log

A webhook whose signature does not verify is silently ignored — by design, so an attacker
learns nothing. It also means a wrong secret looks exactly like no traffic.

### DNS, TLS, email

- A record to the host; TLS via the platform or certbot
- SMTP in Frappe's Email Account, and **send one test email** — the whole funnel depends on
  verification mail arriving
- SPF and DKIM, or your verification emails land in spam and your signups silently stop

### Scheduler

```bash
bench --site <site> set-config enable_scheduler 1
bench --site <site> execute a3_sola.api.monitoring.heartbeat.status   # all 30 jobs
```

### Backups — read `BACKUP_AND_DR.md` first

```bash
bench --site <site> backup --with-files
```

**Two things that will otherwise cost you everything:**

1. **`--with-files`, always.** A database-only backup silently loses every commissioning
   certificate and signed agreement.
2. **Keep `<stamp>-<site>-site_config_backup.json` with the dump.** It holds the encryption
   key. Without it a restored site cannot decrypt a single secret, and it will not tell you.

---

## Smoke test after every deployment

```bash
bench --site <site> execute a3_sola.api.health.detail                 # status ok
bench --site <site> execute a3_sola.api.monitoring.heartbeat.status   # 30 jobs
bench --site <site> execute a3_sola.api.security.audit.run_isolation_audit  # 0 leaks
bench --site <site> execute a3_sola.api.lifecycle.admin.preflight     # expected state
```

Then by hand:

1. The public site renders and the pricing page toggles
2. A signup submits and its verification email arrives
3. A tenant user signs in and sees only their own data
4. One report opens
5. One PDF generates with correct page breaks

---

## Steps I had to work out, that are not obvious

Recorded because the instruction was to report any step not already documented:

- **`--no-mariadb-socket`** was needed on `bench new-site` on this host, or site creation
  fails on the socket path.
- **Redis must be running before `bench migrate`.** It fails with "Service redis_cache is
  not running", which reads like an app error and is not.
- **`allow_tests` must be set** on a restored site before `run-tests` will do anything —
  restoring does not carry it.
- **The encryption key is not restored.** The single most important step in
  `BACKUP_AND_DR.md`.
- **`bench --site X execute a3_sola.module.function`** swallows the real exception and
  re-raises `NameError: name 'a3_sola' is not defined`. When a command fails that way, the
  actual error is being hidden — run the function from a scratch module with a traceback.
