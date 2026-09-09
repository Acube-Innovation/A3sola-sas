# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The document engine.

A single residential job produces, by hand today, a consumer-vendor agreement, a national
portal application, a vendor feasibility report and EHS checklist, a bank covering letter,
three DISCOM annexures, a covering letter to the Assistant Engineer, a net meter request, a
testing checklist, a stamp-paper net metering agreement, a completion report, a second bank
covering letter and a refund request.

Every one of them restates the same twenty facts, and a single transcription error in a
consumer number costs a portal rejection or a payment sent to the wrong account. So there
is ONE context builder: the consumer number on the bank letter and the consumer number on
the DISCOM annexure cannot differ, because they are the same value.

Never scrape, log in to, or automate a government portal. These documents are prepared for
a human to submit.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form, now_datetime

from a3_sola.api.settings import get_value
from a3_sola.solar_crm.doctype.solar_package.solar_package import (
	default_inverter,
	default_module,
)


# --------------------------------------------------------------------- resolution
def resolve_template_set(installation):
	"""Pick the document set by scheme, DISCOM and company."""
	filters = {"is_active": 1, "company": installation.company}
	sets = frappe.get_all(
		"Document Template Set",
		filters=filters,
		fields=["name", "applicable_scheme", "applicable_discom", "is_default"],
	)
	if not sets:
		return None

	def score(row):
		points = 0
		if installation.subsidy_scheme and row.applicable_scheme == installation.subsidy_scheme:
			points += 4
		elif row.applicable_scheme:
			points -= 10
		if installation.discom and row.applicable_discom == installation.discom:
			points += 2
		if row.is_default:
			points += 1
		return points

	best = max(sets, key=score)
	if score(best) < 0:
		best = next((s for s in sets if s.is_default), None)
	return best.name if best else None


