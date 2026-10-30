# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Read an Aadhaar card and fill a customer's permanent address from it - and, from the front,
their name, date of birth and gender.

The card is read as a KSEB bill is (api/kseb_bill.py): a PDF from its text - an e-Aadhaar is
locked with a password, the first four letters of the name in capitals and the year of birth -
a photo with Tesseract OCR on this server. The Aadhaar number, and the 16-digit VID, are taken
out of the text before anything is read: they are never stored or sent back.

The address is where the person lives, so it is the permanent address; the installation site
comes from the KSEB bill. Nothing is saved here: the form is filled for review.
"""

import re

import frappe
from frappe import _
from frappe.utils import getdate
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api import kseb_bill

CONSUMER = "Solar Consumer"
FRONT, BACK = "Aadhaar Front", "Aadhaar Back"
RELATION = re.compile(r"^\s*(?:S|D|W|C)\s*/\s*O\s*:?\s*[^,]*,\s*", re.IGNORECASE)
#: Lines on a card that are never the holder's name.
NOT_A_NAME = re.compile(r"government|india|unique|identification|authority|aadhaar|enrolment|enrollment|"
	r"download|issue|date|dob|birth|male|female|address|help|www|signature|valid", re.IGNORECASE)


def scrub(text):
	"""The text without its Aadhaar number (12 digits, grouped 4-4-4 or not) or VID (16)."""
	text = re.sub(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}\s?\d{4}(?!\d)", " ", text or "")
	return re.sub(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)", " ", text)


# ------------------------------------------------------------------ reading the card
def parse(text):
	"""What the card says: name, date of birth, gender (front), address parts (back)."""
	text = scrub(text).replace("\r", "").replace("|", " ")
	out = {}
	dob = re.search(r"(?:DOB|Date\s*of\s*Birth|D\.O\.B\.?)\s*[:/]?\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})", text, re.IGNORECASE)
	yob = re.search(r"Year\s*of\s*Birth\s*[:/]?\s*(\d{4})", text, re.IGNORECASE)
	if dob:
		out["dob"] = dob.group(1)
	elif yob:
		out["year_of_birth"] = yob.group(1)
	gender = re.search(r"\b(MALE|FEMALE|TRANSGENDER)\b", text, re.IGNORECASE)
	if gender:
		out["gender"] = gender.group(1).capitalize()
	if dob or yob:
		out["name"] = _name_above(text, (dob or yob).start())
	address = _address(text)
	if address:
		out["address"] = address
	return {k: v for k, v in out.items() if v}


def _name_above(text, at):
	"""The holder's name: the nearest English line above the date of birth's line - not the
	Malayalam label before "/ Year of Birth" on that line itself."""
	for line in reversed(text[:at].split("\n")[:-1]):
		line = re.sub(r"[^A-Za-z .']", " ", line)
		line = " ".join(w for w in line.split() if len(w) > 1 or w.isupper())
		if len(line) >= 3 and not NOT_A_NAME.search(line) and sum(c.isalpha() for c in line) >= 3:
			return line.strip()
	return None


def _address(text):
	"""The address after "Address:", up to its PIN code, as its parts."""
	match = re.search(r"Address\s*:?\s*(.+?\b[1-9]\d{5}\b)", text, re.IGNORECASE | re.DOTALL)
	if not match:
		return None
	raw = " ".join(match.group(1).split())
	labelled = {k: _label(raw, k) for k in ("VTC", "PO", "Sub District", "District", "State", "PIN Code")}
	pin = re.search(r"\b([1-9]\d{5})\b", raw).group(1)
	if labelled["District"] or labelled["VTC"]:
		head = re.split(r"\b(?:VTC|PO|Sub\s*District|District|State|PIN\s*Code)\s*:", raw, maxsplit=1, flags=re.IGNORECASE)[0]
		parts = _parts(head)
		return {"line1": parts[0] if parts else None, "line2": ", ".join(parts[1:] + ([labelled["PO"]] if labelled["PO"] else [])) or None,
			"city": labelled["VTC"], "district": labelled["District"], "state": labelled["State"], "pincode": pin}
	parts = _parts(raw.replace(pin, ""))
	state = next((p for p in parts if find_state(p)), None)
	district = next((p for p in parts if p != state and find_district(p, find_state(state) if state else None)), None)
	rest = [p for p in parts if p not in (state, district)]
	city = rest.pop() if len(rest) > 2 else None
	return {"line1": rest[0] if rest else None, "line2": ", ".join(rest[1:]) or None, "city": city,
		"district": district, "state": state, "pincode": pin}


def english_column(content):
	"""The English address on a photo of a card's back. The card prints the address twice, in
	Malayalam and in English, side by side, and OCR reading across both mixes them: so the column
	is read from the English word "Address" rightwards and down, on its own."""
	ocr = kseb_bill.tesseract()
	if not ocr:
		return None
	image = kseb_bill.prepared_image(content)
	data = ocr.image_to_data(image, lang="eng", config="--psm 4", output_type=ocr.Output.DICT)
	found = [i for i, word in enumerate(data["text"]) if re.fullmatch(r"Address\s*:?", (word or "").strip(), re.IGNORECASE)]
	if not found:
		return None
	# The English label is the rightmost "Address" (the Malayalam column is to its left).
	i = max(found, key=lambda k: data["left"][k])
	box = (max(0, data["left"][i] - 15), max(0, data["top"][i] - 15), image.width, image.height)
	return ocr.image_to_string(image.crop(box), lang="eng", config="--psm 6")


def _label(raw, label):
	# "District:" is not the one inside "Sub District:".
	before = r"(?<!Sub )(?<!Sub)" if label == "District" else ""
	match = re.search(before + r"\b" + label.replace(" ", r"\s*") + r"\s*:\s*([^,:]+?)(?=,|\s+\b(?:VTC|PO|Sub\s*District|District|State|PIN\s*Code)\s*:|$)",
		raw, re.IGNORECASE)
	return match.group(1).strip(" ,-") if match else None


def _parts(raw):
	"""Comma parts of an address, without the relation it starts with (S/O ...) or stray dashes."""
	raw = RELATION.sub("", raw)
	# OCR picks up specks at the card's edges as stray marks: "4 Kerala", "Koratti i".
	parts = [re.sub(r"^(?:[^A-Za-z\s]{1,3}\s+)+|(?:\s+[^A-Za-z\s]{1,3})+$|\s+[a-z]$", "", p.strip(" -.")) for p in raw.split(",")]
	parts = [p.strip(" -.") for p in parts]
	return [p for p in parts if re.search(r"[A-Za-z]", p) or len(p) >= 3]


# ------------------------------------------------------------------ into the customer's fields
def find_state(value):
	value = re.sub(r"(?i)^state\s*:?\s*", "", (value or "").strip())
	return frappe.db.get_value("Indian State", {"state_name": value}) if value else None


def find_district(value, state=None):
	value = re.sub(r"(?i)^(?:dist(?:rict)?\.?\s*:?\s*)", "", (value or "").strip())
	if not value:
		return None
	filters = {"district_name": value}
	if state:
		filters["state"] = state
	return frappe.db.get_value("Indian District", filters)


def to_fields(parsed):
	"""The customer's fields from a read card, with warnings for what was not found."""
	fields, warnings = {}, []
	address = parsed.get("address") or {}
	if address:
		state = find_state(address.get("state")) or (find_state("Kerala") if not address.get("state") else None)
		district = find_district(address.get("district"), state)
		if address.get("state") and not state:
			warnings.append(_("State {0} is not among the states: choose it.").format(address["state"]))
		if address.get("district") and not district:
			warnings.append(_("District {0} is not among the districts: choose it.").format(address["district"]))
		fields.update({
			# The card's address is where the person lives: the permanent address, apart from the site.
			"permanent_address_same": "No", "permanent_address_line1": address.get("line1"),
			"permanent_address_line2": address.get("line2"), "permanent_city": address.get("city"),
			"permanent_state": state, "permanent_district": district, "permanent_pincode": address.get("pincode"),
		})
	if parsed.get("name"):
		fields["consumer_name"] = kseb_bill.name_case(parsed["name"])
	if parsed.get("dob"):
		try:
			fields["date_of_birth"] = str(getdate(parsed["dob"].replace(".", "/").replace("-", "/"), parse_day_first=True))
		except Exception:
			warnings.append(_("Date of birth {0} could not be read.").format(parsed["dob"]))
	elif parsed.get("year_of_birth"):
		warnings.append(_("The card gives only the year of birth ({0}): enter the date of birth.").format(parsed["year_of_birth"]))
	if parsed.get("gender") and frappe.db.exists("Gender", parsed["gender"]):
		fields["gender"] = parsed["gender"]
	return {k: v for k, v in fields.items() if v not in (None, "")}, warnings


