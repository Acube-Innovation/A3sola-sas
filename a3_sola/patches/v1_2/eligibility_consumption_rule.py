# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Give every eligibility check made before ELG-12 its Avg Monthly Units and the ELG-12 row.

Completed (submitted) checks do not recompute, so without this they would never show the
consumption comparison. Only the new field and the new rule's row are written: the other
rules' results, the overall result and any waivers stay exactly as they were decided.
"""

import frappe

from a3_sola.api import eligibility
from a3_sola.solar_crm.doctype.subsidy_eligibility_check.subsidy_eligibility_check import reference_details


def execute():
	frappe.reload_doc("solar_crm", "doctype", "eligibility_rule_result")
	frappe.reload_doc("solar_crm", "doctype", "subsidy_eligibility_check")
	for name in frappe.get_all("Subsidy Eligibility Check", filters={"docstatus": ["<", 2]}, pluck="name"):
		try:
			fill(frappe.get_doc("Subsidy Eligibility Check", name))
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"ELG-12 backfill failed for {name}")


def fill(doc):
	details = reference_details(doc.lead, doc.solar_consumer, doc.design_estimate)
	doc.avg_monthly_units = details.get("avg_monthly_units") or 0
	doc.db_set("avg_monthly_units", doc.avg_monthly_units, update_modified=False)

	entry = next(e for e in eligibility.evaluate(doc) if e["rule_code"] == "ELG-12")
	row = next((r for r in doc.rule_results if r.rule_code == "ELG-12"), None)
	if row:
		row.db_set({"rule_description": entry["rule_description"], "result": entry["result"],
			"remarks": entry["remarks"]}, update_modified=False)
		return
	row = doc.append("rule_results", entry)
	row.idx = len(doc.rule_results)
	row.db_insert()