# ------------------------------------------------------------------- the context
def get_document_context(installation, template=None, source=None):
	"""Assemble ONE context dict for every template.

	This is the whole point of the engine. A field is resolved once here, so the same
	value reaches every document that prints it. `source` is the task document a template
	is being generated from, when there is one; templates reach it as `task`.
	"""
	inst = (
		frappe.get_doc("Solar Installation", installation)
		if isinstance(installation, str)
		else installation
	)
	consumer = frappe.get_doc("Solar Consumer", inst.solar_consumer)
	company = frappe.get_doc("Company", inst.company)
	settings = frappe.get_cached_doc("A3 Sola Settings")

	estimate = (
		frappe.get_doc("Solar Design Estimate", inst.solar_design_estimate)
		if inst.solar_design_estimate
		else None
	)
	survey = None
	if estimate and estimate.site_survey:
		survey = frappe.get_doc("Site Survey", estimate.site_survey)
	package = frappe.get_doc("Solar Package", inst.solar_package) if inst.solar_package else None
	section = (
		frappe.get_doc("DISCOM Section", inst.discom_section) if inst.discom_section else None
	)
	address = (
		frappe.get_doc("Address", inst.installation_address) if inst.installation_address else None
	)

	loan = None
	if inst.loan_application:
		loan = frappe.get_doc("Loan Application", inst.loan_application)
	commissioning = frappe.db.get_value(
		"Commissioning Report", {"solar_installation": inst.name, "docstatus": 1}, "name"
	)
	commissioning = frappe.get_doc("Commissioning Report", commissioning) if commissioning else None
	agreement = frappe.db.get_value(
		"Solar Agreement", {"solar_installation": inst.name, "docstatus": 1}, "name"
	) or frappe.db.get_value(
		"Solar Agreement", {"solar_installation": inst.name, "docstatus": 0}, "name", order_by="creation desc"
	)
	agreement = frappe.get_doc("Solar Agreement", agreement) if agreement else None
	task = (
		frappe.get_doc(source[0], source[1]) if source and source[0] and source[1] else None
	)
	contractor = None
	if task and task.get("solar_contractor"):
		contractor = frappe.get_doc("Solar Contractor", task.solar_contractor)
	from a3_sola.api.serials import get_completion_report_data

	completion_data = frappe._dict(get_completion_report_data(inst.name))
	# A dispatch notice carries its own serial snapshot: what was actually sent to site.
	if task and task.doctype == "Material Dispatch Notice" and task.get("serials"):
		completion_data.module_serial_numbers = [r.serial_no for r in task.serials if r.component_type == "Module"]
		completion_data.module_count = len(completion_data.module_serial_numbers)
		inverters = [r.serial_no for r in task.serials if r.component_type == "Inverter"]
		completion_data.inverter_serial_number = inverters[0] if inverters else completion_data.inverter_serial_number

	# The module and inverter specs moved off the package onto its option tables. Document
	# templates are data - a tenant may have edited theirs - so `package.module_wattage` and
	# friends are put back on the in-memory copy rather than rewriting everyone's Jinja.
	# Nothing is saved; `package_module` and `package_inverter` are there for new templates.
	package_module = default_module(package) if package else None
	package_inverter = default_inverter(package) if package else None
	if package:
		for field in ("module_specification", "module_make", "module_alternate_makes",
		              "module_wattage", "module_count"):
			package.set(field, package_module.get(field) if package_module else None)
		for source, legacy in (
			("inverter_specification", "inverter_1_specification"),
			("inverter_make", "inverter_1_make"),
			("inverter_capacity_kw", "inverter_1_capacity_kw"),
			("inverter_count", "inverter_1_count"),
		):
			package.set(legacy, package_inverter.get(source) if package_inverter else None)
		package.set("cost_option_1", package_inverter.get("cost") if package_inverter else None)

	code = getattr(template, "template_code", None) if template is not None else None

	def wants(*codes):
		return code is None or code in codes

	from a3_sola.api import billing, materials, om

	return frappe._dict(
		{
			"installation": inst,
			"consumer": consumer,
			"warranty": om.warranty_terms_for(inst),
			"contacts": _support_contacts(inst.company),
			"google_review_url": frappe.db.get_value("Company", inst.company, "google_review_url"),
			"bom_items": materials.bom_lines(inst) if wants("BOM-SUMMARY", "CUST-HANDOVER-PACK") else [],
			"statement": billing.customer_statement(inst) if wants("CUSTOMER-STATEMENT") else None,
			"meter": _meter_details(inst),
			"work_orders": _work_orders(inst),
			"package_module": package_module,
			"package_inverter": package_inverter,
			"company": company,
			"settings": settings,
			"estimate": estimate,
			"survey": survey,
			"package": package,
			"section": section,
			"address": address,
			"loan": loan,
			"commissioning": commissioning,
			"agreement": agreement,
			"task": task,
			"source": task,
			"contractor": contractor,
			"completion_data": completion_data,
			"template": template,
			"today": frappe.utils.formatdate(frappe.utils.today(), "dd-MM-yyyy"),
			"discom_name": frappe.db.get_value("DISCOM", inst.discom, "discom_name") if inst.discom else "",
			"address_text": _address_text(address),
			"serials": serial_rows(inst),
			"module_serials": [r.serial_no for r in inst.serials if r.component_type == "Module"],
			"inverter_serials": [r.serial_no for r in inst.serials if r.component_type == "Inverter"],
			"ehs": ehs_rows(survey),
			"fmt_money": lambda v: frappe.utils.fmt_money(flt(v), currency="INR"),
		}
	)


def _support_contacts(company):
	return frappe.get_all(
		"Company Support Contact",
		filters={"parent": company, "parenttype": "Company"},
		fields=["contact_type", "person_name", "designation", "mobile_no", "email_id", "available_hours", "display_order"],
		order_by="display_order asc, idx asc",
		ignore_permissions=True,
	)


def _meter_details(inst):
	"""The net meter, from the completed meter task."""
	row = frappe.db.get_value(
		"Installation Task",
		{"solar_installation": inst.name, "task_code": "MTR", "docstatus": 1},
		["meter_source", "meter_make", "meter_model", "meter_serial", "meter_received_on"],
		as_dict=True,
	)
	return row or frappe._dict()


def _work_orders(inst):
	return frappe.get_all(
		"Installation Work Order",
		filters={"solar_installation": inst.name, "docstatus": 1},
		fields=["name", "work_order_kind", "work_order_type", "planned_start_date", "actual_end_date", "status", "solar_contractor"],
		order_by="planned_start_date asc, creation asc",
		ignore_permissions=True,
	)


def _address_text(address):
	if not address:
		return ""
	parts = [
		address.address_line1,
		address.address_line2,
		address.city,
		address.state,
		address.pincode,
	]
	return ", ".join(str(p) for p in parts if p)


def serial_rows(installation):
	return [
		{
			"component_type": row.component_type,
			"serial_no": row.serial_no,
			"manufacturer": row.manufacturer,
			"model_number": row.model_number,
			"wattage": row.wattage,
			"dcr_certificate_no": row.dcr_certificate_no,
		}
		for row in installation.serials
	]


