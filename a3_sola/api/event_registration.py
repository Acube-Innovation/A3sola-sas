# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Registering at an event by QR code: the public form's endpoints and the visitor's proposal.

The QR on the stall opens /register/<key> (www/register). What the visitor sends becomes a
Lead of the event's company, owned by the event's lead owner, with the event's source and
campaign - those come from the event, never from the form. A mobile number already on a
lead of the company updates that lead rather than making a second one. The papers the
visitor uploads (KSEB bill, Aadhaar, PAN, bank proof) are private Files on the lead, typed,
so the lead's KYC list counts them (api/kyc) and the customer made from it gets them.

Defended like the signup form (api/signup): a per-IP and a per-mobile rate limit, a
honeypot, the site's captcha when it is on, every field cleaned and checked, and uploads
sniffed by their bytes rather than trusted by their name.

Each visitor who gives their bill gets their own proposal (api/event_proposal): made in the
background once they finish the form, at the lowest price of the package their bill needs.
It goes to them without WhatsApp's API: the thank-you page offers it and "Chat with us on
WhatsApp", and staff send it from the event page (api/events) in one tap.
"""

import hashlib
import hmac
import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, get_url, now_datetime, today
from frappe.utils.password import get_encryption_key

from a3_sola.api import instant_estimate
from a3_sola.api.ratelimit import client_ip, limit_by_identifier, rate_limited, user_agent, verify_captcha

EVENT = "Solar Event"
LEAD = "Lead"
STATE = "Kerala"
#: The papers a visitor may upload, as {form field: document type} (setup/custom_fields.DOCUMENT_TYPES).
DOCUMENTS = {
	"kseb_bill": "KSEB Bill",
	"aadhaar_front": "Aadhaar Front",
	"aadhaar_back": "Aadhaar Back",
	"pan": "PAN",
	"bank_proof": "Bank Proof",
}
#: What an upload may be, told by its first bytes: {kind: (extension, mime)}.
FILE_KINDS = {"pdf": (".pdf", "application/pdf"), "jpeg": (".jpg", "image/jpeg"), "png": (".png", "image/png"),
	"webp": (".webp", "image/webp")}
DEFAULT_MAX_MB = 5
REGISTER_PATH = "/register/{0}"
SCREEN_PATH = "/event-screen/{0}"
DEFAULT_WELCOME = (
	"Hello {name},\n\nThank you for visiting *{company}* at {event}.\n\n"
	"Here is your solar proposal: {proposal}\n\n{estimate}"
	"Our team will call you{call_time}. Reply here with any question."
)


# ------------------------------------------------------------------ the event behind a link
def event_by_key(key, active=True):
	"""The event a registration link names, or None: an unknown key, or a closed event."""
	key = (key or "").strip()
	if not key or len(key) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
		return None
	event = frappe.db.get_value(EVENT, {"public_key": key}, ["name", "event_name", "company", "venue", "is_active",
		"lead_owner", "lead_source", "campaign", "whatsapp_number", "ask_documents", "welcome_message",
		"screen_headline", "show_estimate_on_screen", "public_key", "display_key"], as_dict=True)
	if not event or (active and not cint(event.is_active)):
		return None
	return event


def register_url(event):
	return get_url(REGISTER_PATH.format(event.public_key))


def screen_url(event):
	return get_url(SCREEN_PATH.format(event.display_key))


def company_name(company):
	return frappe.db.get_value("Company", company, "company_name") or company


def company_logo(company):
	return frappe.db.get_value("Company", company, "company_logo") or None


def districts():
	"""The districts the form offers: Kerala's, by name."""
	return frappe.get_all("Indian District", filters={"state": STATE}, fields=["name", "district_name"],
		order_by="district_name asc")


