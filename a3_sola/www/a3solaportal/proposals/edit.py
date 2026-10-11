# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Edit page for one proposal: the same two tabs as the create page (api/portal_proposal)."""

import frappe

from a3_sola.api import portal_proposal
from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import record_route

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("proposals", name) + "/edit" if name else "/a3solaportal/proposals")
	portal_proposal.page_context(context, name)
	return context
