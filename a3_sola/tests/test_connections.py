# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt
"""The Connections panels, which are how the app is navigated.

Every panel is a promise that a named field on a named doctype points back here. Rename
that field and the panel does not break - it quietly renders an empty section, and the
job that was two clicks away is now unreachable. These tests fail instead.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

#: Every doctype this app puts a Connections panel on, its own or ERPNext's.
PANELS = (
	"Lead",
	"Solar Consumer",
	"Site Survey",
	"Solar Design Estimate",
	"Subsidy Eligibility Check",
	"Solar Proposal",
	"Quotation",
	"Sales Order",
	"Sales Invoice",
	"Solar Installation",
	"Installation Work Order",
	"Installation Snag",
	"Portal Application",
	"Statutory Fee Payment",
	"Commissioning Report",
	"Loan Application",
	"Project",
	"Solar Billing Plan",
	"Solar OM Contract",
	"Solar OM Visit",
	"Service Ticket",
	"Solar Warranty Claim",
	"Subscription Signup",
	"Payment Order",
	"Platform Subscription",
	"Payment Mandate",
	"Provisioning Job",
	"Tenant",
)

#: The doctypes the app itself adds to a panel. ERPNext's own entries are its business:
#: several of them resolve through a child table and a few are for optional apps.
OURS = {
	"Solar Consumer", "Site Survey", "Solar Design Estimate", "Subsidy Eligibility Check",
	"Solar Proposal", "Solar Installation", "Installation Work Order", "Installation Snag",
	"Portal Application", "Statutory Fee Payment", "Net Metering Agreement", "Subsidy Claim",
	"Loan Application", "Commissioning Report", "Solar Billing Plan", "Solar OM Contract",
	"Solar OM Visit", "Service Ticket", "Solar Warranty Claim", "Generation Reading",
	"Statutory Fee Recovery", "Subscription Signup", "Payment Order", "Payment Transaction",
	"Platform Subscription", "Payment Mandate", "Subscription Invoice", "Provisioning Job",
	"Tenant", "Tenant Invitation", "Project",
}


def resolved_items(doctype):
	"""(child doctype, fieldname) for every item on a doctype's panel, the way the
	Connections panel resolves them: the panel's default fieldname unless the item has
	its own entry in non_standard_fieldnames."""
	data = frappe.get_meta(doctype).get_dashboard_data()
	default = data.get("fieldname")
	non_standard = data.get("non_standard_fieldnames") or {}
	items = []
	for group in data.get("transactions") or []:
		for item in group.get("items") or []:
			items.append((item, non_standard.get(item) or default))
	return items


def dynamic_links(doctype):
	return frappe.get_meta(doctype).get_dashboard_data().get("dynamic_links") or {}


class TestConnectionPanels(FrappeTestCase):
	def test_every_item_this_app_adds_points_back(self):
		"""Each doctype the app lists is reachable by the fieldname the panel names."""
		broken = []
		for doctype in PANELS:
			for item, fieldname in resolved_items(doctype):
				if item not in OURS:
					continue
				field = frappe.get_meta(item).get_field(fieldname)
				if not field:
					broken.append(f"{doctype}: {item} has no field {fieldname}")
				elif field.fieldtype == "Dynamic Link":
					# Valid only if the panel says which field carries the doctype -
					# otherwise it lists every document that shares a name.
					if fieldname not in (dynamic_links(doctype) or {}):
						broken.append(
							f"{doctype}: {item}.{fieldname} is a Dynamic Link with no "
							f"dynamic_links entry on the panel"
						)
				elif field.fieldtype != "Link" or field.options != doctype:
					broken.append(
						f"{doctype}: {item}.{fieldname} is a {field.fieldtype} "
						f"to {field.options}, not a link to {doctype}"
					)
		self.assertEqual(broken, [], "\n".join(broken))

	def test_no_item_is_listed_twice_on_one_panel(self):
		for doctype in PANELS:
			items = [item for item, _ in resolved_items(doctype)]
			duplicates = {i for i in items if items.count(i) > 1}
			self.assertEqual(duplicates, set(), f"{doctype} lists {duplicates} more than once")

	def test_erpnext_panels_are_extended_not_replaced(self):
		"""The override hook adds to ERPNext's dashboard. Returning our own data instead
		would silently drop Sales Order from a Quotation and Task from a Project."""
		for doctype, kept, added in (
			("Quotation", "Sales Order", "Solar Installation"),
			("Project", "Task", "Solar OM Contract"),
			("Sales Order", "Delivery Note", "Solar Billing Plan"),
			("Sales Invoice", "Payment Entry", "Solar OM Visit"),
			("Lead", "Opportunity", "Solar Consumer"),
		):
			items = [item for item, _ in resolved_items(doctype)]
			self.assertIn(kept, items, f"{doctype} lost ERPNext's own {kept}")
			self.assertIn(added, items, f"{doctype} is missing {added}")

	def test_the_chain_runs_from_the_lead_to_service(self):
		"""Each link of the pipeline is on the panel of the document before it, so the
		whole job can be walked forward without using the search bar."""
		for parent, child in (
			("Lead", "Solar Consumer"),
			("Solar Consumer", "Site Survey"),
			("Site Survey", "Solar Design Estimate"),
			("Solar Design Estimate", "Solar Proposal"),
			("Solar Design Estimate", "Subsidy Eligibility Check"),
			("Solar Proposal", "Quotation"),
			("Quotation", "Sales Order"),
			("Sales Order", "Solar Installation"),
			("Solar Installation", "Installation Work Order"),
			("Solar Installation", "Commissioning Report"),
			("Solar Installation", "Project"),
			("Commissioning Report", "Net Metering Agreement"),
			("Project", "Solar Billing Plan"),
			("Project", "Solar OM Contract"),
			("Solar OM Contract", "Solar OM Visit"),
			("Solar OM Visit", "Service Ticket"),
			("Service Ticket", "Solar Warranty Claim"),
			("Subscription Signup", "Platform Subscription"),
			("Platform Subscription", "Payment Order"),
			("Payment Order", "Payment Transaction"),
			("Platform Subscription", "Tenant"),
			("Tenant", "Tenant Invitation"),
		):
			items = [item for item, _ in resolved_items(parent)]
			self.assertIn(child, items, f"{parent} does not offer {child}")
