# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Undoing what a provisioning test committed.

Provisioning commits after every step so that a crash leaves an accurate record of where
it stopped. The consequence for tests is that nothing they create is rolled back: each one
leaves a Company with a full chart of accounts and roughly a hundred seeded masters behind
forever.

So the tests undo it themselves. This is the only place in the codebase that removes a
provisioned company, it exists solely for the suite, and it still refuses on anything with
real transactions - if a test somehow produced a company with a ledger entry, that is worth
a human looking at rather than a silent delete.

It is deliberately tolerant of failure. A leftover record is untidy; a teardown that raises
turns a passing test into a failing one and tells you nothing useful.
"""

import frappe

#: Doctypes seeded per company, in reverse dependency order. Anything not listed is left
#: alone - the point is to keep the database from growing without bound, not to be exhaustive.
COMPANY_SCOPED = (
	"Solar Package",
	"Billing Milestone Template",
	"Solar GST Valuation Rule",
	"Installation Stage Template",
	"Document Template Set",
	"Document Checklist Template",
	"Solar Document Template",
	"Outreach Message Template",
	"Grid Regulation Rule",
	"Statutory Fee Schedule",
	"Electricity Tariff",
	"Subsidy Scheme",
	"Component Make",
	"Roof Type",
	"DISCOM Section",
	"DISCOM",
	"Warehouse",
	"Cost Center",
)


def purge_tenants(tenant_names):
	"""Remove the tenants a test class created, and everything provisioning gave them."""
	for tenant in list(tenant_names or []):
		try:
			_purge_one(tenant)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.logger("a3_sola").info(
				{"event": "test_teardown_incomplete", "tenant": tenant}
			)


def _purge_one(tenant_name):
	if not frappe.db.exists("Tenant", tenant_name):
		return
	tenant = frappe.get_doc("Tenant", tenant_name)
	company = tenant.company

	for email in frappe.get_all("User", filters={"a3_sola_tenant": tenant_name}, pluck="name"):
		if email == "Administrator":
			continue
		frappe.db.delete("User Permission", {"user": email})
		frappe.db.delete("DefaultValue", {"parent": email})
		_delete("User", email)

	frappe.db.delete("Tenant Invitation", {"tenant": tenant_name})
	for job in frappe.get_all("Provisioning Job", filters={"tenant": tenant_name}, pluck="name"):
		frappe.db.set_value("Provisioning Job", job, "docstatus", 2, update_modified=False)
		_delete("Provisioning Job", job)

	frappe.db.set_value(
		"Tenant", tenant_name, {"docstatus": 2, "company": None}, update_modified=False
	)
	_delete("Tenant", tenant_name)

	# Only a company this tenant actually owns. The stamp is written by step 05 and by
	# nothing else, so it is the one trustworthy statement that provisioning built this
	# company. Trusting `tenant.company` instead is how a teardown deletes the shared demo
	# company that a stray field default put there - which is not hypothetical.
	if company:
		purge_company(company, expect_tenant=tenant_name)


#: A company is only ever removed by this module if its NAME says a test made it.
#:
#: The provisioning stamp is not enough on its own, and that is the lesson from a sweep
#: that deleted a legitimate company: anything which links a tenant to a real company -
#: a starter dataset, a manual fix, a support action - puts a stamp on it, and a rule that
#: trusts the stamp will then take the company with the tenant. The name is the only
#: property that is under this suite's control and nobody else's.
TEST_COMPANY_PREFIXES = ("Test EPC", "Diag EPC", "Collide EPC", "Sunrise Energy Systems")


def looks_like_a_test_company(company):
	return (company or "").startswith(TEST_COMPANY_PREFIXES)


def purge_company(company, expect_tenant=None):
	"""Remove a test company and the masters seeded into it.

	Three refusals, and every one of them exists because the absence of it caused damage:
	a company with real transactions, a company whose name is not obviously a test
	fixture's, and a company stamped for a different tenant than the one being purged.
	"""
	if not frappe.db.exists("Company", company):
		return
	if not looks_like_a_test_company(company):
		frappe.logger("a3_sola").info(
			{"event": "test_teardown_refused", "company": company,
			 "reason": "the name is not one this suite creates"}
		)
		return
	stamp = frappe.db.get_value("Company", company, "a3_sola_tenant")
	if expect_tenant and stamp and stamp != expect_tenant:
		return
	for doctype in ("GL Entry", "Sales Invoice", "Purchase Invoice", "Stock Ledger Entry"):
		if frappe.db.exists("DocType", doctype) and frappe.db.exists(doctype, {"company": company}):
			# Not a test artefact any more. Leave it and say so.
			frappe.logger("a3_sola").info(
				{"event": "test_teardown_refused", "company": company, "reason": doctype}
			)
			return

	for fieldname in ("solar_account_mapping", "payment_account_mapping"):
		for child in ("Solar Company Account Mapping", "Platform Payment Account Mapping"):
			if frappe.db.table_exists(child):
				frappe.db.delete(child, {"parenttype": "A3 Sola Settings",
				                         "parentfield": fieldname, "company": company})

	for doctype in COMPANY_SCOPED:
		if not frappe.db.exists("DocType", doctype):
			continue
		for name in frappe.get_all(doctype, filters={"company": company}, pluck="name"):
			_delete(doctype, name)

	frappe.db.delete("User Permission", {"allow": "Company", "for_value": company})

	# ERPNext's Company.on_trash is what removes the chart of accounts, and `_delete`
	# deliberately skips on_trash so a half-built master cannot block the sweep. So the
	# accounts have to go explicitly, deepest first - a parent account refuses to go while
	# it still has children. Skipping this is how a site ends up with twenty-five thousand
	# orphaned accounts and a Company insert that takes three seconds.
	_delete_company_accounts(company)
	frappe.db.delete("Party Account", {"company": company})
	frappe.db.delete("Mode of Payment Account", {"company": company})
	_delete("Company", company)


def _delete_company_accounts(company):
	"""Delete a company's accounts leaf-first, so no parent blocks on its children."""
	rows = frappe.get_all(
		"Account", filters={"company": company}, fields=["name", "lft", "rgt"],
		order_by="lft desc",
	)
	for row in rows:
		frappe.db.delete("Account", {"name": row.name})
	frappe.db.delete("Account", {"company": company})


