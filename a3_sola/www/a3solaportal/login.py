# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal sign-in page.

Guest-only by construction: an already-authenticated visitor is sent on rather than
shown a form they do not need. The page itself holds no authentication logic - the
credentials go to Frappe's own `/api/method/login`, so rate limiting, account lockout
and password policy stay in one place instead of being reimplemented here.
"""

import frappe

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Sign in"
	context.redirect_to = safe_redirect(frappe.form_dict.get("redirect-to"))

	if frappe.session.user != "Guest":
		# Already signed in, so this form has nothing to offer. 302 rather than Frappe's
		# default 301: the redirect is conditional on session state, and a permanent one
		# would be cached and keep sending the visitor to /app after they log out.
		frappe.local.flags.redirect_location = context.redirect_to or "/a3solaportal/dashboard"
		raise frappe.Redirect(302)

	return context


def safe_redirect(target):
	"""Return `target` only if it is a path on this site.

	Anything else - an absolute URL, a protocol-relative `//evil.example`, a back-slash
	variant that some browsers normalise to one - is discarded rather than corrected.
	A login page that forwards to an attacker-supplied address is a phishing primitive,
	and the cost of being wrong here is far higher than the cost of dropping a redirect.
	"""
	if not target or not isinstance(target, str):
		return ""
	target = target.strip()
	if not target.startswith("/"):
		return ""
	if target.startswith("//") or target.startswith("/\\"):
		return ""
	return target
