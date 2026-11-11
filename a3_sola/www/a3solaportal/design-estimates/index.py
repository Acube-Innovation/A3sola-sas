# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The design estimates are the steps of a Solar Design Proposal, and are listed there: an
estimate not yet made into a proposal, beside the proposals. This list sends the person on."""

import frappe

from a3_sola.www.a3solaportal import require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/proposals")
	frappe.local.flags.redirect_location = "/a3solaportal/proposals"
	raise frappe.Redirect
