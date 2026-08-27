# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A prospect who has chosen a plan.

============================ THE PHASE 4 / PHASE 5 CONTRACT ============================

This record is the handover between the public funnel and everything that follows.

* Phase 4 (here) creates it from a public form, verifies the email, and stops.
* Phase 5 charges it. It MUST charge `base_amount`, `additional_user_amount`,
  `implementation_fee`, `subtotal` and `total_amount` AS STORED. It must never recall
  `calculate_plan_total` at payment time: the applicant agreed to the number they were
  shown, and marketing may have changed the plan since. The snapshot is the agreement.
* Phase 6 provisions from `subscription_plan` (its entitlements: included users, modules,
  role profile) plus `additional_users`, and writes back `provisioned_company`,
  `provisioned_site` and `admin_user`.
* Phase 7 bills from `billing_cycle` and writes back `subscription`.

Status is owned by code, never by a person typing into the web:

	Draft -> Awaiting Email Verification -> Verified -> Awaiting Payment
	      -> Paid -> Provisioning -> Active
	      (Payment Failed, Abandoned and Rejected are terminal branches)

Phase 4 owns everything up to Verified. Phase 5 owns Awaiting Payment, Payment Failed and
Paid. Every transition appends to `event_log`.
=======================================================================================
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from a3_sola.api.naming import set_name

#: Fields nobody may change through the web, at any point.
PROTECTED_FIELDS = (
	"status",
	"verification_token",
	"token_expires_on",
	"is_email_verified",
	"verified_on",
	"ip_address",
	"user_agent",
	"base_amount",
	"additional_user_amount",
	"implementation_fee",
	"subtotal",
	"total_amount",
	"price_breakdown",
)


class SubscriptionSignup(Document):
	def autoname(self):
		set_name(self, "signup_series_prefix", ".YYYY.-.#####", fallback="SGN")

	def validate(self):
		self.normalise()
		self.validate_plan()
		self.validate_users()
		self.validate_consent()

	def normalise(self):
		self.work_email = (self.work_email or "").strip().lower()
		self.full_name = (self.full_name or "").strip()
		self.organisation_name = (self.organisation_name or "").strip()
		self.phone = (self.phone or "").strip()
		if self.gstin:
			self.gstin = self.gstin.strip().upper()

	def validate_plan(self):
		"""A custom-priced plan cannot be sold self-serve - there is no number to charge."""
		if not self.subscription_plan:
			return
		plan = frappe.get_cached_doc("Subscription Plan", self.subscription_plan)
		if plan.is_custom_pricing:
			frappe.throw(
				_("{0} is priced with our team, so it cannot be bought through the "
				  "self-serve flow.").format(plan.plan_name),
				title=_("Talk to Us Instead"),
			)
		if not plan.is_active:
			frappe.throw(_("{0} is no longer available.").format(plan.plan_name))

	def validate_users(self):
		plan = frappe.get_cached_doc("Subscription Plan", self.subscription_plan)
		self.additional_users = max(cint(self.additional_users), 0)
		self.total_users = cint(plan.included_users) + cint(self.additional_users)

		limit = cint(plan.max_users)
		if limit and self.total_users > limit:
			frappe.throw(
				_("{0} allows at most {1} users. Talk to us about Enterprise for more.").format(
					plan.plan_name, limit
				),
				title=_("Too Many Users"),
			)

	def validate_consent(self):
		if not self.accepted_terms:
			frappe.throw(
				_("The terms and the privacy policy have to be accepted."),
				title=_("Consent Required"),
			)
		if not self.accepted_terms_on:
			self.accepted_terms_on = frappe.utils.now_datetime()

	def log_event(self, event_type, details=None, actor=None, ip_address=None):
		"""Append to the audit trail. Every status change goes through here."""
		from a3_sola.api.ratelimit import client_ip

		self.append(
			"event_log",
			{
				"event_time": frappe.utils.now_datetime(),
				"event_type": event_type,
				"actor": actor or frappe.session.user,
				"ip_address": ip_address or client_ip(),
				"details": details,
			},
		)

	def set_status(self, status, reason=None, details=None):
		"""The only way status moves. Writes the event log with it."""
		if self.status == status:
			return
		previous = self.status
		self.status = status
		if reason:
			self.status_reason = reason
		event = {
			"Awaiting Email Verification": "Email Sent",
			"Verified": "Email Verified",
			"Awaiting Payment": "Payment Initiated",
			"Paid": "Payment Succeeded",
			"Payment Failed": "Payment Failed",
			"Provisioning": "Provisioning Started",
			"Active": "Provisioning Completed",
			"Abandoned": "Abandoned",
			"Rejected": "Rejected",
		}.get(status)
		if event:
			self.log_event(event, details or _("{0} to {1}").format(previous, status))

	def snapshot_price(self):
		"""Freeze what this applicant was quoted. Called once, at signup."""
		from a3_sola.api import platform

		result = platform.calculate_plan_total(
			self.plan_code or frappe.db.get_value(
				"Subscription Plan", self.subscription_plan, "plan_code"
			),
			(self.billing_cycle or "Monthly").lower(),
			self.additional_users,
		)
		self.base_amount = flt(result["base_amount"], 2)
		self.additional_user_amount = flt(result["additional_user_amount"], 2)
		self.implementation_fee = flt(result["implementation_fee"], 2)
		self.subtotal = flt(result["subtotal"], 2)
		self.tax_amount = flt(result["tax_amount"], 2)
		self.total_amount = flt(result["total_amount"], 2)
		self.currency = result["currency"]
		self.total_users = result["total_users"]
		self.price_breakdown = frappe.as_json(result["line_items"])
		return result
