# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

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
		self.validate_one_active_per_type()
		self.validate_items()

	def validate_inverter_type(self):
		if frappe.db.get_value("Component Technology", self.inverter_type, "component_type") != "Inverter":
			frappe.throw(_("Inverter Type must be an Inverter technology."), title=_("Not an Inverter Type"))

	def validate_one_active_per_type(self):
		if not self.is_active:
			return
		other = frappe.db.get_value(
			"Balance of System Package",
			{"inverter_type": self.inverter_type, "company": self.company, "is_active": 1, "name": ("!=", self.name)},
		)
		if other:
			frappe.throw(
				_("{0} is already the active package for this inverter type.").format(frappe.bold(other)),
				title=_("One Package per Inverter Type"),
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


def package_for(inverter_type, company):
	"""The active Balance of System Package for this inverter type, or None."""
	if not inverter_type:
		return None
	return frappe.db.get_value(
		"Balance of System Package", {"inverter_type": inverter_type, "company": company, "is_active": 1}
	)