def page_context(key):
	"""What the registration page shows for this link, or None for a closed one."""
	from a3_sola.setup.custom_fields import CALL_TIME, INTEREST, SYSTEM_TYPE

	event = event_by_key(key)
	if not event:
		return None
	settings = frappe.get_cached_doc("A3 Sola Settings")
	captcha = None
	if cint(settings.get("enable_captcha")) and settings.get("captcha_site_key"):
		captcha = {"provider": settings.get("captcha_provider") or "Cloudflare Turnstile", "site_key": settings.captcha_site_key}
	return frappe._dict(
		key=event.public_key, event_name=event.event_name, venue=event.venue or "", company=company_name(event.company),
		logo=company_logo(event.company), ask_documents=cint(event.ask_documents),
		has_chat=bool(event.whatsapp_number), districts=districts(), interests=INTEREST.split("\n"),
		system_types=SYSTEM_TYPE.split("\n"), call_times=CALL_TIME.split("\n"),
		documents=[{"field": f, "label": t} for f, t in DOCUMENTS.items()], max_mb=_max_mb(), captcha=captcha,
	)


# ------------------------------------------------------------------ registering
#: A visitor's first save (tab 1) and their finished form count as one registration when they
#: come this close together; a later finish, or one at another event, starts a new one.
SAME_VISIT_HOURS = 6


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limited("event_registration_ip", "event_registration_rate_per_ip", 30)
def start():
	"""The form's first tab: name, mobile and district. Saves the visitor's lead at once - so staff
	can call even if they stop there - and the stall screen says they have just scanned. Returns a
	ref that lets the finished form update this lead without a second captcha."""
	data = frappe._dict(frappe.form_dict)
	if _clean(data.get("website_url")):
		frappe.logger("a3_sola").info({"event": "honeypot_tripped", "form": "event_registration_start", "ip": client_ip()})
		return {"ok": True, "ref": "", "first_name": ""}
	event = event_by_key(data.get("key"))
	if not event:
		frappe.throw(_("This registration has closed."), title=_("Registration Closed"))
	verify_captcha(data.get("captcha_token"))
	visitor = _contact(data)
	limit_by_identifier("event_registration_mobile", visitor.mobile, "event_registration_per_mobile_per_day", 5)
	user = frappe.session.user
	frappe.set_user(event.lead_owner)
	try:
		lead, created = _save_scan(event, visitor)
	finally:
		frappe.set_user(user)
	return {"ok": True, "ref": visitor_ref(lead.name), "first_name": visitor.first_name, "created": created}


def _contact(data):
	"""Tab 1, cleaned and checked: name, mobile, WhatsApp, district, and whether the screen may name them."""
	full_name = " ".join(_clean(data.get("full_name"), 140).split())
	if len(full_name) < 2:
		frappe.throw(_("Enter your name."))
	mobile = _mobile(data.get("mobile_no"), _("your mobile"))
	whatsapp = _mobile(data.get("whatsapp_no"), _("WhatsApp")) if _clean(data.get("whatsapp_no"), 24) else mobile
	district = _clean(data.get("district"), 140)
	if not district or not frappe.db.exists("Indian District", {"name": district, "state": STATE}):
		frappe.throw(_("Choose your district."))
	first, _sep, rest = full_name.partition(" ")
	return frappe._dict(full_name=full_name, first_name=first, last_name=rest or None, mobile=mobile, whatsapp=whatsapp,
		district=district, hide_on_screen=1 if str(data.get("show_on_screen", "1")) == "0" else 0)


