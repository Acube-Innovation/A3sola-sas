# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A product capability: one homepage card and one detail page.

A WebsiteGenerator so Frappe owns the routing. Marketing edits the record in the desk and
both the card and the page at /features/<route> change immediately - no deploy.
"""

import frappe
from frappe import _
from frappe.website.website_generator import WebsiteGenerator

from a3_sola.api import platform


class PlatformFeature(WebsiteGenerator):
	website = frappe._dict(
		template="templates/generators/platform_feature.html",
		condition_field="is_published",
		page_title_field="feature_name",
	)

	def autoname(self):
		self.name = frappe.model.naming.make_autoname("PLT-FEAT-.###")

	def validate(self):
		self.route = platform.resolve_route("features", self.route, self.feature_name, self.name)
		platform.validate_bullets(self.card_bullets, limit=3, label=_("card bullets"))

	def on_update(self):
		super().on_update()
		platform.clear_content_cache()

	def on_trash(self):
		super().on_trash()
		platform.clear_content_cache()

	def get_context(self, context):
		context.no_cache = 1
		context.parents = [{"label": _("Features"), "route": "features"}]
		context.title = self.meta_title or self.feature_name
		context.page_meta_title = self.meta_title or self.feature_name
		context.page_meta_description = self.meta_description or self.short_description
		context.siblings = platform.sibling_content("Platform Feature", self.name, limit=4)
		context.settings = platform.site_settings()
		context.breadcrumb_schema = platform.breadcrumb_schema(
			[("Home", ""), ("Features", "features"), (self.feature_name, self.route)]
		)
		return context
