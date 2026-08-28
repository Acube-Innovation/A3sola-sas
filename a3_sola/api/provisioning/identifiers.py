# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Turning what an applicant typed into something safe to build a workspace from.

The applicant controls the organisation name. That string ends up near an ERPNext company
abbreviation, a set of account names, a naming series and - under multi-site - a hostname.
None of those tolerate arbitrary input, and several of them are hard to change afterwards.

The rule this module enforces is narrow and deliberately boring: **derive, never accept**.
Nothing the applicant typed is used directly. A tenant code is *derived* from the name by
an allowlist - lowercase letters, digits and hyphens, nothing else - and everything
downstream is built from the derived code, not from the original string. A name that
survives the derivation with nothing left gets a generated code rather than an error,
because refusing a legitimate customer over their punctuation is a worse outcome than a
slightly opaque identifier.
"""

import re
import unicodedata

import frappe
from frappe import _

from a3_sola.api.settings import get_int, get_value

MIN_LENGTH = 3
MAX_LENGTH = 20

#: Fallback list, used when Settings has been emptied. Kept in code as well as in Settings
#: because an empty blocklist is the kind of configuration mistake that is only noticed
#: when someone registers the tenant code `admin`.
BUILTIN_RESERVED = {
	"admin", "administrator", "api", "app", "assets", "billing", "blog", "cdn", "demo",
	"dev", "docs", "erpnext", "files", "frappe", "ftp", "help", "imap", "login", "mail",
	"platform", "portal", "root", "shop", "signup", "smtp", "sola", "a3sola", "staging",
	"static", "status", "support", "system", "tenant", "test", "www", "account",
}


def reserved_codes():
	configured = get_value("reserved_tenant_codes") or ""
	tokens = re.split(r"[,\n\r\t ]+", configured)
	return BUILTIN_RESERVED | {t.strip().lower() for t in tokens if t.strip()}


def sanitise_name(value, limit=140):
	"""A display name safe to store and print.

	Strips control characters and collapses whitespace. It does NOT strip punctuation -
	"M/s Sunrise Energy & Co." is a real company name and mangling it would be wrong. What
	uses this string is display; what uses the derived code is everything structural.
	"""
	text = unicodedata.normalize("NFKC", str(value or ""))
	text = "".join(ch for ch in text if ch == "\n" or unicodedata.category(ch)[0] != "C")
	text = re.sub(r"\s+", " ", text).strip()
	return text[:limit]


def slugify(value):
	"""Derive a candidate tenant code. Allowlist only - never a blocklist.

	Transliterates what it can (so "Sūrya" becomes "surya" rather than vanishing), drops
	everything else, and returns "" when nothing usable survives. A blocklist here would
	be wrong: the set of characters that break ERPNext account naming, URL parsing and
	shell quoting is not one anybody can enumerate correctly.
	"""
	text = unicodedata.normalize("NFKD", str(value or ""))
	text = text.encode("ascii", "ignore").decode("ascii").lower()
	text = re.sub(r"[^a-z0-9]+", "-", text)
	text = re.sub(r"-{2,}", "-", text).strip("-")
	return text[:MAX_LENGTH].strip("-")


def is_valid_code(code):
	return bool(re.fullmatch(r"[a-z0-9]([a-z0-9-]{1,18})[a-z0-9]", code or ""))


def validate_code(code):
	"""Everything a tenant code must satisfy, in one place, with a reason for each."""
	if not code:
		frappe.throw(_("A tenant code is required."), title=_("Invalid Tenant Code"))
	if len(code) < MIN_LENGTH or len(code) > MAX_LENGTH:
		frappe.throw(
			_("A tenant code must be between {0} and {1} characters.").format(MIN_LENGTH, MAX_LENGTH),
			title=_("Invalid Tenant Code"),
		)
	if not is_valid_code(code):
		frappe.throw(
			_("A tenant code may contain only lowercase letters, digits and hyphens, and "
			  "must start and end with a letter or digit."),
			title=_("Invalid Tenant Code"),
		)
	if code in reserved_codes():
		frappe.throw(
			_("The tenant code {0} is reserved and cannot be used.").format(frappe.bold(code)),
			title=_("Reserved Tenant Code"),
		)
	return code


def code_is_taken(code, exclude_tenant=None):
	"""Is this tenant code already held?

	Only tenant codes are checked here, and that is deliberate. An earlier version also
	rejected a code whose derived company abbreviation was taken - which sounds prudent
	until you notice that the abbreviation is a four-character truncation, so `sunrise`,
	`sunrise-2`, `sunrise-3` and every other disambiguation all derive `SUNR`. Every
	candidate then looks taken and the loop runs to exhaustion on the second customer with
	a similar name.

	The two namespaces are separate and stay separate: tenant codes are made unique here,
	company abbreviations by `free_abbreviation` at the moment the company is created.
	"""
	filters = {"tenant_code": code}
	if exclude_tenant:
		filters["name"] = ["!=", exclude_tenant]
	return bool(frappe.db.exists("Tenant", filters))


def generate_code(organisation_name, exclude_tenant=None):
	"""Derive a free, valid tenant code from the organisation name, deterministically.

	Disambiguation is by an ascending numeric suffix rather than a random one, so the same
	inputs in the same order always produce the same codes - which is what makes a test of
	this function meaningful and a re-run of provisioning predictable.
	"""
	base = slugify(organisation_name)
	if len(base) < MIN_LENGTH:
		# Nothing usable survived - a name written entirely in a non-Latin script, or in
		# punctuation. Derive from a hash of the original so it is still deterministic.
		digest = frappe.generate_hash(sanitise_name(organisation_name) or "tenant", 8)
		base = f"t{digest}"[:MAX_LENGTH]
	base = base.strip("-")[:MAX_LENGTH].strip("-")
	if len(base) < MIN_LENGTH:
		base = (base + "org")[:MAX_LENGTH]

	reserved = reserved_codes()
	candidate = base
	suffix = 1
	while candidate in reserved or code_is_taken(candidate, exclude_tenant):
		suffix += 1
		tail = f"-{suffix}"
		candidate = f"{base[: MAX_LENGTH - len(tail)]}{tail}".strip("-")
		if suffix > 999:
			# Vanishingly unlikely, but a silent infinite loop inside a webhook worker
			# would be worse than a loud failure.
			frappe.throw(
				_("Could not derive a free tenant code from {0}.").format(organisation_name),
				title=_("Tenant Code Exhausted"),
			)
	return candidate


def abbreviation_for(code):
	"""The ERPNext company abbreviation for a tenant code.

	Uppercase, hyphens removed, truncated to the configured length. ERPNext puts this on
	the end of every account name, so it wants to be short and stable.
	"""
	length = get_int("company_abbr_length", 4) or 4
	letters = re.sub(r"[^a-z0-9]", "", (code or "").lower()).upper()
	return (letters[:length] or "TNT")


def free_abbreviation(code):
	"""An abbreviation nobody else holds, derived from the code."""
	base = abbreviation_for(code)
	candidate = base
	suffix = 1
	while frappe.db.exists("Company", {"abbr": candidate}):
		suffix += 1
		tail = str(suffix)
		candidate = f"{base[: max(1, len(base) - len(tail))]}{tail}"
		if suffix > 999:
			frappe.throw(
				_("Could not derive a free company abbreviation from {0}.").format(code),
				title=_("Abbreviation Exhausted"),
			)
	return candidate