def _save_scan(event, visitor):
	"""(lead, made now) after tab 1: the lead their number is on, else a new one, stamped as
	registered at this event now (the screen's "just scanned"). Run as the event's lead owner."""
	from a3_sola.api.leads import lead_defaults
	from a3_sola.api.lead_import import NEW_LEAD

	name = find_lead(event.company, visitor.mobile)
	created = not name
	if created:
		doc = frappe.new_doc(LEAD)
		for field, value in {**lead_defaults(), **NEW_LEAD}.items():
			doc.set(field, value)
		doc.update({"first_name": visitor.first_name, "last_name": visitor.last_name, "company": event.company,
			"lead_owner": event.lead_owner, "source": event.lead_source or doc.source, "campaign_name": event.campaign,
			"mobile_no": visitor.mobile, "whatsapp_no": visitor.whatsapp})
	else:
		doc = frappe.get_doc(LEAD, name)
	fill = {"whatsapp_no": visitor.whatsapp, "district": visitor.district,
		"state": frappe.db.get_value("Indian District", visitor.district, "state")}
	for field, value in fill.items():
		if value and (created or not doc.get(field)):
			doc.set(field, value)
	doc.update({"a3s_event": event.name, "a3s_registered_on": now_datetime(), "a3s_completed_on": None,
		"a3s_hide_on_screen": visitor.hide_on_screen,
		"a3s_registered_from": "{0} | {1}".format(client_ip() or "", (user_agent() or "")[:300])})
	doc.append("outreach_log", {"contact_datetime": now_datetime(), "channel": "Walk-in",
		"outreach_step": "Step 1: First Contact", "call_status": "Not Applicable", "logged_by": event.lead_owner,
		"outcome": _("Scanned the QR code at {0}.").format(event.event_name),
		"next_action": _("Call {0}.").format(visitor.first_name)})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	if created:
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	if not doc.next_followup_date or str(doc.next_followup_date) > today():
		doc.db_set("next_followup_date", today(), update_modified=False)
	return doc, created


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit():
	"""Register a visitor at the event the link names: their lead, made or brought up to date,
	their papers, and the instant estimate to show them. Multipart: the fields, and a file per
	paper they chose to upload."""
	from a3_sola.api.ratelimit import enforce

	data = frappe._dict(frappe.form_dict)
	if _clean(data.get("website_url")):
		# The honeypot: a field no person sees. The same answer as a real registration, and nothing saved.
		frappe.logger("a3_sola").info({"event": "honeypot_tripped", "form": "event_registration", "ip": client_ip()})
		return {"ok": True, "first_name": "", "estimate": None}
	# Tab 1 (start) already passed the per-IP and per-mobile limits and the captcha for this visitor.
	# Its signed ref, for the same number, finishes that registration without counting it twice -
	# a visit is one registration however many tabs it takes - and without a second challenge (a
	# captcha token is good for one check only). Without it, this is a whole registration: all checks.
	started = lead_of_ref(data.get("ref"))
	ip_checked = False
	if not started:
		enforce("event_registration_ip", client_ip(), "event_registration_rate_per_ip", 30, 3600, detail="submit")
		ip_checked = True
	event = event_by_key(data.get("key"))
	if not event:
		frappe.throw(_("This registration has closed."), title=_("Registration Closed"))
	visitor = _visitor(data)
	if not (started and find_lead(event.company, visitor.mobile) == started):
		if not ip_checked:
			enforce("event_registration_ip", client_ip(), "event_registration_rate_per_ip", 30, 3600, detail="submit")
		verify_captcha(data.get("captcha_token"))
		limit_by_identifier("event_registration_mobile", visitor.mobile, "event_registration_per_mobile_per_day", 5)
	papers = _papers(event) if cint(event.ask_documents) else []
	est = instant_estimate.estimate(event.company, visitor.bill_amount, visitor.bill_months, visitor.interest,
		_event_packages(event.name), visitor.system_type) if visitor.bill_amount else None

	user = frappe.session.user
	frappe.set_user(event.lead_owner)
	try:
		lead, created = _save_lead(event, visitor, est)
		for field, doc_type, content, kind in papers:
			_attach(lead, field, doc_type, content, kind)
	finally:
		frappe.set_user(user)
	if any(p[1] == "KSEB Bill" for p in papers):
		frappe.enqueue("a3_sola.api.event_registration.read_bill", queue="short", lead=lead.name,
			enqueue_after_commit=True, job_id=f"event-bill::{lead.name}", deduplicate=True)

	from a3_sola.api import event_proposal

	ref = visitor_ref(lead.name)
	offers_proposal = event_proposal.has_proposal(lead)
	if offers_proposal:
		# The proposal's design estimate made now, so the figures shown are the PDF's own.
		made = event_proposal.prepare(lead.name)
		if made and est:
			est = _as_proposed(est, made["figures"])
			frappe.db.set_value(LEAD, lead.name, "a3s_estimate", json.dumps(est), update_modified=False)
		if made and (made["changed"] or not frappe.db.get_value("Solar Proposal", made["proposal"], "proposal_pdf")):
			event_proposal.queue(made["proposal"])
	return {
		"ok": True, "first_name": visitor.first_name, "created": created, "estimate": est,
		"summary": instant_estimate.summary(est), "ref": ref,
		"proposal_url": proposal_url(event, ref) if offers_proposal else None,
		"chat_url": chat_url(event, visitor.full_name) if event.whatsapp_number else None,
	}


