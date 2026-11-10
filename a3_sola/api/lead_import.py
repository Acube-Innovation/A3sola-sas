# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Leads from a Google Sheet: new ones added, existing ones updated.

The sheet is read as CSV through its link - shared "Anyone with the link can view" - its
first row naming the columns, by the field's label, its name or a common alias ("Mobile",
"Email", "Notes"). Each row goes through the lead form's own rules: only the fields the edit
form offers are set (`leads.edit_fields`), a Select takes one of its options, a Link one of
the choices the form offers this person (so "Social Media" finds the company's own source,
"Thrissur" its district), and the lead is inserted or saved with the person's permissions.

Two steps, so nothing is saved before the person has seen what will happen:

- `preview` reads the sheet and works out, saving nothing, what each row will do - add,
  update, no change, or skip and why - and keeps the rows to import for an hour under a token;
- `run` imports them a batch at a time, each row on its own (one that fails is rolled back
  and said, the rest go in), so a long sheet shows its progress and no request runs long.

Adding skips a row whose mobile number or email is already a lead's, so a sheet imported
twice adds nobody twice. Updating finds each lead by its Lead ID column, else its mobile
number, else its email; a blank cell leaves the lead's value as it is.

A campaign chosen for the import - one there is, or a new one, made when the import runs -
goes on every lead added or updated, unless its row names a campaign of its own.
"""

import csv
import html
import io
import json
import re

import frappe
import requests
from frappe import _
from frappe.utils import cint, flt, getdate

from a3_sola.api.leads import LEAD_STATUSES, _set_full_name, edit_fields, lead_defaults, lead_route, load_lead

MODES = ("add", "update")
MAX_ROWS = 1000
BATCH = 25
TTL = 3600
CACHE = "a3s_lead_import"
SAVEPOINT = "a3s_lead_import"

#: Columns that name the lead to update.
# Not a bare "id": in a Meta (Facebook / Instagram) lead export that is Meta's own lead number.
ID_HEADERS = {"leadid", "leadno", "leadnumber", "leadcode"}
#: Other names people give the columns, normalised (`_norm`), to the field they mean.
ALIASES = {
	"name": "lead_name", "fullname": "lead_name", "customername": "lead_name", "leadname": "lead_name",
	"company": "company_name", "organisation": "company_name", "organization": "company_name",
	"email": "email_id", "emailaddress": "email_id", "mail": "email_id",
	"mobile": "mobile_no", "mobilenumber": "mobile_no", "mobileno": "mobile_no", "contactnumber": "mobile_no",
	"contactno": "mobile_no", "phonenumber": "mobile_no", "cell": "mobile_no",
	"whatsapp": "whatsapp_no", "whatsappnumber": "whatsapp_no",
	"leadsource": "source", "leadstatus": "status", "owner": "lead_owner", "assignedto": "lead_owner",
	"section": "discom_section", "electricalsection": "discom_section", "kseb": "discom",
	"consumerno": "consumer_number", "consumernumber": "consumer_number",
	"category": "consumer_category", "phase": "connection_type", "roof": "roof_type",
	"units": "approx_consumption_units", "consumption": "approx_consumption_units", "monthlyunits": "approx_consumption_units",
	"bill": "avg_monthly_bill", "monthlybill": "avg_monthly_bill", "billamount": "avg_monthly_bill",
	"capacity": "approx_capacity_kw", "kw": "approx_capacity_kw", "capacitykw": "approx_capacity_kw",
	"loan": "loan_required", "loanneeded": "loan_required", "subsidy": "subsidy_scheme", "scheme": "subsidy_scheme",
	"notes": "outreach_notes", "remarks": "outreach_notes", "comments": "outreach_notes",
	"followupdate": "next_followup_date", "nextfollowup": "next_followup_date", "followup": "next_followup_date",
	"place": "city", "town": "city", "village": "city",
}
PHONE_FIELDS = ("mobile_no", "whatsapp_no", "phone")
#: Stands for a campaign the import makes when it runs - nothing is made by checking the sheet.
NEW_CAMPAIGN = "__new_campaign__"
#: Leads from a sheet are new: not called or messaged yet, whatever the lead form starts a lead
#: typed in after a conversation on. What the sheet says still comes first.
NEW_LEAD = {"status": "Lead", "solar_lead_status": "New", "call_status": None, "last_message_date": None}
#: What a sheet may call a new lead's status - ERPNext's first status is "Lead"; a Meta lead
#: export says CREATED.
NEW_WORDS = {"new", "newlead", "fresh", "created"}


def _norm(text):
	return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _phone(raw):
	"""A phone number as the leads keep it: a Meta export's "p:+919847012345", a number column's
	9847012345.0 or "+91 98470 12345" as 9847012345; anything else as written."""
	text = re.sub(r"^p:", "", raw.strip(), flags=re.I)
	if re.fullmatch(r"\d+\.0", text):
		text = text[:-2]
	digits = re.sub(r"\D", "", text)
	if re.fullmatch(r"(\+?91|0)?[\s-]*[6-9][\d\s-]{9,}", text) and len(digits) in (10, 11, 12):
		return digits[-10:]
	return text


def _digits(phone):
	"""A phone number by its last ten digits - +91 98470 12345 and 9847012345 are one number."""
	return re.sub(r"\D", "", str(phone or ""))[-10:]


# ------------------------------------------------------------------ reading the sheet
def export_url(url):
	"""The CSV export of the sheet tab the link points at (its gid, else the first)."""
	from frappe.utils.csvutils import validate_google_sheets_url

	url = (url or "").strip()
	validate_google_sheets_url(url)
	gid = re.search(r"[#&?]gid=(\d+)", url)
	gid = f"&gid={gid.group(1)}" if gid else ""
	published = re.search(r"/spreadsheets/d/e/([\w-]+)", url)
	if published:
		return f"https://docs.google.com/spreadsheets/d/e/{published.group(1)}/pub?output=csv{gid}"
	sheet = re.search(r"/spreadsheets/d/([\w-]+)", url)
	if not sheet:
		frappe.throw(_("That link does not name a sheet. Copy it from the browser's address bar."), title=_("Not a sheet link"))
	return f"https://docs.google.com/spreadsheets/d/{sheet.group(1)}/export?format=csv{gid}"


def fetch(url):
	"""The sheet's text, as CSV."""
	try:
		response = requests.get(export_url(url), timeout=25)
	except requests.RequestException:
		frappe.throw(_("Google Sheets did not answer. Check the link and try again."), title=_("Sheet not read"))
	text = response.content.decode("utf-8-sig", errors="replace") if response.ok else ""
	if not response.ok or "text/html" in response.headers.get("Content-Type", "") or text.lstrip()[:15].lower().startswith("<!doctype"):
		frappe.throw(_("The sheet could not be opened. In Google Sheets choose Share, set General access to "
			"\"Anyone with the link\" as Viewer, then copy the link again."), title=_("Sheet not shared"))
	return text


