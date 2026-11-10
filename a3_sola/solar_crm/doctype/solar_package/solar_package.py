# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The client's package master, mirrored field for field.

They already maintain one in a macro workbook with twenty-six columns per package and
generate their proposals from it, so this is their field list, not an invention. Two
inverter options sit side by side on ONE package because that is how they quote - the same
array offered with a string inverter and with an optimiser or microinverter. It is not two
packages.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from a3_sola.api import calculations, regulation, statutory
from a3_sola.api.expenses import fill_expense_tables, price_by_rate
from a3_sola.api.settings import get_value
from a3_sola.api.uniqueness import assert_unique_in_company
from a3_sola.solar_crm.doctype.inverter_model import inverter_model


class SolarPackage(Document):
	def onload(self):
		"""The groups an add-on's Item Group is one of, for the desk's dropdown."""
		from a3_sola.api.package_items import add_on_groups

		self.set_onload("add_on_groups", add_on_groups())

	def before_insert(self):
		"""A new package offers the usual add-ons until its own are entered."""
		if not self.get("optional_add_ons"):
			self.set("optional_add_ons", default_add_ons(self))

	def validate(self):
		self.fill_company()
		from a3_sola.api import package_kits

		# A bundle or BOM chosen on a tab is replaced by its items (package_kits).
		package_kits.open_up(self)
		assert_unique_in_company(self, ["specification_code"])
		from a3_sola.api import package_items

		package_items.validate(self)
		self.validate_dcr_items()
		self.validate_one_default("modules", _("module"))
		self.total_the_panels()
		self.fill_from_inverter_models()
		self.fill_inverter_phases()
		self.validate_one_default("inverters", _("inverter"))
		self.total_the_inverters()
		self.topology_from_inverters()
		from a3_sola.api import package_bom_tables

		package_bom_tables.validate(self)
		self.validate_one_default_per_type()
		self.no_dcdb_for_microinverter()
		self.name_extra_panel_add_ons()
		self.warranty_extension_from_model()
		self.total_the_add_ons()
		self.total_the_expenses()
		self.compute_batteries()
		self.check_pricing_options()
		self.compute_expenses()
		self.full_bom()
		# Once every amount is worked out: each Pricing Options row's cost is made of them.
		self.cost_the_pricing_options()
		self.total_the_package()
		self.check_regulation()
		self.validate_payment_terms()

	def on_update(self):
		"""Drop the cached copy once the save is committed.

		Validating reads this package back by name through the default-row helpers, which
		caches the copy still in the database - the one from before this save. Left there,
		every estimate priced from the cache would see the old prices and options.
		"""
		frappe.clear_document_cache(self.doctype, self.name)
		frappe.db.after_commit.add(lambda: frappe.clear_document_cache(self.doctype, self.name))

	def fill_from_inverter_models(self):
		"""A row on a price-list model takes its make, size, phase and unit rate from it.

		The specification is left as typed: the estimate and the proposal read it.
		"""
		for row in self.get("inverters") or []:
			if row.get("inverter_model"):
				inverter_model.fill_row(row, row.inverter_model, "unit_rate")
			else:
				row.with_optimizer = 0

	def warranty_extension_from_model(self):
		"""The Warranty Extension add-on is the default inverter model's, and none where
		that model has no extension. A package without a model keeps its own row."""
		inverter = _default_row(self, "inverters")
		if not (inverter and inverter.get("inverter_model")):
			return
		offer = inverter_model.extension(inverter.inverter_model)
		rows = [r for r in self.get("optional_add_ons") or [] if r.add_on_type == "Warranty Extension"]
		if not offer:
			for row in rows:
				self.remove(row)
			return
		row = rows[0] if rows else self.append("optional_add_ons", {"add_on_type": "Warranty Extension"})
		row.item, row.amount = offer
		row.rate, row.qty = offer[1], 1

	def fill_company(self):
		"""The company is not asked on the form: a new package is the user's default company's."""
		self.company = self.company or frappe.defaults.get_user_default("Company") or frappe.defaults.get_global_default("company")
		if not self.company:
			frappe.throw(_("Set a default Company before adding a package."), title=_("No Company"))

	def topology_from_inverters(self):
		"""Each inverter option is built its own way - string, with optimisers, micro, hybrid -
		and the package's topology is its default option's. A row left blank is built the way
		the package was."""
		for row in self.get("inverters") or []:
			if not row.get("inverter_topology"):
				row.inverter_topology = self.inverter_topology or "String"
		inverter = default_inverter(self)
		self.inverter_topology = (inverter.inverter_topology if inverter else None) or self.inverter_topology or "String"

	def fill_inverter_phases(self):
		"""An inverter row without a phase is for the package's own connection type."""
		for row in options(self, "inverters"):
			if not row.inverter_phase:
				row.inverter_phase = self.connection_type

	def check_pricing_options(self):
		"""The Pricing Options are the package's price list: each row a panel, inverter and battery
		of its own, at what they and the rest of the package cost (cost_the_pricing_options). A
		package saved with typed inverter Costs and no rows yet - made before the table, imported,
		loaded - gets its rows from those Costs."""
		self.seed_pricing_options()
		self.require_pricing_options()
		self.validate_pricing_options()
		self.validate_one_default("pricing_options", _("pricing"))

	def cost_the_pricing_options(self):
		"""Each Pricing Options row's cost (pricing_build_up), and from them each inverter option's
		Cost (its row on its own panel and the default battery - what the estimate and proposal
		read) and the Package Cost (the default row's)."""
		for row in self.get("pricing_options") or []:
			parts = pricing_build_up(self, row)
			# A row made from a price typed the old way keeps it: its margin is the rest of it.
			if row.flags.old_price is not None:
				row.margin = flt(row.flags.old_price - (sum(parts.values()) - parts["margin"]), row.precision("margin"))
				parts["margin"] = flt(row.margin)
			row.cost = flt(sum(parts.values()), row.precision("cost"))
		for row in options(self, "inverters"):
			option = pricing_option(self, row)
			row.cost = flt(option.cost) if option else 0.0
		default = _default_row(self, "pricing_options")
		self.package_cost = flt(default.cost) if default else 0.0

	def seed_pricing_options(self):
		"""A row for each inverter option priced the old way: on its panel, with the default
		battery, at its Cost (the default inverter's at the Package Cost when it had none) - its
		margin made what keeps that price (cost_the_pricing_options)."""
		if self.get("pricing_options"):
			return
		battery = default_battery(self)
		for row in options(self, "inverters"):
			cost = flt(row.cost) or (flt(self.package_cost) if row.is_default else 0.0)
			panel = inverter_panel(self, row)
			if not (cost and panel and inverter_name(row)):
				continue
			seeded = self.append("pricing_options", {"panel": panel_name(panel), "inverter": inverter_name(row),
				"battery": battery_name(battery) if battery else None, "cost": cost, "is_default": 1 if row.is_default else 0})
			seeded.flags.old_price = cost

	def require_pricing_options(self):
		"""An Active package has a Pricing Options row at least: the panel, inverter and cost it is
		offered at. A Draft is saved as it stands, to finish later - the row is asked for when it is
		made Active. Setting up, migrating and retiring a package are not held to it."""
		if (self.status or "Draft") != "Active" or self.get("pricing_options") or self.flags.ignore_pricing_options \
				or frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_patch:
			return
		frappe.throw(_("Add a Pricing Options row before making the package Active: a panel, an inverter and the cost "
			"the package is offered at. Without one it can be saved as a Draft."), title=_("No Pricing Option"))

	def validate_pricing_options(self):
		"""A row names one of the package's own panels, inverters and batteries, and each way of
		building the package is priced once. A battery is only for a package that has batteries."""
		panels = {panel_name(r) for r in options(self, "modules")} - {""}
		inverters = {inverter_name(r) for r in options(self, "inverters")} - {""}
		batteries = {battery_name(r) for r in self.get("batteries") or []} - {""}
		problems, seen = [], set()
		for row in self.get("pricing_options") or []:
			row.panel, row.inverter, row.battery = _name(row.panel), _name(row.inverter), _name(row.battery) or None
			if not batteries:
				row.battery = None
			if row.panel not in panels:
				problems.append(_("Row {0}: the panel {1} is not one of this package's Solar Panels.").format(row.idx, frappe.bold(row.panel)))
			if row.inverter not in inverters:
				problems.append(_("Row {0}: the inverter {1} is not one of this package's Inverter Options.").format(row.idx, frappe.bold(row.inverter)))
			if row.battery and row.battery not in batteries:
				problems.append(_("Row {0}: the battery {1} is not one of this package's Batteries.").format(row.idx, frappe.bold(row.battery)))
			key = (row.panel, row.inverter, row.battery or "")
			if key in seen:
				problems.append(_("Row {0}: this panel, inverter and battery are priced in an earlier row.").format(row.idx))
			seen.add(key)
		if problems:
			frappe.throw("<br>".join(problems), title=_("Pricing Options"))

	def validate_payment_terms(self):
		"""The package's payment terms are this company's, active, and add up to the whole price."""
		for field in ("payment_terms", "financed_payment_terms"):
			name = self.get(field)
			if not name:
				continue
			company, active = frappe.db.get_value("Billing Milestone Template", name, ["company", "is_active"]) or (None, 0)
			label = _(self.meta.get_label(field))
			if company and self.company and company != self.company:
				frappe.throw(_("{0}: {1} is {2}'s, not {3}'s.").format(label, name, company, self.company))
			if not active:
				frappe.throw(_("{0}: {1} is not active.").format(label, name))
			total = sum(flt(p) for p in frappe.get_all("Billing Milestone Template Detail",
				filters={"parent": name, "parenttype": "Billing Milestone Template"}, pluck="percentage"))
			if abs(total - 100) > 0.01:
				frappe.throw(_("{0}: the milestones of {1} add up to {2}%, not 100%.").format(label, name, flt(total, 2)))

	def validate_one_default(self, fieldname, noun):
		"""Exactly one option is the default, because everything downstream reads one.

		The proposal prints one module and one inverter, the cost estimate prices one, the
		handoff copies one onto the installation. If nobody has chosen, the first row is it -
		silently picking is better than a package that cannot be quoted, and the tick is
		visible on the form either way.
		"""
		rows = options(self, fieldname)
		if not rows:
			return
		defaults = [row for row in rows if row.is_default]
		if len(defaults) > 1:
			frappe.throw(
				_("{0} {1} options are marked default. Exactly one row can be, because the "
				  "proposal, the estimate and the handoff each read a single {1}.").format(
					len(defaults), noun
				),
				title=_("More Than One Default"),
			)
		if not defaults:
			rows[0].is_default = 1

	def validate_one_default_per_type(self):
		"""Balance of system is different: the default is per type, not per table.

		A package has a DCDB *and* an ACDB *and* a meter, so "the default row" is
		meaningless across the whole table. What can be offered as alternatives is two
		boards of the same type, and exactly one of those is the one quoted.
		"""
		seen = {}
		for row in self.system_items or []:
			if not row.system_type:
				continue
			seen.setdefault(row.system_type, []).append(row)
		for system_type, rows in seen.items():
			defaults = [row for row in rows if row.is_default]
			if len(defaults) > 1:
				frappe.throw(
					_("{0} {1} rows are marked default. One per type is quoted; the rest are "
					  "alternatives.").format(len(defaults), system_type),
					title=_("More Than One Default"),
				)
			if not defaults:
				rows[0].is_default = 1

	def no_dcdb_for_microinverter(self):
		"""A micro-inverter package has no DCDB: its count is 0 (api/microinverter.py)."""
		from a3_sola.api.microinverter import MICROINVERTER

		if self.inverter_topology != MICROINVERTER:
			return
		for row in self.system_items or []:
			if row.system_type == "DCDB":
				row.qty = 0

	def name_extra_panel_add_ons(self):
		"""An Extra Panel add-on left blank is one more of the package's own panel."""
		for row in self.get("optional_add_ons") or []:
			if row.add_on_type == "Extra Panel" and not (row.item or "").strip():
				row.item = extra_panel_item(self)

	def total_the_expenses(self):
		# A bundle's or a BOM's items are its parts, already in its own amount.
		self.total_expenses = flt(sum(flt(r.amount) for r in self.get("expenses") or [] if r.get("row_kind") != "Component"),
			self.precision("total_expenses"))

	def full_bom(self):
		"""The BOM tab as typed: nothing copied in from the other tabs, no bundle or BOM opened out
		into rows (package_bom_tree.keep_own_rows) - then its rows checked and the Expenses totalled."""
		from a3_sola.api import package_bom_tables, package_bom_tree

		package_bom_tree.keep_own_rows(self)
		package_bom_tables.validate(self)
		self.total_the_expenses()

	def total_the_panels(self):
		"""Each panel option's Rate per Panel - its Wattage x Wattage Rate, where it has a Wattage
		Rate (a row without one, and a kit's part, keeps its own) - and its Total Panel Rate: the
		Rate per Panel for every panel."""
		for row in self.get("modules") or []:
			if flt(row.get("wattage_rate")) and not row.get("bundle_part"):
				row.rate = flt(flt(row.module_wattage) * flt(row.wattage_rate), row.precision("rate"))
			row.amount = flt(flt(row.rate) * cint(row.module_count), row.precision("amount"))

	def total_the_add_ons(self):
		"""Each add-on's Amount, its Rate x Quantity (one where blank), and its Item Group, the
		chosen Item's own."""
		price_by_rate(self.get("optional_add_ons"))
		for row in self.get("optional_add_ons") or []:
			if row.item_code:
				row.item_group = frappe.db.get_value("Item", row.item_code, "item_group") or row.item_group

	def total_the_inverters(self):
		"""Each inverter option's Inverter Amount - its Rate per Inverter for every inverter - and its
		Item Group, the chosen Item's own where that is one of the Inverters groups."""
		groups = inverter_groups()
		for row in self.get("inverters") or []:
			row.amount = flt(flt(row.unit_rate) * cint(row.inverter_count), row.precision("amount"))
			group = frappe.db.get_value("Item", row.inverter_item, "item_group") if row.inverter_item else None
			if group in groups:
				row.item_group = group

	def total_the_package(self):
		"""The Total Package Cost: what the default build adds up to (package_build_up)."""
		self.total_package_cost = flt(package_build_up(self)["total"], self.precision("total_package_cost"))

	def compute_batteries(self):
		"""Batteries belong to off-grid and hybrid packages only; the count is typed."""
		if self.system_type not in ("Off-Grid", "Hybrid"):
			# The tab is hidden for On-Grid, so rows left behind would be invisible.
			self.set("batteries", [])
			return
		for row in self.get("batteries"):
			if not row.battery_phase:
				row.battery_phase = self.connection_type or "Single Phase"
			row.total_energy_kwh = flt(
				flt(row.battery_voltage) * flt(row.battery_capacity_ah) * cint(row.nos) / 1000, 3
			)
			row.amount = flt(flt(row.rate) * cint(row.nos), row.precision("amount"))

	def compute_expenses(self):
		"""The same KSEB, mounting and installation tables as the estimate, on the default build.

		Panel capacity is the default module row's; registration is charged on the default
		inverter row's capacity, as the estimate charges it. Either falls back to the rated
		capacity while its table is empty.
		"""
		module = _default_row(self, "modules")
		inverter = _default_row(self, "inverters")
		panel_kw = (
			flt(flt(module.module_wattage) * cint(module.module_count) / 1000, 3) if module else 0.0
		) or flt(self.capacity_kw)
		inverter_kw = (
			flt(flt(inverter.inverter_capacity_kw) * (cint(inverter.inverter_count) or 1), 3) if inverter else 0.0
		) or flt(self.capacity_kw)
		fees = self._statutory_fees(inverter_kw) or {}
		fill_expense_tables(
			self,
			roof_type=self.roof_type,
			panel_kw=panel_kw,
			fees={
				"application_fee": fees.get("application_fee_gross"),
				"registration_fee": fees.get("registration_fee_gross"),
				"net_meter_charge": fees.get("net_meter_charge"),
			},
		)
		# The KSEB and installation rows added by hand: Rate x Quantity.
		price_by_rate(self.get("kseb_expenses"))
		price_by_rate(self.get("installation_expenses"))

	def _statutory_fees(self, capacity_kw=None):
		"""Every statutory figure comes from the fee schedule. None is editable."""
		discom = get_value("default_discom")
		if not discom:
			return None
		try:
			return statutory.get_statutory_fees(
				discom, self.connection_type or "Single Phase", capacity_kw or self.capacity_kw,
				"Purchased by Customer", company=self.company,
			)
		except frappe.ValidationError:
			# A package may be defined before the fee schedule exists on a fresh install.
			return None

	def validate_dcr_items(self):
		"""A DCR package's module items must actually be flagged DCR on the Item master."""
		if not self.is_dcr_compliant:
			return
		for row in self.components:
			if row.component_type != "Module" or not row.item:
				continue
			if not frappe.db.get_value("Item", row.item, "is_dcr"):
				frappe.throw(
					_("Package is marked DCR compliant but module item {0} is not flagged DCR on the Item master.").format(
						frappe.bold(row.item)
					),
					title=_("DCR Mismatch"),
				)

	def check_regulation(self):
		"""Warn, do not block - the three-phase rule is currently stayed."""
		result = regulation.check_connection_type(
			self.capacity_kw, self.connection_type, get_value("default_discom"), company=self.company
		)
		if result["compliant"]:
			return
		clause = frappe.db.get_value("Grid Regulation Rule", result["rule"], "customer_facing_clause")
		frappe.msgprint(
			frappe.utils.strip_html(clause or "") or result["message"],
			title=_("Grid Regulation"),
			indicator="orange",
		)