def _as_proposed(est, figures):
	"""The instant estimate with the proposal's own size, price, subsidy and price after it - what
	its PDF prints - and the payback worked out again from that price."""
	est = dict(est, kw=figures["kw"], price=figures["price"], subsidy=figures["subsidy"], net=figures["net"])
	saving = flt(est.get("monthly_saving"))
	est["payback_years"] = round(est["net"] / (saving * 12), 1) if saving > 0 and est["net"] > 0 else None
	return est


def _clean(value, limit=140):
	from a3_sola.api.sanitise import clean_text

	return clean_text(value, limit)


def _choice(value, options, label, required=False):
	value = _clean(value, 60)
	if not value:
		if required:
			frappe.throw(_("Choose {0}.").format(label))
		return None
	if value not in options.split("\n"):
		frappe.throw(_("Choose {0} from the list.").format(label))
	return value


def _mobile(value, label):
	"""An Indian mobile number as its ten digits, or a refusal."""
	from a3_sola.api.signup import INDIAN_MOBILE

	digits = re.sub(r"[^\d+]", "", _clean(value, 24))
	if not INDIAN_MOBILE.match(digits):
		frappe.throw(_("Enter a ten-digit Indian mobile number for {0}.").format(label), title=_("Check the Number"))
	return re.sub(r"\D", "", digits)[-10:]


def _visitor(data):
	"""What the visitor sent, cleaned and checked."""
	from a3_sola.setup.custom_fields import CALL_TIME, INTEREST, SYSTEM_TYPE

	full_name = " ".join(_clean(data.get("full_name"), 140).split())
	if len(full_name) < 2:
		frappe.throw(_("Enter your name."))
	mobile = _mobile(data.get("mobile_no"), _("your mobile"))
	whatsapp = _mobile(data.get("whatsapp_no"), _("WhatsApp")) if _clean(data.get("whatsapp_no"), 24) else mobile
	district = _clean(data.get("district"), 140)
	if not district or not frappe.db.exists("Indian District", {"name": district, "state": STATE}):
		frappe.throw(_("Choose your district."))
	bill = flt(_clean(data.get("bill_amount"), 12))
	if bill < 0 or bill > 1000000:
		frappe.throw(_("Enter the bill amount in rupees."))
	if not cint(data.get("whatsapp_consent")):
		frappe.throw(_("Tick the box to agree to hear from us on WhatsApp."), title=_("Agree to WhatsApp"))
	first, _sep, rest = full_name.partition(" ")
	return frappe._dict(
		full_name=full_name, first_name=first, last_name=rest or None, mobile=mobile, whatsapp=whatsapp,
		district=district, bill_amount=bill, bill_months=1 if cint(data.get("bill_months")) == 1 else 2,
		interest=_choice(data.get("interest"), INTEREST, _("the type of property"), required=True),
		system_type=_choice(data.get("system_type"), SYSTEM_TYPE, _("the system type")),
		call_time=_choice(data.get("call_time"), CALL_TIME, _("a time to call")),
		# Shown on the stall screen unless the visitor unticks it (or an older form asks to hide).
		hide_on_screen=1 if (str(data.get("show_on_screen", "1")) == "0" or cint(data.get("hide_on_screen"))) else 0,
	)


def _event_packages(event):
	return frappe.get_all("Solar Event Package", filters={"parent": event, "parenttype": EVENT}, pluck="package")


CATEGORY_OF = {"Home": "Residential", "Shop or Office": "Commercial", "Industry": "Industrial", "Institution": "Government"}


