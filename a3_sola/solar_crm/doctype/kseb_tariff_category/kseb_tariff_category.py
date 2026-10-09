# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}
# "LT-1A", "LT 7 A", "LT-1/Single", "lt-1 /three", "HT-2B": supply, tariff number, sub-letter.
WRITTEN = re.compile(r"^\s*(LT|HT)\s*[-\s]?\s*(\d{1,2})\s*(?:\(?\s*([A-Za-z])\s*\)?)?(?![A-Za-z])", re.IGNORECASE)


class KSEBTariffCategory(Document):
	pass


def kseb_code(value):
	"""The KSEB tariff code for a category as it is written on forms, or None.

	A code already on file is returned as it is. Otherwise the arabic tariff number of the
	DISCOM's forms ("LT-1/Single", "LT-7A") becomes the code's roman one ("LT-I",
	"LT-VII(A)"); a sub-letter the list has no code for falls back to the main tariff, so
	"LT-1A" is LT-I. The phase written after a slash is the connection type, not part of
	the tariff, and is ignored.
	"""
	value = (value or "").strip()
	if not value:
		return None
	if frappe.db.exists("KSEB Tariff Category", value):
		return value
	match = WRITTEN.match(value)
	if not match:
		return None
	supply, number, letter = match.group(1).upper(), int(match.group(2)), (match.group(3) or "").upper()
	roman = ROMAN.get(number)
	if not roman:
		return None
	for code in ([f"{supply}-{roman}({letter})"] if letter else []) + [f"{supply}-{roman}"]:
		if frappe.db.exists("KSEB Tariff Category", code):
			return code
	return None
