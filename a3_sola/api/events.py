# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's Events pages: an event's set-up, its QR code and poster, the people who
registered at it, sending each their proposal on WhatsApp, and the funnel from registration
to order (www/a3solaportal/events).

Staff only - a dealer or contractor is refused. Every read goes through the user's own
permissions on Solar Event and Lead, so a company sees only its own events and leads.
"""

import io
import json

import frappe
from frappe import _
from frappe.utils import cint, format_datetime, getdate, today

from a3_sola.api import event_registration as reg

EVENT = "Solar Event"
LEAD = "Lead"
#: What the event form may set.
EDITABLE = ("event_name", "venue", "company", "start_date", "end_date", "is_active", "lead_owner", "lead_source",
	"whatsapp_number", "ask_documents", "welcome_message", "screen_headline", "show_estimate_on_screen")
CHECKS = ("is_active", "ask_documents", "show_estimate_on_screen")
LOGO_MAX_MB = 5


def require_staff():
	from a3_sola.api.partner_scope import is_partner

	if frappe.session.user == "Guest" or is_partner():
		frappe.throw(_("Events are for the company's staff."), frappe.PermissionError)


def _event(name, ptype="read"):
	require_staff()
	if not name or not frappe.db.exists(EVENT, name):
		frappe.throw(_("No such event."), frappe.DoesNotExistError)
	doc = frappe.get_doc(EVENT, name)
	doc.check_permission(ptype)
	return doc


# ------------------------------------------------------------------ the list
def event_rows():
	"""Every event the user may see, newest first, with how many registered."""
	require_staff()
	rows = frappe.get_list(EVENT, fields=["name", "event_name", "venue", "company", "start_date", "end_date",
		"is_active", "lead_owner"], order_by="start_date desc, creation desc", limit_page_length=500)
	counts = dict(frappe.get_all(LEAD, filters={"a3s_event": ["in", [r.name for r in rows] or [""]]},
		fields=["a3s_event", "count(name) as n"], group_by="a3s_event", as_list=True)) if rows else {}
	owners = _names({r.lead_owner for r in rows})
	for r in rows:
		r.registrations = counts.get(r.name, 0)
		r.owner_name = owners.get(r.lead_owner, r.lead_owner)
		r.dates = _dates(r.start_date, r.end_date)
		r.state = "Open" if cint(r.is_active) else "Closed"
	return rows


def _names(users):
	users = [u for u in users if u]
	return dict(frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"], as_list=True)) if users else {}


def _dates(start, end):
	if not start:
		return ""
	start = getdate(start)
	if not end or getdate(end) == start:
		return start.strftime("%-d %b %Y")
	end = getdate(end)
	if start.year == end.year and start.month == end.month:
		return "{0}–{1}".format(start.strftime("%-d"), end.strftime("%-d %b %Y"))
	return "{0} – {1}".format(start.strftime("%-d %b"), end.strftime("%-d %b %Y"))


# ------------------------------------------------------------------ the form
@frappe.whitelist()
def form_options():
	"""The choices of the event form: staff to own the leads, lead sources, companies, and the
	packages the estimate may offer."""
	require_staff()
	from a3_sola.api import partner_scope
	from a3_sola.api.permissions import get_permitted_companies

	staff = frappe.get_all("User", filters={"enabled": 1, "user_type": "System User", "name": ["not in", ["Administrator", "Guest"]]},
		fields=["name", "full_name"], order_by="full_name asc")
	staff = [u for u in staff if not partner_scope.partner_kinds(u.name)]
	companies = get_permitted_companies(frappe.session.user) or frappe.get_all("Company", pluck="name")
	packages = frappe.get_list("Solar Package", filters={"is_active": 1, "company": ["in", companies or [""]]},
		fields=["name", "package_name", "capacity_kw", "connection_type", "company"], order_by="capacity_kw asc, package_name asc",
		limit_page_length=500)
	from a3_sola.api.memberships import active_company

	default = active_company() or frappe.defaults.get_user_default("Company")
	return {"staff": [{"value": u.name, "label": u.full_name or u.name} for u in staff],
		"sources": frappe.get_all("Lead Source", pluck="name", order_by="name asc"),
		"companies": companies, "default_company": default if default in companies else (companies[0] if companies else None),
		"packages": packages, "default_welcome": reg.DEFAULT_WELCOME, "me": frappe.session.user}


def form_values(doc):
	values = {f: doc.get(f) for f in EDITABLE}
	values["name"] = doc.name
	values["packages"] = [r.package for r in doc.get("estimate_packages") or []]
	values["event_logo_name"] = (doc.event_logo or "").rsplit("/", 1)[-1]
	for f in ("start_date", "end_date"):
		values[f] = str(values[f]) if values[f] else ""
	return values


@frappe.whitelist(methods=["POST"])
def save_event(data, name=None):
	"""A new event, or changes to one: what the form may set, and the packages."""
	require_staff()
	data = frappe._dict(json.loads(data) if isinstance(data, str) else (data or {}))
	if name:
		doc = _event(name, "write")
	else:
		if not frappe.has_permission(EVENT, "create"):
			frappe.throw(_("You may not create events."), frappe.PermissionError)
		doc = frappe.new_doc(EVENT)
	for field in EDITABLE:
		if field in data:
			value = data.get(field)
			if field in CHECKS:
				value = 1 if cint(value) else 0
			elif isinstance(value, str):
				value = value.strip() or None
			doc.set(field, value)
	if "packages" in data:
		doc.set("estimate_packages", [{"package": p} for p in dict.fromkeys(data.get("packages") or []) if p])
	doc.save() if name else doc.insert()
	return {"name": doc.name, "route": "/a3solaportal/events/" + doc.name}


@frappe.whitelist(methods=["POST"])
def upload_event_logo(name):
	"""The exhibition's logo for the stall screen's top bar: an image sent with the form, kept public
	because the screen is opened without a login."""
	doc = _event(name, "write")
	upload = frappe.request.files.get("file") if getattr(frappe.request, "files", None) else None
	if not upload or not upload.filename:
		frappe.throw(_("Choose the logo image."))
	limit = LOGO_MAX_MB * 1024 * 1024
	content = upload.stream.read(limit + 1)
	if len(content) > limit:
		frappe.throw(_("The logo is larger than {0} MB. Choose a smaller image.").format(LOGO_MAX_MB))
	kind = reg.sniff(content)
	if kind not in ("png", "jpeg", "webp"):
		frappe.throw(_("The logo must be a PNG, JPG or WebP image."))
	for old in frappe.get_all("File", filters={"attached_to_doctype": EVENT, "attached_to_name": doc.name,
			"attached_to_field": "event_logo"}, pluck="name"):
		frappe.delete_doc("File", old, ignore_permissions=True)
	stem = "".join(c for c in upload.filename.rsplit(".", 1)[0] if c.isalnum() or c in " _-").strip() or "event-logo"
	safe = "{0}.{1}".format(stem, "jpg" if kind == "jpeg" else kind)
	f = frappe.get_doc({"doctype": "File", "file_name": safe, "content": content, "is_private": 0,
		"attached_to_doctype": EVENT, "attached_to_name": doc.name, "attached_to_field": "event_logo"}).insert(ignore_permissions=True)
	doc.db_set("event_logo", f.file_url)
	return {"event_logo_name": safe}

# ------------------------------------------------------------------ one event
def view_context(name):
	"""Everything the event page shows."""
	doc = _event(name)
	event = reg.event_by_key(doc.public_key, active=False)
	return frappe._dict(
		doc=doc, form=form_values(doc), register_url=reg.register_url(event), screen_url=reg.screen_url(event),
		qr_svg=qr_svg(reg.register_url(event)), owner_name=_names({doc.lead_owner}).get(doc.lead_owner, doc.lead_owner),
		dates=_dates(doc.start_date, doc.end_date), can_write=bool(doc.has_permission("write")),
		data=registrations(name),
	)


@frappe.whitelist()
def registrations(event):
	"""The people who registered at the event, newest first, with the funnel - what the event
	page shows, and polls to stay live."""
	doc = _event(event)
	leads = frappe.get_list(LEAD, filters={"a3s_event": doc.name}, fields=["name", "lead_name", "first_name", "mobile_no",
		"whatsapp_no", "district", "avg_monthly_bill", "approx_capacity_kw", "a3s_interest", "a3s_call_time",
		"a3s_registered_on", "a3s_brochure_sent_on", "a3s_brochure_sent_via", "a3s_hide_on_screen", "a3s_estimate",
		"solar_lead_status", "status", "solar_consumer", "site_survey", "solar_proposal", "lead_owner"],
		order_by="a3s_registered_on desc", limit_page_length=2000)
	names = [l.name for l in leads]
	papers = dict(frappe.get_all("File", filters={"attached_to_doctype": LEAD, "attached_to_name": ["in", names or [""]],
		"a3s_document_type": ["in", list(reg.DOCUMENTS.values())]}, fields=["attached_to_name", "count(name) as n"],
		group_by="attached_to_name", as_list=True)) if names else {}
	event = reg.event_by_key(doc.public_key, active=False)
	from a3_sola.api.outreach import whatsapp_link

	proposals = dict(frappe.get_all("Solar Proposal", filters={"lead": ["in", names or [""]], "docstatus": ["<", 2]},
		fields=["lead", "name"], as_list=True)) if names else {}
	rows = []
	for l in leads:
		number = l.whatsapp_no or l.mobile_no
		rows.append({
			"name": l.name, "full_name": l.lead_name or l.first_name or l.name, "mobile": l.mobile_no or "",
			"district": (l.district or "").split(",")[0], "bill": l.avg_monthly_bill or 0,
			"kw": l.approx_capacity_kw or 0, "interest": l.a3s_interest or "", "call_time": l.a3s_call_time or "",
			"registered": format_datetime(l.a3s_registered_on, "d MMM, h:mm a") if l.a3s_registered_on else "",
			"registered_on": str(l.a3s_registered_on or ""),
			"sent": format_datetime(l.a3s_brochure_sent_on, "d MMM, h:mm a") if l.a3s_brochure_sent_on else "",
			"sent_via": l.a3s_brochure_sent_via or "", "hidden": cint(l.a3s_hide_on_screen),
			"papers": papers.get(l.name, 0), "status": l.solar_lead_status or l.status or "",
			"proposal": proposals.get(l.name) or "",
			# The welcome, one tap from the visitor's chat: their proposal link and estimate in it.
			"whatsapp": whatsapp_link(number, reg.welcome_text(event, l)) if number else "",
		})
	return {"rows": rows, "funnel": funnel(doc.name, leads), "today": sum(1 for l in leads
		if l.a3s_registered_on and str(l.a3s_registered_on)[:10] == today())}


def funnel(event, leads):
	"""Registered -> Proposal -> Proposal sent -> Contacted -> Survey -> Accepted -> Quotation ->
	Order, each the number of this event's leads that got that far."""
	names = [l.name for l in leads]
	if not names:
		return [{"label": label, "count": 0} for label in FUNNEL]
	contacted = set(frappe.get_all("Outreach Log", filters={"parent": ["in", names], "parenttype": LEAD,
		"channel": ["!=", "Walk-in"]}, pluck="parent"))
	contacted |= {l.name for l in leads if l.solar_lead_status and l.solar_lead_status not in ("New",)}
	consumers = [l.solar_consumer for l in leads if l.solar_consumer]
	proposals = [l.solar_proposal for l in leads if l.solar_proposal]
	accepted = set(frappe.get_all("Solar Proposal", filters={"name": ["in", proposals or [""]], "status": "Accepted"},
		pluck="name")) if proposals else set()
	quoted = set(frappe.get_all("Quotation", filters={"solar_consumer": ["in", consumers or [""]], "docstatus": ["<", 2]},
		pluck="solar_consumer")) if consumers else set()
	ordered = set(frappe.get_all("Sales Order", filters={"solar_consumer": ["in", consumers or [""]], "docstatus": 1},
		pluck="solar_consumer")) if consumers and frappe.get_meta("Sales Order").has_field("solar_consumer") else set()
	counts = {
		"Registered": len(leads),
		"Proposal sent": sum(1 for l in leads if l.a3s_brochure_sent_on),
		"Contacted": len(contacted),
		"Survey": sum(1 for l in leads if l.site_survey),
		"Proposal": len(proposals),
		"Accepted": len(accepted),
		"Quotation": len(quoted),
		"Order": len(ordered),
	}
	return [{"label": label, "count": counts[label]} for label in FUNNEL]