def find_lead(company, mobile):
	"""The company's lead with this mobile or WhatsApp number (by its last ten digits), newest first."""
	rows = frappe.db.sql("""select name from `tabLead`
		where ifnull(company, '') in (%(company)s, '')
		and (right(regexp_replace(ifnull(mobile_no, ''), '[^0-9]', ''), 10) = %(mobile)s
			or right(regexp_replace(ifnull(whatsapp_no, ''), '[^0-9]', ''), 10) = %(mobile)s)
		order by (company = %(company)s) desc, creation desc limit 1""", {"company": company, "mobile": mobile})
	return rows[0][0] if rows else None


def _save_lead(event, visitor, est):
	"""(lead, made now): the visitor's lead in the event's company - the one their number is on,
	brought up to date, else a new one. Run as the event's lead owner."""
	from a3_sola.api.leads import lead_defaults
	from a3_sola.api.lead_import import NEW_LEAD

	name = find_lead(event.company, visitor.mobile)
	created = not name
	if created:
		doc = frappe.new_doc(LEAD)
		for field, value in {**lead_defaults(), **NEW_LEAD}.items():
			doc.set(field, value)
		doc.update({"first_name": visitor.first_name, "last_name": visitor.last_name, "company": event.company,
			"lead_owner": event.lead_owner, "source": event.lead_source or doc.source, "campaign_name": event.campaign,
			"mobile_no": visitor.mobile, "whatsapp_no": visitor.whatsapp})
	else:
		doc = frappe.get_doc(LEAD, name)
	# What the lead lacks, from what the visitor said; what it has stays (it may be newer).
	fill = {"whatsapp_no": visitor.whatsapp, "district": visitor.district,
		"state": frappe.db.get_value("Indian District", visitor.district, "state"),
		"consumer_category": CATEGORY_OF.get(visitor.interest), "a3s_interest": visitor.interest,
		"a3s_system_type": visitor.system_type, "a3s_call_time": visitor.call_time}
	if visitor.bill_amount:
		fill["avg_monthly_bill"] = round(visitor.bill_amount / visitor.bill_months)
	if est:
		fill.update({"approx_consumption_units": est["monthly_units"] * instant_estimate.CYCLE_MONTHS,
			"approx_capacity_kw": est["kw"]})
	for field, value in fill.items():
		if value and (created or not doc.get(field)):
			doc.set(field, value)
	# Registered when they first saved their name (tab 1), if that was this visit at this event;
	# a form finished without that first save (an older page) is registered now.
	from frappe.utils import add_to_date, get_datetime

	same_visit = doc.a3s_event == event.name and doc.a3s_registered_on and \
		get_datetime(doc.a3s_registered_on) > add_to_date(now_datetime(), hours=-SAME_VISIT_HOURS)
	doc.update({"a3s_event": event.name, "a3s_whatsapp_consent": 1, "a3s_completed_on": now_datetime(),
		"a3s_registered_on": doc.a3s_registered_on if same_visit else now_datetime(),
		"a3s_hide_on_screen": visitor.hide_on_screen,
		"a3s_registered_from": "{0} | {1}".format(client_ip() or "", (user_agent() or "")[:300])})
	if est:
		# A visit without a bill keeps the estimate the lead already has.
		doc.a3s_estimate = json.dumps(est)
	doc.append("outreach_log", {"contact_datetime": now_datetime(), "channel": "Walk-in",
		"outreach_step": "Step 1: First Contact", "call_status": "Not Applicable", "logged_by": event.lead_owner,
		"outcome": _("Registered at {0} by QR code.").format(event.event_name),
		"next_action": _("Call {0}{1}.").format(visitor.first_name,
			" ({0})".format(visitor.call_time.lower()) if visitor.call_time else "")})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	if created:
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	# The first call is due today, whatever the cadence would say.
	if not doc.next_followup_date or str(doc.next_followup_date) > today():
		doc.db_set("next_followup_date", today(), update_modified=False)
	return doc, created


# ------------------------------------------------------------------ the papers
def _max_mb():
	from a3_sola.api.settings import get_int

	return get_int("registration_max_file_mb", DEFAULT_MAX_MB) or DEFAULT_MAX_MB


