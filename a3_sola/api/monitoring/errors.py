# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Error capture with context, and with the customer's data taken out of it.

A stack trace containing a GSTIN, a consumer number or a payment reference, sent to an
external error service, is a data leak - and it is the kind nobody notices because the
trace looks like a trace. Redaction happens here, before anything leaves.

Grouping matters as much as redaction. One recurring failure repeated four thousand times
drowns the one that happened once, and the one that happened once is usually the
interesting one.
"""

import hashlib
import re

import frappe
from frappe.utils import now_datetime

#: Patterns whose *value* must never appear in a captured error.
#:
#: Deliberately specific to what this product holds. A generic redactor either misses
#: these or redacts so much that the trace stops being useful.
REDACTIONS = (
	# GSTIN: 2 digits, PAN, entity digit, Z, checksum.
	(re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z]\w\b"), "[GSTIN]"),
	(re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"), "[PAN]"),
	(re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"), "[AADHAAR]"),
	# Razorpay identifiers - order, payment, mandate, refund.
	(re.compile(r"\b(?:order|pay|token|sub|inv|rfnd)_[A-Za-z0-9]{10,}\b"), "[GATEWAY-REF]"),
	(re.compile(r"\brzp_(?:live|test)_[A-Za-z0-9]+\b"), "[GATEWAY-KEY]"),
	# KSEB consumer number: 13 digits.
	(re.compile(r"\b\d{13}\b"), "[CONSUMER-NO]"),
	# Bank account and IFSC.
	(re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"), "[IFSC]"),
	(re.compile(r"\b\d{9,18}\b(?=\s*(?:account|a/c|acct))", re.IGNORECASE), "[ACCOUNT]"),
	# Email and phone.
	(re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
	(re.compile(r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b"), "[PHONE]"),
	# Anything explicitly labelled a secret.
	(re.compile(r"""((?:password|secret|token|api_key)["']?\s*[:=]\s*["']?)[^\s"',}]+""",
	            re.IGNORECASE), r"\1[REDACTED]"),
)


def redact(text):
	"""Remove customer data and credentials from a string, keeping its shape.

	The placeholders are deliberately visible: an engineer reading `[GSTIN]` knows a GSTIN
	was there, which is usually all the trace needed it for.
	"""
	if not text:
		return text
	out = str(text)
	for pattern, replacement in REDACTIONS:
		out = pattern.sub(replacement, out)
	return out


def fingerprint(traceback_text):
	"""A stable identity for "the same failure", so repeats group instead of drowning.

	Built from the exception type and the last few frames' file and function - not the
	line numbers, which shift on every edit, and not the message, which usually carries
	the very identifiers that make each occurrence look unique.
	"""
	if not traceback_text:
		return "unknown"
	frames = re.findall(r'File "([^"]+)", line \d+, in (\S+)', str(traceback_text))
	tail = frames[-4:]
	exception = re.findall(r"^(\w+(?:Error|Exception)):", str(traceback_text), re.M)
	basis = "|".join(f"{f.split('/')[-1]}:{n}" for f, n in tail)
	basis += "|" + (exception[-1] if exception else "")
	return hashlib.sha256(basis.encode()).hexdigest()[:16]


def context():
	"""Who and what, without who they are.

	The user is hashed rather than named: knowing that one user hits an error a hundred
	times is the useful part, and knowing which person that is rarely is.
	"""
	user = frappe.session.user if frappe.session else None
	tenant = None
	try:
		from a3_sola.api.entitlements import TENANT_FIELD

		if user and user not in ("Guest", "Administrator"):
			tenant = frappe.db.get_value("User", user, TENANT_FIELD)
	except Exception:
		pass
	request = getattr(frappe.local, "request", None)
	return {
		"user_hash": hashlib.sha256((user or "").encode()).hexdigest()[:12] if user else None,
		"is_guest": user == "Guest",
		"tenant": tenant,
		"path": getattr(request, "path", None) if request else None,
		"method": getattr(request, "method", None) if request else None,
		"site": frappe.local.site if hasattr(frappe.local, "site") else None,
		"time": str(now_datetime()),
	}


def capture(title, traceback_text=None, extra=None):
	"""Record an error, redacted, grouped and with context. Returns the group id."""
	traceback_text = traceback_text or frappe.get_traceback()
	group = fingerprint(traceback_text)
	payload = {
		"group": group,
		"context": context(),
		"extra": {k: redact(v) for k, v in (extra or {}).items()},
	}
	body = redact(traceback_text)
	frappe.log_error(
		title=f"[{group}] {redact(title)}"[:140],
		message=f"{frappe.as_json(payload)}\n\n{body}",
	)
	return group


def scrub_existing(limit=500):
	"""Redact what is already in the Error Log.

	Run once before pointing an external error service at this site. Traces written before
	the redactor existed still carry whatever was in them.
	"""
	changed = 0
	for row in frappe.get_all("Error Log", fields=["name", "error"], limit=limit,
	                          order_by="creation desc"):
		cleaned = redact(row.error or "")
		if cleaned != row.error:
			frappe.db.set_value("Error Log", row.name, "error", cleaned,
			                    update_modified=False)
			changed += 1
	frappe.db.commit()
	return {"scanned": limit, "redacted": changed}


def groups(limit=20, hours=168):
	"""The recurring failures, largest group first - the alert-fatigue view."""
	from frappe.utils import add_to_date

	since = add_to_date(now_datetime(), hours=-hours)
	counts = {}
	for row in frappe.get_all("Error Log", filters={"creation": [">", since]},
	                          fields=["name", "method", "creation"], limit=5000,
	                          order_by="creation desc"):
		match = re.match(r"^\[([0-9a-f]{16})\]\s*(.*)$", row.method or "")
		key = match.group(1) if match else (row.method or "")[:60]
		label = match.group(2) if match else (row.method or "")[:60]
		entry = counts.setdefault(key, {"group": key, "title": label, "count": 0,
		                                "latest": row.creation})
		entry["count"] += 1
	return sorted(counts.values(), key=lambda r: -r["count"])[:limit]


def purge_old(days=30):
	"""Error Log retention. It has none by default, and on this site it grew to 165 MB -
	half the database - which is both a disk problem and a way to hide the signal."""
	from frappe.utils import add_days, today

	cutoff = add_days(today(), -int(days))
	deleted = frappe.db.sql(
		"delete from `tabError Log` where creation < %s", (cutoff,)
	)
	frappe.db.commit()
	return {"cutoff": str(cutoff), "deleted": deleted}
