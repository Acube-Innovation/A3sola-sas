# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The bank's project proposal in RIM's format: its cover - title, customer, number, date - is a
page of its own (documents.rim_cover), as in Project Proposal_2kW.docx, so the template's
first page starts with the date and the letter. Only the cover's lines are taken out; the rest
of a template, as a company may have edited it, stays."""

import frappe

CODE = "BANK-PROJECT-PROPOSAL"
COVER = '''<p style="text-align:center;font-weight:bold;margin-bottom:0">For</p>
<p style="text-align:center;font-weight:bold;font-size:13pt;margin-bottom:0">{{ (consumer.consumer_name or "") | upper }}</p>
<p style="text-align:center;font-weight:bold">{{ ((section.district if section else "") or "") | upper }}</p>
<h2>SOLAR PROJECT PROPOSAL</h2>
<p style="text-align:center">No. {{ installation.solar_proposal or installation.name }} &nbsp;&nbsp; Date &ndash; {{ today }}</p>'''
LETTER = '''{#- The cover - title, the customer, number and date - is a page of its own (documents.rim_cover). -#}
<p style="text-align:right">{{ today }}</p>'''


def execute():
	for row in frappe.get_all("Solar Document Template", filters={"template_code": CODE}, fields=["name", "body_template", "version"]):
		body = row.body_template or ""
		if COVER not in body:
			continue
		frappe.db.set_value("Solar Document Template", row.name,
			{"body_template": body.replace(COVER, LETTER), "version": (row.version or 1) + 1}, update_modified=False)
