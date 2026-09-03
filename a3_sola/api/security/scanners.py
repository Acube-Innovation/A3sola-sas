# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Scanning for secrets in the code, and for card data and PII in the stored records.

Both run as standing tests rather than as a one-off sweep, because the finding that
matters is the one introduced next month.

THE STORED-DATA SCAN IS THE ONE PEOPLE SKIP. Nobody commits a card number; what happens is
that a gateway's raw webhook payload gets logged verbatim "for debugging", and eighteen
months later the log table holds card metadata nobody meant to keep. Phase 5 redacts those
payloads deliberately, and this is what proves the redaction still works.
"""

import os
import re

import frappe

#: Secrets in source. Deliberately narrow patterns - a scanner that cries wolf gets
#: switched off, and a switched-off scanner finds nothing.
SOURCE_PATTERNS = {
	"razorpay_live_key": re.compile(r"rzp_live_[A-Za-z0-9]{10,}"),
	"razorpay_test_key": re.compile(r"rzp_test_[A-Za-z0-9]{10,}"),
	"aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
	"private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
	"slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
	"github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
	"jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\."),
	"connection_string": re.compile(r"(?:mysql|postgres|postgresql|mongodb)://[^\s\"']+:[^\s\"']+@"),
	"assigned_password": re.compile(
		r"""(?:password|passwd|secret|api_key|apikey|token)\s*=\s*["'][^"'\s]{8,}["']""",
		re.IGNORECASE,
	),
}

#: Card data and identity numbers in STORED records.
DATA_PATTERNS = {
	# 13-19 digits passing Luhn - checked properly below rather than by shape alone.
	"card_pan": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
	"cvv_labelled": re.compile(r"""["']?cvv["']?\s*[:=]\s*["']?\d{3,4}""", re.IGNORECASE),
	"razorpay_secret": re.compile(r"rzp_(?:live|test)_[A-Za-z0-9]{10,}"),
	"aadhaar": re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"),
	"pan_number": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
}

#: Paths that are allowed to contain what looks like a secret, with the reason.
SOURCE_ALLOWLIST = {
	# The starter dataset's password is documented, deliberate and the user's own
	# decision - see docs/STARTER_DATASET.md, which tells them to change it.
	"setup/starter.py": "the documented starter password, by explicit decision",
	# Test fixtures and mock gateways use obvious fake values.
	"tests/": "test fixtures",
	"api/gateways/mock.py": "the mock gateway's fake credentials",
	"api/security/scanners.py": "this file, which contains the patterns themselves",
}


def scan_source(root=None):
	"""Every secret-shaped string in the app's own code."""
	root = root or frappe.get_app_path("a3_sola")
	findings = []
	for base, dirs, files in os.walk(root):
		dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules", ".git")]
		for filename in files:
			if not filename.endswith((".py", ".js", ".json", ".html", ".md", ".txt",
			                          ".yaml", ".yml")):
				continue
			path = os.path.join(base, filename)
			relative = os.path.relpath(path, root)
			try:
				content = open(path, encoding="utf-8", errors="ignore").read()
			except OSError:
				continue
			for label, pattern in SOURCE_PATTERNS.items():
				for match in pattern.finditer(content):
					if label == "assigned_password" and _is_placeholder(match.group(0)):
						continue
					allowed = _allowlisted(relative)
					findings.append({
						"kind": label, "file": relative,
						"line": content[:match.start()].count("\n") + 1,
						"excerpt": _redact(match.group(0)),
						"allowlisted": allowed,
					})
	return findings


#: Values that look like an assigned secret and are obviously not one.
#:
#: A placeholder, an environment reference or a template variable is what documentation and
#: config examples are supposed to contain. Flagging them trains people to ignore the
#: scanner - and the first thing this pattern caught was the redaction placeholder in the
#: monitoring guide, written by the redactor itself.
PLACEHOLDER = re.compile(
	r"^(?:\[[^\]]*\]|<[^>]*>|\$\{[^}]*\}|\{\{[^}]*\}\}|x{3,}|\*{3,}|"
	r"changeme|your[-_].*|placeholder|redacted|example.*|todo|none|null)$",
	re.IGNORECASE,
)


def _is_placeholder(match_text):
	"""Pull the assigned value out of `key = "value"` and judge that, not the whole match."""
	value = re.split(r"[:=]", match_text, maxsplit=1)[-1].strip().strip("\"'")
	return bool(PLACEHOLDER.match(value))


