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
from a3_sola.api.portal_fields import link_choices, link_title
from a3_sola.solar_crm.doctype.balance_of_system_package.balance_of_system_package import MAKE_TYPE

DOCTYPE = "Solar Design Estimate"
SLUG = "design-estimates"

# Step one, as two columns: who it is for, then what is being proposed.
DETAIL_COLUMNS = (
	("Consumer", ("lead", "solar_consumer", "site_survey", "estimate_date", "electricity_tariff")),
	("Package & sizing", ("connection_type", "override_capacity_kw", "subsidy_option", "subsidy_scheme",
		"solar_package", "system_type")),
)

# Step two. Each field names the choices it draws on, where it has any; `filter_by` narrows
# a make list to the variant, type or item chosen beside it.
SECTIONS = (
	{"key": "panels", "label": "Solar Panel", "icon": "bolt", "fields": (
		{"fieldname": "panel_type", "choices": "panel_type"},
		{"fieldname": "panel_capacity_wp"},
		{"fieldname": "panel_variant", "choices": "module_technology"},
		{"fieldname": "panel_make", "choices": "module_make", "filter_by": "panel_variant"},
		{"fieldname": "rate"},
	), "computed": ("nos", "amount")},
	{"key": "inverters", "label": "Inverter", "icon": "power", "fields": (
		{"fieldname": "inverter_type", "choices": "inverter_technology"},
		{"fieldname": "inverter_capacity_kw"},
		{"fieldname": "inverter_phase", "choices": "phase"},
		{"fieldname": "inverter_make", "choices": "inverter_make", "filter_by": "inverter_type"},
		{"fieldname": "rate"},
	), "computed": ("nos", "amount")},
	{"key": "batteries", "label": "Battery", "icon": "stack", "only_for": ("Off-Grid", "Hybrid"), "fields": (
		{"fieldname": "battery_voltage"},
		{"fieldname": "battery_phase", "choices": "phase"},
		{"fieldname": "battery_capacity_ah"},
		{"fieldname": "battery_variant", "choices": "battery_technology"},
		{"fieldname": "battery_make", "choices": "battery_make", "filter_by": "battery_variant"},
		{"fieldname": "nos"},
		{"fieldname": "rate"},
	), "computed": ("total_energy_kwh", "amount")},
	{"key": "bos_items", "label": "Balance of System", "icon": "box", "fields": (
		{"fieldname": "item", "choices": "bos_item"},
		{"fieldname": "phase", "choices": "phase"},
		{"fieldname": "specification"},
		{"fieldname": "make", "choices": "bos_make", "filter_by": "item"},
		{"fieldname": "numbers"},
		{"fieldname": "rate"},
	), "computed": ("amount",)},
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

INPUT = {
	"Select": "select", "Link": "select", "Int": "number", "Float": "number", "Currency": "number",
	"Percent": "number", "Date": "date", "Small Text": "textarea", "Text": "textarea",
}


# ------------------------------------------------------------------ step one
def detail_columns(doc=None):
	"""The Estimate Details form as two columns of field specs, valued from `doc` if given."""
	meta = frappe.get_meta(DOCTYPE)
	columns = []
	for title, fieldnames in DETAIL_COLUMNS:
		fields = []
		for fieldname in fieldnames:
			df = meta.get_field(fieldname)
			value = doc.get(fieldname) if doc else (df.default or "")
			if fieldname == "estimate_date" and not value:
				value = frappe.utils.today()
			spec = {
				"fieldname": fieldname, "label": _(df.label), "input": INPUT.get(df.fieldtype, "text"),
				"reqd": bool(df.reqd), "hint": _(df.description) if df.description else "",
				"value": "" if value is None else str(value),
			}
			if df.fieldtype == "Select":
				spec["options"] = [{"value": o, "label": o or "—"} for o in (df.options or "").split("\n")]
			elif df.fieldtype == "Link":
				choices = link_choices(df.options)
				if value and not any(c["value"] == value for c in choices):
					choices.insert(0, {"value": value, "label": link_title(df.options, value)})
				spec["options"] = [{"value": "", "label": "—"}] + choices
			if fieldname == "subsidy_scheme":
				spec["show_when"] = "subsidy_option=With Subsidy"
			fields.append(spec)
		columns.append({"title": _(title), "fields": fields})
	return columns


@frappe.whitelist()
def save_details(values, name=None):
	"""Create the estimate, or update its details, from step one; return where step two is."""
	values = frappe.parse_json(values) or {}
	if name:
		doc = _load(name)
	else:
		frappe.has_permission(DOCTYPE, "create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		doc.company = frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
	allowed = {fieldname for _title, fieldnames in DETAIL_COLUMNS for fieldname in fieldnames}
	for fieldname in allowed:
		if fieldname in values:
			doc.set(fieldname, values.get(fieldname) or None)
	if doc.subsidy_option != "With Subsidy":
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
		"phase": [{"value": v, "label": v} for v in ("Single Phase", "Three Phase")],
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
	if df.fieldtype == "Currency":
		return frappe.utils.fmt_money(value, currency="INR")
	if df.fieldtype in ("Float", "Int"):
		return "{0:g}".format(flt(value))
	return str(value)


def _sections(doc):
	out = []
	for section in SECTIONS:
		if section.get("only_for") and doc.system_type not in section["only_for"]:
			continue
		child = frappe.get_meta(doc.meta.get_field(section["key"]).options)
		fieldnames = [f["fieldname"] for f in section["fields"]] + [
			f for f in section["computed"] if f not in {x["fieldname"] for x in section["fields"]}
		]
		columns = [{"fieldname": f, "label": _(child.get_field(f).label)} for f in fieldnames]
		fields = []
		for spec in section["fields"]:
			df = child.get_field(spec["fieldname"])
			default = df.default or ""
			if df.fieldname == "panel_type" and doc.subsidy_option == "With Subsidy":
				# Subsidy needs DCR panels, so that is where a new panel row starts.
				default = "DCR"
			fields.append({
				"fieldname": df.fieldname, "label": _(df.label), "reqd": bool(df.reqd),
				"input": "select" if spec.get("choices") else INPUT.get(df.fieldtype, "text"),
				"choices": spec.get("choices"), "filter_by": spec.get("filter_by"),
				"default": default,
			})
		rows = []
		for row in doc.get(section["key"]):
			rows.append({
				"name": row.name,
				# Rows the estimate computes are refreshed on every save; they are shown, not edited.
				"computed": bool(row.get("source")),
				"values": {f: row.get(f) for f in fieldnames},
				"display": {f: _display(row, child.get_field(f)) for f in fieldnames},
			})
		out.append({
			"key": section["key"], "label": _(section["label"]), "icon": section["icon"],
			"columns": columns, "fields": fields, "rows": rows,
		})
	return out


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
		"details_route": details_route(doc.name),
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
	}


@frappe.whitelist()
def state(name):
	return builder_state(_load(name, "read"))


@frappe.whitelist()
def save_row(name, section, values, row=None):
	"""Add a row to one System & Options table, or change one, and save the estimate."""
	doc = _load(name)
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
