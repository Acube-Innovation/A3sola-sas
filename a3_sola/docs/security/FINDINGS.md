# Security findings — Phase 8

Severity-ranked. Nothing has been softened because it was inconvenient, and everything
that was not fixed says so and why.

**Summary: 0 Blockers, 0 High, 3 Medium (all fixed), 6 Low (4 fixed, 2 accepted),
1 environmental (not ours to fix, reported).**

---

## Blockers

**None.**

5,871 cross-tenant attempts across 34 vector families and 254 doctypes and endpoints
returned zero foreign records. See `ISOLATION_AUDIT.md`, including the negative control
that proves the suite detects a real breach when one exists.

---

## High

**None.**

---

## Medium

### M1 — Unverified webhooks could grow the log table without limit *(FIXED)*

**Where:** `a3_sola/api/webhooks.py`, `_log_unverified`

Every request with a bad signature wrote a committed `Payment Webhook Log` row whose
`event_id` carried a random suffix, so nothing deduplicated them. An unauthenticated
attacker could POST to the webhook endpoint in a loop and grow that table without bound —
no credentials, no valid signature, just volume. Disk exhaustion takes the whole site down,
including the billing portal a suspended tenant needs to pay from.

The body was never stored, which was correct, but the row still was.

**Fixed:** the first 20 unverified attempts per source IP per hour are still written —
losing that signal would hide a genuinely misconfigured webhook secret — and beyond that
the attempt is counted in the file log only. Configurable via
`webhook_unverified_log_max`.

### M2 — Control characters survived into stored text *(FIXED)*

**Where:** `a3_sola/api/signup.py` `_clean`, and `a3_sola/api/lifecycle/events.py`

`_clean` trimmed and truncated but kept control characters, including NUL. Every public
form field goes through it, and Phase 7 writes tenant-typed cancellation text into
`Subscription Event`. Those values leave the database again through layers that do not
share Python's view of a string: a NUL truncates at the C boundary, a CR splits an email
header, and either breaks a CSV cell for whoever opens the export.

Not exploitable on its own. Exactly the sort of thing that becomes a finding later.

**Fixed:** one shared helper, `a3_sola/api/sanitise.py`, used by both. Tab, newline and
carriage return are kept for genuine free text; `clean_header` strips those too for
anything reaching a header or a filename.

### M3 — The pricing endpoint was unauthenticated and uncapped *(FIXED)*

**Where:** `a3_sola/api/platform.py` `calculate_plan_total`

Reachable without logging in and free to call in a loop. It writes nothing and reads
published pricing, so the impact is CPU rather than data — but it is the cheapest
amplification target on the public site.

**Fixed:** rate limited per IP at a deliberately generous 240/hour, because the pricing
page legitimately calls it on every toggle.

---

## Low

### L1 — Card-shaped numbers in Error Log *(FIXED — was a false positive in the scanner)*

The first stored-data scan reported 27 card numbers in `Error Log`. All 27 were the same
value: a Python **thread identifier** in a traceback that happens to pass the Luhn check.

Worth recording because the fix is the lesson. A scanner that reports 27 false positives
gets switched off within a week, and a switched-off scanner finds nothing. The card check
now requires Luhn **and** a real issuer prefix **and** the absence of technical context
(`Thread-`, `object at 0x`, `File "`, a line number). A test plants a real Visa test number
to prove it still fires, and plants the original thread id to prove it no longer does.

**Current result: 0 findings.**

### L2 — SQL built by string interpolation *(REVIEWED — accepted)*

**Where:** `a3_sola/api/funnel_jobs.py:102`

One site interpolates a doctype into a table name. The value comes from a literal tuple in
the same function and every value that comes from data is bound with `%s`. A table name
cannot be a bind parameter, so this is the only way to write the query.

Recorded in `scanners.REVIEWED_SQL` with that reasoning, so the standing test stays green
without hiding a future one.

### L3 — Guest endpoint defences were invisible to the first inventory *(FIXED — scanner)*

Seven guest endpoints were flagged as having no validation. All seven were fine:
`_authorised_signup` verifies reference and token, `limit_by_identifier` rate limits, the
webhook verifies an HMAC, and `resend_verification` returns a deliberately neutral message
so a wrong reference cannot confirm which signups exist.

The inventory's markers were generic rather than this app's. Widened, and the flag list is
now empty — which matters, because eight false flags is how a security report gets skimmed
and then ignored.

### L4 — The scanner flagged its own placeholder, and two test-planted fakes *(FIXED)*

Three collisions between the Phase 5 credential scan and the Phase 8 one, all found by
running them together:

- The Phase 8 negative-control tests **plant a fake Razorpay key and a Visa test number** to
  prove the scanners detect one. Both scanners correctly flagged them. Rather than exempt
  the test directory — which would let a genuine credential hide in a fixture — the planted
  values are now **assembled at runtime**, so no key-shaped literal exists in the source and
  both scans stay maximally strict.