# ------------------------------------------------------------------ the page's call
@frappe.whitelist(methods=["POST"])
def read(doctype=CONSUMER, name=None, password=None):
	"""Read the Aadhaar card posted as `file` (with its password, if a locked PDF). Returns the
	customer's fields to fill and warnings; the card is attached to the customer that exists, or
	kept for the one being created. The Aadhaar number is never read."""
	if doctype != CONSUMER:
		frappe.throw(_("An Aadhaar card fills a customer."), frappe.ValidationError)
	if name:
		if not frappe.has_permission(doctype, "write", name):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
	elif not frappe.has_permission(doctype, "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	upload = (frappe.request.files.getlist("file") or [None])[0] if frappe.request and frappe.request.files else None
	if not upload:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	content = upload.stream.read()
	if len(content) > get_max_file_size():
		frappe.throw(_("{0} is larger than {1} MB.").format(upload.filename, get_max_file_size() // (1024 * 1024)),
			frappe.ValidationError)
	text, source = kseb_bill.extract_text(content, upload.filename, password)
	parsed = parse(text)
	if source == "ocr" and not upload.filename.lower().endswith(".pdf"):
		# A photo of the back: its English address column, read on its own.
		column = english_column(content)
		address = parse(column).get("address") if column else None
		if address:
			parsed["address"] = address
	if not (parsed.get("address") or parsed.get("dob") or parsed.get("year_of_birth")):
		frappe.throw(_("This does not read as an Aadhaar card. Upload the side with the address, clear and straight, "
			"or the e-Aadhaar PDF."), title=_("Card Not Read"))
	fields, warnings = to_fields(parsed)
	# A PDF (e-Aadhaar) holds both sides; a photo is the side it shows.
	kind = FRONT if (source == "pdf-text" or not parsed.get("address")) else BACK
	attached, pending = False, None
	if name:
		kseb_bill.attach(doctype, name, upload.filename, content, kind)
		attached = True
	else:
		pending = kseb_bill.keep(upload.filename, content, kind)
	return {"fields": fields, "warnings": warnings, "source": source, "side": kind, "attached": attached,
		"pending_file": pending}
