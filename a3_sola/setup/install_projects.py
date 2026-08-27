# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Seeding for Solar Projects. Idempotent throughout."""

import frappe

from a3_sola.api.om import DEFAULT_COVERAGE, VISIT_CHECKLIST

PROJ_ROLES = [
	("Solar Project Manager", "Full Project, costing and billing plan access. Cannot post journal entries."),
	("Solar Accounts Executive", "Billing, invoicing, subsidy receivable and warranty recovery. Read-only on operations."),
	("Solar O&M Manager", "Full O&M including contract cancellation, SLA overrides and provision review."),
	("Solar Service Coordinator", "Ticket handling, visit scheduling and warranty claims. Read-only on financials."),
	("Solar Service Technician", "Visits and readings where assigned. Sees no Currency field anywhere."),
]

PROJ_ROLE_PROFILES = {
	"Solar Projects Management": ["Solar Project Manager", "Solar Accounts Executive", "Employee"],
	"Solar Service": ["Solar Service Coordinator", "Solar Service Technician", "Employee"],
	"Solar Service Management": ["Solar O&M Manager", "Solar Service Coordinator", "Employee"],
}

#: The client's actual payment terms, from their proposals:
#: 70% advance with the purchase order, 20% after delivery and installation,
#: 10% after commissioning - with the KSEBL-net-meter variant moving the last 10% to the
#: submission of completion documents, because DISCOM allocation runs two to four weeks.
MILESTONE_TEMPLATES = [
	{
		"template_name": "Standard 70:20:10 - Net Meter Purchased",
		"applicable_net_meter_mode": "Purchased by Customer",
		"applicable_funding": "Self Funded",
		"is_default": 1,
		"milestones": [
			("Advance with Purchase Order", "On Order", None, 70, "Customer", 1, 0),
			("After Delivery and Installation", "On Installation Stage", "INST", 20, "Customer", 0, 15),
			("After Commissioning", "On Installation Stage", "COMM", 10, "Customer", 0, 15),
		],
	},
	{
		"template_name": "Standard 70:20:10 - Net Meter from DISCOM",
		"applicable_net_meter_mode": "Availed from DISCOM on Rental",
		"applicable_funding": "Self Funded",
		"is_default": 0,
		"milestones": [
			("Advance with Purchase Order", "On Order", None, 70, "Customer", 1, 0),
			("After Delivery and Installation", "On Installation Stage", "INST", 20, "Customer", 0, 15),
			(
				"After Submission of Completion Documents", "On Installation Stage", "KTST", 10,
				"Customer", 0, 15,
			),
		],
	},
	{
		"template_name": "Financed (Jan Samarth) 70:30",
		"applicable_net_meter_mode": "Any",
		"applicable_funding": "Financed",
		"is_default": 0,
		"milestones": [
			("Advance on Loan Sanction", "On Loan Disbursement", None, 70, "Lender", 1, 0),
			("Balance on Completion Report", "On Installation Stage", "BCOM", 30, "Lender", 0, 15),
		],
	},
]

COST_CATEGORIES = [
	("Modules", 1, 0),
	("Inverters & Optimisers", 1, 0),
	("Mounting Structure", 1, 0),
	("Cables & Conduits", 1, 0),
	("DCDB / ACDB / Protection", 1, 0),
	("Earthing & Lightning Protection", 1, 0),
	("Meters", 1, 0),
	("Material", 1, 0),
	("Labour", 1, 0),
	("Subcontractor", 1, 0),
	("Logistics", 1, 0),
	("Liaison", 1, 0),
	("Rework", 1, 0),
	("O&M", 1, 0),
	# Paid to the DISCOM on the customer's behalf and recovered against receipts.
	# Booking it as cost would understate margin on every single job.
	("Statutory Fees", 0, 1),
]


def setup(company=None):
	create_roles()
	grant_project_financial_access()
	company = company or _default_company()
	if not company:
		return
	seed_project_type()
	seed_milestone_templates(company)
	seed_gst_rule(company)
	seed_opportunity_types()
	_set_defaults(company)


#: Who may see money on a solar job. A service technician is deliberately absent - the
#: costing and commercial fields on Project sit at permlevel 1 precisely so that a
#: technician on a roof never sees contract value, margin or provision.
FINANCIAL_ROLES = (
	"Accounts Manager",
	"Solar Accounts Executive",
	"Solar O&M Manager",
	"Solar Project Manager",
	"System Manager",
)


def grant_project_financial_access():
	"""Open permlevel 1 on Project to the financial roles, and to nobody else.

	Project belongs to ERPNext, so the grant is a Custom DocPerm rather than an edit to
	that app. Without it the costing tab is invisible to everyone, including the people
	whose job it is to read it.

	The copy first is not optional: the moment a doctype has any Custom DocPerm, Frappe
	stops reading its standard ones. Adding a level-1 row without copying would take
	ordinary Project access away from everybody in the system.
	"""
	from frappe.permissions import setup_custom_perms

	setup_custom_perms("Project")

	for role in FINANCIAL_ROLES:
		if not frappe.db.exists("Role", role):
			continue
		if frappe.db.exists("Custom DocPerm", {"parent": "Project", "role": role, "permlevel": 1}):
			continue
		frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "Project",
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": 1,
				"read": 1,
				"write": 1,
			}
		).insert(ignore_permissions=True)
	frappe.clear_cache(doctype="Project")


