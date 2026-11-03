# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Renewcore's letterhead as the site's default Letter Head, which ERPNext's own prints take
(a quotation or invoice printed from the desk). RIM's is kept for the bank's and PM Surya
Ghar's documents only (documents.RIM_TEMPLATES, rim_letter_head)."""

import frappe

RENEWCORE = "Renewcore Innovations LLP"


def execute():
	if not frappe.db.exists("Letter Head", RENEWCORE):
		return
	frappe.db.sql("update `tabLetter Head` set is_default = 0 where name != %s", RENEWCORE)
	frappe.db.set_value("Letter Head", RENEWCORE, "is_default", 1)
	frappe.clear_cache()
