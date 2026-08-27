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
def get_document_context(installation, template=None):
	"""Assemble ONE context dict for every template.

	This is the whole point of the engine. A field is resolved once here, so the same
	value reaches every document that prints it.
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
		"Net Metering Agreement", {"solar_installation": inst.name, "docstatus": 1}, "name"
	)
	agreement = frappe.get_doc("Net Metering Agreement", agreement) if agreement else None

	return frappe._dict(
		{
			"installation": inst,
			"consumer": consumer,
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
def generate_document(installation, template_code, force=False):
	"""Render one template, attach it and log it. Idempotent - regenerating replaces."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("write")

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

	context = get_document_context(inst, tpl)
	try:
		html = frappe.render_template(tpl.body_template or "", context)
	except Exception as exc:
		frappe.throw(
			_("Template {0} failed to render: {1}").format(tpl.document_name, exc),
			title=_("Template Error"),
		)

	file_url = _attach(inst, tpl, html)
	_log_generation(inst, tpl, file_url)
	_file_into_checklist(inst, tpl, file_url)

	inst.flags.ignore_validate_update_after_submit = True
	inst.save(ignore_permissions=True)
	return {"template": tpl.document_name, "file_url": file_url}


def _attach(installation, template, html):
	from frappe.utils.pdf import get_pdf

	file_name = f"{template.template_code}-{installation.name}.pdf"
	for existing in frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Solar Installation",
			"attached_to_name": installation.name,
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
			"attached_to_doctype": "Solar Installation",
			"attached_to_name": installation.name,
			"is_private": 1,
			"content": get_pdf(wrapper),
		}
	).insert(ignore_permissions=True)
	return file_doc.file_url


def _log_generation(installation, template, file_url):
	for row in installation.generated_documents:
		if row.solar_document_template == template.name:
			row.update(
				{
					"template_version": template.version,
					"generated_on": now_datetime(),
					"generated_by": frappe.session.user,
					"file": file_url,
					"is_stale": 0,
				}
			)
			return
	installation.append(
		"generated_documents",
		{
			"solar_document_template": template.name,
			"document_name": template.document_name,
			"template_version": template.version,
			"generated_on": now_datetime(),
			"generated_by": frappe.session.user,
			"file": file_url,
			"status": "Generated",
			"is_stale": 0,
		},
	)


def _file_into_checklist(installation, template, file_url):
	"""A generated document satisfies its own checklist row."""
	for row in installation.documents:
		if row.solar_document_template == template.name or row.document_name == template.document_name:
			row.attachment = file_url
			row.document_date = frappe.utils.today()
			return


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
