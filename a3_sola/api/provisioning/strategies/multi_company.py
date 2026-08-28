# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The default tenancy model: one Company per tenant, one site for everyone.

Isolation here is enforced rather than structural - a User Permission on Company plus the
permission hooks from Phases 1 to 5. That works, and it is what step 12 exists to prove
before any customer is handed the keys.

Two things in this file deserve their comments read rather than skimmed:

* **Nothing the applicant typed becomes an account name.** The company name is sanitised
  for display; the abbreviation - which ERPNext appends to every single account, warehouse
  and cost centre it creates - is derived from the tenant code, which was itself derived by
  an allowlist. A stray slash or quote in an organisation name would otherwise surface as a
  broken account eight steps later, in the middle of seeding, where it is hardest to read.

* **Rollback refuses rather than forces.** Deleting a Company that has transactions is not
  something ERPNext can do cleanly, so `teardown` checks first and raises if there is
  anything attached. An automated cleanup that guesses wrong here deletes real money.
"""

import frappe
from frappe import _
from frappe.utils import cint

from a3_sola.api.provisioning import blueprint as blueprint_api
from a3_sola.api.provisioning import identifiers
from a3_sola.api.provisioning.strategies import TenancyStrategy
from a3_sola.api.settings import get_value

#: Cost centres a solar EPC actually reports on. Not a generic list.
COST_CENTRES = ("Sales", "Projects", "Service", "Administration")

#: Warehouses the Phase 2 material flow expects to exist on day one.
WAREHOUSES = (
	("Main Store", 0),
	("Site Store", 1),  # group: one child warehouse per site is created per installation
	("Service Van Stock", 0),
	("Scrap Store", 0),
)

ITEM_GROUPS = (
	"Solar Packages", "Modules", "Inverters", "Mounting Structures",
	"Cables and BOS", "Meters", "Solar Consumables", "Solar Services",
)

UOMS = ("kW", "kWp", "kWh", "Nos", "Metre", "Set")


class MultiCompanyStrategy(TenancyStrategy):
	name = "Multi Company"

	# ------------------------------------------------------------------ step 05
	def create_company(self, context):
		tenant = context.tenant
		# Reuse only a company that carries THIS tenant's stamp. A company name sitting in
		# the field for any other reason - a stray default, a half-finished earlier run, a
		# hand edit - must not be adopted, because adopting one means seeding a customer's
		# masters into somebody else's ledger and confining their admin to it.
		if tenant.company and frappe.db.get_value("Company", tenant.company, "a3_sola_tenant") == tenant.name:
			context.company = tenant.company
			return {"created_doctype": "Company", "created_name": tenant.company,
			        "remarks": "already existed"}
		if tenant.company:
			tenant.db_set("company", None, update_modified=False)
			context.reload_tenant()
			tenant = context.tenant

		abbr = identifiers.free_abbreviation(tenant.tenant_code)
		company_name = _free_company_name(tenant.tenant_name)

		company = frappe.new_doc("Company")
		company.update(
			{
				"company_name": company_name,
				"abbr": abbr,
				"country": tenant.country or get_value("provisioning_default_country") or "India",
				"default_currency": get_value("provisioning_default_currency") or "INR",
				"chart_of_accounts": get_value("default_chart_of_accounts") or "Standard",
				"create_chart_of_accounts_based_on": "Standard Template",
				"company_description": _("Provisioned workspace for tenant {0}.").format(
					tenant.tenant_code
				),
			}
		)
		if tenant.gstin:
			company.tax_id = tenant.gstin
		company.flags.ignore_permissions = True
		company.flags.ignore_mandatory = True
		company.insert(ignore_permissions=True)

		frappe.db.set_value("Company", company.name, "a3_sola_tenant", tenant.name,
		                    update_modified=False)
		tenant.db_set("company", company.name, update_modified=False)
		context.company = company.name
		context.reload_tenant()
		context.record("05_CREATE_COMPANY", "Company", company.name)
		return {"created_doctype": "Company", "created_name": company.name}

	def rollback_company(self, context, step_log):
		name = step_log.created_name
		if not name or not frappe.db.exists("Company", name):
			return
		_refuse_if_company_has_data(name)
		# `force=False`, deliberately. Frappe's own link checks stay switched on, so a
		# company that has picked up any dependant at all refuses to go rather than being
		# torn out from under it. The only company this ever removes is one created
		# seconds earlier that nothing has touched.
		frappe.delete_doc("Company", name, force=False, ignore_permissions=True)
		if context.tenant:
			frappe.db.set_value("Tenant", context.tenant.name, "company", None,
			                    update_modified=False)
			context.reload_tenant()
		context.company = None

	# ------------------------------------------------------------------ step 06
	def create_structures(self, context):
		company = context.company or context.tenant.company
		if not company:
			frappe.throw(_("There is no company to build structures in."))
		abbr = frappe.db.get_value("Company", company, "abbr")
		created = []

		if cint(get_value("create_default_cost_centers", 1)):
			created += _cost_centres(company, abbr)
		if cint(get_value("create_default_warehouses", 1)):
			created += _warehouses(company, abbr)
		created += _item_groups()
		created += _uoms()
		created += _commercial_groups(context)
		created += _price_lists(context)

		for doctype, name in created:
			context.record("06_CREATE_STRUCTURES", doctype, name)
		return {
			"created_doctype": "Structures",
			"created_name": f"{len(created)} records",
			"remarks": _("{0} structural records created in {1}.").format(len(created), company),
		}

	def rollback_structures(self, context, step_log):
		"""Delete what step 06 created, newest first, and skip anything now depended on."""
		for artefact in reversed(context.created("06_CREATE_STRUCTURES")):
			_delete_if_unused(artefact["doctype"], artefact["name"])

	# ------------------------------------------------------------------ step 07
	def seed_masters(self, context):
		"""The step where the product value lands.

		The heavy lifting is the same `setup.install.seed_masters` that seeds the first
		company at install time. Reusing it is deliberate: a tenant provisioned in
		production must get exactly what a developer's site gets, and two code paths that
		are supposed to produce the same masters will diverge within a month.
		"""
		from a3_sola.setup import install

		company = context.company or context.tenant.company
		seeded = install.seed_masters(company)
		blueprint_created = _run_blueprint(context, company)
		missing = _verify_essential_masters(company) + _verify_blueprint_completeness(context, company)
		if missing:
			frappe.throw(
				_("Seeding did not produce everything this tenant needs. Missing: {0}").format(
					", ".join(missing)
				),
				title=_("Incomplete Seeding"),
			)
		_scaffold_account_mappings(company)
		_write_back_operations_defaults(context, company)
		return {
			"created_doctype": "Masters",
			"created_name": company,
			"remarks": _("Module masters seeded; {0} blueprint record(s) created.").format(
				len(blueprint_created)
			),
		}

	def rollback_masters(self, context, step_log):
		company = context.company or (context.tenant.company if context.tenant else None)
		for artefact in reversed(context.created("07_SEED_MASTERS")):
			_delete_if_unused(artefact["doctype"], artefact["name"])
		if company:
			_remove_account_mappings(company)

	# ------------------------------------------------------------------ step 09
	def create_admin(self, context):
		from a3_sola.api import tenant_users

		return tenant_users.create_admin_user(context)

	# ------------------------------------------------------------------ step 12
	def verify_isolation(self, context):
		from a3_sola.api import isolation

		return isolation.run_for_tenant(context.tenant, blocking=True)

	# ------------------------------------------------------------------ teardown
	def teardown(self, context):
		"""The reversible unwind, and a refusal on anything that has started trading."""
		company = context.company or (context.tenant.company if context.tenant else None)
		if company:
			_refuse_if_company_has_data(company)
		self.rollback_masters(context, None)
		self.rollback_structures(context, None)
		if company and frappe.db.exists("Company", company):
			frappe.delete_doc("Company", company, force=False, ignore_permissions=True)
		return {"torn_down": company}


# --------------------------------------------------------------------- company
def _free_company_name(tenant_name):
	"""ERPNext company names are unique site-wide. Two customers may share a trading name."""
	base = identifiers.sanitise_name(tenant_name, 100) or "Tenant"
	# Characters ERPNext's account naming cannot carry. Replaced rather than dropped, so
	# "M/s Sunrise" stays readable as "M-s Sunrise" instead of becoming "Ms Sunrise".
	for bad in ("/", "\\", "\n", "\r", "\t", '"', "'", "`", "<", ">", "%", ";"):
		base = base.replace(bad, "-")
	base = " ".join(base.split())[:100].strip(" -") or "Tenant"
	candidate = base
	suffix = 1
	while frappe.db.exists("Company", candidate):
		suffix += 1
		tail = f" ({suffix})"
		candidate = f"{base[: 100 - len(tail)]}{tail}"
		if suffix > 999:
			frappe.throw(_("Could not derive a free company name from {0}.").format(tenant_name))
	return candidate


def _refuse_if_company_has_data(company):
	"""Never delete a company that has started trading. Never force it either."""
	for doctype in ("GL Entry", "Sales Invoice", "Purchase Invoice", "Journal Entry",
	                "Stock Ledger Entry", "Payment Entry"):
		if not frappe.db.exists("DocType", doctype):
			continue
		if frappe.db.exists(doctype, {"company": company}):
			frappe.throw(
				_("Company {0} has {1} records and will not be deleted. Provisioning "
				  "rollback never removes a company that has started trading - clean this "
				  "up by hand, deliberately.").format(frappe.bold(company), _(doctype)),
				title=_("Company Has Data"),
			)


# ------------------------------------------------------------------ structures
def _insert(doc, unique_filters=None, tolerate_duplicate=False):
	if unique_filters and frappe.db.exists(doc["doctype"], unique_filters):
		return None
	document = frappe.get_doc(doc)
	document.flags.ignore_permissions = True
	document.flags.ignore_mandatory = True
	try:
		document.insert(ignore_permissions=True, ignore_if_duplicate=tolerate_duplicate)
	except frappe.DuplicateEntryError:
		if not tolerate_duplicate:
			raise
		# Something else already holds that name. For a skip-if-exists seed item that is
		# the desired outcome, not a failure.
		frappe.db.rollback(save_point="seed_item")
		return None
	return document.name


def _cost_centres(company, abbr):
	created = []
	root = frappe.db.get_value("Cost Center", {"company": company, "is_group": 1}, "name")
	if not root:
		root = _insert({"doctype": "Cost Center", "cost_center_name": company,
		                "company": company, "is_group": 1})
		if root:
			created.append(("Cost Center", root))
	for label in COST_CENTRES:
		name = _insert(
			{"doctype": "Cost Center", "cost_center_name": label, "company": company,
			 "parent_cost_center": root, "is_group": 0},
			{"cost_center_name": label, "company": company},
		)
		if name:
			created.append(("Cost Center", name))
	main = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
	if main:
		frappe.db.set_value("Company", company,
		                    {"cost_center": main, "round_off_cost_center": main},
		                    update_modified=False)
	return created


def _warehouses(company, abbr):
	created = []
	root = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name")
	if not root:
		root = _insert({"doctype": "Warehouse", "warehouse_name": "All Warehouses",
		                "company": company, "is_group": 1})
		if root:
			created.append(("Warehouse", root))
	for label, is_group in WAREHOUSES:
		name = _insert(
			{"doctype": "Warehouse", "warehouse_name": label, "company": company,
			 "parent_warehouse": root, "is_group": is_group},
			{"warehouse_name": label, "company": company},
		)
		if name:
			created.append(("Warehouse", name))
	return created


def _item_groups():
	created = []
	root = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ""}, "name") \
		or "All Item Groups"
	for label in ITEM_GROUPS:
		name = _insert(
			{"doctype": "Item Group", "item_group_name": label, "parent_item_group": root,
			 "is_group": 0},
			{"item_group_name": label},
		)
		if name:
			created.append(("Item Group", name))
	return created


def _uoms():
	created = []
	for label in UOMS:
		name = _insert({"doctype": "UOM", "uom_name": label}, {"uom_name": label})
		if name:
			created.append(("UOM", name))
	return created


def _commercial_groups(context):
	created = []
	tenant = context.tenant
	root_customer = frappe.db.get_value("Customer Group", {"is_group": 1}, "name")
	for label in ("Residential Solar", "Commercial Solar"):
		name = _insert(
			{"doctype": "Customer Group", "customer_group_name": label,
			 "parent_customer_group": root_customer, "is_group": 0},
			{"customer_group_name": label},
		)
		if name:
			created.append(("Customer Group", name))

	root_supplier = frappe.db.get_value("Supplier Group", {"is_group": 1}, "name")
	for label in ("Solar Equipment", "Solar Services"):
		name = _insert(
			{"doctype": "Supplier Group", "supplier_group_name": label,
			 "parent_supplier_group": root_supplier, "is_group": 0},
			{"supplier_group_name": label},
		)
		if name:
			created.append(("Supplier Group", name))

	if tenant.state:
		root_territory = frappe.db.get_value("Territory", {"is_group": 1, "parent_territory": ""},
		                                     "name") or "All Territories"
		name = _insert(
			{"doctype": "Territory", "territory_name": identifiers.sanitise_name(tenant.state, 60),
			 "parent_territory": root_territory, "is_group": 0},
			{"territory_name": tenant.state},
		)
		if name:
			created.append(("Territory", name))
	return created


def _price_lists(context):
	created = []
	currency = get_value("provisioning_default_currency") or "INR"
	for label, selling, buying in (("Standard Selling", 1, 0), ("Standard Buying", 0, 1)):
		name = _insert(
			{"doctype": "Price List", "price_list_name": label, "currency": currency,
			 "enabled": 1, "selling": selling, "buying": buying},
			{"price_list_name": label},
		)
		if name:
			created.append(("Price List", name))
	return created


def _delete_if_unused(doctype, name):
	"""Delete a rollback artefact, and step over anything that has acquired dependants."""
	if doctype in ("Structures", "Masters", "Tenant Code", "Tenant Blueprint"):
		return
	if not frappe.db.exists(doctype, name):
		return
	try:
		frappe.delete_doc(doctype, name, force=False, ignore_permissions=True)
	except Exception:
		# Something links to it now. Leaving it is correct: a shared master with a
		# dependant is not this tenant's to remove.
		frappe.db.rollback()
		frappe.logger("a3_sola").info(
			{"event": "rollback_skipped", "doctype": doctype, "name": name}
		)


# --------------------------------------------------------------------- masters
def _run_blueprint(context, company):
	"""Execute the blueprint's seed items, in sequence, against the new company."""
	if not context.blueprint:
		return []
	blueprint = frappe.get_doc("Tenant Blueprint", context.blueprint)
	tokens = context.token_context()
	created = []
	for item in sorted(blueprint.seed_items, key=lambda r: cint(r.sequence) or r.idx):
		if not item.target_doctype:
			continue
		for record in blueprint_api.payload_records(item, tokens):
			record.setdefault("doctype", item.target_doctype)
			if frappe.get_meta(item.target_doctype).has_field("company"):
				record["company"] = company
			skip = cint(item.skip_if_exists)
			filters = _identity_filters(item.target_doctype, record, company)
			if skip and filters and frappe.db.exists(item.target_doctype, filters):
				continue
			frappe.db.savepoint("seed_item")
			name = _insert(record, tolerate_duplicate=bool(skip))
			if name:
				created.append((item.target_doctype, name))
				context.record("07_SEED_MASTERS", item.target_doctype, name)
	return created


