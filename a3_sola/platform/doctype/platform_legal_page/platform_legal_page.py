# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Privacy, terms and refund text, editable from the desk.

Deliberately not a Web Page: Frappe's document renderer claims a Web Page's route ahead
of a template, which would put the legal text in different chrome from the rest of the
site. This keeps the text editable and the page ours.

The draft banner is driven by `reviewed_by_lawyer`, not by a constant, so it disappears
the day the review actually happens rather than the day somebody remembers to delete it.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class PlatformLegalPage(Document):
	def validate(self):
		self.page_key = (self.page_key or "").strip().strip("/").lower()
		if not self.page_key:
			frappe.throw(_("A legal page needs a URL key."))
		if self.reviewed_by_lawyer and not (self.reviewed_by and self.reviewed_on):
			frappe.throw(
				_("Record who reviewed this page and when before marking it reviewed."),
				title=_("Review Details Missing"),
			)

	def on_update(self):
		from a3_sola.api import platform

		platform.clear_content_cache()
