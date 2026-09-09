# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Task rows that point at documents which no longer exist let go of them.

Before the engine listened to `on_trash`, a task document deleted by hand or by a purge
left its installation with a Dynamic Link to nothing - unsaveable, and a 404 behind the
task link. Every open job is checked once; from now on the installation heals itself on
save and a deletion releases its row as it happens.
"""

import frappe


def execute():
	from a3_sola.api import tasks

	healed = 0
	for name in frappe.get_all("Solar Installation", filters={"docstatus": ["<", 2]}, pluck="name"):
		frappe.db.savepoint("a3s_dangling")
		try:
			if tasks.release_dangling_links(name, save=True):
				healed += 1
		except Exception:
			frappe.db.rollback(save_point="a3s_dangling")
			frappe.log_error(frappe.get_traceback(), f"a3_sola: dangling task links on {name}")
	frappe.db.commit()
	print(f"a3_sola: {healed} installation(s) released links to deleted task documents")
	return healed
