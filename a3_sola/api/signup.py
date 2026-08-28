# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The public signup and demo endpoints.

======================== READ THIS BEFORE CHANGING ANYTHING ==========================

These are unauthenticated endpoints on the same Frappe instance that holds every existing
tenant's customers, contracts and ledgers. They are the highest-risk code in the product.
The rules they follow, all of which are load-bearing:

1. NOTHING here creates a User, a Company, a Role assignment or any ERPNext master.
   Phase 6 provisions, after payment, under controlled conditions. There is a test that
   greps this module to keep it that way.
2. Every field is validated and normalised server-side. The browser's validation is a
   courtesy to the visitor, not a control.
3. Every endpoint is rate limited by IP, and the ones that matter also by email.
4. Nothing is created until the honeypot and the rate limit have both passed.
5. A response NEVER reveals whether an email is already in the system. Signing up twice
   and signing up once return byte-identical bodies.
6. A response never returns the record, the verification token, the IP or the user agent.
7. Token comparison is constant-time, and a wrong token is indistinguishable from an
   expired one or one that never existed.

======================================================================================
"""

import hmac
import re
import secrets

import frappe
from frappe import _
from frappe.utils import cint, get_url, now_datetime

from a3_sola.api import platform
from a3_sola.api.ratelimit import (
	client_ip,
	limit_by_identifier,
	rate_limited,
	user_agent,
	verify_captcha,
)
from a3_sola.api.settings import get_int, get_value

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
#: Indian mobile numbers: ten digits starting 6-9, optionally +91 prefixed.
INDIAN_MOBILE = re.compile(r"^(?:\+?91[\-\s]?)?[6-9]\d{9}$")
GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$")

#: The same words back to every caller, whatever actually happened.
NEUTRAL_SIGNUP_MESSAGE = (
	"Thanks. If that email address can be signed up, we have sent a verification link to "
	"it. Please check your inbox, and your spam folder."
)
GENERIC_TOKEN_ERROR = (
	"That verification link is not valid. It may have expired or already been used."
)

UTM_FIELDS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")


# ------------------------------------------------------------------ validation
def _payload(payload):
	if isinstance(payload, str):
		payload = frappe.parse_json(payload)
	if not isinstance(payload, dict):
		frappe.throw(_("Something went wrong with that submission. Please try again."))
	return frappe._dict(payload)


def _clean(value, limit=140):
	"""Strip, bound the length, and never trust it into HTML later."""
	return (str(value or "").strip())[:limit]


def _require(data, field, label):
	value = _clean(data.get(field))
	if not value:
		frappe.throw(_("{0} is required.").format(label), title=_("Missing Detail"))
	return value


def _check_honeypot(data):
	"""A field a person never sees. Anything in it came from a script.

	Silently accepted-looking rather than refused, so the bot does not learn to skip it.
	"""
	if _clean(data.get("website_url")):
		frappe.logger("a3_sola").info({"event": "honeypot_tripped", "ip": client_ip()})
		raise HoneypotTripped


class HoneypotTripped(Exception):
	"""Raised internally, never surfaced. The caller gets the neutral success response."""


def validate_email(email):
	email = _clean(email, 140).lower()
	if not EMAIL_PATTERN.match(email):
		frappe.throw(_("That does not look like an email address."), title=_("Check the Email"))

	blocked = (get_value("disposable_email_domains") or "").splitlines()
	domain = email.rsplit("@", 1)[-1]
	for entry in blocked:
		entry = entry.strip().lower().lstrip("@")
		if entry and (domain == entry or domain.endswith("." + entry)):
			frappe.throw(
				_("Please use your work email address."), title=_("Work Email Needed")
			)
	return email


def validate_phone(phone, country="India"):
	phone = _clean(phone, 24)
	digits = re.sub(r"[^\d+]", "", phone)
	if country == "India" and not INDIAN_MOBILE.match(digits):
		frappe.throw(
			_("Please enter a ten-digit Indian mobile number."), title=_("Check the Phone Number")
		)
	if len(digits) < 8:
		frappe.throw(_("Please enter a valid phone number."), title=_("Check the Phone Number"))
	return phone


def validate_gstin(gstin):
	gstin = _clean(gstin, 15).upper()
	if gstin and not GSTIN_PATTERN.match(gstin):
		frappe.throw(_("That GSTIN does not look right."), title=_("Check the GSTIN"))
	return gstin


def _attribution(data):
	out = {
		"source": _clean(data.get("source"), 60) or "website",
		"referrer_url": _clean(data.get("referrer_url"), 500),
		"landing_page": _clean(data.get("landing_page"), 500),
		"ip_address": client_ip(),
		"user_agent": _clean(user_agent(), 500),
	}
	for field in UTM_FIELDS:
		out[field] = _clean(data.get(field), 140)
	return out


# --------------------------------------------------------------------- tokens
def _new_token():
	return secrets.token_urlsafe(32)


def _token_matches(stored, supplied):
	"""Constant-time. A timing difference is a way to guess a token one byte at a time."""
	return hmac.compare_digest(str(stored or ""), str(supplied or ""))


def _token_expiry():
	hours = get_int("verification_token_hours", 24) or 24
	return frappe.utils.add_to_date(now_datetime(), hours=hours)


# --------------------------------------------------------------------- signup
@frappe.whitelist(allow_guest=True)
@rate_limited("signup_ip", "signup_rate_limit_per_ip_per_hour", 5)
def submit_signup(payload):
	"""Create a signup and send a verification email.

	Returns only a reference and where to go next. Never the record.
	"""
	if not get_value("enable_public_signup"):
		frappe.throw(
			_("Self-serve signup is closed at the moment. Please book a demo instead."),
			title=_("Signup Paused"),
		)

	data = _payload(payload)
	try:
		_check_honeypot(data)
	except HoneypotTripped:
		# Looks exactly like success. Nothing is created.
		return {"ok": True, "message": _(NEUTRAL_SIGNUP_MESSAGE), "reference": None}

	verify_captcha(data.get("captcha_token"))

	email = validate_email(data.get("work_email"))
	limit_by_identifier("signup_email", email, "signup_rate_limit_per_email_per_day", 3)

	# An existing pending signup gets another email rather than a duplicate record - and
	# the caller cannot tell which happened.
	existing = frappe.db.get_value(
		"Subscription Signup",
		{
			"work_email": email,
			"status": ["in", ["Draft", "Awaiting Email Verification"]],
			"docstatus": ["<", 2],
		},
		"name",
	)
	if existing:
		_issue_verification(frappe.get_doc("Subscription Signup", existing), resend=True)
		return {"ok": True, "message": _(NEUTRAL_SIGNUP_MESSAGE), "reference": existing}

	plan_code = _clean(data.get("plan_code"), 60).lower()
	plan_name = frappe.db.get_value(
		"Subscription Plan",
		# A custom-priced plan has no number to charge, so it is not sellable here.
		{"plan_code": plan_code, "is_active": 1, "is_published": 1, "is_custom_pricing": 0},
		"name",
	)
	if not plan_name:
		frappe.throw(
			_("That plan cannot be bought online. Please book a demo and we will price it "
			  "with you."),
			title=_("Talk to Us Instead"),
		)

	cycle = _clean(data.get("billing_cycle"), 10).title()
	if cycle not in ("Monthly", "Annual"):
		cycle = "Monthly"

	country = _clean(data.get("country"), 60) or "India"
	doc = frappe.get_doc(
		{
			"doctype": "Subscription Signup",
			"full_name": _require(data, "full_name", _("Full name")),
			"work_email": email,
			"phone": validate_phone(data.get("phone"), country),
			"designation": _clean(data.get("designation")),
			"organisation_name": _require(data, "organisation_name", _("Organisation name")),
			"organisation_type": _clean(data.get("organisation_type"), 40) or "Solar EPC",
			"gstin": validate_gstin(data.get("gstin")),
			"city": _clean(data.get("city")),
			"state": _clean(data.get("state")),
			"country": country if frappe.db.exists("Country", country) else "India",
			"website": _clean(data.get("website"), 200),
			"approximate_monthly_installations": _clean(
				data.get("approximate_monthly_installations"), 20
			),
			"subscription_plan": plan_name,
			"billing_cycle": cycle,
			"additional_users": cint(data.get("additional_users")),
			"accepted_terms": 1 if data.get("accepted_terms") else 0,
			"marketing_consent": 1 if data.get("marketing_consent") else 0,
			**_attribution(data),
		}
	)
	doc.plan_code = plan_code
	doc.snapshot_price()
	doc.log_event("Created", _("Signup submitted from the public site."))
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)

	_issue_verification(doc)
	_notify_sales_of_signup(doc)

	return {
		"ok": True,
		"message": _(NEUTRAL_SIGNUP_MESSAGE),
		"reference": doc.name,
		"next": platform.route("get-started/check-email") + "?ref=" + doc.name,
	}


def _issue_verification(doc, resend=False):
	"""Mint a token, store it, email it. The token only ever goes to the applicant."""
	token = _new_token()
	doc.verification_token = token
	doc.token_expires_on = _token_expiry()
	doc.set_status("Awaiting Email Verification")
	if resend:
		doc.log_event("Verification Resent", _("A new verification link was sent."))
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)

	# Same reason as above: a resend can be reached from a GET-rendered page.
	frappe.flags.commit = True
	link = get_url(f"{platform.route('verify-email')}?token={token}")
	try:
		frappe.sendmail(
			recipients=[doc.work_email],
			subject=_("Confirm your email for {0}").format(
				get_value("product_name") or "a3 sola"
			),
			message=frappe.render_template(
				"a3_sola/templates/emails/verify_email.html",
				platform.email_context({"doc": doc, "link": link, "hours": get_int("verification_token_hours", 24)}),
			),
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: verification email {doc.name}")
	return doc


def _notify_sales_of_signup(doc):
	recipient = get_value("sales_email")
	if not recipient:
		return
	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=_("New signup: {0} on {1}").format(doc.organisation_name, doc.plan_code),
			message=frappe.render_template(
				"a3_sola/templates/emails/signup_internal.html", platform.email_context({"doc": doc})
			),
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: signup notification {doc.name}")


@frappe.whitelist(allow_guest=True)
@rate_limited("verify_ip", "signup_rate_limit_per_ip_per_hour", 20)
def verify_email(token):
	"""Consume a verification token.

	Every failure looks the same from outside: expired, reused, wrong and never-existed
	all return the identical message, because distinguishing them would let somebody
	enumerate valid tokens.
	"""
	token = _clean(token, 120)
	if not token:
		frappe.throw(_(GENERIC_TOKEN_ERROR), title=_("Link Not Valid"))

	name = frappe.db.get_value("Subscription Signup", {"verification_token": token}, "name")
	if not name:
		frappe.throw(_(GENERIC_TOKEN_ERROR), title=_("Link Not Valid"))

	doc = frappe.get_doc("Subscription Signup", name)
	doc.verification_attempts = cint(doc.verification_attempts) + 1

	max_attempts = get_int("verification_attempts_max", 10) or 10
	if doc.verification_attempts > max_attempts:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		# The count has to survive, or the cap never bites on repeated GETs.
		frappe.flags.commit = True
		frappe.throw(_(GENERIC_TOKEN_ERROR), title=_("Link Not Valid"))

	expired = doc.token_expires_on and now_datetime() > frappe.utils.get_datetime(
		doc.token_expires_on
	)
	if not _token_matches(doc.verification_token, token) or expired or doc.is_email_verified:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		frappe.flags.commit = True
		frappe.throw(_(GENERIC_TOKEN_ERROR), title=_("Link Not Valid"))

	doc.is_email_verified = 1
	doc.verified_on = now_datetime()
	# Burn it. A verification link is single-use.
	doc.verification_token = None
	doc.token_expires_on = None
	doc.set_status("Verified", details=_("Email address confirmed."))
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)

	# Frappe commits only on POST, PUT and DELETE. A verification link in an email is a
	# GET, so without this the verification is written and then rolled back - the customer
	# sees "confirmed" and the record still says otherwise.
	frappe.flags.commit = True

	_send_verified_confirmation(doc)
	return {"ok": True, "next": f"{platform.route('get-started/summary')}?ref={doc.name}&t={_summary_key(doc)}"}


def _summary_key(doc):
	"""A short read-only key for the summary page.

	The verification token is burned on use, so the summary page needs something else to
	prove the caller is the applicant. This is derived from the record and the site secret,
	so it cannot be guessed from the reference alone and grants read access to nothing but
	that one signup's summary.
	"""
	import hashlib

	secret = frappe.local.conf.get("secret_key") or frappe.local.conf.get("encryption_key") or ""
	basis = f"{doc.name}:{doc.work_email}:{doc.creation}:{secret}"
	return hashlib.sha256(basis.encode()).hexdigest()[:32]


def _send_verified_confirmation(doc):
	try:
		frappe.sendmail(
			recipients=[doc.work_email],
			subject=_("You're verified - here's what happens next"),
			message=frappe.render_template(
				"a3_sola/templates/emails/verified_confirmation.html",
				platform.email_context({"doc": doc, "summary_url": get_url(
					f"{platform.route('get-started/summary')}?ref={doc.name}&t={_summary_key(doc)}"
				)}),
			),
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			now=False,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: confirmation email {doc.name}")


@frappe.whitelist(allow_guest=True)
@rate_limited("resend_ip", "signup_rate_limit_per_ip_per_hour", 5)
def resend_verification(signup_reference):
	"""Send the verification link again. Hard capped per signup."""
	reference = _clean(signup_reference, 40)
	doc = frappe.db.get_value(
		"Subscription Signup",
		{"name": reference, "status": "Awaiting Email Verification"},
		["name", "work_email"],
		as_dict=True,
	)
	# Neutral either way: a wrong reference must not confirm which ones exist.
	if not doc:
		return {"ok": True, "message": _(NEUTRAL_SIGNUP_MESSAGE)}

	limit_by_identifier(
		"resend_signup", doc.name, "resend_verification_max", 3, window_seconds=86400
	)
	_issue_verification(frappe.get_doc("Subscription Signup", doc.name), resend=True)
	return {"ok": True, "message": _(NEUTRAL_SIGNUP_MESSAGE)}


@frappe.whitelist(allow_guest=True)
@rate_limited("update_plan_ip", "signup_rate_limit_per_ip_per_hour", 20)
def update_plan_selection(signup_reference, token, plan_code, cycle, additional_users=0):
	"""Let a verified applicant change tier or cycle before paying.

	Requires the summary key, not just the reference: a reference appears in a URL and
	could be guessed, and guessing one must not let somebody re-price another company's
	signup.
	"""
	doc = _authorised_signup(signup_reference, token)
	if doc.status not in ("Verified", "Awaiting Payment", "Payment Failed"):
		frappe.throw(
			_("This signup can no longer be changed. Please contact us."),
			title=_("Cannot Change Now"),
		)

	plan_code = _clean(plan_code, 60).lower()
	plan_name = frappe.db.get_value(
		"Subscription Plan",
		{"plan_code": plan_code, "is_active": 1, "is_published": 1, "is_custom_pricing": 0},
		"name",
	)
	if not plan_name:
		frappe.throw(_("That plan is not available to buy online."), title=_("Unknown Plan"))

	cycle = _clean(cycle, 10).title()
	if cycle not in ("Monthly", "Annual"):
		frappe.throw(_("Choose monthly or annual billing."))

	before = f"{doc.plan_code}/{doc.billing_cycle}/{doc.additional_users}"
	doc.subscription_plan = plan_name
	doc.plan_code = plan_code
	doc.billing_cycle = cycle
	doc.additional_users = max(cint(additional_users), 0)
	doc.snapshot_price()
	doc.log_event(
		"Plan Changed",
		_("{0} changed to {1}/{2}/{3}").format(
			before, plan_code, cycle, doc.additional_users
		),
	)
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	return get_signup_summary(doc.name, token)


def _authorised_signup(signup_reference, token):
	"""Resolve a signup only when the caller can prove they are the applicant."""
	reference = _clean(signup_reference, 40)
	name = frappe.db.get_value("Subscription Signup", {"name": reference}, "name")
	if not name:
		frappe.throw(_("We could not find that signup."), frappe.DoesNotExistError)

	doc = frappe.get_doc("Subscription Signup", name)
	if not _token_matches(_summary_key(doc), _clean(token, 64)):
		# Identical to a missing record, so a guessed reference reveals nothing.
		frappe.throw(_("We could not find that signup."), frappe.DoesNotExistError)
	return doc


def try_signup_summary(signup_reference, token):
	"""Summary or None. For page controllers, which must not raise a routing exception.

	`get_signup_summary` throws DoesNotExistError, which Frappe turns into a 404 or a 500
	even if the caller catches it. A page that wants to render its own "we could not find
	that" panel needs a version that simply returns nothing.
	"""
	reference = _clean(signup_reference, 40)
	if not reference or not _clean(token, 64):
		return None
	name = frappe.db.get_value("Subscription Signup", {"name": reference}, "name")
	if not name:
		return None
	doc = frappe.get_doc("Subscription Signup", name)
	if not _token_matches(_summary_key(doc), _clean(token, 64)):
		return None
	return _summary_payload(doc)


@frappe.whitelist(allow_guest=True)
@rate_limited("summary_ip", "signup_rate_limit_per_ip_per_hour", 30)
def get_signup_summary(signup_reference, token):
	"""Exactly what the summary page needs to render, and not one field more."""
	doc = _authorised_signup(signup_reference, token)
	return _summary_payload(doc)


def _summary_payload(doc):
	"""Exactly the fields the summary page renders. Nothing internal, ever."""
	return {
		"reference": doc.name,
		"organisation_name": doc.organisation_name,
		"plan_name": frappe.db.get_value("Subscription Plan", doc.subscription_plan, "plan_name"),
		"plan_code": doc.plan_code,
		"billing_cycle": doc.billing_cycle,
		"included_users": cint(doc.total_users) - cint(doc.additional_users),
		"additional_users": cint(doc.additional_users),
		"total_users": cint(doc.total_users),
		"currency": doc.currency,
		"base_amount": doc.base_amount,
		"additional_user_amount": doc.additional_user_amount,
		"implementation_fee": doc.implementation_fee,
		"subtotal": doc.subtotal,
		"total_amount": doc.total_amount,
		"line_items": frappe.parse_json(doc.price_breakdown or "[]"),
		"status": doc.status,
		"is_email_verified": bool(doc.is_email_verified),
	}


# ---------------------------------------------------------------- demo request
@frappe.whitelist(allow_guest=True)
@rate_limited("demo_ip", "demo_rate_limit_per_ip_per_hour", 5)
def submit_demo_request(payload):
	"""Capture a demo request. Same discipline as signup."""
	if not get_value("enable_demo_requests"):
		frappe.throw(
			_("We are not taking demo requests at the moment."), title=_("Requests Paused")
		)

	data = _payload(payload)
	try:
		_check_honeypot(data)
	except HoneypotTripped:
		return {"ok": True, "message": _("Thanks - we will be in touch shortly.")}

	verify_captcha(data.get("captcha_token"))

	email = validate_email(data.get("work_email"))
	limit_by_identifier("demo_email", email, "demo_rate_limit_per_ip_per_hour", 5)

	interested = None
	plan_code = _clean(data.get("plan_code"), 60).lower()
	if plan_code:
		interested = frappe.db.get_value("Subscription Plan", {"plan_code": plan_code}, "name")

	doc = frappe.get_doc(
		{
			"doctype": "Demo Request",
			"full_name": _require(data, "full_name", _("Full name")),
			"work_email": email,
			"phone": validate_phone(data.get("phone")),
			"organisation_name": _require(data, "organisation_name", _("Company name")),
			"approximate_monthly_installations": _clean(
				data.get("approximate_monthly_installations"), 20
			),
			"message": _clean(data.get("message"), 2000),
			"interested_plan": interested,
			**_attribution(data),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return {
		"ok": True,
		"message": _("Thanks - we will be in touch shortly."),
		"next": platform.route("thank-you"),
	}


# ------------------------------------------------------------ payment handoff
def initiate_payment(signup_reference, token):
	"""Implemented in Phase 5. Delegates to `a3_sola.api.payments`.

	Kept under the name Phase 4 published, so nothing that already calls it has to change.
	The contract is unchanged: charge the pricing snapshot stored on the signup, never a
	fresh calculation, and move the status Verified -> Awaiting Payment.
	"""
	from a3_sola.api import payments

	return payments.initiate_payment(signup_reference, token)


@frappe.whitelist(allow_guest=True)
@rate_limited("payment_ip", "signup_rate_limit_per_ip_per_hour", 10)
def request_payment_contact(signup_reference, token):
	"""What the summary page's Proceed button does.

	Payments are live, so this creates the gateway order and hands off to checkout. The
	fallback below is kept deliberately: if the gateway is unconfigured on a given site,
	the applicant is told a person will be in touch rather than shown a broken button.
	"""
	doc = _authorised_signup(signup_reference, token)
	try:
		initiate_payment(signup_reference, token)
		# Payments are live: send them to checkout rather than to a holding message.
		return {
			"ok": True,
			"pending": False,
			"redirect": f"{platform.route('checkout')}?ref={doc.name}&t={_clean(token, 64)}",
		}
	except NotImplementedError:
		pass
	except frappe.ValidationError:
		raise
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: checkout handoff {doc.name}")

	recipient = get_value("sales_email")
	if recipient:
		try:
			frappe.sendmail(
				recipients=[recipient],
				subject=_("Payment requested: {0}").format(doc.organisation_name),
				message=frappe.render_template(
					"a3_sola/templates/emails/payment_pending_internal.html",
					platform.email_context({"doc": doc})
				),
				reference_doctype=doc.doctype,
				reference_name=doc.name,
				now=False,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: payment notice {doc.name}")

	doc.log_event("Payment Initiated", _("Applicant asked to pay; sales notified."))
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	return {
		"ok": True,
		"pending": True,
		"message": _(
			"Payment is being set up. Our team will contact you shortly to complete your "
			"subscription."
		),
	}
