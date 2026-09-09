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
from frappe.utils import flt

from a3_sola.api import calculations, regulation, statutory
from a3_sola.api.settings import get_value
from a3_sola.api.uniqueness import assert_unique_in_company


class SolarPackage(Document):
	def validate(self):
		assert_unique_in_company(self, ["specification_code"])
		self.validate_dcr_items()
		self.validate_one_default("modules", _("module"))
		self.validate_one_default("inverters", _("inverter"))
		self.validate_one_default_per_type()
		self.validate_prices()
		self.price_the_configurations()
		self.check_regulation()

	def validate_one_default(self, fieldname, noun):
		"""Exactly one option is the default, because everything downstream reads one.

		The proposal prints one module and one inverter, the cost estimate prices one, the
		handoff copies one onto the installation. If nobody has chosen, the first row is it -
		silently picking is better than a package that cannot be quoted, and the tick is
		visible on the form either way.
		"""
		rows = self.get(fieldname) or []
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

	def validate_prices(self):
		"""Every price row names a real configuration, and no two name the same one.

		The five choices are what a price is a price *of*. A row that names a module the
		package no longer offers is not a stale label - it is a figure attached to nothing,
		and it would go on a quotation looking exactly as authoritative as the rest.
		"""
		available = self.available_choices()
		seen = {}
		for row in self.prices or []:
			for fieldname, label, choices in available:
				value = row.get(fieldname)
				if value and value not in choices:
					frappe.throw(
						_("Price row {0} is for {1} {2}, which this package no longer offers. "
						  "Choose one of: {3}").format(
							row.idx, label, frappe.bold(value),
							", ".join(sorted(choices)) or _("none - add one first"),
						),
						title=_("Configuration Not Offered"),
					)
			key = tuple(row.get(fieldname) for fieldname, _label, _choices in available)
			if not all(key):
				continue
			if key in seen:
				frappe.throw(
					_("Price rows {0} and {1} are for the same configuration. One combination "
					  "has one price.").format(seen[key], row.idx),
					title=_("Duplicate Configuration"),
				)
			seen[key] = row.idx

	def available_choices(self):
		"""What each of the five selections may be, read off this package's own tables."""
		system = {}
		for row in self.system_items or []:
			if row.system_type and row.specification:
				system.setdefault(row.system_type, set()).add(row.specification)
		return (
			("module", _("module"),
			 {r.module_specification for r in self.modules or [] if r.module_specification}),
			("inverter", _("inverter"),
			 {r.inverter_specification for r in self.inverters or [] if r.inverter_specification}),
			("dcdb", _("DCDB"), system.get("DCDB", set())),
			("acdb", _("ACDB"), system.get("ACDB", set())),
			("energy_meter", _("energy meter"), system.get("Solar Energy Meter", set())),
		)

	def price_the_configurations(self):
		"""Resolve the subsidy, the statutory fees and the generation band onto every row.

		Resolved rather than typed, exactly as they were when they sat on the package, and
		from the same inputs: the package's rated capacity and connection type. They live on
		the row because the row is what gets quoted - not because they differ between rows.
		"""
		scheme = get_value("default_subsidy_scheme")
		category = (
			frappe.db.get_value("Subsidy Scheme", scheme, "consumer_category")
			if scheme and frappe.db.exists("Subsidy Scheme", scheme)
			else None
		)
		fees = self._statutory_fees()
		capacity = flt(self.capacity_kw)
		for row in self.prices or []:
			row.indicative_subsidy = (
				flt(calculations.get_subsidy_amount(scheme, capacity, category)["subsidy_amount"])
				if category
				else 0.0
			)
			if fees:
				row.kseb_application_fee = fees["application_fee_gross"]
				row.kseb_registration_fee = fees["registration_fee_gross"]
				row.kseb_registration_refundable = fees["registration_refundable"]
				row.net_meter_charge = fees["net_meter_charge"]
				row.statutory_total = fees["statutory_total"]
			band = calculations.estimate_daily_generation_band(capacity)
			row.expected_daily_units_low = band["low_units_per_day"]
			row.expected_daily_units_high = band["high_units_per_day"]
			row.net_rate = self._net_rate(row)

	def _statutory_fees(self):
		"""Every statutory figure comes from the fee schedule. None is editable."""
		discom = get_value("default_discom")
		if not discom:
			return None
		try:
			return statutory.get_statutory_fees(
				discom, self.connection_type or "Single Phase", self.capacity_kw,
				"Purchased by Customer", company=self.company,
			)
		except frappe.ValidationError:
			# A package may be defined before the fee schedule exists on a fresh install.
			return None

	def _net_rate(self, row):
		"""Net of subsidy, but only once a price is actually recorded.

		Packages ship with their pricing blank - the client's workbook holds the live
		figures. Subtracting the subsidy from a blank price would publish a negative net
		rate onto every proposal, so an unpriced row stays at zero.
		"""
		cost = flt(row.system_cost)
		if not cost:
			return 0.0
		return (
			cost
			- flt(row.indicative_subsidy)
			- flt(row.standard_discount)
			+ flt(row.additional_structure_and_cable_cost)
		)

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
	rows = doc.get(fieldname) or []
	for row in rows:
		if row.is_default:
			return row
	return rows[0] if rows else None


