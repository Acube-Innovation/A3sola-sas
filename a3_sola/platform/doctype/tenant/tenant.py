# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One customer workspace.

The entitlement fields on this document are a **snapshot**, and that word is doing real
work. They are copied from the Subscription Plan once, at provisioning, and enforcement
reads them and never the live plan. If Starter becomes eight users next quarter, every
existing Starter tenant keeps the five they paid for until somebody deliberately changes
their plan and re-snapshots. The alternative - reading the plan at enforcement time - means
a marketing decision silently changes what every existing customer is entitled to, in both
directions.

Phase 7 owns the Suspended, Cancelled and Terminated transitions. It calls
`set_tenant_access_state` rather than reaching in with `db_set` from a dozen places, so
there is one funnel to audit and one place to add a side effect.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from a3_sola.api.naming import set_name
from a3_sola.api.provisioning import identifiers


class Tenant(Document):
	def autoname(self):
		set_name(self, "tenant_series_prefix", ".YYYY.-.#####", fallback="TNT")

	def before_insert(self):
		"""A new tenant has no company until step 05 creates one. Never the session's.

		Frappe fills any field literally named `company` from the user's default during
		`insert()` - `_set_defaults()` runs there, so clearing the field beforehand does
		not survive. On a Tenant that default is actively dangerous: a tenant that never
		reaches company creation would carry the operator's own company, and anything
		later reading `tenant.company` - provisioning, reporting, cleanup - would act on
		somebody else's workspace.
		"""
		self.company = None

	def validate(self):
		self.validate_code()
		self.derive_quota()
		self.derive_seats()

	def validate_code(self):
		self.tenant_code = (self.tenant_code or "").strip().lower()
		identifiers.validate_code(self.tenant_code)
		clash = frappe.db.get_value(
			"Tenant", {"tenant_code": self.tenant_code, "name": ["!=", self.name]}, "name"
		)
		if clash:
			frappe.throw(
				_("Tenant code {0} is already used by {1}.").format(self.tenant_code, clash),
				title=_("Duplicate Tenant Code"),
			)

	def derive_quota(self):
		self.user_quota = cint(self.included_users) + cint(self.additional_users)

	def derive_seats(self):
		self.seats_available = max(
			0, cint(self.user_quota) - cint(self.active_users) - cint(self.pending_invitations)
		)

	def on_submit(self):
		if not self.provisioned_on:
			self.provisioned_on = now_datetime()

	def on_cancel(self):
		if self.company:
			frappe.throw(
				_("This tenant has a company and cannot be cancelled. Terminate it instead - "
				  "termination exports the data and disables access without deleting "
				  "anything."),
				title=_("Cannot Cancel"),
			)

	def on_trash(self):
		if self.company:
			frappe.throw(
				_("A tenant with a company is never deleted. Nothing in this product deletes "
				  "a customer's company - see docs/PROVISIONING_RUNBOOK.md."),
				title=_("Cannot Delete"),
			)


def set_tenant_access_state(tenant, state, reason):
	"""PHASE 7 IMPLEMENTS THIS.

	Contract:

	* The single entry point for every access-state change after provisioning: Suspended,
	  Cancelled, Terminated, and the return journeys. Phase 6 sets Active exactly once, at
	  the end of provisioning, and touches nothing afterwards.
	* It must set the Tenant status and `status_reason`, disable or re-enable the tenant's
	  users to match, and leave the Company and its data untouched in every case. Nothing
	  in this product deletes a customer's company.
	* It must be idempotent: calling it twice with the same state changes nothing the
	  second time, because a daily lifecycle job will call it repeatedly.
	* It must write an audit entry, because switching a paying customer off is exactly the
	  kind of action somebody asks about six months later.
	"""
	raise NotImplementedError(
		"Phase 7 implements set_tenant_access_state: the one funnel for suspension, "
		"cancellation and reactivation."
	)
