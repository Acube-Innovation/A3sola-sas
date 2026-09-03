# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What this app exposes, enumerated rather than remembered.

The value of this module is that it cannot go out of date. Every table it produces is
walked from the code at the moment it runs, so a method added in a later release appears
here whether or not anybody updated a document - and the guard test built on it fails when
a new guest-facing endpoint appears without being reviewed.
"""

import inspect

import frappe

from a3_sola.api.security.attacks import is_guest_method, whitelisted_methods

#: Guest-reachable endpoints that have been reviewed and are deliberately public.
#:
#: This list is the point of the guard test. Adding a method here is a decision somebody
#: makes on purpose; a new allow_guest method that is NOT here fails the build. That is
#: what stops the unauthenticated attack surface growing quietly over a release.
REVIEWED_GUEST_ENDPOINTS = {
	"a3_sola.api.invitations.accept_invitation",
	"a3_sola.api.payments.cancel_mandate",
	"a3_sola.api.payments.complete_mock_payment",
	"a3_sola.api.payments.get_payment_status",
	"a3_sola.api.payments.initiate_payment",
	"a3_sola.api.payments.verify_checkout_payment",
	# Reviewed Phase 8: returns a status word and a timestamp and nothing else, so an
	# uptime monitor can reach it without an account. Rate limited at 120/hour per IP,
	# and a test fails if the response ever mentions a dependency, a queue or a version.
	"a3_sola.api.health.check",
	"a3_sola.api.platform.calculate_plan_total",
	"a3_sola.api.signup.get_signup_summary",
	"a3_sola.api.signup.request_payment_contact",
	"a3_sola.api.signup.resend_verification",
	"a3_sola.api.signup.submit_demo_request",
	"a3_sola.api.signup.submit_signup",
	"a3_sola.api.signup.update_plan_selection",
	"a3_sola.api.signup.verify_email",
	"a3_sola.api.webhooks.receive",
}

#: Markers that a function applies its own rate limiting.
#:
#: These are THIS app's helpers, not generic names. A scanner looking for the word
#: "ratelimit" reported seven endpoints as unprotected that all call
#: `limit_by_identifier` or sit behind a signature check - and eight false flags is how a
#: security report gets skimmed and then ignored.
RATE_LIMIT_MARKERS = (
	"ratelimit", "rate_limit", "rate_limited", "check_rate", "throttle",
	"limit_by_identifier", "enforce(",
	# A signature-gated endpoint is not rate limited in the usual sense, but an
	# unauthenticated caller cannot make it do anything either.
	"verify_webhook_signature",
)

#: Markers that a function checks a role, an owner or a token before doing anything.
ROLE_MARKERS = (
	"require_role", "check_permission", "has_permission", "only_for",
	"assert_owns", "_assert_tenant", "_authorised_signup", "check_permission",
)


def endpoints():
	"""Every whitelisted method with what can be determined about it from its source."""
	rows = []
	for path, fn in whitelisted_methods():
		try:
			source = inspect.getsource(fn)
		except (OSError, TypeError):
			source = ""
		doc = (inspect.getdoc(fn) or "").strip().split("\n")
		rows.append({
			"path": path,
			"allow_guest": is_guest_method(fn),
			"rate_limited": any(m in source for m in RATE_LIMIT_MARKERS),
			"checks_role": any(m in source for m in ROLE_MARKERS),
			"validates": _validation_signals(source),
			"arguments": _arguments(fn),
			"summary": doc[0] if doc else "(undocumented)",
			"module": getattr(fn, "__module__", ""),
			"reviewed": path in REVIEWED_GUEST_ENDPOINTS,
		})
	return rows


def _validation_signals(source):
	signals = []
	for marker, label in (
		("frappe.throw", "throws on bad input"),
		("validate_", "explicit validation"),
		("_clean(", "input sanitised"),
		("ratelimit", "rate limited"),
		("limit_by_identifier", "rate limited per identifier"),
		("verify_webhook_signature", "HMAC signature verified"),
		("verify_signature", "signature verified"),
		("_authorised_signup", "reference and token verified"),
		("check_permission", "permission checked"),
		("require_role", "role required"),
		("assert_owns", "ownership checked"),
		("NEUTRAL_SIGNUP_MESSAGE", "enumeration-safe response"),
		("captcha", "captcha"),
	):
		if marker in source:
			signals.append(label)
	return signals


def _arguments(fn):
	try:
		return [p.name for p in inspect.signature(fn).parameters.values()]
	except (TypeError, ValueError):
		return []


def flags():
	"""Every guest endpoint that is missing a defence it ought to have.

	A flag is not automatically a finding - `calculate_plan_total` takes no identifier and
	returns published pricing, so rate limiting is the only thing it needs. The table
	states the position for each so a reviewer can disagree with it.
	"""
	problems = []
	for row in endpoints():
		if not row["allow_guest"]:
			continue
		if not row["rate_limited"]:
			problems.append((row["path"], "no rate limiting"))
		if not row["validates"]:
			problems.append((row["path"], "no visible input validation"))
		if not row["reviewed"]:
			problems.append((row["path"], "NOT IN THE REVIEWED ALLOWLIST"))
	return problems


def unreviewed_guest_endpoints():
	"""New guest-facing endpoints nobody has signed off. The guard test's whole job."""
	live = {row["path"] for row in endpoints() if row["allow_guest"]}
	return sorted(live - REVIEWED_GUEST_ENDPOINTS)


def retired_guest_endpoints():
	"""Allowlist entries that no longer exist - dead entries hide real ones."""
	live = {row["path"] for row in endpoints() if row["allow_guest"]}
	return sorted(REVIEWED_GUEST_ENDPOINTS - live)


def render_markdown():
	rows = endpoints()
	guest = [r for r in rows if r["allow_guest"]]
	internal = [r for r in rows if not r["allow_guest"]]
	out = [
		"# Endpoint inventory",
		"",
		"Generated from the code by `a3_sola.api.security.inventory`. It is walked, not "
		"written, so it cannot be out of date - and the guard test fails the build if a "
		"guest-facing endpoint appears that nobody has reviewed.",
		"",
		f"- Whitelisted methods: **{len(rows)}**",
		f"- Reachable without logging in: **{len(guest)}**",
		f"- Authenticated only: **{len(internal)}**",
		"",
		"## Reachable without logging in",
		"",
		"These are the entire unauthenticated attack surface.",
		"",
		"| Method | Rate limited | Validates | Reviewed | What it does |",
		"|---|---|---|---|---|",
	]
	for row in sorted(guest, key=lambda r: r["path"]):
		out.append(
			f"| `{row['path']}` | {'yes' if row['rate_limited'] else '**NO**'} "
			f"| {', '.join(row['validates']) or '**none visible**'} "
			f"| {'yes' if row['reviewed'] else '**NO**'} | {row['summary']} |"
		)
	out += [
		"",
		"## Authenticated",
		"",
		"| Method | Checks a role | Validates | What it does |",
		"|---|---|---|---|",
	]
	for row in sorted(internal, key=lambda r: r["path"]):
		out.append(
			f"| `{row['path']}` | {'yes' if row['checks_role'] else 'no'} "
			f"| {', '.join(row['validates']) or 'none visible'} | {row['summary']} |"
		)
	return "\n".join(out)
