# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The portal's design estimate builder: details first, then the system, option by option.

Step one captures the Estimate Details tab and its options: one row per package offered,
each with the panel, inverter and battery chosen from that package. Step two has a tab per
option, each the system and commercials of that option, one System & Options table at a
time. A change in a tab is worked out on the server - the controller, not this module,
computes the counts, the expense rows and the prices - and held until that tab's Save: the
recommended option saves this estimate, every other option is saved as an estimate of its
own for the same lead, so the options can be compared side by side and quoted.
"""

import json
import re

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
	("Customer", ("lead", "solar_consumer", "site_survey", "estimate_date", "tariff_code", "building_type", "backup_load_kw")),
	# The options: one row per package and sizing, the recommended row the estimate's own.
	# Capacity before the package: the package list follows it, as it follows the rest.
	("Package & Options", ("connection_type", "system_type", "subsidy_option", "subsidy_scheme",
		"override_capacity_kw", "solar_package")),
)

# What each option row chooses from its package, after the package and sizing fields.
COMPONENT_FIELDS = (
	{"fieldname": "panel_make", "label": "Solar Panel", "key": "panels"},
	{"fieldname": "inverter_make", "label": "Inverter", "key": "inverters"},
	{"fieldname": "battery_make", "label": "Battery", "key": "batteries", "only_for": ("Off-Grid", "Hybrid")},
)

# A package name's trailing subsidy scheme, which the package list on an option leaves off.
SCHEME_SUFFIX = re.compile(r"\s*\((?:PM Surya Ghar|Non-Subsidy)\)\s*$", re.IGNORECASE)

# Rebuilt from the package when an option is first worked out as an estimate of its own.
KIT_TABLES = ("panels", "inverters", "batteries", "bos_items", "options", "quoted_options",
	"kseb_expenses", "mounting_expenses", "installation_expenses", "optional_add_ons", "cashflow")
KIT_FIELDS = ("equipment_package", "bos_package", "bos_basis", "included_inverter_options",
	"excluded_inverter_makes", "recommended_option")
# Rows worked out in memory, before a save, are named with this so a change can point at them.
TEMP_ROW = "tmp-"

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
		{"fieldname": "specification", "column": False, "hint": "Printed in the proposal after the rating, e.g. Hybrid with MPPT and Online Monitoring."},
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
		{"fieldname": "specification", "column": False, "hint": "Printed in the proposal after the voltage and capacity."},
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
		{"fieldname": "component_makes", "column": False, "hint": "One line per part, e.g. Isolator - ABB. Printed in place of the make."},
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

# After the charges: the estimate's own table of extras offered beside the system, copied
# from the package. An Option is shown and printed in the proposal; one that is not is priced.
TRAILING_SECTIONS = (
	# The Solar Panel popup's fields, after the add-on's own type and item: an extra panel is
	# chosen as a panel is. Not an Option, it is added to the commercials.
	{"key": "optional_add_ons", "label": "Optional Add-ons", "icon": "star", "fields": (
		{"fieldname": "add_on_type", "choices": "add_on_type"},
		{"fieldname": "item", "column": False, "hint": "Printed in the proposal. An Extra Panel left blank is named from its panel."},
		{"fieldname": "panel_type", "choices": "panel_type"},
		{"fieldname": "panel_capacity_wp"},
		{"fieldname": "panel_count", "column": False, "hint": True},
		{"fieldname": "panel_variant", "choices": "module_technology"},
		{"fieldname": "panel_make", "choices": "module_make", "filter_by": "panel_variant"},
		{"fieldname": "is_option", "choices": "yes_no", "hint": "Yes: offered beside the system, not added to the commercials. No: added to the total."},
		{"fieldname": "rate"},
	), "computed": ("nos", "amount"),
		"compact": {"title": (("add_on_type", ""), ("panel_make", ""), ("panel_capacity_wp", " Wp")),
			"sub": (("item", ""),)}},
)
SECTION_BY_KEY.update({section["key"]: section for section in TRAILING_SECTIONS})

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
				elif df.options == "Solar Package":
					# Retired packages are not offered; one already on the estimate still shows below.
					choices = link_choices(df.options, filters=[["is_active", "=", 1]])
				else:
					choices = link_choices(df.options)
				if value and not any(c["value"] == value for c in choices):
					choices.insert(0, {"value": value, "label": link_title(df.options, value)})
				if df.options == "Solar Package":
					# Each package carries the phases it has inverters for, so a row lists only
					# the packages for its connection type.
					from a3_sola.solar_crm.doctype.solar_package.solar_package import package_phases

					info = {r.name: r for r in frappe.get_all("Solar Package", fields=["name", "is_dcr_compliant", "system_type", "capacity_kw"],
						filters={"name": ["in", [c["value"] for c in choices]]})}
					for c in choices:
						c["phases"] = "|".join(sorted(package_phases(c["value"])))
						pkg = info.get(c["value"]) or frappe._dict()
						# A DCR package is a subsidy package, so each subsidy choice lists its own.
						c["dcr"] = 1 if pkg.is_dcr_compliant else 0
						# An On-Grid estimate lists On-Grid packages, a Hybrid one Hybrid packages.
						c["system_type"] = pkg.system_type or ""
						# The capacity typed on the option narrows the list to packages of that size.
						c["capacity"] = "{0:g}".format(flt(pkg.capacity_kw)) if pkg.capacity_kw else ""
						# The list already follows the option's Subsidy, so the scheme in brackets
						# at the end of the name ("(PM Surya Ghar)", "(Non-Subsidy)") is not repeated.
						c["label"] = SCHEME_SUFFIX.sub("", c["label"]) or c["label"]
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
	columns[1]["rows"] = option_rows(doc, columns[1]["fields"])
	columns[1]["components"] = [
		{"fieldname": c["fieldname"], "label": _(c["label"]), "key": c["key"], "only_for": "|".join(c.get("only_for") or ())}
		for c in COMPONENT_FIELDS
	]
	# Worked out by the estimate, shown beside the package once there is one.
	columns[1]["facts"] = [
		{"label": _("DCR Compliant"), "value": _("Yes") if doc.is_dcr_compliant else _("No")},
		{"label": _("Proposed System Size (kW)"), "value": "{0:g}".format(flt(doc.final_capacity_kw))},
	] if doc and doc.solar_package else []
	return columns


def option_rows(doc, fields):
	"""The option rows step one shows: the estimate's own, else one from the fields' values.

	A row saved as an estimate of its own (from its tab on step two) says so, and is shown
	as it was saved: it is changed on that estimate.
	"""
	names = [f["fieldname"] for f in fields] + [c["fieldname"] for c in COMPONENT_FIELDS]
	if doc and doc.get("sizing_options"):
		rows = []
		# The recommended option first: the first ticked option is the recommended one.
		for row in sorted(doc.sizing_options, key=lambda r: (not r.is_recommended, r.idx)):
			values = {}
			for fieldname in names:
				value = row.get(fieldname)
				if fieldname == "override_capacity_kw":
					value = "{0:g}".format(flt(value)) if flt(value) else ""
				values[fieldname] = "" if value is None else str(value)
			saved = row.design_estimate if row.design_estimate and row.design_estimate != doc.name else ""
			rows.append({"name": row.name, "recommended": bool(row.is_recommended), "values": values,
				"package_cost_label": package_cost_label(row.package_cost), "saved_as": saved,
				"saved_route": design_route(saved) if saved else ""})
		return rows
	values = {f["fieldname"]: f["value"] for f in fields}
	values.update({c["fieldname"]: "" for c in COMPONENT_FIELDS})
	if not flt(values.get("override_capacity_kw")):
		values["override_capacity_kw"] = ""
	return [{"name": "", "recommended": True, "values": values, "package_cost_label": "", "saved_as": "", "saved_route": ""}]


def package_cost_label(amount):
	return _("Package price {0}").format(frappe.utils.fmt_money(amount, currency="INR")) if flt(amount) else ""


def package_choices_json(columns):
	"""Each package on offer's cost and its panels, inverters and batteries, for step one to
	fill a row's choices from when its package is picked."""
	from a3_sola.solar_crm.doctype.solar_package.solar_package import package_components

	field = next((f for f in columns[1]["fields"] if f["fieldname"] == "solar_package"), None)
	out = {}
	for option in (field or {}).get("options") or []:
		if option.get("value"):
			out[option["value"]] = package_components(option["value"])
	return json.dumps(out, default=str).replace("</", "<\\/")


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
		existing = {row.name: row for row in doc.get("sizing_options") or []}
		rows = []
		for row in options:
			if not isinstance(row, dict):
				continue
			old = existing.get(row.get("name")) if row.get("name") else None
			if old and old.design_estimate and old.design_estimate != doc.name:
				# Saved as an estimate of its own: kept as saved, and changed on that estimate.
				old.is_recommended = 1 if row.get("is_recommended") else 0
				rows.append(old)
				continue
			entry = {fieldname: (row.get(fieldname) or None) for fieldname in sizing_fields}
			entry.update({c["fieldname"]: row.get(c["fieldname"]) or None for c in COMPONENT_FIELDS})
			entry["override_capacity_kw"] = flt(row.get("override_capacity_kw")) or None
			entry["is_recommended"] = 1 if row.get("is_recommended") else 0
			if old:
				entry["name"] = old.name  # the same option: its tab and saved estimate follow it
			rows.append(entry)
		doc.set("sizing_options", [])
		for row in rows:
			doc.append("sizing_options", row)
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
		("add_on_type", "Design Estimate Add-on", "add_on_type"),
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
		# Part of the solar package: its price is the package's, not the row's.
		"included": bool(doc.solar_package and row.get("in_package")),
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
		# Charges are records of their own raised against a saved estimate, so an option
		# not saved yet has none.
		if doc.is_new() or not frappe.has_permission(section["doctype"], "read"):
			continue
		child = frappe.get_meta(frappe.get_meta(section["doctype"]).get_field("items").options)
		rows = [row for record in _linked_records(doc, section) for row in record.items]
		out.append(_section(doc, section, child, rows))
	for section in TRAILING_SECTIONS:
		child = frappe.get_meta(doc.meta.get_field(section["key"]).options)
		out.append(_section(doc, section, child, doc.get(section["key"])))
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


