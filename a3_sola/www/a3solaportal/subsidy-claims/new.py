# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Create page for the "subsidy-claims" collection. All logic is shared; this only names the slug."""

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import new_context

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/subsidy-claims/new")
	new_context(context, "subsidy-claims")
	return context
