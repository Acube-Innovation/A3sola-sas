# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The central record of the Operations module.

Status, current stage, progress and blocking party are derived on every save and are never
settable by hand.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api import documents, serials, stages, statutory
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("solar_consumer", "Solar Consumer"),
	("solar_design_estimate", "Solar Design Estimate"),
	("subsidy_eligibility_check", "Subsidy Eligibility Check"),
	("solar_proposal", "Solar Proposal"),
	("solar_package", "Solar Package"),
	("stage_template", "Installation Stage Template"),
	("discom", "DISCOM"),
	("discom_section", "DISCOM Section"),
	("subsidy_scheme", "Subsidy Scheme"),
	("sales_order", "Sales Order"),
	("quotation", "Quotation"),
)


class SolarInstallation(Document):
	def autoname(self):
		set_name(self, "installation_series_prefix", ".YYYY.-.#####", fallback="SOL-INST")

	def validate(self):
		assert_same_company(self, LINKS)
		self.resolve_template()
		self.pull_consumer_defaults()
		self.apply_package_defaults()
		if not self.stages:
			stages.build_stages(self)
		self.validate_capacity()
		self.resolve_statutory()
		serials.validate_register(self)
		self.roll_counts()
		stages.recompute(self)

	def resolve_template(self):
		if self.stage_template:
			return
		self.stage_template = stages.resolve_template(
			self.subsidy_scheme,
			self.system_type,
			frappe.db.get_value("Solar Consumer", self.solar_consumer, "consumer_category"),
			self.company,
		)

	def pull_consumer_defaults(self):
		"""The consumer record already knows who the party is; carry it across.

		Everything downstream - the billing plan, the O&M contract, the renewal
		opportunity - needs a party, and leaving it blank here strands all three.
		"""
		if self.customer or not self.solar_consumer:
			return
		self.customer = frappe.db.get_value("Solar Consumer", self.solar_consumer, "customer")

	def apply_package_defaults(self):
		"""Carry the package's bill of materials onto the installation.

		The package master is where the client records the actual makes - Rayzon modules,
		Solinteg inverters - and those makes drive serial validation, the DCR declaration
		and every warranty term downstream. Site-specific overrides are respected; only
		blanks are filled.
		"""
		if not self.solar_package:
			return
		package = frappe.get_cached_doc("Solar Package", self.solar_package)
		mapping = {
			"module_make": package.module_make,
			"module_wattage": package.module_wattage,
			"module_count": package.module_count,
			"inverter_make": package.inverter_1_make,
			"inverter_capacity_kw": package.inverter_1_capacity_kw,
			"system_type": package.system_type,
			"connection_type": package.connection_type,
		}
		for fieldname, value in mapping.items():
			if value and not self.get(fieldname):
				self.set(fieldname, value)
		if self.is_new() and not self.is_dcr_compliant:
			self.is_dcr_compliant = package.is_dcr_compliant

	def validate_capacity(self):
		"""Capacity must match the design estimate unless a manager overrode it."""
		if not self.solar_design_estimate:
			return
		designed = flt(
			frappe.db.get_value("Solar Design Estimate", self.solar_design_estimate, "final_capacity_kw"), 3
		)
		if not designed or flt(self.capacity_kw, 3) == designed:
			return
		if not set(frappe.get_roles()).intersection(stages.MANAGER_ROLES):
			frappe.throw(
				_("Capacity {0} kW does not match design estimate {1} at {2} kW. Only an operations manager may override this.").format(
					self.capacity_kw, self.solar_design_estimate, designed
				),
				title=_("Capacity Mismatch"),
			)
		self.flags.capacity_overridden = designed

	def resolve_statutory(self):
		"""Fees follow the capacity. A change of capacity changes what the customer owes."""
		if not (self.discom and self.capacity_kw):
			return
		try:
			fees = statutory.get_statutory_fees(
				self.discom,
				self.connection_type or "Single Phase",
				self.capacity_kw,
				self.net_meter_mode or "Purchased by Customer",
				company=self.company,
			)
		except frappe.ValidationError:
			return
		self.kseb_application_fee = fees["application_fee_gross"]
		self.kseb_registration_fee = fees["registration_fee_gross"]
		self.kseb_registration_refundable = fees["registration_refundable"]
		self.net_meter_charge = fees["net_meter_charge"]
		self.statutory_total = fees["statutory_total"]

	def roll_counts(self):
		if self.is_new():
			return
		self.open_snag_count = frappe.db.count(
			"Installation Snag",
			{"solar_installation": self.name, "status": ["in", ["Open", "In Progress"]], "docstatus": ["<", 2]},
		)
		self.critical_snag_count = frappe.db.count(
			"Installation Snag",
			{
				"solar_installation": self.name,
				"severity": "Critical",
				"status": ["in", ["Open", "In Progress"]],
				"docstatus": ["<", 2],
			},
		)
		self.stale_document_count = len([r for r in self.generated_documents if r.is_stale])
		mandatory = [r for r in self.documents if r.is_mandatory]
		self.document_pack_complete = 1 if mandatory and all(r.attachment for r in mandatory) else 0

	def on_submit(self):
		if self.flags.capacity_overridden:
			self.add_comment(
				"Comment",
				_("Capacity overridden from {0} kW (design estimate) to {1} kW by {2}.").format(
					self.flags.capacity_overridden, self.capacity_kw, frappe.session.user
				),
			)
		for row in self.stages:
			if row.status == "Pending":
				row.status = "In Progress"
				row.actual_start_date = self.order_date
				break
		stages.recompute(self)

	def before_update_after_submit(self):
		"""Execution happens after submit, so the guards must run here too.

		Serial capture, document generation and stage transitions all edit a submitted
		installation. Running only `validate` would leave the serial uniqueness guard - a
		compliance control, not a nicety - unenforced for the whole life of the job.

		This is the BEFORE hook deliberately: `on_update_after_submit` runs after the row
		has already been written, so anything computed there is silently discarded.
		"""
		serials.validate_register(self)
		self.roll_counts()
		stages.recompute(self)

	def on_cancel(self):
		self.status = "Cancelled"


