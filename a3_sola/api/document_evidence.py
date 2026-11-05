# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer's documents, as the subsidy eligibility check sees them: each one uploaded on
the lead or the customer and read by OCR - the KSEB bill, the Aadhaar card, the passbook or
cancelled cheque - with what it said, and each detail with the document it came from: "Customer
Name: Manoj P - from the Aadhaar card".

What a document said is kept on its File (`a3s_read_values`) whenever it is read - on upload,
by Read, by "Read KSEB bill" or "Read Aadhaar front" / "back" - so it is evidence that stays: what the form
holds may be typed over later, what the document said does not change.

Where two documents spell a detail two ways - the bill's "MANOJ P" and the card's "Manoj
Prabhakaran", or an account holder who is not the customer - it is a conflict. The check
shows it as a warning, and is submitted only once someone has looked at the documents and
confirmed the details are correct. A new or re-read document that changes the conflicts asks
for the confirmation again.
"""

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import format_date, format_datetime, now_datetime

CHECK = "Subsidy Eligibility Check"
CONSUMER = "Solar Consumer"
#: The records whose documents are the customer's.
DOCTYPES = ("Lead", CONSUMER)
READ_VALUES, READ_ON = "a3s_read_values", "a3s_read_on"
#: What the page calls each kind of document.
DOCUMENT_NAMES = {"KSEB Bill": "KSEB bill", "Aadhaar Front": "Aadhaar card", "Aadhaar Back": "Aadhaar card",
	"Bank Passbook": "Bank passbook", "Cancelled Cheque": "Cancelled cheque"}
#: A lead's field and the customer's that hold the same detail, under the customer's name. The
#: account holder is the customer too: the subsidy is paid into the customer's own account.
SAME_AS = {"lead_name": "consumer_name", "bank_account_holder_name": "consumer_name", "state": "site_state",
	"district": "site_district", "approx_consumption_units": "avg_consumption_units"}
#: Details compared by their letters alone: "C.K. Boban" and "CK BOBAN" are one spelling.
NAMES = {"consumer_name"}
#: Not details of the customer: how the form was set, not what the document says.
SKIP = {"permanent_address_same"}


# ------------------------------------------------------------------ keeping what was read
def store(file_name, fields):
	"""What OCR read from a document, kept on its File."""
	if not (file_name and fields):
		return
	frappe.db.set_value("File", file_name, {READ_VALUES: json.dumps(fields, sort_keys=True, default=str),
		READ_ON: now_datetime()}, update_modified=False)


def _read(file):
	try:
		value = json.loads(file.get(READ_VALUES) or "{}")
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}


# ------------------------------------------------------------------ the customer's documents
def records(check):
	"""The lead and the customer the check is for - the customer's lead, if the check names none."""
	lead, consumer = check.get("lead"), check.get("solar_consumer")
	if consumer and not lead:
		lead = frappe.db.get_value(CONSUMER, consumer, "lead")
	return [(dt, name) for dt, name in (("Lead", lead), (CONSUMER, consumer)) if name and frappe.db.exists(dt, name)]


def _documents(check):
	from a3_sola.api.portal_attachments import READERS

	out = []
	for doctype, name in records(check):
		readable = [t for (dt, t) in READERS if dt == doctype]
		files = frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name, "is_folder": 0,
			"a3s_document_type": ["in", readable]}, fields=["name", "file_name", "file_url", "a3s_document_type",
			READ_VALUES, READ_ON], order_by="creation asc")
		for f in files:
			out.append({"file": f.name, "file_name": f.file_name, "file_url": f.file_url, "document_type": f.a3s_document_type,
				"document": DOCUMENT_NAMES.get(f.a3s_document_type, f.a3s_document_type), "doctype": doctype, "record": name,
				"read_on": format_datetime(f.get(READ_ON), "d MMM yyyy, h:mm a") if f.get(READ_ON) else "",
				"fields": _read(f)})
	return out


def _label(fieldname, doctype):
	for dt in (CONSUMER, doctype):
		df = frappe.get_meta(dt).get_field(fieldname)
		if df:
			return _(df.label)
	return fieldname.replace("_", " ").title()


def _shown(value, fieldname, doctype):
	"""A value as a person reads it: a linked record by its title, not its id."""
	df = frappe.get_meta(doctype).get_field(fieldname)
	if df and df.fieldtype == "Date" and value:
		return format_date(value, "d MMM yyyy")
	if df and df.fieldtype == "Link" and value:
		title_field = frappe.get_meta(df.options).title_field
		if title_field and title_field != "name":
			return frappe.db.get_value(df.options, value, title_field) or value
	return str(value)


