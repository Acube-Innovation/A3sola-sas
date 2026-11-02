# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Enter Serial Numbers task: the job's serial register - modules, inverters, optimisers and
the rest - filled after the supplier's bill is in.

Three ways in, all onto the one register (Solar Installation's `serials`, checked by
api/serials.validate_register - each serial once, on no other job - and read by Serials to
Electrical Contractor and the commissioning gate):

- from the supplier's bill: the serials its lines list (api/supplier_bill puts them in each
  Purchase Invoice line's description as "Serial nos.: ..."), typed by the line's HSN code;
- read off a photo or PDF of the labels, the sticker sheet or a packing list (OCR, as the KSEB
  bill is read), ticked on the page before they are added;
- typed or corrected on the page.
"""

import re

import frappe
from frappe import _
from frappe.utils import today
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api import stages
from a3_sola.api.stages import _get_stage

CODE = "SERIAL"
INSTALLATION = "Solar Installation"
TYPES = ("Module", "Inverter", "Optimiser", "Other")
#: The page's field for each type's serials, one a line.
FIELDS = {"Module": "module_serials", "Inverter": "inverter_serials", "Optimiser": "optimiser_serials",
	"Other": "other_serials"}

SERIALS_IN = re.compile(r"Serial nos?\.?\s*:\s*(.+)", re.IGNORECASE)
#: A serial read off a label: 8 to 30 letters, digits, "-" or "/", six digits or more of them.
TOKEN = re.compile(r"(?<![\w/-])([A-Za-z0-9][A-Za-z0-9/-]{6,28}[A-Za-z0-9])(?![\w/-])")
GSTIN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")
DATE = re.compile(r"^\d{1,2}[-/.](\d{1,2}|[A-Za-z]{3})[-/.]\d{2,4}$")


def is_serial_entry_task(code):
	return code == CODE


def _job(installation, ptype="read"):
	if not installation or not frappe.db.exists(INSTALLATION, installation):
		frappe.throw(_("No such project."), frappe.DoesNotExistError)
	inst = frappe.get_doc(INSTALLATION, installation)
	inst.check_permission(ptype)
	return inst


def kind_of(hsn=None, name=None):
	"""What a bill line is, by its HSN code - 8541 solar modules, 8504 inverters - else its name."""
	hsn, name = (hsn or "").strip(), (name or "").lower()
	if hsn.startswith("8541") or "module" in name or re.search(r"\d{3}\s*w\s*p\b", name):
		return "Module"
	if "optimi" in name:
		return "Optimiser"
	if hsn.startswith("8504") or "inverter" in name:
		return "Inverter"
	return "Other"


def from_bills(inst):
	"""The serials the job's supplier bills list, each with its type, item and bill."""
	if not frappe.get_meta("Purchase Invoice").has_field("a3s_material_bill"):
		return []
	rows = frappe.db.sql("""
		select pi.name as invoice, pi.bill_no, item.item_name, item.item_code, item.gst_hsn_code, item.description
		from `tabPurchase Invoice` pi join `tabPurchase Invoice Item` item on item.parent = pi.name
		where pi.solar_installation = %s and pi.a3s_material_bill = 1 and pi.docstatus = 1
		order by pi.posting_date, pi.name, item.idx""", inst.name, as_dict=True)
	out, seen = [], set()
	for row in rows:
		match = SERIALS_IN.search(row.description or "")
		if not match:
			continue
		kind = kind_of(row.gst_hsn_code, row.item_name)
		for serial in re.split(r"[,\s]+", match.group(1).split("\n")[0]):
			serial = serial.strip().strip(".")
			if serial and serial.upper() not in seen:
				seen.add(serial.upper())
				out.append({"serial_no": serial, "component_type": kind, "item_name": row.item_name,
					"item_code": row.item_code, "bill_no": row.bill_no, "invoice": row.invoice})
	return out


def serial_tokens(text):
	"""The serial numbers in a label's text: codes with six digits or more - not amounts, dates,
	HSN codes, GSTINs or phone numbers."""
	found, seen = [], set()
	for token in TOKEN.findall((text or "").replace("|", " ")):
		if sum(c.isdigit() for c in token) < 6 or DATE.match(token) or GSTIN.match(token.upper()):
			continue
		if "/" in token or re.search(r"(?i)\d\s*x\s*\d|mm|micron|sqmm|kwp?$|udyam", token):
			continue  # a bill or reference number, a size, a registration - not a serial
		if len(token) > 24 and re.fullmatch(r"[0-9a-f]+", token):
			continue  # an e-invoice IRN
		if len(token) == 15 and re.fullmatch(r"[0-9A-Z]{2}[A-Z]{5}[0-9A-Z]{4}[A-Z][0-9A-Z]{3}", token.upper()):
			continue  # a GSTIN, misread or not
		if token.isdigit() and len(token) <= 8:
			continue  # an HSN code or a pin code - not a serial (a 10-digit one may be: ticked on the page)
		if token.upper() not in seen:
			seen.add(token.upper())
			found.append(token)
	return found


def _register(inst):
	return {t: [r.serial_no for r in inst.get("serials") or [] if r.component_type == t and not r.is_replaced]
		for t in TYPES}


