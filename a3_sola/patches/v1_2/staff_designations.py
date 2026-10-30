# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The designations Renewcore's staff hold that ERPNext does not ship: Managing Partner,
Project Coordinator, Project Engineer, Sales Coordinator.

A site that once had HRMS installed keeps a "skills" table on Designation whose code is gone,
so a Designation cannot be created the usual way (nor over the API) - the record, which is
only its name, is written directly."""

import frappe
from frappe.utils import now

DESIGNATIONS = ("Managing Partner", "Project Coordinator", "Project Engineer", "Sales Coordinator")


def execute():
	for name in DESIGNATIONS:
		if frappe.db.exists("Designation", name):
			continue
		stamp = now()
		frappe.get_doc({"doctype": "Designation", "designation_name": name, "name": name, "owner": "Administrator",
			"modified_by": "Administrator", "creation": stamp, "modified": stamp}).db_insert()
	frappe.db.commit()
