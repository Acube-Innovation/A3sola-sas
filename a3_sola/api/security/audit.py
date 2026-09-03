# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Running every attack vector against every tenant, and reporting the evidence.

The output is deliberately two things: a machine-readable artefact so a later run can be
diffed against this one, and a human summary that says how many attempts were made and how
many succeeded. A number of successes other than zero is a Blocker, and this reports it as
one rather than as a warning.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from a3_sola.api.security import attacks
from a3_sola.api.security.attacks import BLOCKED, LEAKED, SKIPPED


def run_attack_suite(actor, own_company, foreign_company, own_tenant=None,
                     foreign_tenant=None, read_only=True, doctype_limit=None):
	"""Every vector, as `actor`, against `foreign_company`. Returns a list of Attempt.

	`read_only` skips the two vectors that would write - used by the production audit,
	where proving a write is refused is not worth the risk of proving it is not.
	"""
	original = frappe.session.user
	attempts = []
	try:
		frappe.set_user(actor)

		scoped = attacks.company_scoped_doctypes()
		if doctype_limit:
			scoped = scoped[:doctype_limit]
		names_by_doctype = {
			doctype: attacks.foreign_records(doctype, foreign_company) for doctype in scoped
		}

		for doctype in scoped:
			foreign_names = names_by_doctype[doctype]
			attempts.append(attacks.v01_list_view(actor, doctype, foreign_company, foreign_names))
			attempts.append(attacks.v02_direct_get(actor, doctype, foreign_company, foreign_names))
			attempts.extend(attacks.v03_client_api(actor, doctype, foreign_company, foreign_names))
			attempts.extend(attacks.v05_link_search(actor, doctype, foreign_company, foreign_names))
			attempts.append(attacks.v06_print_and_pdf(actor, doctype, foreign_company, foreign_names))
			attempts.append(attacks.v08_export(actor, doctype, foreign_company, foreign_names))
			attempts.extend(attacks.v12_timeline(actor, doctype, foreign_company, foreign_names))
			if not read_only:
				attempts.extend(
					attacks.v09_bulk_endpoints(actor, doctype, foreign_company, foreign_names))

		# Your own business records, which no customer may read at all.
		for doctype in attacks.platform_private_doctypes():
			attempts.append(_platform_private_check(doctype))

		for report in _reports():
			attempts.extend(attacks.v04_reports(actor, report, foreign_company, own_company))

		attempts.extend(attacks.v07_private_files(actor, foreign_company, names_by_doctype))
		attempts.extend(attacks.v10_dashboard_aggregates(actor, foreign_company, own_company))

		needle = _distinctive_string(foreign_company, names_by_doctype)
		if needle:
			attempts.append(attacks.v11_global_search(actor, needle, foreign_company))

		attempts.extend(attacks.v13_portals(
			actor,
			_foreign_subscription(foreign_tenant),
			(names_by_doctype.get("Project") or [None])[0],
		))

		foreign_name = _any_foreign_name(names_by_doctype)
		attempts.extend(attacks.v15_every_whitelisted_method(foreign_name, foreign_company))

		if own_tenant and foreign_tenant and not read_only:
			attempts.extend(attacks.v16_privilege_escalation(actor, own_tenant, foreign_tenant))

		attempts.extend(attacks.v17_grouped_aggregate(actor, foreign_company, own_company))
	finally:
		# Always, whatever happened. A suite that leaves the session as another user
		# would corrupt every test after it.
		frappe.set_user(original)
	return attempts


def _platform_private_check(doctype):
	"""A customer reading your tenant list, your payment orders or your settings."""
	try:
		rows = frappe.get_list(doctype, pluck="name", limit_page_length=5)
	except frappe.PermissionError:
		return attacks.Attempt("platform_private", doctype, frappe.session.user, doctype,
		                       BLOCKED, "PermissionError")
	except Exception as exception:
		return attacks.Attempt("platform_private", doctype, frappe.session.user, doctype,
		                       BLOCKED, type(exception).__name__)
	if rows:
		return attacks.Attempt("platform_private", doctype, frappe.session.user, doctype,
		                       LEAKED, f"read {len(rows)} of your own business records",
		                       rows[:3])
	return attacks.Attempt("platform_private", doctype, frappe.session.user, doctype,
	                       BLOCKED, "empty")


def _reports():
	from a3_sola import registry

	modules = ("Solar CRM", "Solar Operations", "Solar Projects", "Platform")
	return frappe.get_all("Report", filters={"module": ["in", modules], "disabled": 0},
	                      pluck="name", ignore_permissions=True)


def _distinctive_string(company, names_by_doctype):
	"""Something that exists only in the foreign tenant's data - its consumer names."""
	consumers = names_by_doctype.get("Solar Consumer") or []
	if not consumers:
		return None
	return frappe.db.get_value("Solar Consumer", consumers[0], "consumer_name")


