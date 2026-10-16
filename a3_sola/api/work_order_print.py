# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""What a work order tells its contractor: the job.

A structure or installation work order goes to a contractor who has never seen the site. It
carries who the customer is and where the site is - the address, the landmark, the map
location - what is being built (capacity, system, roof, panels and inverter), the material
for the work (the procurement task's list), and the pre-installation photographs. The same
facts make the order's Job card on the portal and its PDF, sent by WhatsApp or email.
"""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, today

from a3_sola.api import documents, kyc, material_delivery, purchase_list

STRUCTURE, INSTALLATION = "Structure", "Installation"
#: Which procurement task's list goes with each kind of order.
MATERIAL_TASK = {STRUCTURE: "SPROC", INSTALLATION: "PROC"}
MAX_PHOTOS = 6
PHOTO_TYPES = ("Pre-Installation Photo",)


def url(work_order, download=False):
	return "/api/method/a3_sola.api.work_order_print.pdf?work_order=" + frappe.utils.quote(work_order) + (
		"&download=1" if download else "")


def _photos(inst, kind):
	"""The site as it is before the work: the pre-installation photographs filed on the
	customer, the lead, the survey or the proposal; then the survey's own; for an
	installation, the design images. The newest first, at most MAX_PHOTOS."""
	urls = []

	def add(url_, caption):
		if url_ and url_ not in [u for u, _c in urls]:
			urls.append((url_, caption))

	have = kyc.files_by_type(inst.get("solar_consumer"), inst.get("lead"))
	for kind_ in PHOTO_TYPES:
		for u in reversed(have.get(kind_, [])):
			add(u, _("Pre-installation"))
	for doctype, name in (("Site Survey", inst.get("site_survey")), ("Solar Proposal", inst.get("solar_proposal"))):
		if name:
			for u in frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name,
					"a3s_document_type": ["in", list(PHOTO_TYPES)]}, pluck="file_url", order_by="creation desc"):
				add(u, _("Pre-installation"))
	if inst.get("site_survey"):
		for r in frappe.get_all("Survey Image", filters={"parent": inst.site_survey, "parenttype": "Site Survey"},
				fields=["image", "caption"], order_by="idx asc"):
			add(r.image, r.caption or _("Site survey"))
	if kind == INSTALLATION:
		for r in inst.get("design_images") or []:
			add(r.image, r.caption or _("Design"))
	return [{"url": u, "caption": c} for u, c in urls if frappe.db.exists("File", {"file_url": u})][:MAX_PHOTOS]


SLD = "Approved single line diagram"


def sld_for(inst):
	"""(url, register row) of the job's single line diagram: the Design Freeze's - filed on
	its page, or under the task's documents - else one attached on the old design task."""
	rows = [d for d in inst.get("documents") or [] if d.stage_code == "DSGN" and "single line diagram" in (d.document_name or "").lower()]
	filed = next((d for d in reversed(rows) if d.attachment), None)
	if filed:
		return filed.attachment, filed.name
	old = frappe.db.get_value("Installation Task", {"solar_installation": inst.name, "task_code": "DSGN",
		"sld_attachment": ["is", "set"]}, "sld_attachment", order_by="creation desc")
	return old, rows[0].name if rows else None


def _contractor(name):
	if not name:
		return None
	return frappe.db.get_value("Solar Contractor", name, ["name", "contractor_name", "contractor_type", "contact_person",
		"mobile_no", "email_id", "licence_no", "licence_class"], as_dict=True)


def job_context(installation, kind, work_order=None, contractor=None):
	"""Everything the order tells its contractor, from the job (and the order, once it exists)."""
	inst = frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	order = frappe.get_doc("Installation Work Order", work_order) if isinstance(work_order, str) else work_order
	kind = (order.work_order_kind if order else kind) or INSTALLATION
	from a3_sola.api import contractors

	contractor = contractor or (order.solar_contractor if order else None) or contractors.for_work_order(inst.name, kind)
	name, address, mobile, point = material_delivery.site(inst)
	landmark = frappe.db.get_value("Solar Consumer", inst.solar_consumer, "landmark") if inst.get("solar_consumer") else None
	make = lambda m: frappe.db.get_value("Component Make", m, "make_name") or m if m else ""  # noqa: E731
	material = None
	code = MATERIAL_TASK.get(kind)
	task = frappe.db.get_value("Installation Task", {"solar_installation": inst.name, "task_code": code,
		"docstatus": ["<", 2]}, "name", order_by="creation desc") if code else None
	if task:
		material = purchase_list.lines(frappe.get_doc("Installation Task", task))
	serials = {t: [r.serial_no for r in inst.get("serials") or [] if r.component_type == t and not r.is_replaced]
		for t in ("Module", "Inverter")} if kind == INSTALLATION else {}
	section = frappe.db.get_value("DISCOM Section", inst.discom_section, "section_name") if inst.get("discom_section") else ""
	return frappe._dict({
		"kind": kind,
		"title": _("Work Order - {0}").format(_(kind)),
		"order": {
			"name": order.name if order else "", "status": order.status if order else "",
			"types": ", ".join(r.work_type for r in order.get("work_types") or []) if order else "",
			"start": formatdate(order.planned_start_date, "dd-MM-yyyy") if order and order.planned_start_date else "",
			"end": formatdate(order.planned_end_date, "dd-MM-yyyy") if order and order.planned_end_date else "",
			"description": (order.work_description or "") if order else "",
		},
		"contractor": _contractor(contractor),
		"customer": {"name": name, "mobile": mobile, "consumer_number": inst.get("consumer_number") or "",
			"section": section or "", "address": address, "landmark": landmark or "",
			"point": point, "map_url": documents.maps_link(*point) if point else ""},
		"system": [(label, value) for label, value in (
			(_("Capacity"), "{0:g} kW".format(flt(inst.capacity_kw)) if flt(inst.capacity_kw) else ""),
			(_("System"), inst.get("system_type") or ""),
			(_("Connection"), inst.get("connection_type") or ""),
			(_("Roof"), frappe.db.get_value("Roof Type", inst.roof_type, "roof_type") or inst.roof_type if inst.get("roof_type") else ""),
			(_("Panels"), " · ".join(filter(None, [make(inst.get("module_make")),
				"{0:g} Wp".format(flt(inst.module_wattage)) if flt(inst.get("module_wattage")) else "",
				"× {0}".format(inst.module_count) if inst.get("module_count") else ""]))),
			(_("Inverter"), " · ".join(filter(None, [make(inst.get("inverter_make")),
				"{0:g} kW".format(flt(inst.inverter_capacity_kw)) if flt(inst.get("inverter_capacity_kw")) else ""]))),
			(_("Usable roof area"), "{0:g} sq ft".format(flt(inst.survey_usable_area_sqft)) if kind == STRUCTURE and flt(inst.get("survey_usable_area_sqft")) else ""),
			(_("Structure"), (inst.get("survey_structure_type") or "") if kind == STRUCTURE else ""),
			(_("Package"), frappe.db.get_value("Solar Package", inst.solar_package, "package_name") or inst.solar_package if inst.get("solar_package") else ""),
		) if value],
		"material": material,
		"serials": serials,
		"photos": _photos(inst, kind),
		# The installation is wired to the single line diagram, so it goes with the order.
		"sld": sld_for(inst)[0] if kind == INSTALLATION else None,
		"project": inst.name,
		"company": material_delivery.company_lines(inst.company),
	})


def file_name(doc):
	consumer = frappe.db.get_value("Solar Installation", doc.solar_installation, "consumer_name")
	return "Work Order - {0} - {1}.pdf".format(consumer or doc.solar_installation, doc.name)


def render(doc):
	"""(file name, PDF) of the work order for its contractor."""
	job = job_context(doc.solar_installation, doc.work_order_kind, work_order=doc)
	for photo in job.photos:
		photo["src"] = documents.image_src(photo["url"])
	html = frappe.render_template("a3_sola/templates/print/work_order.html", {
		"job": job, "date": formatdate(today(), "dd-MM-yyyy")})
	pdf = documents.plain_pdf(html)
	if job.sld:
		pdf = _with_sld(pdf, job.sld)
	return file_name(doc), pdf


def _with_sld(pdf, sld_url):
	"""The order with its single line diagram after it: a PDF's pages as they are, an image on
	a page of its own. An SLD that cannot be read leaves the order as it is."""
	from io import BytesIO

	from pypdf import PdfReader, PdfWriter

	name = frappe.db.get_value("File", {"file_url": sld_url}, "name")
	if not name:
		return pdf
	try:
		content = frappe.get_doc("File", name).get_content()
		if isinstance(content, str):
			content = content.encode()
		if not content.startswith(b"%PDF"):
			page = frappe.render_template("a3_sola/templates/print/work_order_sld.html", {"src": documents.image_src(sld_url)})
			content = documents.plain_pdf(page)
		writer = PdfWriter()
		for part in (pdf, content):
			for page in PdfReader(BytesIO(part)).pages:
				writer.add_page(page)
		out = BytesIO()
		writer.write(out)
		return out.getvalue()
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: single line diagram {sld_url} not added to the work order")
		return pdf


@frappe.whitelist()
def pdf(work_order, download=0):
	"""The work order, shown in the browser; saved as a file with `download`."""
	doc = frappe.get_doc("Installation Work Order", work_order)
	doc.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(doc)
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"