def builder_state(doc, editable=None):
	"""Everything a tab of step two paints from: the header, each section and the commercials.

	`doc` may be an option worked out in memory and not saved yet; `editable` then says
	whether the person may save it.
	"""
	commercials = doc.commercials()
	for line in commercials["lines"]:
		line["label"] = _(line["label"])
	subject = doc.solar_consumer or doc.lead
	saved = not doc.is_new()
	if editable is None:
		editable = bool(doc.has_permission("write")) and cint(doc.docstatus) == 0
	return {
		"name": doc.name if saved else "",
		"saved": saved,
		"title": link_title("Solar Consumer" if doc.solar_consumer else "Lead", subject) if subject else (doc.name or ""),
		"editable": bool(editable),
		"docstatus": cint(doc.docstatus),
		"pdf_route": "/api/method/a3_sola.api.portal_estimate.download_pdf?name=" + frappe.utils.quote(doc.name) if saved else "",
		"view_route": "/a3solaportal/{0}/{1}".format(SLUG, frappe.utils.quote(doc.name)) if saved else "",
		"summary": [
			{"label": _("Proposed size"), "value": "{0:g} kW".format(flt(doc.final_capacity_kw))},
			{"label": _("Connection"), "value": doc.connection_type or ""},
			{"label": _("System type"), "value": doc.system_type or ""},
			{"label": _("Subsidy"), "value": doc.subsidy_option or ""},
			{"label": _("Package"), "value": link_title("Solar Package", doc.solar_package) if doc.solar_package else "—"},
			{"label": _("Package price"), "value": frappe.utils.fmt_money(doc.package_price(), currency="INR") if doc.solar_package else "—"},
		],
		"sections": _sections(doc),
		"choices": _choices(doc),
		"commercials": commercials,
		# The proposal this saved option is offered in, or the way to one.
		"proposal_action": _proposal_action(doc.name) if saved else None,
		# Said on the last change without stopping it, as the inverter sizing with Options.
		"warnings": list(doc.flags.get("warnings") or []),
	}


