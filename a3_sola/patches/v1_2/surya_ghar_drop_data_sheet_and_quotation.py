# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""PM Surya Ghar registration (NPA) no longer lists the national portal application data sheet or
the Bank Quotation (still on Accept Customer): their rows go from the running projects' registers."""

import frappe

CODE = "NPA"
DROPPED = ("National portal application data sheet", "Bank Quotation")


def execute():
	frappe.db.sql("""delete from `tabInstallation Document`
		where parenttype='Solar Installation' and stage_code=%s and document_name in %s""", (CODE, DROPPED))
