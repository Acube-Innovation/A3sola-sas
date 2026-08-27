# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The standalone pricing page: the same pricing block as the homepage, plus the FAQ."""

from a3_sola.api import platform

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.plans = platform.get_published_plans()
	context.faq_groups = _grouped_faqs()
	context.software_schema = platform.software_schema(context.plans)
	context.faq_schema = platform.faq_schema(platform.faqs())
	context.page_meta_title = "Pricing - a3 sola"
	context.page_meta_description = (
		"Starter, Growth and Enterprise plans for solar EPCs. Two months free on annual "
		"billing, with the implementation fee waived."
	)
	return context


def _grouped_faqs():
	rows = platform.faqs()
	grouped = {}
	for row in rows:
		grouped.setdefault(row.faq_group, []).append(row)
	order = ("Pricing", "Product", "Implementation", "Support")
	return [(group, grouped[group]) for group in order if group in grouped]
