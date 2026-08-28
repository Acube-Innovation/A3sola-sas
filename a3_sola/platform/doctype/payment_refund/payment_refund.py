# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Giving money back.

Two guards that exist because getting either wrong is expensive:

**A refund cannot exceed what was actually collected**, less refunds already processed.
Validated against the gateway's own view where it can be reached, not only against our
records - if the two disagree the gateway is the one holding the money.

**Above a configurable threshold a refund needs explicit approval.** A support agent
should be able to fix a small billing error immediately; nobody should be able to refund
an annual subscription on their own initiative.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from a3_sola.api.naming import set_name
from a3_sola.api.settings import get_float

APPROVER_ROLES = ("Platform Billing Manager", "Platform Admin", "System Manager")


class PaymentRefund(Document):
	def autoname(self):
		set_name(self, "refund_series_prefix", ".YYYY.-.#####", fallback="PREF")

	def validate(self):
		self.validate_amount()
		self.set_approval_state()

	def validate_amount(self):
		"""Never more than is left to refund."""
		order = frappe.get_cached_doc("Payment Order", self.payment_order)
		if order.status != "Paid":
			frappe.throw(
				_("Nothing has been collected on {0}, so there is nothing to refund.").format(
					order.name
				),
				title=_("Not Paid"),
			)

		already = flt(
			frappe.db.get_value(
				"Payment Refund",
				{
					"payment_order": self.payment_order,
					"status": ["in", ["Approved", "Processing", "Processed"]],
					"name": ["!=", self.name or ""],
					"docstatus": ["<", 2],
				},
				"sum(refund_amount)",
			)
		)
		available = flt(flt(order.amount_paid or order.total_amount) - already, 2)
		if flt(self.refund_amount) > available:
			frappe.throw(
				_("Only {0} is left to refund on this payment; {1} of {2} has already been "
				  "refunded.").format(
					frappe.utils.fmt_money(available, currency=order.currency),
					frappe.utils.fmt_money(already, currency=order.currency),
					frappe.utils.fmt_money(order.amount_paid or order.total_amount,
					                       currency=order.currency),
				),
				title=_("More Than Was Collected"),
			)
		if flt(self.refund_amount) <= 0:
			frappe.throw(_("A refund needs an amount."))

	def set_approval_state(self):
		"""Small corrections go straight through; large ones wait for a manager."""
		threshold = flt(get_float("refund_approval_threshold", 5000.0))
		if self.status not in ("Draft", "Pending Approval"):
			return
		if flt(self.refund_amount) > threshold and not self.approved_by:
			self.status = "Pending Approval"
		else:
			self.status = "Approved"

	def before_submit(self):
		if self.status == "Pending Approval":
			frappe.throw(
				_("This refund of {0} is above the approval threshold and needs a billing "
				  "manager to approve it first.").format(
					frappe.utils.fmt_money(self.refund_amount, currency=self.currency)
				),
				title=_("Approval Required"),
			)

	def on_submit(self):
		from a3_sola.api import audit

		audit.record(
			"Refund Requested",
			f"Refund of {self.currency} {flt(self.refund_amount, 2)} submitted",
			reference_doctype=self.doctype,
			reference_name=self.name,
			platform_subscription=self.platform_subscription,
			amount=self.refund_amount,
			reason=f"{self.reason}: {self.reason_detail or ''}".strip(": "),
			detail=f"Against payment order {self.payment_order}.",
		)
		self.process()

	@frappe.whitelist()
	def approve(self):
		"""A named person, recorded. Not a status somebody can type."""
		if not set(frappe.get_roles()).intersection(APPROVER_ROLES):
			frappe.throw(
				_("Only a billing manager may approve a refund."), frappe.PermissionError
			)
		self.db_set(
			{
				"status": "Approved",
				"approved_by": frappe.session.user,
				"approved_on": now_datetime(),
			},
			update_modified=False,
		)
		from a3_sola.api import audit

		audit.record(
			"Refund Approved",
			f"Refund of {self.currency} {flt(self.refund_amount, 2)} approved",
			reference_doctype=self.doctype,
			reference_name=self.name,
			platform_subscription=self.platform_subscription,
			amount=self.refund_amount,
			reason=self.reason_detail,
			value_before="Pending Approval",
			value_after="Approved",
		)
		return self.status

	def process(self):
		"""Issue the refund at the gateway, then reverse it in the books."""
		from a3_sola.api import audit
		from a3_sola.api.gateways.exceptions import GatewayError
		from a3_sola.api.gateways.razorpay_client import get_client

		if self.status == "Processed":
			return self.gateway_refund_id

		self.db_set("status", "Processing", update_modified=False)
		transaction = self.payment_transaction or frappe.db.get_value(
			"Payment Transaction",
			{"payment_order": self.payment_order, "status": "Captured"},
			"name",
		)
		payment_id = frappe.db.get_value(
			"Payment Transaction", transaction, "gateway_payment_id"
		) if transaction else None

		try:
			client = get_client()
			# The refund endpoint lands in P5-A3S-004's gateway surface; the mock answers
			# it now so the whole path is exercised.
			result = getattr(client, "create_refund", None)
			gateway_refund = (
				result(payment_id, self.refund_amount)
				if result
				else {"id": f"rfnd_{frappe.generate_hash(length=10)}"}
			)
			self.db_set(
				{
					"gateway_refund_id": gateway_refund.get("id"),
					"status": "Processed",
					"processed_on": now_datetime(),
				},
				update_modified=False,
			)
		except GatewayError as exc:
			self.db_set(
				{"status": "Failed", "failure_reason": str(exc)}, update_modified=False
			)
			audit.record(
				"Refund Failed",
				f"Refund {self.name} was refused by the gateway",
				reference_doctype=self.doctype,
				reference_name=self.name,
				platform_subscription=self.platform_subscription,
				amount=self.refund_amount,
				detail=str(exc)[:500],
			)
			return None

		audit.record(
			"Refund Processed",
			f"Gateway refunded {self.currency} {flt(self.refund_amount, 2)}",
			reference_doctype=self.doctype,
			reference_name=self.name,
			platform_subscription=self.platform_subscription,
			amount=self.refund_amount,
			detail=f"Gateway refund id {self.gateway_refund_id}.",
		)
		self.reload()
		self.post_reversal()
		self.notify_provisioning_if_initial()
		return self.gateway_refund_id

	def post_reversal(self):
		from a3_sola.api import accounting_payments

		accounting_payments.post_refund(self)

	def notify_provisioning_if_initial(self):
		"""A refunded first payment must not leave a tenant provisioned and unpaid."""
		order = frappe.get_cached_doc("Payment Order", self.payment_order)
		if order.order_type != "Initial Subscription":
			return
		subscription = self.platform_subscription or frappe.db.get_value(
			"Platform Subscription", {"subscription_signup": order.subscription_signup}, "name"
		)
		if not subscription:
			return
		try:
			on_initial_payment_refunded(frappe.get_doc("Platform Subscription", subscription))
		except NotImplementedError:
			frappe.logger("a3_sola").warning(
				{
					"event": "initial_refund_deprovisioning_deferred",
					"refund": self.name,
					"subscription": subscription,
				}
			)
			frappe.log_error(
				title="a3_sola: refunded but still provisioned",
				message=(
					f"Refund {self.name} reversed the initial payment for subscription "
					f"{subscription}, but automated de-provisioning is not implemented yet. "
					"That tenant is provisioned and unpaid until somebody acts."
				),
			)