#: What a package offers beside its price unless its own add-ons are entered: one more panel
#: of its own, and the inverter's warranty taken to 25 years. Printed in the proposal's 3.3.3.
DEFAULT_ADD_ONS = (
	("Extra Panel", None, 17500),
	("Warranty Extension", "Warranty Extension for Inverter – 13th Year to 25th year", 10000),
)


def extra_panel_item(package):
	"""'Supply and Installation of 1X550Wp Solar Panel', with the package's default panel."""
	module = _default_row(package, "modules") if package.get("modules") else None
	watt = flt(module.module_wattage) if module else 0
	return "Supply and Installation of 1X{0:g}Wp Solar Panel".format(watt) if watt else "Supply and Installation of 1 Solar Panel"


def default_add_ons(package):
	"""The DEFAULT_ADD_ONS rows for `package` (a document)."""
	return [{"add_on_type": kind, "item": item or extra_panel_item(package), "rate": amount, "qty": 1, "amount": amount}
		for kind, item, amount in DEFAULT_ADD_ONS]


def _doc(package):
	return package if hasattr(package, "get") and hasattr(package, "doctype") else frappe.get_cached_doc("Solar Package", package)


def options(package, fieldname):
	"""A table's options. On the panel and inverter tabs a kit - a bundle or BOM opened into its
	items (api/package_kits) - is one option, its first row; its other rows are its parts."""
	return [row for row in _doc(package).get(fieldname) or [] if not row.get("bundle_part")]


