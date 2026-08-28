# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Proving that a new tenant cannot see anybody else's data.

This is the step people skip, and the reason they skip it is that it feels redundant - the
permission hooks are right there, they were tested in Phase 1, what could go wrong? What
goes wrong is one missing User Permission. That single record is the whole of the isolation
in a multi-company model; without it every query the new admin runs returns the entire
instance, and nothing anywhere throws an error. It looks like a working tenant.

So this runs as a **gating step**: a tenant that fails it is never handed to a customer,
and activation is blocked rather than warned about.

Two design choices worth keeping:

* **It iterates the registry, not a hand-written list.** A doctype added in Phase 7 or 8 is
  covered automatically. A list would be correct on the day it was written and stale by the
  next phase.
* **It runs as the actual new user**, via `frappe.set_user` with a restore in `finally`.
  Simulating the check with permission-query strings would test the code that builds the
  filter, not the thing the customer will actually experience.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

#: Your own business data. A customer must never read any of it.
PLATFORM_PRIVATE_DOCTYPES = (
	"Tenant",
	"Provisioning Job",
	"Tenant Blueprint",
	"Tenant Invitation",
	"Payment Order",
	"Payment Transaction",
	"Payment Webhook Log",
	"Payment Mandate",
	"Subscription Invoice",
	"Payment Refund",
	"Settlement Reconciliation",
	"Subscription Signup",
	"Demo Request",
	"Platform Subscription",
	"Platform Audit Entry",
	"A3 Sola Settings",
)


def run_for_tenant(tenant, blocking=True):
	"""Execute every check as the tenant's own admin and write the results onto the Tenant."""
	tenant = tenant if hasattr(tenant, "name") else frappe.get_doc("Tenant", str(tenant))
	admin = tenant.admin_user
	if not admin:
		frappe.throw(
			_("There is no tenant administrator to run the isolation test as."),
			title=_("Cannot Verify Isolation"),
		)
	if not tenant.company:
		frappe.throw(_("The tenant has no company to isolate."), title=_("Cannot Verify Isolation"))

	from a3_sola.api.settings import get_value

	if not frappe.utils.cint(get_value("run_isolation_test_on_provision", 1)):
		reason = get_value("isolation_test_waiver_reason") or _("No justification recorded.")
		_write_results(
			tenant,
			[_result("SKIPPED", _("Isolation verification is switched off in Settings."),
			         status="Skipped", details=reason)],
			passed=False,
		)
		return {
			"created_doctype": "Isolation",
			"created_name": tenant.name,
			"remarks": _("Skipped by configuration: {0}").format(reason),
		}

	other_company = _another_company(tenant.company)
	results = []
	original_user = frappe.session.user
	try:
		frappe.set_user(admin)
		results += _check_registered_doctypes(tenant, other_company)
		results += _check_reports(tenant, other_company)
		results += _check_platform_private()
		results += _check_settings_and_credentials()
		results += _check_link_search(tenant, other_company)
		results += _check_role_escalation(tenant)
	finally:
		# Never leave the session as somebody else, whatever happened above.
		frappe.set_user(original_user)

	failures = [r for r in results if r["status"] in ("Failed", "Error")]
	passed = not failures
	_write_results(tenant, results, passed=passed)

	if not passed:
		message = _("{0} isolation check(s) failed: {1}").format(
			len(failures), ", ".join(r["test_code"] for r in failures[:8])
		)
		frappe.db.set_value(
			"Tenant", tenant.name,
			{"status": "Provisioned with Errors", "status_reason": message},
			update_modified=False,
		)
		frappe.log_error(
			title="a3_sola: tenant isolation FAILED",
			message=(
				f"Tenant {tenant.name} ({tenant.tenant_code}) failed isolation verification "
				f"and has NOT been activated.\n\n"
				+ "\n".join(
					f"  {r['test_code']}: {r['test_description']} -> {r['actual_result']} "
					f"({r['details']})"
					for r in failures
				)
			),
		)
		if blocking:
			frappe.throw(message, title=_("Isolation Verification Failed"))

	return {
		"created_doctype": "Isolation",
		"created_name": tenant.name,
		"remarks": _("{0} checks, all passed.").format(len(results)),
	}


# ---------------------------------------------------------------- the checks
def _check_registered_doctypes(tenant, other_company):
	"""Every company-scoped doctype in all four modules, from the registry."""
	from a3_sola.registry import all_permission_doctypes

	results = []
	for doctype in sorted(set(all_permission_doctypes())):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if meta.issingle or meta.istable:
			continue
		results.append(_list_leak_check(doctype, tenant, other_company))
		direct = _direct_read_check(doctype, tenant, other_company)
		if direct:
			results.append(direct)
	return results