def ehs_rows(survey):
	if not survey:
		return []
	return [
		{
			"code": row.question_code,
			"phase": row.phase,
			"question": row.question_text,
			"response": row.response,
			"remarks": row.remarks,
		}
		for row in survey.ehs_checklist
	]


# ------------------------------------------------------------------- generation
@frappe.whitelist()
def generate_document(installation, template_code, force=False, source_doctype=None, source_name=None):
	"""Render one template, attach it and register it. Idempotent - regenerating replaces.

	With a source, the PDF is attached to that task document and the register row on the
	installation names it; without one, it is attached to the installation as before.
	"""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("write")
	source = (source_doctype, source_name) if source_doctype and source_name else None

	template = frappe.db.get_value(
		"Solar Document Template",
		{"template_code": template_code, "company": inst.company},
		"name",
	) or frappe.db.get_value("Solar Document Template", {"template_code": template_code}, "name")
	if not template:
		frappe.throw(_("Document template {0} does not exist.").format(template_code))

	tpl = frappe.get_cached_doc("Solar Document Template", template)
	if not tpl.is_active:
		frappe.throw(_("Document template {0} is not active.").format(tpl.document_name))

	context = get_document_context(inst, tpl, source=source)
	try:
		html = frappe.render_template(tpl.body_template or "", context)
	except Exception as exc:
		frappe.throw(
			_("Template {0} failed to render: {1}").format(tpl.document_name, exc),
			title=_("Template Error"),
		)

	target_doctype, target_name = source or ("Solar Installation", inst.name)
	file_url = _attach(target_doctype, target_name, tpl, html)
	_log_generation(inst, tpl, file_url, target_doctype, target_name)
	# The task that generated the document is the truth about which task it belongs to;
	# the template's own stage code is only the answer when nothing generated it.
	task_code = _task_code_of(context.get("task")) or tpl.stage_code
	register_document(
		inst, task_code, target_doctype, target_name, tpl.document_name, file_url,
		kind="Generated", template=tpl.name, save=False,
	)

	inst.flags.ignore_validate_update_after_submit = True
	inst.save(ignore_permissions=True)
	return {
		"template": tpl.document_name,
		"template_code": tpl.template_code,
		"template_name": tpl.name,
		"template_version": tpl.version,
		"file_url": file_url,
	}


def _task_code_of(doc):
	if doc is None:
		return None
	from a3_sola.api.tasks import code_for

	return code_for(doc)


def _attach(target_doctype, target_name, template, html):
	"""The PDF, attached to the task document that produced it (or the installation).

	Regenerating replaces: the previous file of the same name on the same document goes.
	"""
	from frappe.utils.pdf import get_pdf

	file_name = f"{template.template_code}-{target_name}.pdf"
	for existing in frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": target_doctype,
			"attached_to_name": target_name,
			"file_name": file_name,
		},
		pluck="name",
	):
		frappe.delete_doc("File", existing, ignore_permissions=True, force=True)

	wrapper = f"<div style='font-family:serif;font-size:12px'>{html}</div>"
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": target_doctype,
			"attached_to_name": target_name,
			"is_private": 1,
			"content": get_pdf(wrapper),
		}
	).insert(ignore_permissions=True)
	return file_doc.file_url


def _log_generation(installation, template, file_url, source_doctype=None, source_name=None):
	values = {
		"template_version": template.version,
		"generated_on": now_datetime(),
		"generated_by": frappe.session.user,
		"file": file_url,
		"is_stale": 0,
		"source_doctype": source_doctype,
		"source_document": source_name,
	}
	for row in installation.generated_documents:
		if row.solar_document_template == template.name:
			row.update(values)
			return
	installation.append(
		"generated_documents",
		{
			"solar_document_template": template.name,
			"document_name": template.document_name,
			"status": "Generated",
			**values,
		},
	)


