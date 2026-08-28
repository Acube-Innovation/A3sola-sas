# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The narrow slice of settings a tenant may change - their own, and only their own.

A3 Sola Settings is a site-wide singleton. In a multi-company deployment that means one
tenant editing it would change behaviour for every other tenant on the instance, so no
customer role can reach it at all; the isolation test asserts exactly that.

But a tenant genuinely does need to do one thing in there: map their own ledger accounts.
Provisioning deliberately leaves every account blank, and the first item on their setup
checklist is to fill them in with their accountant. This module is that surface, and it is
built so the scoping cannot be argued with:

* The company is **derived from the session**, never accepted from the caller. There is no
  parameter to tamper with.
* Every account named is checked to belong to that company before it is written. A valid
  account name from a competitor's chart is refused explicitly rather than silently
  ignored, because silently ignoring it would leave the accountant believing they had
  mapped something.
* Only the mapping row is touched. The rest of the singleton is not loaded, not returned,
  and not writable through here.
"""

import frappe
from frappe import _

from a3_sola.api.entitlements import tenant_of

SOLAR_FIELDS = (
	"subsidy_receivable_account",
	"subsidy_recovery_income_account",
	"om_provision_liability_account",
	"om_expense_account",
	"wip_account",
	"project_revenue_account",
	"material_consumption_account",
	"subcontractor_cost_account",
	"statutory_fee_receivable_account",
	"statutory_refund_receivable_account",
	"warranty_claim_receivable_account",
	"loan_advance_received_account",
	"write_off_account",
)

LABELS = {
	"subsidy_receivable_account": "Subsidy receivable",
	"subsidy_recovery_income_account": "Subsidy recovery income",
	"om_provision_liability_account": "O&M provision (liability)",
	"om_expense_account": "O&M expense",
	"wip_account": "Work in progress",
	"project_revenue_account": "Project revenue",
	"material_consumption_account": "Material consumption",
	"subcontractor_cost_account": "Subcontractor cost",
	"statutory_fee_receivable_account": "Statutory fee receivable",
	"statutory_refund_receivable_account": "Statutory refund receivable",
	"warranty_claim_receivable_account": "Warranty claim receivable",
	"loan_advance_received_account": "Loan advance received",
	"write_off_account": "Write off",
}


def _my_company():
	"""The caller's own company, derived from their tenant. Never taken as a parameter."""
	tenant_name = tenant_of()
	if not tenant_name:
		frappe.throw(
			_("This page is for workspace administrators."), frappe.PermissionError
		)
	tenant = frappe.get_cached_doc("Tenant", tenant_name)
	if frappe.session.user != tenant.admin_user:
		frappe.throw(
			_("Only the workspace administrator can change the account mapping."),
			frappe.PermissionError,
		)
	if not tenant.company:
		frappe.throw(_("This workspace has no company yet."), title=_("Not Ready"))
	return tenant, tenant.company


@frappe.whitelist()
def get_account_mapping():
	tenant, company = _my_company()
	row = frappe.db.get_value(
		"Solar Company Account Mapping",
		{"parenttype": "A3 Sola Settings", "company": company},
		["name"] + list(SOLAR_FIELDS),
		as_dict=True,
	) or {}
	return {
		"company": company,
		"tenant": tenant.tenant_name,
		"fields": [
			{"fieldname": f, "label": LABELS[f], "value": row.get(f)} for f in SOLAR_FIELDS
		],
		"complete": all(row.get(f) for f in SOLAR_FIELDS),
	}


@frappe.whitelist()
def save_account_mapping(mapping):
	"""Write the caller's own mapping row. Refuses any account outside their company."""
	tenant, company = _my_company()
	if isinstance(mapping, str):
		mapping = frappe.parse_json(mapping)
	if not isinstance(mapping, dict):
		frappe.throw(_("Nothing to save."), title=_("Bad Request"))

	values = {}
	for fieldname in SOLAR_FIELDS:
		account = (mapping.get(fieldname) or "").strip()
		if not account:
			values[fieldname] = None
			continue
		owner = frappe.db.get_value("Account", account, "company")
		if not owner:
			frappe.throw(
				_("There is no account called {0}.").format(frappe.bold(account)),
				title=_("Unknown Account"),
			)
		if owner != company:
			# Named explicitly rather than dropped, so nobody walks away thinking it saved.
			frappe.throw(
				_("{0} belongs to another company and cannot be used here.").format(
					frappe.bold(account)
				),
				title=_("Wrong Company"),
			)
		values[fieldname] = account

	row = frappe.db.get_value(
		"Solar Company Account Mapping",
		{"parenttype": "A3 Sola Settings", "company": company},
		"name",
	)
	if not row:
		frappe.throw(
			_("This workspace has no account mapping row. Contact support."),
			title=_("Not Set Up"),
		)
	frappe.db.set_value("Solar Company Account Mapping", row, values, update_modified=False)
	frappe.clear_cache(doctype="A3 Sola Settings")

	if all(values.get(f) for f in SOLAR_FIELDS):
		_complete_task(tenant.name, "ACCOUNT_MAPPING")
	frappe.flags.commit = True
	return get_account_mapping()


@frappe.whitelist()
def my_accounts(search=None):
	"""Account options for the mapping form - the caller's own company, nothing else."""
	_tenant, company = _my_company()
	filters = {"company": company, "is_group": 0}
	if search:
		filters["name"] = ["like", f"%{search}%"]
	return frappe.get_all(
		"Account", filters=filters, fields=["name", "account_type", "root_type"],
		order_by="name asc", limit_page_length=200,
	)


def _complete_task(tenant_name, task_code):
	row = frappe.db.get_value(
		"Tenant Onboarding Task",
		{"parent": tenant_name, "parenttype": "Tenant", "task_code": task_code},
		"name",
	)
	if row:
		frappe.db.set_value(
			"Tenant Onboarding Task", row,
			{"is_complete": 1, "completed_on": frappe.utils.now_datetime(),
			 "completed_by": frappe.session.user},
			update_modified=False,
		)