def _proposal_action(name):
	from a3_sola.api import portal_proposal

	return portal_proposal.proposal_action(name)


# --------------------------------------------------------------- option tabs
def root_of(doc):
	"""The estimate whose option `doc` was saved from, else `doc` itself: the estimate whose
	option rows are the tabs of step two."""
	parent = doc.get("parent_estimate")
	if (parent and frappe.db.exists(DOCTYPE, parent) and frappe.has_permission(DOCTYPE, "read", parent)
			and frappe.db.exists("Design Estimate Sizing Option",
				{"parent": parent, "parenttype": DOCTYPE, "design_estimate": doc.name})):
		return frappe.get_doc(DOCTYPE, parent)
	return doc


def _tab_target(root, option):
	"""(option row, estimate) for a tab: the recommended row is the root estimate itself,
	another row the estimate it was saved as, or None while it is not saved."""
	row = next((r for r in root.get("sizing_options") or [] if r.name == option), None) if option else None
	if option and not row:
		frappe.throw(_("That option is no longer on {0}. Reload the page.").format(root.name))
	if not row or row.is_recommended:
		return row, root.name
	if row.design_estimate and frappe.db.exists(DOCTYPE, row.design_estimate):
		return row, row.design_estimate
	return row, None


def option_key(root, doc):
	"""The tab `doc` is shown in: its option row on the root, else the root's own."""
	if doc.name != root.name:
		row = next((r for r in root.get("sizing_options") or [] if r.design_estimate == doc.name), None)
		if row:
			return row.name
	row = next((r for r in root.get("sizing_options") or [] if r.is_recommended), None)
	return row.name if row else ""