def parse(text):
	"""(headers, [(sheet row number, cells)]) - the first non-empty row names the columns; empty
	rows are left out."""
	rows = [(n, [c.strip() for c in r]) for n, r in enumerate(csv.reader(io.StringIO(text)), start=1)]
	rows = [(n, r) for n, r in rows if any(r)]
	if not rows:
		frappe.throw(_("The sheet is empty."), title=_("Nothing to import"))
	(_n, headers), body = rows[0], rows[1:]
	return headers, body


# ------------------------------------------------------------------ columns and values
def field_specs():
	"""{fieldname: spec} of the fields the lead edit form offers this person - the only ones set."""
	return {f["fieldname"]: f for section in edit_fields(frappe.new_doc("Lead")) for f in section["fields"]}


def columns(headers, specs):
	"""Each column's field ("id" for the lead's ID, None when it means nothing here), and the
	columns left out."""
	names = {}
	for fieldname, spec in specs.items():
		names.setdefault(_norm(spec["label"]), fieldname)
		names.setdefault(_norm(fieldname), fieldname)
	for alias, fieldname in ALIASES.items():
		if fieldname in specs:
			names.setdefault(alias, fieldname)
	out, seen, ignored = [], set(), []
	for header in headers:
		key = _norm(header)
		field = "id" if key in ID_HEADERS else names.get(key)
		if not field or field in seen:
			out.append(None)
			if header:
				ignored.append(header)
			continue
		seen.add(field)
		out.append(field)
	return out, ignored


