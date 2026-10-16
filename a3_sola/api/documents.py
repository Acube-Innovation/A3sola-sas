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
	# A bank document generated or printed from its loan application reads that application,
	# draft or not - the job only links its loan once the application is submitted.
	if task and task.doctype == "Loan Application":
		loan = task
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
		completion_data.inverter_serial_numbers = inverters or completion_data.inverter_serial_numbers

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
			"discom_short": _initials(frappe.db.get_value("DISCOM", inst.discom, "discom_name") if inst.discom else ""),
			"image_src": image_src,
			"address_text": _address_text(address),
			"party_address": _party_address(address, inst),
			"bank_proposal": bank_proposal(inst, survey, section) if wants("BANK-PROJECT-PROPOSAL") else None,
			"quotation_doc": frappe.get_doc("Quotation", inst.quotation)
			if wants("BANK-QUOTATION") and inst.get("quotation") and frappe.db.exists("Quotation", inst.quotation) else None,
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


def _initials(name):
	"""A DISCOM as its documents name it: "Kerala State Electricity Board" is KSEB."""
	words = [w for w in (name or "").replace("-", " ").split() if w.lower() not in ("of", "and", "the")]
	return "".join(w[0] for w in words).upper() if len(words) > 1 else (name or "")


def image_src(file_url):
	"""An attached image as a data URI, so a PDF carries it whatever the file's privacy and
	without wkhtmltopdf fetching it over HTTP. "" when there is no such file."""
	import base64
	import mimetypes

	if not file_url:
		return ""
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		return ""
	content = frappe.get_doc("File", name).get_content()
	if isinstance(content, str):
		content = content.encode()
	mime = mimetypes.guess_type(file_url)[0] or "image/png"
	return f"data:{mime};base64,{base64.b64encode(content).decode()}"


#: Documents printed on the company letterhead, each a single page as its Word original is.
LETTERHEAD_TEMPLATES = ("BANK-COVERING-LOAN", "BANK-VENDOR-FEASIBILITY")
#: Documents on the letterhead that run on over pages - the band on every page.
LETTERHEAD_FLOW_TEMPLATES = ("BANK-EHS-CHECKLIST", "BANK-PROJECT-PROPOSAL", "BANK-QUOTATION")