def default_module(package):
	"""The module option a package is quoted, priced and built with."""
	return _default_row(package, "modules")


def default_inverter(package):
	"""The inverter option a package is quoted, priced and built with.

	Its `cost` is the package price: what the array costs built that way.
	"""
	return _default_row(package, "inverters")


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


def system_cost(package):
	"""What the balance of system adds, counting only the rows actually quoted."""
	return sum(flt(row.cost) for row in default_system_items(package).values())


def default_price(package):
	"""The price row for the package as it is offered by default.

	Derived, not flagged: it is the row whose five choices are the default module, the
	default inverter and the default DCDB, ACDB and meter. There is deliberately no
	"default price" tick, because that would be a sixth place to disagree with the five
	that already say which configuration is standard.

	Falls back to the first row, so a package whose defaults have moved since its prices
	were entered still quotes something rather than nothing.
	"""
	doc = (
		package
		if hasattr(package, "get") and hasattr(package, "doctype")
		else frappe.get_cached_doc("Solar Package", package)
	)
	rows = doc.get("prices") or []
	if not rows:
		return None

	module = default_module(doc)
	inverter = default_inverter(doc)
	system = default_system_items(doc)
	wanted = (
		module.module_specification if module else None,
		inverter.inverter_specification if inverter else None,
		(system.get("DCDB") or frappe._dict()).get("specification"),
		(system.get("ACDB") or frappe._dict()).get("specification"),
		(system.get("Solar Energy Meter") or frappe._dict()).get("specification"),
	)
	for row in rows:
		if (row.module, row.inverter, row.dcdb, row.acdb, row.energy_meter) == wanted:
			return row
	return rows[0]


def default_prices(package_names):
	"""The default price row of each package, in one query.

	`default_price` matches the row against the package's default module, inverter and
	boards; doing that per package would be a document load each. Here the whole catalogue
	is being rendered, so the first row of each package is taken and then corrected by the
	defaults where they are known - the same answer, one query.
	"""
	if not package_names:
		return {}
	modules = default_rows("modules", package_names)
	inverters = default_rows("inverters", package_names)
	found, first = {}, {}
	for row in frappe.get_all(
		"Solar Package Price",
		filters={"parent": ["in", list(package_names)], "parenttype": "Solar Package"},
		fields=["*"],
		order_by="parent asc, idx asc",
	):
		first.setdefault(row.parent, row)
		module = modules.get(row.parent)
		inverter = inverters.get(row.parent)
		matches = (
			(not module or row.module == module.module_specification)
			and (not inverter or row.inverter == inverter.inverter_specification)
		)
		if matches:
			found.setdefault(row.parent, row)
	for parent, row in first.items():
		found.setdefault(parent, row)
	return found


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
		filters={"parent": ["in", list(package_names)], "parenttype": "Solar Package"},
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
	from a3_sola.api.gst import resolve_valuation

	try:
		rule = resolve_valuation(company)
		hsn = frappe.db.get_value("Solar GST Valuation Rule", rule, "goods_hsn_code")
	except frappe.ValidationError:
		hsn = None
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