def option_rows(package, fieldname, option):
	"""An option's rows: itself, and a kit's parts."""
	if not option:
		return []
	key = option.get("bundle_key")
	return [option] + ([r for r in _doc(package).get(fieldname) or [] if r.get("bundle_part") and r.get("bundle_key") == key]
		if key else [])


#: Each option table's rate and count, which make a row's amount.
OPTION_PRICE = {"modules": ("rate", "module_count"), "inverters": ("unit_rate", "inverter_count")}


def option_amount(package, fieldname, option):
	"""What an option costs: its rate x count, with a kit's parts'."""
	rate, count = OPTION_PRICE[fieldname]
	return sum(flt(r.get(rate)) * (cint(r.get(count)) or (1 if fieldname == "inverters" else 0))
		for r in option_rows(package, fieldname, option))


def option_unit_rate(package, fieldname, option):
	"""An option's rate for one of it - a panel, an inverter - with a kit's parts in it."""
	if not option:
		return 0.0
	count = cint(option.get(OPTION_PRICE[fieldname][1])) or 1
	return flt(option_amount(package, fieldname, option) / count, 2)


def _default_row(package, fieldname):
	"""The row marked default, else the first row, else None.

	`package` may be a name or a loaded document. None is a real answer: a draft package
	with nothing filled in yet is allowed to exist, so every caller copes with it.

	One function per table, because a package offering a DCR panel and its non-DCR
	equivalent must not be read as the DCR one by the proposal and the other by the handoff.
	"""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	rows = options(doc, fieldname)
	for row in rows:
		if row.is_default:
			return row
	return rows[0] if rows else None


