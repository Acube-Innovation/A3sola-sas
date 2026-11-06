# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The cover page shared by the Solar Proposal and the Quotation print formats.

`print_cover(doc)` (a Jinja method) says what the cover shows for either document: the
title, the scope line naming the kind of plant, who it is for and where, the document's
number and date, and the company's logo and address. The page itself is
templates/includes/print_cover.html.
"""

import frappe
from frappe.utils import cint, flt, getdate

from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import BUILDING_BY_CATEGORY as BUILDING

#: The plant the scope line names, by the estimate's system type.
PLANT = {"On-Grid": "On-Grid", "Off-Grid": "Off-Grid", "Hybrid": "Hybrid"}
#: Shipped with the app, used while neither the company nor the settings has a logo.
DEFAULT_LOGO = "/assets/a3_sola/images/renewcore-logo.png"


# ------------------------------------------------------------------ fonts
#: The print's fonts, shipped in public/fonts/print: (family, file, weight, style). Embedded
#: in the HTML, so a server without Poppins or a Palatino draws the same text at the same
#: size, and no page's text runs into its footer.
PRINT_FONTS = (
	("A3 Print Sans", "Poppins-Regular.ttf", 400, "normal"),
	("A3 Print Sans", "Poppins-Bold.ttf", 700, "normal"),
	("A3 Print Serif", "P052-Roman.otf", 400, "normal"),
	("A3 Print Serif", "P052-Bold.otf", 700, "normal"),
	("A3 Print Serif", "P052-Italic.otf", 400, "italic"),
)
_font_css = None


def print_fonts():
	"""A <style> of @font-face rules carrying the print's fonts as data URIs, since
	wkhtmltopdf may not read local files.

	`src` leads with a local() no machine has: Frappe's get_pdf appends !important to any
	`: url(...)` (frappe.utils.data.URL_NOTATION_PATTERN), data URIs included, and that
	makes the rule invalid. After a local() the url() is not matched, and is the one used."""
	global _font_css
	if _font_css is None:
		import base64
		import os

		folder = frappe.get_app_path("a3_sola", "public", "fonts", "print")
		rules = []
		for family, filename, weight, style in PRINT_FONTS:
			with open(os.path.join(folder, filename), "rb") as f:
				data = base64.b64encode(f.read()).decode()
			kind = "otf" if filename.endswith(".otf") else "ttf"
			rules.append('@font-face {{ font-family: "{0}"; font-weight: {1}; font-style: {2}; '
				'src: local("{0} Embedded"), url(data:font/{3};base64,{4}); }}'.format(family, weight, style, kind, data))
		_font_css = "<style>" + "\n".join(rules) + "</style>"
	return _font_css


def print_cover(doc):
	"""The cover's content for a Solar Proposal or a Quotation."""
	if doc.doctype == "Solar Proposal":
		cover = _proposal(doc)
	else:
		cover = _quotation(doc)
	estimate = cover.pop("estimate", None)
	system = frappe.db.get_value("Solar Design Estimate", estimate, "system_type") if estimate else None
	plant = PLANT.get(system or "", "")
	cover["scope"] = "Design, Supply, Installation, Testing and Commissioning of {0}Solar Power Plant".format(
		plant + " " if plant else "")
	cover["date"] = getdate(cover["date"]).strftime("%d.%m.%Y") if cover.get("date") else ""
	cover["customer"] = " ".join(p for p in (_titled(cover.pop("salutation", None)), cover.get("customer")) if p)
	cover.update(_company(doc.get("company")))
	return cover


def proposal_number(doc, version=None):
	"""RENC/PROP/26-27/351, and _R2 for its second version on: the client's own numbering, as
	the version's file name has it (solar_proposal._version_file_name). `version` numbers an
	earlier version instead of the current one."""
	from a3_sola.api.settings import get_value
	from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import _fiscal_label

	prefix = (get_value("proposal_series_prefix") or "RENC-PROP").replace("-", "/")
	fiscal = _fiscal_label(doc.get("fiscal_year"), get_value("proposal_fiscal_year_format") or "YY-YY")
	number = "/".join(str(p) for p in (prefix, fiscal, doc.proposal_sequence) if p) if doc.get("proposal_sequence") else doc.name
	version = cint(doc.get("current_version")) if version is None else cint(version)
	if version > 1:
		number += "_R{0}".format(version)
	return number


def is_revised(doc):
	"""Whether the proposal is past its first version (current_version is the latest version's number)."""
	return cint(doc.get("current_version")) > 1


def _proposal(doc):
	return {
		"title": "Solar Project Proposal",
		"salutation": doc.get("salutation"),
		"customer": doc.customer_name,
		"place": _place(doc.get("location"), doc.get("district")),
		"number": proposal_number(doc),
		"date": doc.proposal_date,
		"estimate": doc.solar_design_estimate,
	}


def _quotation(doc):
	proposal = frappe.db.get_value("Solar Proposal", doc.get("solar_proposal"),
		["salutation", "location", "district"], as_dict=True) if doc.get("solar_proposal") else None
	place = _place(proposal.location, proposal.district) if proposal else ""
	customer = frappe.db.get_value("Solar Proposal", doc.solar_proposal, "customer_name") if doc.get("solar_proposal") else None
	if not place and doc.get("solar_consumer"):
		con = frappe.db.get_value("Solar Consumer", doc.solar_consumer, ["village", "local_body_name"], as_dict=True)
		place = (con.village or con.local_body_name) if con else ""
	return {
		"title": "Solar Project Quotation",
		"salutation": proposal.salutation if proposal else None,
		"customer": customer or doc.customer_name or doc.party_name,
		"place": place,
		"number": doc.name,
		"date": doc.transaction_date,
		"estimate": doc.get("solar_design_estimate"),
	}


def _titled(salutation):
	"""'Mr' -> 'Mr.', as the client writes it; anything longer is left as it is."""
	salutation = (salutation or "").strip()
	return salutation + "." if salutation and len(salutation) <= 4 and not salutation.endswith(".") else salutation


def _place(location, district):
	"""'Nagapuzha, Thodupuzha': the place, and the district when it says something more."""
	parts = [p for p in (location, district) if p]
	if len(parts) == 2 and parts[1].lower() in parts[0].lower():
		parts = parts[:1]
	return ", ".join(parts)


def _company(company):
	"""The logo and address lines: the company's own, else the settings', else the app's."""
	from a3_sola.api.settings import get_value

	logo = (frappe.db.get_value("Company", company, "company_logo") if company else None) \
		or get_value("brand_logo") or DEFAULT_LOGO
	address = ""
	if company:
		from frappe.contacts.doctype.address.address import get_default_address

		name = get_default_address("Company", company)
		if name:
			a = frappe.db.get_value("Address", name, ["address_line1", "address_line2", "city", "state", "pincode"], as_dict=True)
			first = ", ".join(p for p in (a.address_line1, a.address_line2) if p)
			second = ", ".join(p for p in (a.city, a.state) if p) + (". PIN : {0}".format(a.pincode) if a.pincode else "")
			address = "\n".join(p for p in (first, second) if p)
	if not address:
		address = get_value("office_address") or ""
	return {"logo": logo, "address_lines": [line.strip() for line in address.splitlines() if line.strip()],
		**_letterhead_bands(company)}


def _letterhead_bands(company):
	"""The company letterhead's own header and footer artwork, as data URIs, for the inner
	pages' frame to print in place of the bands it otherwise draws (print_frame.html)."""
	from a3_sola.api.documents import image_src

	head = frappe.db.get_value("Company", company, "default_letter_head") if company else None
	images = frappe.db.get_value("Letter Head", head, ["image", "footer_image"], as_dict=True) if head else None
	return {"header_image": image_src(images.image) if images else "",
		"footer_image": image_src(images.footer_image) if images else ""}