def _allowlisted(relative):
	for prefix, reason in SOURCE_ALLOWLIST.items():
		if relative.startswith(prefix) or prefix in relative:
			return reason
	return None


def _redact(value):
	"""Never print a secret while reporting that a secret exists."""
	text = str(value)
	if len(text) <= 8:
		return "*" * len(text)
	return f"{text[:4]}{'*' * (len(text) - 8)}{text[-4:]}"


def luhn(number):
	digits = [int(d) for d in re.sub(r"\D", "", number)]
	if not 13 <= len(digits) <= 19:
		return False
	checksum, parity = 0, len(digits) % 2
	for index, digit in enumerate(digits):
		if index % 2 == parity:
			digit *= 2
			if digit > 9:
				digit -= 9
		checksum += digit
	return checksum % 10 == 0


#: Tables that hold third-party payloads or free text and are therefore where card data
#: would end up if anything ever logged it verbatim.
SCANNED_TABLES = [
	("Payment Webhook Log", ["raw_payload", "signature", "error_message"]),
	("Payment Transaction", ["raw_response", "gateway_payment_id", "method_detail"]),
	("Payment Order", ["gateway_response", "gateway_order_id"]),
	("Error Log", ["error", "method"]),
	("Scheduled Job Log", ["details"]),
	("Comment", ["content"]),
	("Version", ["data"]),
	("Subscription Event", ["reason", "reason_detail"]),
	("Platform Audit Entry", ["detail"]),
]


def scan_stored_data(limit=500):
	"""Card data, CVVs, live keys and identity numbers in what the app has stored."""
	findings = []
	for doctype, fields in SCANNED_TABLES:
		if not frappe.db.exists("DocType", doctype):
			continue
		available = [f for f in fields if frappe.get_meta(doctype).get_field(f)]
		if not available:
			continue
		try:
			rows = frappe.get_all(doctype, fields=["name"] + available, limit=limit,
			                      order_by="creation desc", ignore_permissions=True)
		except Exception:
			continue
		for row in rows:
			for field in available:
				value = row.get(field)
				if not value:
					continue
				findings.extend(_scan_value(doctype, row["name"], field, str(value)))
	return findings


#: Text around a number that means it is not a card. Thread identifiers, object
#: addresses and line numbers are all long digit runs and a good few are Luhn-valid -
#: the first version of this scanner reported a Python thread id as a card number.
TECHNICAL_CONTEXT = re.compile(
	r"Thread-|object at 0x|File \"|, line \d|Timer\(|pid=|0x[0-9a-f]{6,}|"
	r"timestamp|epoch|nanosecond|_id\b|id=\d",
	re.IGNORECASE,
)

#: The issuer ranges a real card actually starts with. Nothing else is a PAN, whatever
#: Luhn says: Visa 4, Mastercard 51-55 and 2221-2720, Amex 34/37, Discover 6011/65,
#: Diners 300-305/36/38, JCB 35, RuPay 60/65/81/82.
CARD_PREFIXES = re.compile(
	r"^(?:4|5[1-5]|2[2-7]|34|37|6011|65|30[0-5]|36|38|35|60|81|82)"
)


def _scan_value(doctype, name, field, value):
	out = []
	for label, pattern in DATA_PATTERNS.items():
		for match in pattern.finditer(value):
			hit = match.group(0)
			if label == "card_pan" and not _is_a_card(hit, value, match):
				continue
			out.append({
				"kind": label, "doctype": doctype, "name": name, "field": field,
				"excerpt": _redact(hit),
			})
	return out


def _is_a_card(hit, haystack, match):
	"""Three tests, all of which a real PAN passes and almost nothing else does.

	Shape alone is uselessly noisy - order ids, amounts in paise, timestamps and thread
	identifiers are all long digit runs, and roughly one in ten passes Luhn by chance. A
	scanner that reports those gets switched off within a week, and a switched-off scanner
	finds nothing.
	"""
	digits = re.sub(r"\D", "", hit)
	if not luhn(digits):
		return False
	if _is_masked(hit):
		return False  # `**** 1111` is what a gateway is supposed to store
	if not CARD_PREFIXES.match(digits):
		return False  # not an issuer range, so not a card whatever Luhn says
	window = haystack[max(0, match.start() - 90):match.end() + 40]
	return not TECHNICAL_CONTEXT.search(window)


