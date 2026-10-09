# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's design estimate builder: details first, then the system, row by row.

Step one captures the Estimate Details tab. Step two works one System & Options table at a
time: the rows saved so far, a form to add or change one, and the commercials beside them.
Every change saves the whole estimate, so the controller - not this module - computes the
counts, the expense rows and the prices, and the page simply shows what came back.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt

from a3_sola.api.expenses import EXPENSE_GROUPS
from a3_sola.api.settings import get_value
from a3_sola.api.portal_fields import link_choices, link_title
from a3_sola.solar_crm.doctype.balance_of_system_package.balance_of_system_package import MAKE_TYPE

DOCTYPE = "Solar Design Estimate"
SLUG = "design-estimates"

# Step one, top to bottom: who it is for (with that consumer's details beside the
# fields), then the package and how it is sized.
DETAIL_COLUMNS = (
	# The tariff asked for is KSEB's category code. The priced tariff the savings are worked
	# out on (electricity_tariff) is not asked: the estimate picks it for the DISCOM.
	("Consumer", ("lead", "solar_consumer", "site_survey", "estimate_date", "tariff_code")),
	# The package and how it is sized, asked for as the desk asks: one package per estimate.
	# The estimate keeps them on its recommended sizing row, which it follows.
	("Package Details", ("connection_type", "system_type", "subsidy_option", "subsidy_scheme",
		"solar_package", "override_capacity_kw")),
)

# The consumer's details shown under the Consumer fields: (fieldname, label) per source.
# A consumer is preferred to its lead, as the estimate itself prefers it.
PROFILE_FIELDS = {
	"Solar Consumer": (
		("consumer_name", "Name"), ("mobile_no", "Mobile"), ("email_id", "Email"),
		("consumer_number", "Consumer No."), ("discom", "DISCOM"), ("discom_section", "Section"),
		("tariff_category", "Tariff"), ("connection_type", "Connection"),
		("sanctioned_load_kw", "Sanctioned load (kW)"), ("annual_consumption_units", "Annual units"),
		("installation_address", "Address"),
	),
	"Lead": (
		("lead_name", "Name"), ("company_name", "Organisation"), ("mobile_no", "Mobile"),
		("email_id", "Email"), ("city", "City"), ("source", "Source"), ("status", "Status"),
	),
}