# ------------------------------------------------------------------ page 2: the letter
#: "Dear Madam" for these salutations, "Dear Sir" for the rest that name one.
MADAM = {"mrs", "ms", "miss", "madam", "smt"}

#: The letter's opening, under the salutation and before what is enclosed.
LETTER_OPENING = (
	"We thank you for your interest evinced in renewable energy solutions from us. We are pleased to submit "
	"our proposal for a solar power project aimed at delivering sustainable energy solutions tailored to your "
	"environmental goals.",
	"Our team at Renewcore specializes in end-to-end solar project development, including feasibility studies, "
	"permitting, engineering, procurement, construction, and grid integration.",
	"This proposal outlines a custom-designed solar power system suited to your site requirements and energy "
	"consumption profile. The project is expected to deliver long-term cost savings, reduce carbon emissions, "
	"and increase energy independence\u2014all aligned with your vision for a sustainable future.",
)
#: Its close, after what is enclosed and before the thanks.
LETTER_CLOSING = (
	"We look forward to the opportunity to collaborate and are confident in our ability to bring this project "
	"to life efficiently and professionally.",
	"Please feel free to reach out with any questions or to schedule a follow-up discussion.",
)


#: The revised letter's close, as the client's revised proposal (RENC/PROP/.._R1) ends it.
REVISED_CLOSING = LETTER_CLOSING + ("Thank you for considering our proposal.",)


def print_letter(doc):
	"""The covering letter of a Solar Proposal: one point per design estimate, in the
	table's order (Option 1 first), then one per line of the proposal's Remarks.

	A revised proposal (R1, R2...) has the client's short letter instead (`short`): no
	address block or introduction, the earlier proposal's number and date, each option as
	"With 20kWp Solar Panels and 25kW Inverter.", and the Remarks as paragraphs under them."""
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	base = base_estimate(doc)
	estimates = proposal_estimates(doc, base) if base else []
	revised = is_revised(doc)
	remarks = [line.strip() for line in (doc.get("remarks") or "").splitlines() if line.strip()]
	if revised:
		points = [_short_option_line(e) for e in estimates]
		points = [p for p in points if p]
	else:
		options = [_option_line(e, technology_name) for e in estimates]
		points = [("Option {0}: {1}".format(i, line) if len(options) > 1 else line) for i, line in enumerate(options, 1) if line]
		points += remarks

	salutation = (doc.get("salutation") or "").strip().rstrip(".")
	dear = "Dear Madam," if salutation.lower() in MADAM else ("Dear Sir," if salutation else "Dear Sir/Madam,")
	company = frappe.db.get_value("Company", doc.company, ["company_name", "website", "phone_no", "email",
		"epc_authorised_signatory", "epc_signatory_designation"], as_dict=True) if doc.get("company") else frappe._dict()
	from a3_sola.api.settings import get_value

	website = (company.website or get_value("brand_website") or "").strip()
	letter = {
		"date": getdate(doc.proposal_date).strftime("%d.%m.%Y") if doc.get("proposal_date") else "",
		"to": " ".join(p for p in (_titled(doc.get("salutation")), doc.customer_name) if p),
		"place": _place(doc.get("location"), doc.get("district")),
		"dear": dear,
		"opening": list(LETTER_OPENING),
		"closing": list(LETTER_CLOSING),
		"intro": "Please find enclosed our quotation for the following:" if doc.get("quotation") else
			"Please find enclosed our {0}offer with the following {1}:".format(
				"revised " if revised else "", "options" if len(estimates) > 1 else "details"),
		"points": points,
		"company_name": company.company_name or doc.get("company") or "",
		"signatory": company.epc_authorised_signatory or "",
		"designation": company.epc_signatory_designation or "",
		"website": website.replace("https://", "").replace("http://", "").rstrip("/"),
		"phone": company.phone_no or get_value("sales_phone") or "",
		"email": company.email or get_value("sales_email") or "",
		"short": revised,
		"remarks": remarks if revised else [],
	}
	if revised:
		versions = doc.get("versions") or []
		earlier = versions[-2] if len(versions) > 1 else None
		dated = " dated {0}".format(getdate(earlier.version_date).strftime("%d.%m.%Y")) if earlier and earlier.get("version_date") else ""
		kinds = {r.panel_type for e in estimates for r in e.get("panels") or [] if not r.get("is_option") and r.panel_type}
		system = " for {0} system".format("DCR" if kinds == {"DCR"} else "Non DCR") if len(kinds) == 1 else ""
		letter["opening"] = ["Further to our proposal No. {0}{1}, we hereby submit our revised proposal{2} as below:".format(
			proposal_number(doc, cint(doc.get("current_version")) - 1), dated, system)]
		letter["closing"] = list(REVISED_CLOSING)
	letter.update(_company(doc.get("company")))
	letter["font_pt"] = _letter_pt(letter)
	return letter


def _short_option_line(est):
	"""'With 20kWp Solar Panels and 25kW Inverter.': an option as the revised letter lists it."""
	priced = lambda table: [r for r in est.get(table) or [] if not r.get("is_option")]
	kwp = round(sum(flt(r.get("total_capacity_kwp")) or flt(r.panel_capacity_wp) * cint(r.nos) / 1000 for r in priced("panels")), 2)
	inv_kw = sum(flt(r.inverter_capacity_kw) * (cint(r.nos) or 1) for r in priced("inverters"))
	kwh = sum(flt(r.total_energy_kwh) or flt(r.battery_voltage) * flt(r.battery_capacity_ah) * cint(r.nos) / 1000
		for r in priced("batteries"))
	parts = [p for p in ("{0:g}kWp Solar Panels".format(kwp) if kwp else "", "{0:g}kW Inverter".format(inv_kw) if inv_kw else "",
		"{0:g}kWh Battery".format(round(kwh, 2)) if kwh else "") if p]
	if not parts:
		return ""
	return "With " + (parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]) + "."


#: The letter's type size, in pt: the largest, in quarter points, at which the signature
#: still ends above the page's footer. Every gap in print_letter.html is in em, so the
#: whole letter scales with it. Past the minimum, the remarks are too long for one page.
LETTER_MAX_PT, LETTER_MIN_PT = 12.5, 9.5
#: The text column of the A4 frame (print_frame.html), in pt: its width, and the height
#: from its top to just above the footer's address - less a margin, since justified lines
#: wrap a little more than the average character width counts: at 610 a full letter
#: (RENC-PROP-26-27-RIL-0002) was reckoned to fit and ran its signature into the footer.
LETTER_WIDTH_PT, LETTER_ROOM_PT = 458, 575
#: P052's average character width, in em, with a margin for words that wrap early.
CHAR_EM = 0.46
LINE_HEIGHT = 1.38  # .a3lt .a3l-body


def _letter_pt(letter):
	for quarters in range(int(LETTER_MAX_PT * 4), int(LETTER_MIN_PT * 4), -1):
		if _letter_height(letter, quarters / 4) <= LETTER_ROOM_PT:
			return quarters / 4
	return LETTER_MIN_PT


