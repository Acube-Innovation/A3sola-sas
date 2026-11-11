# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Solar Design Proposal page: the proposals, and above them the design estimates not yet
made into one, each opening on its builder (api/portal_proposal.unproposed_estimates)."""

from a3_sola.api import portal_proposal
from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import list_context

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/proposals")
	list_context(context, "proposals")
	context.pending = portal_proposal.unproposed_estimates()
	context.list_extra_template = "templates/includes/portal_proposals_pending.html"
	return context