FUNNEL = ("Registered", "Proposal", "Proposal sent", "Contacted", "Survey", "Accepted", "Quotation", "Order")


# ------------------------------------------------------------------ the proposal on WhatsApp
@frappe.whitelist()
def proposal_message(lead):
	"""The WhatsApp welcome for one visitor and the link that opens it to them - the text is the
	event's, their proposal link and estimate filled in."""
	require_staff()
	doc = frappe.get_doc(LEAD, lead)
	doc.check_permission("read")
	if not doc.a3s_event:
		frappe.throw(_("{0} did not register at an event.").format(doc.lead_name))
	event = reg.event_by_key(frappe.db.get_value(EVENT, doc.a3s_event, "public_key"), active=False)
	from a3_sola.api.outreach import whatsapp_link

	text = reg.welcome_text(event, doc)
	return {"text": text, "whatsapp": whatsapp_link(doc.whatsapp_no or doc.mobile_no, text)}


@frappe.whitelist(methods=["POST"])
def mark_sent(lead):
	"""Staff sent the visitor their proposal on WhatsApp: logged on the lead, and the stall
	screen shows it."""
	require_staff()
	from a3_sola.api.outreach import log_outreach

	doc = frappe.get_doc(LEAD, lead)
	doc.check_permission("write")
	log_outreach(lead, "WhatsApp", outreach_step="Step 1: First Contact", call_status="Not Applicable",
		outcome=_("Proposal sent on WhatsApp."))
	reg.note_brochure(lead, "WhatsApp")
	return {"sent": format_datetime(frappe.db.get_value(LEAD, lead, "a3s_brochure_sent_on"), "d MMM, h:mm a")}