- The monitoring guide's redaction example ended `password='[REDACTED]'`, which the
  `assigned_password` pattern matched. **The scanner now ignores placeholders** —
  `[REDACTED]`, `<your-key>`, `${VAR}`, `changeme`, `xxx` — because flagging them trains
  people to ignore the scanner. A test asserts a real assigned value still fires, so the
  rule is a noise reduction rather than a hole.

### L5 — A new guest endpoint appeared unreviewed *(FIXED — the guard worked)*

Phase 8 added `a3_sola.api.health.check` as `allow_guest` so an uptime monitor can reach it.
The guard test failed the build with *"this endpoint is reachable without logging in and has
not been reviewed"* — which is exactly what it is for, on its author.

Reviewed and allowlisted with the reasoning recorded: it returns a status word and a
timestamp, is rate limited at 120/hour per IP, and a separate test fails if the response
ever mentions a dependency, a queue or a version.

### L6 — The starter dataset ships a password in source *(ACCEPTED — the user's decision)*

`a3_sola/setup/starter.py` contains `a3sola-starter` for the demo login, and the patch
installs that user on every deploy. This was raised at the time and reaffirmed: the dataset
must install with no configuration. `docs/STARTER_DATASET.md` says plainly that it is a real
credential on a real site and gives the teardown command.

Allowlisted in the scanner **with that reason recorded**, so it stays visible rather than
silently ignored.

---

## Environmental — not this app's to fix, reported

### E1 — Dependency advisories in the bench toolchain and the Frappe frontend

`a3_sola` declares **no Python and no JavaScript dependencies of its own**. Its supply
chain is Frappe and ERPNext. What the audits found belongs to those:

**Python** (`pip-audit`, 43 packages): 10 advisories in 3 packages.

| Package | Version | Advisories | Fixed in | Reachable from a request? |
|---|---|---|---|---|
| `pip` | 24.0 | 6 | 26.2 | **No** — install-time tooling |
| `setuptools` | 81.0.0 | 1 | 83.0.0 | **No** — build-time only |
| `click` | 8.2.1 | 1 | 8.3.3 | **No** — the bench CLI, not the web process |

None is imported by `a3_sola` (verified by grep) and none sits in the web request path.

**JavaScript** (`yarn audit` against Frappe's `package.json`, 536 dependencies): 67 unique
advisories — 3 critical, 60 high, 51 moderate, 9 low. All are Frappe's **build-time**
frontend toolchain. The three criticals are `form-data` (via `superagent`), `shell-quote`
(via `launch-editor`) and `loader-utils` (via `@vue/component-compiler`) — asset pipeline
and dev tooling, not shipped to a browser and not executed by the server at runtime.

**Recommendation, not applied here:** upgrading `pip`, `setuptools` and `click` inside the
bench virtualenv is an infrastructure change that can break `bench` itself, and the Node
tree belongs to the framework vendor. Do it deliberately on the deployment host, with a
smoke test after:

    ./env/bin/pip install --upgrade 'pip>=26.2' 'setuptools>=83.0.0' 'click>=8.3.3'
    bench --site <site> execute a3_sola.setup.install.setup   # smoke test

Re-run `pip-audit` and `yarn audit` at each Frappe upgrade; neither is pinned by this app.

---

## What is now guarded automatically

Each of these fails the build rather than producing a report nobody reads:

| Guard | Fails when |
|---|---|
| `test_no_unreviewed_guest_endpoint_exists` | A new `allow_guest` method appears unreviewed |
| `test_the_allowlist_has_no_dead_entries` | A reviewed entry no longer exists |
| `test_every_guest_endpoint_defends_itself` | A guest endpoint loses its rate limit or validation |
| `test_no_secret_is_committed_in_the_source` | A key or private key is committed |
| `test_no_card_data_or_identity_number_is_stored` | Card data or an Aadhaar/PAN reaches a stored record |
| `test_password_fields_are_encrypted_at_rest` | A Password field is stored in the clear |
| `test_every_raw_sql_site_is_parameterised_or_reviewed` | New interpolated SQL appears |
| `test_the_scanners_would_actually_find_something` | The scanners stop detecting a planted secret or card |
| `test_guest_holds_nothing_beyond_published_content` | Guest gains a permission |
| `test_no_customer_role_touches_a_platform_private_doctype` | A tenant role gains platform access |
| `test_no_user_holds_both_a_tenant_stamp_and_an_internal_role` | A user ends up on both sides |
| `test_cost_and_margin_stay_behind_permlevel_one` | A cost field is added at permlevel 0 |
| `test_no_attempt_returned_foreign_data` | Any cross-tenant read succeeds |
| `test_the_suite_detects_isolation_that_is_actually_broken` | The attack suite stops detecting a real breach |
