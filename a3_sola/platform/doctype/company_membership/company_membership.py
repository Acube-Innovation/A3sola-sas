# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One person's place in one company: their type and roles there.

The login is shared; the access is not. See a3_sola/api/memberships.py for how the active
membership becomes the user's real roles and company permission.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime


class CompanyMembership(Document):
	def validate(self):
		from a3_sola.api import memberships

		self.tenant = frappe.db.get_value("Company", self.company, "a3_sola_tenant") \
			if frappe.get_meta("Company").has_field("a3_sola_tenant") else None
		other = frappe.db.get_value(self.doctype, {"user": self.user, "company": self.company,
			"name": ["!=", self.name or ""]}, "name")
		if other:
			frappe.throw(_("{0} already works in {1}.").format(self.user, self.company), frappe.DuplicateEntryError)
		protected = [r.role for r in self.roles if memberships.is_protected_role(r.role)]
		if protected:
			frappe.throw(_("{0} is an instance-wide role and cannot be given for one company.").format(
				", ".join(protected)))
		if not self.roles and self.role_profile:
			self.set("roles", [{"role": r} for r in memberships.clean_roles(memberships.profile_roles(self.role_profile))])
		roles = [r.role for r in self.roles]
		self.is_admin = cint(self.portal_type == "Admin")
		self.desk_access = cint(memberships.desk_access(roles))
		self.counts_seat = self.desk_access
		if self.is_new():
			self.added_on = self.added_on or now_datetime()
			self.added_by = self.added_by or frappe.session.user
		self._check_seat()

	def _check_seat(self):
		if not self.tenant or not cint(self.enabled) or not cint(self.counts_seat) or frappe.flags.a3s_migrating:
			return
		before = self.get_doc_before_save()
		if before and cint(before.enabled) and cint(before.counts_seat) and before.tenant == self.tenant:
			return  # already counted
		if frappe.db.get_value("Tenant", self.tenant, "admin_user") == self.user:
			return
		from a3_sola.api.entitlements import assert_seat_available, seat_holders

		if self.user in seat_holders(self.tenant):
			return  # already holds a seat here (created a moment ago, say)
		assert_seat_available(self.tenant, for_email=self.user, counting_pending=False)

	def on_update(self):
		from a3_sola.api import memberships

		self._recalculate()
		if frappe.flags.a3s_migrating:
			return
		active = memberships.active_company(self.user) == self.company
		if active and not memberships.eligible(self):
			memberships.leave_if_active(self.user, self.company)
		elif active or self.flags.get("a3s_apply"):
			memberships.apply_membership(self.user, self.company)

	def on_trash(self):
		from a3_sola.api import memberships

		memberships.leave_if_active(self.user, self.company)

	def after_delete(self):
		self._recalculate()

	def _recalculate(self):
		before = self.get_doc_before_save()
		tenants = {self.tenant, before.tenant if before else None} - {None, ""}
		from a3_sola.api.entitlements import recalculate_usage

		for tenant in tenants:
			if frappe.db.exists("Tenant", tenant):
				recalculate_usage(tenant)