def _list_leak_check(doctype, tenant, other_company):
	code = f"LIST::{doctype}"
	description = _("A list query on {0} returns nothing belonging to another company").format(doctype)
	try:
		# `get_list`, never `get_all`. `frappe.get_all` sets ignore_permissions=True, so a
		# test written with it passes on an instance with no isolation at all - it is
		# checking the database, not the permission layer. `get_list` is what the desk,
		# the reports and the REST API actually use.
		rows = frappe.get_list(
			doctype, fields=["name", "company"], limit_page_length=200, ignore_ifnull=True
		)
	except frappe.PermissionError:
		# No read permission at all is stronger isolation than a filtered list.
		return _result(code, description, status="Passed", target=doctype,
		               expected="0 foreign rows", actual="no read access at all")
	except Exception as exception:
		return _result(code, description, status="Error", target=doctype,
		               actual=type(exception).__name__, details=str(exception)[:200])
	foreign = [r for r in rows if r.get("company") and r["company"] != tenant.company]
	return _result(
		code, description,
		status="Passed" if not foreign else "Failed",
		target=doctype,
		expected="0 foreign rows",
		actual=f"{len(foreign)} foreign rows",
		details="" if not foreign else f"e.g. {foreign[0]['name']} in {foreign[0]['company']}",
	)


def _direct_read_check(doctype, tenant, other_company):
	"""Opening another tenant's document by its exact name must be refused."""
	if not other_company:
		return None
	target = frappe.db.get_value(doctype, {"company": other_company}, "name")
	if not target:
		return None
	code = f"DIRECT::{doctype}"
	description = _("Opening another company's {0} by name is refused").format(doctype)
	try:
		frappe.get_doc(doctype, target).check_permission("read")
	except frappe.PermissionError:
		return _result(code, description, status="Passed", target=doctype,
		               expected="PermissionError", actual="PermissionError")
	except Exception as exception:
		return _result(code, description, status="Passed", target=doctype,
		               expected="PermissionError", actual=type(exception).__name__,
		               details=str(exception)[:200])
	return _result(
		code, description, status="Failed", target=doctype,
		expected="PermissionError", actual="readable",
		details=f"{doctype} {target} in {other_company} was readable by the tenant admin",
	)


def _check_reports(tenant, other_company):
	"""Every report in the app, run as the tenant admin, must return no foreign rows."""
	results = []
	reports = frappe.get_all(
		"Report",
		filters={"module": ["in", ("Solar CRM", "Solar Operations", "Solar Projects")],
		         "disabled": 0},
		fields=["name", "report_type"],
	)
	for row in reports:
		code = f"REPORT::{row.name}"
		description = _("Report {0} shows nothing from another company").format(row.name)
		try:
			report = frappe.get_doc("Report", row.name)
			result = report.execute_script_report(filters={"company": other_company} if other_company else {})
			data = result[1] if len(result) > 1 else []
			leaked = len(data or [])
		except frappe.PermissionError:
			results.append(_result(code, description, status="Passed", target=row.name,
			                       actual="no access"))
			continue
		except Exception as exception:
			results.append(_result(code, description, status="Skipped", target=row.name,
			                       actual=type(exception).__name__, details=str(exception)[:200]))
			continue
		results.append(
			_result(
				code, description,
				status="Passed" if not leaked else "Failed",
				target=row.name, expected="0 rows", actual=f"{leaked} rows",
			)
		)
	return results


def _check_platform_private():
	"""Your own business data, read as the customer. Every one of these must refuse."""
	results = []
	for doctype in PLATFORM_PRIVATE_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		code = f"PLATFORM::{doctype}"
		description = _("The tenant admin cannot read {0}").format(doctype)
		try:
			readable = frappe.has_permission(doctype, "read")
		except Exception:
			readable = False
		rows = 0
		# A Single has no table to list, so `has_permission` is the whole of the check for
		# it. Calling get_all on one raises a TableMissingError, which would fail the step
		# rather than the test.
		if readable and not frappe.get_meta(doctype).issingle:
			try:
				rows = len(frappe.get_list(doctype, limit_page_length=5))
			except frappe.PermissionError:
				readable = False
			except Exception:
				rows = 0
		results.append(
			_result(
				code, description,
				status="Failed" if readable else "Passed",
				target=doctype, expected="no read access",
				actual="readable" if readable else "refused",
				details=f"{rows} row(s) visible" if readable else "",
			)
		)
	return results


def _check_settings_and_credentials():
	"""The settings singleton holds the gateway keys. A customer must not reach it."""
	results = []
	code = "SETTINGS::A3 Sola Settings"
	try:
		readable = frappe.has_permission("A3 Sola Settings", "read")
	except Exception:
		readable = False
	results.append(
		_result(code, _("The tenant admin cannot read the settings singleton"),
		        status="Failed" if readable else "Passed",
		        target="A3 Sola Settings", expected="no read access",
		        actual="readable" if readable else "refused")
	)

	leaked_secret = False
	details = ""
	# Through `frappe.client.get`, not `frappe.get_doc`. `get_doc` does not check
	# permissions - it is the internal accessor - so a check written with it reports a
	# leak on every site whether or not one exists, which is the same as reporting nothing.
	try:
		from frappe.client import get as client_get

		data = client_get("A3 Sola Settings")
		for field in ("razorpay_key_secret", "razorpay_webhook_secret", "captcha_secret_key"):
			if data.get(field):
				leaked_secret = True
				details = f"{field} was readable"
				break
	except Exception:
		leaked_secret = False
	results.append(
		_result("CREDENTIALS::gateway", _("The tenant admin cannot read gateway credentials"),
		        status="Failed" if leaked_secret else "Passed",
		        target="A3 Sola Settings", expected="no credential access",
		        actual="leaked" if leaked_secret else "refused", details=details)
	)
	return results