# Step two. Each field names the choices it draws on, where it has any; `filter_by` narrows
# a make list to the variant, type or item chosen beside it.
SECTIONS = (
	{"key": "panels", "label": "Solar Panel", "icon": "bolt", "fields": (
		{"fieldname": "panel_type", "choices": "panel_type"},
		{"fieldname": "panel_capacity_wp"},
		# Asked in the popup, not shown as a column: the Nos column shows the count in force,
		# typed or worked out.
		{"fieldname": "panel_count", "column": False, "hint": True},
		{"fieldname": "panel_variant", "choices": "module_technology"},
		{"fieldname": "panel_make", "choices": "module_make", "filter_by": "panel_variant"},
		{"fieldname": "is_option", "choices": "yes_no", "hint": "Yes: an alternative shown to the customer, not added to the commercials."},
		{"fieldname": "rate", "hint": "Leave blank to use the price on file in the backend."},
	), "computed": ("nos", "amount"),
		# Shown as the Inverter Options are: a bold title, a line under it, then the figures.
		"compact": {"title": (("panel_make", ""), ("panel_capacity_wp", " Wp"), ("panel_type", "")),
			"sub": (("panel_variant", ""),)}},
	{"key": "inverters", "label": "Inverter", "icon": "power", "fields": (
		{"fieldname": "inverter_type", "choices": "inverter_technology"},
		{"fieldname": "inverter_capacity_kw"},
		{"fieldname": "inverter_count", "column": False, "hint": True},
		{"fieldname": "inverter_phase", "choices": "phase"},
		{"fieldname": "inverter_make", "choices": "inverter_make", "filter_by": "inverter_type"},
		{"fieldname": "is_option", "choices": "yes_no", "hint": "Yes: an alternative shown to the customer, not added to the commercials."},
		{"fieldname": "rate", "hint": "Leave blank to use the price on file in the backend."},
	), "computed": ("nos", "amount"),
		"compact": {"title": (("inverter_make", ""), ("inverter_type", ""), ("inverter_capacity_kw", " kW")),
			"sub": (("inverter_phase", ""),)}},
	{"key": "batteries", "label": "Battery", "icon": "stack", "only_for": ("Off-Grid", "Hybrid"), "fields": (
		{"fieldname": "battery_voltage"},
		{"fieldname": "battery_phase", "choices": "phase"},
		{"fieldname": "battery_capacity_ah"},
		{"fieldname": "battery_variant", "choices": "battery_technology"},
		{"fieldname": "battery_make", "choices": "battery_make", "filter_by": "battery_variant"},
		{"fieldname": "is_option", "choices": "yes_no", "hint": "Yes: an alternative shown to the customer, not added to the commercials."},
		{"fieldname": "nos"},
		{"fieldname": "rate"},
	), "computed": ("total_energy_kwh", "amount"),
		"compact": {"title": (("battery_make", ""), ("battery_variant", ""), ("battery_voltage", " V"), ("battery_capacity_ah", " Ah")),
			"sub": (("battery_phase", ""), ("total_energy_kwh", " kWh"))}},
	{"key": "bos_items", "label": "Balance of System", "icon": "box", "fields": (
		{"fieldname": "item", "choices": "bos_item"},
		{"fieldname": "phase", "choices": "phase"},
		{"fieldname": "specification"},
		{"fieldname": "make", "choices": "bos_make", "filter_by": "item"},
		{"fieldname": "numbers"},
		{"fieldname": "rate", "hint": "Leave blank to use the price on file in the backend."},
	), "computed": ("amount",),
		"compact": {"title": (("item", ""), ("make", "")), "sub": (("specification", ""), ("phase", "")),
			"count": "numbers"}},
	{"key": "kseb_expenses", "label": "KSEB Expenses", "icon": "receipt", "fields": (
		{"fieldname": "particulars", "choices": "kseb_expenses_item"},
		{"fieldname": "amount"},
	), "computed": ()},
	{"key": "mounting_expenses", "label": "Mounting Structure Expenses", "icon": "wrench", "fields": (
		{"fieldname": "item", "choices": "mounting_expenses_item"},
		{"fieldname": "specification"},
		{"fieldname": "make", "choices": "mounting_make"},
		{"fieldname": "capacity_kw"},
		{"fieldname": "amount"},
	), "computed": ()},
	{"key": "installation_expenses", "label": "Installation Expenses", "icon": "checklist", "fields": (
		{"fieldname": "item", "choices": "installation_expenses_item"},
		{"fieldname": "specification"},
	), "computed": ("amount",)},
)
SECTION_BY_KEY = {section["key"]: section for section in SECTIONS}

# After the estimate's own tables: charges kept in their own records, raised against the
# estimate. Their rows are those records' items; the first row added makes the record. The
# keys match the commercials lines in the estimate's LINKED_CHARGES.
LINKED_SECTIONS = (
	{"key": "additional_structure", "doctype": "Additional Structure", "label": "Additional Structure", "icon": "box", "fields": (
		{"fieldname": "structure_type", "choices": "structure_type"},
		{"fieldname": "description"},
		{"fieldname": "uom"},
		{"fieldname": "qty"},
		{"fieldname": "rate"},
	), "computed": ("amount",)},
	{"key": "additional_cable", "doctype": "Additional Cable", "label": "Additional Cable", "icon": "bolt", "fields": (
		{"fieldname": "cable_type", "choices": "cable_type"},
		{"fieldname": "cable_size"},
		{"fieldname": "description"},
		{"fieldname": "length"},
		{"fieldname": "rate"},
	), "computed": ("amount",)},
	{"key": "special_discount", "doctype": "Special Discount", "label": "Special Discount", "icon": "refund", "fields": (
		{"fieldname": "description"},
		{"fieldname": "discount_type", "choices": "discount_type"},
		{"fieldname": "discount_value"},
		{"fieldname": "base_amount", "hint": "For a percentage. Left blank, it is the estimate's subtotal before discount."},
	), "computed": ("amount",)},
)
LINKED_BY_KEY = {section["key"]: section for section in LINKED_SECTIONS}

INPUT = {
	"Select": "select", "Link": "select", "Int": "number", "Float": "number", "Currency": "number",
	"Percent": "number", "Date": "date", "Small Text": "textarea", "Text": "textarea",
}


