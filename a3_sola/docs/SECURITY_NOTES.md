# Security notes — the public surface

Phase 4 puts unauthenticated endpoints on the same Frappe instance that holds every
tenant's customers, contracts and ledgers. This document is the inventory of that surface
and what defends it. Read it before changing anything under `a3_sola/api/signup.py`.

## The rules the funnel code follows

These are not style preferences. Each one closes a specific hole:

1. **Nothing public creates a privileged record.** No User, Company, Role assignment,
   Customer or any ERPNext master is created anywhere in the signup or demo flow. Phase 6
   provisions, after payment, under controlled conditions. `test_signup.py` greps the
   module to keep it that way.
2. **Every field is validated and normalised server-side.** The browser's validation is a
   courtesy to the visitor; it is not a control.
3. **Every endpoint is rate limited** by IP, and the ones that matter also by email.
4. **Nothing is created until the honeypot and the rate limit have both passed.**
5. **A response never reveals whether an email is already in the system.** Signing up
   twice and signing up once return byte-identical bodies.
6. **A response never returns the record**, the verification token, the IP or the user
   agent.
7. **Token comparison is constant-time**, and a wrong token is indistinguishable from an
   expired one or one that never existed.

## Every allow_guest endpoint

| Endpoint | What it does | Limits |
|---|---|---|
| `a3_sola.api.signup.submit_signup` | Creates a Subscription Signup and sends a verification email | Per IP per hour, and per email per day |
| `a3_sola.api.signup.verify_email` | Consumes a verification token, once | Per IP per hour, plus an attempt cap on the record |
| `a3_sola.api.signup.resend_verification` | Sends the verification link again | Per IP per hour, plus a hard cap per signup |
| `a3_sola.api.signup.update_plan_selection` | Re-prices a verified signup before payment | Per IP per hour; **requires the summary key**, not just the reference |
| `a3_sola.api.signup.get_signup_summary` | Returns the summary page's fields | Requires the summary key |
| `a3_sola.api.signup.request_payment_contact` | The pre-Phase-5 "we will call you" path | Requires the summary key |
| `a3_sola.api.signup.submit_demo_request` | Creates a Demo Request | Per IP per hour, and per email |
| `a3_sola.api.platform.calculate_plan_total` | Prices a plan. Pure - reads and computes, writes nothing | None needed |

Everything else in the app requires a session.

## Proving you are the applicant

The verification token is burned on use, so the summary page cannot use it. It uses a
**summary key**: a SHA-256 of the signup name, the applicant's email, the record's
creation timestamp and the site secret. It cannot be derived from a reference alone, and
it grants read access to exactly one signup's summary and nothing else.

A guessed reference and a wrong key produce the same error as a record that does not
exist, so neither confirms anything.

## Rate limits, and where to tune them

All in **A3 Sola Settings → Platform → Abuse Control**:

| Setting | Default | Protects |
|---|---|---|
| `signup_rate_limit_per_ip_per_hour` | 5 | Bulk signup from one address |
| `signup_rate_limit_per_email_per_day` | 3 | One address being cycled through many IPs |
| `demo_rate_limit_per_ip_per_hour` | 5 | Demo form spam |
| `verification_attempts_max` | 10 | Brute-forcing a token on one record |
| `resend_verification_max` | 3 | Using our mail server to bombard somebody |
| `verification_token_hours` | 24 | How long a stolen link stays useful |

Counters are a fixed window in the cache, incremented with an atomic redis `INCR` so two
simultaneous requests cannot both slip under the limit. If the cache is unavailable the
limiter **fails open** and logs loudly — a redis restart must not take signup down — so
alert on `a3_sola: rate limit backend unavailable`.

The refusal message never states the limit. Telling somebody they get five an hour tells
them to come back in an hour from somewhere else.

## Captcha — turn this on before go-live

`enable_captcha` is **off by default**, so a missing key cannot break signup on day one.
It should be on in production. A honeypot and a rate limit stop scripts; they do not stop
a determined person with a browser.

Cloudflare Turnstile is implemented and verified server-side. Configure
`captcha_provider`, `captcha_site_key` and `captcha_secret_key`, then switch
`enable_captcha` on. Verification **fails closed**: if the captcha service is unreachable
or the secret is missing, submissions are refused, because failing open would defeat the
point.

## Personal data, and how long it is kept

| Data | Where | Retained |
|---|---|---|
| Name, work email, phone, company | Subscription Signup, Demo Request | For the life of the sales relationship |
| GSTIN, city, state, website | Subscription Signup | As above |
| **IP address and user agent** | Both | `personal_data_retention_days`, default **30** |
| **Verification token** | Subscription Signup | `verification_token_retention_days`, default **30**, and burned immediately on use |
| Price snapshot | Subscription Signup | Kept — it is the record of what was agreed |

The purge runs daily and is **on by default**. Holding somebody's IP address indefinitely
because nobody configured a retention period is not a defensible position under the DPDP
Act.

`ip_address`, `user_agent`, `verification_token` and `price_breakdown` sit at **permlevel
1**, granted only to Platform Admin. Platform Sales works the pipeline every day and has
no reason to see an applicant's IP address. The token is additionally hidden, `no_copy`,
absent from every list view and standard filter, and not in the doctype's search fields —
so it cannot surface through a report, an export or a print format.

## Guest permissions

Exactly eleven doctypes are readable by a logged-out visitor, all of them Platform
marketing content. `tests/platform/test_guest_permissions.py` enumerates **every doctype
in the whole app** and fails if anything else is guest-readable, or if a guest holds any
write-like permission anywhere.

That test is what stops a doctype added in Phase 5, 6, 7 or 8 becoming world-readable
because a permission row was copied from the wrong template. Do not weaken it.

## Pre-go-live checklist

- [ ] Turn `enable_captcha` on and configure the provider keys.
- [ ] Have an Indian technology lawyer review all three legal pages, then record the
      review on each **Platform Legal Page** — the draft banner disappears when the review
      is recorded, not when somebody deletes a warning.
- [ ] Run the guest permission audit: `bench --site <site> run-tests --app a3_sola
      --module a3_sola.tests.platform.test_guest_permissions`.
- [ ] Confirm the retention periods match what the privacy policy promises.
- [ ] Set `sales_email` to a monitored address — several failure paths notify it.
- [ ] Confirm `robots.txt` still excludes every signup route, and that `sitemap.xml`
      contains none of them.
- [ ] Alert on `a3_sola: rate limit backend unavailable` and on
      `a3_sola: captcha misconfigured`.
- [ ] Review `disposable_email_domains` against a current blocklist.
