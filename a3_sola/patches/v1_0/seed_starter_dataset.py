# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Seed one of everything - but only where the site has asked for it.

A patch runs on every `bench migrate`, on every site, including production. Seeding sample
records unconditionally would put a fictional consumer and a fictional subscription into a
real customer's database, and they would find it before anybody here did. So this is
opt-in, and the switch is in the site's own config rather than in a settings record that a
migration could create before anyone has seen it:

    bench --site <site> set-config a3s_seed_starter_data true
    bench --site <site> migrate

The same dataset is available directly, which is usually what you want:

    bench --site <site> execute a3_sola.setup.starter.install
    bench --site <site> execute a3_sola.setup.starter.teardown

Idempotent either way: it creates nothing the second time.
"""

import frappe


def execute():
	if not frappe.conf.get("a3s_seed_starter_data"):
		return None

	from a3_sola.setup.starter import install

	try:
		return install()
	except Exception:
		# A starter dataset must never be the reason a migration fails. The schema change
		# is what matters; sample records are a convenience, and a half-seeded site with a
		# completed migration is recoverable by re-running the command by hand.
		frappe.db.rollback()
		frappe.log_error(
			title="a3_sola: starter dataset could not be seeded",
			message=(
				"The migration itself completed. Re-run it with:\n"
				"  bench --site <site> execute a3_sola.setup.starter.install\n\n"
				+ frappe.get_traceback()
			),
		)
		return None
