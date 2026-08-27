# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Text from the Web Page record, chrome from this site."""

from a3_sola.api import platform

no_cache = 1


def get_context(context):
	return platform.legal_page_context(context, "privacy")