# ------------------------------------------------------------------- the register
#: Attach fields on task documents whose files belong in the installation's register.
#: (fieldname, register document name). Driven from `tasks.sync_from_document`.
REGISTERED_ATTACHMENTS = {
	"Commissioning Report": [
		("commissioning_certificate", "Commissioning certificate"),
		("net_meter_photograph", "Net meter photograph"),
	],
	"Portal Application": [("approval_attachment", "Approval letter")],
	"Statutory Fee Payment": [("receipt", "Payment receipt")],
	"Solar Agreement": [
		("stamp_paper_scan", "Stamp paper scan"),
		("signed_agreement", "Signed agreement"),
		("solar_meter_calibration_certificate", "Meter calibration certificate"),
	],
	"Subsidy Claim": [
		("pcr_acknowledgement", "Portal acknowledgement"),
		("disbursement_proof", "Subsidy credit confirmation"),
		("customer_bank_confirmation", "Customer bank confirmation"),
	],
	"Installation Work Order": [("height_work_permit", "Height work permit")],
	"Installation Task": [
		("certificate", "Completion certificate"),
		("dcr_certificate", "DCR certificate"),
		("signed_checklist", "Signed testing checklist"),
		("meter_test_certificate", "Meter test certificate"),
		("sld_attachment", "Approved single line diagram"),
		("structure_drawing_attachment", "Structure drawing"),
		("bank_advice", "Bank advice"),
	],
	"Customer Review": [("google_review_screenshot", "Google review screenshot")],
}


def register_document(installation, task_code, source_doctype, source_name, document_name, file_url,
                      kind="Uploaded", template=None, reference_no=None, document_date=None, save=True):
	"""Record a file in the installation's document register, naming where it came from.

	The one write path. An Expected row for the task is filled when there is one for this
	document; otherwise a row is appended. Registering the same (source, document) twice
	updates the row rather than adding another, so callers can be careless about repeats.
	"""
	inst = (
		frappe.get_doc("Solar Installation", installation)
		if isinstance(installation, str)
		else installation
	)
	row = _match_register_row(inst, task_code, template, document_name, source_doctype, source_name)
	if row is None:
		row = inst.append(
			"documents",
			{"stage_code": task_code, "document_name": document_name, "is_mandatory": 0},
		)
	row.document_kind = kind
	row.attachment = file_url
	row.source_doctype = source_doctype
	row.source_document = source_name
	if template:
		row.solar_document_template = template
	if reference_no:
		row.document_reference_no = reference_no
	row.document_date = document_date or row.document_date or frappe.utils.today()
	if save:
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
	return row


def _match_register_row(inst, task_code, template, document_name, source_doctype, source_name):
	# the same file registered again by the same document
	for row in inst.documents:
		if row.source_doctype == source_doctype and row.source_document == source_name and (
			(template and row.solar_document_template == template) or row.document_name == document_name
		):
			return row
	# an expectation waiting to be met
	for row in inst.documents:
		if row.attachment or (task_code and row.stage_code and row.stage_code != task_code):
			continue
		if (template and row.solar_document_template == template) or row.document_name == document_name:
			return row
	return None


def unregister_document(installation, source_doctype, source_name, save=True):
	"""A cancelled document takes its files out of the register.

	A row the task template expected goes back to Expected; a row the document added goes.
	"""
	inst = (
		frappe.get_doc("Solar Installation", installation)
		if isinstance(installation, str)
		else installation
	)
	changed = False
	for row in list(inst.documents):
		if not (row.source_doctype == source_doctype and row.source_document == source_name):
			continue
		changed = True
		if row.solar_document_template or row.is_mandatory:
			row.document_kind = "Expected"
			row.attachment = None
			row.source_doctype = None
			row.source_document = None
			row.document_date = None
			row.is_verified = 0
		else:
			inst.remove(row)
	if changed and save:
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
	return changed


def register_attachments(installation, doc, task_code, save=True):
	"""Every file a task document holds, into the register: its declared Attach fields, its
	`uploads` rows and its `generated` rows - whichever of those the doctype has."""
	changed = False
	for fieldname, document_name in REGISTERED_ATTACHMENTS.get(doc.doctype, ()):
		file_url = doc.get(fieldname)
		if not file_url:
			continue
		register_document(
			installation, task_code, doc.doctype, doc.name, document_name, file_url,
			kind="Uploaded", save=False,
		)
		changed = True
	for row in doc.get("uploads") or []:
		if not row.get("attachment"):
			continue
		register_document(
			installation, task_code, doc.doctype, doc.name, row.document_name, row.attachment,
			kind="Uploaded", reference_no=row.get("reference_no"), document_date=row.get("document_date"),
			save=False,
		)
		changed = True
	for row in doc.get("generated") or []:
		if not row.get("file"):
			continue
		register_document(
			installation, task_code, doc.doctype, doc.name, row.document_name, row.file,
			kind="Generated", template=row.get("solar_document_template"), save=False,
		)
		changed = True
	if changed and save:
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
	return changed