def sniff(content):
	"""The kind of file these bytes are - pdf, jpeg, png, webp - or None."""
	head = content[:16]
	if head.startswith(b"%PDF-"):
		return "pdf"
	if head.startswith(b"\xff\xd8\xff"):
		return "jpeg"
	if head.startswith(b"\x89PNG\r\n\x1a\n"):
		return "png"
	if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
		return "webp"
	return None


def _papers(event):
	"""[(form field, document type, bytes, kind)] of the files sent - every one checked before
	anything is saved, so a bad file refuses the whole registration with nothing half-made."""
	files = getattr(frappe.request, "files", None) if getattr(frappe.local, "request", None) else None
	if not files:
		return []
	limit = _max_mb() * 1024 * 1024
	out = []
	for field, doc_type in DOCUMENTS.items():
		upload = files.get(field)
		if not upload or not upload.filename:
			continue
		content = upload.stream.read(limit + 1)
		if not content:
			continue
		if len(content) > limit:
			frappe.throw(_("{0} is larger than {1} MB. Take a smaller photo or upload a PDF.").format(
				_(doc_type), _max_mb()), title=_("File Too Large"))
		kind = sniff(content)
		if not kind:
			frappe.throw(_("{0} must be a photo (JPG, PNG) or a PDF.").format(_(doc_type)), title=_("File Not Accepted"))
		if kind == "pdf":
			_check_pdf(content, doc_type)
		out.append((field, doc_type, content, kind))
	return out


def _check_pdf(content, doc_type):
	"""A PDF Frappe will store: one it can open, with no script in it (File refuses those, and a
	damaged one breaks its check) - asked here so the visitor hears it before anything is saved."""
	from frappe.utils.pdf import pdf_contains_js

	try:
		scripted = pdf_contains_js(content)
	except Exception:
		frappe.throw(_("{0} could not be opened. Take a photo of it instead.").format(_(doc_type)), title=_("File Not Accepted"))
	if scripted:
		frappe.throw(_("{0} cannot be accepted as it is. Take a photo of it instead.").format(_(doc_type)),
			title=_("File Not Accepted"))


def _attach(lead, field, doc_type, content, kind):
	"""The paper as a private File on the lead, typed - KYC counts it."""
	ext = FILE_KINDS[kind][0]
	stamp = now_datetime().strftime("%Y%m%d%H%M%S")
	return frappe.get_doc({"doctype": "File", "file_name": f"{field}-{lead.name}-{stamp}{ext}", "content": content,
		"is_private": 1, "attached_to_doctype": LEAD, "attached_to_name": lead.name,
		"a3s_document_type": doc_type}).insert(ignore_permissions=True)


def read_bill(lead):
	"""Background: the uploaded KSEB bill read (api/kseb_bill), and what it says put on the lead
	where the lead says nothing yet - the consumer number, the section, the units."""
	from a3_sola.api import kseb_bill

	f = frappe.get_all("File", filters={"attached_to_doctype": LEAD, "attached_to_name": lead,
		"a3s_document_type": "KSEB Bill"}, fields=["name"], order_by="creation desc", limit=1)
	if not f:
		return
	file_doc = frappe.get_doc("File", f[0].name)
	try:
		read = kseb_bill.read_content(file_doc.get_content(), file_doc.file_name, LEAD)
	except Exception:
		# A photo the reader cannot make out is ordinary; staff read it by eye.
		frappe.log_error(frappe.get_traceback(), f"a3_sola: event registration bill of {lead}")
		return
	doc = frappe.get_doc(LEAD, lead)
	meta = frappe.get_meta(LEAD)
	changed = False
	for field, value in (read.get("fields") or {}).items():
		if value and meta.has_field(field) and not doc.get(field) and field not in ("lead_name", "first_name", "last_name"):
			doc.set(field, value)
			changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)


# ------------------------------------------------------------------ the visitor's link
def visitor_ref(lead):
	"""A key naming this visitor's lead, for their proposal link: an HMAC, so it cannot be made
	for another lead."""
	secret = (get_encryption_key() + ":event-visitor").encode()
	return lead + "." + hmac.new(secret, lead.encode(), hashlib.sha256).hexdigest()[:20]