def _same(fieldname, value):
	text = str(value or "").lower()
	return re.sub(r"[^a-z]", "", text) if fieldname in NAMES else re.sub(r"[^a-z0-9]", "", text)


def evidence(check):
	"""The documents, each detail with the documents it came from, and the conflicts."""
	documents = _documents(check)
	details = {}
	for doc in documents:
		for fieldname, value in doc["fields"].items():
			if fieldname in SKIP or value in (None, ""):
				continue
			key = SAME_AS.get(fieldname, fieldname)
			detail = details.setdefault(key, {"field": key, "label": _label(key, doc["doctype"]), "values": []})
			detail["values"].append({"value": _shown(value, fieldname, doc["doctype"]), "compare": _same(key, value),
				"document": doc["document"], "file_name": doc["file_name"], "file_url": doc["file_url"],
				# Said when it is another field's: the account holder's name, beside the customer's.
				"as": _label(fieldname, doc["doctype"]) if fieldname != key else ""})
	rows = []
	for detail in details.values():
		spellings = {v["compare"] for v in detail["values"]}
		detail["conflict"] = len(spellings) > 1
		rows.append(detail)
	order = {"consumer_name": 0}
	rows.sort(key=lambda d: (not d["conflict"], order.get(d["field"], 1), d["label"]))
	conflicts = [{"field": d["field"], "label": d["label"],
		"values": [{k: v[k] for k in ("value", "document", "as")} for v in d["values"]]} for d in rows if d["conflict"]]
	for d in rows:
		for v in d["values"]:
			v.pop("compare", None)
	return {"documents": documents, "details": rows, "conflicts": conflicts, "signature": signature(conflicts)}


def signature(conflicts):
	"""What was confirmed: the conflicting details and their spellings. A document that changes
	them changes this, and the confirmation is asked for again."""
	if not conflicts:
		return ""
	basis = sorted((c["field"], sorted({(v["value"], v["document"]) for v in c["values"]})) for c in conflicts)
	return hashlib.sha1(json.dumps(basis).encode()).hexdigest()


def is_confirmed(check, found=None):
	found = found or evidence(check)
	return not found["conflicts"] or check.get("documents_confirmed") == found["signature"]


def assert_confirmed(check):
	found = evidence(check)
	if not is_confirmed(check, found):
		frappe.throw(_("The customer's documents differ on {0}. Check them on this eligibility check and confirm they are "
			"correct before submitting it.").format(", ".join(c["label"] for c in found["conflicts"])),
			title=_("Documents Differ"))


# ------------------------------------------------------------------ the page's calls
@frappe.whitelist()
def get(name):
	"""The check's documents, details and conflicts, and whether they are confirmed."""
	check = frappe.get_doc(CHECK, name)
	check.check_permission("read")
	found = evidence(check)
	by = check.get("documents_confirmed_by")
	confirmed = bool(found["conflicts"]) and check.get("documents_confirmed") == found["signature"]
	return dict(found, confirmed=confirmed,
		confirmed_by=(frappe.db.get_value("User", by, "full_name") or by) if confirmed and by else "",
		confirmed_on=format_datetime(check.get("documents_confirmed_on"), "d MMM yyyy, h:mm a") if confirmed else "",
		can_confirm=bool(frappe.has_permission(CHECK, "write", name) or frappe.has_permission(CHECK, "submit", name)))


@frappe.whitelist(methods=["POST"])
def confirm(name, signature):
	"""Someone has checked the documents: the details that differ are correct as they stand."""
	check = frappe.get_doc(CHECK, name)
	if not (frappe.has_permission(CHECK, "write", name) or frappe.has_permission(CHECK, "submit", name)):
		frappe.throw(_("You do not have permission to do that."), frappe.PermissionError)
	found = evidence(check)
	if not found["conflicts"]:
		return get(name)
	if signature != found["signature"]:
		frappe.throw(_("The documents have changed since this page was opened. Check them again and confirm."),
			title=_("Documents Changed"))
	frappe.db.set_value(CHECK, name, {"documents_confirmed": signature, "documents_confirmed_by": frappe.session.user,
		"documents_confirmed_on": now_datetime()})
	frappe.get_doc(CHECK, name).add_comment("Info", _("Confirmed the customer's documents correct where they differ: {0}.").format(
		", ".join(c["label"] for c in found["conflicts"])))
	return get(name)