def _default_company():
	from a3_sola.setup.install import default_company

	return default_company()


def create_roles():
	for role, _desc in PROJ_ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
				"is_custom": 1,
				"search_bar": 1,
				"notifications": 1,
				"list_sidebar": 1,
				"bulk_actions": 1,
				"form_sidebar": 1,
				"timeline": 1,
				"dashboard": 1,
			}
		).insert(ignore_permissions=True)

	for profile, roles in PROJ_ROLE_PROFILES.items():
		available = [r for r in roles if frappe.db.exists("Role", r)]
		if not available or frappe.db.exists("Role Profile", profile):
			continue
		frappe.get_doc(
			{"doctype": "Role Profile", "role_profile": profile, "roles": [{"role": r} for r in available]}
		).insert(ignore_permissions=True)


def seed_project_type():
	if frappe.db.exists("Project Type", "Solar Rooftop Installation"):
		return
	frappe.get_doc(
		{"doctype": "Project Type", "project_type": "Solar Rooftop Installation"}
	).insert(ignore_permissions=True)


def seed_opportunity_types():
	for name in ("AMC Renewal", "System Expansion"):
		if frappe.db.exists("Opportunity Type", name):
			continue
		frappe.get_doc({"doctype": "Opportunity Type", "name": name}).insert(ignore_permissions=True)


def seed_milestone_templates(company):
	for spec in MILESTONE_TEMPLATES:
		if frappe.db.exists(
			"Billing Milestone Template", {"template_name": spec["template_name"], "company": company}
		):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Billing Milestone Template",
				"template_name": spec["template_name"],
				"applicable_consumer_category": "All",
				"applicable_net_meter_mode": spec["applicable_net_meter_mode"],
				"applicable_funding": spec["applicable_funding"],
				"is_default": spec["is_default"],
				"is_active": 1,
				"company": company,
				"milestones": [
					{
						"milestone_name": name,
						"trigger_type": trigger,
						"trigger_stage_code": stage,
						"percentage": percent,
						"funding_source": funding,
						"is_advance": advance,
						"credit_days": credit,
					}
					for name, trigger, stage, percent, funding, advance, credit in spec["milestones"]
				],
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


def seed_gst_rule(company):
	"""Seeded INACTIVE by design.

	The client's proposals quote a single all-inclusive figure and state no valuation basis.
	Activating a rule is a decision their CA must make, so the seeded rule is a starting
	point to be reviewed - not a default to be inherited silently.
	"""
	if frappe.db.exists("Solar GST Valuation Rule", {"rule_name": "Solar EPC 70:30 Composite", "company": company}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Solar GST Valuation Rule",
			"rule_name": "Solar EPC 70:30 Composite",
			"valuation_mode": "Blended 70:30",
			"applicable_consumer_category": "All",
			"effective_from": "2026-04-01",
			"is_active": 0,
			"company": company,
			"goods_value_percent": 70,
			"services_value_percent": 30,
			"services_sac_code": "9954",
			"notes": (
				"<p><strong>Review before activating.</strong> Solar EPC is treated as a composite "
				"supply and the industry commonly applies a 70:30 valuation, with the goods rate "
				"having moved to 5% in the September 2025 reform. Published sources still "
				"disagree, some EPCs bill goods and services on separate lines for input-credit "
				"clarity, and the correct treatment depends on contract structure.</p>"
				"<p>The client's own proposals quote a single all-inclusive figure and state no "
				"basis at all, so there is nothing to infer from them. Confirm the treatment with "
				"the chartered accountant, attach the item tax templates, record the confirmation "
				"on A3 Sola Settings, then activate this rule. Ledger postings stay blocked until "
				"that confirmation is recorded.</p>"
			),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)


def _set_defaults(company):
	settings = frappe.get_single("A3 Sola Settings")
	changed = False

	if not settings.project_type_solar and frappe.db.exists("Project Type", "Solar Rooftop Installation"):
		settings.project_type_solar = "Solar Rooftop Installation"
		changed = True

	if not settings.default_billing_milestone_template:
		settings.default_billing_milestone_template = frappe.db.get_value(
			"Billing Milestone Template", {"is_default": 1, "company": company}, "name"
		)
		changed = changed or bool(settings.default_billing_milestone_template)

	if not settings.cost_categories:
		for name, direct, pass_through in COST_CATEGORIES:
			settings.append(
				"cost_categories",
				{
					"category_name": name,
					"include_in_direct_cost": direct,
					"is_pass_through": pass_through,
				},
			)
		changed = True

	# Scaffold the account mapping row so the accountant has somewhere to map into.
	if not any(row.company == company for row in settings.solar_account_mapping):
		settings.append("solar_account_mapping", {"company": company})
		changed = True

	if changed:
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
