# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The signup form.

Four steps on one page. The plan and cycle arrive from the pricing CTA's query string, so
somebody who clicked "Growth, annual" sees Growth and annual already chosen.
"""

import frappe

from a3_sola.api import platform

no_cache = 1


def get_context(context):
	context.no_cache = 1
	settings = platform.site_settings()
	context.signup_enabled = bool(settings.enable_public_signup)
	context.plans = platform.get_published_plans()
	context.installation_volumes = platform.INSTALLATION_VOLUMES
	context.organisation_types = (
		"Solar EPC", "Dealer or Distributor", "O&M Service Provider",
		"Multi-Branch Group", "Other",
	)

	# Whatever the pricing CTA sent, validated against what is actually sellable.
	requested = (frappe.form_dict.get("package") or "").strip().lower()
	sellable = {p["plan_code"] for p in context.plans if not p["is_custom_pricing"]}
	context.selected_plan = requested if requested in sellable else (
		next((p["plan_code"] for p in context.plans if p["is_popular"] and not p["is_custom_pricing"]), None)
		or next(iter(sorted(sellable)), None)
	)
	context.selected_cycle = (
		"annual" if (frappe.form_dict.get("cycle") or "").lower() == "annual" else "monthly"
	)
	context.page_meta_title = "Get started"
	context.no_index = True
	return context