# ------------------------------------------------------------------ form actions
@frappe.whitelist()
def verify_document(installation, row_name):
	"""Stamp a checklist row as verified. Evidence must be checked, not just attached."""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")
	for row in doc.documents:
		if row.name == row_name:
			if not row.attachment:
				frappe.throw(_("Attach {0} before verifying it.").format(row.document_name))
			row.is_verified = 1
			row.verified_by = frappe.session.user
			row.verified_on = frappe.utils.now_datetime()
			break
	else:
		frappe.throw(_("Checklist row not found."))
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return True


@frappe.whitelist()
def get_stage_chain_html(installation):
	"""The visual stage chain rendered on the form."""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("read")
	colours = {
		"Pending": ("#e9ecef", "#495057"),
		"In Progress": ("#cfe2ff", "#084298"),
		"Blocked": ("#f8d7da", "#842029"),
		"Completed": ("#d1e7dd", "#0f5132"),
		"Skipped": ("#f1f3f5", "#868e96"),
	}
	chips = []
	for row in doc.stages:
		bg, fg = colours.get(row.status, ("#e9ecef", "#495057"))
		if row.is_sla_breached:
			bg, fg = "#f8d7da", "#842029"
		title = row.skip_reason or row.blocked_reason or f"{row.status} - SLA {row.sla_days or 0}d"
		chips.append(
			f'<span title="{frappe.utils.escape_html(title)}" style="display:inline-block;margin:2px 4px 2px 0;'
			f'padding:3px 9px;border-radius:11px;font-size:11px;background:{bg};color:{fg};'
			f'{"text-decoration:line-through;" if row.status == "Skipped" else ""}">'
			f"{frappe.utils.escape_html(row.stage_code)} · {frappe.utils.escape_html(row.stage_name)}</span>"
		)
	return "<div style='line-height:2'>" + "".join(chips) + "</div>"
