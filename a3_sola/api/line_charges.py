# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What Additional Structure, Additional Cable and Special Discount have in common.

Each is a list of priced rows hung off a lead or a consumer: the rows are worked out one
by one and summed into `total_amount`. Only how a row's amount is reached differs, so
each controller passes that in and everything else lives here, once.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api.permissions import assert_same_company

LINKS = (
	("lead", "Lead"),
	("solar_consumer", "Solar Consumer"),
	("solar_design_estimate", "Solar Design Estimate"),
)


def validate(doc, row_amount):
	"""Check the record is anchored to a customer, then price every row and total them."""
	if not doc.lead and not doc.solar_consumer:
		frappe.throw(_("Choose the lead or the solar consumer this {0} is for.").format(_(doc.doctype)),
			frappe.MandatoryError)
	assert_same_company(doc, LINKS)

	total = 0.0
	for row in doc.get("items") or []:
		row.amount = flt(row_amount(row), row.precision("amount"))
		total += row.amount
	doc.total_amount = flt(total, doc.precision("total_amount"))
