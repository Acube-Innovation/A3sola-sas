# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Read a bank passbook's first page or a cancelled cheque and fill a customer's bank details
from it: the account holder's name, the account number, the bank, the branch and the IFSC.

Read as a KSEB bill is (api/kseb_bill.py): a PDF from its text, a photo with Tesseract OCR on
this server. A photo of a passbook or a cheque is often taken sideways, so it is turned upright
first - the way Tesseract says it is facing, then each other way until the IFSC and the account
number are found. The bank is named from the IFSC's first four letters, which say whose it is.

Nothing is saved here: the form is filled for review.
"""

import re

import frappe
from frappe import _
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api import kseb_bill

CONSUMER = "Solar Consumer"

#: An IFSC's first four letters and the bank they belong to (the Reserve Bank's bank codes).
BANKS = {
	"SBIN": "State Bank of India", "CNRB": "Canara Bank", "FDRL": "Federal Bank", "SIBL": "South Indian Bank",
	"CSBK": "CSB Bank", "KSBK": "Kerala Bank", "KLGB": "Kerala Gramin Bank", "DLXB": "Dhanlaxmi Bank",
	"ESAF": "ESAF Small Finance Bank", "HDFC": "HDFC Bank", "ICIC": "ICICI Bank", "UTIB": "Axis Bank",
	"KKBK": "Kotak Mahindra Bank", "PUNB": "Punjab National Bank", "BARB": "Bank of Baroda", "UBIN": "Union Bank of India",
	"IOBA": "Indian Overseas Bank", "IDIB": "Indian Bank", "BKID": "Bank of India", "CBIN": "Central Bank of India",
	"MAHB": "Bank of Maharashtra", "UCBA": "UCO Bank", "PSIB": "Punjab & Sind Bank", "IBKL": "IDBI Bank",
	"YESB": "Yes Bank", "INDB": "IndusInd Bank", "IDFB": "IDFC First Bank", "KVBL": "Karur Vysya Bank",
	"TMBL": "Tamilnad Mercantile Bank", "CIUB": "City Union Bank", "KARB": "Karnataka Bank", "AUBL": "AU Small Finance Bank",
}
#: Bank names as printed, for a document whose IFSC was not read.
PRINTED = (("State Bank of India", r"\bSBI\b|State\s*Bank\s*of\s*India"), ("Canara Bank", r"Canara"),
	("Federal Bank", r"Federal\s*Bank"), ("South Indian Bank", r"South\s*Indian\s*Bank"), ("Kerala Bank", r"Kerala\s*Bank"),
	("Kerala Gramin Bank", r"Kerala\s*Gramin"), ("HDFC Bank", r"\bHDFC\b"), ("ICICI Bank", r"\bICICI\b"),
	("Axis Bank", r"Axis\s*Bank"), ("Union Bank of India", r"Union\s*Bank"), ("Bank of Baroda", r"Bank\s*of\s*Baroda"),
	("Indian Overseas Bank", r"Indian\s*Overseas"), ("Punjab National Bank", r"Punjab\s*National"))

IFSC = re.compile(r"\b([A-Z]{4})\s?([0O])\s?([A-Z0-9]{6})\b")
#: Lines whose numbers are never the account number.
NOT_ACCOUNT = re.compile(r"CIF|Phone|Mobile|Mob\b|MICR|Code|PIN|Cust(?:omer)?\s*(?:ID|No)|Email|Date|Tel|PPO", re.IGNORECASE)
#: Lines on a passbook or cheque that are never the holder's name.
NOT_A_NAME = re.compile(r"bank|branch|ifs|micr|account|a/c|pay|bearer|rupees|valid|date|sign|india|savings|current|"
	r"address|phone|mail|cif|nominee|multi|city|road|kerala|order|cheque|payable", re.IGNORECASE)
HONORIFIC = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Smt|Shri|Sri|Dr|Kum)\.?\s+", re.IGNORECASE)


# ------------------------------------------------------------------ reading the document
def parse(text):
	"""What a passbook or a cheque says: name, account_no, ifsc, bank, branch."""
	text = (text or "").replace("\r", "").replace("|", " ")
	lines = [l.strip() for l in text.split("\n") if l.strip()]
	out = {"ifsc": _ifsc(text)}
	out["account_no"], out["account_labelled"] = _account(lines)
	out["bank"] = BANKS.get((out["ifsc"] or "")[:4]) or next((b for b, p in PRINTED if re.search(p, text, re.IGNORECASE)), None)
	out["branch"] = _branch(lines)
	out["name"] = _name(lines)
	return {k: v for k, v in out.items() if v}


def score(found):
	"""How fully a reading found the details: a labelled account number counts most."""
	return (3 * bool(found.get("ifsc")) + 2 * bool(found.get("account_no")) + 2 * bool(found.get("account_labelled"))
		+ bool(found.get("name")) + bool(found.get("branch")))


def _ifsc(text):
	"""The IFSC: four letters, a zero, six letters or digits - with OCR's O for the zero put
	right, and in a code of digits, its Os too."""
	labelled = re.search(r"IFS\s*C?\s*(?:Code)?\s*[:\-.=]?\s*([A-Z]{4}\s?[0O]\s?[A-Z0-9]{6})", text, re.IGNORECASE)
	found = [labelled.group(1).upper()] if labelled else []
	found += ["".join(m.groups()) for m in IFSC.finditer(text.upper())]
	for raw in found:
		raw = raw.replace(" ", "")
		code, branch = raw[:4], raw[5:]
		if re.fullmatch(r"[0-9O]{6}", branch):
			branch = branch.replace("O", "0")
		ifsc = code + "0" + branch
		# A bank code we know, or one that was labelled IFSC.
		if code in BANKS or (labelled and raw == labelled.group(1).upper().replace(" ", "")):
			return ifsc
	return None


def _account(lines):
	"""The account number, and whether it was labelled: the number after "A/c No" or "Account
	No", else the longest number of 9 to 18 digits on a line that is not a phone, CIF, MICR or
	code line."""
	for line in lines:
		# OCR reads "A/c.No." as "Aic.No." or loses the A: "ic.No.".
		label = re.search(r"(?:(?:\bA\s*[/\\il1]?|(?<![A-Za-z])[/\\il1])\s*[cC]\s*\.{0,2}\s*(?:No|N0|Number)\b|\bAccount\s*(?:No|Number|Num|Wo|N0|Ro)?\b)", line)
		if not label:
			continue
		# The first run of 9 to 18 digits after it - printed in groups, or not; a stray digit OCR adds is not part of it.
		for run in re.finditer(r"(?<!\d)\d{3,}(?: \d{3,})*(?!\d)", line[label.end():label.end() + 40]):
			digits = run.group(0).replace(" ", "")
			if 9 <= len(digits) <= 18:
				return digits, True
	candidates = []
	for line in lines:
		# The MICR band at a cheque's foot: its numbers sit between ⑈ marks OCR reads as quotes.
		if NOT_ACCOUNT.search(line) or re.search(r"[\"'“”]\s*\d|\d\s*[\"'“”]", line):
			continue
		candidates += [m.group(0) for m in re.finditer(r"(?<!\d)\d{9,18}(?!\d)", line)]
	return (max(candidates, key=len) if candidates else None), False


def _branch(lines):
	"""The branch: after "Branch:" (a passbook), else the capitals line above the branch's
	address and IFSC (a cheque)."""
	for line in lines:
		match = re.search(r"(?:Branch|ranch|anch)\s*(?:Name)?\s*[:\-]\s*([A-Za-z][A-Za-z .&()\-]{2,}?)(?=\s{2,}|\s+Code\b|$)", line)
		if match:
			return _clean(match.group(1))
	ifsc_at = next((i for i, l in enumerate(lines) if re.search(r"IFS\s*C", l, re.IGNORECASE)), None)
	if ifsc_at is None:
		return None
	for line in lines[max(0, ifsc_at - 8):ifsc_at]:
		line = re.split(r"\s{2,}", line)[0].strip(" ,.-")
		if (re.fullmatch(r"[A-Z][A-Z .,&()\-]{3,}", line) and not re.search(r"\d", line) and not NOT_A_NAME.search(line.replace("ROAD", ""))
				and not re.search(r"DD|MM|YY", line) and len(line.split()) >= 1 and sum(c.isalpha() for c in line) >= 5):
			return _clean(line)
	return None


def _name(lines):
	"""The holder's name: after "Name:" (a passbook - on its line, or the next lines), else the
	capitals line printed above "Please sign above" (a cheque)."""
	for i, line in enumerate(lines):
		# "Name", "Account Holder Name", or a statement's "Customer Name" / "Account Name".
		match = re.match(r"^\W*(?:(?:Account\s*Holder(?:'?s)?|Account|Customer)\s*)?Name\s*[:\-]?\s*(.*)$", line, re.IGNORECASE)
		if not match:
			continue
		for candidate in [match.group(1)] + lines[i + 1:i + 4]:
			name = _as_name(candidate)
			if name:
				return name
	sign_at = next((i for i, l in enumerate(lines) if re.search(r"sign\s*above|authori[sz]ed\s*signator", l, re.IGNORECASE)), None)
	if sign_at is not None:
		for line in reversed(lines[max(0, sign_at - 4):sign_at]):
			name = _as_name(line, capitals=True)
			if name:
				return name
	return None


def _as_name(line, capitals=False):
	line = re.split(r"\s{2,}", (line or "").strip())[0]
	line = HONORIFIC.sub("", re.sub(r"[^A-Za-z .]", " ", line)).strip(" .")
	words = [w for w in line.split() if w.strip(".")]
	if not words or NOT_A_NAME.search(line) or sum(c.isalpha() for c in line) < 4:
		return None
	if capitals and not line.isupper():
		return None
	# A name is words of letters - single initials allowed - with at least one full word.
	if not any(len(w.strip(".")) >= 3 for w in words) or len(words) > 6:
		return None
	return " ".join(words)


def _clean(value):
	return " ".join((value or "").split()).strip(" ,.-")


def ocr_photo(content):
	"""A photo's text, turned upright: the way Tesseract says it faces first, then each other
	way, until the IFSC and the account number read."""
	ocr = kseb_bill.tesseract()
	if not ocr:
		frappe.throw(kseb_bill.NO_OCR, title=_("Photo Not Read"))
	image = kseb_bill.prepared_image(content)
	turns = [0, 90, 270, 180]
	try:
		osd = ocr.image_to_osd(image)
		facing = int(re.search(r"Rotate:\s*(\d+)", osd).group(1))
		# Only a sure guess goes first: a cheque's pattern fools it. "Rotate" is clockwise; PIL's turn is not.
		if float(re.search(r"Orientation confidence:\s*([\d.]+)", osd).group(1)) >= 2:
			turns.insert(0, (360 - facing) % 360)
	except Exception:
		pass
	best, best_score, best_image, best_found = "", -1, image, {}
	for turn in dict.fromkeys(turns):
		upright = image.rotate(turn, expand=True) if turn else image
		if upright.width < 2500:
			upright = upright.resize((2500, int(upright.height * 2500 / upright.width)))
		text = ocr.image_to_string(upright, lang="eng", config="--psm 3")
		found = parse(text)
		if score(found) > best_score:
			best, best_score, best_image, best_found = text, score(found), upright, found
		if found.get("ifsc") and found.get("account_labelled"):
			break
	if best_found.get("ifsc") and not best_found.get("name"):
		# The name sits apart from the rest (a passbook's top line): read the words one by one.
		best += "\n" + ocr.image_to_string(best_image, lang="eng", config="--psm 11")
	return best


def read_content(content, filename):
	"""The customer's bank fields and warnings from a passbook or a cheque's bytes."""
	name = (filename or "").lower()
	if name.endswith(".pdf") or content[:5] == b"%PDF-":
		text, _source = kseb_bill.extract_text(content, filename)
	else:
		text = ocr_photo(content)
	found = parse(text)
	if not (found.get("ifsc") or found.get("account_no")):
		frappe.throw(_("No IFSC or account number could be read. Upload the passbook's first page, the cheque or the "
			"statement's first page, clear, straight and in good light."), title=_("Bank Details Not Read"))
	return to_fields(found)


def to_fields(found):
	fields = {"bank_account_holder_name": kseb_bill.name_case(found["name"]) if found.get("name") else None,
		"bank_account_no": found.get("account_no"), "bank_name": found.get("bank"),
		"bank_branch": found["branch"].title() if found.get("branch") else None, "bank_ifsc_code": found.get("ifsc")}
	labels = {"bank_account_holder_name": _("account holder's name"), "bank_account_no": _("account number"),
		"bank_name": _("bank"), "bank_branch": _("branch"), "bank_ifsc_code": _("IFSC")}
	missing = [labels[k] for k, v in fields.items() if not v]
	warnings = [_("Not read: {0}. Enter it from the document.").format(", ".join(missing))] if missing else []
	return {k: v for k, v in fields.items() if v}, warnings


# ------------------------------------------------------------------ the page's call
@frappe.whitelist(methods=["POST"])
def read(doctype=CONSUMER, name=None, **kwargs):
	"""Read the passbook or cheque posted as `file` into the customer's bank fields. Nothing is
	saved or attached here: the Attachments card uploads the file itself."""
	if doctype != CONSUMER:
		frappe.throw(_("A passbook or cheque fills a customer's bank details."), frappe.ValidationError)
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
	fields, warnings = read_content(content, upload.filename)
	return {"fields": fields, "warnings": warnings}