def inverter_phase(package, row):
	"""The connection an inverter row is for: its own phase, else the package's."""
	return row.get("inverter_phase") or package.get("connection_type") or ""


def package_phases(package):
	"""Every connection type the package offers an inverter for, else its own."""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	phases = {inverter_phase(doc, row) for row in options(doc, "inverters")} - {""}
	return phases or ({doc.connection_type} if doc.connection_type else set())


def inverters_for_phase(package, phase):
	"""The package's inverter rows for this connection type; all of them when none is given."""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	return [row for row in options(doc, "inverters") if not phase or inverter_phase(doc, row) == phase]


def default_module(package):
	"""The module option a package is quoted, priced and built with."""
	return _default_row(package, "modules")


def default_inverter(package):
	"""The inverter option a package is quoted, priced and built with.

	Its `cost` is the package price: what the array costs built that way.
	"""
	return _default_row(package, "inverters")


def default_package_cost(package):
	"""What the package costs built its default way: the default pricing option's cost, else
	the default inverter's. Zero when it has neither."""
	option = _default_row(package, "pricing_options")
	if option and flt(option.cost):
		return flt(option.cost)
	inverter = default_inverter(package)
	return flt(inverter.cost) if inverter else 0.0


def _name(text):
	"""A panel, inverter or battery as a pricing option names it: its text on one line."""
	return " ".join((text or "").split())


