# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""/event-screen/<key>: the stall screen - the TV at the event that welcomes each visitor as
they register (Solar Event, api/event_screen). Opened from the event page; the key is the
event's display key, never the QR's."""

import frappe

from a3_sola.api import event_registration as reg
from a3_sola.api import event_screen
from a3_sola.api.events import qr_svg

no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_index = True
	event = event_screen.screen_event(frappe.form_dict.get("key"))
	context.screen = None
	if event:
		company = reg.company_name(event.company)
		context.screen = frappe._dict(
			key=frappe.form_dict.get("key"), event_name=event.event_name, company=company,
			logo=reg.company_logo(event.company),
			headline=(event.screen_headline or "").strip() or "Welcome to {0}".format(company),
			qr_svg=qr_svg(reg.register_url(event), color="#1d2433"),
			max_subsidy=max_subsidy(),
		)
	context.page_meta_title = context.screen.event_name if context.screen else "Stall screen"
	return context


def max_subsidy():
	"""The most a home gets under the default subsidy scheme - "Up to ₹78,000" on the screen - read
	from the scheme, not typed; None when there is no scheme (the slide is left out)."""
	from frappe.utils import flt

	from a3_sola.api import calculations
	from a3_sola.api.settings import get_value

	scheme = get_value("default_subsidy_scheme")
	if not scheme or not frappe.db.exists("Subsidy Scheme", scheme):
		return None
	try:
		category = frappe.db.get_value("Subsidy Scheme", scheme, "consumer_category") or "Residential"
		amount = flt(calculations.get_subsidy_amount(scheme, 10, category)["subsidy_amount"])
	except Exception:
		return None
	return int(amount) or None
