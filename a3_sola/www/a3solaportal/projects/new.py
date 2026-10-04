# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Create page for the "projects" collection: the lead is chosen first, the rest follows from it."""

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import lead_first_context

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/projects/new")
	lead_first_context(context, "projects")
	return context
