# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""How a tenant gets a workspace - the one decision Phases 1 to 5 deliberately deferred.

Two models, and the choice between them is architectural rather than a preference:

  **Multi Company** - every tenant is a Company inside one Frappe site, isolated by User
  Permissions and the permission hooks built across Phases 1 to 5. Provisioning takes
  seconds and runs in an ordinary background worker. Cross-tenant reporting is a query.
  The blast radius of a permission bug is every tenant.

  **Multi Site** - every tenant is its own Frappe site with its own database. Isolation is
  structural rather than enforced. Provisioning takes minutes and needs OS-level
  privileges the web process must never hold. Upgrades are one migrate per site.

Multi Company is right for the first twenty to fifty tenants and lets the product ship.
Multi Site becomes right when one tenant's data loss would end the business, or when one
tenant's data volume starts degrading everyone else's queries. The interface exists so
that day is an implementation swap rather than a rewrite. See docs/TENANCY_MODEL.md.

The strategy is always resolved from the **tenant's snapshot**, never from the live
setting - otherwise flipping the setting would silently reclassify every existing tenant.
"""

import frappe
from frappe import _


class TenancyStrategy:
	name = ""

	# ------------------------------------------------------- workspace creation
	def create_workspace(self, context):
		"""Steps 05 and 06 together. The orchestrator calls the parts individually."""
		self.create_company(context)
		return self.create_structures(context)

	def create_company(self, context):
		raise NotImplementedError

	def create_structures(self, context):
		raise NotImplementedError

	def seed_masters(self, context):
		raise NotImplementedError

	def create_admin(self, context):
		raise NotImplementedError

	def verify_isolation(self, context):
		raise NotImplementedError

	def teardown(self, context):
		raise NotImplementedError

	# ------------------------------------------------------------- rollback legs
	def rollback_company(self, context, step_log):
		raise NotImplementedError

	def rollback_structures(self, context, step_log):
		raise NotImplementedError

	def rollback_masters(self, context, step_log):
		raise NotImplementedError


def get_strategy(name):
	from a3_sola.api.provisioning.strategies.multi_company import MultiCompanyStrategy
	from a3_sola.api.provisioning.strategies.multi_site import MultiSiteStrategy

	strategies = {
		"Multi Company": MultiCompanyStrategy,
		"Multi Site": MultiSiteStrategy,
	}
	cls = strategies.get(name or "Multi Company")
	if not cls:
		frappe.throw(_("Unknown tenancy strategy {0}.").format(name), title=_("Bad Strategy"))
	return cls()
