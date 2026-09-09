# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Seeding for Solar Operations. Idempotent throughout, and self-healing on re-run.

Self-healing matters more than it used to: the task template is one record per company and
later releases add or re-point tasks. `seed_stage_templates` therefore synchronises the rows
of an existing template rather than skipping it, and never deletes a row - a task somebody
has already started must not vanish from the template underneath them.
"""

import frappe

from a3_sola.setup import seed_documents, seed_stages
from a3_sola.setup.roles import create_roles as create_crm_roles

OPS_ROLES = [
	("Solar Operations Executive", "Creates installations, works tasks, manages documents and materials."),
	("Solar Site Engineer", "Design freeze, work orders, commissioning, snags, serial capture and material requests."),
	("Solar Technician", "Work orders where on the crew. Sees no commercial figure and no Subsidy Claim."),
	("Solar Liaison Officer", "Chases the DISCOM and the inspectorate; works externally-owned tasks."),
	("Solar Documentation Officer", "Prepares and issues the DISCOM, portal and bank packs."),
	("Solar QC Inspector", "Raises and verifies snags; verifies documents."),
	("Solar Operations Manager", "Full access including skip, reopen, subsidy claim and settings."),
]

OPS_ROLE_PROFILES = {
	"Solar Operations": ["Solar Operations Executive", "Solar Site Engineer", "Employee"],
	"Solar Documentation": ["Solar Documentation Officer", "Solar Liaison Officer", "Employee"],
	"Solar Field Crew": ["Solar Technician", "Employee"],
	"Solar Operations Management": [
		"Solar Operations Manager", "Solar Operations Executive", "Solar QC Inspector", "Employee"
	],
}

#: The one template every company gets. Tasks are independent, so there is no residential
#: versus commercial chain any more - a commercial job simply pre-skips the subsidy tasks.
TASK_TEMPLATE_NAME = "Solar Installation Tasks"

#: Templates from before tasks existed. Left in place but inactive, because open
#: installations still link them until the rebuild patch re-points every job.
LEGACY_TEMPLATE_NAMES = ("PM Surya Ghar Residential (Default)", "Commercial / Non-Subsidy")

#: Fields on a template row that the seed owns. Anything else on the row is the tenant's.
SYNCED_ROW_FIELDS = (
	"stage_name", "owner_type", "sla_days", "responsible_role", "is_mandatory",
	"applicability", "applicability_threshold_kw", "task_doctype", "due_anchor_task",
	"due_anchor_days", "stage_description", "document_checklist_template", "display_order",
)


def setup(company=None):
	create_roles()
	company = company or _default_company()
	if not company:
		return
	# Order matters: a checklist links a document template, and a task template links a
	# checklist. Seeding a task template first leaves it with no expected documents at all.
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
	"""One expected-documents list per task that produces documents. Upserted, not skipped.

	Upserted because the list changes as tasks change, and a stale list would keep
	pre-creating register rows for documents nobody produces any more.
	"""
	for code, (name, items) in seed_stages.checklists().items():
		title = f"{name} ({code})"
		rows = [
			{
				"document_name": document,
				"is_mandatory": mandatory,
				"requires_verification": 0,
				"solar_document_template": _template_name(template_code, company),
			}
			for document, mandatory, template_code in items
		]
		existing = frappe.db.get_value(
			"Document Checklist Template", {"stage_code": code, "company": company}, "name"
		)
		if existing:
			doc = frappe.get_doc("Document Checklist Template", existing)
			if doc.template_name != title or _rows_differ(doc.items, rows):
				doc.template_name = title
				doc.set("items", rows)
				doc.flags.ignore_permissions = True
				doc.save(ignore_permissions=True)
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Document Checklist Template",
				"template_name": title,
				"stage_code": code,
				"company": company,
				"items": rows,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


def _rows_differ(current, wanted):
	keys = ("document_name", "is_mandatory", "solar_document_template")
	have = [tuple(row.get(k) for k in keys) for row in current]
	want = [tuple(row.get(k) for k in keys) for row in wanted]
	return have != want


def _template_name(template_code, company):
	if not template_code:
		return None
	return frappe.db.get_value(
		"Solar Document Template", {"template_code": template_code, "company": company}, "name"
	)


# --------------------------------------------------------------- task template
def seed_stage_templates(company=None):
	"""Exactly one task template, shared by every company: create it, or bring its rows up
	to date. `company` is accepted because provisioning seeds per company; it is ignored.

	The rows carry no checklist link: checklists are per company, and `stages.build_stages`
	looks the right one up for the job's company when the rows are copied onto it.
	"""
	existing = frappe.db.get_value("Installation Stage Template", {"is_shared": 1}, "name")
	if existing:
		doc = frappe.get_doc("Installation Stage Template", existing)
		changed = _sync_task_rows(doc)
		if not doc.is_active or not doc.is_default:
			doc.is_active, doc.is_default = 1, 1
			changed = True
		if changed:
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Installation Stage Template",
			"template_name": TASK_TEMPLATE_NAME,
			"applicable_scheme": None,
			"applicable_system_type": "All",
			"consumer_category": "All",
			"is_default": 1,
			"is_active": 1,
			"is_shared": 1,
			"company": None,
			"stages": [_task_row(task, index) for index, task in enumerate(seed_stages.TASKS, start=1)],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _task_row(task, index, company=None):
	return {
		"stage_code": task["code"],
		"stage_name": task["name"],
		"owner_type": task["owner_type"],
		"sla_days": task["sla_days"],
		"responsible_role": task["default_assignee_role"]
		if frappe.db.exists("Role", task["default_assignee_role"])
		else None,
		"is_mandatory": task["is_mandatory"],
		"applicability": task["applicability"],
		"applicability_threshold_kw": task["threshold_kw"],
		"task_doctype": resolve_task_doctype(task["task_doctype"]),
		"due_anchor_task": task["due_anchor_task"],
		"due_anchor_days": task["due_anchor_days"],
		"display_order": index,
		"stage_description": task["description"],
		"document_checklist_template": None,
	}


def resolve_task_doctype(wanted):
	"""The doctype a task executes in - or the generic task until that doctype ships.

	The template row links a DocType, and a Link to a doctype that is not installed yet
	refuses to save. Tasks whose dedicated document arrives in a later release run as an
	Installation Task until then; `_sync_task_rows` re-points them on the next seed.
	"""
	if frappe.db.exists("DocType", wanted):
		return wanted
	return "Installation Task"


def _sync_task_rows(doc, company=None):
	"""Add missing task rows and refresh the seed-owned fields on existing ones. Never delete."""
	by_code = {row.stage_code: row for row in doc.stages}
	changed = False
	for index, task in enumerate(seed_stages.TASKS, start=1):
		wanted = _task_row(task, index)
		row = by_code.get(task["code"])
		if not row:
			doc.append("stages", wanted)
			changed = True
			continue
		for field in SYNCED_ROW_FIELDS:
			if (row.get(field) or None) != (wanted.get(field) or None):
				row.set(field, wanted.get(field))
				changed = True
	return changed


def deactivate_legacy_templates(company):
	"""Retire the pre-task templates for a company. Returns how many were still active."""
	retired = 0
	for name in frappe.get_all(
		"Installation Stage Template",
		filters={"company": company, "template_name": ["in", list(LEGACY_TEMPLATE_NAMES)]},
		pluck="name",
	):
		active, default = frappe.db.get_value("Installation Stage Template", name, ["is_active", "is_default"])
		if active or default:
			frappe.db.set_value(
				"Installation Stage Template", name, {"is_active": 0, "is_default": 0}, update_modified=False
			)
			retired += 1
	return retired


# ------------------------------------------------------------ document templates
#: Where a template sits in the task list is the app's decision, not the site's; these
#: follow the code on every seed. The body, being editable per company, never does.
RETARGETED_TEMPLATE_FIELDS = ("stage_code", "source_doctype", "recipient")


def seed_document_templates(company):
	for spec in seed_documents.TEMPLATES:
		existing = frappe.db.get_value(
			"Solar Document Template",
			{"template_code": spec["template_code"], "company": company},
			["name", *RETARGETED_TEMPLATE_FIELDS],
			as_dict=True,
		)
		if existing:
			wanted = {
				"stage_code": spec.get("stage_code"),
				"source_doctype": spec.get("source_doctype", "Solar Installation"),
				"recipient": spec.get("recipient"),
			}
			changes = {k: v for k, v in wanted.items() if v and existing.get(k) != v}
			if changes:
				frappe.db.set_value("Solar Document Template", existing.name, changes, update_modified=False)
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
	"""Point Settings at the live defaults.

	`default_stage_template` is now read by `stages.resolve_template`, so it must never be
	left pointing at a retired template - that is the one way a new job could still be built
	on the old chain.
	"""
	settings = frappe.get_single("A3 Sola Settings")
	changed = False

	wanted = frappe.db.get_value(
		"Installation Stage Template", {"is_shared": 1, "is_active": 1}, "name"
	) or frappe.db.get_value(
		"Installation Stage Template", {"is_default": 1, "is_active": 1, "company": company}, "name"
	)
	current = settings.default_stage_template
	current_is_live = bool(current) and bool(
		frappe.db.get_value("Installation Stage Template", {"name": current, "is_active": 1}, "name")
	)
	if wanted and not current_is_live:
		settings.default_stage_template = wanted
		changed = True

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

	A checklist links a document template and a task template links a checklist. Anything
	seeded before its target existed carries a null link, and a null link means a generated
	document never files itself into the register row it satisfies.
	"""
	wanted = {
		document: code
		for _task, (_name, items) in seed_stages.checklists().items()
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
	"""Repair a company-specific task template seeded before its checklists existed.

	The shared template carries no checklist links by design (checklists are per company
	and resolved when a job is built), so this only touches a company's own variant.
	"""
	for name in frappe.get_all(
		"Installation Stage Template",
		filters={"company": company, "template_name": TASK_TEMPLATE_NAME},
		pluck="name",
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
