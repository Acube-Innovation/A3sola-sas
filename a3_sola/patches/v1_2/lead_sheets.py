# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Google Sheets leads come in on, kept by name in A3 Sola Settings (Lead Sheets) so the
import dialog reads any of them with one click. Starts with Renewcore's Meta leads sheet,
unless that link is kept already."""

import frappe

FIRST = ("Renewcore New Meta Leads",
	"https://docs.google.com/spreadsheets/d/1WczoLTNLKxaKGp_NGG_JNmEWEc33AG9ghIYM9yy7WsQ/edit?usp=sharing")


def execute():
	frappe.reload_doc("solar_crm", "doctype", "lead_import_sheet")
	frappe.reload_doc("solar_crm", "doctype", "a3_sola_settings")
	from a3_sola.api.lead_import import add_sheet, saved_sheets

	if not any(s["url"] == FIRST[1] for s in saved_sheets()):
		add_sheet(*FIRST)
