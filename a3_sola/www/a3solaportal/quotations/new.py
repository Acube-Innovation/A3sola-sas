# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A new quotation: one option of a proposal, chosen by lead or proposal (api/quotation_option)."""

from a3_sola.api import quotation_option
from a3_sola.www.a3solaportal import require_login

no_cache = 1


def get_context(context):
	require_login("/a3solaportal/quotations/new")
	quotation_option.page_context(context)
	return context
