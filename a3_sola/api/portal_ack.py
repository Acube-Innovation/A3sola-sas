# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The PM Surya Ghar portal's acknowledgement - "Acknowledgement for Submission of Rooftop Solar
Application" - read into the Portal Registration task's Portal Application: its Application
Reference Number and date, as the National Portal gives them:

	1  Application Reference Number/ Date   NP-KLSEB26-16222078 / 28-10-2026
	2  Name of Applicant                    P MANOJ

It is attached on the task's Attachments card as a PM Surya Ghar Acknowledgement, as the Jan
Samarth task's approval letter is (api/approval_letter).
"""

import re

import frappe
from frappe import _

from a3_sola.api.approval_letter import _customer, same_person
from a3_sola.api.kseb_bill import extract_text

DOCUMENT_TYPE = "PM Surya Ghar Acknowledgement"
DOCTYPE = "Portal Application"
#: A National Portal application number: NP-<state and DISCOM>-<digits>.
NUMBER = r"(NP-[A-Z0-9]+-\d{5,})"
DATE = r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{4})"


def _date(value):
	from datetime import datetime

	for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
		try:
			return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
		except (TypeError, ValueError):
			continue
	return None


def parse(text):
	"""{application_number, application_date, name, consumer_number, capacity_kw}, as far as
	the acknowledgement gives them."""
	text = (text or "").replace("\r", "")
	out = {}
	row = re.search(r"Application\s+Reference\s+Number\s*/\s*Date\s+" + NUMBER + r"\s*/\s*" + DATE, text, re.IGNORECASE)
	if row:
		out["application_number"], out["application_date"] = row.group(1), _date(row.group(2))
	else:
		number = re.search(r"Application\s+Reference\s+Number[^A-Z0-9]*" + NUMBER, text, re.IGNORECASE) or re.search(NUMBER, text)
		if number:
			out["application_number"] = number.group(1)
		date = re.search(r"\bDate\s*:\s*" + DATE, text)
		if date:
			out["application_date"] = _date(date.group(1))
	name = re.search(r"Name\s+of\s+Applicant\s+([A-Z][A-Za-z .]+?)\s*$", text, re.MULTILINE) or \
		re.search(r"Sh/Smt\.?\s+([A-Z][A-Za-z .]+?)(?:\s{2,}|\s+Date\b|$)", text, re.MULTILINE)
	if name:
		out["name"] = name.group(1).strip()
	consumer = re.search(r"Consumer\s+Account\s+Number\s+in\s+Discom\s+(\d{6,})", text, re.IGNORECASE)
	if consumer:
		out["consumer_number"] = consumer.group(1)
	capacity = re.search(r"Applied\s+Capacity\s*[–-]\s*([\d.]+)\s*kWp", text, re.IGNORECASE)
	if capacity:
		out["capacity_kw"] = float(capacity.group(1))
	return out


def is_acknowledgement(text):
	return bool(re.search(r"Acknowledgement\s+for\s+Submission", text or "", re.IGNORECASE))


def fields_of(found):
	"""The Portal Application fields the acknowledgement fills."""
	out = {}
	if found.get("application_number"):
		out["application_number"] = found["application_number"]
		out["national_portal_application_id"] = found["application_number"]
	if found.get("application_date"):
		out["application_date"] = found["application_date"]
	return out


def warnings(found, installation=None):
	out = []
	customer = _customer(installation)
	if found.get("name") and customer and not same_person(found["name"], customer):
		out.append(_("This acknowledgement is for {0}, but the project is {1}'s. Check it is the right customer's.").format(
			found["name"], customer))
	if found.get("consumer_number") and installation:
		ours = frappe.db.get_value("Solar Installation", installation, "consumer_number") or \
			frappe.db.get_value("Solar Consumer", frappe.db.get_value("Solar Installation", installation, "solar_consumer"),
				"consumer_number")
		if ours and str(ours).strip() != found["consumer_number"]:
			out.append(_("Its consumer number is {0}, the project's is {1}.").format(found["consumer_number"], ours))
	return out


@frappe.whitelist(methods=["POST"])
def read(installation=None, task=None):
	"""Read the acknowledgement posted as `file`: the fields to fill, warnings when it is
	another customer's, and how it was read. Nothing is saved - the form fills its fields,
	and the file goes on the application as it is attached."""
	if task and frappe.db.exists(DOCTYPE, task):
		installation = installation or frappe.db.get_value(DOCTYPE, task, "solar_installation")
	if installation:
		frappe.get_doc("Solar Installation", installation).check_permission("read")
	upload = (frappe.request.files.getlist("file") or [None])[0] if frappe.request and frappe.request.files else None
	if not upload:
		frappe.throw(_("No file was sent."))
	text, source = extract_text(upload.stream.read(), upload.filename)
	if not is_acknowledgement(text):
		return {"fields": {}, "warnings": [_("This does not look like the National Portal's acknowledgement.")],
			"source": source}
	found = parse(text)
	return {"fields": fields_of(found), "warnings": warnings(found, installation), "source": source, "found": found}


def fill_document(name, content, filename):
	"""An acknowledgement attached to a saved Portal Application fills its number and date
	where they are blank - attached from its own page, where there is no form to fill."""
	doc = frappe.get_doc(DOCTYPE, name)
	text, _source = extract_text(content, filename)
	if not is_acknowledgement(text):
		return
	changed = False
	for field, value in fields_of(parse(text)).items():
		df = doc.meta.get_field(field)
		# A submitted application takes only what may still change after submit.
		if value and df and not doc.get(field) and (doc.docstatus == 0 or df.allow_on_submit):
			doc.set(field, value)
			changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
