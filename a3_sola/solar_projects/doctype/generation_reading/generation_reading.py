# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Generation readings, and the contractual performance obligation.

Generation tracking exists to prove the five-year 75% obligation is being met, not to draw
a chart. A system drifting below the floor raises a ticket before the customer notices.
"""

import frappe
from frappe.model.document import Document

from a3_sola.api import sla
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("solar_installation", "Solar Installation"),
	("project", "Project"),
	("om_contract", "Solar OM Contract"),
)


class GenerationReading(Document):
	def autoname(self):
		set_name(self, "generation_reading_series_prefix", ".YYYY.-.#####", fallback="SOL-GEN")

	def validate(self):
		assert_same_company(self, LINKS)
		self.pull_context()
		sla.compute_reading(self)

	def pull_context(self):
		if not self.om_contract:
			self.om_contract = frappe.db.get_value(
				"Solar OM Contract",
				{"solar_installation": self.solar_installation, "docstatus": 1},
				"name",
			)
		if self.om_contract and not self.project:
			self.project = frappe.db.get_value("Solar OM Contract", self.om_contract, "project")

	def on_submit(self):
		ticket = sla.evaluate_performance(self)
		if ticket:
			self.db_set("triggered_ticket", ticket, update_modified=False)


@frappe.whitelist()
def import_readings(rows):
	"""Bulk import - most clients export from an inverter portal rather than key them in."""
	import json

	if isinstance(rows, str):
		rows = json.loads(rows)

	created, errors = [], []
	for row in rows:
		try:
			doc = frappe.get_doc({"doctype": "Generation Reading", **row})
			doc.flags.ignore_permissions = True
			doc.insert(ignore_permissions=True)
			doc.submit()
			created.append(doc.name)
		except Exception as exc:
			errors.append({"row": row, "error": str(exc)})
	return {"created": created, "errors": errors}
