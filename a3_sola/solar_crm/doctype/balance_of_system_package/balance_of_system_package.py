# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api.uniqueness import assert_unique_in_company

#: The Component Make type each balance-of-system item's make is drawn from.
MAKE_TYPE = {
	"DCDB": "DCDB",
	"ACDB": "ACDB",
	"DC Cable": "Cable",
	"AC Cable": "Cable",
	"Earthing": "Earthing",
	"Lightning Protection": "Lightning Protection",
	"Solar Energy Meter": "Energy Meter",
}


class BalanceofSystemPackage(Document):
	def validate(self):
		assert_unique_in_company(self, ["package_name"])
		self.validate_inverter_type()
		self.validate_capacity_range()
		self.validate_one_active_per_type()
		self.validate_items()

	def validate_inverter_type(self):
		if frappe.db.get_value("Component Technology", self.inverter_type, "component_type") != "Inverter":
			frappe.throw(_("Inverter Type must be an Inverter technology."), title=_("Not an Inverter Type"))

	def validate_capacity_range(self):
		if flt(self.max_inverter_capacity_kw) and flt(self.max_inverter_capacity_kw) < flt(self.min_inverter_capacity_kw):
			frappe.throw(
				_("To Inverter Capacity must not be below From Inverter Capacity."), title=_("Capacity Range")
			)

	def validate_one_active_per_type(self):
		"""One active package per inverter type and capacity band: the bands may not overlap,
		so a design's inverter capacity selects one package. Bands may touch - 0 to 5 and
		5 to 10 - and a capacity on the shared bound takes the lower band."""
		if not self.is_active:
			return
		others = frappe.get_all(
			"Balance of System Package",
			filters={"inverter_type": self.inverter_type, "company": self.company, "is_active": 1, "name": ("!=", self.name)},
			fields=["name", "min_inverter_capacity_kw", "max_inverter_capacity_kw"],
		)
		low, high = _band(self)
		for other in others:
			other_low, other_high = _band(other)
			if low < other_high and other_low < high:
				frappe.throw(
					_("{0} is already the active package for this inverter type from {1} to {2} kW.").format(
						frappe.bold(other.name), _kw(other_low), _kw(other_high)
					),
					title=_("Overlapping Capacity Range"),
				)

	def validate_items(self):
		for row in self.items:
			if row.phase and row.item != "Solar Energy Meter":
				row.phase = None
			if row.make:
				make_name, make_type = frappe.db.get_value("Component Make", row.make, ["make_name", "component_type"])
				if make_type != MAKE_TYPE.get(row.item):
					frappe.throw(
						_("Row {0}: make {1} is a {2} make, not {3}.").format(
							row.idx, frappe.bold(make_name), make_type, MAKE_TYPE.get(row.item)
						),
						title=_("Make Mismatch"),
					)


def _band(row):
	"""(from, to) kW of a package; a blank To is open-ended."""
	low = flt(row.get("min_inverter_capacity_kw"))
	high = flt(row.get("max_inverter_capacity_kw")) or float("inf")
	return low, high


def _kw(value):
	return "{0:g}".format(value) if value != float("inf") else _("any")


def package_for(inverter_type, company, inverter_capacity_kw=0.0):
	"""The active Balance of System Package for this inverter type whose capacity band holds
	`inverter_capacity_kw`, or None. A package with no band set holds every capacity."""
	if not inverter_type:
		return None
	capacity = flt(inverter_capacity_kw)
	packages = frappe.get_all(
		"Balance of System Package",
		filters={"inverter_type": inverter_type, "company": company, "is_active": 1},
		fields=["name", "min_inverter_capacity_kw", "max_inverter_capacity_kw"],
		order_by="min_inverter_capacity_kw asc",
	)
	for package in packages:
		low, high = _band(package)
		if low <= capacity <= high:
			return package.name
	return None
