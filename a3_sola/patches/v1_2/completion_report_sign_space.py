# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The bank's Project Completion Report leaves room above "Sign and Seal of the Vendor" for the
signature and seal. A template is data a tenant may have edited, so only the sign line still as
first seeded is changed."""

import frappe

CODE = "BANK-COMPLETION-REPORT"
OLD = '<table width="100%"><tr>\n  <td>Sign and Seal of the Vendor</td>'
NEW = '<table width="100%" style="margin-top:28mm"><tr>\n  <td>Sign and Seal of the Vendor</td>'


def execute():
	for name, body in frappe.get_all("Solar Document Template", filters={"template_code": CODE},
			fields=["name", "body_template"], as_list=True):
		if body and OLD in body:
			frappe.db.set_value("Solar Document Template", name, "body_template", body.replace(OLD, NEW),
				update_modified=False)
