# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Read a KSEB bill and fill a lead's or customer's details from it.

A KSEB e-bill PDF carries its text, which is read as it is. A photo or a scan is read with
Tesseract OCR, on this server: nothing is sent anywhere. The text is then read by the bill's
own labels (Consumer#, Section [code]-name, Name & Mailing Address, Tariff/Phase, Connected
Load, Billing Period, the meter readings' Units, Total Amt.) and turned into the record's
fields, its DISCOM, section and tariff found among their records.

Nothing is saved here: the page fills its form with what is returned, and the person checks
it and saves. On a record that exists, the bill is also attached to it as its KSEB Bill; on a
new one it is kept, and attached as the record is created (`claim`).
"""

import io
import os
import re
import shutil
import subprocess
import tempfile

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.file_manager import get_max_file_size

CONSUMER = "Solar Consumer"
DOCTYPES = ("Lead", CONSUMER)
KSEB_BILL = "KSEB Bill"
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic")
NO_OCR = _("Photos of bills can't be read on this server yet (OCR is not installed). Upload the PDF bill, "
	"or fill the details in.")


# ------------------------------------------------------------------ reading the text
def extract_text(content, filename):
	"""The bill's text, and how it was read: "pdf-text" or "ocr"."""
	name = (filename or "").lower()
	if name.endswith(".pdf") or content[:5] == b"%PDF-":
		text = pdf_text(content)
		if len(text.strip()) > 50:
			return text, "pdf-text"
		return ocr_pdf(content), "ocr"
	if name.endswith(IMAGE_TYPES) or content[:4] in (b"\x89PNG", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1", b"\xff\xd8\xff\xdb"):
		return ocr_image(content), "ocr"
	frappe.throw(_("Upload the KSEB bill as a PDF or a photo (JPG or PNG)."), frappe.ValidationError)


def pdf_text(content):
	from pypdf import PdfReader

	try:
		reader = PdfReader(io.BytesIO(content))
		return "\n".join(page.extract_text(extraction_mode="layout") or "" for page in reader.pages[:3])
	except Exception:
		frappe.throw(_("The PDF could not be read. Save it again and retry."), frappe.ValidationError)


def tesseract():
	"""pytesseract, when Tesseract is installed here; else None."""
	if not shutil.which("tesseract"):
		return None
	try:
		import pytesseract
	except ImportError:
		return None
	return pytesseract


def ocr_image(content):
	from PIL import Image, ImageOps

	ocr = tesseract()
	if not ocr:
		frappe.throw(NO_OCR, title=_("Photo Not Read"))
	try:
		image = Image.open(io.BytesIO(content))
		image = ImageOps.exif_transpose(image)
	except Exception:
		frappe.throw(_("The photo could not be opened. Take it again as a JPG or PNG."), frappe.ValidationError)
	image = ImageOps.autocontrast(ImageOps.grayscale(image))
	# Tesseract reads best near 300 dpi - an A4 bill about 2500 px wide: a smaller photo is scaled up.
	if image.width < 2500:
		image = image.resize((2500, int(image.height * 2500 / image.width)))
	# English only: the bill's labels and details are English, and the Malayalam model reads
	# English text as Malayalam letters. Mode 4 keeps the bill's columns apart.
	return ocr.image_to_string(image, lang="eng", config="--psm 4")


def ocr_pdf(content):
	"""A scanned PDF: its first pages as images, read with OCR."""
	if not (tesseract() and shutil.which("pdftoppm")):
		frappe.throw(NO_OCR, title=_("Scan Not Read"))
	with tempfile.TemporaryDirectory() as tmp:
		path = f"{tmp}/bill.pdf"
		with open(path, "wb") as f:
			f.write(content)
		subprocess.run(["pdftoppm", "-r", "300", "-png", "-f", "1", "-l", "2", path, f"{tmp}/page"],
			check=True, timeout=60, capture_output=True)
		pages = sorted(p for p in os.listdir(tmp) if p.startswith("page"))
		return "\n".join(ocr_image(open(f"{tmp}/{p}", "rb").read()) for p in pages)


# ------------------------------------------------------------------ reading the bill
def _first(pattern, text, group=1, flags=re.IGNORECASE):
	match = re.search(pattern, text, flags)
	return match.group(group).strip() if match else None


def _number(value):
	return flt((value or "").replace(",", "")) if value else None


def _left(line):
	"""The left column of a two-column line: up to the first wide gap."""
	return re.split(r"\s{3,}", line.strip())[0].strip()


def parse(text):
	"""What a KSEB bill says, by its labels. A label not found is left out."""
	# A photo read by OCR draws the bill's table borders as "|", and loses a label's first
	# letter at a border ("ariff/Phase", "onnected Load", "otal Amt."): read past both.
	text = text.replace("\r", "").replace("|", " ")
	out = {}
	number = _first(r"Consum\w*\s*(?:#|No\.?|Number)?\s*:?\s*((?:\d\s?){9,15})", text)
	out["consumer_number"] = re.sub(r"\s", "", number) if number else None
	section = re.search(r"Section\s*(?:#|:)?\s*\[\s*(\d{3,6})\s*\]\s*-?\s*([^\n]+?)(?:\s{2,}|$)", text, re.IGNORECASE | re.MULTILINE)
	if section:
		out["section_code"] = section.group(1)
		out["section_name"] = re.sub(r"(?i)^electrical\s+section\s*", "", section.group(2)).strip()
	out.update(_name_and_address(text))
	tariff = re.search(r"T?ariff\s*/\s*Phase\s*:?\s*([A-Z]{2}\s*-?\s*[\dIVX]+\s*\(?[A-Z]?\)?)\s*/\s*(Single|Three|1|3)",
		text, re.IGNORECASE)
	if tariff:
		out["tariff"] = re.sub(r"\s+", "", tariff.group(1)).upper()
		out["phase"] = "Three" if tariff.group(2).lower() in ("three", "3") else "Single"
	else:
		out["tariff"] = _first(r"Tariff\s*:?\s*((?:LT|HT)\s*-?\s*\d{1,2}\s*\(?[A-Z]?\)?)", text)
		phase = _first(r"Phase\s*:?\s*(Single|Three|1|3)\b", text)
		if phase:
			out["phase"] = "Three" if phase.lower() in ("three", "3") else "Single"
	load = re.search(r"C?onnected\s*Load\s*:?\s*([\d,]+(?:\.\d+)?)\s*(kW|W|Watts)?", text, re.IGNORECASE)
	if load:
		watts = _number(load.group(1))
		out["connected_load_watts"] = watts * 1000 if (load.group(2) or "").lower() == "kw" else watts
	period = _first(r"Billing\s*Period\s*:?\s*([^\n]*?)(?:\s{3,}|$)", text, flags=re.IGNORECASE | re.MULTILINE) or ""
	if re.search(r"bi\s*-?\s*monthly", period or text, re.IGNORECASE):
		out["billing_frequency"] = "Bimonthly"
	elif re.search(r"\bmonthly\b", period, re.IGNORECASE):
		out["billing_frequency"] = "Monthly"
	out["units"] = _units(text)
	amount = _first(r"T?otal\s*Amt\.?[^\n]*?([\d,]+\.\d{2})\s*$", text, flags=re.IGNORECASE | re.MULTILINE) \
		or _first(r"Net\s*Amount\s*(?:Payable)?\s*:?\s*(?:Rs\.?)?\s*([\d,]+(?:\.\d{2})?)", text)
	out["bill_amount"] = _number(amount)
	out["bill_date"] = _first(r"Bill\s*Date\s*:?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})", text)
	return {k: v for k, v in out.items() if v not in (None, "", [])}


#: The e-bill's address column, in characters: a longer address runs on to the next line.
ADDRESS_WIDTH = 45


def _name_and_address(text):
	"""The name and mailing address: the left column of the lines under "Name & Mailing Address",
	up to the bill number. The address repeats the name first; lines cut at the column's width
	run on into the next."""
	lines = text.split("\n")
	start = next((i for i, l in enumerate(lines) if re.search(r"Name\s*&\s*(?:Mailing\s*)?Address", l, re.IGNORECASE)), None)
	if start is None:
		return {}
	block = []
	for line in lines[start + 1:start + 12]:
		if re.match(r"\s*(Bill\s*(#|No)|Billing\s*Period|Bill\s*Date)", line, re.IGNORECASE):
			break
		part = _left(line)
		if part and not re.match(r"(South|Central|North|State Electricity)\b", part, re.IGNORECASE):
			block.append(part)
	if not block:
		return {}
	# Read as one line by OCR, a line runs on into the CGRF column beside it ("South: ...",
	# "...SubStation,Kalamassery-683503,Ph:0484-..."): cut it there.
	block = [re.split(r"\s+(?:South|Central|North)\s*:|\s+\S*,\s*[A-Za-z]+-\d{6}\s*,\s*Ph\s*:|\s+\S*Ph\s*:\s*\d",
		part)[0].strip() for part in block]
	block = [part for part in block if part]
	name, address = block[0], ""
	for part in block[1:]:
		# A line as wide as the column was cut there, mid-word: it runs on without a space.
		address += part if address and len(previous) == ADDRESS_WIDTH else (" " if address else "") + part
		previous = part
	address = re.sub(r"^\s*" + re.escape(name) + r"\s*,\s*", "", address, flags=re.IGNORECASE).strip(" ,")
	out = {"name": name}
	if address:
		out["address"] = address
		pin = _first(r"\b(6\d{5})\b", address)
		if pin:
			out["pincode"] = pin
	return out


def _units(text):
	"""Units billed: the meter readings' Units column summed over its zones (a ToD meter has
	three - Normal, Off Peak, Peak; others one, Cumulative), else a "Units Consumed" figure."""
	rows = re.findall(r"^\s*KWH\s+[A-Za-z][A-Za-z ]*?\s+Import\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s*$",
		text, re.IGNORECASE | re.MULTILINE)
	if rows:
		return sum(flt(r) for r in rows)
	return _number(_first(r"Units\s*(?:Consumed|Billed)?\s*:?\s*([\d,]+(?:\.\d+)?)", text))


# ------------------------------------------------------------------ into the record's fields
def to_fields(parsed, doctype):
	"""The record's fields from a read bill, its DISCOM, section and tariff found among their
	records, and warnings for what could not be found."""
	from a3_sola.solar_crm.doctype.kseb_tariff_category.kseb_tariff_category import kseb_code

	fields, warnings = {}, []
	section, discom = find_section(parsed)
	if parsed.get("section_code") and not section:
		warnings.append(_("Section [{0}] {1} is not among the DISCOM Sections: choose it.").format(
			parsed["section_code"], parsed.get("section_name") or ""))
	discom = discom or kseb_discom()
	phase = {"Single": "Single Phase", "Three": "Three Phase"}.get(parsed.get("phase"))
	cycle_months = 2 if parsed.get("billing_frequency") == "Bimonthly" else 1
	name = name_case(parsed.get("name")) or None
	if doctype == "Lead":
		fields.update({
			"lead_name": name, "consumer_number": parsed.get("consumer_number"), "discom": discom,
			"discom_section": section, "connection_type": phase, "approx_consumption_units": parsed.get("units"),
			"avg_monthly_bill": flt(parsed["bill_amount"] / cycle_months, 2) if parsed.get("bill_amount") else None,
		})
	else:
		tariff = kseb_code(parsed.get("tariff"))
		if parsed.get("tariff") and not tariff:
			warnings.append(_("Tariff {0} is not among the KSEB Tariff Categories: choose it.").format(parsed["tariff"]))
		line1, line2 = split_address(parsed.get("address"))
		fields.update({
			"consumer_name": name, "consumer_number": parsed.get("consumer_number"), "discom": discom,
			"discom_section": section, "tariff_category": tariff, "connection_type": phase,
			"connected_load_watts": parsed.get("connected_load_watts"), "avg_consumption_units": parsed.get("units"),
			"avg_bill_amount": parsed.get("bill_amount"), "billing_frequency": parsed.get("billing_frequency"),
			"site_address_line1": line1, "site_address_line2": line2, "site_pincode": parsed.get("pincode"),
		})
	return {k: v for k, v in fields.items() if v not in (None, "")}, warnings


def name_case(name):
	"""A bill's capitals as a name is written: "LIJO KURIAN" is Lijo Kurian; initials stay as
	they are ("CK BOBAN" is CK Boban, "K. RAJAN" is K. Rajan)."""
	words = (name or "").split()
	return " ".join(w if len(w.rstrip(".")) <= 2 else w.capitalize() for w in words)


def kseb_discom():
	"""The KSEB DISCOM record: of those named KSEB, the one with the most sections."""
	rows = frappe.db.sql("""select d.name, count(s.name) n from `tabDISCOM` d
		left join `tabDISCOM Section` s on s.discom = d.name
		where d.discom_name like '%%KSEB%%' or d.discom_name like '%%Kerala State Electricity%%'
		group by d.name order by n desc""", as_dict=True)
	return rows[0].name if rows else None


def find_section(parsed):
	"""The DISCOM Section the bill names, and its DISCOM: by name; by code only where that code's
	section bears the bill's name too (the codes on file are not unique)."""
	name, code = (parsed.get("section_name") or "").strip(), parsed.get("section_code")
	if not (name or code):
		return None, None
	fields = ["name", "discom", "section_name"]
	if name:
		exact = frappe.get_all("DISCOM Section", filters={"section_name": name}, fields=fields)
		found = exact or frappe.get_all("DISCOM Section", filters={"section_name": ["like", f"{name}%"]}, fields=fields)
		if len(found) == 1:
			return found[0].name, found[0].discom
	if code:
		by_code = frappe.get_all("DISCOM Section", filters={"section_code": code}, fields=fields)
		word = (name.split() or [""])[0].lower()
		match = [s for s in by_code if word and word in (s.section_name or "").lower()]
		if len(match) == 1:
			return match[0].name, match[0].discom
	return None, None


def split_address(address):
	"""House / building, and street / area: the first comma part (two, when the first is only a
	house number), and the rest."""
	parts = [p.strip() for p in (address or "").split(",") if p.strip()]
	if not parts:
		return None, None
	take = 2 if len(parts) > 2 and len(parts[0]) <= 5 else 1
	return ", ".join(parts[:take]), ", ".join(parts[take:]) or None


# ------------------------------------------------------------------ the page's call
@frappe.whitelist(methods=["POST"])
def read(doctype, name=None):
	"""Read the KSEB bill posted as `file`. Returns the record's fields to fill, warnings and how
	the bill was read; on a record that exists, the bill is attached to it as its KSEB Bill."""
	if doctype not in DOCTYPES:
		frappe.throw(_("A KSEB bill fills a lead or a customer."), frappe.ValidationError)
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
	text, source = extract_text(content, upload.filename)
	parsed = parse(text)
	if not parsed.get("consumer_number") and not parsed.get("name"):
		frappe.throw(_("This does not read as a KSEB bill. Upload the bill's first page, clear and straight."),
			title=_("Bill Not Read"))
	fields, warnings = to_fields(parsed, doctype)
	attached, pending = False, None
	if name:
		attach(doctype, name, upload.filename, content)
		attached = True
	else:
		# No record yet: the bill waits, private and the reader's own, for the one created.
		pending = frappe.get_doc({"doctype": "File", "file_name": upload.filename, "content": content, "is_private": 1,
			"a3s_document_type": KSEB_BILL}).insert(ignore_permissions=True).name
	return {"fields": fields, "warnings": warnings, "source": source, "attached": attached, "pending_file": pending}


def claim(file_name, doctype, name):
	"""The bill read on a create form, attached to the record it created as its KSEB Bill: only
	the reader's own, and only one not yet attached to anything."""
	if not file_name or doctype not in DOCTYPES:
		return None
	file = frappe.db.get_value("File", file_name, ["name", "owner", "attached_to_doctype", "a3s_document_type",
		"file_url"], as_dict=True)
	if not file or file.owner != frappe.session.user or file.attached_to_doctype or file.a3s_document_type != KSEB_BILL:
		return None
	from a3_sola.api import portal_attachments

	frappe.db.set_value("File", file.name, {"attached_to_doctype": doctype, "attached_to_name": name})
	if doctype == CONSUMER:
		portal_attachments._sync_kyc(name, file.file_url, KSEB_BILL)
	portal_attachments._refresh_kyc(doctype, name)
	return file.file_url


def attach(doctype, name, filename, content):
	"""The bill on the record as its KSEB Bill - and, on a customer, its KYC row."""
	from a3_sola.api import portal_attachments

	file = frappe.get_doc({"doctype": "File", "file_name": filename, "content": content, "is_private": 1,
		"attached_to_doctype": doctype, "attached_to_name": name, "a3s_document_type": KSEB_BILL}).insert(ignore_permissions=True)
	if doctype == CONSUMER:
		portal_attachments._sync_kyc(name, file.file_url, KSEB_BILL)
	portal_attachments._refresh_kyc(doctype, name)
	return file.file_url