def _letter_height(letter, pt):
	"""The letter's height, in pt, set at `pt`: its wrapped lines, and the gaps (in em)
	print_letter.html puts after each paragraph."""

	def lines(text, indent_em=0):
		per_line = (LETTER_WIDTH_PT - indent_em * pt) / (pt * CHAR_EM)
		return max(1, -(-len(text or "") // int(per_line)))

	# (text, gap after it in em, indent in em)
	to = letter["to"] + (", " + letter["place"] if letter.get("place") else "")
	short = letter.get("short")
	paras = [(letter["date"], 0.6, 0)] if letter.get("date") else []
	if not short:
		paras += [("To,", 0.3, 0), (to, 1.0, 0)]
	paras += [(letter["dear"], 0.8, 0)]
	paras += [(p, 0.6, 0) for p in letter["opening"][:-1]]
	paras += [(letter["opening"][-1], 0.9, 0)] if letter["opening"] else []  # .a3l-intro's margin
	if not short:
		paras += [(letter["intro"], 0.6, 0)]
	paras += [(p, 0.5, 1.8) for p in letter["points"]]
	if letter["points"]:
		paras[-1] = (paras[-1][0], 0.9, 1.8)  # the list's own margin
	paras += [(p, 0.6, 0) for p in letter.get("remarks") or []]
	paras += [(p, 0.6, 0) for p in letter["closing"][:-1]]
	paras += [(letter["closing"][-1], 0.9, 0)] if letter["closing"] else []  # .a3l-thanks's margin
	if not short:
		paras += [("Thanking you and assuring you of our best attention and services always.", 0.6, 0)]
	paras += [("Thanks & Regards", 0.6, 0), ("For " + letter["company_name"], 2.0, 0)]
	paras += [(p, 0.6, 0) for p in (letter["signatory"], letter["designation"]) if p]
	return pt * sum(lines(text, indent) * LINE_HEIGHT + gap for text, gap, indent in paras)


def _option_line(est, technology_name):
	"""'9.92kWp with 620Wp DCR Solar Panels by Rayzon, 10kW Three Phase String On-Grid Inverter
	by Solinteg and 4 x 48V 100Ah Lithium Battery by ...': the priced rows of each main table."""

	def make(name):
		return frappe.db.get_value("Component Make", name, "make_name") if name else ""

	def priced(table):
		return [r for r in est.get(table) or [] if not r.get("is_option")]

	parts = []
	panels = priced("panels")
	if panels:
		kwp = sum(flt(r.get("total_capacity_kwp")) or flt(r.panel_capacity_wp) * cint(r.nos) / 1000 for r in panels)
		kinds = ["{0:g}Wp {1}Solar Panels{2}".format(flt(r.panel_capacity_wp),
			("DCR " if r.panel_type == "DCR" else "Non DCR ") if r.panel_type else "",
			" by " + make(r.panel_make) if r.panel_make else "") for r in panels]
		parts.append("{0:g}kWp with {1}".format(round(kwp, 2), " and ".join(kinds)))
	for r in priced("inverters"):
		kind = technology_name(r.inverter_type) if r.inverter_type else ""
		noun = "" if "inverter" in (kind or "").lower() else " Inverter"
		parts.append("{0}{1:g}kW {2}{3}{4}{5}".format(
			"{0} x ".format(cint(r.nos)) if cint(r.nos) > 1 else "", flt(r.inverter_capacity_kw),
			(r.inverter_phase + " ") if r.inverter_phase else "", kind, noun,
			" by " + make(r.inverter_make) if r.inverter_make else "").replace("  ", " "))
	for r in priced("batteries"):
		parts.append("{0}{1:g}V {2:g}Ah {3}Battery{4}".format(
			"{0} x ".format(cint(r.nos)) if cint(r.nos) > 1 else "", flt(r.battery_voltage), flt(r.battery_capacity_ah),
			(technology_name(r.battery_variant) + " ") if r.battery_variant else "",
			" by " + make(r.battery_make) if r.battery_make else ""))
	if not parts:
		return ""
	text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
	return text + "."


# ------------------------------------------------------------------ section 3.1: executive summary
#: How the site reads, by the consumer's category, when the estimate names no Building Type:
#: BUILDING (the estimate's own BUILDING_BY_CATEGORY), imported at the top.


def print_summary(doc):
	"""3.1 Executive Summary of a Solar Proposal, from its base design estimate and the records
	before it: the estimate's site survey, the consumer, the lead, the package and the roof type.

	Returns {"rows": [(particular, description)], "missing": [particular]} - a row whose data is
	on no record prints a dash and is named in `missing`.
	"""
	est = base_estimate(doc)
	survey_name = (est.site_survey if est else None) or doc.get("site_survey")
	survey = frappe.get_doc("Site Survey", survey_name) if survey_name and frappe.db.exists("Site Survey", survey_name) else None
	consumer = frappe.db.get_value("Solar Consumer", doc.solar_consumer, ["consumer_category", "roof_type"], as_dict=True) \
		if doc.get("solar_consumer") else None
	lead = frappe.db.get_value("Lead", doc.lead, ["consumer_category", "roof_type"], as_dict=True) if doc.get("lead") else None

	def first(*values):
		return next((v for v in values if v), None)

	priced = lambda table: [r for r in (est.get(table) if est else None) or [] if not r.get("is_option")]
	panels, inverters, batteries = priced("panels"), priced("inverters"), priced("batteries")
	kwp = round(sum(flt(r.get("total_capacity_kwp")) or flt(r.panel_capacity_wp) * cint(r.nos) / 1000 for r in panels), 2)
	roof_type = first(est.roof_type if est else None, survey.roof_type if survey else None,
		consumer.roof_type if consumer else None, lead.roof_type if lead else None)
	roof = frappe.db.get_value("Roof Type", roof_type, ["roof_type", "typical_tilt_degrees", "area_per_kw_sqft"], as_dict=True) \
		if roof_type else None

	rows = []
	category = first(consumer.consumer_category if consumer else None, est.consumer_category if est else None,
		lead.consumer_category if lead else None)
	place = _place(doc.get("location"), doc.get("district"))
	building = (est.get("building_type") if est else None) or BUILDING.get(category or "")
	rows.append(("Site Location", " in ".join(p for p in (building, place) if p)))
	# Every option's plant, as the client writes it: "20 kWp/25kWp, Three Phase".
	sizes = list(dict.fromkeys(_kwp(e) for e in (proposal_estimates(doc, est) if est else []) if _kwp(e))) or ([kwp] if kwp else [])
	capacity = "/".join("{0:g}kWp".format(k) for k in sizes)
	if capacity and est and est.connection_type:
		capacity += ", " + est.connection_type
	rows.append(("Capacity of the Plant Proposed", capacity))
	rows.append(("Tilt & Orientation", _tilt(survey, roof)))
	system = est.system_type if est else None
	rows.append(("Type of Solar Power Plant", "{0} Rooftop".format(SYSTEM_NAMES.get(system, system)) if system else ""))
	area = flt(roof.area_per_kw_sqft) * kwp if roof and flt(roof.area_per_kw_sqft) and kwp else \
		flt(frappe.db.get_value("Solar Package", est.solar_package, "area_required_sqft")) if est and est.solar_package else 0
	rows.append(("Roof Area Required", "{0:,.0f} Sq. Ft.".format(area) if area else ""))
	rows.append(("Type of Roof", roof.roof_type if roof else ""))
	if system in ("Hybrid", "Off-Grid") or batteries:
		inv_kw = sum(flt(r.inverter_capacity_kw) * (cint(r.nos) or 1) for r in inverters)
		three = any((r.inverter_phase or "") == "Three Phase" for r in inverters) or (est and est.connection_type == "Three Phase")
		rows.append(("Total Backup Load Capacity", "{0:g} kW{1}".format(inv_kw, " ({0:g}kW per phase)".format(round(inv_kw / 3, 1)) if three else "")
			if inv_kw else ""))
		kwh = sum(flt(r.total_energy_kwh) or flt(r.battery_voltage) * flt(r.battery_capacity_ah) * cint(r.nos) / 1000 for r in batteries)
		# Hours on battery at the estimate's Backup Load, else at the plant's own rating.
		load = flt(est.get("backup_load_kw")) or kwp
		hours = round(kwh / load, 1) if kwh and load else 0
		rows.append(("Back up Hours", "{0:g} hour{1} for {2:g} kW".format(hours, "" if hours == 1 else "s", load) if hours else ""))
	# The band for the panels proposed, as the estimate works it out for its own capacity:
	# from the smallest option's low to the largest's high.
	if sizes:
		from a3_sola.api.calculations import estimate_daily_generation_band

		section = frappe.db.get_value("Solar Consumer", doc.solar_consumer, "discom_section") if doc.get("solar_consumer") else None
		low = flt(estimate_daily_generation_band(min(sizes), section)["low_units_per_day"])
		high = flt(estimate_daily_generation_band(max(sizes), section)["high_units_per_day"])
	else:
		low, high = (flt(est.expected_daily_units_low), flt(est.expected_daily_units_high)) if est else (0, 0)
	rows.append(("Expected generated per day",
		"{0:.0f} - {1:.0f} units".format(low, high) if low and high else ("{0:.0f} units".format(low or high) if (low or high) else "")))
	layout = image_src_of(est.get("tentative_layout")) if est else ""
	return {"rows": rows, "missing": [p for p, v in rows if not v], "layout": layout, "sections": section_numbers(bool(layout))}


#: The plant's kind as the client's executive summary names it.
SYSTEM_NAMES = {"On-Grid": "Grid Connected"}


def _kwp(est):
	return round(sum(flt(r.get("total_capacity_kwp")) or flt(r.panel_capacity_wp) * cint(r.nos) / 1000
		for r in est.get("panels") or [] if not r.get("is_option")), 2)


def image_src_of(file_url):
	from a3_sola.api.documents import image_src

	return image_src(file_url) if file_url else ""


def section_numbers(layout):
	"""Section 3's numbers: 3.2 is the Tentative Layout when the estimate has one, and every
	later section moves down one."""
	n = 1 if layout else 0
	keys = ("specs", "cost", "terms", "payment", "schedule", "warranty")
	return {key: "3.{0}".format(i + 2 + n) for i, key in enumerate(keys)}


def base_estimate(doc):
	"""The design estimate a proposal-shaped record prints from: its first option's own
	record when the options are worked out in memory (an estimate's unsaved options), else
	its Design Estimate."""
	rows = doc.get("design_estimates") or []
	if rows and rows[0].get("estimate_doc"):
		return rows[0].estimate_doc
	name = doc.get("solar_design_estimate")
	return frappe.get_doc("Solar Design Estimate", name) if name else None


def _tilt(survey, roof):
	"""'10 - 12 degrees, South': the usable roof segments' tilt and facing, else the roof type's tilt."""
	segments = [s for s in (survey.get("roof_segments") if survey else None) or [] if s.get("is_usable") or len(survey.roof_segments) == 1]
	tilts = sorted({flt(s.tilt_degrees) for s in segments if flt(s.tilt_degrees)})
	facing = [s.azimuth for s in segments if s.azimuth]
	facing = max(set(facing), key=facing.count) if facing else ""
	if tilts:
		tilt = "{0:g} - {1:g} degrees".format(tilts[0], tilts[-1]) if len(tilts) > 1 else "{0:g} degrees".format(tilts[0])
	elif roof and flt(roof.typical_tilt_degrees):
		tilt = "{0:g} degrees".format(flt(roof.typical_tilt_degrees))
	else:
		tilt = ""
	return ", ".join(p for p in (tilt, facing) if p)


# ------------------------------------------------------------------ section 3.2: major components
#: Balance-of-system rows as the client's table names them, in its order. The battery sits
#: after the DCDB; the mounting structure and installation close the table.
BOS_ROWS = (("DCDB", "DCDB"), ("ACDB", "ACDB"), ("DC Cable", "DC Cables"), ("AC Cable", "AC Cables"),
	("Earthing", "Earthing"), ("Lightning Protection", "Lightning Protection"), ("Solar Energy Meter", "Solar Energy Meter"))
#: Counted as sets, not pieces; cables are a lump sum.
SETS = ("Earthing", "Lightning Protection")
INSTALLATION_DEFAULT = "Complying with Electrical Inspectorate & KSEB standards"
#: The Component Make type a row's makes are listed from when the row names none.
MAKE_TYPE = {"DCDB": "DCDB", "ACDB": "ACDB", "DC Cable": "Cable", "AC Cable": "Cable", "Earthing": "Earthing",
	"Lightning Protection": "Lightning Protection", "Solar Energy Meter": "Energy Meter", "mounting": "Mounting Structure"}


def proposal_estimates(doc, est):
	"""The design estimates a proposal offers, one per option, in its order - the base `est`
	first when the proposal lists none. Options worked out in memory are their own records."""
	docs = [r.estimate_doc for r in doc.get("design_estimates") or [] if r.get("estimate_doc")]
	if docs:
		return docs
	names = [r.solar_design_estimate for r in doc.get("design_estimates") or [] if r.get("solar_design_estimate")]
	names = list(dict.fromkeys(names)) or [est.name]
	return [est if n == est.name else frappe.get_doc("Solar Design Estimate", n) for n in names
		if n == est.name or frappe.db.exists("Solar Design Estimate", n)]


def print_components(doc):
	"""3.2 Specifications & Quantity of Major Components, from the proposal's base design
	estimate: its priced panel, inverter and battery rows, its balance of system, mounting
	structure and installation - and, where the proposal offers options, each option's inverter.
	Returns {"rows": [...], "missing": [...], "notes": [...]} - each row is {item, spec, make,
	nos}, `missing` names the rows without a make on record, and `notes` explains an asterisk:
	a micro inverter is marked, and its option has no DCDB (api/microinverter.py). A panel,
	inverter or battery row also has its unit's `capacity` (550 Wp, 3 kW, 4.8 kWh) and
	`spec_detail`, its spec without it, for a table with a Capacity column (the BOM tab)."""
	from a3_sola.api import microinverter
	from a3_sola.api.proposal_comparison import unit_capacity
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	est = base_estimate(doc)
	if not est:
		return {"rows": [], "missing": []}

	def make(name):
		return frappe.db.get_value("Component Make", name, "make_name") if name else ""

	def makes_of(kind):
		"""The company's active makes of a component type, 'Apar/ Seichem'."""
		filters = {"component_type": MAKE_TYPE.get(kind), "is_active": 1}
		if doc.get("company") and frappe.get_meta("Component Make").has_field("company"):
			filters["company"] = doc.company
		names = frappe.get_all("Component Make", filters=filters, pluck="make_name", order_by="make_name asc") if MAKE_TYPE.get(kind) else []
		return "/ ".join(dict.fromkeys(names))

	def priced(table):
		return [r for r in est.get(table) or [] if not r.get("is_option")]

	alternates = {r.module_make: r.module_alternate_makes for r in frappe.get_all("Solar Package Module",
		filters={"parent": est.solar_package}, fields=["module_make", "module_alternate_makes"])} if est.solar_package else {}
	rows = []
	for r in priced("panels"):
		detail = " ".join(p for p in (technology_name(r.panel_variant) if r.panel_variant else "",
			("DCR" if r.panel_type == "DCR" else "Non DCR") if r.panel_type else "") if p)
		spec = " ".join(p for p in ("{0:g}Wp".format(flt(r.panel_capacity_wp)) if flt(r.panel_capacity_wp) else "", detail) if p)
		names = [make(r.panel_make)] + [m.strip() for m in (alternates.get(r.panel_make) or "").split("/")
			if m.strip() and m.strip().lower() not in ("equivalent", make(r.panel_make).lower())]
		rows.append({"item": "Solar Panels", "spec": spec, "spec_detail": detail, "capacity": unit_capacity("panels", r),
			"make": "/ ".join(n for n in names if n), "nos": cint(r.nos)})
	hybrid = est.system_type == "Hybrid"
	# Each option's inverter - the options differ by inverter - or the one design's.
	options = proposal_estimates(doc, est)
	micro = [microinverter.uses_microinverter(e) for e in options]
	for number, option in enumerate(options, 1):
		for r in option.get("inverters") or []:
			if r.get("is_option"):
				continue
			phase = {"Three Phase": "3 phase", "Single Phase": "1 phase"}.get(r.inverter_phase or "", r.inverter_phase or "")
			kind = (r.get("specification") or "").strip() or (technology_name(r.inverter_type) if r.inverter_type else "")
			kw = "{0:g} kW".format(flt(r.inverter_capacity_kw)) if flt(r.inverter_capacity_kw) else ""
			spec, detail = (", ".join(p for p in parts if p) for parts in ((kw, phase, kind), (phase, kind)))
			if len(options) > 1:
				spec, detail = ("Option {0}: {1}".format(number, text) for text in (spec, detail))
			if microinverter.is_micro(r):
				spec, detail = spec + " *", detail + " *"
			rows.append({"item": "Solar PV Hybrid Inverter" if hybrid else "Solar PV Inverter", "spec": spec,
				"spec_detail": detail, "capacity": unit_capacity("inverters", r), "make": make(r.inverter_make), "nos": cint(r.nos)})
	# The options' inverters are one item: one Sl. No. and description over their rows.
	group = [r for r in rows if r["item"] in ("Solar PV Inverter", "Solar PV Hybrid Inverter")]
	if len(group) > 1:
		group[0]["span"] = len(group)
		for r in group[1:]:
			r["spanned"] = True

	bos = {}
	for r in est.get("bos_items") or []:
		bos.setdefault(r.item, []).append(r)

	def bos_row(item, label):
		for r in bos.get(item, []):
			spec = r.specification or ""
			if item == "Solar Energy Meter" and r.phase:
				spec = "{0} {1}".format(r.phase, spec).strip()
			count = flt(r.numbers)
			if "Cable" in item:
				nos = "Ls."
			elif item in SETS:
				nos = "{0:g} Set{1}".format(count, "" if count == 1 else "s") if count else ""
			elif item == "DCDB" and any(micro):
				# None with a micro inverter: "0*" when every option has one, else "1 (0*)".
				nos = "0*" if all(micro) else "{0} (0*)".format(dcdb_count(options, micro) or "1")
			else:
				nos = "{0:g}".format(count) if count else ""
			by_part = [line.strip() for line in (r.get("component_makes") or "").splitlines() if line.strip()]
			rows.append({"item": label, "spec": spec, "make": "\n".join(by_part) or make(r.make) or makes_of(item), "nos": nos})

	bos_row("DCDB", "DCDB")
	for r in priced("batteries"):
		described = (r.get("specification") or "").strip()
		# Volts and amp-hours as far as they are known: never "0V, 0Ah".
		rating = ", ".join(p for p in ("{0:g}V".format(flt(r.battery_voltage)) if flt(r.battery_voltage) else "",
			"{0:g}Ah".format(flt(r.battery_capacity_ah)) if flt(r.battery_capacity_ah) else "") if p)
		spec = " ".join(p for p in (rating,
			described or " ".join(p for p in (technology_name(r.battery_variant) if r.battery_variant else "", "Battery") if p)) if p)
		rows.append({"item": "Battery", "spec": spec, "spec_detail": spec, "capacity": unit_capacity("batteries", r),
			"make": make(r.battery_make), "nos": cint(r.nos)})
	for item, label in BOS_ROWS[1:]:
		bos_row(item, label)
	known = {item for item, _label in BOS_ROWS}
	for item in bos:
		if item not in known:
			bos_row(item, item)
	for r in est.get("mounting_expenses") or []:
		rows.append({"item": r.item or "Solar PV Roof Mounting Structure", "spec": r.specification or "",
			"make": make(r.make) or makes_of("mounting"), "nos": "{0:g}kWp".format(flt(r.capacity_kw)) if flt(r.capacity_kw) else ""})
	for r in est.get("installation_expenses") or []:
		rows.append({"item": r.item or "Installation, Testing, Commissioning", "spec": r.specification or INSTALLATION_DEFAULT,
			"make": None, "nos": "Set."})
	return {"rows": rows, "missing": [r["item"] for r in rows if r["make"] == ""],
		"notes": [microinverter.NOTE] if any(micro) else []}


def dcdb_count(options, micro):
	"""The DCDB count of the string-inverter options, '1' - what the DCDB row says beside the 0*."""
	counts = {flt(r.numbers) for e, m in zip(options, micro) if not m for r in e.get("bos_items") or [] if r.item == "DCDB"}
	return "/".join("{0:g}".format(c) for c in sorted(counts) if c)


# ------------------------------------------------------------------ sections 3.3 to 6
#: The estimate's own tables that make up the plant's price (KSEB and linked charges apart).
# The package line is the package at its price; the rest price only what is added to it.
PLANT_LINES = ("package", "panels", "inverters", "batteries", "bos_items", "mounting_expenses", "installation_expenses")
#: Charges raised against the estimate in records of their own: (doctype, sign).
CHARGES = (("Additional Structure", 1), ("Additional Cable", 1), ("Special Discount", -1))
#: How a charge line is named on the proposal and the quotation, where its type is not what the
#: customer is told: an elevated structure is charged as the additional cost for the structure.
PRINTED_AS = {"Elevated Structure": "Additional Cost for Structure"}
#: The client's payment terms. Nothing on file holds them yet, so they are printed as standing.
PAYMENT_TERMS = (
	"70% as advance with PO.",
	"20% after delivery and installation.",
	"10% after commissioning of system.",
)
#: The PV modules' output guarantee the client prints under their performance warranty.
MODULE_OUTPUT_WARRANTY = ("The PV Modules shall be warranted for output wattage, which should not be less than 90% "
	"at the end of 12 years and 80% at the end of {0} years.")
#: 5. Way Forward, as the client's document has it, and who it names to reach.
WAY_FORWARD = (
	"The proposed solar power plant represents a sustainable, cost-effective, and environmentally friendly solution "
	"to meet growing energy demands while reducing carbon emissions. By harnessing the abundant solar energy resource, "
	"this project aligns with global efforts to combat climate change and transition to renewable energy sources.",
	"We are confident that this project will not only contribute to energy independence but also create economic "
	"opportunities and promote sustainable development.",
	"Should you require any further details or clarifications, please do not hesitate to contact us. We would be "
	"delighted to address any questions or provide additional information to support your decision-making process.",
	"Please feel free to reach out to us:",
)
#: (name, designation, phone) - the company's authorised signatory, if set, takes the first.
CONTACTS = (("Nevil Jose", "Managing Partner", "+91 8891024312"), ("Shiju N K", "Strategic Partner", "+91 9895778516"))


def print_rest(doc):
	"""Sections 3.3/3.4 to 5 of a Solar Proposal print: the solar power plant cost and KSEBL
	expenses, the terms, payment and bank details, the schedule, the warranty, the scope of
	work and the way forward. All from the base design estimate, the records it links to,
	the Company and A3 Sola Settings."""
	from frappe.utils import fmt_money, money_in_words

	from a3_sola.api.settings import get_settings

	settings = get_settings()
	est = base_estimate(doc)
	company = frappe.get_doc("Company", doc.company) if doc.get("company") else frappe._dict()
	money = lambda v: fmt_money(flt(v), precision=0)  # 7,76,000 - the client prints whole rupees
	empty = {"label": "", "rows": []}
	out = {"cost": [], "cost_options": [empty], "cost_pages": [{"options": [empty], "kseb": True}], "add_ons": [], "kseb": [], "kseb_total": 0, "kseb_words": "", "kseb_note": "", "terms_html": "",
		"validity": "", "payment_terms": list(PAYMENT_TERMS), "bank": [], "bank_credentials": [], "payment_qr": "",
		"schedule_html": settings.get("delivery_schedule_text") or "",
		"warranty": [], "scope": {"company": [], "customer": []}, "way_forward": list(WAY_FORWARD), "contacts": _contacts(company),
		"company_scope_label": "", "customer_scope_label": "", "system_type": "",
		"sections": section_numbers(bool(est and est.get("tentative_layout"))), "flow": []}
	if not est:
		return out

	out["system_type"] = est.system_type or ""

	# Solar Power Plant Cost: every option of the proposal, in its order - Option 1 is the
	# base - each with its plant, its linked charges, GST, the total and the price after
	# discount. A quotation is one option, and prints what it charges.
	q = doc.get("quotation")
	if q:
		rows = [{"item": frappe.utils.strip_html(r.description or r.item_name or ""), "amount": flt(r.amount)} for r in q.items]
		rows.append({"item": "Total", "amount": flt(q.total), "right": True, "bold": True})
		if flt(q.discount_amount):
			rows.append({"item": "Special Price after Discount", "amount": flt(q.net_total), "right": True, "bold": True})
		for t in q.taxes:
			if flt(t.tax_amount):
				rows.append({"item": t.description, "amount": flt(t.tax_amount), "right": True})
		if q.taxes:
			rows.append({"item": "Grand Total", "amount": flt(q.rounded_total or q.grand_total), "right": True, "bold": True})
		options = [{"label": "", "rows": rows}]
	else:
		estimates = proposal_estimates(doc, est)
		options = [{"label": _option_label(e, i) if len(estimates) > 1 else "", "rows": plant_cost_rows(e)}
			for i, e in enumerate(estimates, 1)]
	for option in options:
		for r in option["rows"]:
			r["amount_text"] = money(r["amount"])
	out["cost"] = options[0]["rows"]
	out["cost_options"] = options

	# KSEBL expenses, as the fee schedule resolved them for the estimate - each fee, no total,
	# as the client's table lists them.
	import json

	statutory = json.loads(est.statutory_breakdown) if est.statutory_breakdown else {}
	labels = {"KSEB Application Fee": "Application Fee", "Solar Plant Registration Fee": "Registration Fee",
		"Bi-directional (Net) Meter": "Bi-Directional Meter (Net Meter)"}
	purchased = (est.net_meter_mode or "") == "Purchased by Customer"
	kseb = [{"item": labels.get(r.get("item"), r.get("item")) + (" *" if "Meter" in (r.get("item") or "") and purchased else ""),
		"amount_text": money(r.get("amount"))} for r in statutory.get("breakdown") or [] if flt(r.get("amount"))]
	out["kseb"] = kseb
	out["kseb_total"] = money(statutory.get("statutory_total"))
	if flt(statutory.get("statutory_total")):
		words = money_in_words(flt(statutory["statutory_total"]), "INR")
		# "Rupees Twenty Two Thousand Nine Hundred Eighty Only", as the client writes it.
		words = words.replace("INR", "Rupees", 1).replace("Rupees Rupees", "Rupees").replace(",", "").replace(" And ", " ")
		out["kseb_words"] = words.rstrip(".").replace(" only", " Only")
	if purchased:
		out["kseb_note"] = "*Bi-directional meter can be availed from KSEBL on rental basis also."
	# What the packages offer beside their price - for information, in no total.
	out["add_ons"] = add_on_rows(proposal_estimates(doc, est))
	out["cost_pages"] = cost_pages(out["cost_options"], len(kseb), bool(out["kseb_note"]), len(out["add_ons"]))

	# The terms and offer validity; the payment terms and the bank details from the Company.
	out["terms_html"] = settings.get("terms_and_conditions_text") or ""
	if cint(settings.get("offer_validity_days")) and "validity" not in out["terms_html"].lower():
		out["validity"] = "Offer Validity: {0} days from the date of offer.".format(cint(settings.offer_validity_days))
	out["bank"] = [
		("Registered name of the Company", company.get("payee_legal_name") or company.get("company_name") or ""),
		("PAN", company.get("payee_pan") or company.get("pan") or ""),
		("GST", company.get("payee_gstin") or company.get("gstin") or settings.get("company_gstin") or ""),
	]
	out["bank_credentials"] = [("Bank", company.get("payee_bank_name") or ""), ("A/c No.", company.get("payee_bank_account_no") or ""),
		("Branch", company.get("payee_bank_branch") or ""), ("IFS Code", company.get("payee_bank_ifsc") or "")]
	# The company's payment QR (Company > Payee Bank > Payment QR Code): a column of its own
	# beside the bank details, for the customer to scan and pay. Carried in the page, as the
	# logo and layout are, so the PDF shows it even when the file was uploaded private.
	qr = company.get("payment_qr_code") or ""
	out["payment_qr"] = (image_src_of(qr) or qr) if qr else ""

	# Warranty, as the client numbers it: the package's system warranty, the modules' performance
	# warranty, then each option's inverter (and battery) by make and size.
	out["warranty_items"] = warranty_items(est, proposal_estimates(doc, est))
	out["warranty"] = [w["text"] + "".join(" " + s for s in w["sub"]) for w in out["warranty_items"]]

	# 4 scope of work, from Settings, by responsibility.
	for r in sorted(settings.get("scope_of_work") or [], key=lambda r: (cint(r.display_order), r.idx)):
		side = "company" if r.responsibility == "Company" else "customer"
		out["scope"][side].append({"category": r.category, "text": r.scope_text})
	short = (company.get("company_name") or "").split(" ")[0]
	out["company_scope_label"] = "{0} Scope".format(short) if short else (settings.get("company_scope_label") or "Our Scope")
	out["customer_scope_label"] = settings.get("customer_scope_label") or "Client's Scope"
	out["flow"] = flow_pages(out)
	return out


def _contacts(company):
	"""5. Way Forward's contacts: CONTACTS, the first named as the company's authorised signatory."""
	contacts = [list(c) for c in CONTACTS]
	if company.get("epc_authorised_signatory"):
		contacts[0][0] = company.epc_authorised_signatory
		contacts[0][1] = company.get("epc_signatory_designation") or contacts[0][1]
	return [tuple(c) for c in contacts]


def warranty_items(est, estimates):
	"""[{"text", "sub": [...]}]: the system warranty, the modules', and "Inverter Warranty" with
	one line per option's inverter ("Solinteg 25kW - 10 years"), the battery likewise."""

	def make_doc(name):
		return frappe.get_cached_doc("Component Make", name) if name and frappe.db.exists("Component Make", name) else None

	items = []
	years = cint(frappe.db.get_value("Solar Package", est.solar_package, "warranty_years")) if est.solar_package else 0
	if years:
		items.append({"text": "System Warranty shall be for {0} years from the date of Commissioning.".format(years), "sub": []})
	priced = lambda e, table: [r for r in e.get(table) or [] if not r.get("is_option")]
	seen = set()
	for e in estimates:
		for r in priced(e, "panels"):
			m = make_doc(r.panel_make)
			if not m or m.name in seen or not cint(m.performance_warranty_years):
				continue
			seen.add(m.name)
			n = cint(m.performance_warranty_years)
			items.append({"text": "Solar PV Modules will have performance warranty of {0} years. {1}".format(n,
				MODULE_OUTPUT_WARRANTY.format(n)), "sub": []})
	for label, table, field, size in (("Inverter", "inverters", "inverter_make", "inverter_capacity_kw"),
			("Battery", "batteries", "battery_make", None)):
		lines = []
		for e in estimates:
			for r in priced(e, table):
				m = make_doc(r.get(field))
				if not m:
					continue
				# An inverter on a price-list model carries that model's warranty, not the make's.
				model = r.get("inverter_model") if table == "inverters" else None
				years_ = cint(frappe.db.get_value("Inverter Model", model, "warranty_years")) if model else cint(m.product_warranty_years)
				if not years_:
					continue
				name = " ".join(p for p in (m.make_name, "{0:g}kW".format(flt(r.get(size))) if size and flt(r.get(size)) else "") if p)
				line = "{0} - {1} years".format(name, years_)
				if line not in lines:
					lines.append(line)
		if lines:
			items.append({"text": "{0} Warranty".format(label), "sub": lines})
	return items


def plant_cost_rows(est):
	"""One option's 3.3.1 rows: the plant, each linked charge's lines, GST, the total and the
	price after discount."""
	commercials = est.commercials()
	lines = {line["key"]: flt(line["amount"]) for line in commercials["lines"]}
	rows = [{"item": plant_description(est), "amount": sum(lines.get(k, 0) for k in PLANT_LINES)}]
	discount = 0.0
	for doctype, sign in CHARGES:
		for name in frappe.get_all(doctype, filters={"solar_design_estimate": est.name, "docstatus": ["<", 2]}, pluck="name"):
			for item in frappe.get_doc(doctype, name).items:
				if sign < 0:
					discount += flt(item.amount)
				else:
					label = item.description or item.get("structure_type") or item.get("cable_type") or doctype
					rows.append({"item": PRINTED_AS.get(label.strip(), label), "amount": flt(item.amount), "right": True})
	if flt(commercials.get("gst_amount")):
		rows.append({"item": "GST @ {0:g}%".format(flt(commercials["gst_percent"])), "amount": flt(commercials["gst_amount"]), "right": True})
	total = sum(r["amount"] for r in rows)
	rows.append({"item": "Total", "amount": total, "right": True, "bold": True})
	if discount:
		rows.append({"item": "Special Price after Discount", "amount": total - discount, "right": True, "bold": True})
	return rows


def _option_label(est, number):
	"""'Option 2 – 25kWp with 30kW Inverter': the option as the client heads its cost table."""
	kwp = _kwp(est)
	inv_kw = sum(flt(r.inverter_capacity_kw) * (cint(r.nos) or 1) for r in est.get("inverters") or [] if not r.get("is_option"))
	label = " with ".join(p for p in ("{0:g}kWp".format(kwp) if kwp else "", "{0:g}kW Inverter".format(inv_kw) if inv_kw else "") if p)
	return "Option {0}{1}".format(number, " – " + label if label else "")


#: How much of a printed page section 3.3 may fill, and what each block takes, in mm. The
#: page is a fixed A4 frame that clips what overflows, so the options are laid out page by
#: page here rather than left to run on. Measured on the Solar Proposal Document print.
PAGE_MM = 200
HEADINGS_MM = 18   # 3.3 Project Cost and 3.3.1 Solar Power Plant
CONTINUED_MM = 10  # 3.3.1 (continued)
OPTION_MM = 22     # the option's label, the table's header and its gap
LINE_MM = 7        # one printed line of a row


def _rows_mm(rows):
	# The plant's description runs to about 85 characters a line in its column.
	return sum(LINE_MM * max(1, -(-len(r["item"]) // 85)) + 2 for r in rows)


def cost_pages(options, kseb_rows, kseb_note, add_on_rows=0):
	"""Section 3.3 as pages: [{"options": [...], "kseb": bool, "add_ons": bool}]. Options fill
	a page in order; the KSEBL expenses follow the last of them, on its page when they fit,
	else on the next; the optional add-ons follow the KSEBL expenses the same way."""
	kseb_mm = 14 + 12 + (kseb_rows + 2) * (LINE_MM + 2) + (12 if kseb_note else 0)
	add_ons_mm = 14 + 12 + add_on_rows * (LINE_MM + 2) if add_on_rows else 0
	pages, current, used = [], [], HEADINGS_MM
	for option in options:
		need = (OPTION_MM if option["label"] else 12) + _rows_mm(option["rows"])
		if current and used + need > PAGE_MM:
			pages.append({"options": current, "kseb": False, "add_ons": False})
			current, used = [], CONTINUED_MM
		current.append(option)
		used += need
	if used + kseb_mm > PAGE_MM:
		pages.append({"options": current, "kseb": False, "add_ons": False})
		current, used = [], 0
	used += kseb_mm
	if add_ons_mm and used + add_ons_mm > PAGE_MM:
		pages.append({"options": current, "kseb": True, "add_ons": False})
		pages.append({"options": [], "kseb": False, "add_ons": True})
		return pages
	pages.append({"options": current, "kseb": True, "add_ons": bool(add_ons_mm)})
	return pages


#: 3.2's table, as print_summary.html sets it, measured on the print: the height its
#: frame's column has, in pt; a row's padding and border; each column's width and type
#: size (its text room is the width less the padding); and 3.1's line, at 15pt.
COMPONENTS_ROOM_PT = 615
COMPONENTS_LINE = 1.3
ROW_PAD_PT = 9
COMPONENTS_COLS = {"item": (94, 12), "spec": (169, 14), "make": (99, 13), "nos": (75, 14)}
SUMMARY_COLS = ((221, 15), (188, 15))  # 3.1's Particulars and Description
SUMMARY_LINE_PT = 21


def _cell_lines(text, width_pt, size_pt):
	"""The lines `text` wraps to in a cell, broken between words as the print breaks them."""
	import textwrap

	per_line = max(1, int((width_pt - 12) / (size_pt * 0.5)))
	return sum(len(textwrap.wrap(part, per_line)) or 1 for part in str(text or "—").split("\n"))


def _component_pt(row):
	"""One row of 3.2's table, in pt: its tallest cell, and the cell's padding."""
	cells = [("spec", row.get("spec")), ("make", row.get("make")), ("nos", row.get("nos"))]
	if row.get("make") is None:  # the spec spans the make's column too
		cells = [("spec", row.get("spec")), ("nos", row.get("nos"))]
	tallest = max(_cell_lines(text, *COMPONENTS_COLS[col]) * COMPONENTS_COLS[col][1] for col, text in cells)
	return tallest * COMPONENTS_LINE + ROW_PAD_PT


def component_pages(summary, components):
	"""3.2 laid out page by page, as the frame clips what runs past its footer:
	{"under_summary", "pages": [{"rows", "start"}]}. The first page has what fits under
	3.1 (`under_summary`; else 3.2 starts on the next page), each next page what fits on a
	page. A group of spanned rows is never split, and the notes follow the last row.
	`start` is the Sl. No. the page's first row takes."""
	rows = components.get("rows") or []
	if not rows:
		return {"under_summary": True, "pages": []}
	# Groups: a row with `span` and the `spanned` rows after it, as one block.
	groups = []
	for r in rows:
		if r.get("spanned") and groups:
			groups[-1].append(r)
		else:
			groups.append([r])

	def group_pt(group):
		head = group[0]
		item = _cell_lines(head.get("item"), *COMPONENTS_COLS["item"]) * COMPONENTS_COLS["item"][1] * COMPONENTS_LINE + ROW_PAD_PT
		return max(item, sum(_component_pt(r) for r in group))

	summary_pt = 62 + 28 + sum(  # 3. and 3.1's headings, the table's header
		max(_cell_lines(p, *SUMMARY_COLS[0]), _cell_lines(d, *SUMMARY_COLS[1])) * SUMMARY_LINE_PT + ROW_PAD_PT
		for p, d in summary.get("rows") or [])
	if summary.get("layout"):
		# The Tentative Layout fills the rest of 3.1's page: the components start the next.
		summary_pt = COMPONENTS_ROOM_PT
	notes_pt = sum(_cell_lines(n, 482, 12) * 12 * 1.3 + 6 for n in components.get("notes") or [])
	table_head_pt = 46 + 46  # 3.2's heading and its gap, the two-line header row

	pages, used = [[]], summary_pt + table_head_pt
	for i, group in enumerate(groups):
		need = group_pt(group) + (notes_pt if i == len(groups) - 1 else 0)
		if used + need > COMPONENTS_ROOM_PT:
			if pages[-1]:
				pages.append([])
				used = 0
			elif len(pages) == 1:  # 3.1 leaves no room: 3.2, heading and all, starts the next page
				pages.append([])
				used = table_head_pt - 20  # no gap above the heading
		pages[-1].extend(group)
		used += need
	under_summary = bool(pages[0])
	out, start = [], 1
	for page_rows in pages[0 if under_summary else 1:]:
		out.append({"rows": page_rows, "start": start})
		start += sum(1 for r in page_rows if not r.get("spanned"))
	return {"under_summary": under_summary, "pages": out}


#: The pages after the cost hold the terms, the payment terms and bank details, the schedule,
#: the warranty, the scope of work and the way forward one after another, as many to a page
#: as fit, in printed lines of the page's column (print_rest.html, 12.5pt). A section is not
#: split: one that does not fit starts the next page.
TERMS_PAGE_LINES = 38
TERMS_LINE_CHARS = 78  # a bulleted line of the column
#: The scope of work is two sections here, as the client's document breaks it over a page.
FLOW = ("terms", "payment", "schedule", "warranty", "scope_company", "scope_customer", "way_forward")


def flow_pages(rest):
	"""[[section, ...], ...]: FLOW's sections laid out page by page by their printed lines."""
	import re

	from frappe.utils import strip_html

	def lines(text, chars=TERMS_LINE_CHARS):
		return max(1, -(-len(text or "") // chars)) + 0.25  # the item's gap

	def html_lines(html):
		return sum(lines(b) for b in (strip_html(b).strip() for b in re.split(r"</li>|</p>|<br\s*/?>", html or "")) if b)

	bank_rows = len(rest.get("bank") or []) + len(rest.get("bank_credentials") or [])
	scope = rest.get("scope") or {}
	need = {
		"terms": 2 + html_lines(rest.get("terms_html")) + (lines(rest["validity"]) if rest.get("validity") else 0),
		"payment": 2 + sum(lines(t) for t in rest.get("payment_terms") or [])
			+ 1.5 + max(bank_rows * 1.4 + 1, 11 if rest.get("payment_qr") else 0),
		"schedule": 2 + html_lines(rest.get("schedule_html")),
		"warranty": 2 + sum(lines(w["text"]) + sum(lines(x, 70) for x in w["sub"]) for w in rest.get("warranty_items") or []),
		"scope_company": 2.5 + 1.5 + sum(lines("{0}: {1}".format(x.get("category"), x.get("text"))) for x in scope.get("company") or []),
		"scope_customer": 1.5 + sum(lines("{0}: {1}".format(x.get("category"), x.get("text"))) for x in scope.get("customer") or []),
		"way_forward": 2.5 + sum(lines(p, 82) for p in rest.get("way_forward") or []) + 7,  # the contacts' table
	}
	pages, used = [[]], 0
	for key in FLOW:
		if pages[-1] and used + need[key] > TERMS_PAGE_LINES:
			pages.append([])
			used = 0
		pages[-1].append(key)
		used += need[key] + 1  # the gap before the next section
	return pages


def add_on_rows(estimates):
	"""3.3.3 Optional Add-ons: each add-on of the estimates the options are, once,
	in option order - [{item_html, amount_text}]. "13th" prints as 13<sup>th</sup>."""
	import re

	from frappe.utils import escape_html, fmt_money

	def add_ons(estimate):
		"""The estimate's own add-ons still offered (an Option; one taken is in the price), at
		their amount; an estimate made before it had them offers its package's."""
		own = estimate.get("optional_add_ons")
		if own:
			return [r for r in own if r.is_option]
		if not estimate.get("solar_package"):
			return []
		return frappe.get_all("Solar Package Add-on", filters={"parent": estimate.solar_package, "parenttype": "Solar Package"},
			fields=["item", "amount"], order_by="idx asc")

	rows, seen = [], set()
	for estimate in estimates:
		for r in add_ons(estimate):
			key = ((r.item or "").strip(), flt(r.amount))
			if not key[0] or key in seen:
				continue
			seen.add(key)
			rows.append({"item_html": re.sub(r"(\d)(st|nd|rd|th)\b", r"\1<sup>\2</sup>", escape_html(key[0])),
				"amount_text": fmt_money(flt(r.amount), precision=0)})
	return rows


def plant_description(est):
	"""'Design, Supply, Installation, Testing and Commissioning of 20kWp Non-DCR Grid Connected
	Rooftop Solar Power Plant with 25 kW Inverter including AC Cabling and earthing from roof to
	the electrical room' - the plant as the client's cost table prices it, with the battery
	(10.24kWh LiFePO4 battery (51.2V, 100Ah X 2)) of a hybrid or off-grid plant."""
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	priced = lambda table: [r for r in est.get(table) or [] if not r.get("is_option")]
	panels, inverters, batteries = priced("panels"), priced("inverters"), priced("batteries")
	kwp = _kwp(est)
	inv_kw = sum(flt(r.inverter_capacity_kw) * (cint(r.nos) or 1) for r in inverters)
	kwh = sum(flt(r.total_energy_kwh) or flt(r.battery_voltage) * flt(r.battery_capacity_ah) * cint(r.nos) / 1000 for r in batteries)
	kinds = {r.panel_type for r in panels if r.panel_type}
	dcr = ("DCR " if kinds == {"DCR"} else "Non-DCR ") if len(kinds) == 1 else ""
	system = SYSTEM_NAMES.get(est.system_type or "", est.system_type or "")
	battery_text = ""
	if batteries:
		b = batteries[0]
		battery_text = ", {0:g}kWh {1} battery ({2})".format(round(kwh, 2),
			technology_name(b.battery_variant) if b.battery_variant else "",
			", ".join("{0:g}V, {1:g}Ah X {2}".format(flt(r.battery_voltage), flt(r.battery_capacity_ah), cint(r.nos)) for r in batteries)
		).replace("  ", " ")
	return ("Design, Supply, Installation, Testing and Commissioning of {0:g}kWp {1}{2}Rooftop Solar Power Plant with "
		"{3:g} kW Inverter{4} including AC Cabling and earthing from roof to the electrical room").format(
		kwp, dcr, (system + " ") if system else "", inv_kw, battery_text)