# ------------------------------------------------------------------ step one
def tariff_code_choices():
	"""KSEB's tariff codes as choices, in the board's own order, and what each one covers.

	Returns (choices, help): the label reads "LT-I · Domestic"; `help` maps each code to
	the details the "?" beside the field shows.
	"""
	rows = frappe.get_all("KSEB Tariff Category", filters={"is_active": 1},
		fields=["name", "category_name", "supply_group", "voltage_level", "usage"],
		order_by="sort_order asc, name asc")
	choices = [
		{"value": r.name, "label": r.name if r.category_name == r.name else "{0} · {1}".format(r.name, r.category_name)}
		for r in rows
	]
	info = {
		r.name: {"code": r.name, "name": r.category_name, "group": r.supply_group,
			"voltage": r.voltage_level or "", "usage": r.usage or ""}
		for r in rows
	}
	return choices, info


def estimate_prefill(values):
	"""A new estimate's details from the records it is raised from, so none is asked again.

	`values` names any of the lead, consumer and survey. The survey brings its consumer, the
	consumer its lead; then the consumer (else the lead) gives the connection type and KSEB
	tariff code, and a survey with batteries in scope makes the system Hybrid. Each record
	is read only if the person may read it.
	"""
	from a3_sola.solar_crm.doctype.kseb_tariff_category.kseb_tariff_category import kseb_code

	out = {k: v for k, v in (values or {}).items() if v}

	def readable(doctype, name):
		return bool(name) and frappe.db.exists(doctype, name) and frappe.has_permission(doctype, "read", name)

	survey = frappe.get_doc("Site Survey", out["site_survey"]) if readable("Site Survey", out.get("site_survey")) else None
	if survey:
		out.setdefault("solar_consumer", survey.solar_consumer)
		out.setdefault("lead", survey.lead)
		if cint(survey.get("batteries_in_scope")):
			out.setdefault("system_type", "Hybrid")
	consumer = (frappe.db.get_value("Solar Consumer", out["solar_consumer"],
		["lead", "connection_type", "tariff_category"], as_dict=True)
		if readable("Solar Consumer", out.get("solar_consumer")) else None)
	if consumer:
		out.setdefault("lead", consumer.lead)
		out.setdefault("connection_type", consumer.connection_type)
		code = kseb_code(consumer.tariff_category) if consumer.tariff_category else None
		if code:
			out.setdefault("tariff_code", code)
	if readable("Lead", out.get("lead")):
		if not out.get("solar_consumer"):
			out["solar_consumer"] = frappe.db.get_value("Lead", out["lead"], "solar_consumer")
		out.setdefault("connection_type", frappe.db.get_value("Lead", out["lead"], "connection_type"))
		if not out.get("site_survey") and out.get("solar_consumer"):
			# The consumer's survey, the submitted one first, as the estimate itself picks it.
			out["site_survey"] = (frappe.get_all("Site Survey", filters={"solar_consumer": out["solar_consumer"],
				"docstatus": ("<", 2)}, pluck="name", order_by="docstatus desc, creation desc", limit=1) or [None])[0]
	return {k: v for k, v in out.items() if v}