def lead_of_ref(ref):
	lead, _sep, mac = (ref or "").rpartition(".")
	if not lead or not mac or not frappe.db.exists(LEAD, lead):
		return None
	return lead if hmac.compare_digest(visitor_ref(lead), ref) else None


def chat_url(event, full_name):
	"""Our WhatsApp, opened from the visitor's phone with their hello typed in."""
	from a3_sola.api.outreach import whatsapp_link

	text = _("Hi, I am {0}. I registered at {1}. Please send me my solar proposal.").format(full_name, event.event_name)
	return whatsapp_link(event.whatsapp_number, text)


def proposal_url(event, ref):
	return get_url("/api/method/a3_sola.api.event_registration.proposal?key={0}&ref={1}".format(event.public_key, ref))


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limited("event_brochure_ip", "event_brochure_rate_per_ip", 120)
def proposal(key, ref=None):
	"""The visitor's own proposal, from the thank-you page or the WhatsApp message: their
	signed `ref` opens it, and only theirs. Printed as it stands (api/event_proposal.pdf_for);
	opening it notes on their lead that they have it (and the stall screen says so)."""
	from a3_sola.api import event_proposal

	event = event_by_key(key, active=False)
	lead = lead_of_ref(ref) if ref else None
	if not event or not lead or frappe.db.get_value(LEAD, lead, "a3s_event") != event.name:
		frappe.throw(_("This proposal link is not valid."), frappe.DoesNotExistError)
	found = event_proposal.pdf_for(lead)
	if not found:
		# A page for the phone, not an error: their own offer comes from our team.
		frappe.respond_as_web_page(_("Your proposal is on its way"),
			_("Our team is preparing your solar proposal and will send it to you on WhatsApp. "
			"Reply there with any question."), indicator_color="orange", http_status_code=200)
		return
	note_brochure(lead, "Downloaded")
	frappe.db.commit()  # a GET request is not committed for us
	file_name, content = found
	frappe.local.response.filename = file_name
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"
	frappe.local.response.display_content_as = "inline"


def note_brochure(lead, via):
	"""The proposal reached the visitor (the field names are the brochure's, which it replaced): the first time, stamped on the lead for the event page
	and the stall screen."""
	if frappe.db.get_value(LEAD, lead, "a3s_brochure_sent_on"):
		return
	frappe.db.set_value(LEAD, lead, {"a3s_brochure_sent_on": now_datetime(), "a3s_brochure_sent_via": via},
		update_modified=False)


# ------------------------------------------------------------------ the welcome message
def welcome_text(event, lead):
	"""The WhatsApp welcome for a visitor, from the event's message (DEFAULT_WELCOME when it has
	none): their name, the event, the company, their proposal link and their estimate filled in.
	A line whose link is not there (no proposal for a battery system or a business) is left out;
	so is a {brochure} line of an older message - events send the proposal now."""
	from a3_sola.api import event_proposal

	ref = visitor_ref(lead.name)
	est = json.loads(lead.get("a3s_estimate") or "null") if lead.get("a3s_estimate") else None
	line = instant_estimate.summary(est)
	values = {
		"name": (lead.get("first_name") or lead.get("lead_name") or "").strip(),
		"event": event.event_name, "company": company_name(event.company),
		"brochure": "",
		"proposal": proposal_url(event, ref) if event_proposal.has_proposal(lead) else "",
		"estimate": (_("Your indicative estimate: {0}. Our engineer will confirm it after a site visit.").format(line)
			+ "\n\n") if line else "",
		"call_time": (" in the " + lead.a3s_call_time.lower()) if lead.get("a3s_call_time") in ("Morning", "Afternoon", "Evening") else " soon",
	}
	template = (event.get("welcome_message") or "").strip() or DEFAULT_WELCOME

	def fill(match):
		return str(values.get(match.group(1), match.group(0)))

	lines = [line for line in template.split("\n")
		if not any("{" + link + "}" in line and not values[link] for link in ("proposal", "brochure"))]
	text = re.sub(r"\{(\w+)\}", fill, "\n".join(lines))
	return re.sub(r"\n{3,}", "\n\n", text).strip()
