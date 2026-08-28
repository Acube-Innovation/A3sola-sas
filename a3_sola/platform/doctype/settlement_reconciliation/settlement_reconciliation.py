# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One settlement from the gateway, matched against what we recorded."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api.naming import set_name


class SettlementReconciliation(Document):
	def autoname(self):
		set_name(self, "reconciliation_series_prefix", ".YYYY.-.###", fallback="RECN")

	def before_submit(self):
		"""A settlement with lines nobody has explained must not be posted."""
		if self.unmatched_count:
			frappe.throw(
				_("{0} settlement line(s) are unmatched. Money has moved that this system "
				  "cannot account for - investigate each one before submitting.").format(
					self.unmatched_count
				),
				title=_("Unmatched Lines"),
			)

	def on_submit(self):
		from a3_sola.api import audit

		self.db_set("status", "Posted", update_modified=False)
		audit.record(
			"Reconciliation Submitted",
			f"Settlement {self.settlement_id} posted, {self.matched_count} line(s) matched",
			reference_doctype=self.doctype,
			reference_name=self.name,
			amount=self.net_settled,
			detail=(
				f"Gross {self.gross_total}, fees {self.total_fees}, tax {self.total_tax}, "
				f"refunds {self.total_refunds}, net settled {self.net_settled}. "
				f"Variance {self.variance_total}."
			),
		)