def option_tabs(root):
	"""One tab per option row of the root estimate, described by what it chooses."""
	makes = {}

	def make_name(name):
		if name and name not in makes:
			makes[name] = frappe.db.get_value("Component Make", name, "make_name") or name
		return makes.get(name) or ""

	tabs = []
	rows = sorted(root.get("sizing_options") or [], key=lambda r: r.idx)
	for n, row in enumerate(rows, start=1):
		_row, estimate = _tab_target(root, row.name)
		source, docstatus = row, cint(root.docstatus)
		if estimate and estimate != root.name:
			# A saved option is described as it was saved: it may have been changed there.
			source = frappe.get_all("Design Estimate Sizing Option", filters={"parent": estimate, "parenttype": DOCTYPE,
				"is_recommended": 1}, fields=["*"], limit=1)
			source = source[0] if source else row
			docstatus = cint(frappe.db.get_value(DOCTYPE, estimate, "docstatus"))
		tabs.append({
			"key": row.name, "number": n, "recommended": bool(row.is_recommended),
			"estimate": estimate or "", "docstatus": docstatus,
			"package": link_title("Solar Package", source.solar_package) if source.solar_package else _("No package"),
			"capacity": "{0:g} kW".format(flt(source.override_capacity_kw)) if flt(source.override_capacity_kw) else "",
			"parts": [p for p in (make_name(source.panel_make), make_name(source.inverter_make), make_name(source.battery_make)) if p],
			"package_cost": flt(source.package_cost),
		})
	if not tabs:
		tabs.append({"key": "", "number": 1, "recommended": True, "estimate": root.name, "docstatus": cint(root.docstatus),
			"package": link_title("Solar Package", root.solar_package) if root.solar_package else _("No package"),
			"capacity": "", "parts": [], "package_cost": 0.0})
	return tabs


def _new_option_estimate(root, row):
	"""An option row worked out as an estimate of its own, not saved: the root's details
	with this row as its only, recommended, option, and the kit rebuilt from its package."""
	from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import SIZING_FIELDS

	doc = frappe.copy_doc(root)
	doc.parent_estimate = root.name
	doc.source_option = row.name
	values = {field: row.get(field) for field in SIZING_FIELDS}
	values.update({c["fieldname"]: row.get(c["fieldname"]) for c in COMPONENT_FIELDS})
	doc.set("sizing_options", [])
	doc.append("sizing_options", {**values, "is_recommended": 1, "option_notes": row.option_notes})
	for field in SIZING_FIELDS:
		doc.set(field, row.get(field))
	for table in KIT_TABLES:
		doc.set(table, [])
	for field in KIT_FIELDS:
		doc.set(field, None)
	return doc


def _compute(doc, tag):
	"""Work an estimate out as a save would, without saving it, and name its new rows so a
	change can point at them. Replaying the same changes names them the same again."""
	doc.flags.warnings = []
	doc._set_defaults()
	doc.run_method("before_validate")
	doc.run_method("validate")
	for child in doc.get_all_children():
		if not child.name:
			child.name = "{0}{1}-{2}-{3}".format(TEMP_ROW, tag, child.parentfield, child.idx)


def _apply_change(doc, change):
	"""One change to a System & Options table: {section, values, row, action}."""
	section = (change or {}).get("section")
	spec = SECTION_BY_KEY.get(section)
	if not spec:
		frappe.throw(_("Unknown section: {0}").format(section))
	row = change.get("row")
	target = next((r for r in doc.get(section) if r.name == row), None) if row else None
	if row and not target:
		frappe.throw(_("That row no longer exists. Reload the page."))
	if target and target.get("source"):
		frappe.throw(_("This row is worked out by the estimate and cannot be changed here."))
	if change.get("action") == "remove":
		if not target:
			frappe.throw(_("Choose a row to remove."))
		doc.remove(target)
		return
	if not target:
		target = doc.append(section, {})
	values = change.get("values") or {}
	for fieldname in {f["fieldname"] for f in spec["fields"]}:
		if fieldname in values:
			target.set(fieldname, _typed(target, fieldname, values.get(fieldname)))


