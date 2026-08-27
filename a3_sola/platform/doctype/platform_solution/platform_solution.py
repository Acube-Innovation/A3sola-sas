# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Who the product is for: one homepage card and one detail page at /solutions/<route>."""

import frappe
from frappe import _
from frappe.website.website_generator import WebsiteGenerator

from a3_sola.api import platform


class PlatformSolution(WebsiteGenerator):
	website = frappe._dict(
		template="templates/generators/platform_solution.html",
		condition_field="is_published",
		page_title_field="solution_name",
	)

	def autoname(self):
		self.name = frappe.model.naming.make_autoname("PLT-SOLN-.###")

	def validate(self):
		self.route = platform.resolve_route("solutions", self.route, self.solution_name, self.name)
		platform.validate_bullets(self.key_outcomes, limit=6, label=_("key outcomes"))

	def on_update(self):
		super().on_update()
		platform.clear_content_cache()

	def on_trash(self):
		super().on_trash()
		platform.clear_content_cache()

	def get_context(self, context):
		context.no_cache = 1
		context.parents = [{"label": _("Solutions"), "route": "solutions"}]
		context.title = self.meta_title or self.solution_name
		context.page_meta_title = self.meta_title or self.solution_name
		context.page_meta_description = self.meta_description or self.short_description
		context.siblings = platform.sibling_content("Platform Solution", self.name, limit=4)
		context.settings = platform.site_settings()
		context.breadcrumb_schema = platform.breadcrumb_schema(
			[("Home", ""), ("Solutions", "solutions"), (self.solution_name, self.route)]
		)
		return context