def detail_columns(doc=None, prefill=None):
	"""The Estimate Details form as two columns of field specs, valued from `doc` if given,
	else from `prefill` (see estimate_prefill) and the field defaults."""
	meta = frappe.get_meta(DOCTYPE)
	columns = []
	for title, fieldnames in DETAIL_COLUMNS:
		fields = []
		for fieldname in fieldnames:
			df = meta.get_field(fieldname)
			value = doc.get(fieldname) if doc else ((prefill or {}).get(fieldname) or df.default or "")
			if fieldname == "estimate_date" and (not value or value == "Today"):
				# The doctype's default is the word "Today", which a date input cannot show.
				value = frappe.utils.today()
			spec = {
				"fieldname": fieldname, "label": _(df.label), "input": INPUT.get(df.fieldtype, "text"),
				"reqd": bool(df.reqd), "hint": _(df.description) if df.description else "",
				"value": "" if value is None else str(value),
			}
			if df.fieldtype == "Select":
				spec["options"] = [{"value": o, "label": o or "—"} for o in (df.options or "").split("\n")]
			elif df.fieldtype == "Link":
				if df.options == "KSEB Tariff Category":
					choices, spec["help"] = tariff_code_choices()
					spec["label"] = _("Electricity Tariff")
					spec["hint"] = ""
				else:
					choices = link_choices(df.options)
				if value and not any(c["value"] == value for c in choices):
					choices.insert(0, {"value": value, "label": link_title(df.options, value)})
				if df.options == "Solar Package":
					# Each package carries the phases it has inverters for, so a row lists only
					# the packages for its connection type.
					from a3_sola.solar_crm.doctype.solar_package.solar_package import package_phases

					for c in choices:
						c["phases"] = "|".join(sorted(package_phases(c["value"])))
				if df.options == "Solar Consumer":
					# The lead each consumer came from, either way round the link is kept, so
					# choosing a lead lists only its consumers.
					rows = {r.name: r for r in frappe.get_all("Solar Consumer", fields=["name", "lead", "tariff_category"],
						filters={"name": ["in", [c["value"] for c in choices]]})}
					leads = {name: r.lead for name, r in rows.items()}
					for lead, consumer in frappe.get_all("Lead", fields=["name", "solar_consumer"],
							filters={"solar_consumer": ["in", [c["value"] for c in choices]]}, as_list=True):
						leads[consumer] = leads.get(consumer) or lead
					for c in choices:
						c["lead"] = leads.get(c["value"]) or ""
						# Its KSEB code, which the Electricity Tariff takes when a consumer is chosen.
						c["tariff"] = (rows.get(c["value"]) or {}).get("tariff_category") or ""
				if df.options == "Site Survey":
					# The consumer each survey is of, so surveys follow the lead and consumer
					# chosen. A survey has no name of its own, so it reads as its consumer's,
					# with its id under it.
					surveys = {r.name: r for r in frappe.get_all("Site Survey", fields=["name", "solar_consumer", "customer_name"],
						filters={"name": ["in", [c["value"] for c in choices]]})}
					for c in choices:
						row = surveys.get(c["value"])
						c["consumer"] = row.solar_consumer if row else ""
						if row and row.customer_name:
							c["label"] = row.customer_name
							c["show_id"] = True
				spec["options"] = [{"value": "", "label": "—"}] + choices
				spec["searchable"] = True  # typed into as well as picked from: lists run long
			if fieldname == "subsidy_option":
				# Subsidy is for one tariff only (LT-I, domestic): the page offers it only there.
				from a3_sola.solar_crm.doctype.kseb_tariff_category.kseb_tariff_category import kseb_code

				required = get_value("subsidy_tariff_category", "LT-I")
				spec["subsidy_tariff"] = kseb_code(required) or required
			if fieldname == "subsidy_scheme":
				spec["show_when"] = "subsidy_option=With Subsidy"
				# The scheme a subsidised estimate takes unless another is chosen (PM Surya Ghar).
				spec["default_value"] = get_value("default_subsidy_scheme") or ""
				if not doc and not spec["value"]:
					spec["value"] = spec["default_value"]
			fields.append(spec)
		columns.append({"title": _(title), "fields": fields})
	# Worked out by the estimate, shown beside the package once there is one.
	columns[1]["facts"] = [
		{"label": _("DCR Compliant"), "value": _("Yes") if doc.is_dcr_compliant else _("No")},
		{"label": _("Proposed System Size (kW)"), "value": "{0:g}".format(flt(doc.final_capacity_kw))},
	] if doc and doc.solar_package else []
	return columns


def subject_profile(lead=None, solar_consumer=None):
	"""{title, source, rows} describing who the estimate is for, or None.

	Read with the caller's own permissions: a record they cannot read shows nothing rather
	than failing the page.
	"""
	doctype, name = ("Solar Consumer", solar_consumer) if solar_consumer else ("Lead", lead)
	if not name or not frappe.db.exists(doctype, name):
		return None
	if not frappe.has_permission(doctype, "read", name):
		return None
	doc = frappe.get_doc(doctype, name)
	meta = doc.meta
	rows = []
	for fieldname, label in PROFILE_FIELDS[doctype]:
		df = meta.get_field(fieldname)
		value = doc.get(fieldname)
		if not df or value in (None, "", 0):
			continue
		if fieldname == "installation_address":
			text = frappe.db.get_value("Address", value, "address_line1") or value
			city = frappe.db.get_value("Address", value, "city")
			text = ", ".join(p for p in (text, city) if p)
		elif df.fieldtype == "Link":
			text = link_title(df.options, value)
		elif df.fieldtype in ("Float", "Int"):
			text = "{0:g}".format(flt(value))
		else:
			text = str(value)
		rows.append({"label": _(label), "value": text})
	return {"title": rows[0]["value"] if rows else name, "source": _(doctype), "name": name, "rows": rows[1:]}


