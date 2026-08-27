# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What the product is sold for, and what a customer gets.

This record is read by three later phases: Phase 5 prices from it, Phase 6 provisions
users and modules from its entitlements, Phase 7 bills from it. The plan_code is the
identifier that travels through all of them and appears in every public pricing link, so
it is validated hard and warned about on change.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SubscriptionPlan(Document):
	def autoname(self):
		self.name = frappe.model.naming.make_autoname("PLT-PLAN-.###")

	def validate(self):
		self.validate_code()
		self.validate_commercials()
		self.warn_on_annual_mismatch()
		self.validate_inheritance()

	def validate_code(self):
		self.plan_code = (self.plan_code or "").strip().lower()
		if not CODE_PATTERN.match(self.plan_code):
			frappe.throw(
				_("Plan code {0} must be lowercase letters, digits and hyphens only - it "
				  "appears in every public pricing link.").format(frappe.bold(self.plan_code)),
				title=_("Invalid Plan Code"),
			)
		if not self.is_new():
			before = self.get_doc_before_save()
			if before and before.plan_code and before.plan_code != self.plan_code:
				frappe.msgprint(
					_("The plan code changed from {0} to {1}. Every pricing link and every "
					  "signup already in flight carries the old code.").format(
						before.plan_code, self.plan_code
					),
					title=_("Plan Code Changed"),
					indicator="orange",
				)

	def validate_commercials(self):
		"""A plan that is sold self-serve has to have a price and a user count."""
		if self.is_custom_pricing:
			return
		if not flt(self.monthly_price):
			frappe.throw(
				_("A plan without custom pricing needs a monthly price."),
				title=_("Price Missing"),
			)
		if not cint(self.included_users):
			frappe.throw(
				_("A plan without custom pricing needs an included user count."),
				title=_("Users Missing"),
			)
		if cint(self.max_users) and cint(self.max_users) < cint(self.included_users):
			frappe.throw(
				_("The maximum of {0} users is below the {1} included.").format(
					self.max_users, self.included_users
				),
				title=_("Impossible Limit"),
			)

	def warn_on_annual_mismatch(self):
		"""Warn, never block. Marketing is allowed to price a promotion however it likes."""
		if self.is_custom_pricing or not flt(self.annual_price) or not flt(self.monthly_price):
			return
		expected = flt(self.monthly_price) * (12 - cint(self.annual_months_free))
		if abs(flt(self.annual_price) - expected) > 1:
			frappe.msgprint(
				_("The annual price of {0} does not match {1} months at {2} ({3}). That is "
				  "allowed - just confirm it is deliberate.").format(
					self.annual_price, 12 - cint(self.annual_months_free),
					self.monthly_price, expected,
				),
				title=_("Annual Price Looks Off"),
				indicator="orange",
			)

	def validate_inheritance(self):
		if not self.inherits_from_plan:
			return
		if self.inherits_from_plan == self.name:
			frappe.throw(_("A plan cannot inherit from itself."))
		seen, current = {self.name}, self.inherits_from_plan
		while current:
			if current in seen:
				frappe.throw(
					_("Plan inheritance loops back on itself."), title=_("Circular Inheritance")
				)
			seen.add(current)
			current = frappe.db.get_value("Subscription Plan", current, "inherits_from_plan")

	def on_update(self):
		from a3_sola.api import platform

		platform.clear_content_cache()
