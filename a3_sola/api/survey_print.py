# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Site Survey Report: a site survey as the team's paper form (KSEB / ANERT format) lays
it out, filled from the survey - to have the customer sign, or to keep on file. Nothing is
saved."""

import frappe
from frappe.utils import flt, formatdate

from a3_sola.api import documents


def url(survey, download=False):
	return "/api/method/a3_sola.api.survey_print.pdf?survey=" + frappe.utils.quote(survey) + ("&download=1" if download else "")


def _metres(value):
	return "{0:g} m".format(flt(value)) if flt(value) else ""


def report(doc):
	"""What the paper shows that is not a field of the survey as it stands."""
	roof = (frappe.db.get_value("Roof Type", doc.roof_type, "roof_type") or doc.roof_type) if doc.roof_type else ""
	low = roof.lower()
	user = lambda u: frappe.db.get_value("User", u, "full_name") or u if u else ""  # noqa: E731
	date = lambda d: formatdate(d, "dd-MM-yyyy") if d else ""  # noqa: E731
	return frappe._dict({
		"company": frappe.db.get_value("Company", doc.company, "epc_name") or doc.company or "",
		"date": date(doc.survey_date),
		"district": frappe.db.get_value("Indian District", doc.district, "district_name") or doc.district or "" if doc.get("district") else "",
		"section": frappe.db.get_value("DISCOM Section", doc.discom_section, "section_name") or doc.discom_section or "" if doc.discom_section else "",
		"roof_type": roof,
		"sheet_roof": any(w in low for w in ("sheet", "metal", "tin", "asbestos", "tile")),
		"concrete_roof": any(w in low for w in ("concrete", "rcc", "slab")),
		"supply": [
			("Incomer", doc.incomer or ""),
			("DG availability", "Yes" if doc.dg_available else ("No" if doc.supply_type else "")),
			("Common Panel incomer", doc.common_panel_incomer or ""),
			("Automatic COS", "Yes" if doc.automatic_cos else ("No" if doc.supply_type else "")),
			("Cable Duct/Trench/Tray", doc.cable_duct_trench_tray or ""),
		],
		"surveyor": user(doc.surveyor),
		"engineer": user(doc.engineer_name),
		"engineer_date": date(doc.engineer_approval_date),
		"customer_date": date(doc.customer_approval_date),
		"m": _metres,
	})


def file_name(doc):
	return documents.customer_file_name(doc.customer_name or doc.solar_consumer, "Site Survey Report {0}".format(doc.name))


def render(doc):
	html = frappe.render_template("a3_sola/templates/print/site_survey_report.html", {"s": doc, "r": report(doc)})
	return file_name(doc), documents.plain_pdf(html)


@frappe.whitelist()
def pdf(survey, download=0):
	"""The report, shown in the browser; saved as a file with `download`."""
	doc = frappe.get_doc("Site Survey", survey)
	doc.check_permission("read")
	frappe.local.response.filename, frappe.local.response.filecontent = render(doc)
	frappe.local.response.type = "download" if frappe.utils.cint(download) else "pdf"
