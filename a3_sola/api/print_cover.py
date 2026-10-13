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


def _proposal(doc):
	from a3_sola.api.settings import get_value
	from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import _fiscal_label

	# RENC/PROP/26-27/351, and _R2 once it has been revised: the client's own numbering.
	prefix = (get_value("proposal_series_prefix") or "RENC-PROP").replace("-", "/")
	fiscal = _fiscal_label(doc.fiscal_year, get_value("proposal_fiscal_year_format") or "YY-YY")
	number = "/".join(str(p) for p in (prefix, fiscal, doc.proposal_sequence) if p) if doc.proposal_sequence else doc.name
	if cint(doc.get("current_version")):
		number += "_R{0}".format(cint(doc.current_version))
	return {
		"title": "Solar Project Proposal",
		"salutation": doc.get("salutation"),
		"customer": doc.customer_name,
		"place": _place(doc.get("location"), doc.get("district")),
		"number": number,
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
	return {"logo": logo, "address_lines": [line.strip() for line in address.splitlines() if line.strip()]}


# ------------------------------------------------------------------ page 2: the letter
#: "Dear Madam" for these salutations, "Dear Sir" for the rest that name one.
MADAM = {"mrs", "ms", "miss", "madam", "smt"}


def print_letter(doc):
	"""The covering letter of a Solar Proposal: one point per design estimate, in the
	table's order (Option 1 first), then one per line of the proposal's Remarks."""
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	names = [r.solar_design_estimate for r in doc.get("design_estimates") or [] if r.solar_design_estimate]
	if not names and doc.get("solar_design_estimate"):
		names = [doc.solar_design_estimate]
	options = [_option_line(frappe.get_doc("Solar Design Estimate", n), technology_name) for n in names]
	points = [("Option {0}: {1}".format(i, line) if len(options) > 1 else line) for i, line in enumerate(options, 1) if line]
	points += [line.strip() for line in (doc.get("remarks") or "").splitlines() if line.strip()]

	salutation = (doc.get("salutation") or "").strip().rstrip(".")
	dear = "Dear Madam," if salutation.lower() in MADAM else ("Dear Sir," if salutation else "Dear Sir/Madam,")
	revised = cint(doc.get("current_version")) > 0
	company = frappe.db.get_value("Company", doc.company, ["company_name", "website", "phone_no", "email",
		"epc_authorised_signatory", "epc_signatory_designation"], as_dict=True) if doc.get("company") else frappe._dict()
	from a3_sola.api.settings import get_value

	website = (company.website or get_value("brand_website") or "").strip()
	letter = {
		"date": getdate(doc.proposal_date).strftime("%d.%m.%Y") if doc.get("proposal_date") else "",
		"to": " ".join(p for p in (_titled(doc.get("salutation")), doc.customer_name) if p),
		"place": _place(doc.get("location"), doc.get("district")),
		"dear": dear,
		"intro": "Please find enclosed our quotation for the following:" if doc.get("quotation") else
			"Please find enclosed our {0}offer with the following {1}:".format(
				"revised " if revised else "", "options" if len(options) > 1 else "details"),
		"points": points,
		"company_name": company.company_name or doc.get("company") or "",
		"signatory": company.epc_authorised_signatory or "",
		"designation": company.epc_signatory_designation or "",
		"website": website.replace("https://", "").replace("http://", "").rstrip("/"),
		"phone": company.phone_no or get_value("sales_phone") or "",
		"email": company.email or get_value("sales_email") or "",
	}
	letter.update(_company(doc.get("company")))
	return letter


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
	est = frappe.get_doc("Solar Design Estimate", doc.solar_design_estimate) if doc.get("solar_design_estimate") else None
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
	rows.append(("Capacity of Solar Panels Proposed", "{0:g} kWp".format(kwp) if kwp else ""))
	rows.append(("Tilt & Orientation", _tilt(survey, roof)))
	system = est.system_type if est else None
	rows.append(("Type of Solar Power Plant", "{0} Rooftop".format(system) if system else ""))
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
	# The band for the panels proposed, as the estimate works it out for its own capacity.
	if kwp:
		from a3_sola.api.calculations import estimate_daily_generation_band

		section = frappe.db.get_value("Solar Consumer", doc.solar_consumer, "discom_section") if doc.get("solar_consumer") else None
		band = estimate_daily_generation_band(kwp, section)
		low, high = flt(band["low_units_per_day"]), flt(band["high_units_per_day"])
	else:
		low, high = (flt(est.expected_daily_units_low), flt(est.expected_daily_units_high)) if est else (0, 0)
	rows.append(("Estimated Annual Average Generation",
		"{0:.0f}-{1:.0f} units per day".format(low, high) if low and high else ("{0:.0f} units per day".format(low or high) if (low or high) else "")))
	return {"rows": rows, "missing": [p for p, v in rows if not v]}


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


def print_components(doc):
	"""3.2 Specifications & Quantity of Major Components, from the proposal's base design
	estimate: its priced panel, inverter and battery rows, its balance of system, mounting
	structure and installation. Returns {"rows": [...], "missing": [...]} - each row is
	{item, spec, make, nos}, and `missing` names the rows without a make on record."""
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	if not doc.get("solar_design_estimate"):
		return {"rows": [], "missing": []}
	est = frappe.get_doc("Solar Design Estimate", doc.solar_design_estimate)

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
		spec = " ".join(p for p in ("{0:g}Wp".format(flt(r.panel_capacity_wp)) if flt(r.panel_capacity_wp) else "",
			technology_name(r.panel_variant) if r.panel_variant else "",
			("DCR" if r.panel_type == "DCR" else "Non DCR") if r.panel_type else "") if p)
		names = [make(r.panel_make)] + [m.strip() for m in (alternates.get(r.panel_make) or "").split("/")
			if m.strip() and m.strip().lower() not in ("equivalent", make(r.panel_make).lower())]
		rows.append({"item": "Solar Panels", "spec": spec, "make": "/ ".join(n for n in names if n), "nos": cint(r.nos)})
	hybrid = est.system_type == "Hybrid"
	for r in priced("inverters"):
		phase = {"Three Phase": "3 phase", "Single Phase": "1 phase"}.get(r.inverter_phase or "", r.inverter_phase or "")
		spec = ", ".join(p for p in ("{0:g} kW".format(flt(r.inverter_capacity_kw)) if flt(r.inverter_capacity_kw) else "",
			phase, (r.get("specification") or "").strip() or (technology_name(r.inverter_type) if r.inverter_type else "")) if p)
		rows.append({"item": "Solar PV Hybrid Inverter" if hybrid else "Solar PV Inverter", "spec": spec,
			"make": make(r.inverter_make), "nos": cint(r.nos)})

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
			else:
				nos = "{0:g}".format(count) if count else ""
			by_part = [line.strip() for line in (r.get("component_makes") or "").splitlines() if line.strip()]
			rows.append({"item": label, "spec": spec, "make": "\n".join(by_part) or make(r.make) or makes_of(item), "nos": nos})

	bos_row("DCDB", "DCDB")
	for r in priced("batteries"):
		described = (r.get("specification") or "").strip()
		spec = " ".join(p for p in ("{0:g}V, {1:g}Ah".format(flt(r.battery_voltage), flt(r.battery_capacity_ah)),
			described or " ".join(p for p in (technology_name(r.battery_variant) if r.battery_variant else "", "Battery") if p)) if p)
		rows.append({"item": "Battery", "spec": spec, "make": make(r.battery_make), "nos": cint(r.nos)})
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
	return {"rows": rows, "missing": [r["item"] for r in rows if r["make"] == ""]}


# ------------------------------------------------------------------ sections 3.3 to 6
#: The estimate's own tables that make up the plant's price (KSEB and linked charges apart).
# The package line is the package at its price; the rest price only what is added to it.
PLANT_LINES = ("package", "panels", "inverters", "batteries", "bos_items", "mounting_expenses", "installation_expenses")
#: Charges raised against the estimate in records of their own: (doctype, sign).
CHARGES = (("Additional Structure", 1), ("Additional Cable", 1), ("Special Discount", -1))
#: The client's payment terms. Nothing on file holds them yet, so they are printed as standing.
PAYMENT_TERMS = (
	"70% as advance with PO.",
	"20% after installation completion.",
	"10% after commissioning of system with Net Meter. In case of net meter availed from KSEBL, "
	"10% to be transferred after submission of completion documents to KSEBL.",
)
#: Shipped with the app, used while nothing on file names installation photographs.
DEFAULT_PICTURES = tuple("/assets/a3_sola/images/installations/installation-{0}.jpg".format(i) for i in (1, 2, 3))


def print_rest(doc):
	"""Sections 3.3 to 6 of a Solar Proposal print: the project cost and KSEBL expenses, the
	terms, payment and bank details, the schedule, the warranty, the scope of work, the
	pictures of similar installations and the way forward. All from the base design
	estimate, the records it links to, the Company and A3 Sola Settings."""
	from frappe.utils import fmt_money, money_in_words

	from a3_sola.api.settings import get_settings
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	settings = get_settings()
	est = frappe.get_doc("Solar Design Estimate", doc.solar_design_estimate) if doc.get("solar_design_estimate") else None
	company = frappe.get_doc("Company", doc.company) if doc.get("company") else frappe._dict()
	money = lambda v: fmt_money(flt(v), precision=0)  # 7,76,000 - the client prints whole rupees
	empty = {"label": "", "rows": []}
	out = {"cost": [], "cost_options": [empty], "cost_pages": [{"options": [empty], "kseb": True}], "kseb": [], "kseb_total": 0, "kseb_words": "", "kseb_note": "", "terms_html": "",
		"validity": "", "payment_terms": list(PAYMENT_TERMS), "bank": [], "schedule_html": settings.get("delivery_schedule_text") or "",
		"warranty": [], "scope": {"company": [], "customer": []}, "pictures": list(DEFAULT_PICTURES),
		"company_scope_label": "", "customer_scope_label": "", "system_type": ""}
	if not est:
		return out

	priced = lambda table: [r for r in est.get(table) or [] if not r.get("is_option")]
	panels, inverters, batteries = priced("panels"), priced("inverters"), priced("batteries")
	kwp = round(sum(flt(r.get("total_capacity_kwp")) or flt(r.panel_capacity_wp) * cint(r.nos) / 1000 for r in panels), 2)
	inv_kw = sum(flt(r.inverter_capacity_kw) * (cint(r.nos) or 1) for r in inverters)
	kwh = sum(flt(r.total_energy_kwh) or flt(r.battery_voltage) * flt(r.battery_capacity_ah) * cint(r.nos) / 1000 for r in batteries)
	out["system_type"] = est.system_type or ""

	# 3.3.1 Every option of the proposal, in its order - Option 1 is the base - each with its
	# plant, its linked charges, the total and the price after discount. A quotation is one
	# option, and prints what it charges.
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
		names = [r.solar_design_estimate for r in doc.get("design_estimates") or [] if r.get("solar_design_estimate")]
		names = list(dict.fromkeys(names)) or [est.name]
		estimates = [est if n == est.name else frappe.get_doc("Solar Design Estimate", n) for n in names
			if n == est.name or frappe.db.exists("Solar Design Estimate", n)]
		options = [{"label": _option_label(e, i) if len(estimates) > 1 else "", "rows": plant_cost_rows(e)}
			for i, e in enumerate(estimates, 1)]
	for option in options:
		for r in option["rows"]:
			r["amount_text"] = money(r["amount"])
	out["cost"] = options[0]["rows"]
	out["cost_options"] = options

	# 3.3.2 KSEBL expenses, as the fee schedule resolved them for the estimate.
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
	out["cost_pages"] = cost_pages(out["cost_options"], len(kseb), bool(out["kseb_note"]))

	# 3.4 terms and offer validity; 3.5 the bank details from the Company.
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

	# 3.7 warranty: the package's system warranty, then each make's own terms.
	def make_doc(name):
		return frappe.get_cached_doc("Component Make", name) if name and frappe.db.exists("Component Make", name) else None

	years = cint(frappe.db.get_value("Solar Package", est.solar_package, "warranty_years")) if est.solar_package else 0
	warranty = []
	if years:
		warranty.append("System Warranty shall be for {0} years from the date of initial Commissioning.".format(years))
	seen = set()
	for label, rows_, field in (("Solar PV Modules", panels, "panel_make"), ("Inverter", inverters, "inverter_make"), ("Battery", batteries, "battery_make")):
		for r in rows_:
			m = make_doc(r.get(field))
			if not m or m.name in seen:
				continue
			seen.add(m.name)
			if label == "Solar PV Modules":
				parts = []
				if cint(m.performance_warranty_years):
					parts.append("performance warranty of {0} years".format(cint(m.performance_warranty_years)))
				if cint(m.product_warranty_years):
					parts.append("product warranty of {0} years".format(cint(m.product_warranty_years)))
				if parts:
					warranty.append("Solar PV Modules will have {0} as offered by the manufacturer.".format(" and ".join(parts)))
			elif cint(m.product_warranty_years):
				warranty.append("{0} Warranty – {1} Years as offered by the manufacturer.".format(label, cint(m.product_warranty_years)))
	out["warranty"] = warranty

	# 4 scope of work, from Settings, by responsibility.
	for r in sorted(settings.get("scope_of_work") or [], key=lambda r: (cint(r.display_order), r.idx)):
		side = "company" if r.responsibility == "Company" else "customer"
		out["scope"][side].append({"category": r.category, "text": r.scope_text})
	short = (company.get("company_name") or "").split(" ")[0]
	out["company_scope_label"] = "{0} Scope".format(short) if short else (settings.get("company_scope_label") or "Our Scope")
	out["customer_scope_label"] = settings.get("customer_scope_label") or "Client's Scope"
	return out


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
					rows.append({"item": item.description or item.get("structure_type") or item.get("cable_type") or doctype,
						"amount": flt(item.amount), "right": True})
	if flt(commercials.get("gst_amount")):
		rows.append({"item": "GST @ {0:g}%".format(flt(commercials["gst_percent"])), "amount": flt(commercials["gst_amount"]), "right": True})
	total = sum(r["amount"] for r in rows)
	rows.append({"item": "Total", "amount": total, "right": True, "bold": True})
	if discount:
		rows.append({"item": "Special Price after Discount", "amount": total - discount, "right": True, "bold": True})
	return rows


def _option_label(est, number):
	"""'Option 2 – 3 kW Single Phase On-Grid (PM Surya Ghar) – Solinteg': the package it is
	built on and the inverter it is priced with, since two options often share a package."""
	package = frappe.db.get_value("Solar Package", est.solar_package, "package_name") if est.solar_package else None
	makes = [frappe.db.get_value("Component Make", r.inverter_make, "make_name") for r in est.get("inverters") or []
		if r.inverter_make and not r.get("is_option")]
	label = " – ".join(part for part in (package, " + ".join(dict.fromkeys(m for m in makes if m))) if part)
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


def cost_pages(options, kseb_rows, kseb_note):
	"""Section 3.3 as pages: [{"options": [...], "kseb": bool}]. Options fill a page in order;
	the KSEBL expenses follow the last of them, on its page when they fit, else on the next."""
	kseb_mm = 14 + 12 + (kseb_rows + 2) * (LINE_MM + 2) + (12 if kseb_note else 0)
	pages, current, used = [], [], HEADINGS_MM
	for option in options:
		need = (OPTION_MM if option["label"] else 12) + _rows_mm(option["rows"])
		if current and used + need > PAGE_MM:
			pages.append({"options": current, "kseb": False})
			current, used = [], CONTINUED_MM
		current.append(option)
		used += need
	if used + kseb_mm > PAGE_MM:
		pages.append({"options": current, "kseb": False})
		current = []
	pages.append({"options": current, "kseb": True})
	return pages


def plant_description(est):
	"""'Design, Supply, Installation, Testing and Commissioning of 4.95 kWp Single Phase Hybrid
	Solar Power Plant with 5kW Inverter, 10.24kWh LiFePO4 battery (51.2V, 100Ah X 2) and
	Balance of System and other accessories.' - the plant as the proposal prices it."""
	from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name

	priced = lambda table: [r for r in est.get(table) or [] if not r.get("is_option")]
	panels, inverters, batteries = priced("panels"), priced("inverters"), priced("batteries")
	kwp = round(sum(flt(r.get("total_capacity_kwp")) or flt(r.panel_capacity_wp) * cint(r.nos) / 1000 for r in panels), 2)
	inv_kw = sum(flt(r.inverter_capacity_kw) * (cint(r.nos) or 1) for r in inverters)
	kwh = sum(flt(r.total_energy_kwh) or flt(r.battery_voltage) * flt(r.battery_capacity_ah) * cint(r.nos) / 1000 for r in batteries)
	battery_text = ""
	if batteries:
		b = batteries[0]
		battery_text = ", {0:g}kWh {1} battery ({2})".format(round(kwh, 2),
			technology_name(b.battery_variant) if b.battery_variant else "",
			", ".join("{0:g}V, {1:g}Ah X {2}".format(flt(r.battery_voltage), flt(r.battery_capacity_ah), cint(r.nos)) for r in batteries)
		).replace("  ", " ")
	description = "Design, Supply, Installation, Testing and Commissioning of {0:g} kWp {1}{2}Solar Power Plant with {3:g}kW Inverter{4} and Balance of System and other accessories.".format(
		kwp, (est.connection_type + " ") if est.connection_type else "", (est.system_type + " ") if est.system_type else "", inv_kw, battery_text)
	return description