def panel_name(row):
	return _name(row.get("module_specification")) if row else ""


def inverter_name(row):
	return _name(row.get("inverter_specification")) if row else ""


def battery_name(row):
	"""A battery by its specification, else its volts and Ah."""
	if not row:
		return ""
	return _name(row.get("specification")) or " x ".join(part for part in (
		"{0:g} V".format(flt(row.get("battery_voltage"))) if flt(row.get("battery_voltage")) else "",
		"{0:g} Ah".format(flt(row.get("battery_capacity_ah"))) if flt(row.get("battery_capacity_ah")) else "") if part)


def pricing_option(package, inverter=None, panel=None, battery=None):
	"""The pricing row for the package built with this inverter option (the default when None),
	on this panel and with this battery - each a row or its name. A panel or battery without a
	row of its own falls back to the default panel
	and the default battery, then to any. None when the inverter is not priced at all."""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	inverter = inverter or default_inverter(doc)
	rows = [r for r in doc.get("pricing_options") or [] if inverter and r.inverter == inverter_name(inverter)]
	if not rows:
		return None

	def named(value, name_of):
		return _name(value) if isinstance(value, str) else name_of(value) if value else ""

	panels = [p for p in (named(panel, panel_name), panel_name(inverter_panel(doc, inverter))) if p] + [None]
	own_battery = default_battery(doc)
	batteries = [b for b in (named(battery, battery_name), battery_name(own_battery) if own_battery else "") if b] + [None]
	for want_panel in panels:
		for want_battery in batteries:
			hit = next((r for r in rows if (want_panel is None or r.panel == want_panel)
				and (want_battery is None or (r.battery or "") == want_battery)), None)
			if hit:
				return hit
	return None


