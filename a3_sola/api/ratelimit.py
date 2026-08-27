# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Rate limiting for the public endpoints.

These endpoints are unauthenticated and sit on the same instance as every tenant's business
data. The limits below are the cheapest defence there is, and they are deliberately dumb:
a fixed window in the cache, keyed by IP and by identifier, with a generic refusal.

Two rules shape everything here:

* The refusal message never states the limit. Telling an attacker they get five an hour
  tells them to come back in an hour with a different address.
* A breach is logged with enough to investigate and nothing that identifies a person
  beyond the address they came from.
"""

import functools

import frappe
from frappe import _

#: Deliberately vague. It does not say what the limit is or which one was hit.
THROTTLE_MESSAGE = "Too many attempts from here. Please wait a little and try again."


def client_ip():
	request = getattr(frappe.local, "request", None)
	if not request:
		return "unknown"
	# X-Forwarded-For is set by our own proxy; the left-most entry is the client.
	forwarded = request.headers.get("X-Forwarded-For")
	if forwarded:
		return forwarded.split(",")[0].strip()
	return request.remote_addr or "unknown"


def user_agent():
	request = getattr(frappe.local, "request", None)
	return (request.headers.get("User-Agent") if request else "") or ""


def _limit(setting, fallback):
	from a3_sola.api.settings import get_int

	value = get_int(setting, fallback)
	return value if value and value > 0 else fallback


def check(bucket, identifier, setting, fallback, window_seconds):
	"""Count one attempt. Returns True while under the limit, False once over it.

	Fixed window rather than sliding: a sliding window costs a sorted set per key and buys
	very little against the kind of abuse a marketing form actually sees.

	Counted with an atomic INCR rather than get-then-set, for two reasons. It is race-free
	- two simultaneous requests cannot both read 4 and both write 5 - and it sidesteps
	Frappe's `get_value`, which caches a miss in `frappe.local` while `set_value` with an
	expiry does not update that cache, so a read-then-write counter silently never
	increments inside one process.
	"""
	limit = _limit(setting, fallback)
	cache = frappe.cache()
	key = cache.make_key(f"a3s_rl:{bucket}:{identifier}")

	try:
		count = cache.incrby(key, 1)
		if count == 1:
			cache.expire(key, window_seconds)
	except Exception:
		# A cache that is down must not take signup down with it. Log loudly and allow -
		# failing closed here would mean nobody can sign up while redis is restarting.
		frappe.log_error(frappe.get_traceback(), "a3_sola: rate limit backend unavailable")
		return True

	return count <= limit


def enforce(bucket, identifier, setting, fallback, window_seconds, detail=None):
	"""Check, and refuse loudly-but-vaguely if over."""
	if check(bucket, identifier, setting, fallback, window_seconds):
		return

	frappe.logger("a3_sola").warning(
		{
			"event": "rate_limit_hit",
			"bucket": bucket,
			# The identifier is an IP or a hashed email, never a raw address in the log.
			"identifier": identifier,
			"detail": detail,
		}
	)
	frappe.throw(_(THROTTLE_MESSAGE), frappe.TooManyRequestsError, title=_("Please slow down"))


def rate_limited(bucket, setting, fallback, window_seconds=3600):
	"""Per-IP limit on a public endpoint."""

	def decorator(fn):
		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			enforce(bucket, client_ip(), setting, fallback, window_seconds, detail=fn.__name__)
			return fn(*args, **kwargs)

		return wrapper

	return decorator


def limit_by_identifier(bucket, identifier, setting, fallback, window_seconds=86400):
	"""Per-email (or per-record) limit, on top of the per-IP one.

	The identifier is hashed so the cache and the logs never hold a raw email address.
	"""
	import hashlib

	digest = hashlib.sha256((identifier or "").strip().lower().encode()).hexdigest()[:32]
	enforce(bucket, digest, setting, fallback, window_seconds)


def reset(bucket, identifier):
	"""Clear one counter. Used by tests and by an admin unblocking a real customer."""
	cache = frappe.cache()
	cache.delete_value(f"a3s_rl:{bucket}:{identifier}")


def reset_all():
	"""Clear every counter. Tests only - never call this from a request."""
	cache = frappe.cache()
	for key in cache.keys(cache.make_key("a3s_rl:*")):
		cache.delete(key)


# ------------------------------------------------------------------- captcha
def verify_captcha(token):
	"""Verify a captcha response server-side.

	Implemented for Cloudflare Turnstile. Disabled by default so a missing key cannot
	break signup on day one - but see docs/SECURITY_NOTES.md: this should be on before
	go-live, because a honeypot and a rate limit stop scripts, not a determined human.
	"""
	from a3_sola.api.settings import get_value

	settings = frappe.get_cached_doc("A3 Sola Settings")
	if not settings.enable_captcha:
		return True

	secret = settings.get_password("captcha_secret_key", raise_exception=False)
	if not secret:
		frappe.log_error(
			"Captcha is enabled but no secret key is configured. Submissions are being "
			"refused because failing open would defeat the point.",
			"a3_sola: captcha misconfigured",
		)
		frappe.throw(_("We could not verify that you are human. Please try again."))

	if not token:
		frappe.throw(_("Please complete the verification challenge."))

	provider = settings.captcha_provider or "Cloudflare Turnstile"
	endpoint = {
		"Cloudflare Turnstile": "https://challenges.cloudflare.com/turnstile/v0/siteverify",
		"Google reCAPTCHA v3": "https://www.google.com/recaptcha/api/siteverify",
	}.get(provider)

	try:
		import requests

		response = requests.post(
			endpoint,
			data={"secret": secret, "response": token, "remoteip": client_ip()},
			timeout=10,
		)
		ok = bool(response.json().get("success"))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: captcha verification failed")
		# Fail closed. An unreachable captcha service is not a reason to accept anything.
		frappe.throw(_("We could not verify that you are human. Please try again shortly."))

	if not ok:
		frappe.throw(_("We could not verify that you are human. Please try again."))
	return True