def register_print(doc, installation, document_name, task_code, print_format=None, save=True):
	"""Print a document to PDF, attach it to itself and register it on the installation.

	For the ERPNext documents that carry a task - order, purchase order, delivery note -
	whose "generated document" is their own print.
	"""
	pdf = frappe.get_print(doc.doctype, doc.name, print_format, as_pdf=True)
	file_name = f"{doc.name}.pdf"
	for existing in frappe.get_all(
		"File",
		filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "file_name": file_name},
		pluck="name",
	):
		frappe.delete_doc("File", existing, ignore_permissions=True, force=True)
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": pdf,
		}
	).insert(ignore_permissions=True)
	return register_document(
		installation, task_code, doc.doctype, doc.name, document_name, file_doc.file_url,
		kind="Generated", save=save,
	)


#: ERPNext documents that register their own print on submit.
ERPNEXT_PRINTS = {
	"Purchase Order": ("PROC", "Purchase order"),
	"Purchase Receipt": ("PROC", "Purchase receipt"),
	"Delivery Note": ("DISP", "Delivery note"),
}


def register_erpnext_document(doc, method=None):
	"""doc_event: an ERPNext document with a `solar_installation` files its print."""
	spec = ERPNEXT_PRINTS.get(doc.doctype)
	installation = doc.get("solar_installation")
	if not spec or not installation:
		return
	try:
		register_print(doc, installation, spec[1], spec[0])
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: register print {doc.doctype} {doc.name}")


@frappe.whitelist()
def generate_document_pack(installation, stage_code=None):
	"""Generate every due, applicable, active template.

	Failures are reported per document - one bad template must not abort the pack.
	"""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("write")

	set_name = resolve_template_set(inst)
	if not set_name:
		frappe.throw(_("No document template set matches this installation."))

	template_set = frappe.get_cached_doc("Document Template Set", set_name)
	results = []
	for row in sorted(template_set.templates, key=lambda r: (r.display_order or 0, r.idx)):
		tpl = frappe.get_cached_doc("Solar Document Template", row.solar_document_template)
		if not tpl.is_active:
			continue
		if stage_code and tpl.stage_code != stage_code:
			continue
		try:
			outcome = generate_document(inst.name, tpl.template_code)
			results.append({"template": tpl.document_name, "status": "generated", **outcome})
		except Exception as exc:
			frappe.db.rollback()
			results.append({"template": tpl.document_name, "status": "failed", "error": str(exc)})
	return results


# ------------------------------------------------------------------------ stale
#: Source fields whose change invalidates a generated document.
WATCHED_FIELDS = {
	"Solar Consumer": (
		"consumer_name", "consumer_number", "tariff_category", "connection_type",
		"connected_load_watts", "bank_account_no", "bank_ifsc_code", "bank_account_holder_name",
		"installation_address", "local_body_name", "village", "survey_number",
	),
	"Solar Installation": (
		"capacity_kw", "national_portal_application_id", "jan_samarth_id", "loan_sanction_no",
		"spin", "discom_section", "module_make", "module_count", "inverter_make",
	),
	"Company": (
		"registered_vendor_name", "mnre_vendor_registration_no", "epc_name",
		"payee_bank_account_no", "payee_bank_ifsc",
	),
}


def mark_stale_on_change(doc, method=None):
	"""Flag generated documents whose context has changed.

	An edited consumer number must visibly invalidate the letters that carried it - a
	document already issued has left the building.
	"""
	watched = WATCHED_FIELDS.get(doc.doctype)
	if not watched or doc.is_new():
		return
	before = doc.get_doc_before_save()
	if not before:
		return
	if not any(before.get(f) != doc.get(f) for f in watched):
		return

	installations = _installations_for(doc)
	for name in installations:
		count = frappe.db.sql(
			"""update `tabGenerated Document Log`
			   set is_stale = 1
			   where parent = %s and parenttype = 'Solar Installation' and is_stale = 0""",
			(name,),
		)
		frappe.db.set_value(
			"Solar Installation",
			name,
			"stale_document_count",
			frappe.db.count("Generated Document Log", {"parent": name, "is_stale": 1}),
			update_modified=False,
		)


def _installations_for(doc):
	if doc.doctype == "Solar Installation":
		return [doc.name]
	if doc.doctype == "Solar Consumer":
		return frappe.get_all("Solar Installation", filters={"solar_consumer": doc.name}, pluck="name")
	if doc.doctype == "Company":
		return frappe.get_all(
			"Solar Installation", filters={"company": doc.name, "docstatus": ["<", 2]}, pluck="name"
		)
	return []
