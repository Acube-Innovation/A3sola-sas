# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Manufacturer warranty claims.

Settled between the vendor or the customer and the manufacturer; DISCOMs and implementing
agencies are excluded from warranty disputes. Warranty expiry is computed from the make's
own term, so a Rayzon module and a Vikram module on adjacent roofs expire three years apart.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_years, flt, getdate

from a3_sola.api import om
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("om_contract", "Solar OM Contract"),
	("project", "Project"),
	("solar_installation", "Solar Installation"),
	("service_ticket", "Service Ticket"),
)


class SolarWarrantyClaim(Document):
	def autoname(self):
		set_name(self, "warranty_claim_series_prefix", ".YYYY.-.#####", fallback="SOL-WCL")

	def validate(self):
		assert_same_company(self, LINKS)
		self.pull_context()
		self.validate_serial_belongs_here()
		self.compute_warranty_position()
		self.compute_cost()

	def pull_context(self):
		contract = frappe.get_cached_doc("Solar OM Contract", self.om_contract)
		self.project = contract.project
		self.solar_installation = contract.solar_installation

	def validate_serial_belongs_here(self):
		"""The serial must be in this installation's Phase 2 register - traceability is the point."""
		row = frappe.db.get_value(
			"Installation Serial Register",
			{"parent": self.solar_installation, "serial_no": self.serial_no},
			["name", "manufacturer", "dcr_certificate_no", "component_type"],
			as_dict=True,
		)
		if row:
			self.manufacturer = self.manufacturer or row.manufacturer
			self.dcr_certificate_no = row.dcr_certificate_no
			return

		elsewhere = frappe.db.get_value(
			"Installation Serial Register", {"serial_no": self.serial_no}, "parent"
		)
		if elsewhere:
			frappe.throw(
				_("Serial {0} belongs to installation {1}, not {2}. Raise the claim against the "
				  "correct installation.").format(
					frappe.bold(self.serial_no),
					frappe.utils.get_link_to_form("Solar Installation", elsewhere),
					self.solar_installation,
				),
				title=_("Serial on Another Installation"),
			)
		frappe.throw(
			_("Serial {0} is not in the serial register for {1}. A warranty claim must trace to a "
			  "recorded serial.").format(frappe.bold(self.serial_no), self.solar_installation),
			title=_("Serial Not Registered"),
		)

	def compute_warranty_position(self):
		"""Expiry from THIS make's term, and the claim basis chosen."""
		contract = frappe.get_cached_doc("Solar OM Contract", self.om_contract)
		make = (
			contract.module_make
			if self.component_type == "Module"
			else contract.inverter_make
			if self.component_type in ("Inverter", "Optimiser")
			else None
		)
		self.component_make = make
		years = om.warranty_years_for(make, self.claim_basis) or contract.workmanship_warranty_years or 5
		self.warranty_years_applicable = years

		start = getdate(contract.start_date)
		self.warranty_expiry_date = add_years(start, int(years))
		failure = getdate(self.failure_date) if self.failure_date else getdate(frappe.utils.today())
		self.is_within_warranty = 1 if failure <= getdate(self.warranty_expiry_date) else 0

		if not self.is_within_warranty:
			frappe.msgprint(
				_("The failure date {0} is outside the {1}-year warranty, which expired on {2}. "
				  "The manufacturer is likely to reject this claim.").format(
					failure, years, self.warranty_expiry_date
				),
				title=_("Outside Warranty"),
				indicator="orange",
			)

	def compute_cost(self):
		self.cost_borne_by_company = flt(flt(self.claim_value) - flt(self.amount_recovered), 2)

	def before_update_after_submit(self):
		# Before, not after: on_update_after_submit runs past the write, so anything
		# computed there is thrown away.
		self.compute_cost()

	def on_update_after_submit(self):
		if self.claim_status == "Replaced" and self.replacement_serial_no:
			self.update_serial_register()

	def update_serial_register(self):
		"""Traceability must survive the swap, or the DCR manifest goes stale."""
		installation = frappe.get_doc("Solar Installation", self.solar_installation)
		old = next((r for r in installation.serials if r.serial_no == self.serial_no), None)
		if not old or old.is_replaced:
			return

		old.is_replaced = 1
		old.replaced_by_serial = self.replacement_serial_no
		installation.append(
			"serials",
			{
				"component_type": old.component_type,
				"serial_no": self.replacement_serial_no,
				"item": old.item,
				"manufacturer": old.manufacturer,
				"model_number": old.model_number,
				"wattage": old.wattage,
				"dcr_certificate_no": old.dcr_certificate_no,
				"warranty_start_date": self.replacement_installed_on,
			},
		)
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)
		installation.add_comment(
			"Comment",
			_("Serial {0} replaced by {1} under warranty claim {2}.").format(
				self.serial_no, self.replacement_serial_no, self.name
			),
		)
