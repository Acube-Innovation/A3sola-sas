# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The stall screen's feed: what the TV at the stall shows, polled every two seconds by
www/event_screen.

The screen's link carries the event's display key - a different key from the QR's, so a
visitor holding the registration link can never open it. It returns only what the screen
shows: a visitor's full name, district, property and system type, their mobile masked
("98••• ••345"), their indicative estimate, and that the brochure reached them - never the full
number, an address, a bill or a document. A visitor who asked not to be shown, or whom staff
hid, is welcomed as "a visitor from <district>" and shows none of it.

Polling rather than realtime: a guest's realtime events reach every website visitor, and a
poll survives the exhibition hall's Wi-Fi dropping without reconnect logic.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime, today

from a3_sola.api.ratelimit import enforce

EVENT = "Solar Event"
LEAD = "Lead"
#: A screen polls every 2 s: 1,800 an hour. Room for two screens on one link, and a reload.
POLLS_PER_HOUR = 4000
#: The first poll shows what happened in the last few minutes, not the whole day again.
FIRST_LOOKBACK_MINUTES = 3
#: Every later poll looks this far behind the screen's last one. A registration is stamped when
#: it starts but is only seen once it is saved - seconds later with papers on a phone - and by
#: then the screen has moved on. The screen skips the moments it has already played (their key).
OVERLAP_SECONDS = 300
TICKER = 8


def screen_event(key):
	"""The event a screen link names, or None."""
	key = (key or "").strip()
	if not key or len(key) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
		return None
	return frappe.db.get_value(EVENT, {"display_key": key}, ["name", "event_name", "company", "public_key",
		"screen_headline", "show_estimate_on_screen", "is_active", "brochure"], as_dict=True)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def feed(key, after=None):
	"""New moments since `after` (welcomes, brochures sent), the counters and the ticker."""
	enforce("event_screen", (key or "")[:64], "event_screen_polls_per_hour", POLLS_PER_HOUR, 3600, detail="feed")
	event = screen_event(key)
	if not event:
		frappe.throw(_("This screen link is not valid."), frappe.PermissionError)
	now = now_datetime()
	try:
		since = add_to_date(get_datetime(after), seconds=-OVERLAP_SECONDS) if after \
			else add_to_date(now, minutes=-FIRST_LOOKBACK_MINUTES)
	except Exception:
		since = add_to_date(now, minutes=-FIRST_LOOKBACK_MINUTES)
	show_estimate = cint(event.show_estimate_on_screen)

	fields = ["name", "lead_name", "first_name", "district", "a3s_registered_on", "a3s_brochure_sent_on",
		"a3s_brochure_sent_via", "a3s_hide_on_screen", "a3s_estimate", "approx_capacity_kw", "a3s_interest",
		"a3s_system_type", "mobile_no"]
	recent = frappe.get_all(LEAD, filters={"a3s_event": event.name}, or_filters=[["a3s_registered_on", ">", since],
		["a3s_brochure_sent_on", ">", since]], fields=fields, order_by="a3s_registered_on asc", limit=200)
	items = []
	for l in recent:
		who = _who(l, show_estimate)
		if l.a3s_registered_on and get_datetime(l.a3s_registered_on) > since:
			items.append({"kind": "welcome", "at": str(l.a3s_registered_on), "id": l.name,
				"key": "welcome|{0}|{1}".format(l.name, l.a3s_registered_on), **who})
		if l.a3s_brochure_sent_on and get_datetime(l.a3s_brochure_sent_on) > since:
			items.append({"kind": "sent", "at": str(l.a3s_brochure_sent_on), "id": l.name, "via": l.a3s_brochure_sent_via or "",
				"key": "sent|{0}|{1}".format(l.name, l.a3s_brochure_sent_on), "name": who["name"]})
	items.sort(key=lambda i: i["at"])

	stats = frappe.db.sql("""select count(*) as total,
			sum(case when date(a3s_registered_on) = %(today)s then 1 else 0 end) as today,
			sum(ifnull(approx_capacity_kw, 0)) as kw
		from `tabLead` where a3s_event = %(event)s""", {"event": event.name, "today": today()}, as_dict=True)[0]
	ticker = frappe.get_all(LEAD, filters={"a3s_event": event.name}, fields=fields, order_by="a3s_registered_on desc",
		limit=TICKER)
	savings = sum(_saving(l) for l in frappe.get_all(LEAD, filters={"a3s_event": event.name, "a3s_estimate": ["is", "set"]},
		fields=["a3s_estimate"], limit=5000))
	return {
		"now": str(now), "items": items,
		"counters": {"today": cint(stats.today), "total": cint(stats.total), "kw": round(float(stats.kw or 0), 1),
			"yearly_savings": round(savings * 12)},
		"ticker": [_who(l, False)["name"] for l in ticker],
		"open": cint(event.is_active),
	}


def _who(lead, show_estimate):
	"""How the screen names a visitor: their full name, district, property and system type and
	their mobile masked ("98••• ••345") - or, hidden, only where they are from - and their
	estimate when the event shows it. Never the full number."""
	district = (lead.district or "").split(",")[0].strip()
	if cint(lead.a3s_hide_on_screen):
		return {"name": "", "district": district, "estimate": None, "hidden": 1}
	est = None
	if show_estimate and lead.a3s_estimate:
		try:
			raw = json.loads(lead.a3s_estimate)
			est = {k: raw.get(k) for k in ("kw", "price", "subsidy", "net", "monthly_saving", "payback_years",
				"monthly_bill", "monthly_units", "battery")}
		except Exception:
			est = None
	return {"name": lead.lead_name or lead.first_name or "", "district": district, "estimate": est, "hidden": 0,
		"interest": lead.get("a3s_interest") or "", "system_type": lead.get("a3s_system_type") or "",
		"mobile": mask_mobile(lead.get("mobile_no"))}


def mask_mobile(number):
	"""A mobile number the screen may show: its first two and last three digits - "98••• ••345" -
	so a visitor knows the welcome is theirs; the rest never leaves the server."""
	digits = "".join(ch for ch in (number or "") if ch.isdigit())[-10:]
	if len(digits) < 10:
		return ""
	return "{0}\u2022\u2022\u2022 \u2022\u2022{1}".format(digits[:2], digits[-3:])


def _saving(lead):
	try:
		return float((json.loads(lead.a3s_estimate) or {}).get("monthly_saving") or 0)
	except Exception:
		return 0.0
