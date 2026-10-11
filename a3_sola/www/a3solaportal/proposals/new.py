# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Create page for a proposal: the desk form's two tabs, lead first (api/portal_proposal)."""

from a3_sola.api import portal_proposal
from a3_sola.www.a3solaportal import require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/proposals/new")
	portal_proposal.page_context(context)
	return context
