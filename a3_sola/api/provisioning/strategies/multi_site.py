# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Multi-site tenancy. NOT IMPLEMENTED - and the reason matters.

`bench new-site` cannot run inside a web worker. It needs to create a database, write to
the sites directory and run migrations, which are OS-level privileges the web process must
never hold: a web process that can create databases is a web process that can drop them,
and it is reachable from the internet.

The correct shape, for whoever implements this:

  * A queue table the web process writes to, and nothing else. The web process never
    shells out - not once, not "just for the site name".
  * A supervised runner under its own account, polling that queue, with a narrow and
    audited command allowlist. It executes site creation, app installation and migration.
  * The site name comes from the validated `tenant_code` and from nothing else. Command
    construction from user input is forbidden outright, not merely escaped - escaping is a
    thing people get right until the day they do not.
  * Provisioning becomes minutes rather than seconds, so the customer-facing progress
    indicator and the job status surface stop being nice-to-have.
  * Isolation verification in this model asserts the database is genuinely separate and
    that no cross-site connection string is reachable from tenant code.

Until then, this class refuses loudly. A strategy that half-works would be worse than one
that does not exist: it would create the site and leave the isolation unproven.
"""

from a3_sola.api.provisioning.strategies import TenancyStrategy

REASON = (
	"The multi-site tenancy strategy is not implemented. It requires a privileged "
	"out-of-process runner - see a3_sola/api/provisioning/strategies/multi_site.py and "
	"docs/TENANCY_MODEL.md. Set tenancy_strategy to Multi Company in A3 Sola Settings."
)


class MultiSiteStrategy(TenancyStrategy):
	name = "Multi Site"

	def create_company(self, context):
		raise NotImplementedError(REASON)

	def create_structures(self, context):
		raise NotImplementedError(REASON)

	def seed_masters(self, context):
		raise NotImplementedError(REASON)

	def create_admin(self, context):
		raise NotImplementedError(REASON)

	def verify_isolation(self, context):
		raise NotImplementedError(REASON)

	def teardown(self, context):
		raise NotImplementedError(REASON)

	def rollback_company(self, context, step_log):
		raise NotImplementedError(REASON)

	def rollback_structures(self, context, step_log):
		raise NotImplementedError(REASON)

	def rollback_masters(self, context, step_log):
		raise NotImplementedError(REASON)
