# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Seeding for Solar Operations. Idempotent throughout."""

import frappe

from a3_sola.setup import seed_documents, seed_stages
from a3_sola.setup.roles import create_roles as create_crm_roles

OPS_ROLES = [
	("Solar Operations Executive", "Creates installations, advances internal stages, manages documents and materials."),
	("Solar Site Engineer", "Commissioning, snags, serial capture and material requests."),
	("Solar Technician", "Work orders where on the crew. Sees no commercial figure and no Subsidy Claim."),
	("Solar Liaison Officer", "Chases the DISCOM and the inspectorate; advances externally-owned stages only."),
	("Solar Documentation Officer", "Prepares and issues the DISCOM, portal and bank packs."),
	("Solar QC Inspector", "Raises and verifies snags; verifies documents."),
	("Solar Operations Manager", "Full access including skip, revert, subsidy claim and settings."),
]

OPS_ROLE_PROFILES = {
	"Solar Operations": ["Solar Operations Executive", "Solar Site Engineer", "Employee"],
	"Solar Documentation": ["Solar Documentation Officer", "Solar Liaison Officer", "Employee"],
	"Solar Field Crew": ["Solar Technician", "Employee"],
	"Solar Operations Management": [
		"Solar Operations Manager", "Solar Operations Executive", "Solar QC Inspector", "Employee"
	],
}


def setup(company=None):
	create_roles()
	company = company or _default_company()
	if not company:
		return
	# Order matters: a checklist links a document template, and a stage template links a
	# checklist. Seeding a stage template first leaves it with no checklist at all.
	seed_document_templates(company)
	seed_checklists(company)
	seed_stage_templates(company)
	seed_template_sets(company)
	backfill_checklist_links(company)
	_set_defaults(company)


def _default_company():
	from a3_sola.setup.install import default_company

	return default_company()


def create_roles():
	create_crm_roles()
	for role, _desc in OPS_ROLES:
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

	for profile, roles in OPS_ROLE_PROFILES.items():
		available = [r for r in roles if frappe.db.exists("Role", r)]
		if not available or frappe.db.exists("Role Profile", profile):
			continue
		frappe.get_doc(
			{"doctype": "Role Profile", "role_profile": profile, "roles": [{"role": r} for r in available]}
		).insert(ignore_permissions=True)


# ------------------------------------------------------------------- checklists
def seed_checklists(company):
	for stage_code, (name, items) in seed_stages.CHECKLISTS.items():
		title = f"{name} ({stage_code})"
		if frappe.db.exists("Document Checklist Template", {"template_name": title, "company": company}):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Document Checklist Template",
				"template_name": title,
				"stage_code": stage_code,
				"company": company,
				"items": [
					{
						"document_name": document,
						"is_mandatory": mandatory,
						"requires_verification": 1 if mandatory else 0,
						"solar_document_template": _template_name(template_code, company),
					}
					for document, mandatory, template_code in items
				],
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


def _template_name(template_code, company):
	if not template_code:
		return None
	return frappe.db.get_value(
		"Solar Document Template", {"template_code": template_code, "company": company}, "name"
	)


# --------------------------------------------------------------- stage templates
def seed_stage_templates(company):
	scheme = frappe.db.get_value(
		"Subsidy Scheme", {"scheme_name": "PM Surya Ghar: Muft Bijli Yojana", "company": company}, "name"
	)
	_seed_chain(
		company,
		"PM Surya Ghar Residential (Default)",
		seed_stages.RESIDENTIAL_CHAIN,
		scheme=scheme,
		consumer_category="Residential",
		is_default=1,
	)
	commercial = [row for row in seed_stages.RESIDENTIAL_CHAIN if row[0] in seed_stages.COMMERCIAL_CHAIN]
	_seed_chain(company, "Commercial / Non-Subsidy", commercial, consumer_category="Commercial")


