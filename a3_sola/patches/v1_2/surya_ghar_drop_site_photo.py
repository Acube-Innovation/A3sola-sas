# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""PM Surya Ghar registration (NPA) no longer lists the pre-installation site photo: its rows go
from the running projects' registers."""

import frappe


def execute():
	frappe.db.sql("""delete from `tabInstallation Document`
		where parenttype='Solar Installation' and stage_code='NPA' and document_name='Pre-installation site photo'""")
