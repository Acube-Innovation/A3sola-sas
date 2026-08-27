# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The five-year operation and maintenance obligation.

Not a service module - a liability. The obligation runs from the date of DISCOM
commissioning, the performance ratio must be maintained at the contractual floor for the
whole period, and the ministry can temporarily deactivate a vendor that fails to resolve
complaints or rectify defects.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from a3_sola.api import om, stages
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("project", "Project"),
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
	("solar_package", "Solar Package"),
)
MANAGER_ROLES = ("Solar O&M Manager", "Solar Operations Manager", "System Manager")


class SolarOMContract(Document):
	def autoname(self):
		set_name(self, "om_contract_series_prefix", ".YYYY.-.#####", fallback="SOL-AMC")

	def validate(self):
		assert_same_company(self, LINKS)
		self.validate_one_per_project()
		self.set_duration()
		om.compute_warranty_terms(self)
		om.build_visit_plan(self)
		om.refresh_contract_compliance(self)
		om.refresh_contract_financials(self)

	def validate_one_per_project(self):
		"""One live contract per project - but a renewal succeeds rather than competes."""
		existing = frappe.db.get_value(
			"Solar OM Contract",
			{
				"project": self.project,
				"name": ["!=", self.name],
				"docstatus": ["<", 2],
				"status": ["not in", ["Renewed", "Terminated", "Expired"]],
			},
			"name",
		)
		if existing and existing == self.renewed_from:
			return
		if existing:
			frappe.throw(
				_("Project {0} already has contract {1}.").format(
					self.project, frappe.utils.get_link_to_form("Solar OM Contract", existing)
				)
			)

	def set_duration(self):
		if self.start_date and self.end_date:
			days = frappe.utils.date_diff(self.end_date, self.start_date)
			self.duration_years = max(round(days / 365.0), 1)
		self.is_scheme_mandated = (
			1
			if frappe.db.get_value("Solar Installation", self.solar_installation, "subsidy_scheme")
			else 0
		)

	def on_submit(self):
		self.status = "Active"
		om.refresh_contract_compliance(self)

	def before_update_after_submit(self):
		om.refresh_contract_compliance(self)
		om.refresh_contract_financials(self)

	def before_cancel(self):
		"""A scheme-mandated contract is a registration condition, not a commercial choice."""
		if not self.is_scheme_mandated:
			return
		if not set(frappe.get_roles()).intersection(MANAGER_ROLES):
			frappe.throw(
				_("This is a scheme-mandated five-year obligation and cannot be cancelled by "
				  "your role. The obligation is a condition of the vendor's registration."),
				frappe.PermissionError,
			)
		frappe.msgprint(
			_("You are cancelling a scheme-mandated O&M obligation. Record why in the comments - "
			  "failing the obligation is a vendor-registration risk."),
			title=_("Scheme-Mandated Contract"),
			indicator="red",
		)


@frappe.whitelist()
def renew_contract(om_contract, contract_value=None, years=1):
	"""Create a paid successor dated from the predecessor's end date."""
	source = frappe.get_doc("Solar OM Contract", om_contract)
	source.check_permission("write")
	if source.status == "Renewed":
		frappe.throw(_("Contract {0} has already been renewed.").format(om_contract))

	successor = frappe.copy_doc(source)
	successor.contract_type = "AMC (Paid Renewal)"
	successor.start_date = frappe.utils.add_days(getdate(source.end_date), 1)
	successor.end_date = frappe.utils.add_years(getdate(source.end_date), int(years))
	successor.contract_value = contract_value or 0
	successor.set("visit_plan", [])
	successor.set("performance_log", [])
	successor.status = "Draft"
	successor.flags.ignore_permissions = True
	successor.insert(ignore_permissions=True)
	successor.submit()

	source.db_set("status", "Renewed", update_modified=False)
	source.add_comment("Comment", _("Renewed as {0}.").format(successor.name))
	return successor.name