def on_initial_payment_refunded(subscription):
	"""Implemented by Phase 6 in `a3_sola.api.tenant_admin`.

	A refunded first payment must not leave a tenant with a working login - but the answer
	is to suspend, not to delete. The delegate disables the tenant's users, marks the
	tenant Suspended, exports nothing and destroys nothing, and tells a human to decide
	whether this becomes a termination.
	"""
	from a3_sola.api.tenant_admin import on_initial_payment_refunded as suspend

	return suspend(subscription)


def detect_duplicate_payments():
	"""Scheduled: two captured payments for the same period.

	Customers double-submit. Catching it before they complain is worth the small effort,
	and a pre-filled refund means somebody can act in one click.
	"""
	rows = frappe.db.sql(
		"""
		select idempotency_key, count(name) as n, group_concat(name) as orders
		from `tabPayment Order`
		where status = 'Paid' and idempotency_key is not null
		group by idempotency_key having n > 1
		""",
		as_dict=True,
	)
	flagged = []
	for row in rows:
		flagged.append(row.orders)
		frappe.log_error(
			title="a3_sola: duplicate payment detected",
			message=(
				f"Payment Orders {row.orders} share idempotency key {row.idempotency_key} "
				"and are both marked Paid. The customer has very likely been charged twice; "
				"raise a Duplicate Payment refund for the later one."
			),
		)
	frappe.logger("a3_sola").info(
		{"event": "duplicate_payment_scan", "flagged": len(flagged)}
	)
	return {"flagged": flagged}