def _is_masked(value):
	"""`XXXXXXXXXXXX1111` and `**** 1111` are what a gateway is supposed to store."""
	return bool(re.search(r"[X*x]{4,}", value))


def scan_password_fields():
	"""Password-type fields must be encrypted at rest and never returned by an API path.

	Checked by reading the raw column: if the stored value equals what `get_password`
	returns, it is not encrypted.
	"""
	from a3_sola import registry

	findings = []
	for doctype in sorted(set(registry.all_doctypes())) + ["A3 Sola Settings"]:
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		password_fields = [f.fieldname for f in meta.fields if f.fieldtype == "Password"]
		if not password_fields:
			continue
		if meta.istable:
			continue
		if meta.issingle:
			for field in password_fields:
				# `order_by=None` because the Singles table has no `modified` column and
				# get_value orders by it unless told otherwise.
				raw = frappe.db.get_value("Singles", {"doctype": doctype, "field": field},
				                          "value", order_by=None)
				if raw and not _looks_encrypted(raw):
					findings.append({
						"kind": "password_not_encrypted", "doctype": doctype,
						"field": field, "excerpt": _redact(raw),
					})
			continue
		for name in frappe.get_all(doctype, pluck="name", limit=20, ignore_permissions=True):
			for field in password_fields:
				raw = frappe.db.get_value(doctype, name, field)
				if raw and not _looks_encrypted(raw):
					findings.append({
						"kind": "password_not_encrypted", "doctype": doctype,
						"name": name, "field": field, "excerpt": _redact(raw),
					})
	return findings


def _looks_encrypted(value):
	"""Frappe stores Password fields in __Auth and leaves the column empty or tokenised."""
	text = str(value)
	if text in ("", "*" * len(text)):
		return True
	# A Fernet token starts with gAAAAA and is long.
	return text.startswith("gAAAAA") or len(text) > 60


#: Raw-SQL sites reviewed and accepted, with why. A table name cannot be a bind
#: parameter, so interpolating one from a hardcoded tuple is the only way to write the
#: query - and it is safe precisely because the value never comes from a request.
REVIEWED_SQL = {
	"api/funnel_jobs.py": (
		"the doctype is interpolated from a literal tuple in the same function; every "
		"value that comes from data is bound with %s"
	),
}


def scan_raw_sql():
	"""Every `frappe.db.sql` call with a formatted string rather than parameters.

	String interpolation into SQL is the finding; `%(name)s` with a dict is not.
	"""
	root = frappe.get_app_path("a3_sola")
	findings = []
	interpolated = re.compile(r"frappe\.db\.sql\(\s*f?[\"']{1,3}[^\"']*?(?:\{|%s\s*%|\+\s*\w)")
	for base, dirs, files in os.walk(root):
		dirs[:] = [d for d in dirs if d not in ("__pycache__", "node_modules")]
		for filename in files:
			if not filename.endswith(".py"):
				continue
			path = os.path.join(base, filename)
			relative = os.path.relpath(path, root)
			content = open(path, encoding="utf-8", errors="ignore").read()
			for match in interpolated.finditer(content):
				snippet = content[match.start():match.start() + 200]
				# An f-string that only interpolates a table name from a literal is a
				# different risk from one interpolating a request value, so the excerpt
				# is reported for a human to judge.
				findings.append({
					"kind": "sql_interpolation", "file": relative,
					"line": content[:match.start()].count("\n") + 1,
					"excerpt": snippet.split("\n")[0][:160],
					"reviewed": REVIEWED_SQL.get(relative),
				})
	return findings


def render_findings(source, stored, passwords, sql):
	lines = [
		"| Scan | Findings | Result |",
		"|---|---|---|",
		f"| Secrets in source | {len([f for f in source if not f['allowlisted']])} "
		f"| {'CLEAN' if not [f for f in source if not f['allowlisted']] else 'FINDINGS'} |",
		f"| Card data / PII in stored records | {len(stored)} "
		f"| {'CLEAN' if not stored else 'FINDINGS'} |",
		f"| Unencrypted password fields | {len(passwords)} "
		f"| {'CLEAN' if not passwords else 'FINDINGS'} |",
		f"| SQL string interpolation | {len(sql)} "
		f"| {'CLEAN' if not sql else 'REVIEW'} |",
	]
	return "\n".join(lines)
