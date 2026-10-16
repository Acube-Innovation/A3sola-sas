# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SolarCompanyAccountMapping(Document):
	def validate(self):
		self.validate_receiving_firms()

	def validate_receiving_firms(self):
		"""Each firm once, booked to a ledger (not a group) of this company."""
		seen = set()
		for row in self.get("receiving_firms") or []:
			key = (row.firm_name or "").strip().lower()
			if key in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, row.firm_name))
			seen.add(key)
			company, is_group = frappe.db.get_value("Account", row.account, ["company", "is_group"]) or (None, 0)
			if company != self.company:
				frappe.throw(_("Row {0}: account {1} is not {2}'s.").format(row.idx, row.account, self.company))
			if is_group:
				frappe.throw(_("Row {0}: {1} is a group; choose a ledger account.").format(row.idx, row.account))


def receiving_firms(company):
	"""{firm: account} of the company's active receiving firms, in their order."""
	mapping = frappe.db.get_value("Solar Company Account Mapping", {"company": company}, "name") if company else None
	if not mapping:
		return {}
	return {r.firm_name: r.account for r in frappe.get_all("Payment Receiving Firm",
		filters={"parent": mapping, "parenttype": "Solar Company Account Mapping", "is_active": 1},
		fields=["firm_name", "account"], order_by="idx asc")}