def _option(spec, raw):
	options = [o for o in spec.get("options") or [] if o]
	hit = [o for o in options if o.lower() == raw.lower()] or [o for o in options if _norm(o) == _norm(raw)]
	hit = hit or [o for o in options if _norm(o).startswith(_norm(raw))]
	if len(hit) == 1:
		return hit[0]
	frappe.throw(_("{0}: \"{1}\" is not one of {2}.").format(spec["label"], raw, ", ".join(options[:8])))


def _keys(choice):
	"""What a choice may be called in a sheet: its name, its label, the label without the
	section code or district after it, the name without the company after it."""
	value, label = str(choice["value"]), str(choice.get("label") or choice["value"])
	keys = {value, label, label.split(" – ")[0], label.split(" (")[0], value.rsplit(" - ", 1)[0]}
	code = re.search(r"– (\d+)", label)
	if code:
		keys.add(code.group(1))
	return {_norm(k) for k in keys if k}


def _link(spec, raw, row):
	choices = spec.get("choices") or []
	if any(str(c["value"]) == raw for c in choices):
		return raw
	hit = {c["value"] for c in choices if _norm(raw) in _keys(c)}
	if len(hit) == 1:
		return hit.pop()
	if len(hit) > 1:
		frappe.throw(_("{0}: \"{1}\" could be {2}. Write it as it is in the lead form.").format(
			spec["label"], raw, ", ".join(sorted(str(h) for h in hit)[:3])))
	doctype = spec["link_doctype"]
	# A list that follows another field (the districts of the chosen state) does not hold them all.
	if doctype == "Indian District" and row.get("state") and frappe.db.exists(doctype, f"{raw}, {row['state']}"):
		return f"{raw}, {row['state']}"
	# Looked up as the person may see the records - a master they may not list (the districts),
	# as it stands - by name, else by its title.
	title = frappe.get_meta(doctype).title_field
	for filters in [{"name": raw}] + ([{title: raw}] if title else []):
		try:
			found = frappe.get_list(doctype, filters=filters, pluck="name", limit=2)
		except frappe.PermissionError:
			frappe.clear_messages()
			found = frappe.get_all(doctype, filters=filters, pluck="name", limit=2)
		if len(found) == 1:
			return found[0]
	frappe.throw(_("{0}: \"{1}\" was not found.").format(spec["label"], raw))


def _date(spec, raw):
	if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
		return str(getdate(raw[:10]))
	from dateutil import parser

	dayfirst = not (frappe.db.get_default("date_format") or "dd-mm-yyyy").lower().startswith("mm")
	try:
		return str(parser.parse(raw, dayfirst=dayfirst).date())
	except (ValueError, OverflowError):
		frappe.throw(_("{0}: \"{1}\" is not a date.").format(spec["label"], raw))


def _number(spec, raw):
	text = re.sub(r"[₹,\s]|Rs\.?|INR", "", raw, flags=re.I)
	try:
		return cint(float(text)) if spec["type"] == "Int" else flt(text)
	except ValueError:
		frappe.throw(_("{0}: \"{1}\" is not a number.").format(spec["label"], raw))


