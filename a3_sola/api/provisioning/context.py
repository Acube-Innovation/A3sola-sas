# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What a provisioning run carries between its steps.

Steps read and write this object and nothing else. They do not reach into globals, do not
re-query the subscription, and do not read live settings for anything that was snapshotted
- so a step can be tested by constructing a context and calling it, and so the ordering of
steps is the only thing that decides what a step can see.
"""

import frappe
from frappe.utils import cint

from a3_sola.api.settings import get_value


class ProvisioningContext:
	def __init__(self, subscription, job=None, triggered_by="Payment Webhook"):
		self.subscription = subscription
		self.job = job
		self.triggered_by = triggered_by

		self.signup = None
		self.payment_order = None
		self.plan = None
		self.entitlements = {}
		self.blueprint = None
		self.tenant = None
		self.company = None
		self.admin_user = None
		self.strategy = None

		#: Everything the run created, keyed by step code. Rollback reads this, and the
		#: failure report shows it to whoever has to clean up by hand.
		self.artefacts = {}
		self.warnings = []

	# ------------------------------------------------------------------ helpers
	def note(self, message):
		"""Something worth telling a human that is not a failure."""
		self.warnings.append(message)
		frappe.logger("a3_sola").info({"event": "provisioning_note", "message": message})

	def record(self, step_code, doctype, name):
		self.artefacts.setdefault(step_code, []).append({"doctype": doctype, "name": name})

	def created(self, step_code):
		return self.artefacts.get(step_code, [])

	def reload_tenant(self):
		if self.tenant:
			self.tenant = frappe.get_doc("Tenant", self.tenant.name)
		return self.tenant

	# -------------------------------------------------------------- entitlements
	def snapshot_entitlements(self, plan_name, additional_users=0):
		"""Copy the plan's entitlements once, at provisioning time, and never again.

		Price is snapshotted at signup for the same reason: the customer bought what they
		were shown. If Starter later becomes eight users, existing Starter tenants keep
		the five they paid for until somebody explicitly changes their plan.
		"""
		plan = frappe.get_cached_doc("Subscription Plan", plan_name)
		included = cint(plan.included_users)
		modules = [
			{"module_name": row.module_name, "is_enabled": cint(row.is_enabled)}
			for row in plan.enabled_modules
		]
		self.plan = plan
		self.entitlements = {
			"subscription_plan": plan.name,
			"plan_code": plan.plan_code,
			"included_users": included,
			"additional_users": cint(additional_users),
			"user_quota": included + cint(additional_users),
			"max_companies": cint(plan.included_companies) or 1,
			"storage_limit_gb": cint(plan.storage_limit_gb),
			"assigned_role_profile": plan.role_profile
			or get_value("admin_role_profile_fallback"),
			"enabled_modules": modules,
		}
		return self.entitlements

	def enabled_module_names(self):
		source = self.tenant.enabled_modules if self.tenant else self.entitlements.get("enabled_modules", [])
		out = []
		for row in source:
			name = row.get("module_name") if isinstance(row, dict) else row.module_name
			enabled = row.get("is_enabled") if isinstance(row, dict) else row.is_enabled
			if cint(enabled):
				out.append(name)
		return out

	def token_context(self):
		"""What a blueprint payload may substitute. Nothing outside this reaches a payload."""
		tenant = self.tenant
		return {
			"tenant": tenant.name if tenant else "",
			"tenant_code": tenant.tenant_code if tenant else "",
			"tenant_name": tenant.tenant_name if tenant else "",
			"company": self.company or (tenant.company if tenant else ""),
			"company_abbr": frappe.db.get_value("Company", self.company, "abbr") if self.company else "",
			"state": tenant.state if tenant else "",
			"state_code": tenant.state_code if tenant else "",
			"country": (tenant.country if tenant else "") or get_value("provisioning_default_country"),
			"currency": get_value("provisioning_default_currency") or "INR",
			"admin_email": tenant.primary_contact_email if tenant else "",
		}