def pricing_build_up(package, row):
	"""What a Pricing Options row's cost is made of: its panel's and inverter's options (a kit's
	parts in them) and its battery, at their amounts; the Installation rows; the Materials,
	Structure and Expenses rows that go with that panel and inverter (their Depends On); and the
	row's margin. KSEB is not in it, nor the mounting, the balance of system or the add-ons."""
	from a3_sola.api import package_bom_tables
	from a3_sola.api.package_bom_tree import is_own

	doc = _doc(package)
	panel = next((r for r in options(doc, "modules") if panel_name(r) and panel_name(r) == _name(row.get("panel"))), None)
	inverter = next((r for r in options(doc, "inverters") if inverter_name(r) and inverter_name(r) == _name(row.get("inverter"))), None)
	battery = next((r for r in doc.get("batteries") or [] if battery_name(r) == _name(row.get("battery"))), None) \
		if row.get("battery") and doc.get("system_type") in ("Off-Grid", "Hybrid") else None
	used = package_bom_tables.used_items(doc, chosen={"modules": option_rows(doc, "modules", panel),
		"inverters": option_rows(doc, "inverters", inverter), "batteries": [battery] if battery else []})

	def applying(table):
		return sum(flt(r.amount) for r in doc.get(table) or [] if r.item and is_own(r) and package_bom_tables.applies(r, used))

	return {
		"panel": option_amount(doc, "modules", panel),
		"inverter": option_amount(doc, "inverters", inverter),
		"battery": flt(battery.rate) * cint(battery.nos) if battery else 0.0,
		"installation": sum(flt(r.amount) for r in doc.get("installation_expenses") or []),
		"materials": applying("material_bom"),
		"structure": applying("structure_boms"),
		"expenses": applying("expenses"),
		"margin": flt(row.get("margin")),
	}


def package_cost(package):
	"""The package's cost as recorded on it, else as its defaults price it."""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	return flt(doc.get("package_cost")) or default_package_cost(doc)


def default_battery(package):
	"""The battery a package is built with: its first row not marked as an option."""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	rows = [row for row in doc.get("batteries") or [] if row.battery_make]
	return next((row for row in rows if not row.is_option), rows[0] if rows else None)


def package_components(package, phase=None):
	"""What an option row may choose from a package: one panel, one inverter, one battery.

	Returns {"package_cost", "panels", "inverters", "batteries"}, each list of
	{"value": make, "label", "default"} with the package's default first. Inverters are the
	package's for `phase` when one is given; batteries are listed only for Off-Grid and
	Hybrid packages.
	"""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	makes = {}
	wanted = [r.module_make for r in options(doc, "modules")] + [r.inverter_make for r in options(doc, "inverters")] \
		+ [r.battery_make for r in doc.get("batteries") or []]
	if any(wanted):
		makes = {
			m.name: m.make_name
			for m in frappe.get_all("Component Make", filters={"name": ["in", [w for w in wanted if w]]}, fields=["name", "make_name"])
		}

	def ordered(rows, default):
		return ([default] if default in rows else []) + [r for r in rows if r is not default]

	def number(value, unit):
		return "{0:g} {1}".format(flt(value), unit) if flt(value) else ""

	def label(*parts):
		return " \u00b7 ".join(p for p in parts if p)

	panels = []
	module = default_module(doc)
	for row in ordered([r for r in options(doc, "modules") if r.module_make], module):
		panels.append({
			"value": row.module_make, "default": row is module,
			"label": label(makes.get(row.module_make) or row.module_make, number(row.module_wattage, "Wp"),
				"{0} nos".format(cint(row.module_count)) if cint(row.module_count) else ""),
		})

	# The panel each inverter is costed on: the package's default panel.
	default_panel = module.module_make if module else None
	panel_of = {}
	for row in options(doc, "inverters"):
		panel = inverter_panel(doc, row)
		make = panel.module_make if panel else None
		if make and make != default_panel:
			panel_of[row.inverter_specification] = make

	inverters = []
	matching = [r for r in inverters_for_phase(doc, phase) if r.inverter_make]
	inverter = next((r for r in matching if r.is_default), matching[0] if matching else None)
	for row in ordered(matching, inverter):
		inverters.append({
			"value": row.inverter_make, "default": row is inverter, "phase": inverter_phase(doc, row),
			# The package's price built with this inverter: the price list's MRP for it.
			"cost": flt(row.cost) or (package_cost(doc) if row is inverter else 0.0),
			# Its own panels, when the price list builds it on other panels than the default.
			"panel": panel_of.get(row.inverter_specification, ""),
			"label": label(makes.get(row.inverter_make) or row.inverter_make, row.get("inverter_model") and
				frappe.db.get_value("Inverter Model", row.inverter_model, "model_name"), number(row.inverter_capacity_kw, "kW"),
				"\u00d7 {0}".format(cint(row.inverter_count)) if cint(row.inverter_count) > 1 else "",
				_("with optimizer") if row.get("with_optimizer") else ""),
		})

	batteries = []
	if doc.system_type in ("Off-Grid", "Hybrid"):
		battery = default_battery(doc)
		seen = set()
		for row in ordered([r for r in doc.get("batteries") or [] if r.battery_make], battery):
			if row.battery_make in seen:
				continue
			seen.add(row.battery_make)
			batteries.append({
				"value": row.battery_make, "default": row is battery,
				"label": label(makes.get(row.battery_make) or row.battery_make, number(row.battery_voltage, "V"),
					number(row.battery_capacity_ah, "Ah"), "\u00d7 {0}".format(cint(row.nos)) if cint(row.nos) > 1 else ""),
			})

	return {"package_cost": package_cost(doc), "panels": panels, "inverters": inverters, "batteries": batteries}


