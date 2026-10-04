# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Component Type is mandatory on a design estimate option.

Options priced on a whole package were written without one and without a make to read it
from. They are the package's inverter alternatives, so they are typed Inverter - as the
estimate types them on save - and submitted estimates can be amended again.
"""

import frappe


def execute():
	frappe.db.sql(
		"""update `tabDesign Estimate Option` set component_type = 'Inverter'
		where ifnull(component_type, '') = '' and ifnull(component_make, '') = ''"""
	)