def _typed(row, fieldname, value):
	"""A value from the form as its field holds it. The form sends text, and "0" is true to
	Python: an Option set to No would read as ticked, and a table's one priced row as none."""
	if value == "" or value is None:
		return None
	df = row.meta.get_field(fieldname)
	fieldtype = df.fieldtype if df else None
	if fieldtype in ("Check", "Int"):
		return cint(value)
	if fieldtype in ("Float", "Currency", "Percent"):
		return flt(value)
	return value


def _work(doc, changes):
	"""Apply a tab's unsaved changes in order, working the estimate out after each, as
	each would have been saved. The state before each change is what the estimate tells a
	row just changed by (an Option just unticked is the one priced)."""
	if doc.is_new():
		_compute(doc, "0")
	for n, change in enumerate(changes or [], start=1):
		doc._doc_before_save = frappe.get_doc(doc.as_dict())
		_apply_change(doc, change)
		_compute(doc, str(n))


def _tab_doc(root, option, changes, permtype="read"):
	"""(doc, editable) for a tab, its unsaved changes applied: read fresh, as each tab is
	worked out on its own copy."""
	row, estimate = _tab_target(root, option)
	if estimate:
		doc = _load(estimate, permtype)
		editable = bool(doc.has_permission("write")) and cint(doc.docstatus) == 0
	else:
		if permtype == "write":
			frappe.has_permission(DOCTYPE, "create", throw=True)
		doc = _new_option_estimate(frappe.get_doc(DOCTYPE, root.name), row)
		editable = bool(frappe.has_permission(DOCTYPE, "create"))
	if changes and not editable:
		frappe.throw(_("This option cannot be changed."), frappe.PermissionError)
	_work(doc, changes)
	return doc, editable


def _payload(root, option, doc, editable=None):
	frappe.local.message_log = []  # worked out, not saved: the page shows its own messages
	root_editable = bool(root.has_permission("write")) and cint(root.docstatus) == 0
	return {"tabs": option_tabs(root), "option": option or "", "root": root.name,
		"details_route": details_route(root.name) if root_editable else "",
		# Options can be taken off a draft estimate the person may change.
		"can_remove": root_editable and len(root.get("sizing_options") or []) > 1,
		"state": builder_state(doc, editable)}


@frappe.whitelist()
def remove_option(name, option):
	"""Take an option off the estimate - the row on step one - and say where to reload.

	The recommended option is the estimate itself: taking it off makes the next option the
	recommended one, and the estimate is rebuilt on it. An option already saved as an
	estimate of its own leaves that estimate as it is.
	"""
	doc = _load(name)
	rows = sorted(doc.get("sizing_options") or [], key=lambda r: r.idx)
	row = next((r for r in rows if r.name == option), None)
	if not row:
		frappe.throw(_("That option is no longer on {0}. Reload the page.").format(doc.name))
	if len(rows) == 1:
		frappe.throw(_("An estimate keeps at least one option."))
	if row.is_recommended:
		heir = next((r for r in rows if r is not row
			and not (r.design_estimate and r.design_estimate != doc.name)), None)
		if not heir:
			frappe.throw(_("Every other option is saved as an estimate of its own, so this one stays as {0}.").format(doc.name))
		heir.is_recommended = 1
	doc.remove(row)
	doc.save()
	return {"route": design_route(doc.name)}


def _changes(ops):
	changes = frappe.parse_json(ops) if ops else []
	return [c for c in changes if isinstance(c, dict)] if isinstance(changes, list) else []


@frappe.whitelist()
def tab_state(name, option=None, ops=None):
	"""A tab of step two with its unsaved changes applied, nothing saved."""
	root = _load(name, "read")
	doc, editable = _tab_doc(root, option, _changes(ops))
	return _payload(root, option, doc, editable)