def _seed_chain(company, template_name, chain, scheme=None, consumer_category="All", is_default=0):
	if frappe.db.exists("Installation Stage Template", {"template_name": template_name, "company": company}):
		return
	doc = frappe.get_doc(
		{
			"doctype": "Installation Stage Template",
			"template_name": template_name,
			"applicable_scheme": scheme,
			"consumer_category": consumer_category,
			"is_default": is_default,
			"is_active": 1,
			"company": company,
			"stages": [
				{
					"stage_code": code,
					"stage_name": name,
					"owner_type": owner,
					"sla_days": sla,
					"is_mandatory": mandatory,
					"applicability": applicability,
					"applicability_threshold_kw": threshold,
					"display_order": index,
					"stage_description": description,
					"document_checklist_template": frappe.db.get_value(
						"Document Checklist Template",
						{"stage_code": code, "company": company},
						"name",
					),
				}
				for index, (code, name, owner, sla, mandatory, applicability, threshold, description)
				in enumerate(chain, start=1)
			],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)


# ------------------------------------------------------------ document templates
def seed_document_templates(company):
	for spec in seed_documents.TEMPLATES:
		if frappe.db.exists(
			"Solar Document Template", {"template_code": spec["template_code"], "company": company}
		):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Solar Document Template",
				"template_code": spec["template_code"],
				"document_name": spec["document_name"],
				"category": spec["category"],
				"recipient": spec.get("recipient"),
				"stage_code": spec.get("stage_code"),
				"source_doctype": spec.get("source_doctype", "Solar Installation"),
				"signatory": spec.get("signatory"),
				"requires_stamp_paper": spec.get("requires_stamp_paper", 0),
				"requires_company_seal": spec.get("requires_company_seal", 0),
				"attachment_checklist": spec.get("attachment_checklist"),
				"body_template": spec["body"],
				"notes": spec.get("notes"),
				"is_mandatory": 1,
				"is_active": 1,
				"version": 1,
				"company": company,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


def seed_template_sets(company):
	scheme = frappe.db.get_value(
		"Subsidy Scheme", {"scheme_name": "PM Surya Ghar: Muft Bijli Yojana", "company": company}, "name"
	)
	for set_name, codes in seed_documents.TEMPLATE_SETS.items():
		if frappe.db.exists("Document Template Set", {"set_name": set_name, "company": company}):
			continue
		templates = []
		for order, code in enumerate(codes, start=1):
			name = _template_name(code, company)
			if name:
				templates.append({"solar_document_template": name, "display_order": order, "is_mandatory": 1})
		doc = frappe.get_doc(
			{
				"doctype": "Document Template Set",
				"set_name": set_name,
				"applicable_scheme": scheme if "PM Surya Ghar" in set_name else None,
				"is_default": 1 if set_name.endswith("Self Funded") else 0,
				"is_active": 1,
				"company": company,
				"templates": templates,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


def _set_defaults(company):
	settings = frappe.get_single("A3 Sola Settings")
	changed = False
	if not settings.default_stage_template:
		settings.default_stage_template = frappe.db.get_value(
			"Installation Stage Template", {"is_default": 1, "company": company}, "name"
		)
		changed = bool(settings.default_stage_template)
	if not settings.default_document_template_set:
		settings.default_document_template_set = frappe.db.get_value(
			"Document Template Set", {"is_default": 1, "company": company}, "name"
		)
		changed = changed or bool(settings.default_document_template_set)
	if not settings.escalation_role and frappe.db.exists("Role", "Solar Operations Manager"):
		settings.escalation_role = "Solar Operations Manager"
		changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)


def backfill_checklist_links(company):
	"""Repair links seeded out of order.

	A checklist links a document template and a stage template links a checklist. Anything
	seeded before its target existed carries a null link, and a null link means a generated
	document never files itself into the checklist it satisfies.
	"""
	# checklist item -> document template
	wanted = {
		document: code
		for _stage, (_name, items) in seed_stages.CHECKLISTS.items()
		for document, _mandatory, code in items
		if code
	}
	for name in frappe.get_all(
		"Document Checklist Template", filters={"company": company}, pluck="name"
	):
		doc = frappe.get_doc("Document Checklist Template", name)
		changed = False
		for row in doc.items:
			if row.solar_document_template:
				continue
			code = wanted.get(row.document_name)
			template = _template_name(code, company) if code else None
			if template:
				row.solar_document_template = template
				changed = True
		if changed:
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)

	_backfill_stage_links(company)


def _backfill_stage_links(company):
	"""Repair stage templates seeded before their checklists existed."""
	for name in frappe.get_all(
		"Installation Stage Template", filters={"company": company}, pluck="name"
	):
		doc = frappe.get_doc("Installation Stage Template", name)
		changed = False
		for row in doc.stages:
			if row.document_checklist_template:
				continue
			checklist = frappe.db.get_value(
				"Document Checklist Template",
				{"stage_code": row.stage_code, "company": company},
				"name",
			)
			if checklist:
				row.document_checklist_template = checklist
				changed = True
		if changed:
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)