def _any_foreign_name(names_by_doctype):
	for names in names_by_doctype.values():
		if names:
			return names[0]
	return None


def _foreign_subscription(foreign_tenant):
	if not foreign_tenant:
		return None
	return frappe.db.get_value("Tenant", foreign_tenant, "platform_subscription")


# ------------------------------------------------------------------- reporting
def summarise(attempts):
	"""Counts by outcome, by vector and by doctype, plus every leak in full."""
	leaks = [a for a in attempts if a.outcome == LEAKED]
	by_vector, by_doctype = {}, {}
	for attempt in attempts:
		for bucket, key in ((by_vector, attempt.vector), (by_doctype, attempt.doctype)):
			row = bucket.setdefault(key, {"attempts": 0, BLOCKED: 0, LEAKED: 0, SKIPPED: 0})
			row["attempts"] += 1
			row[attempt.outcome] += 1
	return {
		"generated_on": str(now_datetime()),
		"attempts": len(attempts),
		"blocked": sum(1 for a in attempts if a.outcome == BLOCKED),
		"leaked": len(leaks),
		"skipped": sum(1 for a in attempts if a.outcome == SKIPPED),
		"vectors": len(by_vector),
		"doctypes": len({a.doctype for a in attempts}),
		"by_vector": by_vector,
		"by_doctype": by_doctype,
		"leaks": [a.as_dict() for a in leaks],
		"skipped_detail": sorted({
			f"{a.doctype}: {a.detail}" for a in attempts if a.outcome == SKIPPED
		}),
	}


def render_summary(result):
	"""The human-readable version. Blunt on purpose."""
	lines = [
		f"Attempts      : {result['attempts']}",
		f"Vectors       : {result['vectors']}",
		f"Doctypes      : {result['doctypes']}",
		f"Blocked       : {result['blocked']}",
		f"Skipped       : {result['skipped']}",
		f"SUCCESSFUL    : {result['leaked']}",
		"",
	]
	if result["leaked"]:
		lines.append("BLOCKER - cross-tenant access succeeded:")
		for leak in result["leaks"][:40]:
			lines.append(
				f"  {leak['vector']:<26} {leak['doctype']:<28} as {leak['actor']}"
				f" -> {leak['target']} ({leak['detail']})"
			)
	else:
		lines.append("No attempt returned foreign data.")
	return "\n".join(lines)


# ------------------------------------------------------------ admin-invokable
@frappe.whitelist()
def run_isolation_audit(tenant=None, read_only=1):
	"""Re-run the attack suite against live data. Read-only by default.

	Given to the client so they can re-run it after any future change rather than trusting
	that a release did not break isolation. Read-only skips the write vectors: proving a
	write is refused is not worth the small chance of proving it is not, on real data.
	"""
	from a3_sola.api import permissions

	permissions.require_role(("Platform Admin", "System Manager"),
	                         action="run the isolation audit")

	tenants = [tenant] if tenant else frappe.get_all(
		"Tenant", filters={"status": "Active"}, pluck="name", limit=10)
	all_attempts, covered = [], []
	for name in tenants:
		row = frappe.db.get_value("Tenant", name, ["company", "admin_user"], as_dict=True)
		if not (row and row.company and row.admin_user):
			continue
		other = frappe.db.get_value(
			"Tenant", {"name": ["!=", name], "company": ["is", "set"]},
			["name", "company"], as_dict=True)
		if not other:
			continue
		all_attempts.extend(run_attack_suite(
			row.admin_user, row.company, other.company,
			own_tenant=name, foreign_tenant=other.name,
			read_only=cint(read_only),
		))
		covered.append(name)

	result = summarise(all_attempts)
	result["tenants_covered"] = covered
	_record(result)
	if result["leaked"]:
		_alert(result)
	return result


def _record(result):
	"""Keep the artefact so a later run can be diffed against this one."""
	frappe.log_error(
		title="a3_sola: isolation audit " + ("FAILED" if result["leaked"] else "clean"),
		message=render_summary(result) + "\n\n" + json.dumps(
			{k: v for k, v in result.items() if k != "by_doctype"}, indent=1, default=str
		)[:80000],
	)


def _alert(result):
	from a3_sola.api.lifecycle import notify

	notify.alert_internal(
		"a3_sola: CROSS-TENANT ACCESS SUCCEEDED",
		"The isolation audit found attempts that returned another tenant's data. Treat "
		"this as a Sev-1 and follow docs/PROVISIONING_RUNBOOK.md.\n\n"
		+ render_summary(result),
	)


def monthly_isolation_audit():
	"""Scheduled. A regression introduced by a later change should be found by us."""
	try:
		return run_isolation_audit(read_only=1)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: monthly isolation audit failed")
		return None
