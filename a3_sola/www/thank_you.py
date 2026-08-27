# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Where a demo request lands."""

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	context.page_meta_title = "Thank you"
	return context
