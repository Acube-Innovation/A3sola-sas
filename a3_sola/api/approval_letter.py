# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Digital Approval Letter from Jan Samarth, read as a KSEB bill is (api/kseb_bill.py): a
PDF from its text, a photo or scan through OCR. Its sanction number is the Jan Samarth task's
reference and its date the day the approval came:

	Digital Sanction for your application : ANS-SOLAR-18883537-6148915
	Date : 28 October 2026
"""

import re
from datetime import datetime

import frappe
from frappe import _
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api.kseb_bill import extract_text

DOCUMENT_TYPE = "Digital Approval Letter"
#: The Installation Task fields the letter fills: (field, what is read).
FIELDS = (("approval_reference", "reference"), ("approval_received_on", "date"))


def parse(text):
	"""{reference, date (YYYY-MM-DD)}, as far as the letter's text gives them."""
	text = (text or "").replace("\r", "")
	out = {}
	# Another document picked as the letter (a KSEB bill) gives nothing, not its own dates.
	if not re.search(r"sanction|jan\s*samarth", text, re.IGNORECASE):
		return out
	# The applicant, under the letter's "Congratulations".
	name = re.search(r"Congratulations\s*\n\s*([A-Za-z][A-Za-z .']{1,60}?)\s*\n", text, re.IGNORECASE)
	if name:
		out["name"] = re.sub(r"\s+", " ", name.group(1)).strip()
	reference = re.search(r"Digital\s*Sanction[^:\n]*:\s*([A-Z]{2,}[A-Z0-9]*(?:\s*-\s*[A-Z0-9]+)+)", text, re.IGNORECASE)
	if not reference:
		reference = re.search(r"\b(ANS\s*-\s*[A-Z]+\s*-\s*\d+\s*-\s*\d+)\b", text, re.IGNORECASE)
	if reference:
		out["reference"] = re.sub(r"\s+", "", reference.group(1)).upper()
	date = re.search(r"^\s*Date\s*:?\s*(\d{1,2}\s*[A-Za-z]{3,9}\s*,?\s*\d{4}|\d{1,2}[-/.]\d{1,2}[-/.]\d{4})", text, re.MULTILINE)
	if date:
		out["date"] = _date(date.group(1))
	return {k: v for k, v in out.items() if v}


def _date(value):
	value = re.sub(r"\s+", " ", value.replace(",", " ")).strip()
	for fmt in ("%d %B %Y", "%d %b %Y", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
		try:
			return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
		except ValueError:
			continue
	return None


def task_values(read):
	"""The task's fields from what the letter gave."""
	return {field: read[key] for field, key in FIELDS if read.get(key)}


def read_content(content, filename):
	text, source = extract_text(content, filename)
	return parse(text), source


def _words(name):
	return [w for w in re.split(r"[^a-z]+", (name or "").lower()) if w]


def same_person(a, b):
	"""Whether two spellings name one person: "Manoj P" and "P MANOJ", "CK Boban" and
	"C.K. Boban". Every full word (three letters or more) of the shorter name is in the other,
	and they share at least one."""
	wa, wb = [w for w in _words(a) if len(w) > 2], [w for w in _words(b) if len(w) > 2]
	if not wa or not wb:
		return True  # nothing to tell them apart by
	short, long_ = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
	return all(w in long_ for w in short)


def _customer(installation=None, task=None):
	"""The customer's name on the job the letter is for."""
	if task and frappe.db.exists("Installation Task", task):
		installation = frappe.db.get_value("Installation Task", task, "solar_installation")
	if installation and frappe.db.exists("Solar Installation", installation):
		return frappe.db.get_value("Solar Installation", installation, "consumer_name")
	return None


def warnings(found, installation=None, task=None):
	customer = _customer(installation, task)
	if found.get("name") and customer and not same_person(found["name"], customer):
		return [_("This letter is for {0}, but the project is {1}'s. Check it is the right customer's letter.").format(
			found["name"], customer)]
	return []


@frappe.whitelist(methods=["POST"])
def read(installation=None, task=None):
	"""Read the letter posted as `file`: the task's fields to fill, a warning when it names
	someone other than the job's customer, and how it was read. Nothing is saved - the form
	fills its fields, and the file goes on the task as it is attached."""
	if not (frappe.has_permission("Installation Task", "create") or frappe.has_permission("Installation Task", "write")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	upload = (frappe.request.files.getlist("file") or [None])[0] if frappe.request and frappe.request.files else None
	if not upload:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	content = upload.stream.read()
	if len(content) > get_max_file_size():
		frappe.throw(_("{0} is larger than {1} MB.").format(upload.filename, get_max_file_size() // (1024 * 1024)),
			frappe.ValidationError)
	found, source = read_content(content, upload.filename)
	return {"fields": task_values(found), "name": found.get("name"), "warnings": warnings(found, installation, task),
		"source": source}


def fill_task(task_name, content, filename):
	"""A letter attached to a saved Jan Samarth task fills its reference and date where they
	are blank - attached from its own page, where there is no form to fill."""
	task = frappe.get_doc("Installation Task", task_name)
	if task.task_code != "DAL" or task.docstatus != 0:
		return {}
	try:
		found, _source = read_content(content, filename)
	except Exception:
		return {}
	values = {k: v for k, v in task_values(found).items() if not task.get(k)}
	if values:
		frappe.db.set_value("Installation Task", task_name, values)
	return values