def value_of(spec, raw, row):
	"""The cell as the field's value - or a ValidationError saying why it cannot be."""
	kind = spec["type"]
	if spec["fieldname"] in ("status", "solar_lead_status") and _norm(raw) in NEW_WORDS:
		return "Lead" if spec["fieldname"] == "status" else "New"
	if kind == "Select":
		return _option(spec, raw)
	if kind == "Link":
		return _link(spec, raw, row)
	if kind == "Date":
		return _date(spec, raw)
	if kind in ("Int", "Float", "Currency", "Percent"):
		return _number(spec, raw)
	if spec["fieldname"] in PHONE_FIELDS:
		raw = _phone(raw)
	if spec["fieldname"] == "email_id" and not frappe.utils.validate_email_address(raw):
		frappe.throw(_("{0}: \"{1}\" is not an email address.").format(spec["label"], raw))
	return raw


def read_row(cells, cols, specs):
	"""({field: value}, lead ID, [errors]) of one row; blank cells are left out."""
	values, errors, lead_id = {}, [], ""
	raw = {f: (cells[i] if i < len(cells) else "") for i, f in enumerate(cols) if f}
	lead_id = raw.pop("id", "")
	# Parents first: a district is looked up in its state.
	for field in sorted(raw, key=lambda f: f not in ("state", "discom")):
		text = raw[field]
		if not text:
			continue
		try:
			values[field] = value_of(specs[field], text, values)
		except frappe.ValidationError as e:
			errors.append(str(e))
			frappe.clear_messages()
	return values, lead_id, errors


# ------------------------------------------------------------------ what each row will do
def _known():
	"""The leads this person may see, by mobile number and by email."""
	by_phone, by_email = {}, {}
	for lead in frappe.get_list("Lead", fields=["name", "mobile_no", "whatsapp_no", "email_id"], limit_page_length=0):
		for phone in {_digits(lead.mobile_no), _digits(lead.whatsapp_no)} - {""}:
			by_phone.setdefault(phone, []).append(lead.name)
		if lead.email_id:
			by_email.setdefault(lead.email_id.strip().lower(), []).append(lead.name)
	return by_phone, by_email


def _changes(doc, values, specs):
	"""The labels of the fields this row changes on the lead."""
	out = []
	for field, value in values.items():
		now = doc.get(field)
		if specs[field]["type"] in ("Int", "Float", "Currency", "Percent"):
			same = flt(now) == flt(value)
		else:
			same = str(now or "")[:10 if specs[field]["type"] == "Date" else None] == str(value)
		if not same:
			out.append(specs[field]["label"])
	return out


def plan(mode, headers, body, specs, campaign=None):
	"""What each row will do, and the columns read and left out. `campaign` (a Campaign's name,
	or NEW_CAMPAIGN) goes on every row that names none."""
	cols, ignored = columns(headers, specs)
	used = [f for f in cols if f]
	if mode == "update" and not {"id", "mobile_no", "email_id"} & set(used):
		frappe.throw(_("To update leads the sheet needs a Lead ID, Mobile or Email column to find each one by."),
			title=_("No column to match on"))
	if mode == "add" and not {"lead_name", "company_name"} & set(used):
		frappe.throw(_("To add leads the sheet needs a Name (or Company) column."), title=_("No name column"))
	by_phone, by_email = _known()
	seen, rows = {}, []
	for number, cells in body:
		values, lead_id, errors = read_row(cells, cols, specs)
		if campaign and "campaign_name" in specs and not values.get("campaign_name"):
			values["campaign_name"] = campaign
		title = values.get("lead_name") or values.get("company_name") or values.get("mobile_no") or lead_id or ""
		row = {"row": number, "title": title, "action": "skip", "lead": "", "changes": [], "errors": errors, "values": values}
		phone, email = _digits(values.get("mobile_no")), (values.get("email_id") or "").lower()
		key = phone or email
		if key and key in seen:
			errors.append(_("Same mobile number or email as row {0}.").format(seen[key]))
		elif key:
			seen[key] = number
		if mode == "add":
			if not (values.get("lead_name") or values.get("company_name")):
				errors.append(_("No name or company."))
			existing = by_phone.get(phone) or by_email.get(email) or []
			if existing:
				row["lead"] = existing[0]
				errors.append(_("Already a lead: {0}. Use Update existing leads to change it.").format(existing[0]))
			if not errors:
				row["action"] = "add"
		else:
			if lead_id:
				found = frappe.get_list("Lead", filters={"name": lead_id}, pluck="name", limit=1)
				how = _("Lead ID {0}").format(lead_id)
			else:
				found = by_phone.get(phone) or by_email.get(email) or []
				how = _("this mobile number") if phone and (phone in by_phone or not email) else _("this email")
			if not found:
				errors.append(_("No lead with {0}.").format(how if (lead_id or key) else _("a Lead ID, mobile or email")))
			elif len(set(found)) > 1:
				errors.append(_("{0} leads have {1} ({2}). Add a Lead ID column.").format(len(set(found)), how, ", ".join(sorted(set(found))[:3])))
			else:
				row["lead"] = found[0]
				doc = frappe.get_doc("Lead", found[0])
				if not doc.has_permission("write"):
					errors.append(_("You may not change {0}.").format(found[0]))
				elif not errors:
					row["changes"] = _changes(doc, values, specs)
					row["action"] = "update" if row["changes"] else "same"
				row["title"] = row["title"] if values.get("lead_name") else (doc.lead_name or doc.company_name or row["title"])
		rows.append(row)
	return rows, [specs[f]["label"] if f != "id" else _("Lead ID") for f in used], ignored


