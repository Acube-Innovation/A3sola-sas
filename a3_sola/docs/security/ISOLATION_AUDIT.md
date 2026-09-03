# Adversarial isolation audit

The highest-consequence risk in this product is one solar EPC reading another's pipeline.
This is the evidence that they cannot, and — more importantly — the evidence that the test
which says so would notice if they could.

Re-run it any time:

    bench --site <site> run-tests --module a3_sola.tests.security.test_isolation_attacks

Or against live data, read-only, from the desk:

    bench --site <site> execute a3_sola.api.security.audit.run_isolation_audit

It also runs monthly on its own and alerts on any success.

---

## Result

| | |
|---|---|
| Attempts | **5,871** |
| Vector families | **34** |
| Doctypes and endpoints attacked | **254** |
| Blocked | **5,052** |
| Not attempted (stated below) | **819** |
| **Successful cross-tenant accesses** | **0** |

Zero is the only passing result. Any success fails the test run rather than raising a
warning.

### The negative control

A clean run is only evidence if the attacks would find something when there is something
to find. So the suite deliberately deletes the User Permission that *is* the isolation
boundary for one user, re-runs a slice of itself, and **requires** a leak:

> negative control: **66 leaks detected** with the boundary removed, as expected

66 with the boundary gone, 0 with it in place. That is the difference between "we found
nothing" and "there is nothing to find".

---

## What was attacked

Three tenants (A, B, C), each with its own company, its own tenant record and users at
three role levels — administrator, ordinary user, technician. Every user attacks a
*different* tenant than their own: A→B, B→C, C→A.

Three tenants rather than two on purpose. With two, a bug that leaks "everything except
mine" and one that leaks "exactly one other tenant" look identical.

| # | Vector | What it tries |
|---|---|---|
| 1 | `list_view` | The ordinary list, filtered to a foreign company |
| 2 | `direct_get` | Straight to a known foreign name, bypassing the list |
| 3 | `client.get` / `get_list` / `get_value` / `get_count` | The REST layer, four separate code paths |
| 4 | `report_foreign_filter` / `report_no_filter` | Every report, with a foreign company **and with none at all** |
| 5 | `link_search` / `search_widget` | The link dropdown and awesome bar — these leak *names* even when reads are blocked |
| 6 | `print_view` | Print and PDF for a foreign document |
| 7 | `private_file` | A private attachment on a foreign document, by URL |
| 8 | `export` | CSV export from a list filtered to a foreign company |
| 9 | `bulk_set_value` / `bulk_delete` | Writing to and deleting a foreign document |
| 10 | `dashboard_aggregate` | Number cards — an aggregate leaks without exposing a record |
| 11 | `global_search` | A string that exists only in foreign data |
| 12 | `comments` / `versions` / `activity` | The timeline, a separate read path |
| 13 | Portal endpoints | Billing and customer portal with manipulated parameters |
| 14 | Public endpoints | The funnel with a foreign reference and a guessed token, as Guest |
| 15 | `whitelisted_method` | **Every one of the 133 whitelisted methods**, called with a foreign reference |
| 16 | Privilege escalation | Six attempts, each verified by outcome |
| 17 | `group_by_company` | A report grouped by company, checking whose names appear |
| — | `platform_private` | The vendor's own records — tenants, payment orders, settings |

The doctype list is read from the module registries, not written here, so a doctype added
in a later release is attacked without anybody remembering to add it.

The endpoint list is walked from the code for the same reason: a whitelisted method added
next month cannot escape the sweep.

### Privilege escalation, and why each check verifies the outcome

The first version of this vector reported six Blockers that were not real. Frappe accepts a
save in which a user appends a role they may not grant, and then silently discards the row
— so "the call did not raise" is not escalation.

Every check now asserts on the **effect**:

| Attempt | Verified by |
|---|---|
| Grant myself `Platform Admin` | Do I hold it afterwards? |
| Delete my own User Permission | Can I now read the other tenant's data? |
| Raise my own seat quota | Did the number actually change? |
| Read A3 Sola Settings | Does `check_permission` pass? |
| Read another tenant's record | Does `check_permission` pass? |
| Read the gateway secret | Does a **value** come back? |

All six blocked, verified by outcome.

---

## What was not attempted, and why

**819 attempts were skipped.** Skipped is not passed, so each is stated:

- **Whitelisted methods that take no document reference.** A method with no
  identifier argument cannot be pointed at a foreign record; the enumeration still counts
  it so the total reflects the whole surface.
- **A handful of doctypes that would not accept even a minimal seeded row.** Their
  controllers refuse an insert that ignores mandatory fields, so there was no foreign
  record to attack. They are still covered by vectors 1, 4, 8 and 17, which do not need an
  existing record.

The fixture deliberately seeds one row in **every** company-scoped doctype rather than the
three the business flow creates, precisely so "no foreign record exists" stops being the
answer. That change alone converted roughly a thousand skips into real attempts.

---

## Limits of this evidence

Stated plainly, because an audit that overclaims is worse than none:

- It runs **in-process** with `frappe.set_user`, not over HTTP with real sessions. It
  therefore exercises the permission layer honestly but not the web server, the reverse
  proxy, or anything terminating TLS.
- It is not a penetration test by a third party. It is a regression suite that encodes
  what we know to look for.
- The public-endpoint vector runs as Guest against the funnel; it does not fuzz tokens at
  scale, and brute-force resistance rests on the rate limiting inventoried separately.
- Attachments: it attacks private files that exist on foreign documents. On a site with no
  such attachments the vector reports skipped rather than passed.
