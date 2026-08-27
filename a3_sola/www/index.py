# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The public homepage.

Nothing on this page is written in the template. Every feature, solution, statistic,
integration and price comes from a record in the desk, so marketing can change the site
without a deploy.
"""

from a3_sola.api import platform

no_cache = 1


def get_context(context):
	context.no_cache = 1
	platform.homepage_context(context)
	settings = platform.site_settings()
	context.page_meta_title = settings.meta_title
	context.page_meta_description = settings.meta_description
	return context