def _delete(doctype, name):
	try:
		frappe.delete_doc(
			doctype, name, force=True, ignore_permissions=True,
			ignore_on_trash=True, delete_permanently=True,
		)
	except Exception:
		frappe.db.rollback()


def purge_all_test_residue():
	"""Sweep a development site clean of everything the provisioning suite has left behind.

	Run it by hand when a dev site has become slow:
	    bench --site <site> execute \\
	        a3_sola.tests.platform.provisioning_cleanup.purge_all_test_residue
	"""
	# Only names this suite generates. `%epc.example%` used to be here and was too broad -
	# it is an address fragment, and address fragments turn up in data nobody meant to
	# match.
	patterns = ("Test EPC %", "Diag EPC %", "Sunrise Energy Systems%", "Collide EPC %",
	            "M/s S%ya Energy%")
	names = set()
	for pattern in patterns:
		names.update(frappe.get_all("Tenant", filters={"tenant_name": ["like", pattern]},
		                            pluck="name"))
	names.update(
		frappe.get_all(
			"Tenant", filters={"primary_contact_email": ["like", "%@epc.example"]}, pluck="name"
		)
	)
	purge_tenants(sorted(names))

	# Companies whose tenant is already gone - residue from an earlier run that predates
	# this cleanup existing at all.
	orphans = []
	for company in frappe.get_all(
		"Company", filters={"a3_sola_tenant": ["is", "set"]}, fields=["name", "a3_sola_tenant"]
	):
		if not looks_like_a_test_company(company.name):
			continue
		if not frappe.db.exists("Tenant", company.a3_sola_tenant):
			orphans.append(company.name)
	for company in orphans:
		try:
			purge_company(company)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()

	# Companies created directly by a fixture rather than by provisioning - the
	# abbreviation-collision test makes one every time it runs.
	direct = set()
	for pattern in ("Collide EPC %", "Test EPC %", "Diag EPC %"):
		direct.update(frappe.get_all("Company", filters={"name": ["like", pattern]}, pluck="name"))
	for company in sorted(direct):
		try:
			purge_company(company)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()

	# Jobs whose tenant is gone, and any account left behind by an earlier sweep that ran
	# before this function knew to remove them.
	stranded_jobs = 0
	for job in frappe.get_all(
		"Provisioning Job", fields=["name", "tenant"], limit_page_length=0
	):
		if job.tenant and not frappe.db.exists("Tenant", job.tenant):
			frappe.db.set_value("Provisioning Job", job.name, "docstatus", 2,
			                    update_modified=False)
			_delete("Provisioning Job", job.name)
			stranded_jobs += 1
	orphan_accounts = frappe.db.sql(
		"""DELETE a FROM `tabAccount` a
		   LEFT JOIN `tabCompany` c ON c.name = a.company
		   WHERE a.company IS NOT NULL AND a.company != '' AND c.name IS NULL"""
	)
	del orphan_accounts

	frappe.db.commit()
	return {
		"tenants_purged": len(names),
		"orphan_companies_purged": len(orphans),
		"fixture_companies_purged": len(direct),
		"stranded_jobs_purged": stranded_jobs,
		"companies_remaining": frappe.db.count("Company"),
		"accounts_remaining": frappe.db.count("Account"),
	}
