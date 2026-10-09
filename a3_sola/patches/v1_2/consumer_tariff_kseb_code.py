# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A consumer's tariff category is a KSEB tariff code, as the design estimate's is.

The free text on file ("LT-1/Single", "LT-7A") is turned into its code (LT-I, LT-VII(A));
text no code can be read from is cleared and logged, since a link must name a record. The
subsidy setting becomes a code too, and each estimate takes its consumer's code as its
Electricity Tariff where none was chosen. Written directly, so nothing is re-validated.
"""

import frappe

from a3_sola.setup.install import seed_kseb_tariff_categories
from a3_sola.solar_crm.doctype.kseb_tariff_category.kseb_tariff_category import kseb_code


def execute():
	frappe.reload_doc("solar_crm", "doctype", "kseb_tariff_category")
	seed_kseb_tariff_categories()  # the codes must exist before anything links to them

	unread = []
	for name, text in frappe.get_all("Solar Consumer", filters={"tariff_category": ["is", "set"]},
			fields=["name", "tariff_category"], as_list=True):
		code = kseb_code(text)
		if code != text:
			frappe.db.set_value("Solar Consumer", name, "tariff_category", code, update_modified=False)
		if not code:
			unread.append(f"{name}: {text}")
	if unread:
		frappe.log_error("\n".join(unread), "consumer_tariff_kseb_code: tariff text with no KSEB code, cleared")

	required = frappe.db.get_single_value("A3 Sola Settings", "subsidy_tariff_category")
	frappe.db.set_single_value("A3 Sola Settings", "subsidy_tariff_category", kseb_code(required) or "LT-I")

	for name, text, code in frappe.get_all("Solar Design Estimate", fields=["name", "tariff_category", "tariff_code"], as_list=True):
		updates = {}
		if text and kseb_code(text) != text:
			updates["tariff_category"] = kseb_code(text)
		if not code and kseb_code(text):
			updates["tariff_code"] = kseb_code(text)
		if updates:
			frappe.db.set_value("Solar Design Estimate", name, updates, update_modified=False)