# ------------------------------------------------------------------ endpoints
def _may(mode):
	if mode not in MODES:
		frappe.throw(_("Choose to add new leads or update existing ones."))
	if not frappe.has_permission("Lead", "create" if mode == "add" else "write"):
		frappe.throw(_("You may not {0} leads.").format(_("add") if mode == "add" else _("change")), frappe.PermissionError)


def _key(token):
	return f"{CACHE}::{frappe.session.user}::{token}"


def campaign_choices():
	"""The campaigns this person may put leads in, newest first: {value, label}."""
	from a3_sola.api.portal_fields import link_choices

	return link_choices("Campaign")


def _campaign_named(title):
	return frappe.db.get_value("Campaign", {"campaign_name": title})


def _chosen_campaign(campaign, new_campaign, specs):
	"""(what goes on the rows, its name to show, the new campaign's name to make) - the campaign
	chosen must be one offered; a new one, one this person may make."""
	new_campaign = (new_campaign or "").strip()
	if new_campaign:
		if len(new_campaign) > 140:
			frappe.throw(_("Keep the campaign's name under 140 letters."))
		existing = _campaign_named(new_campaign)
		if existing:
			return existing, new_campaign, ""
		if not frappe.has_permission("Campaign", "create"):
			frappe.throw(_("You may not make campaigns. Choose one there is."), frappe.PermissionError)
		return NEW_CAMPAIGN, new_campaign, new_campaign
	if not campaign:
		return None, "", ""
	choice = next((c for c in (specs.get("campaign_name") or {}).get("choices") or [] if c["value"] == campaign), None)
	if not choice:
		frappe.throw(_("Choose a campaign from the list."))
	return campaign, choice.get("label") or campaign, ""


SETTINGS = "A3 Sola Settings"
SHEET_ROW = "Lead Import Sheet"


def saved_sheets():
	"""The Google Sheets leads come in on (A3 Sola Settings > Lead Sheets), in their order:
	[{id, title, url}]."""
	rows = frappe.get_all(SHEET_ROW, filters={"parenttype": SETTINGS, "parentfield": "lead_sheets"},
		fields=["name", "sheet_name", "sheet_url"], order_by="idx asc")
	return [{"id": r.name, "title": r.sheet_name, "url": r.sheet_url} for r in rows]


def may_save_sheet():
	return bool(frappe.has_permission(SETTINGS, "write"))


def _must_save():
	if not may_save_sheet():
		frappe.throw(_("You do not have permission to do that."), frappe.PermissionError)