def _identity_filters(doctype, record, company):
	"""What makes this record the same record - used for skip_if_exists.

	Three ways a Frappe doctype can be identified, tried in order of how specific they
	are: an explicit name in the payload, the field the doctype is named by, and its title
	field. Falling through all three returns None, and the caller then relies on the
	database's own uniqueness rather than guessing.
	"""
	meta = frappe.get_meta(doctype)
	if record.get("name"):
		return {"name": record["name"]}

	autoname = (meta.autoname or "")
	if autoname.startswith("field:"):
		fieldname = autoname.split(":", 1)[1]
		if record.get(fieldname):
			return {fieldname: record[fieldname]}

	filters = {}
	for candidate in (meta.get_title_field(), "title"):
		if candidate and record.get(candidate) and meta.has_field(candidate):
			filters[candidate] = record[candidate]
			break
	if not filters:
		return None
	if meta.has_field("company"):
		filters["company"] = company
	return filters


#: What a tenant cannot function without, and what breaks for them if it is absent. The
#: verification pass exists because seeding "succeeded" is not the same as seeding worked -
#: a company-blind existence check reports success while producing nothing.
ESSENTIAL_MASTERS = (
	("DISCOM", "no distribution company, so no portal application"),
	("Roof Type", "no roof types, so a site survey cannot be completed"),
	("Subsidy Scheme", "no scheme, so no eligibility check and no subsidy"),
	("Electricity Tariff", "no tariff, so every savings figure is zero"),
	("Solar Package", "no packages, so there is nothing to quote"),
	("Component Make", "no makes, so no warranty terms"),
	("Installation Stage Template", "no stage chain, so no installation can start"),
	("Document Checklist Template", "no checklists, so no document pack"),
	("Billing Milestone Template", "no milestones, so nothing can be invoiced"),
)


