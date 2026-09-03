# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One place to strip what must never reach storage, however it arrived.

FINDING (Phase 8, Medium). Frappe escapes markup on the way into a text field, but it
does not remove control characters - a null byte typed into a public form or a
cancellation reason survives into the database intact.

That matters because those values leave the database again through layers that do not
share Python's view of a string:

* a NUL truncates at the C boundary, so a value validated as `harmless\\x00.php` is
  `harmless` to whatever handles the file
* a carriage return splits an email header, and a bare newline splits a log line
* both break a CSV cell for whoever opens the export

None of it is exploitable on its own. All of it is the kind of thing that turns into a
finding later, and it costs one translate() to prevent.
"""

#: Everything below 0x20 except tab, newline and carriage return, plus DEL.
#: Tab and newline are kept because free text legitimately contains them; CR is kept and
#: normalised by the caller where a header is involved.
CONTROL_CHARACTERS = dict.fromkeys(
	[c for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)] + [0x7F]
)


def strip_control_characters(value):
	"""Remove control characters. Returns a string, always."""
	if value is None:
		return ""
	return str(value).translate(CONTROL_CHARACTERS)


def clean_text(value, limit=None):
	"""Strip control characters, trim, and optionally bound the length."""
	text = strip_control_characters(value).strip()
	return text[:limit] if limit else text


def clean_header(value, limit=200):
	"""For anything that reaches an email header or a filename.

	Stricter than `clean_text`: carriage returns and newlines go too, because a header is
	terminated by them and a filename has no business containing either.
	"""
	text = strip_control_characters(value).replace("\r", " ").replace("\n", " ").strip()
	return text[:limit] if limit else text
