# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class PlatformIntegration(Document):
	def on_update(self):
		from a3_sola.api import platform

		platform.clear_content_cache()
