# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A KYC paper uploaded on the lead now counts for its customer: every customer's stored KYC
status, and its jobs', is derived again with them."""

import frappe

from a3_sola.api import kyc


def execute():
	for name in frappe.get_all("Solar Consumer", pluck="name"):
		kyc.refresh(name)
