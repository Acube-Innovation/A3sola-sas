# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Each package names its payment terms. A package without them takes its company's default
terms for a job the customer pays for (70% advance, 20% after installation, 10% after
commissioning), and its financed terms for a job on a bank loan. Written directly: the rest
of the package is not re-validated."""

import frappe


def _terms(company, funding):
	rows = frappe.get_all("Billing Milestone Template", filters={"company": company, "is_active": 1,
		"applicable_funding": ["in", [funding, "Any"]]}, fields=["name", "is_default", "applicable_funding"])
	rows.sort(key=lambda r: (r.applicable_funding != funding, not r.is_default, r.name))
	return rows[0].name if rows else None


def execute():
	frappe.reload_doc("solar_crm", "doctype", "solar_package")
	for name, company, terms, financed in frappe.get_all("Solar Package",
			fields=["name", "company", "payment_terms", "financed_payment_terms"], as_list=True):
		values = {}
		if not terms:
			values["payment_terms"] = _terms(company, "Self Funded")
		if not financed:
			values["financed_payment_terms"] = _terms(company, "Financed")
		values = {k: v for k, v in values.items() if v}
		if values:
			frappe.db.set_value("Solar Package", name, values, update_modified=False)
