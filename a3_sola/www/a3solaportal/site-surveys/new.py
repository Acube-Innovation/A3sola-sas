# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Create page for the "site-surveys" collection. All logic is shared; this only names the slug."""

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import new_context

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/site-surveys/new")
	new_context(context, "site-surveys")
	return context