def add_sheet(title, url):
	"""Keep a sheet by name; the same link kept again only takes the new name. Written as a row
	of the settings, not by saving them, so nothing else in the settings is checked."""
	url, title = (url or "").strip(), (title or "").strip()
	export_url(url)
	if not title:
		frappe.throw(_("Name the sheet."))
	if len(title) > 140:
		frappe.throw(_("Keep the sheet's name under 140 letters."))
	same = frappe.db.get_value(SHEET_ROW, {"parenttype": SETTINGS, "parentfield": "lead_sheets", "sheet_url": url})
	if same:
		frappe.db.set_value(SHEET_ROW, same, "sheet_name", title)
		return
	idx = frappe.db.sql("select coalesce(max(idx), 0) from `tabLead Import Sheet` where parenttype = %s and parentfield = 'lead_sheets'",
		SETTINGS)[0][0]
	row = frappe.get_doc({"doctype": SHEET_ROW, "parent": SETTINGS, "parenttype": SETTINGS, "parentfield": "lead_sheets",
		"idx": idx + 1, "sheet_name": title, "sheet_url": url})
	row.db_insert()


@frappe.whitelist(methods=["POST"])
def sheet_title(url=None):
	"""The name Google Sheets gives the sheet at this link, to start the saved sheet's name from;
	"" when it cannot be read - the person names it."""
	_must_save()
	sheet = re.search(r"/spreadsheets/d/([\w-]+)", export_url(url))
	if not sheet or sheet.group(1) == "e":
		return ""
	try:
		response = requests.get(f"https://docs.google.com/spreadsheets/d/{sheet.group(1)}/edit", timeout=15)
	except requests.RequestException:
		return ""
	found = re.search(r"<title>(.*?)</title>", response.text or "", re.S) if response.ok else None
	title = re.sub(r"\s*-\s*Google (Sheets|Drive)\s*$", "", html.unescape(found.group(1)).strip()) if found else ""
	return "" if title.lower() in ("google sheets", "google drive", "sign in") else title[:140]


@frappe.whitelist(methods=["POST"])
def save_sheet(url=None, title=None):
	"""Keep this link, by the name given, among the lead sheets; the sheets as they now are."""
	_must_save()
	add_sheet(title, url)
	return saved_sheets()


@frappe.whitelist(methods=["POST"])
def remove_sheet(sheet=None):
	"""No longer keep this sheet among the lead sheets (the sheet itself is not touched)."""
	_must_save()
	if sheet and frappe.db.exists(SHEET_ROW, {"name": sheet, "parenttype": SETTINGS}):
		frappe.db.delete(SHEET_ROW, {"name": sheet, "parenttype": SETTINGS})
	return saved_sheets()


@frappe.whitelist(methods=["POST"])
def preview(url=None, mode="add", campaign=None, new_campaign=None):
	"""Read the sheet and say what each row will do - nothing is saved. The rows to import are
	kept for an hour under the token `run` is given."""
	_may(mode)
	specs = field_specs()
	on_rows, campaign_title, to_make = _chosen_campaign(campaign, new_campaign, specs)
	headers, body = parse(fetch(url))
	if len(body) > MAX_ROWS:
		frappe.throw(_("The sheet has {0} rows; import up to {1} at a time.").format(len(body), MAX_ROWS), title=_("Too many rows"))
	rows, read, ignored = plan(mode, headers, body, specs, on_rows)
	todo = [{"row": r["row"], "lead": r["lead"], "values": r["values"]} for r in rows if r["action"] in ("add", "update")]
	token = frappe.generate_hash(length=16)
	frappe.cache().set_value(_key(token), json.dumps({"mode": mode, "todo": todo, "new_campaign": to_make}), expires_in_sec=TTL)
	counts = {a: sum(1 for r in rows if r["action"] == a) for a in ("add", "update", "same", "skip")}
	for r in rows:
		r.pop("values")
	return {"token": token, "mode": mode, "rows": rows, "counts": counts, "columns": read, "ignored": ignored,
		"campaign": campaign_title, "campaign_is_new": bool(to_make)}