def _verify_essential_masters(company):
	"""Fail the step rather than hand over a tenant that cannot do its own job.

	Every entry here corresponds to something the tenant would discover was missing at the
	worst moment - mid-survey, mid-installation, or at their first invoice.
	"""
	missing = []
	for doctype, consequence in ESSENTIAL_MASTERS:
		if not frappe.db.exists("DocType", doctype):
			continue
		if not frappe.db.exists(doctype, {"company": company}):
			missing.append(f"{doctype} ({consequence})")
	return missing


def _verify_blueprint_completeness(context, company):
	"""Every mandatory blueprint item must have produced something. Say which did not.

	A tenant missing its stage templates is a tenant whose Phase 2 does not function, and
	they will find that out on their first installation rather than here.
	"""
	if not context.blueprint:
		return []
	missing = []
	for item in blueprint_api.mandatory_items(context.blueprint):
		if not item.target_doctype:
			continue
		filters = {"company": company} if frappe.get_meta(item.target_doctype).has_field("company") else {}
		if not frappe.db.exists(item.target_doctype, filters or None):
			missing.append(f"{item.target_doctype} (item {item.idx})")
	return missing


def _scaffold_account_mappings(company):
	"""Create the mapping rows EMPTY, and deliberately so.

	A guessed account mapping posts money to the wrong ledger and nobody notices until a
	reconciliation. An empty one blocks postings - which are off by default anyway - and
	puts the decision in front of the tenant's own accountant, where it belongs.
	"""
	from a3_sola.solar_crm.doctype.a3_sola_settings.a3_sola_settings import (
		repair_orphan_company_rows,
	)

	repair_orphan_company_rows()
	settings = frappe.get_single("A3 Sola Settings")
	changed = False
	if not any(row.company == company for row in settings.solar_account_mapping):
		settings.append("solar_account_mapping", {"company": company})
		changed = True
	if settings.meta.has_field("payment_account_mapping") and not any(
		row.company == company for row in settings.payment_account_mapping
	):
		settings.append("payment_account_mapping", {"company": company})
		changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)