@frappe.whitelist()
def state(installation):
	inst = _job(installation)
	row = _get_stage(inst, CODE)
	register = _register(inst)
	have = {s.upper() for serials in register.values() for s in serials}
	bills = from_bills(inst)
	for b in bills:
		b["in_register"] = b["serial_no"].upper() in have
	expected = int(inst.get("modules_expected") or inst.get("module_count") or 0)
	return {
		"task": {"code": row.stage_code, "name": row.stage_name, "status": row.status,
			"completed_on": frappe.utils.format_date(row.actual_completion_date, "d MMM yyyy") if row.actual_completion_date else ""},
		"installation": inst.name, "consumer_name": inst.get("consumer_name") or "",
		"register": register, "bills": bills, "types": list(TYPES),
		"expected_modules": expected,
		"counts": {t: len(v) for t, v in register.items()},
		"can_edit": bool(inst.has_permission("write")) and row.status != "Skipped",
		"can_complete": bool(inst.has_permission("write")) and row.status not in ("Completed", "Skipped"),
	}


def _write(inst, lists):
	"""Each type's serials as given, one a line: rows from a delivery note or receipt stay; a new
	row from a supplier bill takes its item and maker."""
	from a3_sola.api.dispatch_task import _set_serials

	for kind, text in lists.items():
		if text is not None:
			_set_serials(inst, kind, text)
	bills = {b["serial_no"].upper(): b for b in from_bills(inst)}
	for row in inst.get("serials") or []:
		bill = bills.get((row.serial_no or "").strip().upper())
		if bill and not row.item and bill.get("item_code") and frappe.db.exists("Item", bill["item_code"]):
			row.item = bill["item_code"]
		if bill and not row.model_number:
			row.model_number = (bill.get("item_name") or "")[:140]


@frappe.whitelist(methods=["POST"])
def save(installation, module_serials=None, inverter_serials=None, optimiser_serials=None, other_serials=None):
	"""The register as typed on the page; each serial once, on no other job (validate_register)."""
	inst = _job(installation, "write")
	row = _get_stage(inst, CODE)
	if row.status == "Skipped":
		frappe.throw(_("{0} is skipped.").format(row.stage_name))
	_write(inst, {"Module": module_serials, "Inverter": inverter_serials, "Optimiser": optimiser_serials,
		"Other": other_serials})
	if row.status == "Pending":
		row.status = "In Progress"
	stages._save(inst, _("{0}: serial numbers saved.").format(row.stage_name))
	return state(installation)


@frappe.whitelist(methods=["POST"])
def fetch_from_bills(installation):
	"""Every serial the supplier bills list that the register lacks, added under its type."""
	inst = _job(installation, "write")
	row = _get_stage(inst, CODE)
	register = _register(inst)
	have = {s.upper() for serials in register.values() for s in serials}
	added = [b for b in from_bills(inst) if b["serial_no"].upper() not in have]
	if not added:
		return state(installation)
	for b in added:
		register[b["component_type"]].append(b["serial_no"])
	_write(inst, {t: "\n".join(v) for t, v in register.items()})
	if row.status == "Pending":
		row.status = "In Progress"
	stages._save(inst, _("{0}: {1} serial numbers fetched from the supplier invoice.").format(row.stage_name, len(added)))
	return state(installation)


@frappe.whitelist(methods=["POST"])
def read_upload(installation):
	"""The serial numbers read off the photo or PDF posted as `file` - labels, a sticker sheet,
	a packing list. Nothing is saved: the page ticks which to add."""
	from a3_sola.api.kseb_bill import extract_text

	_job(installation, "write")
	upload = (frappe.request.files.getlist("file") or [None])[0] if frappe.request and frappe.request.files else None
	if not upload:
		frappe.throw(_("No file was sent."), frappe.ValidationError)
	content = upload.stream.read()
	if len(content) > get_max_file_size():
		frappe.throw(_("{0} is larger than {1} MB.").format(upload.filename, get_max_file_size() // (1024 * 1024)),
			frappe.ValidationError)
	text, source = extract_text(content, upload.filename)
	return {"serials": serial_tokens(text), "source": source}


@frappe.whitelist(methods=["POST"])
def mark_done(installation):
	"""Done once the modules the system takes have their serials, and an inverter has one."""
	inst = _job(installation, "write")
	row = _get_stage(inst, CODE)
	if row.status in ("Completed", "Skipped"):
		frappe.throw(_("{0} is already {1}.").format(row.stage_name, row.status.lower()))
	counts = {t: len(v) for t, v in _register(inst).items()}
	expected = int(inst.get("modules_expected") or inst.get("module_count") or 0)
	if expected and (counts["Module"] < expected or not counts["Inverter"]):
		frappe.throw(_("{0} of {1} module serials and {2} inverter serials entered: enter every module's and the inverter's first.").format(
			counts["Module"], expected, counts["Inverter"]), title=_("Serial Numbers Missing"))
	if not sum(counts.values()):
		frappe.throw(_("Enter the serial numbers first."), title=_("Serial Numbers Missing"))
	row.status = "Completed"
	row.actual_completion_date = today()
	row.completed_by = frappe.session.user
	row.external_reference = _("{0} modules, {1} inverters").format(counts["Module"], counts["Inverter"])
	stages._save(inst, _("{0}: {1} serial numbers entered.").format(row.stage_name, sum(counts.values())))
	from a3_sola.api.tasks import notify_task_completed

	notify_task_completed(inst, CODE)
	return state(installation)