@frappe.whitelist(methods=["POST"])
def set_hidden(lead, hidden):
	"""Keep a visitor's name off the stall screen - or show it again."""
	require_staff()
	doc = frappe.get_doc(LEAD, lead)
	doc.check_permission("write")
	frappe.db.set_value(LEAD, lead, "a3s_hide_on_screen", 1 if cint(hidden) else 0, update_modified=False)
	return {"hidden": 1 if cint(hidden) else 0}


# ------------------------------------------------------------------ the QR code
def _qr(url):
	import pyqrcode

	return pyqrcode.create(url, error="M")


def qr_svg(url, color="#1d2433"):
	"""The QR code as inline SVG, scaling to its box."""
	buf = io.BytesIO()
	_qr(url).svg(buf, scale=8, module_color=color, background="#ffffff", quiet_zone=2, xmldecl=False, svgns=True,
		omithw=True, title=None, svgclass="a3s-qr", lineclass="a3s-qr__line")
	return buf.getvalue().decode()


@frappe.whitelist()
def qr_pdf(event):
	"""The event's QR code as an A4 PDF, to print or send to a printer: the code large in the
	middle, the company's and the exhibition's logos, what scanning gives, and the link to type."""
	import base64

	from frappe.utils import escape_html
	from frappe.utils.pdf import get_pdf

	doc = _event(event)
	url = reg.register_url(reg.event_by_key(doc.public_key, active=False))
	buf = io.BytesIO()
	_qr(url).png(buf, scale=20, quiet_zone=2)
	qr = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
	company = reg.company_name(doc.company)
	logo, event_logo = _pdf_image(reg.company_logo(doc.company)), _pdf_image(doc.event_logo)
	where = " · ".join(x for x in (_dates(doc.start_date, doc.end_date), (doc.venue or "").strip()) if x)
	e = escape_html

	def logo_cell(src, align):
		return '<td style="width:50%;text-align:{0};vertical-align:middle">{1}</td>'.format(align,
			'<img src="{0}" style="max-height:20mm;max-width:60mm">'.format(src) if src else "")

	html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
		body {{ margin: 0; font-family: "Plus Jakarta Sans", "DejaVu Sans", Arial, sans-serif; color: #1d2433; text-align: center; }}
		.page {{ padding: 12mm 16mm 0; }}
		.event {{ margin: 6mm 0 0; font-size: 19pt; font-weight: 800; }}
		.where {{ margin: 2mm 0 0; font-size: 11.5pt; color: #6b7383; }}
		.title {{ margin: 6mm 0 0; font-size: 34pt; font-weight: 800; color: #e07f0c; line-height: 1; }}
		.sub {{ margin: 3mm 0 0; font-size: 15pt; color: #2a3342; }}
		.qr {{ display: inline-block; margin-top: 6mm; padding: 4mm; border: 2mm solid #f7941e; border-radius: 8mm; }}
		.qr img {{ width: 112mm; height: 112mm; display: block; }}
		.point {{ margin: 5mm 0 0; font-size: 16pt; font-weight: 800; color: #e07f0c; }}
		.link {{ margin: 2mm 0 0; font-size: 10pt; color: #6b7383; }}
		.foot {{ margin: 6mm 0 0; font-size: 11pt; color: #6b7383; }}
	</style></head><body><div class="page">
		<table style="width:100%;border-collapse:collapse"><tr>{logo_cell(logo, "left")}{logo_cell(event_logo, "right")}</tr></table>
		<p class="event">{e(doc.event_name)}</p>
		{f'<p class="where">{e(where)}</p>' if where else ""}
		<p class="title">Scan to register</p>
		<p class="sub">Get your free solar estimate on WhatsApp</p>
		<div class="qr"><img src="{qr}"></div>
		<p class="point">Point your phone camera at the code</p>
		<p class="link">or open {e(url)}</p>
		<p class="foot">{e(company)}{(" · WhatsApp " + e(doc.whatsapp_number)) if doc.whatsapp_number else ""}</p>
	</div></body></html>"""
	frappe.local.response.filename = "QR - {0}.pdf".format(doc.event_name)
	frappe.local.response.filecontent = get_pdf(html, {"page-size": "A4", "margin-top": "0mm", "margin-bottom": "0mm",
		"margin-left": "0mm", "margin-right": "0mm"})
	frappe.local.response.type = "download"


def _pdf_image(url):
	"""An image for a PDF as a data URI: an uploaded file, or one of the app's own (/assets/...,
	as a company logo can be). "" when there is none."""
	import base64
	import mimetypes
	import os

	from a3_sola.api.documents import image_src

	if not url:
		return ""
	if url.startswith("/assets/"):
		# Kept inside sites/assets (no "..") - checked before links are followed, as assets/<app> is one.
		root = os.path.normpath(os.path.join(frappe.local.sites_path, "assets"))
		path = os.path.normpath(os.path.join(frappe.local.sites_path, url.split("?")[0].lstrip("/")))
		if not path.startswith(root + os.sep) or not os.path.isfile(path):
			return ""
		with open(path, "rb") as f:
			data = f.read()
		return "data:{0};base64,{1}".format(mimetypes.guess_type(path)[0] or "image/png", base64.b64encode(data).decode())
	return image_src(url)


def poster_context(name):
	doc = _event(name)
	event = reg.event_by_key(doc.public_key, active=False)
	return frappe._dict(doc=doc, qr_svg=qr_svg(reg.register_url(event)), register_url=reg.register_url(event),
		company=reg.company_name(doc.company), logo=reg.company_logo(doc.company), dates=_dates(doc.start_date, doc.end_date),
		whatsapp=doc.whatsapp_number or "")

