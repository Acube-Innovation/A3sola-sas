# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Which document each field was read from: the proof of a customer's name, number or bank
details.

When a KSEB bill, an Aadhaar card, a passbook or cheque, an approval letter or the portal's
acknowledgement is read (OCR) into a form, the page notes under each field it filled where
the value came from - "From Aadhaar card" - and keeps that in the hidden `a3s_read_from`
field as {fieldname: document}. A field typed over by hand loses its note. The form posts it
with everything else, and it is saved here, on the record, so the note is there next time.
"""

import json

FIELD = "a3s_read_from"
#: The documents a field can be read from, as the page names them.
DOCUMENTS = ("KSEB bill", "Aadhaar card", "Bank proof", "Bank passbook", "Cancelled cheque", "Approval letter",
	"Portal acknowledgement")


def set_posted(doc, values):
	"""The record's read-from notes, from what the form posted: only fields of this record that
	hold a value, and only documents the page reads. Not posted, nothing changes."""
	if FIELD not in (values or {}) or not doc.meta.get_field(FIELD):
		return
	try:
		posted = json.loads(values.get(FIELD) or "{}")
	except (TypeError, ValueError):
		return
	if not isinstance(posted, dict):
		return
	notes = {k: v for k, v in posted.items() if isinstance(k, str) and v in DOCUMENTS and k != FIELD
		and doc.meta.get_field(k) and doc.get(k) not in (None, "")}
	doc.set(FIELD, json.dumps(notes, sort_keys=True) if notes else None)


def notes(doc):
	"""The record's notes as a dict."""
	try:
		value = json.loads(doc.get(FIELD) or "{}")
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}
