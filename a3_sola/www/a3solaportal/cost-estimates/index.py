# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""List page for the "cost-estimates" collection - ERPNext Quotations. Shared logic; this names the slug."""

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import list_context

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/cost-estimates")
	list_context(context, "cost-estimates")
	return context
