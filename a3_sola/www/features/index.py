# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every published feature, grouped the way a buyer thinks about them."""

from a3_sola.api import platform

no_cache = 1

GROUP_ORDER = ("Core", "Operations", "Finance", "Service", "Analytics")


def get_context(context):
	context.no_cache = 1
	features = platform.all_features()
	grouped = {}
	for feature in features:
		grouped.setdefault(feature.feature_group, []).append(feature)

	context.groups = [
		(group, grouped[group]) for group in GROUP_ORDER if group in grouped
	]
	context.bullets = platform.bullets_for(
		"Platform Feature", [f.name for f in features], "card_bullets"
	)
	context.page_meta_title = "Features - everything a solar EPC has to do"
	context.page_meta_description = (
		"Solar CRM, subsidy management, KSEB and bank document automation, installation "
		"tracking, O&M contracts, service SLAs and project accounting."
	)
	return context
