# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""An RBI e-mandate, card token or UPI Autopay authorisation.

Two design points that exist because of the regulation, not because of preference:

**The ceiling is snapshotted at registration.** `afa_ceiling_at_registration` records what
the no-AFA threshold was on the day this mandate was authorised. The RBI has revised that
threshold repeatedly, and a later revision must not silently reclassify a mandate the
customer already authorised under the old one.

**The registered maximum carries headroom.** A mandate registered at exactly the current
debit breaks the moment the customer adds one user. The headroom percentage is what stops
a routine upgrade turning into a failed collection at the bank.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from a3_sola.api.naming import set_name
from a3_sola.api.settings import get_float


class PaymentMandate(Document):
	def autoname(self):
		set_name(self, "mandate_series_prefix", ".YYYY.-.#####", fallback="MND")

	def validate(self):
		self.snapshot_ceiling()
		self.set_registered_maximum()
		self.classify()

	def snapshot_ceiling(self):
		"""Freeze the threshold this mandate was authorised under."""
		if not self.afa_ceiling_at_registration:
			self.afa_ceiling_at_registration = flt(
				get_float("afa_free_debit_ceiling", 15000.0)
			)

	def set_registered_maximum(self):
		"""Default to the debit plus headroom, rounded up to a clean hundred."""
		if self.registered_max_amount:
			return
		headroom = flt(get_float("mandate_headroom_percent", 20.0))
		raw = flt(self.recurring_debit_amount) * (1 + headroom / 100.0)
		# A registered maximum of 8,496 looks arbitrary to a customer reading their bank
		# statement; 8,500 does not.
		self.registered_max_amount = flt(-(-raw // 100) * 100, 2)

	def classify(self):
		"""Does every debit under this mandate need authentication?"""
		ceiling = flt(self.afa_ceiling_at_registration)
		amount = flt(self.recurring_debit_amount)
		self.requires_afa_per_debit = 1 if amount > ceiling else 0
		if self.requires_afa_per_debit:
			self.classification_reason = _(
				"The recurring debit of {0} is above the {1} ceiling that applied when this "
				"mandate was registered, so each debit needs the customer's authentication."
			).format(
				frappe.utils.fmt_money(amount, currency="INR"),
				frappe.utils.fmt_money(ceiling, currency="INR"),
			)
		else:
			self.classification_reason = _(
				"The recurring debit of {0} is within the {1} ceiling that applied when this "
				"mandate was registered, so it can be debited automatically."
			).format(
				frappe.utils.fmt_money(amount, currency="INR"),
				frappe.utils.fmt_money(ceiling, currency="INR"),
			)

	def covers(self, amount):
		"""Would a debit of this amount be within what the customer authorised?"""
		return flt(amount) <= flt(self.registered_max_amount)

	def set_status(self, status, reason=None, source=None):
		if self.status == status:
			return False
		self.db_set(
			{
				"status": status,
				"status_reason": reason,
				"cancelled_on": frappe.utils.today() if status == "Cancelled" else None,
				"cancellation_source": source if status == "Cancelled" else None,
			},
			update_modified=False,
		)
		frappe.logger("a3_sola").info(
			{"event": "mandate_status", "mandate": self.name, "status": status, "reason": reason}
		)
		if status == "Rejected":
			self.raise_rejection_alert(reason)
		return True

	def raise_rejection_alert(self, reason):
		"""A silently rejected mandate means no revenue next cycle.

		It has to be visible now, while there is still time to ask the customer to
		re-register, rather than discovered when the debit fails.
		"""
		from a3_sola.api.settings import get_value

		frappe.log_error(
			title="a3_sola: mandate rejected",
			message=f"Mandate {self.name} for {self.customer_name} was rejected: {reason}. "
			"The next collection will fail unless it is re-registered.",
		)
		recipient = get_value("sales_email")
		if not recipient or frappe.flags.in_test or frappe.flags.in_demo:
			return
		try:
			frappe.sendmail(
				recipients=[recipient],
				subject=_("Mandate rejected: {0}").format(self.customer_name),
				message=_(
					"The payment mandate for {0} was rejected ({1}). Their next collection "
					"will fail unless they re-register. Contact them today."
				).format(self.customer_name, reason or _("no reason given")),
				reference_doctype=self.doctype,
				reference_name=self.name,
				now=False,
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"a3_sola: mandate alert {self.name}")
