# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Supplier Invoice task: a supplier's bill for a job's material, read from its PDF into an
ERPNext Purchase Invoice on the job.

The bill is read as a KSEB bill is (api/kseb_bill.py) - a PDF from its text, a photo through
OCR - and laid out as the suppliers' Tally tax invoices are (RIM Projects' RPVT/26-27/6602):

	1  RENEWSYS DESERV 565WP DCR EXT-GG MONO BIS 1500V    85414300   5 %   6 Nos  12,599.50 Nos   75,597.00
	      r1200042260127725                                      <- a serial number of the line
	2  POLYCAB SOLAR GRID TIE INVERTER - 1PH & 1MPPT 3000 ...
	   WATT WITH RMS- PSIS-3K0                                   <- the description runs on
	        L&T Testing Charge 1PH Energy   998346   18 %   284.00   <- a charge, qty 1
	                                CGST   4,562.37
	                         Rounded Off       0.11
	                               Total   ₹ 1,26,029.00

Nothing is saved by reading: the page shows the lines to check, and `create` makes the
Purchase Invoice - submitted, the PDF attached, the job linked, costed as its material
(api/costing.py) - in ERPNext's own tax format: the invoice's purchase tax template, each
line's item tax template (GST 5%, GST 18%, ...), and ERPNext's calculation of both, shown on
the page line by line before it is entered (`preview`).
"""

import re
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint, flt, today
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api import partner_scope
from a3_sola.api.kseb_bill import extract_text

CODE = "SUPINV"
INSTALLATION = "Solar Installation"
DOCUMENT_TYPE = "Supplier Invoice"
#: The bill's units as ERPNext's: anything else is Nos.
UOMS = {"nos": "Nos", "no": "Nos", "pcs": "Nos", "ea": "Nos", "each": "Nos", "mtr": "Meter", "mtrs": "Meter", "m": "Meter", "meter": "Meter",
	"kg": "Kg", "kgs": "Kg", "bag": "Bag", "bags": "Bag", "set": "Set", "sets": "Set", "box": "Box", "pair": "Pair"}
#: How far the lines and taxes may be from the bill's total before it is said.
TOLERANCE = 1.0

_NUM = r"[\d,]+(?:\.\d+)?"
ITEM = re.compile(
	r"^(?P<indent>\s*)(?P<sl>\d{1,3})\s+(?P<desc>\S.*?)\s{2,}(?P<hsn>\d{4,8})\s+(?P<gst>\d{1,2}(?:\.\d+)?)\s*%\s+"
	r"(?P<qty>" + _NUM + r")\s*(?P<unit>[A-Za-z]+)\s+(?P<rate>" + _NUM + r")\s+[A-Za-z]+\s+"
	r"(?:(?P<disc>\d{1,2}(?:\.\d+)?)\s*%\s+)?(?P<amount>[\d,]+\.\d{2})\s*$")
CHARGE = re.compile(
	r"^\s+(?P<desc>[A-Za-z][^\n]*?)\s{2,}(?P<hsn>\d{4,8})\s+(?P<gst>\d{1,2}(?:\.\d+)?)\s*%\s+(?P<amount>[\d,]+\.\d{2})\s*$")
TAX = re.compile(r"^\s*(?P<kind>CGST|SGST|UTGST|IGST)\b[^\n\d]*?(?:@\s*[\d.]+\s*%)?[^\n\d]*(?P<amount>[\d,]+\.\d{2})\s*$",
	re.IGNORECASE)
ROUND = re.compile(r"^\s*(?:(?:Less|Add)\s*:?\s*)?Round(?:ed|ing)?\s*Off\b[^\n\d(-]*(?P<sign>\(?\s*-\s*\)?)?\s*(?P<amount>[\d,]+\.\d{2})\s*$",
	re.IGNORECASE)
TOTAL = re.compile(r"^\s*Total\s+(?:₹|Rs\.?|INR)?\s*(?P<amount>[\d,]+\.\d{2})\s*$", re.IGNORECASE)
GSTIN = re.compile(r"(?:GSTIN(?:/UIN)?|GST\s*(?:Registration\s*)?(?:No|Number)\.?)\s*:?\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z])")
#: A company's name as a bill signs or heads it: "... Limited", "... LLP", "... Pvt Ltd".
COMPANY = r"[A-Z][A-Za-z0-9&.()' -]{2,80}?\b(?:Limited|Ltd\.?|LLP|Private|Pvt\.?(?:\s*Ltd\.?)?)"


def _n(value):
	return flt((value or "").replace(",", "")) if value else 0.0


def _date(value):
	for fmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%y"):
		try:
			return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
		except (ValueError, TypeError):
			continue
	return None


def parse(text):
	"""What the bill says: supplier, GSTINs, bill no. and date, its lines and charges, its
	taxes, rounding and total. Only the invoice is read - the e-way bill after it repeats
	the goods."""
	text = (text or "").replace("\r", "").replace("\t", "    ")
	# A bill printed in copies - the original, then the transporter's duplicate: the original only.
	original = re.search(r"Original\s+for\s+Recipient", text, re.IGNORECASE)
	copy = original and re.compile(r"\b(?:Duplicate|Triplicate)\s+for\b", re.IGNORECASE).search(text, original.end())
	if copy:
		text = text[:copy.start()]
	lines = text.split("\n")
	out = {"lines": [], "charges": [], "cgst": 0.0, "sgst": 0.0, "igst": 0.0, "round_off": 0.0}

	gstins = GSTIN.findall(text)
	if gstins:
		out["supplier_gstin"] = gstins[0]
		out["buyer_gstin"] = next((g for g in gstins[1:] if g != gstins[0]), None)
	# The bill's number and date: "Reference No. & Date." reads "RPVT/26-27/6602 dt. 29-Oct-26";
	# else the number and the first date under "Invoice No.".
	ref = re.search(r"\b([A-Z]{2,}[A-Z0-9]*/[A-Z0-9/-]+)\s+dt\.?\s*(\d{1,2}-[A-Za-z]{3}-\d{2,4})", text)
	head = next((i for i, l in enumerate(lines) if re.search(r"Invoice\s*No", l, re.IGNORECASE)), None)
	if ref:
		out["bill_no"], out["bill_date"] = ref.group(1), _date(ref.group(2))
	elif head is not None:
		below = "\n".join(lines[head:head + 3])
		number = re.search(r"\b([A-Z]{2,}[A-Z0-9]*/[A-Z0-9/-]+)", below)
		date = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{2,4}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})", below)
		out["bill_no"] = number.group(1) if number else None
		out["bill_date"] = _date(date.group(1)) if date else None
	# The seller: the left column of the line its "Invoice No." heads, less Tally's year.
	if head is not None:
		name = re.split(r"\s{3,}", lines[head].strip())[0]
		if not re.search(r"Invoice|\bGST\b|\bNo\b", name, re.IGNORECASE):  # not the label itself
			out["supplier_name"] = re.sub(r"\s+\d{4}\s*-\s*\d{2,4}$", "", name).strip() or None
	if not out.get("supplier_name"):
		out["supplier_name"] = _seller_name(text)

	# The customer the material is for: the first line under "Consignee (Ship to)", its left
	# column - else the buyer, where the bill names no consignee.
	for heading in (r"Consignee\s*\(Ship\s*to\)", r"Buyer\s*\(Bill\s*to\)"):
		at = next((i for i, l in enumerate(lines) if re.search(heading, l, re.IGNORECASE)), None)
		if at is None:
			continue
		name = next((re.split(r"\s{3,}", l.strip())[0] for l in lines[at + 1:at + 4] if l.strip()), "")
		if name and not re.search(r"GSTIN|State Name|Contact", name, re.IGNORECASE):
			out["consignee" if "Consignee" in heading else "buyer"] = name.strip(" ,.")
			break
	ship_to = not out.get("consignee") and re.search(r"Ship\s*To\s*:\s*([A-Z][A-Za-z.]*(?: [A-Z][A-Za-z.]*){0,4})", text)
	if ship_to:  # "Ship To : LIJO KURIEN", on the line it heads
		out["consignee"] = ship_to.group(1).strip(" .")

	current = None
	for line in lines:
		if TOTAL.match(line):
			out["total"] = _n(TOTAL.match(line).group("amount"))
			break  # the invoice ends here; the e-way bill follows
		item = ITEM.match(line)
		if item:
			current = {
				"description": re.sub(r"\s+", " ", item.group("desc")).strip(), "hsn": item.group("hsn"),
				"gst_rate": flt(item.group("gst")), "qty": _n(item.group("qty")), "uom": item.group("unit"),
				"rate": _n(item.group("rate")), "discount": flt(item.group("disc")), "amount": _n(item.group("amount")),
				"serials": [], "_col": len(item.group("indent")) + len(item.group("sl")),
			}
			out["lines"].append(current)
			continue
		charge = CHARGE.match(line)
		if charge and not TAX.match(line):
			amount = _n(charge.group("amount"))
			out["charges"].append({"description": re.sub(r"\s+", " ", charge.group("desc")).strip(), "hsn": charge.group("hsn"),
				"gst_rate": flt(charge.group("gst")), "qty": 1, "uom": "Nos", "rate": amount, "amount": amount, "serials": []})
			current = None
			continue
		tax = TAX.match(line)
		if tax:
			kind = tax.group("kind").lower().replace("utgst", "sgst")
			out[kind] = flt(out[kind] + _n(tax.group("amount")), 2)
			current = None
			continue
		rounding = ROUND.match(line)
		if rounding:
			out["round_off"] = -_n(rounding.group("amount")) if rounding.group("sign") else _n(rounding.group("amount"))
			continue
		if current is None or not line.strip():
			continue
		if re.search(r"continued to page|Computer Generated|^\s*(Sl|No\.)\s", line, re.IGNORECASE):
			current = None
			continue
		indent = len(line) - len(line.lstrip())
		words = line.split()
		# A single code with six digits or more under the line is one of its serial numbers;
		# a line level with the description continues it; deeper text repeats it and is dropped.
		if len(words) == 1 and re.match(r"^[\d,]+\.\d{2}$", words[0]):
			continue  # the page's subtotal, not a serial
		if len(words) == 1 and sum(c.isdigit() for c in words[0]) >= 6:
			current["serials"].append(words[0])
		elif indent <= current["_col"] + 3:
			current["description"] = (current["description"] + " " + " ".join(words)).strip()
	for row in out["lines"]:
		row.pop("_col", None)
	if not out["lines"]:
		_parse_gst_table(text, out)
	if out["lines"]:
		_bill_labels(text, out)
	else:
		_parse_simple(text, out)
	out["supplier_details"] = supplier_details(text, out)
	return out


def _seller_name(text):
	"""The seller where no Tally column names it: as the bill signs it ("For Vashi Integrated
	Solutions Limited,"), names its bank account for, or heads it."""
	for pattern in (r"\bFor\s+(" + COMPANY + r")\s*[,:]?\s*$", r"\bIn\s+favou?r\s+of\s+(" + COMPANY + r")"):
		m = re.search(pattern, text, re.MULTILINE)
		if m:
			return re.sub(r"\s+", " ", m.group(1)).strip(" .,")
	for line in text.split("\n")[:10]:
		m = re.search(r"(" + COMPANY + r")\s*$", line.strip())
		if m:
			return re.sub(r"\s+", " ", m.group(1)).strip(" .,")
	return None


#: GST state codes, as a GSTIN's first two digits give them.
STATES = {"01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
	"06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
	"12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
	"18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
	"24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
	"31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
	"36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh"}
#: Where the seller's block ends: its registrations, contacts and the buyer's block.
_BLOCK_END = re.compile(r"GSTIN|UDYAM|State\s*(Name)?\s*:|CIN\s*:|Contact|Phone|E-?Mail|Consignee|Buyer|Bill\s*To|"
	r"Tax\s*Invoice|GST\s*No|\bIRN\b|E-?Way|Original\s+for", re.IGNORECASE)
#: Where the buyer's block starts: the seller's phone and e-mail are looked for before it.
_BUYER_START = re.compile(r"Bill\s*To|Buyer|Consignee|Ship\s*To|Place\s+of\s+Supply", re.IGNORECASE)
#: A bank by its IFSC's first four letters - surer than the OCR's reading of its name.
IFSC_BANKS = {"HDFC": "HDFC Bank", "ICIC": "ICICI Bank", "SBIN": "State Bank of India", "UTIB": "Axis Bank",
	"KKBK": "Kotak Mahindra Bank", "FDRL": "Federal Bank", "SIBL": "South Indian Bank", "CNRB": "Canara Bank",
	"BARB": "Bank of Baroda", "PUNB": "Punjab National Bank", "UBIN": "Union Bank of India", "IDIB": "Indian Bank",
	"CSBK": "CSB Bank", "YESB": "Yes Bank", "IBKL": "IDBI Bank", "INDB": "IndusInd Bank", "KVBL": "Karur Vysya Bank",
	"DLXB": "Dhanlaxmi Bank"}


def _labelled(text, label):
	"""The value after `label :`, on the same line or - as Tally prints some - the next."""
	m = re.search(label + r"\s*:?\s*\n?\s*:\s*([^\n]+)", text, re.IGNORECASE) or \
		re.search(label + r"\s*:\s*([^\n]+)", text, re.IGNORECASE)
	return re.split(r"\s{3,}", m.group(1).strip())[0].strip() if m else ""


def supplier_details(text, out):
	"""What the bill says of its seller, to make it a Supplier: its address, state, phone,
	e-mail, PAN and bank account - each only where the bill labels it."""
	text = (text or "").replace("\r", "")
	lines = text.split("\n")
	d = {}
	gstin = out.get("supplier_gstin") or ""
	# The seller's address: the left column of the lines under its name, to its registrations.
	name = out.get("supplier_name") or ""
	at = next((i for i, l in enumerate(lines) if name and name.split()[0] in l and ("Invoice" in l or name in l)), None)
	address = []
	if at is not None:
		for line in lines[at + 1:at + 10]:
			if _BLOCK_END.search(line):
				break
			if re.search(r"Formerly", line, re.IGNORECASE):
				continue
			part = re.split(r"\s{3,}", line.strip())[0].strip()
			found = re.search(r"([A-Z0-9][A-Za-z0-9 .,&/#()-]{2,})", part)  # past a photo's noise
			part = found.group(1).strip(" ,") if found else ""
			# A photo's noise ahead of the words ("4 zy EKM, ALUVA"): short scraps before capitals.
			part = re.sub(r"^(?:(?:\d{1,2}|[a-z]{1,3}|[^\w\s]+)\s+)+(?=[A-Z])", "", part)
			if part and not re.search(r"[\d,]", part) and name.split()[0].lower() in part.lower():
				continue  # a logo's letters ("VY Vashi"), not an address
			if part and part.lower() not in ("india",) and part not in STATES.values():
				address.append(part)
	if address:
		d["address_line1"] = address[0][:140]
		if len(address) > 1:
			d["address_line2"] = ", ".join(address[1:])[:140]
		joined = ", ".join(address)
		pin = re.search(r"\b(\d{6})\b", joined)
		if pin:
			d["pincode"] = pin.group(1)
			before = [re.sub(r"[^A-Za-z .]", "", p).strip() for p in joined[:pin.start()].strip(" -,").split(",")]
			before = [p for p in before if p and p not in STATES.values()]  # "Ernakulam, Kerala - 683503"
			d["city"] = before[-1] if before else None
		else:
			d["city"] = re.sub(r"[^A-Za-z .]", "", joined.split(",")[-1]).strip() or None
	# Its state: "State Name : Kerala, Code : 32", "State: 32-Kerala", else its GSTIN's code.
	state = re.search(r"State\s*Name\s*:\s*([A-Za-z ]+?)\s*,\s*Code\s*:\s*(\d{2})", text) or \
		re.search(r"State\s*:\s*(\d{2})\s*-\s*([A-Za-z ]+)", text)
	if state:
		a, b = state.group(1).strip(), state.group(2).strip()
		code, named = (b, a) if a[:1].isalpha() else (a, b)
		d["state_code"], d["state"] = code, STATES.get(code, named.strip())
	elif gstin[:2] in STATES:
		d["state_code"], d["state"] = gstin[:2], STATES[gstin[:2]]
	seller = _BUYER_START.split(text, 1)[0]  # not the buyer's contact
	phone = re.search(r"(?:Contact|Phone|Mobile|Ph|Toll\s*Free)\s*(?:No\.?)?\s*[:;]\s*(\+?[\d][\d -]{6,}\d)", seller, re.IGNORECASE)
	if phone:
		d["phone"] = re.sub(r"\s+", " ", phone.group(1)).strip()
	email = re.search(r"(?:E-?Mail)\s*[:;]?\s*([\w.+-]+@[\w-]+\.[\w.]+)", seller, re.IGNORECASE)
	if email:
		d["email"] = email.group(1).strip(".")
	pan = _labelled(text, r"(?:Company'?s\s*)?PAN")
	pan = re.search(r"\b([A-Z]{5}\d{4}[A-Z])\b", pan.upper()) if pan else None
	d["pan"] = pan.group(1) if pan else (gstin[2:12] if len(gstin) == 15 else None)
	# Its bank account, from "Company's Bank Details".
	holder = _labelled(text, r"A/c\s*Holder'?s\s*Name")
	bank = _labelled(text, r"Bank\s*Name")
	account = _labelled(text, r"A/c\s*No\.?")
	branch_ifsc = _labelled(text, r"Branch\s*&\s*IFS\s*Code")
	swift = _labelled(text, r"SWIFT\s*Code")
	if holder:
		d["account_holder"] = holder
	if bank:
		d["bank_name"] = re.split(r"\s*[-,]?\s*\d", bank)[0].strip(" -,") or bank
	if account:
		number = re.search(r"\d[\d ]{5,}\d", account)
		d["account_no"] = re.sub(r"\s", "", number.group(0)) if number else account
	if branch_ifsc:
		ifsc = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", branch_ifsc.upper())
		if ifsc:
			d["ifsc"] = ifsc.group(1)
		place = re.split(r"\s*&\s*|\s+[A-Z]{4}0[A-Z0-9]{6}", branch_ifsc)[0].strip(" &,")
		if place and not re.fullmatch(r"[A-Z]{4}0[A-Z0-9]{6}", place.upper()):
			d["branch"] = place
	if swift:
		d["swift"] = swift.split()[0]
	_bank_by_label(text, d)
	d["gst_category"] = "Registered Regular" if gstin else "Unregistered"
	return {k: v for k, v in d.items() if v}


def _bank_by_label(text, d):
	"""A bank block not laid out as Tally's, its labels anywhere on a line as the OCR runs the
	columns together: "Name : Hdfe Bank", "AIC no.VISL78100081037", "IFSC: HDFC0000240",
	"Branch Address WORLI", "In favour of Vashi Integrated Solutions Limited."."""
	if not d.get("account_no"):
		m = re.search(r"\bA\s*[/I1l|]\s*C\.?\s*(?:No|Number)\.?\s*[:.]?\s*([A-Z0-9]*\d[A-Z0-9]{4,19})\b", text, re.IGNORECASE)
		if m:
			d["account_no"] = m.group(1).upper()
	if not d.get("ifsc"):
		m = re.search(r"\bIFS(?:C)?\s*(?:CODE)?\s*[:.]?\s*([A-Z]{4}0[A-Z0-9]{6})\b", text.upper())
		if m:
			d["ifsc"] = m.group(1)
	if not d.get("bank_name"):
		m = re.search(r"(?:Bank\s*)?Name\s*:\s*([A-Za-z][A-Za-z .&]*?\bBank)\b", text, re.IGNORECASE)
		known = IFSC_BANKS.get((d.get("ifsc") or "")[:4])
		if known or m:
			d["bank_name"] = known or m.group(1).strip()
	if not d.get("branch"):
		m = re.search(r"\bBranch(?:\s*Address)?\s*[:.]?\s*([A-Za-z][A-Za-z .-]{1,40}?)\s*$", text, re.IGNORECASE | re.MULTILINE)
		if m and "&" not in m.group(0):
			d["branch"] = m.group(1).strip(" .-")
	if not d.get("account_holder"):
		m = re.search(r"\bIn\s+favou?r\s+of\s+(" + COMPANY + r")", text) or \
			re.search(r"(?:Beneficiary|Account)\s*Name\s*:\s*([A-Z][^\n]{2,80}?)\s*(?:\s{2,}|$)", text, re.MULTILINE)
		if m:
			d["account_holder"] = re.sub(r"\s+", " ", m.group(1)).strip(" .,")


MONEY = r"[\d,]+\.\d{2}"
#: The head of a GST table that gives each line's CGST, SGST and IGST in columns.
GST_TABLE = re.compile(r"HSN.*?(?:CGST.*?(?:SGST|UTGST)|IGST)", re.IGNORECASE)
#: One of its rows, its borders taken out: Sr, HSN, whatever else is on the row, its quantity,
#: unit, and its figures - rate, discounts, net rate, taxable, each tax's rate and amount, total.
GST_ROW = re.compile(r"^\s*(?P<sl>\d{1,3})\s+(?P<hsn>\d{4,8})\s+(?P<mid>.*?)\s*(?P<qty>\d[\d,]*(?:\.\d+)?)\s+"
	r"(?P<uom>[A-Za-z]{1,6})\s+(?P<nums>(?:[\d,]+\.\d+\s*)+)$")
_TABLE_END = re.compile(r"^\s*(?:Packed\s*By|Checked\s*By|Total\b|Invoice\s*Total|Amount\s+in\s+Words)", re.IGNORECASE)


def _serial_line(line):
	"""The serials a line lists ("R1300035261 909972/R1300035261910258/"), the OCR's breaks in
	them taken out; else None."""
	joined = re.sub(r"(?<=\d) (?=\d)", "", line.strip())
	tokens = [t for t in re.split(r"[/,\s]+", joined) if t]
	if tokens and all(sum(c.isdigit() for c in t) >= 6 for t in tokens):
		return tokens
	return None


def _parse_gst_table(text, out):
	"""A tax invoice whose table gives each line's CGST, SGST and IGST in columns (Vashi
	Integrated Solutions', as its scan's OCR reads it):

		Sr | HSN/ SAC Item Code / Product Description Quantity UOM Rate ... CGST SGST/UTGST IGST Line Total
		Renewsys Solar I-RENEWSYS620N-TOPCON-G2G-BF
		R1300035261909972/R1300035261910258/
		1 | 85414300 R1300035261909802/R1300035261909733/ 16 EA | 8680.00 | 0.00 0.00 8680.00 |138880.00} 2.50 3472.00 2.50 | 3472.00 0.00 0.00 145824.00

	A line's description and serials are on the text lines around its row: those above it, and
	the serials under it up to the next description."""
	lines = text.split("\n")
	head = next((i for i, l in enumerate(lines) if GST_TABLE.search(l)), None)
	if head is None:
		return
	order = [k for k, pattern in (("cgst", r"CGST"), ("sgst", r"SGST|UTGST"), ("igst", r"IGST"))
		if re.search(pattern, lines[head], re.IGNORECASE)]
	same_state = (out.get("supplier_gstin") or "")[:2] == (out.get("buyer_gstin") or "")[:2]
	taxes = {"cgst": 0.0, "sgst": 0.0, "igst": 0.0}
	desc, serials, current = [], [], None
	for line in lines[head + 1:]:
		if _TABLE_END.match(line):
			break
		clean = re.sub(r"\s+", " ", re.sub(r"[|}\]\[{]", " ", line)).strip()
		if not clean or (re.search(r"(?i)\b(Rate|Amount|Per\s*Unit|Code)\b", clean) and not re.search(r"\d{3}", clean)):
			continue  # the table head's second line
		row = GST_ROW.match(clean)
		if row:
			qty, nums = _n(row.group("qty")), [_n(n) for n in row.group("nums").split()]
			# The taxable value: the first figure that is the quantity times a rate before it.
			at = next((j for j in range(1, len(nums)) if nums[j] > 0 and any(abs(nums[j] - qty * nums[k]) <= TOLERANCE
				for k in range(j))), None)
			if at is None or not qty:
				continue
			rate, taxable, total = nums[0], nums[at], nums[-1]
			pairs, line_tax, gst_rate = nums[at + 1:-1], {}, 0
			if len(pairs) == 2 * len(order):
				line_tax = {k: pairs[2 * i + 1] for i, k in enumerate(order)}
				gst_rate = sum(pairs[2 * i] for i, k in enumerate(order) if pairs[2 * i + 1])
			if not line_tax or abs(sum(line_tax.values()) - (total - taxable)) > TOLERANCE:
				tax = flt(total - taxable, 2)
				half = flt(tax / 2, 2)
				line_tax = {"cgst": half, "sgst": flt(tax - half, 2)} if same_state else {"igst": tax}
				gst_rate = round(tax / taxable * 100, 2) if taxable else 0
			for k, v in line_tax.items():
				taxes[k] = flt(taxes[k] + v, 2)
			mid = row.group("mid")
			mid_serials = _serial_line(mid) if mid else None
			if mid and not mid_serials:
				desc.append(mid)
			net = taxable / qty
			current = {"description": re.sub(r"\bl-(?=[A-Z])", "I-", " ".join(desc)).strip(), "hsn": row.group("hsn"),
				"gst_rate": flt(gst_rate), "qty": qty, "uom": row.group("uom"), "rate": rate,
				"discount": flt((1 - net / rate) * 100, 2) if rate and net < rate - 0.005 else 0.0,
				"amount": taxable, "serials": serials + (mid_serials or [])}
			out["lines"].append(current)
			desc, serials = [], []
			continue
		found = _serial_line(clean)
		if found:
			# Under a row, before the next description: that row's.
			(current["serials"] if current is not None and not desc else serials).extend(found)
		else:
			desc.append(clean)
	if current is not None and desc:  # a description printed under its row
		current["description"] = (current["description"] + " " + " ".join(desc)).strip()
	for row in out["lines"]:
		row["description"] = row["description"] or _("Item {0}").format(row["hsn"])
	if out["lines"] and not (out["cgst"] or out["sgst"] or out["igst"]):
		out.update(taxes)


def _bill_labels(text, out):
	"""The bill's number, date and total by their labels, where no Tally column gave them."""
	if not out.get("bill_no"):
		number = re.search(r"Invoice\s*No\.?\s*[:.;]?\s*\n?\s*([A-Za-z0-9/-]*\d[A-Za-z0-9/-]*)", text, re.IGNORECASE) or \
			re.search(r"(?<![A-Za-z])(?:Invoice|Bill)?\s*No\s*[.:;]\s*([A-Za-z0-9][A-Za-z0-9/-]*)", text, re.IGNORECASE)
		out["bill_no"] = number.group(1) if number else None
	if not out.get("bill_date"):
		date = re.search(r"Date\s*[.:;]?\s*\n?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})", text, re.IGNORECASE)
		out["bill_date"] = _date(date.group(1)) if date else None
	if not out.get("total"):
		total = re.search(r"^\s*(?:Invoice\s*|Grand\s*)?Total\b[^\n\d]*(" + MONEY + r")\s*$", text, re.IGNORECASE | re.MULTILINE)
		out["total"] = _n(total.group(1)) if total else None


def _parse_simple(text, out):
	"""A plain bill, not laid out as Tally's: a small supplier's, often unregistered - no GSTIN,
	HSN or GST (Tech Power Solutions' No. 7):

		TECH POWER SOLUTIONS ...  No: 7  Date: 03-10-2026
		1  5 kw solar flat roof structure installation ( Philip)   5   ₹ 2,700.00   ₹ 13,500.00
		Total : ₹ 13,500.00                      For TECH POWER SOLUTIONS:

	Read by its labels, as a photo's OCR gives them: a line is its number, its description and
	its rate and amount - the quantity, often lost to the table's borders, is the amount over
	the rate."""
	lines = text.replace("\r", "").split("\n")
	if not out.get("supplier_name"):
		signed = re.search(r"\bFor\s+([A-Z][A-Za-z0-9&.,()' -]{2,60}?)\s*:", text)
		if signed:
			out["supplier_name"] = re.sub(r"\s+", " ", signed.group(1)).strip(" .,")
		else:  # the bill's heading: its first run of capitalised words
			heading = next((m.group(1) for l in lines[:8] for m in [re.search(r"([A-Z][A-Z&.]+(?:\s+[A-Z][A-Z&.]+)+)", l)] if m), None)
			out["supplier_name"] = heading
	_bill_labels(text, out)
	for line in lines:
		m = re.match(r"^\s*(\d{1,3})\s*[|.]?\s*(\S.*\S)\s+(" + MONEY + r")\s+(?:\S{1,3}\s+)?(" + MONEY + r")\s*$", line)
		if not m or re.match(r"(?i)\s*(sub\s*)?total", m.group(2)):
			continue
		rate, amount = _n(m.group(3)), _n(m.group(4))
		if not rate or amount < rate:
			continue
		description = m.group(2)
		# The description, less the OCR's border noise after it ("ee eee) %").
		words = description.split()
		while words and (words[-1] in ("%", "=", "z", "₹", "Rs", "Rs.") or (len(re.sub(r"[^A-Za-z0-9]", "", words[-1])) <= 3
				and not re.search(r"\d", words[-1]) and not words[-1].endswith(")") or re.fullmatch(r"[a-z]{1,3}\)?", words[-1]))):
			words.pop()
		description = re.sub(r"^[|S]\s(?=kw|kW|KW)", "5 ", " ".join(words)).strip()
		qty = round(amount / rate, 3)
		out["lines"].append({"description": description, "hsn": "", "gst_rate": 0.0, "qty": qty, "uom": "Nos",
			"rate": rate, "discount": 0.0, "amount": amount, "serials": []})



def check(parsed, company=None):
	"""What does not add up on the bill, as sentences."""
	warnings = []
	rows = parsed.get("lines", []) + parsed.get("charges", [])
	if not rows:
		return [_("No item lines could be read from this bill. Check it is the supplier's tax invoice, as a PDF or a clear photo.")]
	taxable = flt(sum(flt(r["amount"]) for r in rows), 2)
	taxes = flt(parsed.get("cgst")) + flt(parsed.get("sgst")) + flt(parsed.get("igst"))
	worked = flt(taxable + taxes + flt(parsed.get("round_off")), 2)
	if parsed.get("total") and abs(worked - flt(parsed["total"])) > TOLERANCE:
		warnings.append(_("The lines and taxes come to {0}, but the bill's total is {1}: check the lines.").format(
			frappe.format_value(worked, {"fieldtype": "Currency"}), frappe.format_value(parsed["total"], {"fieldtype": "Currency"})))
	for r in parsed.get("lines", []):
		if abs(flt(r["qty"]) * flt(r["rate"]) * (1 - flt(r.get("discount")) / 100) - flt(r["amount"])) > TOLERANCE:
			warnings.append(_("{0}: {1} × {2} is not {3}.").format(r["description"], r["qty"], r["rate"], r["amount"]))
	own = frappe.db.get_value("Company", company, "gstin") if company and frappe.get_meta("Company").has_field("gstin") else None
	if own and parsed.get("buyer_gstin") and parsed["buyer_gstin"] != own:
		warnings.append(_("The bill is made out to GSTIN {0}, not the company's {1}.").format(parsed["buyer_gstin"], own))
	return warnings


# ------------------------------------------------------------------ the job, the supplier, the items
def _job(installation, ptype="read"):
	partner_scope.refuse_partners(_("Supplier invoices"))
	if not installation or not frappe.db.exists(INSTALLATION, installation):
		frappe.throw(_("No such project."), frappe.DoesNotExistError)
	inst = frappe.get_doc(INSTALLATION, installation)
	inst.check_permission(ptype)
	return inst


def is_supplier_bill_task(code):
	return code == CODE


def find_supplier(name=None, gstin=None):
	"""The Supplier the bill is from. Its GSTIN decides: with one, only the supplier holding that
	GSTIN is it. Without a match by GSTIN, a supplier of exactly that name counts only if it has no
	GSTIN on file yet - one with another GSTIN is another supplier, never this bill's."""
	gstin = (gstin or "").strip().upper()
	if gstin:
		found = frappe.db.get_value("Supplier", {"tax_id": gstin, "disabled": 0}, "name")
		if found:
			return found
	if name and name.strip():
		for row in frappe.get_all("Supplier", filters={"supplier_name": name.strip(), "disabled": 0}, fields=["name", "tax_id"]):
			if not row.tax_id or (gstin and row.tax_id.upper() == gstin):
				return row.name
	return None


def supplier_gstin(supplier):
	return (frappe.db.get_value("Supplier", supplier, "tax_id") or "").upper() if supplier else ""


def match_item(description):
	"""The ERPNext Item a bill line is, where its name says so; else None."""
	if not description:
		return None
	exact = frappe.db.get_value("Item", {"item_name": description, "disabled": 0}, "name")
	if exact:
		return exact
	return frappe.db.get_value("Item", {"item_code": description, "disabled": 0}, "name")


def _uom(unit):
	uom = UOMS.get((unit or "").strip().lower().rstrip("."), "Nos")
	return uom if frappe.db.exists("UOM", uom) else "Nos"


# ------------------------------------------------------------------ the page's calls
def _upload():
	upload = (frappe.request.files.getlist("file") or [None])[0] if frappe.request and frappe.request.files else None
	if not upload:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	content = upload.stream.read()
	if len(content) > get_max_file_size():
		frappe.throw(_("{0} is larger than {1} MB.").format(upload.filename, get_max_file_size() // (1024 * 1024)),
			frappe.ValidationError)
	return upload.filename, content


@frappe.whitelist(methods=["POST"])
def read(installation):
	"""Read the bill posted as `file` for the job: its lines to check, the supplier it is from
	(on file, or one to be made), each line's Item where one matches, and what does not add
	up. Nothing is saved."""
	inst = _job(installation, "write")
	filename, content = _upload()
	text, source = extract_text(content, filename)
	parsed = parse(text)
	supplier = find_supplier(parsed.get("supplier_name"), parsed.get("supplier_gstin"))
	for row in parsed["lines"] + parsed["charges"]:
		row["item_code"] = match_item(row["description"])
		row["item_tax_template"] = item_template_for(inst.company, row["gst_rate"])
	template = default_template(inst.company, parsed.get("supplier_gstin"), parsed.get("igst"))
	# A supplier on file whose invoice gives an account it does not hold: offered to be added.
	new_account = None
	read_bank = parsed.get("supplier_details") or {}
	if supplier and read_bank.get("account_no") and _digits(read_bank["account_no"]) not in [
			_digits(b["account_no"]) for b in bank_accounts(supplier)]:
		new_account = {k: read_bank.get(k) or "" for k in ("account_holder", "bank_name", "account_no", "ifsc", "swift")}
	return {
		"new_bank_account": new_account,
		"already_entered": already_entered(supplier, parsed.get("bill_no")),
		"name_check": name_check(inst, parsed.get("consignee")),
		"bill": parsed, "warnings": check(parsed, inst.company), "source": source,
		"tax_template": template, "choices": tax_choices(inst.company),
		"calculation": _calculation(_build(inst, {"lines": parsed["lines"] + parsed["charges"], "tax_template": template,
			"supplier_gstin": parsed.get("supplier_gstin")}), parsed),
		"supplier": {"name": supplier, "supplier_name": parsed.get("supplier_name"), "gstin": parsed.get("supplier_gstin"),
			"new": not supplier, "gstin_on_file": supplier_gstin(supplier),
			"details": dict(parsed.get("supplier_details") or {}, supplier_name=parsed.get("supplier_name") or "",
				gstin=parsed.get("supplier_gstin") or "") if not supplier else None},
		"supplier_groups": frappe.get_all("Supplier Group", pluck="name", order_by="lft asc") if not supplier else [],
		"default_supplier_group": (frappe.db.get_single_value("Buying Settings", "supplier_group") or "All Supplier Groups") if not supplier else None,
		"gst_categories": ((frappe.get_meta("Supplier").get_field("gst_category").options or "").split("\n")
			if frappe.get_meta("Supplier").has_field("gst_category") else []) if not supplier else [],
	}


#: The Item Tax Template a line's GST % reads as, by rate ("GST 18% - RIL"); 0% is Nil-Rated.
NIL_RATED = "Nil-Rated"


def tax_choices(company):
	"""The company's purchase tax templates (the invoice's) and item tax templates (each line's)."""
	return {
		"templates": frappe.get_all("Purchase Taxes and Charges Template", filters={"company": company, "disabled": 0},
			pluck="name", order_by="name asc"),
		"item_templates": frappe.get_all("Item Tax Template", filters={"company": company, "disabled": 0},
			pluck="name", order_by="name asc"),
	}


def default_template(company, supplier_gstin=None, igst=0):
	"""The invoice's tax template: in-state when the supplier's GSTIN is of the company's state
	(and the bill charges no IGST), else out-state - never a reverse-charge one by default."""
	own = frappe.db.get_value("Company", company, "gstin") if frappe.get_meta("Company").has_field("gstin") else None
	state_code = (own or "")[:2] or "32"
	out_state = flt(igst) > 0 or bool(supplier_gstin and supplier_gstin[:2] != state_code)
	names = [t for t in tax_choices(company)["templates"] if "rcm" not in t.lower()]
	pick = [t for t in names if ("out-state" in t.lower()) == out_state and ("in-state" in t.lower() or out_state)]
	return (pick or names or [None])[0]


def item_template_for(company, rate):
	"""The item tax template of a GST rate: "GST 5% - RIL"; Nil-Rated for none."""
	abbr = frappe.db.get_value("Company", company, "abbr")
	names = tax_choices(company)["item_templates"]
	wanted = "{0} - {1}".format(NIL_RATED, abbr) if not flt(rate) else "GST {0:g}% - {1}".format(flt(rate), abbr)
	return wanted if wanted in names else None


def _supplier(data):
	"""The bill's Supplier, worked out again from its GSTIN and name as they stand now - the one
	the page found when it read the bill only if the GSTIN still agrees - and made, with its
	GSTIN, the first time it bills. A supplier found by name alone is given the bill's GSTIN."""
	gstin = (data.get("supplier_gstin") or "").strip().upper()
	if gstin and not GSTIN.search("GSTIN: " + gstin):
		frappe.throw(_("{0} is not a GSTIN: check the supplier's GSTIN on the bill.").format(gstin), title=_("Supplier GSTIN"))
	sent = data.get("supplier")
	if sent and frappe.db.exists("Supplier", sent) and (not gstin or supplier_gstin(sent) in ("", gstin)):
		name = sent
	else:
		name = find_supplier(data.get("supplier_name"), gstin)
	if name:
		if gstin and not supplier_gstin(name):
			frappe.db.set_value("Supplier", name, "tax_id", gstin)
		return name
	frappe.throw(_("{0} is not a supplier in ERPNext yet: create the supplier first, from the invoice's details.").format(
		(data.get("supplier_name") or "").strip() or _("The bill's supplier")), title=_("Create the Supplier First"))


@frappe.whitelist(methods=["POST"])
def create_supplier(installation, details=None):
	"""A new supplier, from what its invoice says of it (supplier_details, as checked on the
	page): the Supplier with its GSTIN, PAN and GST category, its address and contact, and its bank
	account where the bill gives one. A supplier already holding that GSTIN is returned, not made
	twice. Returns {supplier, name, gstin}."""
	inst = _job(installation, "write")
	if not frappe.has_permission("Supplier", "create"):
		frappe.throw(_("You may not add suppliers. Ask Accounts to add it."), frappe.PermissionError)
	d = frappe._dict(frappe.parse_json(details) if isinstance(details, str) else (details or {}))
	title = (d.get("supplier_name") or "").strip()
	if not title:
		frappe.throw(_("Enter the supplier's name."))
	gstin = (d.get("gstin") or "").strip().upper()
	if gstin and not GSTIN.search("GSTIN: " + gstin):
		frappe.throw(_("{0} is not a GSTIN.").format(gstin), title=_("Supplier GSTIN"))
	existing = find_supplier(title, gstin) if gstin else None
	if existing:
		return {"supplier": existing, "name": frappe.db.get_value("Supplier", existing, "supplier_name"), "gstin": gstin, "existed": True}
	own = (frappe.db.get_value("Company", inst.company, "gstin") or "")[:2] if frappe.get_meta("Company").has_field("gstin") else ""
	code = (d.get("state_code") or gstin[:2] or "").strip()
	out_state = bool(code and (own or "32") != code)
	meta = frappe.get_meta("Supplier")
	values = {"doctype": "Supplier", "supplier_name": title, "supplier_type": "Company", "country": "India",
		"supplier_group": d.get("supplier_group") or frappe.db.get_single_value("Buying Settings", "supplier_group") or "All Supplier Groups",
		"tax_id": gstin or None}
	if meta.has_field("gstin"):
		values["gstin"] = gstin or None
	if meta.has_field("pan"):
		values["pan"] = (d.get("pan") or (gstin[2:12] if gstin else "") or "").upper() or None
	if meta.has_field("gst_category"):
		values["gst_category"] = d.get("gst_category") or ("Registered Regular" if gstin else "Unregistered")
	if frappe.db.exists("Tax Category", "Out-State" if out_state else "In-State"):
		values["tax_category"] = "Out-State" if out_state else "In-State"
	doc = frappe.get_doc(values)
	# Another supplier of that name, with another GSTIN, is another firm: named apart by its GSTIN.
	name = doc.insert(set_name="{0} - {1}".format(title, gstin or frappe.generate_hash(length=5))).name \
		if frappe.db.exists("Supplier", title) else doc.insert().name
	link = [{"link_doctype": "Supplier", "link_name": name}]
	if d.get("address_line1") or d.get("city"):
		address = {"doctype": "Address", "address_title": title, "address_type": "Billing",
			"address_line1": (d.get("address_line1") or d.get("city"))[:140], "address_line2": (d.get("address_line2") or "")[:140] or None,
			"city": d.get("city") or d.get("address_line1"), "state": d.get("state") or None, "pincode": d.get("pincode") or None,
			"country": "India", "phone": d.get("phone") or None, "email_id": d.get("email") or None,
			"is_primary_address": 1, "links": link}
		amed = frappe.get_meta("Address")
		if amed.has_field("gstin"):
			address["gstin"] = gstin or None
		field = amed.get_field("gst_state")
		if field and d.get("state") and d.state in (field.options or "").split("\n"):
			address["gst_state"] = d.state
		frappe.db.set_value("Supplier", name, "supplier_primary_address", frappe.get_doc(address).insert().name)
	if d.get("phone") or d.get("email"):
		contact = frappe.get_doc({"doctype": "Contact", "first_name": title[:140], "is_primary_contact": 1, "links": link,
			"phone_nos": [{"phone": d.phone, "is_primary_phone": 1, "is_primary_mobile_no": 1}] if d.get("phone") else [],
			"email_ids": [{"email_id": d.email, "is_primary": 1}] if d.get("email") else []}).insert()
		frappe.db.set_value("Supplier", name, "supplier_primary_contact", contact.name)
	if d.get("account_no") and d.get("bank_name"):
		if not frappe.db.exists("Bank", d.bank_name):
			frappe.get_doc({"doctype": "Bank", "bank_name": d.bank_name, "swift_number": d.get("swift") or None}).insert()
		_insert_bank_account(frappe.get_doc({"doctype": "Bank Account", "account_name": (d.get("account_holder") or title)[:140],
			"bank": d.bank_name, "party_type": "Supplier", "party": name, "bank_account_no": d.account_no,
			"branch_code": d.get("ifsc") or None, "is_default": 1, "is_company_account": 0}))
	return {"supplier": name, "name": title, "gstin": gstin, "existed": False}


def _insert_bank_account(account):
	"""ERPNext names a bank account "<holder> - <bank>": another supplier's account of that holder and
	bank is told apart by its supplier."""
	default = "{0} - {1}".format(account.account_name, account.bank)
	if frappe.db.exists("Bank Account", default):
		return account.insert(set_name="{0} - {1}".format(default, account.party))
	return account.insert()


def _digits(value):
	return re.sub(r"\D", "", value or "")


def bank_accounts(supplier):
	"""The supplier's bank accounts - not those removed - its default first."""
	if not supplier:
		return []
	rows = frappe.get_all("Bank Account", filters={"party_type": "Supplier", "party": supplier, "disabled": 0},
		fields=["name", "account_name", "bank", "bank_account_no", "branch_code", "is_default"], order_by="is_default desc, creation asc")
	return [{"name": r.name, "account_holder": r.account_name or "", "bank_name": r.bank or "", "account_no": r.bank_account_no or "",
		"ifsc": r.branch_code or "", "swift": frappe.db.get_value("Bank", r.bank, "swift_number") or "" if r.bank else "",
		"is_default": int(r.is_default or 0)} for r in rows]


def _save_bank_account(supplier, a, holder_default):
	"""One account of the supplier, saved: an existing one (by `name`, else by its account no.)
	updated, a new one added. Returns its name."""
	if not (a.get("account_no") and a.get("bank_name")):
		return None
	if not frappe.db.exists("Bank", a["bank_name"]):
		frappe.get_doc({"doctype": "Bank", "bank_name": a["bank_name"], "swift_number": a.get("swift") or None}).insert()
	elif a.get("swift"):
		frappe.db.set_value("Bank", a["bank_name"], "swift_number", a["swift"])
	name = a.get("name") if a.get("name") and frappe.db.get_value("Bank Account", a.get("name"), "party") == supplier else None
	if not name:  # the same account no. already on the supplier is that account, not another
		name = next((b["name"] for b in bank_accounts(supplier) if _digits(b["account_no"]) == _digits(a["account_no"])), None)
	account = frappe.get_doc("Bank Account", name) if name else frappe.get_doc({"doctype": "Bank Account",
		"party_type": "Supplier", "party": supplier, "is_company_account": 0})
	account.update({"account_name": (a.get("account_holder") or holder_default)[:140], "bank": a["bank_name"],
		"bank_account_no": re.sub(r"\s+", "", a["account_no"]), "branch_code": (a.get("ifsc") or "").strip().upper() or None, "disabled": 0})
	if name:
		account.save()
	else:
		_insert_bank_account(account)
	return account.name


def _set_default_account(supplier, keep):
	for b in frappe.get_all("Bank Account", filters={"party_type": "Supplier", "party": supplier}, pluck="name"):
		frappe.db.set_value("Bank Account", b, "is_default", 1 if b == keep else 0)


@frappe.whitelist(methods=["POST"])
def add_bank_account(installation, supplier, details=None):
	"""A bank account an invoice gives, added to its supplier - the one firm, its accounts in one
	place. An account no. it already holds is that account."""
	_job(installation)
	sup = _supplier_doc(supplier)
	if not frappe.has_permission("Supplier", "write", sup.name):
		frappe.throw(_("You may not change suppliers. Ask Accounts to change it."), frappe.PermissionError)
	a = frappe._dict(frappe.parse_json(details) if isinstance(details, str) else (details or {}))
	if not (a.get("account_no") and a.get("bank_name")):
		frappe.throw(_("Enter the bank name and the account no."))
	had = bank_accounts(sup.name)
	name = _save_bank_account(sup.name, a, sup.supplier_name)
	if not had or not any(b["is_default"] for b in had):
		_set_default_account(sup.name, name)
	return {"account": name, "bank_accounts": bank_accounts(sup.name)}


def _supplier_doc(supplier):
	if not supplier or not frappe.db.exists("Supplier", supplier):
		frappe.throw(_("No such supplier."), frappe.DoesNotExistError)
	return frappe.get_doc("Supplier", supplier)


def _linked(doctype, supplier, primary_field=None):
	"""The supplier's primary Address or Contact - else the first linked to it."""
	if primary_field:
		name = frappe.db.get_value("Supplier", supplier, primary_field)
		if name and frappe.db.exists(doctype, name):
			return frappe.get_doc(doctype, name)
	name = frappe.db.get_value("Dynamic Link", {"parenttype": doctype, "link_doctype": "Supplier", "link_name": supplier}, "parent")
	return frappe.get_doc(doctype, name) if name else None


@frappe.whitelist()
def supplier_profile(installation, supplier):
	"""What the supplier pop-up shows and edits: the supplier, its address, contact and bank
	account, as the New supplier form lays them out."""
	_job(installation)
	sup = _supplier_doc(supplier)
	address = _linked("Address", sup.name, "supplier_primary_address")
	contact = _linked("Contact", sup.name, "supplier_primary_contact")
	d = {"supplier_name": sup.supplier_name, "gstin": sup.get("gstin") or sup.tax_id or "", "pan": sup.get("pan") or "",
		"gst_category": sup.get("gst_category") or "", "supplier_group": sup.supplier_group or ""}
	if address:
		d.update({"address_line1": address.address_line1 or "", "address_line2": address.address_line2 or "", "city": address.city or "",
			"state": address.state or "", "pincode": address.pincode or "", "phone": address.phone or "", "email": address.email_id or ""})
	if contact:
		d["phone"] = d.get("phone") or contact.phone or contact.mobile_no or ""
		d["email"] = d.get("email") or contact.email_id or ""
	d["bank_accounts"] = bank_accounts(sup.name)
	return {"supplier": sup.name, "details": d,
		"supplier_groups": frappe.get_all("Supplier Group", pluck="name", order_by="lft asc"),
		"gst_categories": (frappe.get_meta("Supplier").get_field("gst_category").options or "").split("\n")
			if frappe.get_meta("Supplier").has_field("gst_category") else [],
		"can_edit": bool(frappe.has_permission("Supplier", "write", sup.name))}


@frappe.whitelist(methods=["POST"])
def update_supplier(installation, supplier, details=None):
	"""The supplier's details as changed in the pop-up: the Supplier, and its primary address,
	contact and bank account - each made where it has none yet."""
	_job(installation)
	sup = _supplier_doc(supplier)
	if not frappe.has_permission("Supplier", "write", sup.name):
		frappe.throw(_("You may not change suppliers. Ask Accounts to change it."), frappe.PermissionError)
	d = frappe._dict(frappe.parse_json(details) if isinstance(details, str) else (details or {}))
	gstin = (d.get("gstin") or "").strip().upper()
	if gstin and not GSTIN.search("GSTIN: " + gstin):
		frappe.throw(_("{0} is not a GSTIN.").format(gstin), title=_("Supplier GSTIN"))
	other = frappe.db.get_value("Supplier", {"tax_id": gstin, "name": ["!=", sup.name]}, "name") if gstin else None
	if other:
		frappe.throw(_("GSTIN {0} is already {1}'s.").format(gstin, other), title=_("Supplier GSTIN"))
	if (d.get("supplier_name") or "").strip():
		sup.supplier_name = d.supplier_name.strip()
	sup.tax_id = gstin or None
	if sup.meta.has_field("gstin"):
		sup.gstin = gstin or None
	if sup.meta.has_field("pan"):
		sup.pan = (d.get("pan") or "").strip().upper() or None
	if sup.meta.has_field("gst_category") and d.get("gst_category"):
		sup.gst_category = d.gst_category
	if d.get("supplier_group"):
		sup.supplier_group = d.supplier_group
	sup.save()
	link = {"link_doctype": "Supplier", "link_name": sup.name}
	address = _linked("Address", sup.name, "supplier_primary_address")
	if d.get("address_line1") or d.get("city") or address:
		address = address or frappe.get_doc({"doctype": "Address", "address_title": sup.supplier_name, "address_type": "Billing",
			"country": "India", "is_primary_address": 1, "links": [link]})
		address.update({"address_line1": (d.get("address_line1") or d.get("city") or address.address_line1 or "")[:140],
			"address_line2": (d.get("address_line2") or "")[:140] or None, "city": d.get("city") or d.get("address_line1") or address.city,
			"state": d.get("state") or None, "pincode": d.get("pincode") or None, "phone": d.get("phone") or None,
			"email_id": d.get("email") or None})
		if address.meta.has_field("gstin"):
			address.gstin = gstin or None
		field = address.meta.get_field("gst_state")
		if field and d.get("state") and d.state in (field.options or "").split("\n"):
			address.gst_state = d.state
		address.save()
		frappe.db.set_value("Supplier", sup.name, "supplier_primary_address", address.name)
	contact = _linked("Contact", sup.name, "supplier_primary_contact")
	if d.get("phone") or d.get("email") or contact:
		contact = contact or frappe.get_doc({"doctype": "Contact", "first_name": sup.supplier_name[:140], "is_primary_contact": 1, "links": [link]})
		if d.get("phone") and not any(p.phone == d.phone for p in contact.phone_nos):
			for p in contact.phone_nos:
				p.is_primary_phone = p.is_primary_mobile_no = 0
			contact.append("phone_nos", {"phone": d.phone, "is_primary_phone": 1, "is_primary_mobile_no": 1})
		if d.get("email") and not any(e.email_id == d.email for e in contact.email_ids):
			for e in contact.email_ids:
				e.is_primary = 0
			contact.append("email_ids", {"email_id": d.email, "is_primary": 1})
		contact.save()
		frappe.db.set_value("Supplier", sup.name, "supplier_primary_contact", contact.name)
	# Its bank accounts, as the pop-up lists them: updated, added, removed (disabled - payments
	# may point at one), exactly one the default.
	rows = d.get("bank_accounts")
	if rows is None and d.get("account_no"):  # one account, as the fields used to give it
		rows = [{"account_holder": d.get("account_holder"), "bank_name": d.get("bank_name"), "account_no": d.get("account_no"),
			"ifsc": d.get("ifsc"), "swift": d.get("swift"), "is_default": 1}]
	if rows is not None:
		default = None
		for row in rows:
			row = frappe._dict(row)
			if row.get("remove"):
				if row.get("name") and frappe.db.get_value("Bank Account", row.name, "party") == sup.name:
					frappe.db.set_value("Bank Account", row.name, {"disabled": 1, "is_default": 0})
				continue
			name = _save_bank_account(sup.name, row, sup.supplier_name)
			if name and (row.get("is_default") or not default):
				default = name if row.get("is_default") or default is None else default
		live = bank_accounts(sup.name)
		if live:
			_set_default_account(sup.name, default if default in [b["name"] for b in live] else live[0]["name"])
	return supplier_profile(installation, sup.name)


def _rows(data):
	rows = [frappe._dict(r) for r in (data.get("lines") or [])]
	return [r for r in rows if flt(r.get("qty")) and (r.get("description") or "").strip()]


def _build(inst, data, supplier=None):
	"""The bill as an unsaved Purchase Invoice in ERPNext's own tax format: the invoice's tax
	template (its CGST + SGST, or IGST, rows "On Net Total"), each line's item tax template
	setting that line's rates, and ERPNext's calculation of every line's tax, the totals and
	the rounding. The page's preview and the invoice entered are the same build."""
	from erpnext.controllers.accounts_controller import get_taxes_and_charges
	from erpnext.stock.get_item_details import get_item_tax_map

	company = inst.company
	expense = frappe.db.get_value("Company", company, "default_expense_account")
	cost_center = frappe.db.get_value("Company", company, "cost_center")
	currency = frappe.db.get_value("Company", company, "default_currency") or "INR"
	template = data.get("tax_template") or default_template(company, data.get("supplier_gstin"))
	pi = frappe.new_doc("Purchase Invoice")
	pi.update({
		"company": company, "supplier": supplier, "bill_no": (data.get("bill_no") or "").strip() or None,
		"bill_date": data.get("bill_date") or None, "posting_date": today(), "set_posting_time": 1,
		"solar_installation": inst.name, "a3s_material_bill": 1, "project": inst.get("project") or None,
		"update_stock": 0, "currency": currency, "conversion_rate": 1, "price_list_currency": currency,
		"plc_conversion_rate": 1, "taxes_and_charges": template,
		"tax_category": ("Out-State" if template and "out-state" in template.lower() else "In-State")
		if frappe.db.exists("Tax Category", "In-State") else None,
		"remarks": _("Material for {0} ({1}), bill {2}.").format(inst.name, inst.get("consumer_name") or "",
			data.get("bill_no") or ""),
	})
	for r in _rows(data):
		description = r.description.strip()
		if r.get("serials"):
			serials = r.serials if isinstance(r.serials, list) else str(r.serials).split()
			description += "\n" + _("Serial nos.: {0}").format(", ".join(serials))
		# The bill is the job's material bought outright - shipped to the site, no goods receipt
		# behind it - so a line matched to a stock item names it rather than links it: linked,
		# ERPNext would hold its amount in Stock Received But Not Billed for a receipt never made.
		item = r.get("item_code") if r.get("item_code") and frappe.db.exists("Item", r.get("item_code")) else None
		if item and cint(frappe.db.get_value("Item", item, "is_stock_item")):
			description += "\n" + _("Item: {0}").format(item)
			item = None
		item_template = r.get("item_tax_template") or item_template_for(company, r.get("gst_rate"))
		pi.append("items", {
			"item_code": item, "item_name": r.description.strip()[:140], "description": description,
			"gst_hsn_code": r.get("hsn") or None, "qty": flt(r.qty), "uom": _uom(r.get("uom")),
			"stock_uom": _uom(r.get("uom")), "conversion_factor": 1, "rate": flt(r.rate),
			"discount_percentage": flt(r.get("discount")), "expense_account": None if item else expense,
			"cost_center": cost_center, "item_tax_template": item_template,
			"item_tax_rate": get_item_tax_map(company, item_template) if item_template else "{}",
		})
	for tax in (get_taxes_and_charges("Purchase Taxes and Charges Template", template) or []) if template else []:
		tax.setdefault("cost_center", cost_center)
		pi.append("taxes", tax)
	pi.calculate_taxes_and_totals()
	return pi


def _calculation(pi, bill=None):
	"""ERPNext's calculation of the invoice, as the page shows it: each line's taxable amount,
	its taxes at the line's own rates and its total; each tax; the totals and rounding - and
	the bill's own figures beside them."""
	precision = pi.precision("tax_amount", "taxes") if pi.get("taxes") else 2
	lines = []
	for row in pi.items:
		rates = frappe.parse_json(row.item_tax_rate or "{}") or {}
		taxes = []
		for tax in pi.taxes:
			rate = flt(rates[tax.account_head]) if tax.account_head in rates else flt(tax.rate)
			taxes.append({"account": tax.account_head, "label": tax.description or tax.account_head,
				"rate": rate, "amount": flt(flt(row.net_amount) * rate / 100, precision)})
		lines.append({"idx": row.idx, "item_tax_template": row.item_tax_template, "net_amount": flt(row.net_amount),
			"taxes": taxes, "total": flt(flt(row.net_amount) + sum(t["amount"] for t in taxes), 2)})
	out = {
		"tax_template": pi.taxes_and_charges, "lines": lines,
		"taxes": [{"account": t.account_head, "label": t.description or t.account_head, "rate": flt(t.rate),
			"amount": flt(t.tax_amount)} for t in pi.taxes],
		"net_total": flt(pi.net_total), "total_taxes": flt(pi.total_taxes_and_charges), "grand_total": flt(pi.grand_total),
		"rounding_adjustment": flt(pi.rounding_adjustment), "rounded_total": flt(pi.rounded_total or pi.grand_total),
		"warnings": [],
	}
	if bill and flt(bill.get("total")):
		out["bill"] = {k: flt(bill.get(k)) for k in ("cgst", "sgst", "igst", "round_off", "total")}
		if abs(out["rounded_total"] - flt(bill["total"])) > TOLERANCE:
			out["warnings"].append(_("ERPNext works the invoice out to {0}, but the bill says {1}: check each line's tax template and the lines.").format(
				frappe.format_value(out["rounded_total"], {"fieldtype": "Currency"}),
				frappe.format_value(flt(bill["total"]), {"fieldtype": "Currency"})))
	return out


# ------------------------------------------------------------------ paid or unpaid
PAID, UNPAID = "Paid", "Unpaid"
#: The modes a supplier is mostly paid by, offered first and in this order; the rest follow by name.
PAYMENT_MODES_FIRST = ("NEFT/RTGS", "UPI")
#: "Paid from" meaning an employee paid it: paid from the company's Employee Reimbursement account
#: (patches/v1_2/employee_reimbursement_account), with the employee's claim raised for it.
REIMBURSEMENT = "Reimbursement"
REIMBURSEMENT_ACCOUNT = "Employee Reimbursement"


def reimbursement_account(company):
	return frappe.db.get_value("Account", {"company": company, "account_name": REIMBURSEMENT_ACCOUNT, "is_group": 0}, "name")


def claimants():
	"""Who may have paid it: the enabled staff, by name - the person signed in first."""
	me = frappe.session.user
	users = frappe.get_all("User", filters={"enabled": 1, "user_type": "System User", "name": ["not in", ["Guest"]]},
		fields=["name", "full_name"], order_by="full_name asc")
	users.sort(key=lambda u: u.name != me)
	return [{"user": u.name, "name": u.full_name or u.name} for u in users]


def payment_choices(company):
	"""What a payment is made by and from: the enabled modes of payment (each with its own
	account where it has one) and the company's bank and cash accounts."""
	accounts = frappe.get_all("Account", filters={"company": company, "is_group": 0, "disabled": 0,
		"account_type": ["in", ["Bank", "Cash"]]}, fields=["name", "account_type"], order_by="account_type asc, name asc")
	banks = [a.name for a in accounts if a.account_type == "Bank"]
	modes = []
	for m in frappe.get_all("Mode of Payment", filters={"enabled": 1}, fields=["name", "type"], order_by="name asc"):
		own = frappe.db.get_value("Mode of Payment Account", {"parent": m.name, "company": company}, "default_account")
		modes.append({"name": m.name, "type": m.type, "account": own or (banks[0] if m.type == "Bank" and banks else
			next((a.name for a in accounts if a.account_type == "Cash"), None))})
	first = {name: i for i, name in enumerate(PAYMENT_MODES_FIRST)}
	modes.sort(key=lambda m: (first.get(m["name"], len(first)), m["name"]))
	default = modes[0] if modes else None
	accounts = [a.name for a in accounts if a.name != reimbursement_account(company)]
	return {"modes": modes, "accounts": accounts, "default_mode": default["name"] if default else None,
		"reimbursement": bool(reimbursement_account(company)), "claimants": claimants(), "me": frappe.session.user}


def _proof():
	"""The payment proof posted as `proof`, as (file name, content) - or None."""
	upload = (frappe.request.files.getlist("proof") or [None])[0] if frappe.request and frappe.request.files else None
	if not upload:
		return None
	content = upload.stream.read()
	if len(content) > get_max_file_size():
		frappe.throw(_("{0} is larger than {1} MB.").format(upload.filename, get_max_file_size() // (1024 * 1024)),
			frappe.ValidationError)
	return upload.filename, content


def _check_payment(payment, proof):
	payment = frappe._dict(payment or {})
	if payment.get("status") != PAID:
		return None
	if not (payment.get("reference_no") or "").strip() and not proof:
		frappe.throw(_("Enter the transaction number or attach the payment proof to mark it paid."),
			title=_("Payment Proof Needed"))
	if not payment.get("mode") or not frappe.db.exists("Mode of Payment", payment.mode):
		frappe.throw(_("Choose how it was paid."))
	if not payment.get("account"):
		frappe.throw(_("Choose the account it was paid from."))
	if payment.account == REIMBURSEMENT:
		if not payment.get("claimant") or not frappe.db.exists("User", payment.claimant):
			frappe.throw(_("Choose the employee who paid it."))
		if flt(payment.get("amount")) <= 0:
			frappe.throw(_("Enter the amount to reimburse."))
	return payment


def _party_account(supplier, chosen=None):
	"""The supplier's bank account a payment goes into: the one chosen - only one of that supplier's
	own - else its default, else none."""
	accounts = bank_accounts(supplier)
	if chosen:
		if chosen not in [a["name"] for a in accounts]:
			frappe.throw(_("{0} is not a bank account of {1}.").format(chosen, supplier), title=_("Pay To"))
		return chosen
	return accounts[0]["name"] if accounts else None


def _pay(pi, payment, proof=None):
	"""Pay the bill in ERPNext's way: a Payment Entry against it, submitted - the invoice is then
	Paid. A bank payment needs a reference; a proof alone stands as one."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	if not frappe.has_permission("Payment Entry", "create"):
		frappe.throw(_("You may not enter payments."), frappe.PermissionError)
	paid_on = payment.get("paid_on") or today()
	reference = (payment.get("reference_no") or "").strip() or _("Proof attached: {0}").format(proof[0])[:140]
	reimbursed = payment.account == REIMBURSEMENT
	account = reimbursement_account(pi.company) if reimbursed else payment.account
	if not account:
		frappe.throw(_("The company has no Employee Reimbursement account to pay it from."))
	outstanding = flt(pi.outstanding_amount)
	amount = flt(payment.get("amount")) if reimbursed else outstanding
	if amount > outstanding + 0.005:
		frappe.throw(_("{0} is more than the {1} due on the bill.").format(
			frappe.format_value(amount, {"fieldtype": "Currency"}), frappe.format_value(outstanding, {"fieldtype": "Currency"})))
	pe = get_payment_entry("Purchase Invoice", pi.name, party_amount=amount)
	pe.party_bank_account = _party_account(pi.supplier, payment.get("party_bank_account")) or pe.get("party_bank_account")
	pe.mode_of_payment = payment.mode
	pe.paid_from = account
	pe.paid_from_account_currency = frappe.db.get_value("Account", account, "account_currency") or pi.currency
	pe.posting_date = paid_on
	pe.reference_no = reference
	pe.reference_date = paid_on
	who = frappe.utils.get_fullname(payment.claimant) if reimbursed else None
	pe.remarks = _("Supplier bill {0} ({1}) for {2}: paid by {3}, reference {4}.").format(
		pi.bill_no or pi.name, pi.name, pi.get("solar_installation") or "",
		_("{0}, to be reimbursed").format(who) if reimbursed else payment.mode, reference)
	pe.insert()
	pe.submit()
	file_url = None
	if proof:
		file_url = frappe.get_doc({"doctype": "File", "file_name": proof[0], "content": proof[1], "is_private": 1,
			"attached_to_doctype": "Payment Entry", "attached_to_name": pe.name}).insert(ignore_permissions=True).file_url
	if reimbursed:
		# The employee's claim, Pending Approval: approved and paid back as every claim is.
		from a3_sola.solar_operations.doctype.expense_reimbursement.expense_reimbursement import raise_claim

		claim = raise_claim(pi.solar_installation, CODE, amount,
			_("Supplier bill {0} paid to {1}").format(pi.bill_no or pi.name, pi.supplier_name or pi.supplier),
			expense_date=paid_on, remarks=_("Paid as {0}, reference {1}; Payment Entry {2}.").format(payment.mode, reference, pe.name),
			receipt=file_url, source_doctype="Purchase Invoice", source_document=pi.name, claimant=payment.claimant)
		pe.db_set("remarks", pe.remarks + " " + _("Claim {0}.").format(claim.name), update_modified=False)
	return pe.name


def _payments(invoice):
	from a3_sola.www.a3solaportal.collections import record_route

	rows = frappe.db.sql("""select pe.name, pe.reference_no, pe.reference_date, pe.mode_of_payment, ref.allocated_amount,
			pe.party_bank_account
		from `tabPayment Entry` pe join `tabPayment Entry Reference` ref on ref.parent = pe.name
		where ref.reference_doctype = 'Purchase Invoice' and ref.reference_name = %s and pe.docstatus = 1
		order by pe.posting_date""", invoice, as_dict=True)
	for r in rows:
		r["reference_date"] = frappe.utils.formatdate(r.reference_date, "dd-MM-yyyy") if r.reference_date else ""
		r["allocated_amount"] = flt(r.allocated_amount)
		acct = frappe.db.get_value("Bank Account", r.party_bank_account, ["bank", "bank_account_no"], as_dict=True) if r.party_bank_account else None
		r["paid_into"] = "{0} \u2026{1}".format(acct.bank, (acct.bank_account_no or "")[-4:]) if acct else ""
		r["proof_url"] = frappe.db.get_value("File", {"attached_to_doctype": "Payment Entry", "attached_to_name": r.name}, "file_url")
		r["url"] = record_route("payment-entries", r.name)  # the portal's own page of it
		claim = frappe.db.get_value("Expense Reimbursement", {"source_doctype": "Purchase Invoice", "source_document": invoice,
			"remarks": ["like", "%" + r.name + "%"]}, ["name", "claimant_name", "status"], as_dict=True)
		r["claim"] = {"name": claim.name, "who": claim.claimant_name, "status": claim.status,
			"url": record_route("reimbursements", claim.name)} if claim else None
	return rows


@frappe.whitelist(methods=["POST"])
def mark_paid(installation, invoice, payment=None):
	"""An entered bill of the job, paid: its Payment Entry made with the transaction number or the
	proof posted as `proof`."""
	inst = _job(installation, "write")
	bill = frappe.db.get_value("Purchase Invoice", invoice, ["name", "solar_installation", "a3s_material_bill",
		"docstatus", "outstanding_amount"], as_dict=True)
	if not bill or bill.solar_installation != inst.name or not bill.a3s_material_bill:
		frappe.throw(_("{0} is not a supplier bill of this project.").format(invoice), frappe.PermissionError)
	if bill.docstatus != 1:
		frappe.throw(_("{0} is not submitted.").format(invoice))
	if flt(bill.outstanding_amount) <= 0:
		frappe.throw(_("{0} is already paid.").format(invoice), title=_("Already Paid"))
	proof = _proof()
	payment = _check_payment(dict(frappe.parse_json(payment) if isinstance(payment, str) else (payment or {}), status=PAID), proof)
	_pay(frappe.get_doc("Purchase Invoice", invoice), payment, proof)
	return state(installation)


def already_entered(supplier, bill_no):
	"""The Purchase Invoice a supplier's bill no. is already entered as - with the project it is on -
	or None. One bill is entered once."""
	if not (supplier and bill_no):
		return None
	from a3_sola.www.a3solaportal.collections import record_route

	row = frappe.db.get_value("Purchase Invoice", {"supplier": supplier, "bill_no": bill_no.strip(), "docstatus": ["<", 2]},
		["name", "solar_installation", "status", "docstatus"], as_dict=True)
	if not row:
		return None
	customer = frappe.db.get_value(INSTALLATION, row.solar_installation, "consumer_name") if row.solar_installation else None
	return {"invoice": row.name, "url": record_route("purchase-invoices", row.name), "status": row.status,
		"draft": row.docstatus == 0, "project": row.solar_installation, "customer": customer or "",
		"project_url": record_route("projects", row.solar_installation) if row.solar_installation else ""}


def _duplicate_message(dup, bill_no, supplier):
	where = _(" on project {0} ({1})").format(dup["project"], dup["customer"]) if dup.get("project") else ""
	return _("Bill {0} from {1} is already entered as {2}{3}. To enter it again, cancel {2} first.").format(
		bill_no, supplier, dup["invoice"], where)


def name_check(inst, consignee):
	"""Whether the bill's consignee is the job's customer ("Manoj P" is "P MANOJ"): a bill for
	another customer's material is entered on this job only once someone confirms it."""
	from a3_sola.api.approval_letter import same_person

	customer = inst.get("consumer_name") or ""
	matches = not consignee or not customer or same_person(consignee, customer)
	return {"bill_name": consignee or "", "customer": customer, "matches": matches}


@frappe.whitelist(methods=["POST"])
def preview(installation, data=None):
	"""ERPNext's calculation of the bill as checked on the page - nothing is saved."""
	inst = _job(installation, "write")
	data = frappe._dict(frappe.parse_json(data) if isinstance(data, str) else (data or {}))
	return _calculation(_build(inst, data), data.get("bill"))


@frappe.whitelist(methods=["POST"])
def create(installation, data=None):
	"""The bill, as checked on the page (`data`: supplier, bill no. and date, its tax template,
	lines with their item tax templates), entered as a submitted Purchase Invoice on the job -
	the PDF posted as `file` attached. One bill no. is entered once per supplier."""
	inst = _job(installation, "write")
	if not frappe.has_permission("Purchase Invoice", "create"):
		frappe.throw(_("You may not enter purchase invoices."), frappe.PermissionError)
	data = frappe._dict(frappe.parse_json(data) if isinstance(data, str) else (data or {}))
	if not _rows(data):
		frappe.throw(_("The bill has no lines to enter."))
	bill_no = (data.get("bill_no") or "").strip()
	if not bill_no:
		frappe.throw(_("Enter the supplier's bill number."))
	proof = _proof()
	payment = _check_payment(data.get("payment"), proof)  # before anything is entered
	check = name_check(inst, data.get("consignee"))
	if not check["matches"] and not cint(data.get("name_confirmed")):
		frappe.throw(_("This bill is for {0}, but the project is {1}'s. Confirm the name mismatch to enter it on this project.").format(
			check["bill_name"], check["customer"]), title=_("Name Mismatch"))
	supplier = _supplier(data)
	dup = already_entered(supplier, bill_no)
	if dup:
		frappe.throw(_duplicate_message(dup, bill_no, supplier), title=_("Already Entered"))
	pi = _build(inst, data, supplier)
	if not check["matches"]:
		pi.remarks = (pi.remarks or "") + "\n" + _("The bill is for {0}; entered on {1}'s project on {2}'s confirmation.").format(
			check["bill_name"], check["customer"], frappe.session.user)
	pi.insert()
	pi.submit()

	upload = (frappe.request.files.getlist("file") or [None])[0] if frappe.request and frappe.request.files else None
	if upload:
		content = upload.stream.read()
		frappe.get_doc({"doctype": "File", "file_name": upload.filename, "content": content, "is_private": 1,
			"attached_to_doctype": "Purchase Invoice", "attached_to_name": pi.name,
			"a3s_document_type": DOCUMENT_TYPE if DOCUMENT_TYPE in _document_types() else None}).insert(ignore_permissions=True)
	paid = _pay(pi, payment, proof) if payment else None
	return {"name": pi.name, "grand_total": pi.grand_total, "rounded_total": pi.rounded_total, "payment_entry": paid,
		"state": state(inst.name)}


def _document_types():
	from a3_sola.api.portal_attachments import document_types

	return document_types()


@frappe.whitelist()
def state(installation):
	"""The job's supplier bills, and whether the task is done."""
	from a3_sola.www.a3solaportal.collections import record_route

	inst = _job(installation)
	row = next((r for r in inst.stages if r.stage_code == CODE), None)
	bills = frappe.get_all("Purchase Invoice", filters={"solar_installation": inst.name, "docstatus": ["<", 2]},
		fields=["name", "supplier", "supplier_name", "bill_no", "bill_date", "grand_total", "rounded_total", "docstatus",
			"status", "outstanding_amount"],
		order_by="creation asc") if frappe.get_meta("Purchase Invoice").has_field("solar_installation") else []
	for b in bills:
		b["url"] = record_route("purchase-invoices", b.name)  # the portal's own page of it
		b["total"] = flt(b.rounded_total or b.grand_total)
		# Drawn from JSON on the page: the date as text, the amounts as numbers.
		b["bill_date"] = frappe.utils.formatdate(b.bill_date, "dd-MM-yyyy") if b.bill_date else ""
		b["grand_total"], b["rounded_total"] = flt(b.grand_total), flt(b.rounded_total)
		b["outstanding"] = flt(b.pop("outstanding_amount"))
		b["payments"] = _payments(b.name) if b.docstatus == 1 else []
	return {
		"installation": inst.name, "consumer_name": inst.get("consumer_name"), "company": inst.company,
		"task": {"code": CODE, "name": row.stage_name if row else _("Supplier Invoice")},
		"status": row.status if row else None, "bills": bills, "payment_choices": payment_choices(inst.company),
		"can_pay": bool(frappe.has_permission("Payment Entry", "create")) and bool(frappe.has_permission(INSTALLATION, "write", inst.name)),
		"statement": _statement_summary(bills),
		"suppliers": project_suppliers(inst, bills),

		"can_edit": bool(frappe.has_permission(INSTALLATION, "write", inst.name)) and bool(row) and row.status != "Completed",
	}


def project_suppliers(inst, bills):
	"""The project's suppliers, each with its bills and what it is owed: those its procurement
	tasks name first (Material, Structure Material - their supplier, pending-items supplier and
	each pending item's), then those it has bills from."""
	named = []
	for task in frappe.get_all("Installation Task", filters={"solar_installation": inst.name,
			"task_code": ["in", ["PROC", "SPROC"]], "docstatus": ["<", 2]}, fields=["name", "supplier", "pending_supplier"]):
		named += [task.supplier, task.pending_supplier]
		named += frappe.get_all("Installation Task Pending Item", filters={"parent": task.name, "supplier": ["is", "set"]},
			pluck="supplier")
	order = []
	for name in named + [b.supplier for b in bills]:
		if name and name not in order and frappe.db.exists("Supplier", name):
			order.append(name)
	out = []
	for name in order:
		mine = [b for b in bills if b.supplier == name and b.docstatus == 1]
		total = flt(sum(b.total for b in mine), 2)
		due = flt(sum(b.outstanding for b in mine), 2)
		out.append({
			"supplier": name, "name": frappe.db.get_value("Supplier", name, "supplier_name") or name,
			"gstin": supplier_gstin(name), "bills": [b.name for b in bills if b.supplier == name],
			"unpaid": [b.name for b in mine if b.outstanding > 0], "total": total, "paid": flt(total - due, 2), "due": due,
			"bank_accounts": bank_accounts(name),
			"state": "none" if not mine else ("paid" if due <= 0 else ("part" if due < total else "unpaid")),
		})
	return out


@frappe.whitelist(methods=["POST"])
def pay_supplier(installation, supplier, payment=None):
	"""Every unpaid bill of one supplier on the project, paid in one Payment Entry to that supplier
	- with the transaction number or the proof posted as `proof`. Each supplier is paid on its own."""
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	inst = _job(installation, "write")
	if not frappe.has_permission("Payment Entry", "create"):
		frappe.throw(_("You may not enter payments."), frappe.PermissionError)
	unpaid = frappe.get_all("Purchase Invoice", filters={"solar_installation": inst.name, "a3s_material_bill": 1,
		"docstatus": 1, "supplier": supplier, "outstanding_amount": [">", 0]}, fields=["name", "outstanding_amount", "bill_no"],
		order_by="posting_date asc, name asc")
	if not unpaid:
		frappe.throw(_("{0} has no unpaid bill on this project.").format(supplier), title=_("Nothing Due"))
	proof = _proof()
	payment = _check_payment(dict(frappe.parse_json(payment) if isinstance(payment, str) else (payment or {}), status=PAID), proof)
	if payment.account == REIMBURSEMENT:
		frappe.throw(_("A reimbursement is entered bill by bill: use Mark as paid on the bill."))
	if len(unpaid) == 1:
		_pay(frappe.get_doc("Purchase Invoice", unpaid[0].name), payment, proof)
		return state(installation)
	paid_on = payment.get("paid_on") or today()
	reference = (payment.get("reference_no") or "").strip() or _("Proof attached: {0}").format(proof[0])[:140]
	pe = get_payment_entry("Purchase Invoice", unpaid[0].name)
	for bill in unpaid[1:]:
		pi = frappe.get_doc("Purchase Invoice", bill.name)
		pe.append("references", {"reference_doctype": "Purchase Invoice", "reference_name": pi.name,
			"bill_no": pi.bill_no, "due_date": pi.due_date, "total_amount": pi.rounded_total or pi.grand_total,
			"outstanding_amount": flt(bill.outstanding_amount), "allocated_amount": flt(bill.outstanding_amount)})
	amount = flt(sum(flt(b.outstanding_amount) for b in unpaid), 2)
	pe.paid_amount = pe.received_amount = amount
	pe.base_paid_amount = pe.base_received_amount = amount
	pe.party_bank_account = _party_account(supplier, payment.get("party_bank_account")) or pe.get("party_bank_account")
	pe.mode_of_payment = payment.mode
	pe.paid_from = payment.account
	pe.paid_from_account_currency = frappe.db.get_value("Account", payment.account, "account_currency") or pe.paid_to_account_currency
	pe.posting_date = pe.reference_date = paid_on
	pe.reference_no = reference
	pe.remarks = _("Supplier bills {0} for {1}: paid by {2}, reference {3}.").format(
		", ".join(b.bill_no or b.name for b in unpaid), inst.name, payment.mode, reference)
	pe.insert()
	pe.submit()
	if proof:
		frappe.get_doc({"doctype": "File", "file_name": proof[0], "content": proof[1], "is_private": 1,
			"attached_to_doctype": "Payment Entry", "attached_to_name": pe.name}).insert(ignore_permissions=True)
	return state(installation)


@frappe.whitelist(methods=["POST"])
def mark_done(installation):
	"""Every supplier's bill for the job is entered: the task is done."""
	inst = _job(installation, "write")
	bills = [b for b in state(installation)["bills"] if b.docstatus == 1]
	if not bills:
		frappe.throw(_("Enter the supplier's bill first."))
	from a3_sola.api import stages

	row = next((r for r in inst.stages if r.stage_code == CODE), None)
	if not row:
		frappe.throw(_("This project has no Supplier Invoice task."))
	if row.status in ("Completed", "Skipped"):
		frappe.throw(_("{0} is already {1}.").format(row.stage_name, row.status.lower()))
	row.status = "Completed"
	row.actual_completion_date = today()
	row.completed_by = frappe.session.user
	row.external_reference = ", ".join(b.bill_no for b in bills if b.bill_no)[:140]
	stages._save(inst, _("{0}: {1} entered ({2}).").format(row.stage_name,
		", ".join(b.bill_no or b.name for b in bills), ", ".join(b.name for b in bills)))
	from a3_sola.api.tasks import notify_task_completed

	notify_task_completed(inst, CODE)
	return state(installation)


def on_bill_change(doc, method=None):
	"""A material bill submitted starts the job's Supplier Invoice task; the last one cancelled
	takes it back to Pending - completed or not - since the job has no bill left."""
	if not (doc.get("a3s_material_bill") and doc.get("solar_installation")):
		return
	if not frappe.db.exists(INSTALLATION, doc.solar_installation):
		return
	inst = frappe.get_doc(INSTALLATION, doc.solar_installation)
	row = next((r for r in inst.stages if r.stage_code == CODE), None)
	if not row or row.status == "Skipped":
		return
	others = frappe.db.count("Purchase Invoice", {"solar_installation": inst.name, "a3s_material_bill": 1,
		"docstatus": 1, "name": ["!=", doc.name]})
	from a3_sola.api import stages

	if method == "on_cancel" and not others:
		if row.status == "Pending":
			return
		row.status = "Pending"
		row.actual_completion_date = None
		row.external_reference = None
		stages._save(inst, _("{0}: bill {1} cancelled, none left.").format(row.stage_name, doc.bill_no or doc.name))
	elif method == "on_submit" and row.status == "Pending":
		row.status = "In Progress"
		stages._save(inst, _("{0}: bill {1} entered as {2}.").format(row.stage_name, doc.bill_no or doc.name, doc.name))


# ------------------------------------------------------------------ the project's material statement
def _gst_rate(row, taxes):
	"""A line's GST %: its item tax template's ("GST 18% - RIL"), else its rates' sum."""
	match = re.search(r"(\d+(?:\.\d+)?)\s*%", row.item_tax_template or "")
	if match:
		return flt(match.group(1))
	rates = frappe.parse_json(row.item_tax_rate or "{}") or {}
	heads = {t.account_head for t in taxes}
	return flt(sum(flt(v) for k, v in rates.items() if k in heads)) or None


def _statement_summary(bills):
	"""The material statement's figures, from the bills the page lists - the submitted ones."""
	done = [b for b in bills if b.docstatus == 1]
	if not done:
		return None
	taxable = tax = 0.0
	for b in done:
		taxable += flt(frappe.db.get_value("Purchase Invoice", b.name, "net_total"))
		tax += flt(frappe.db.get_value("Purchase Invoice", b.name, "total_taxes_and_charges"))
	total = flt(sum(b.total for b in done), 2)
	due = flt(sum(b.outstanding for b in done), 2)
	return {"bills": len(done), "suppliers": len({b.supplier for b in done}), "taxable": flt(taxable, 2), "tax": flt(tax, 2),
		"total": total, "paid": flt(total - due, 2), "due": due}


def statement(installation):
	"""Every supplier's bill on the project, its lines and taxes, and the whole: taxable value and
	tax by GST rate, CGST, SGST and IGST, the total, what is paid and what is due."""
	inst = _job(installation)
	names = frappe.get_all("Purchase Invoice", filters={"solar_installation": inst.name, "a3s_material_bill": 1,
		"docstatus": 1}, pluck="name", order_by="bill_date asc, posting_date asc, name asc")
	bills, by_rate = [], {}
	kinds = {"cgst": 0.0, "sgst": 0.0, "igst": 0.0}
	for name in names:
		pi = frappe.get_doc("Purchase Invoice", name)
		lines = []
		for row in pi.items:
			rate = _gst_rate(row, pi.taxes)
			description = (row.description or row.item_name or "").split("\n")
			serials = next((SERIALS_IN_DESC.search(l).group(1) for l in description if SERIALS_IN_DESC.search(l)), "")
			lines.append({"description": description[0], "serials": serials, "hsn": row.get("gst_hsn_code") or "",
				"gst_rate": rate, "qty": flt(row.qty), "uom": row.uom, "rate": flt(row.rate), "amount": flt(row.net_amount)})
			slab = by_rate.setdefault(rate, {"rate": rate, "taxable": 0.0, "tax": 0.0})
			slab["taxable"] += flt(row.net_amount)
			# Each tax on the line rounded on its own, as the bill rounds it (round_row_wise_tax).
			rates = frappe.parse_json(row.item_tax_rate or "{}") or {}
			slab["tax"] += sum(flt(flt(row.net_amount) * flt(rates.get(t.account_head, t.rate)) / 100, 2) for t in pi.taxes
				if t.charge_type == "On Net Total")
		taxes = []
		for t in pi.taxes:
			kind = next((k for k in kinds if k in (t.account_head or "").lower()), None)
			if kind:
				kinds[kind] += flt(t.tax_amount)
			taxes.append({"label": t.description or t.account_head, "account": t.account_head, "amount": flt(t.tax_amount)})
		total = flt(pi.rounded_total or pi.grand_total)
		bills.append({
			"invoice": pi.name, "supplier": pi.supplier_name or pi.supplier, "supplier_id": pi.supplier,
			"gstin": frappe.db.get_value("Supplier", pi.supplier, "tax_id") or "", "bill_no": pi.bill_no or "",
			"bill_date": frappe.utils.formatdate(pi.bill_date, "dd-MM-yyyy") if pi.bill_date else "",
			"status": pi.status, "taxable": flt(pi.net_total), "tax": flt(pi.total_taxes_and_charges),
			"rounding": flt(pi.rounding_adjustment), "total": total, "due": flt(pi.outstanding_amount),
			"paid": flt(total - flt(pi.outstanding_amount)), "lines": lines, "taxes": taxes,
		})
	per_supplier = {}
	for b in bills:
		# By the supplier itself: two firms of one name are two suppliers, each paid on its own.
		row = per_supplier.setdefault(b["supplier_id"], {"supplier": b["supplier"], "gstin": b["gstin"], "bills": 0,
			"total": 0.0, "paid": 0.0, "due": 0.0})
		row["bills"] += 1
		for k in ("total", "paid", "due"):
			row[k] = flt(row[k] + b[k], 2)
	slabs = sorted(by_rate.values(), key=lambda s: (s["rate"] is None, s["rate"] or 0))
	for s in slabs:
		s["taxable"], s["tax"] = flt(s["taxable"], 2), flt(s["tax"], 2)
	return {
		"installation": inst.name, "customer": inst.get("consumer_name") or "", "company": inst.company,
		"site": frappe.db.get_value("Solar Consumer", inst.solar_consumer, "installation_site_address") if inst.get("solar_consumer") else "",
		"date": frappe.utils.formatdate(today(), "dd-MM-yyyy"), "bills": bills, "slabs": slabs,
		"by_supplier": sorted(per_supplier.values(), key=lambda r: -r["due"]),
		"suppliers": len({b["supplier_id"] for b in bills}),
		"taxable": flt(sum(b["taxable"] for b in bills), 2), "tax": flt(sum(b["tax"] for b in bills), 2),
		"cgst": flt(kinds["cgst"], 2), "sgst": flt(kinds["sgst"], 2), "igst": flt(kinds["igst"], 2),
		"total": flt(sum(b["total"] for b in bills), 2), "paid": flt(sum(b["paid"] for b in bills), 2),
		"due": flt(sum(b["due"] for b in bills), 2),
	}


SERIALS_IN_DESC = re.compile(r"Serial nos?\.?\s*:\s*(.+)", re.IGNORECASE)


def statement_file_name(data):
	from a3_sola.api.documents import customer_file_name

	return customer_file_name(data["customer"], _("Material Statement {0}").format(data["installation"]))


def render_statement(installation):
	"""The project's material statement as a PDF on the company letterhead."""
	from a3_sola.api.documents import letterhead_flow_pdf

	data = statement(installation)
	html = frappe.render_template("a3_sola/templates/print/supplier_bill_statement.html", {
		"s": data, "money": lambda value: frappe.utils.fmt_money(value, currency="INR"),
		"qty": lambda value: "{0:g}".format(flt(value)),
	})
	return letterhead_flow_pdf(html, data["company"])


@frappe.whitelist()
def statement_pdf(installation, download=0):
	"""The project's material statement: to view, or with `download`, to save."""
	data = statement(installation)
	frappe.local.response.filename = statement_file_name(data)
	frappe.local.response.filecontent = render_statement(installation)
	frappe.local.response.type = "download" if cint(download) else "pdf"