def default_system_items(package):
	"""The balance-of-system parts a package is quoted with - one per type.

	Returns a dict keyed by type, because that is how the specification reads: one DCDB,
	one ACDB, one meter, whichever of each was ticked.
	"""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	chosen = {}
	for row in doc.get("system_items") or []:
		if not row.system_type:
			continue
		if row.is_default or row.system_type not in chosen:
			if row.system_type in chosen and not row.is_default:
				continue
			chosen[row.system_type] = row
	return chosen


def package_build_up(package):
	"""What a package's default build adds up to, part by part, and its total - the Total
	Package Cost: the default panel's Total Panel Rate, the default inverter's Rate per Inverter
	x Nos, the batteries (an Off-Grid or Hybrid package's, not those offered as options), the
	default Balance of System rows' Cost, and the KSEB, Mounting and Installation amounts.

	A build-up, not a price: an estimate or proposal prices the package at its inverter
	option's Cost (price_for), as before."""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	panel = default_module(doc)
	inverter = default_inverter(doc)
	batteries = (doc.get("batteries") or []) if doc.get("system_type") in ("Off-Grid", "Hybrid") else []
	parts = {
		"panel": option_amount(doc, "modules", panel),
		"inverter": option_amount(doc, "inverters", inverter),
		"batteries": sum(flt(r.rate) * cint(r.nos) for r in batteries if not r.get("is_option")),
		"balance_of_system": system_cost(doc),
		"kseb": sum(flt(r.amount) for r in doc.get("kseb_expenses") or []),
		"mounting": sum(flt(r.amount) for r in doc.get("mounting_expenses") or []),
		"installation": sum(flt(r.amount) for r in doc.get("installation_expenses") or []),
	}
	parts["total"] = sum(parts.values())
	return parts


def system_cost(package):
	"""What the balance of system adds, counting only the rows actually quoted."""
	return sum(flt(row.cost) for row in default_system_items(package).values())


def inverter_panel(package, inverter):
	"""The panel row an inverter option is costed on: the package's default panel. (Each Pricing
	Options row names its own panel.)"""
	return default_module(package)


def package_subsidy(package):
	"""The subsidy the default scheme gives a package of this capacity - a DCR-compliant
	package is a subsidy package; any other is sold without one."""
	scheme = get_value("default_subsidy_scheme")
	if not (scheme and package.get("is_dcr_compliant") and frappe.db.exists("Subsidy Scheme", scheme)):
		return 0.0
	category = frappe.db.get_value("Subsidy Scheme", scheme, "consumer_category")
	if not category:
		return 0.0
	return flt(calculations.get_subsidy_amount(scheme, flt(package.get("capacity_kw")), category)["subsidy_amount"])


def price_for(package, inverter=None):
	"""What the package costs built with `inverter` (one of its inverter options; the default
	when None), and what the quotation says around it - worked out, not typed:

	- the MRP is the inverter option's Cost (the default's falls back to the Package Cost);
	- the subsidy is the default scheme's for the package's capacity (DCR packages only);
	- the net cost is the MRP less the subsidy, and 0 while there is no MRP - a blank price
	  less the subsidy would publish a negative net cost;
	- the statutory fees are the fee schedule's for its connection and capacity;
	- the generation band follows the capacity.

	The keys are those of the price table this replaced, so its readers read it as before."""
	doc = package if hasattr(package, "get") and hasattr(package, "doctype") else frappe.get_cached_doc("Solar Package", package)
	inverter = inverter or default_inverter(doc)
	module = inverter_panel(doc, inverter)
	system = default_system_items(doc)
	cost = flt(inverter.cost) if inverter else 0.0
	if not cost and (not inverter or inverter.get("is_default")):
		cost = flt(doc.get("package_cost"))
	subsidy = package_subsidy(doc)
	fees = (doc._statutory_fees() if hasattr(doc, "_statutory_fees") else None) or {}
	band = calculations.estimate_daily_generation_band(flt(doc.get("capacity_kw")))
	return frappe._dict({
		"module": module.module_specification if module else None,
		"inverter": inverter.inverter_specification if inverter else None,
		"dcdb": (system.get("DCDB") or frappe._dict()).get("specification"),
		"acdb": (system.get("ACDB") or frappe._dict()).get("specification"),
		"energy_meter": (system.get("Solar Energy Meter") or frappe._dict()).get("specification"),
		"system_cost": cost,
		"standard_discount": 0.0,
		"additional_structure_and_cable_cost": 0.0,
		"indicative_subsidy": subsidy,
		"net_rate": cost - subsidy if cost else 0.0,
		"kseb_application_fee": flt(fees.get("application_fee_gross")),
		"kseb_registration_fee": flt(fees.get("registration_fee_gross")),
		"kseb_registration_refundable": flt(fees.get("registration_refundable")),
		"net_meter_charge": flt(fees.get("net_meter_charge")),
		"statutory_total": flt(fees.get("statutory_total")),
		"expected_daily_units_low": band["low_units_per_day"],
		"expected_daily_units_high": band["high_units_per_day"],
	})