@frappe.whitelist()
def save_tab(name, option=None, ops=None):
	"""Save a tab: the recommended option into this estimate, any other option into the
	estimate it was saved as - made, for the same lead, the first time it is saved."""
	root = _load(name, "read")
	row, estimate = _tab_target(root, option)
	doc, _editable = _tab_doc(root, option, _changes(ops), "write")
	for child in doc.get_all_children():
		if (child.name or "").startswith(TEMP_ROW):
			child.name = None
			child.set("__islocal", 1)
	if estimate:
		doc.save()
	else:
		doc._doc_before_save = None
		doc.insert()
		# A child row's link, set directly, so the estimate open on step one is not
		# reported as changed by someone else.
		frappe.db.set_value("Design Estimate Sizing Option", row.name, "design_estimate", doc.name, update_modified=False)
	root = frappe.get_doc(DOCTYPE, root.name)
	return _payload(root, option, frappe.get_doc(DOCTYPE, doc.name))


def _linked_change(name, option, ops, change):
	"""A charge record's row changed on a saved tab's estimate, at once; then the tab with
	its unsaved changes."""
	root = _load(name, "read")
	_row, estimate = _tab_target(root, option)
	if not estimate:
		frappe.throw(_("Save this option first: its charges are kept against the saved estimate."))
	change(_load(estimate))
	doc, editable = _tab_doc(root, option, _changes(ops))
	return _payload(root, option, doc, editable)


@frappe.whitelist()
def save_linked_row(name, section, values, option=None, row=None, ops=None):
	"""Add or change an Additional Structure, Additional Cable or Special Discount row."""
	if section not in LINKED_BY_KEY:
		frappe.throw(_("Unknown section: {0}").format(section))
	return _linked_change(name, option, ops,
		lambda doc: _save_linked_row(doc, LINKED_BY_KEY[section], frappe.parse_json(values) or {}, row))


@frappe.whitelist()
def remove_linked_row(name, section, row, option=None, ops=None):
	if section not in LINKED_BY_KEY:
		frappe.throw(_("Unknown section: {0}").format(section))
	return _linked_change(name, option, ops, lambda doc: _remove_linked_row(doc, LINKED_BY_KEY[section], row))


@frappe.whitelist()
def compare(name, pending=None):
	"""Every option side by side - its kit and commercials - with each tab's unsaved
	changes applied. An option that cannot be worked out says why instead."""
	root = _load(name, "read")
	pending = frappe.parse_json(pending) if pending else {}
	pending = pending if isinstance(pending, dict) else {}
	out = []
	for tab in option_tabs(root):
		entry = {"key": tab["key"], "number": tab["number"], "recommended": tab["recommended"],
			"estimate": tab["estimate"], "package": tab["package"], "unsaved": bool(pending.get(tab["key"]))}
		try:
			doc, _editable = _tab_doc(root, tab["key"], _changes(pending.get(tab["key"])))
		except frappe.ValidationError as error:
			entry["error"] = frappe.utils.strip_html(str(error)) or _("This option could not be worked out.")
			out.append(entry)
			continue
		state = builder_state(doc, False)
		priced = {}
		for section in state["sections"]:
			if section["key"] in ("panels", "inverters", "batteries"):
				row = next((r for r in section["rows"] if not cint(r["values"].get("is_option"))), None)
				priced[section["key"]] = row["title"] if row else ""
		entry.update({
			"size": "{0:g} kW".format(flt(doc.final_capacity_kw)),
			"panel_kwp": "{0:g} kWp".format(doc.panel_capacity_kwp()),
			"inverter_kw": "{0:g} kW".format(doc.inverter_capacity_kw()),
			"package_cost": next((s["value"] for s in state["summary"] if s["label"] == _("Package price")), ""),
			"panel": priced.get("panels", ""), "inverter": priced.get("inverters", ""), "battery": priced.get("batteries", ""),
			"lines": [{"key": line["key"], "label": line["label"], "amount": line["amount"]} for line in state["commercials"]["lines"]],
			"subtotal": state["commercials"]["subtotal"], "gst_amount": state["commercials"]["gst_amount"],
			"total": state["commercials"]["total"],
		})
		out.append(entry)
	frappe.local.message_log = []
	return out


def page_json(doc):
	"""Step two's first paint: the tabs of `doc`'s root estimate, on the tab `doc` is."""
	root = root_of(doc)
	option = option_key(root, doc)
	editable = None
	if doc.name != root.name or not option:
		target = doc
	else:
		target, editable = _tab_doc(root, option, [])
	payload = _payload(root, option, target, editable)
	return json.dumps(payload, default=str).replace("</", "<\\/")


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
