# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


class TenantBlueprint(Document):
	def validate(self):
		self.validate_single_default()
		self.validate_payloads()

	def validate_single_default(self):
		if not self.is_default:
			return
		other = frappe.db.get_value(
			"Tenant Blueprint",
			{"is_default": 1, "name": ["!=", self.name], "applicable_plan": self.applicable_plan or ""},
			"name",
		)
		if other:
			frappe.throw(
				_("{0} is already the default for this plan. Two defaults means provisioning "
				  "picks one arbitrarily.").format(other),
				title=_("Duplicate Default"),
			)

	def validate_payloads(self):
		"""Catch a broken payload here, not eight steps into a customer's provisioning."""
		for row in self.seed_items:
			if not (row.payload or "").strip():
				continue
			try:
				json.loads(row.payload)
			except ValueError as exception:
				frappe.throw(
					_("Seed item {0} has a payload that is not valid JSON: {1}").format(
						row.idx, exception
					),
					title=_("Bad Payload"),
				)
