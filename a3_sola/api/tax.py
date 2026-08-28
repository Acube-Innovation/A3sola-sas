# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""GST on the SaaS subscription supply.

DISTINCT FROM PHASE 3. Phase 3's GST work concerns the tenant's own solar EPC contracts,
which are a composite supply of goods and services with a contested valuation. This is a
different supply entirely: the client selling a software subscription. That is a service,
taxed at the standard services rate, with place of supply determined by where the
recipient is.

Kerala supplier + Kerala customer = CGST + SGST. Any other state = IGST.

The rate is read from Settings and is not hardcoded anywhere in this module, for the same
reason as Phase 3: it is the client's CA's decision, not a developer's.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt

from a3_sola.api.settings import get_float, get_value

#: A GSTIN carries its state code in the first two characters. If the customer typed a
#: Kerala GSTIN but selected Karnataka, one of the two is wrong - and getting it wrong
#: breaks their input tax credit, which they will notice at their next return.
GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$")

#: Enough to resolve a typed state name to its GST code. Not exhaustive - an unknown
#: state falls back to whatever the customer's GSTIN says, which is authoritative.
STATE_CODES = {
	"jammu and kashmir": "01", "himachal pradesh": "02", "punjab": "03",
	"chandigarh": "04", "uttarakhand": "05", "haryana": "06", "delhi": "07",
	"rajasthan": "08", "uttar pradesh": "09", "bihar": "10", "sikkim": "11",
	"arunachal pradesh": "12", "nagaland": "13", "manipur": "14", "mizoram": "15",
	"tripura": "16", "meghalaya": "17", "assam": "18", "west bengal": "19",
	"jharkhand": "20", "odisha": "21", "chhattisgarh": "22", "madhya pradesh": "23",
	"gujarat": "24", "maharashtra": "27", "karnataka": "29", "goa": "30",
	"lakshadweep": "31", "kerala": "32", "tamil nadu": "33", "puducherry": "34",
	"andaman and nicobar islands": "35", "telangana": "36", "andhra pradesh": "37",
	"ladakh": "38",
}


def state_code_for(state_name):
	return STATE_CODES.get((state_name or "").strip().lower())


def validate_gstin(gstin, state_code=None):
	"""Format, and consistency with the stated place of supply.

	Returns the normalised GSTIN. Raises when the embedded state code contradicts the
	state the customer said they are in - that mismatch is not a typo we can guess past.
	"""
	gstin = (gstin or "").strip().upper()
	if not gstin:
		return ""
	if not GSTIN_PATTERN.match(gstin):
		frappe.throw(
			_("{0} is not a valid GSTIN.").format(gstin), title=_("Check the GSTIN")
		)
	embedded = gstin[:2]
	if state_code and str(state_code).strip().zfill(2) != embedded:
		frappe.throw(
			_("The GSTIN {0} belongs to state {1}, but the address says state {2}. "
			  "One of the two is wrong, and an invoice raised on the wrong one will "
			  "break your input tax credit.").format(gstin, embedded, str(state_code).zfill(2)),
			title=_("GSTIN and State Do Not Match"),
		)
	return gstin


def resolve_place_of_supply(customer_state=None, customer_state_code=None, customer_gstin=None):
	"""Where the supply is treated as made.

	The GSTIN wins when present: it is the registered position, and the customer's typed
	address is what people get wrong.
	"""
	if get_value("place_of_supply_rule") == "Company State":
		code = (get_value("company_state_code") or "").strip().zfill(2)
		return code, _company_state_name(code)

	code = None
	if customer_gstin and GSTIN_PATTERN.match((customer_gstin or "").strip().upper()):
		code = customer_gstin.strip().upper()[:2]
	elif customer_state_code:
		code = str(customer_state_code).strip().zfill(2)
	elif customer_state:
		code = state_code_for(customer_state)
	return code, (customer_state or _company_state_name(code) or "")


def _company_state_name(code):
	for name, value in STATE_CODES.items():
		if value == code:
			return name.title()
	return None


def compute_tax(taxable_value, customer_state_code=None):
	"""Split the tax the way the place of supply requires.

	Returns a dict with the type, the rate, each component and the total. Rounded to two
	decimals at the component level so the components always add back to the total - a
	split computed at full precision and rounded on display does not.
	"""
	rate = flt(get_float("subscription_gst_rate", 18.0))
	company_code = (get_value("company_state_code") or "").strip().zfill(2)
	customer_code = (str(customer_state_code or "").strip() or company_code).zfill(2)

	taxable = flt(taxable_value, 2)
	total_tax = flt(taxable * rate / 100.0, 2)

	if customer_code and company_code and customer_code == company_code:
		half = flt(total_tax / 2.0, 2)
		# The halves must add back to the total; give any odd paisa to CGST.
		return {
			"tax_type": "CGST+SGST",
			"tax_rate": rate,
			"igst_amount": 0.0,
			"cgst_amount": flt(total_tax - half, 2),
			"sgst_amount": half,
			"total_tax": total_tax,
			"taxable_value": taxable,
		}
	return {
		"tax_type": "IGST",
		"tax_rate": rate,
		"igst_amount": total_tax,
		"cgst_amount": 0.0,
		"sgst_amount": 0.0,
		"total_tax": total_tax,
		"taxable_value": taxable,
	}


def to_paise(amount):
	"""Rupees to paise, without floating-point drift.

	`int(3540.00 * 100)` is 353999 on some inputs because 35.40 has no exact binary
	representation. Going through Decimal on the string form is the only way to be sure,
	and this number is what the customer is actually charged.
	"""
	from decimal import ROUND_HALF_UP, Decimal

	value = Decimal(str(flt(amount, 2))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
	return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


def from_paise(paise):
	from decimal import Decimal

	return flt(Decimal(cint(paise)) / Decimal(100), 2)