def _add(values):
	"""A new lead: the lead form's defaults, as a lead not yet contacted (NEW_LEAD), where the
	sheet says nothing."""
	doc = frappe.new_doc("Lead")
	defaults = {**lead_defaults(), **NEW_LEAD}
	for field, value in defaults.items():
		if field not in values:
			doc.set(field, value or None)
	for field, value in values.items():
		doc.set(field, value)
	# Left blank on purpose: insert would otherwise put the doctype's default back (Connected, today).
	doc.dont_update_if_missing = [f for f, v in NEW_LEAD.items() if v is None and f not in values]
	doc.insert()
	return doc


def _update(name, values):
	doc = load_lead(name, "write")
	for field, value in values.items():
		if field == "lead_name":
			_set_full_name(doc, value)
		elif field == "status" and value not in LEAD_STATUSES:
			frappe.throw(_("Choose a valid status."))
		else:
			doc.set(field, value)
	doc.save()
	return doc


@frappe.whitelist(methods=["POST"])
def run(token=None, start=0):
	"""Import the next batch of the previewed rows, each on its own: what went in, and why any
	did not."""
	saved = frappe.cache().get_value(_key(token or ""))
	if not saved:
		frappe.throw(_("This check has expired. Check the sheet again."), title=_("Check again"))
	data = json.loads(saved)
	_may(data["mode"])
	start = max(cint(start), 0)
	batch = data["todo"][start:start + BATCH]
	# The new campaign, made once - by the first batch - and found by its name after.
	made = ""
	if data.get("new_campaign") and batch:
		made = _campaign_named(data["new_campaign"])
		if not made:
			made = frappe.get_doc({"doctype": "Campaign", "campaign_name": data["new_campaign"],
				"description": _("Leads imported from a Google Sheet.")}).insert().name
	results = []
	for item in batch:
		if made and item["values"].get("campaign_name") == NEW_CAMPAIGN:
			item["values"]["campaign_name"] = made
		frappe.db.savepoint(SAVEPOINT)
		try:
			doc = _add(dict(item["values"])) if data["mode"] == "add" else _update(item["lead"], dict(item["values"]))
			results.append({"row": item["row"], "ok": True, "lead": doc.name, "title": doc.lead_name or doc.company_name or doc.name,
				"route": lead_route(doc.name)})
		except Exception as e:
			frappe.db.rollback(save_point=SAVEPOINT)
			message = re.sub(r"<[^>]+>", "", str(e)) or _("Could not be saved.")
			results.append({"row": item["row"], "ok": False, "lead": item["lead"], "error": message})
		frappe.clear_messages()
	end = start + len(batch)
	if end >= len(data["todo"]):
		frappe.cache().delete_value(_key(token))
	return {"results": results, "next": end, "total": len(data["todo"]), "done": end >= len(data["todo"])}


@frappe.whitelist()
def template(with_leads=0):
	"""A CSV of the columns the import reads - with the leads this person may see, to edit and
	import back as an update, when `with_leads`."""
	specs = field_specs()
	fields = list(specs)
	out = io.StringIO()
	writer = csv.writer(out)
	writer.writerow([_("Lead ID")] + [specs[f]["label"] for f in fields])
	if cint(with_leads):
		labels = {f: {str(c["value"]): c.get("label") or c["value"] for c in specs[f].get("choices") or []} for f in fields}
		for lead in frappe.get_list("Lead", fields=["name"] + fields, order_by="creation desc", limit_page_length=MAX_ROWS):
			writer.writerow([lead.name] + [labels[f].get(str(lead.get(f)), lead.get(f)) if lead.get(f) not in (None, "") else ""
				for f in fields])
	frappe.response["type"] = "download"
	frappe.response["filename"] = "leads.csv" if cint(with_leads) else "leads-import-template.csv"
	frappe.response["filecontent"] = out.getvalue()