@frappe.whitelist()
def profile(lead=None, solar_consumer=None):
	"""The consumer details card, for step one to refresh when the lead or consumer changes."""
	return subject_profile(lead, solar_consumer)


@frappe.whitelist()
def save_details(values, name=None, sizing_options=None):
	"""Create the estimate, or update its details, from step one; return where step two is.

	`sizing_options` is the Package & Sizing table, one dict per row. The estimate makes
	the recommended row its own package and sizing on save.
	"""
	values = frappe.parse_json(values) or {}
	options = frappe.parse_json(sizing_options) if sizing_options else None
	if name:
		doc = _load(name)
	else:
		frappe.has_permission(DOCTYPE, "create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		doc.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	sizing_fields = DETAIL_COLUMNS[1][1]
	allowed = {fieldname for _title, fieldnames in DETAIL_COLUMNS for fieldname in fieldnames}
	if options:
		allowed -= set(sizing_fields)
	for fieldname in allowed:
		if fieldname in values:
			doc.set(fieldname, values.get(fieldname) or None)
	if options:
		doc.set("sizing_options", [])
		for row in options:
			if not isinstance(row, dict):
				continue
			entry = {fieldname: (row.get(fieldname) or None) for fieldname in sizing_fields}
			entry["override_capacity_kw"] = flt(row.get("override_capacity_kw")) or None
			entry["is_recommended"] = 1 if row.get("is_recommended") else 0
			doc.append("sizing_options", entry)
	elif doc.subsidy_option != "With Subsidy":
		doc.subsidy_scheme = None
	doc.save()
	return {"name": doc.name, "route": design_route(doc.name)}


# ------------------------------------------------------------------ step two
def design_route(name):
	return "/a3solaportal/{0}/{1}/design".format(SLUG, frappe.utils.quote(name))


def details_route(name):
	return "/a3solaportal/{0}/{1}/details".format(SLUG, frappe.utils.quote(name))


def _load(name, permtype="write"):
	if not name or not frappe.db.exists(DOCTYPE, name):
		raise frappe.DoesNotExistError(_("That design estimate does not exist."))
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission(permtype)
	if permtype == "write" and cint(doc.docstatus) != 0:
		frappe.throw(_("A submitted design estimate cannot be changed."), frappe.PermissionError)
	return doc


def _choices(doc):
	"""Every dropdown step two offers, read once per page."""
	company = doc.company

	def technologies(component_type):
		return [
			{"value": r.name, "label": r.technology_name}
			for r in frappe.get_all("Component Technology", filters={"component_type": component_type, "company": company},
				fields=["name", "technology_name"], order_by="technology_name")
		]

	def makes(component_type):
		return [
			{"value": r.name, "label": r.make_name, "filter": r.technology or ""}
			for r in frappe.get_all("Component Make",
				filters={"component_type": component_type, "is_active": 1, "company": company},
				fields=["name", "make_name", "technology"], order_by="make_name")
		]

	meta = frappe.get_meta("Design Estimate BOS Item")
	bos_items = [o for o in (meta.get_field("item").options or "").split("\n") if o]
	bos_make = [
		{"value": r.name, "label": r.make_name, "filter": item}
		for item in bos_items
		for r in frappe.get_all("Component Make",
			filters={"component_type": MAKE_TYPE.get(item, item), "is_active": 1, "company": company},
			fields=["name", "make_name"], order_by="make_name")
	]
	out = {
		"panel_type": [{"value": v, "label": v} for v in ("DCR", "Non-DCR")],
		# An estimate's equipment is for its own connection type, so that is the one phase
		# its rows are offered.
		"yes_no": [{"value": "0", "label": "No"}, {"value": "1", "label": "Yes"}],
		"phase": [{"value": v, "label": v} for v in ("Single Phase", "Three Phase")
			if not doc.get("connection_type") or v == doc.get("connection_type")],
		"module_technology": technologies("Module"),
		"module_make": makes("Module"),
		"inverter_technology": technologies("Inverter"),
		"inverter_make": makes("Inverter"),
		"battery_technology": technologies("Battery"),
		"battery_make": makes("Battery"),
		"bos_item": [{"value": v, "label": v} for v in bos_items],
		"bos_make": bos_make,
		"mounting_make": makes("Mounting Structure"),
	}
	for key, doctype, fieldname in (
		("structure_type", "Additional Structure Item", "structure_type"),
		("cable_type", "Additional Cable Item", "cable_type"),
		("discount_type", "Special Discount Item", "discount_type"),
	):
		out[key] = [{"value": v, "label": v} for v in (frappe.get_meta(doctype).get_field(fieldname).options or "").split("\n") if v]
	for table, group in EXPENSE_GROUPS.items():
		out[f"{table}_item"] = [
			{"value": r.name, "label": r.item_name or r.name}
			for r in frappe.get_all("Item", filters={"item_group": group, "disabled": 0},
				fields=["name", "item_name"], order_by="item_name")
		]
	return out


def _display(row, df):
	value = row.get(df.fieldname)
	if value in (None, ""):
		return ""
	if df.fieldtype == "Link":
		return link_title(df.options, value)
	if df.fieldtype == "Check":
		return _("Yes") if cint(value) else ""
	if df.fieldtype == "Currency":
		return frappe.utils.fmt_money(value, currency="INR")
	if df.fieldtype in ("Float", "Int"):
		return "{0:g}".format(flt(value))
	return str(value)


def _editable_value(row, df):
	value = row.get(df.fieldname)
	if df.fieldtype == "Int" and not df.reqd and not df.read_only and not cint(value):
		return None
	return value


def _section(doc, section, child, rows):
	"""One table of step two as the page paints it: columns, popup fields and saved rows."""
	fieldnames = [f["fieldname"] for f in section["fields"]] + [
		f for f in section["computed"] if f not in {x["fieldname"] for x in section["fields"]}
	]
	hidden = {f["fieldname"] for f in section["fields"] if f.get("column") is False}
	columns = [{"fieldname": f, "label": _(child.get_field(f).label)} for f in fieldnames if f not in hidden]
	fields = []
	for spec in section["fields"]:
		df = child.get_field(spec["fieldname"])
		default = df.default or ""
		if df.fieldname == "panel_type" and doc.subsidy_option == "With Subsidy":
			# Subsidy needs DCR panels, so that is where a new panel row starts.
			default = "DCR"
		if spec.get("choices") == "phase" and doc.get("connection_type"):
			default = doc.connection_type
		hint = spec.get("hint")
		if hint is True:
			hint = df.description or ""
		fields.append({
			"fieldname": df.fieldname, "label": _(df.label), "reqd": bool(df.reqd),
			"input": "select" if spec.get("choices") else INPUT.get(df.fieldtype, "text"),
			"choices": spec.get("choices"), "filter_by": spec.get("filter_by"),
			"default": default, "hint": _(hint) if hint else "",
		})
	rows = [{
		"name": row.name,
		# Rows the estimate computes are refreshed on every save; they are shown, not edited.
		"computed": bool(row.get("source")),
		# An optional count left at 0 was never typed, so the popup shows it blank.
		"values": {f: _editable_value(row, child.get_field(f)) for f in fieldnames},
		"display": {f: _display(row, child.get_field(f)) for f in fieldnames},
	} for row in rows]
	compact = section.get("compact")
	if compact:
		def line(parts, display):
			return " \u00b7 ".join(display[f] + unit for f, unit in parts if display.get(f))
		for payload in rows:
			payload["title"] = line(compact["title"], payload["display"])
			payload["sub"] = line(compact["sub"], payload["display"])
	return {
		"key": section["key"], "label": _(section["label"]), "icon": section["icon"],
		"compact": bool(compact),
		# Which field holds the count, and whether a row can be marked as an Option.
		"count_field": (compact or {}).get("count", "nos"),
		"has_option": any(f["fieldname"] == "is_option" for f in section["fields"]),
		"columns": columns, "fields": fields,
		"rows": rows,
	}


def _sections(doc):
	out = []
	for section in SECTIONS:
		if section.get("only_for") and doc.system_type not in section["only_for"]:
			continue
		child = frappe.get_meta(doc.meta.get_field(section["key"]).options)
		out.append(_section(doc, section, child, doc.get(section["key"])))
	for section in LINKED_SECTIONS:
		if not frappe.has_permission(section["doctype"], "read"):
			continue
		child = frappe.get_meta(frappe.get_meta(section["doctype"]).get_field("items").options)
		rows = [row for record in _linked_records(doc, section) for row in record.items]
		out.append(_section(doc, section, child, rows))
	return out


def _linked_records(doc, section):
	"""The records of a linked section raised against the estimate, oldest first."""
	names = frappe.get_all(section["doctype"], filters={"solar_design_estimate": doc.name},
		pluck="name", order_by="creation asc")
	return [frappe.get_doc(section["doctype"], name) for name in names]


def _save_linked_row(doc, section, values, row=None):
	"""Add an item to the estimate's record of a linked section - making the record on the
	first one - or change an item, and save that record."""
	records = _linked_records(doc, section)
	if row:
		record = next((r for r in records if any(i.name == row for i in r.items)), None)
		if not record:
			frappe.throw(_("That row no longer exists. Reload the page."))
		target = next(i for i in record.items if i.name == row)
	else:
		record = records[-1] if records else frappe.get_doc({
			"doctype": section["doctype"],
			"posting_date": frappe.utils.today(),
			"company": doc.company,
			"lead": doc.lead,
			"solar_consumer": doc.solar_consumer,
			"customer_name": link_title("Solar Consumer" if doc.solar_consumer else "Lead",
				doc.solar_consumer or doc.lead) if (doc.solar_consumer or doc.lead) else None,
			"solar_design_estimate": doc.name,
		})
		target = record.append("items", {})
	for spec in section["fields"]:
		fieldname = spec["fieldname"]
		if fieldname in values:
			target.set(fieldname, values.get(fieldname) if values.get(fieldname) != "" else None)
	if (section["key"] == "special_discount" and target.discount_type == "Percentage"
			and not flt(target.base_amount)):
		# A percentage off what the estimate comes to before any discount.
		target.base_amount = sum(
			line["amount"] for line in doc.commercials()["lines"] if line["key"] != "special_discount"
		)
	record.save()


def _remove_linked_row(doc, section, row):
	"""Drop an item from a linked record; a record left with none is deleted."""
	record = next((r for r in _linked_records(doc, section) if any(i.name == row for i in r.items)), None)
	if not record:
		frappe.throw(_("That row no longer exists. Reload the page."))
	if len(record.items) == 1:
		frappe.delete_doc(section["doctype"], record.name)
		return
	record.remove(next(i for i in record.items if i.name == row))
	record.save()


def builder_state(doc):
	"""Everything step two paints from: the header, each section and the commercials."""
	commercials = doc.commercials()
	for line in commercials["lines"]:
		line["label"] = _(line["label"])
	subject = doc.solar_consumer or doc.lead
	return {
		"name": doc.name,
		"title": link_title("Solar Consumer" if doc.solar_consumer else "Lead", subject) if subject else doc.name,
		"editable": bool(doc.has_permission("write")) and cint(doc.docstatus) == 0,
		# A draft or a submitted estimate can be copied into a new one; a cancelled one cannot.
		"can_save_as": cint(doc.docstatus) in (0, 1) and bool(frappe.has_permission(DOCTYPE, "create")),
		"details_route": details_route(doc.name),
		"pdf_route": "/api/method/a3_sola.api.portal_estimate.download_pdf?name=" + frappe.utils.quote(doc.name),
		"view_route": "/a3solaportal/{0}/{1}".format(SLUG, frappe.utils.quote(doc.name)),
		"summary": [
			{"label": _("Proposed size"), "value": "{0:g} kW".format(flt(doc.final_capacity_kw))},
			{"label": _("Connection"), "value": doc.connection_type or ""},
			{"label": _("System type"), "value": doc.system_type or ""},
			{"label": _("Subsidy"), "value": doc.subsidy_option or ""},
			{"label": _("Package"), "value": link_title("Solar Package", doc.solar_package) if doc.solar_package else "—"},
		],
		"sections": _sections(doc),
		"choices": _choices(doc),
		"commercials": commercials,
		# Said on the last save without stopping it, as the inverter sizing with Options.
		"warnings": list(doc.flags.get("warnings") or []),
	}


@frappe.whitelist()
def state(name):
	return builder_state(_load(name, "read"))


@frappe.whitelist()
def save_row(name, section, values, row=None):
	"""Add a row to one System & Options table, or change one, and save the estimate."""
	doc = _load(name)
	if section in LINKED_BY_KEY:
		_save_linked_row(doc, LINKED_BY_KEY[section], frappe.parse_json(values) or {}, row)
		return builder_state(doc)
	spec = SECTION_BY_KEY.get(section)
	if not spec:
		frappe.throw(_("Unknown section: {0}").format(section))
	values = frappe.parse_json(values) or {}
	allowed = {f["fieldname"] for f in spec["fields"]}
	if row:
		target = next((r for r in doc.get(section) if r.name == row), None)
		if not target:
			frappe.throw(_("That row no longer exists. Reload the page."))
		if target.get("source"):
			frappe.throw(_("This row is worked out by the estimate and cannot be changed here."))
	else:
		target = doc.append(section, {})
	for fieldname in allowed:
		if fieldname in values:
			target.set(fieldname, values.get(fieldname) if values.get(fieldname) not in ("",) else None)
	doc.save()
	return builder_state(doc)


@frappe.whitelist()
def remove_row(name, section, row):
	"""Drop one hand-added row from a System & Options table and save the estimate."""
	doc = _load(name)
	if section in LINKED_BY_KEY:
		_remove_linked_row(doc, LINKED_BY_KEY[section], row)
		return builder_state(doc)
	if section not in SECTION_BY_KEY:
		frappe.throw(_("Unknown section: {0}").format(section))
	target = next((r for r in doc.get(section) if r.name == row), None)
	if not target:
		frappe.throw(_("That row no longer exists. Reload the page."))
	if target.get("source"):
		frappe.throw(_("This row is worked out by the estimate and comes back on every save."))
	doc.remove(target)
	doc.save()
	return builder_state(doc)


def builder_json(doc):
	return json.dumps(builder_state(doc), default=str).replace("</", "<\\/")


@frappe.whitelist()
def download_pdf(name):
	"""The estimate as a PDF to save or send: who it is for, the system and the commercials."""
	from frappe.utils.pdf import get_pdf

	doc = _load(name, "read")
	html = frappe.render_template("a3_sola/templates/print/design_estimate.html", {
		"doc": doc,
		"state": builder_state(doc),
		"profile": subject_profile(doc.lead, doc.solar_consumer),
		"company": doc.company or "",
		"money": lambda value: frappe.utils.fmt_money(value, currency="INR"),
		"_": _,
	})
	frappe.local.response.filename = "{0}.pdf".format(doc.name)
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "download"


@frappe.whitelist()
def whatsapp_link(name):
	"""A wa.me link to the consumer (else the lead), prefilled with the estimate's summary.

	Opens WhatsApp with the message ready to send, as the proposal's button does; it does
	not send on anyone's behalf. The PDF is not attached - wa.me cannot carry a file - so
	it is downloaded beside it and sent in the chat.
	"""
	from a3_sola.api import outreach

	doc = _load(name, "read")
	mobile, person = None, None
	if doc.solar_consumer:
		mobile, person = frappe.db.get_value("Solar Consumer", doc.solar_consumer, ["mobile_no", "consumer_name"]) or (None, None)
	if not mobile and doc.lead:
		mobile, person = frappe.db.get_value("Lead", doc.lead, ["mobile_no", "lead_name"]) or (None, None)
	if not mobile:
		frappe.throw(_("Neither the consumer nor the lead has a mobile number to send to."))
	commercials = doc.commercials()
	package = link_title("Solar Package", doc.solar_package) if doc.solar_package else ""
	lines = [
		_("Dear {0},").format(person or _("Sir/Madam")),
		"",
		_("Here is the solar design estimate {0} prepared for you.").format(doc.name),
		_("System: {0:g} kW, {1}, {2}").format(flt(doc.final_capacity_kw), doc.connection_type or "", doc.system_type or "").strip(", "),
	]
	if package:
		lines.append(_("Package: {0}").format(package))
	lines += [
		_("Estimated total: {0}").format(frappe.utils.fmt_money(commercials["total"], currency="INR")),
		"",
		_("The detailed estimate PDF follows. Please reach out with any questions."),
		"",
		doc.company or "",
	]
	return outreach.whatsapp_link(mobile, "\n".join(lines).strip())


@frappe.whitelist()
def save_as(name):
	"""Copy an estimate into a new draft - the desk's Duplicate - and say where it opens.

	`frappe.copy_doc` copies what the desk's Duplicate copies, child tables included, and
	leaves out the fields marked not to be copied. The copy is dated today, takes the next
	number on save, and opens on its details step for the person to review.
	"""
	source = _load(name, "read")
	if cint(source.docstatus) == 2:
		frappe.throw(_("A cancelled design estimate cannot be copied. Amend it instead."))
	frappe.has_permission(DOCTYPE, "create", throw=True)
	copy = frappe.copy_doc(source)
	copy.estimate_date = frappe.utils.today()
	copy.insert()
	return {"name": copy.name, "route": details_route(copy.name)}