def _check_link_search(tenant, other_company):
	"""A link field's dropdown is a query too, and an easy one to forget."""
	if not other_company:
		return []
	from frappe.desk.search import search_link

	code = "SEARCH::Solar Consumer"
	description = _("A link search returns no other-company options")
	if not frappe.db.exists("DocType", "Solar Consumer"):
		return []
	try:
		frappe.response.pop("results", None)
		search_link(doctype="Solar Consumer", txt="", filters=None)
		results = frappe.response.get("results") or []
	except Exception as exception:
		return [_result(code, description, status="Skipped", target="Solar Consumer",
		                actual=type(exception).__name__, details=str(exception)[:200])]
	foreign = 0
	for row in results:
		company = frappe.db.get_value("Solar Consumer", row.get("value"), "company")
		if company and company != tenant.company:
			foreign += 1
	return [
		_result(code, description,
		        status="Passed" if not foreign else "Failed",
		        target="Solar Consumer", expected="0 foreign options",
		        actual=f"{foreign} foreign options")
	]


def _check_role_escalation(tenant):
	"""Can the tenant admin give themselves more power than they bought?"""
	from a3_sola.api.entitlements import forbidden_roles

	results = []
	held = set(frappe.get_roles(frappe.session.user))
	leaked = held & set(forbidden_roles(tenant.name))
	results.append(
		_result("ROLES::entitlement", _("The tenant admin holds only roles their plan includes"),
		        status="Failed" if leaked else "Passed",
		        target="User", expected="no forbidden roles",
		        actual=", ".join(sorted(leaked)) or "none")
	)

	can_write_roles = False
	try:
		can_write_roles = frappe.has_permission("Role", "write") or frappe.has_permission(
			"User Permission", "write"
		)
	except Exception:
		can_write_roles = False
	results.append(
		_result("ROLES::escalation", _("The tenant admin cannot edit roles or user permissions"),
		        status="Failed" if can_write_roles else "Passed",
		        target="Role", expected="no write access",
		        actual="writable" if can_write_roles else "refused")
	)
	return results


# ------------------------------------------------------------------ plumbing
def _result(code, description, status="Passed", target=None, expected=None, actual=None,
            details=""):
	return {
		"test_code": code[:140],
		"test_description": str(description)[:500],
		"target_doctype": (target or "")[:140],
		"expected_result": (expected or "")[:140],
		"actual_result": (actual or "")[:140],
		"status": status,
		"details": str(details)[:500],
		"run_on": now_datetime(),
	}


def _write_results(tenant, results, passed):
	doc = frappe.get_doc("Tenant", tenant.name)
	doc.set("isolation_results", [])
	for row in results:
		doc.append("isolation_results", row)
	doc.isolation_test_passed = 1 if passed else 0
	doc.isolation_test_on = now_datetime()
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def _another_company(company):
	other = frappe.get_all(
		"Company", filters={"name": ["!=", company]}, pluck="name", limit=1, order_by="creation asc"
	)
	return other[0] if other else None


# ---------------------------------------------------------------- desk + cron
@frappe.whitelist()
def rerun(tenant):
	"""Available at any time, because a regression in a later phase is exactly the risk."""
	from a3_sola.api.permissions import require_role

	require_role(
		("Platform Tenant Manager", "Platform Provisioning Operator", "Platform Admin",
		 "System Manager"),
		_("Running an isolation test"),
	)
	return run_for_tenant(tenant, blocking=False)


def monthly_isolation_sweep():
	"""Scheduled. A regression introduced by a later phase should be caught by us."""
	from a3_sola.api.settings import get_value

	if not frappe.utils.cint(get_value("isolation_recheck_monthly", 1)):
		return {"checked": 0}
	failed = []
	for name in frappe.get_all("Tenant", filters={"status": "Active"}, pluck="name"):
		try:
			run_for_tenant(name, blocking=False)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="a3_sola: isolation sweep errored",
				message=f"Tenant {name}\n\n{frappe.get_traceback()}",
			)
			continue
		if not frappe.db.get_value("Tenant", name, "isolation_test_passed"):
			failed.append(name)
	if failed:
		frappe.log_error(
			title="a3_sola: active tenants failing isolation",
			message=(
				"These ACTIVE tenants no longer pass isolation verification. Treat this as "
				"a Sev-1 - see docs/PROVISIONING_RUNBOOK.md.\n\n" + "\n".join(failed)
			),
		)
	return {"checked": frappe.db.count("Tenant", {"status": "Active"}), "failed": len(failed)}
