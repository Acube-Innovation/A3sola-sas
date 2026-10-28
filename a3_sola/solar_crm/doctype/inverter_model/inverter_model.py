# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One inverter model as the master price list gives it.

The rate is the model's price; a package's system price is built on one model, so an
estimate that takes another model is repriced by the difference (`price`). A string
inverter with optimizer carries the optimizer's model, price and quantity; a micro inverter
is sold as a kit of `units` inverters, its contents printed as the specification.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

PHASE_CODES = {"Single Phase": "1PH", "Three Phase": "3PH"}


class InverterModel(Document):
	def autoname(self):
		# HM-1000 is sold as a kit of 1 to 10 kW in either phase: the name carries both.
		self.name = "{0}-{1}-{2:g}kW".format(
			self.model_name.strip(), PHASE_CODES.get(self.inverter_phase, ""), flt(self.capacity_kw))

	def validate(self):
		self.units = cint(self.units) or 1
		self.optimizer_total = flt(flt(self.optimizer_price) * cint(self.optimizer_qty), 2)
		if not self.extension_available:
			self.extension_years = self.extension_rate = 0
		ctype = frappe.db.get_value("Component Make", self.inverter_make, "component_type")
		if ctype and ctype != "Inverter":
			frappe.throw(_("Make {0} is a {1} make, not an inverter make.").format(self.inverter_make, ctype))


def price(model, with_optimizer=False):
	"""The model's price, with its optimizer when taken. 0 for no model."""
	if not model:
		return 0.0
	row = frappe.db.get_value("Inverter Model", model, ["rate", "optimizer_total"], as_dict=True)
	if not row:
		return 0.0
	return flt(row.rate) + (flt(row.optimizer_total) if cint(with_optimizer) else 0.0)


def details(model):
	"""The model's row, or None."""
	return frappe.get_cached_doc("Inverter Model", model) if model and frappe.db.exists("Inverter Model", model) else None


def specification(model):
	"""What prints for the inverter: a kit's contents, else make, model, size and phase."""
	doc = details(model)
	if not doc:
		return ""
	if doc.kit_includes:
		return doc.kit_includes
	make = frappe.db.get_value("Component Make", doc.inverter_make, "make_name") or ""
	text = "{0} {1} {2:g} kW {3} {4} Inverter".format(
		make, doc.model_name, flt(doc.capacity_kw), PHASE_CODES.get(doc.inverter_phase, ""), doc.category or "")
	if doc.optimizer_model:
		text += " with {0} optimizer".format(doc.optimizer_model)
	return " ".join(text.split())


def fill_row(row, model, rate_field):
	"""Copy a model onto a package or estimate inverter row: make, size, count, phase,
	specification and the per-unit rate. Returns False when there is no such model."""
	doc = details(model)
	if not doc:
		return False
	units = cint(doc.units) or 1
	row.inverter_make = doc.inverter_make
	row.inverter_phase = doc.inverter_phase
	row.inverter_capacity_kw = flt(flt(doc.capacity_kw) / units, 3)
	if units > 1:
		row.inverter_count = units
	if rate_field:
		row.set(rate_field, flt(price(model, row.get("with_optimizer")) / units, 2))
	return True


def extension(model):
	"""The model's Warranty Extension add-on as (item, amount), or None when it has none."""
	doc = details(model)
	if not doc or not doc.extension_available or not cint(doc.extension_years):
		return None
	first, last = cint(doc.warranty_years) + 1, cint(doc.warranty_years) + cint(doc.extension_years)
	return (_("Warranty Extension for Inverter – {0} Year to {1} year").format(ordinal(first), ordinal(last)),
		flt(doc.extension_rate))


def ordinal(n):
	suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
	return "{0}{1}".format(n, suffix)