def default_price(package):
	"""The package as it is offered by default - its default inverter - priced (price_for)."""
	return price_for(package)


def default_prices(package_names):
	"""The default price of each package, for a whole catalogue (the cost estimator, the
	package comparison, the portal's list): each package read once, from the cache."""
	return {name: default_price(frappe.get_cached_doc("Solar Package", name)) for name in package_names or []}


def default_rows(fieldname, package_names):
	"""The default row of `fieldname` for many packages, in one query.

	Same rule as `_default_row` - ticked wins, else the first - applied in bulk, because
	the public cost estimator and the package comparison both read a whole catalogue and
	must not issue a query per package.
	"""
	if not package_names:
		return {}
	doctype = {"modules": "Solar Package Module", "inverters": "Solar Package Inverter"}[fieldname]
	found = {}
	for row in frappe.get_all(
		doctype,
		filters={"parent": ["in", list(package_names)], "parenttype": "Solar Package", "bundle_part": 0},
		fields=["*"],
		order_by="parent asc, is_default desc, idx asc",
	):
		found.setdefault(row.parent, row)
	return found


@frappe.whitelist()
def create_item_and_bom(solar_package):
	"""Create the ERPNext Item and BOM from the component table, then link them back."""
	doc = frappe.get_doc("Solar Package", solar_package)
	doc.check_permission("write")
	created = {}

	if not doc.item:
		_ensure_item_group("Solar Packages")
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": doc.specification_code or doc.package_name,
				"item_name": doc.package_name,
				"item_group": "Solar Packages",
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"description": doc.package_name,
			}
		)
		hsn = _package_hsn_code(doc.company)
		if hsn and item.meta.has_field("gst_hsn_code"):
			item.gst_hsn_code = hsn
		item.insert(ignore_permissions=True)
		doc.db_set("item", item.name, update_modified=False)
		created["item"] = item.name

	component_items = [row for row in doc.components if row.item and flt(row.qty)]
	if not doc.bom and component_items:
		bom = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": doc.item,
				"company": doc.company,
				"quantity": 1,
				"is_active": 1,
				"is_default": 1,
				"items": [
					{"item_code": row.item, "qty": flt(row.qty), "uom": row.uom} for row in component_items
				],
			}
		)
		bom.insert(ignore_permissions=True)
		bom.submit()
		doc.db_set("bom", bom.name, update_modified=False)
		created["bom"] = bom.name

	return created or {"message": _("Item and BOM already exist.")}


#: Solar photovoltaic modules assembled in panels - the HSN a rooftop package is sold under
#: when no GST valuation rule has been recorded for the company yet.
DEFAULT_PACKAGE_HSN = "85414300"


def _package_hsn_code(company):
	"""The goods HSN for a package item.

	India Compliance makes HSN mandatory on every Item, so an item created without one fails
	on any Indian site. Prefer the company's active Solar GST Valuation Rule - it is the
	recorded position on how the plant is billed - and fall back to the module HSN.
	"""
	from a3_sola.api.gst import find_valuation

	rule = find_valuation(company)
	hsn = rule and frappe.db.get_value("Solar GST Valuation Rule", rule, "goods_hsn_code")
	hsn = hsn or DEFAULT_PACKAGE_HSN
	if frappe.db.exists("DocType", "GST HSN Code") and not frappe.db.exists("GST HSN Code", hsn):
		return None
	return hsn


def _ensure_item_group(name):
	if frappe.db.exists("Item Group", name):
		return
	frappe.get_doc(
		{
			"doctype": "Item Group",
			"item_group_name": name,
			"parent_item_group": "All Item Groups",
			"is_group": 0,
		}
	).insert(ignore_permissions=True)


def inverter_groups():
	"""The Item Groups under Inverters (On-Grid, Hybrid, Off-Grid ...), and Inverters itself."""
	lft, rgt = frappe.db.get_value("Item Group", "Inverters", ["lft", "rgt"]) or (None, None)
	if lft is None:
		return set()
	return set(frappe.get_all("Item Group", filters={"lft": [">=", lft], "rgt": ["<=", rgt]}, pluck="name"))