def _remove_account_mappings(company):
	"""Take the scaffolded mapping rows back out again.

	Leaving them behind would point the settings singleton at a company that is about to
	stop existing, and the next save of settings - by anybody, for any reason - would fail
	link validation.
	"""
	for child_doctype, fieldname in (
		("Solar Company Account Mapping", "solar_account_mapping"),
		("Platform Payment Account Mapping", "payment_account_mapping"),
	):
		if not frappe.db.table_exists(child_doctype):
			continue
		frappe.db.delete(
			child_doctype,
			{"parenttype": "A3 Sola Settings", "parentfield": fieldname, "company": company},
		)


def _write_back_operations_defaults(context, company):
	"""Point the Phase 2 material flow at the warehouses this tenant just got.

	Without this the first work order fails on a missing warehouse, and the tenant's first
	experience of the product is a support call about a field they have never heard of.
	"""
	settings = frappe.get_single("A3 Sola Settings")
	changed = False
	main = frappe.db.get_value("Warehouse", {"warehouse_name": "Main Store", "company": company}, "name")
	site_group = frappe.db.get_value("Warehouse", {"warehouse_name": "Site Store", "company": company}, "name")
	if main and not settings.default_source_warehouse:
		settings.default_source_warehouse = main
		changed = True
	if site_group and not settings.site_warehouse_group:
		settings.site_warehouse_group = site_group
		changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
	context.note(
		f"Warehouses for {company}: main={main or 'none'}, site group={site_group or 'none'}."
	)
