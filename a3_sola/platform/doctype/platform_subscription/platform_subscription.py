# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A live subscription.

PHASE 5 BUILDS ONLY WHAT COLLECTION NEEDS. Phase 7 owns the lifecycle - renewal policy,
grace periods, suspension, upgrade and downgrade - and the extension points at the bottom
of this file are the contract it implements against.

The load-bearing decision here is `collection_route`. It is derived, never chosen, from
the recurring amount against the RBI ceiling and from the billing cycle. Getting it wrong
in either direction is expensive: routing an eligible customer to assisted renewal costs
renewals to friction, and routing an ineligible one to auto-debit produces a debit the
bank will decline.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, add_years, cint, flt, getdate, today

from a3_sola.api.naming import set_name


class PlatformSubscription(Document):
	def autoname(self):
		set_name(self, "subscription_series_prefix", ".YYYY.-.#####", fallback="SUB")

	def onload(self):
		"""The tenant, for the lifecycle actions on the form.

		Every one of them acts on the tenant rather than the subscription - suspension,
		restoration and seats are all about users - and the link runs the other way, from
		Tenant to subscription, so the form cannot follow it on its own.
		"""
		self.set_onload(
			"tenant",
			frappe.db.get_value("Tenant", {"platform_subscription": self.name}, "name"),
		)

	def validate(self):
		self.roll_up_users()
		self.derive_recurring_amount()
		self.derive_collection_route()
		self.warn_if_mandate_no_longer_covers()

	def roll_up_users(self):
		self.total_users = cint(self.included_users) + cint(self.additional_users)

	def derive_recurring_amount(self):
		"""The per-cycle debit including tax. This is what the ceiling is measured on."""
		if not self.recurring_amount:
			self.recurring_amount = flt(flt(self.subtotal) + flt(self.tax_amount), 2)

	def derive_collection_route(self):
		from a3_sola.api.payments import classify_collection

		mode, reason = classify_collection(self.recurring_amount, self.billing_cycle)
		self.collection_route = "Auto Debit" if mode == "Auto Debit" else "Assisted Renewal"
		self.route_reason = reason

	def warn_if_mandate_no_longer_covers(self):
		"""A debit above the registered maximum is declined at the bank.

		Flag it here, loudly, while somebody can still act - not on the morning the
		collection fails.
		"""
		if not self.payment_mandate or not self.recurring_amount:
			return
		mandate = frappe.get_cached_doc("Payment Mandate", self.payment_mandate)
		if flt(self.recurring_amount) <= flt(mandate.registered_max_amount):
			return
		frappe.msgprint(
			_("The recurring amount is now {0}, above the {1} this customer authorised on "
			  "mandate {2}. The next automatic debit will be declined by their bank unless "
			  "the mandate is re-registered.").format(
				frappe.utils.fmt_money(self.recurring_amount, currency=self.currency),
				frappe.utils.fmt_money(mandate.registered_max_amount, currency=self.currency),
				mandate.name,
			),
			title=_("Mandate No Longer Covers This Amount"),
			indicator="red",
		)

	def advance_period(self):
		"""Move the window forward one cycle. Idempotent per period."""
		if (self.billing_cycle or "").lower() == "annual":
			start = add_days(getdate(self.current_period_end), 1)
			end = add_days(add_years(start, 1), -1)
		else:
			start = add_days(getdate(self.current_period_end), 1)
			end = add_days(add_months(start, 1), -1)
		self.db_set(
			{
				"current_period_start": start,
				"current_period_end": end,
				"next_billing_date": start,
				"next_debit_date": start,
			},
			update_modified=False,
		)
		return start, end

	def cycle_for(self, period_start):
		"""The billing cycle row for a period, created once."""
		for row in self.billing_cycles:
			if getdate(row.period_start) == getdate(period_start):
				return row
		return None

	def set_status(self, status, reason=None):
		if self.status == status:
			return False
		was = self.status
		self.db_set({"status": status, "status_reason": reason}, update_modified=False)
		frappe.logger("a3_sola").info(
			{"event": "subscription_status", "subscription": self.name, "status": status}
		)
		if status == "Active" and was in (None, "", "Draft", "Pending Payment"):
			# Once, on the first transition into Active. A subscription that recovers from
			# Past Due has not just been activated - it was already alive - and firing the
			# lifecycle start again would restart a trial clock that is long spent.
			safely(on_subscription_activated, self, "on_subscription_activated")
		return True


# ------------------------------------------------------------ Phase 7 contracts
def on_billing_cycle_completed(subscription):
	"""Phase 7 implements this. See a3_sola/api/lifecycle/handlers.py.

	Phase 7 owns renewal policy after a collected cycle: advancing the period,
	restoring a customer whose balance is now clear, and applying any change that was
	waiting for the boundary.
	"""
	from a3_sola.api.lifecycle.handlers import on_billing_cycle_completed as implementation

	return implementation(subscription)


def on_payment_failed_final(subscription):
	"""Phase 7 implements this. See a3_sola/api/lifecycle/handlers.py.

	Phase 7 owns what happens after dunning: Past Due, and no access change. A failed
	payment is usually a bank problem rather than a refusal to pay.
	"""
	from a3_sola.api.lifecycle.handlers import on_payment_failed_final as implementation

	return implementation(subscription)


def on_subscription_activated(subscription):
	"""Phase 7 implements this. See a3_sola/api/lifecycle/handlers.py.

	Phase 7 owns the lifecycle clock: the trial window, the first renewal date and the
	policy this subscription will be governed by.
	"""
	from a3_sola.api.lifecycle.handlers import on_subscription_activated as implementation

	return implementation(subscription)


def safely(handler, subscription, event):
	"""A missing Phase 7 must never break a collection that already succeeded."""
	try:
		return handler(subscription)
	except NotImplementedError:
		frappe.logger("a3_sola").info(
			{"event": f"{event}_deferred", "subscription": subscription.name}
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: {event} {subscription.name}")
	return None
