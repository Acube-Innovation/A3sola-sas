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
		self.resolve_subsidy()
		self.resolve_statutory()
		self.compute_generation_band()
		self.compute_net_rate()
		self.validate_dcr_items()
		self.check_regulation()

	def resolve_subsidy(self):
		"""Indicative only, and resolved from the scheme - never typed."""
		scheme = get_value("default_subsidy_scheme")
		if not scheme or not frappe.db.exists("Subsidy Scheme", scheme):
			self.indicative_subsidy = 0.0
			return
		category = frappe.db.get_value("Subsidy Scheme", scheme, "consumer_category")
		result = calculations.get_subsidy_amount(scheme, self.capacity_kw, category)
		self.indicative_subsidy = flt(result["subsidy_amount"])

	def resolve_statutory(self):
		"""Every statutory figure comes from the fee schedule. None is editable."""
		discom = get_value("default_discom")
		if not discom:
			return
		try:
			fees = statutory.get_statutory_fees(
				discom, self.connection_type or "Single Phase", self.capacity_kw, "Purchased by Customer",
				company=self.company,
			)
		except frappe.ValidationError:
			# A package may be defined before the fee schedule exists on a fresh install.
			return
		self.kseb_application_fee = fees["application_fee_gross"]
		self.kseb_registration_fee = fees["registration_fee_gross"]
		self.kseb_registration_refundable = fees["registration_refundable"]
		self.net_meter_charge = fees["net_meter_charge"]
		self.statutory_total = fees["statutory_total"]

	def compute_generation_band(self):
		band = calculations.estimate_daily_generation_band(self.capacity_kw)
		self.expected_daily_units_low = band["low_units_per_day"]
		self.expected_daily_units_high = band["high_units_per_day"]

	def compute_net_rate(self):
		"""Net of subsidy, but only once a price is actually recorded.

		Packages ship with their pricing blank - the client's workbook holds the live
		figures. Subtracting the subsidy from a blank price would publish a negative net
		rate onto every proposal, so an unpriced package stays at zero.
		"""
		if not flt(self.cost_option_1):
			self.net_rate = 0.0
			return
		self.net_rate = (
			flt(self.cost_option_1)
			- flt(self.indicative_subsidy)
			- flt(self.standard_discount)
			+ flt(self.additional_structure_and_cable_cost)
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
		).insert(ignore_permissions=True)
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