def letterhead_flow_pdf(html, company, signed=True):
	"""`html` run on over as many A4 pages as it takes, each on the company letterhead.

	The text is laid out with room left for the letterhead's bands, and each page is then
	put over a copy of the bare letterhead sheet - so the bands are on every page whatever
	the server's wkhtmltopdf can or cannot repeat."""
	from io import BytesIO

	from frappe.utils.pdf import get_pdf
	from pypdf import PdfReader, PdfWriter

	zoom = 1 if _patched_wkhtmltopdf() else 1.3046
	content = get_pdf(f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
	.print-format {{ margin-top: 38mm; margin-bottom: 27mm; margin-left: 17.5mm; margin-right: 20mm; }}
	body {{ margin: 0; zoom: {zoom}; font-family: "Book Antiqua", "Palatino Linotype", Palatino, serif;
		font-size: 11pt; line-height: 1.4; color: #000; }}
	p {{ margin: 0 0 5pt; }}
	table {{ border-collapse: collapse; }}
	thead {{ display: table-header-group; }}
	tr {{ page-break-inside: avoid; }}
	.a3s-page-break {{ page-break-before: always; }}
	{"" if signed else ".a3s-sign { visibility: hidden; }"}
	</style></head><body>{html}</body></html>""")
	sheet = letterhead_pdf([""], company)
	out = PdfWriter()
	for page in PdfReader(BytesIO(content)).pages:
		base = PdfReader(BytesIO(sheet)).pages[0]
		base.merge_page(page)
		out.add_page(base)
	buf = BytesIO()
	out.write(buf)
	return buf.getvalue()


def letterhead_pdf(pages, company, signed=True, letterhead=True, margins=None, letter_head=None):
	"""Each of `pages` (HTML, or one string) as an A4 sheet on the company's letterhead - or,
	with `letterhead=False`, on plain paper inside `margins` (CSS padding, Word's).

	Unsigned, the signature and seal (`.a3s-sign`) are left out but keep their space, to be
	signed and stamped by hand.

	A sheet is drawn whole - the letterhead's header image across the top edge, its footer
	image across the bottom, the text between, in Word's margins - rather than through
	wkhtmltopdf's header and footer, which its unpatched builds cannot draw at all. Those
	builds also lay out at 0.767 of true size, so the sheet is scaled back up there.
	"""
	from frappe.utils.pdf import get_pdf

	if isinstance(pages, str):
		pages = [pages]
	# A named `letter_head` (a document printed on another firm's paper), else the company's.
	head = (letter_head or (frappe.db.get_value("Company", company, "default_letter_head") if company else None)) if letterhead else None
	images = frappe.db.get_value("Letter Head", head, ["image", "footer_image"], as_dict=True) if head else None
	header = image_src(images.image) if images else ""
	footer = image_src(images.footer_image) if images else ""
	sheets = "".join(
		'<div class="a3s-sheet">'
		+ (f'<img class="a3s-sheet__head" src="{header}">' if header else "")
		+ f'<div class="a3s-letter">{page}</div>'
		+ (f'<img class="a3s-sheet__foot" src="{footer}">' if footer else "")
		+ "</div>"
		for page in pages
	)
	zoom = 1 if _patched_wkhtmltopdf() else 1.3046
	# Margins through `.print-format`: get_pdf lets the page's own CSS override its options.
	# WebKit takes fontconfig's fallback for the first family it cannot find, so Book
	# Antiqua is named first only where the server has it.
	html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
	.print-format {{ margin-top: 0mm; margin-bottom: 0mm; margin-left: 0mm; margin-right: 0mm; }}
	body {{ margin: 0; zoom: {zoom}; }}
	.a3s-sheet {{ position: relative; width: 210mm; height: 296.5mm; overflow: hidden; page-break-after: always; }}
	.a3s-sheet:last-child {{ page-break-after: auto; }}
	.a3s-sheet__head {{ position: absolute; top: 0; left: 0; width: 210mm; }}
	.a3s-sheet__foot {{ position: absolute; bottom: 0; left: 0; width: 210mm; }}
	.a3s-letter {{ padding: {margins or (("37mm" if header else "25mm") + " 20mm 0 17.5mm")};
		font-family: "Book Antiqua", "Palatino Linotype", Palatino, serif; font-size: 12pt; line-height: 1.45; color: #000; }}
	.a3s-letter p {{ margin: 0 0 6pt; }}
	.a3s-letter table {{ border-collapse: collapse; }}
	{"" if signed else ".a3s-sign { visibility: hidden; }"}
	</style></head><body>{sheets}</body></html>"""
	return get_pdf(html)


def plain_pdf(html, margins="12mm"):
	"""`html` as A4 pages that flow - a long list runs on, its table head repeated - in
	`margins` (CSS), scaled as letterhead_pdf scales for the server's wkhtmltopdf."""
	from frappe.utils.pdf import get_pdf

	zoom = 1 if _patched_wkhtmltopdf() else 1.3046
	page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
	.print-format {{ margin-top: {margins}; margin-bottom: {margins}; margin-left: {margins}; margin-right: {margins}; }}
	body {{ margin: 0; zoom: {zoom}; font-family: "Book Antiqua", "Palatino Linotype", Palatino, serif; font-size: 10pt; color: #000; }}
	table {{ border-collapse: collapse; width: 100%; }}
	thead {{ display: table-header-group; }}
	tr {{ page-break-inside: avoid; }}
	a {{ color: #0b57d0; }}
	</style></head><body>{html}</body></html>"""
	return get_pdf(page)


def maps_link(lat, lng):
	"""Google Maps directions to a point, or "" without one."""
	from frappe.utils import flt

	if not (flt(lat) or flt(lng)):
		return ""
	return f"https://www.google.com/maps/dir/?api=1&destination={flt(lat, 6)},{flt(lng, 6)}"


def _patched_wkhtmltopdf():
	"""Whether the server's wkhtmltopdf is the patched-Qt build, which lays out at true size."""
	import subprocess

	if not hasattr(_patched_wkhtmltopdf, "result"):
		try:
			out = subprocess.run(["wkhtmltopdf", "-V"], capture_output=True, text=True, timeout=10).stdout
		except Exception:
			out = ""
		_patched_wkhtmltopdf.result = "patched qt" in out.lower()
	return _patched_wkhtmltopdf.result


def bank_proposal(inst, survey, section):
	"""What the bank's project proposal prints about the system, worked out once."""
	from a3_sola.api.portal_fields import link_title

	kw = flt(inst.capacity_kw)
	panel = (inst.get("panels") or [None])[0]
	inverter = (inst.get("inverters") or [None])[0]
	bos = {r.item: r for r in inst.get("bos_items") or []}
	mounting = (inst.get("mounting_expenses") or [None])[0]
	roof = link_title("Roof Type", inst.roof_type) if inst.get("roof_type") else ""
	district = (section.district if section else "") or (frappe.db.get_value("Lead", inst.lead, "city") if inst.get("lead") else "")
	phase = inst.get("connection_type") or ""

	def make(row, field):
		return link_title("Component Make", row.get(field)) if row and row.get(field) else ""

	def bos_row(name, spec, makes):
		r = bos.get(name)
		return {"spec": (r.specification if r and r.specification else spec), "make": (make(r, "make") if r else "") or makes,
			"nos": (("%g" % flt(r.numbers)) if r and flt(r.numbers) else "Ls.")}

	from a3_sola.api.microinverter import uses_microinverter

	micro = uses_microinverter(inst)  # no DCDB with a micro inverter
	area = flt(survey.total_usable_area_sqft) if survey and flt(survey.get("total_usable_area_sqft")) else kw * 50
	return frappe._dict({
		"kw": "%g" % kw, "phase": phase,
		"site": "Residential Building in {0}".format(district.upper()) if district else "Residential Building",
		"tilt": "10 - 12 degrees, South",
		"plant": "Grid Connected Rooftop" if (inst.get("system_type") or "On-Grid") == "On-Grid" else "{0} Rooftop".format(inst.system_type),
		"roof_area": "%d Sq. Ft." % round(area), "roof": roof,
		"generation": "%g - %g units" % (round(kw * 3), round(kw * 4)),
		"components": [
			{"item": "Solar Panels", "spec": "{0:g} Wp {1}".format(flt(panel.panel_capacity_wp), panel.panel_type or "") if panel else "",
			 "make": make(panel, "panel_make"), "nos": "%g" % sum(flt(r.nos) for r in inst.get("panels") or []) if panel else ""},
			{"item": "Solar PV Inverter", "spec": "{0:g}kW {1} On-Grid Inverter and Online Monitoring".format(flt(inverter.inverter_capacity_kw), inverter.inverter_phase or phase) if inverter else "",
			 "make": make(inverter, "inverter_make"), "nos": "%g" % sum(flt(r.nos) for r in inst.get("inverters") or []) if inverter else ""},
			{"item": "DCDB", **({"spec": "Not required for micro inverter", "make": "", "nos": "0"} if micro else
				bos_row("DCDB", "With PV Fuses at input, DC Isolator and Type 2 DC SPD in IP65 rated enclosure", "ABB/Eaton, Mersen"))},
			{"item": "ACDB", **bos_row("ACDB", "With MCB and Type 2 AC SPD in PC/ABS/CRCA IP54 rated enclosure", "ABB/Eaton, Mersen/Citel")},
			{"item": "DC Cables", **bos_row("DC Cable", "UV Rated Solar Copper Cable with E-Beam Cross Linked sheath and insulation", "Apar/ Seichem")},
			{"item": "AC Cables", **bos_row("AC Cable", "Type: PVC/XLPE Aluminium", "Apar/ Polycab")},
			{"item": "Earthing", **bos_row("Earthing", "Maintenance Free Chemical Earthing with 250 microns Copper Bonded Earth Rod of 14 mm dia / 1.2 m long", "Excel Earthing")},
			{"item": "Lightning Protection", **bos_row("Lightning Protection", "Single Spike Air Termination Rod with insulated base and chemical earth kit", "Excel Earthing")},
			{"item": "Solar Energy Meter", **bos_row("Solar Energy Meter", "Type: Watt-hour Meter", "L&T")},
			{"item": "Solar PV Roof Mounting Structure", "spec": (mounting.specification if mounting and mounting.specification else "Epoxy Coated GP Tubes"),
			 "make": make(mounting, "make") or "Apollo/ Equivalent", "nos": "%g kWp" % kw},
			{"item": "Installation, Testing, Commissioning", "spec": "Complying with Electrical Inspectorate & KSEB standards", "make": "", "nos": ""},
		],
	})


def _party_address(address, inst):
	"""Where the consumer lives, as a party to a document names it - house, street, place,
	without state and PIN - from the address record, else the lead's town."""
	if address:
		return ", ".join(p for p in (address.address_line1, address.address_line2, address.city) if p)
	lead = inst.get("lead")
	return (frappe.db.get_value("Lead", lead, "city") or "") if lead else ""


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

	# The bank's loan pair goes on the company letterhead, as the Word originals do.
	if template.get("template_code") in LETTERHEAD_TEMPLATES:
		content = letterhead_pdf(html, template.get("company"))
	elif template.get("template_code") in LETTERHEAD_FLOW_TEMPLATES:
		content = letterhead_flow_pdf(html, template.get("company"))
	else:
		content = get_pdf(f"<div style='font-family:serif;font-size:12px'>{html}</div>")
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": target_doctype,
			"attached_to_name": target_name,
			"is_private": 1,
			"content": content,
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
