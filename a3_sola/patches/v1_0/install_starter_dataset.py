# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Seed the starter dataset on every site, on the next migrate.

A test company, a user who can sign in as it, and one record of every document the app
defines - so a freshly deployed site has something in it rather than sixty empty list
views.

**Why this is not the earlier `seed_starter_dataset`.** That one was opt-in behind a site
config flag, and it ran - as a no-op - on sites that never set the flag. Frappe records a
patch in `tabPatch Log` the first time it executes and never runs it again, so changing
that patch's body would have had no effect on any site that had already deployed it. A new
module name is the only thing that makes it run. This is the standard way to re-issue a
patch, and it is worth knowing: editing a shipped patch is a no-op.

**What it creates**, all under one company so it is easy to find and easy to remove:

    Company    Starter Solar EPC
    User       starter.engineer@example.com
    Records    one job followed from the first enquiry to its fourth year of service -
               lead, consumer, survey, estimate, eligibility check, proposal, quotation,
               order, installation, work orders, portal application, fee payment and its
               recovery, loan, subsidy claim, snag, commissioning report, net metering
               agreement, project, billing plan, O&M contract, visits, tickets, warranty
               claim and generation readings - plus the platform's own chain from signup
               to an invited tenant user

Every document links back to the one before it, so the whole job can be walked forward
from the Connections panel at the foot of each form. See `docs/STARTER_DATASET.md`.

Idempotent: a second migrate creates nothing.

**To remove it from a site:**

    bench --site <site> execute a3_sola.setup.starter.teardown

That user has a password written in the source (`a3_sola/setup/starter.py`). It is a real
credential on a real site - change it or run the teardown once the site is in use.
"""

import frappe


def execute():
	from a3_sola.setup.starter import install

	try:
		result = install()
	except Exception:
		# Sample data must never be the reason a schema migration fails. The migration is
		# what matters; this is a convenience, and a partially seeded site is recoverable
		# by re-running the command by hand.
		frappe.db.rollback()
		frappe.log_error(
			title="a3_sola: starter dataset could not be seeded",
			message=(
				"The migration itself completed. Re-run the seeding with:\n"
				"  bench --site <site> execute a3_sola.setup.starter.install\n\n"
				+ frappe.get_traceback()
			),
		)
		return None

	coverage = result.get("coverage", {})
	print(
		f"  a3_sola starter dataset: {coverage.get('covered', 0)} of "
		f"{coverage.get('total', 0)} documents have a record"
	)
	return result
