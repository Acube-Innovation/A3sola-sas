# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Running a tenant after it exists: usage, entitlements, export and termination.

The termination flow is the part worth reading carefully, because the tempting version of
it is wrong. Terminating a customer means their access stops - it does not mean their data
is destroyed. So this exports first, disables second, and never deletes a Company at all.

Deleting data is a separate, deliberate, manual operation that requires a documented
customer request. That distinction matters twice over: for a billing dispute, where the
records are the evidence, and for data-protection obligations, where erasure has to be
demonstrably intentional rather than a side effect of an account closing.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from a3_sola.api import audit
from a3_sola.api.permissions import require_role

MANAGER_ROLES = ("Platform Tenant Manager", "Platform Admin", "System Manager")
OPERATOR_ROLES = ("Platform Provisioning Operator",) + MANAGER_ROLES


@frappe.whitelist()
def recalculate_usage(tenant):
	require_role(OPERATOR_ROLES, _("Recalculating tenant usage"))
	from a3_sola.api.entitlements import recalculate_usage as recalc

	return recalc(tenant)


@frappe.whitelist()
def apply_entitlements(tenant):
	"""Reconcile every user's roles against the snapshot. Also Phase 7's upgrade path."""
	require_role(MANAGER_ROLES, _("Applying entitlements"))
	from a3_sola.api.entitlements import apply_module_entitlements

	result = apply_module_entitlements(tenant)
	audit.record(
		"Compliance Setting Changed",
		f"Module entitlements reapplied for {tenant}",
		reference_doctype="Tenant",
		reference_name=tenant,
		detail=json.dumps(result, default=str, indent=1)[:2000],
	)
	return result


@frappe.whitelist()
def resend_welcome(tenant):
	require_role(OPERATOR_ROLES, _("Resending the welcome email"))
	from a3_sola.api import onboarding

	sent = onboarding.send_welcome_email(tenant)
	return {"sent": bool(sent)}


@frappe.whitelist()
def export_tenant_data(tenant):
	"""Everything belonging to this tenant, as a downloadable archive.

	Run before termination, and available at any time - a customer asking for their data
	should not have to ask twice. It walks the registry rather than a hand-written list, so
	a doctype added by a later phase is included without anyone remembering to add it.
	"""
	require_role(MANAGER_ROLES, _("Exporting tenant data"))
	from a3_sola.registry import all_permission_doctypes

	doc = frappe.get_doc("Tenant", tenant)
	if not doc.company:
		frappe.throw(_("This tenant has no company, so there is nothing to export."))

	payload = {
		"tenant": doc.as_dict(no_nulls=True),
		"exported_on": str(now_datetime()),
		"company": doc.company,
		"records": {},
	}
	for doctype in sorted(set(all_permission_doctypes())):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if meta.issingle or meta.istable:
			continue
		rows = frappe.get_all(
			doctype, filters={"company": doc.company}, fields=["*"], limit_page_length=0
		)
		if rows:
			payload["records"][doctype] = rows

	content = frappe.as_json(payload, indent=1)
	filename = f"{doc.tenant_code}-export-{frappe.utils.today()}.json"
	saved = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": content,
			"is_private": 1,
			"attached_to_doctype": "Tenant",
			"attached_to_name": doc.name,
		}
	)
	saved.flags.ignore_permissions = True
	saved.insert(ignore_permissions=True)

	audit.record(
		"Compliance Setting Changed",
		f"Tenant data exported for {doc.tenant_code}",
		reference_doctype="Tenant",
		reference_name=doc.name,
		detail=f"{sum(len(v) for v in payload['records'].values())} records across "
		       f"{len(payload['records'])} doctypes, saved as {filename}.",
	)
	return {"file_url": saved.file_url, "doctypes": len(payload["records"])}


@frappe.whitelist()
def terminate_tenant(tenant, confirmation, reason):
	"""End a tenant's access. Exports first, disables second, deletes nothing.

	The typed confirmation is not ceremony. Terminate is reached from a list view where
	the row above and the row below are other people's businesses, and a mis-click that
	only needed an OK would end the wrong one.
	"""
	require_role(MANAGER_ROLES, _("Terminating a tenant"))
	doc = frappe.get_doc("Tenant", tenant)

	if (confirmation or "").strip() != doc.tenant_code:
		frappe.throw(
			_("Type the tenant code {0} exactly to confirm. Nothing has been changed.").format(
				frappe.bold(doc.tenant_code)
			),
			title=_("Confirmation Does Not Match"),
		)
	reason = (reason or "").strip()
	if len(reason) < 10:
		frappe.throw(
			_("Record why this tenant is being terminated. It is kept permanently."),
			title=_("A Reason is Required"),
		)
	if doc.status == "Terminated":
		return {"status": "Terminated", "already": True}

	export = export_tenant_data(tenant)

	disabled = []
	for email in frappe.get_all("User", filters={"a3_sola_tenant": doc.name}, pluck="name"):
		if email == "Administrator":
			continue
		frappe.db.set_value("User", email, "enabled", 0, update_modified=False)
		disabled.append(email)

	frappe.db.set_value(
		"Tenant", doc.name,
		{"status": "Terminated", "status_reason": reason[:500]},
		update_modified=False,
	)

	audit.record(
		"Compliance Setting Changed",
		f"Tenant {doc.tenant_code} terminated",
		reference_doctype="Tenant",
		reference_name=doc.name,
		reason=reason,
		value_before=doc.status,
		value_after="Terminated",
		detail=(
			f"{len(disabled)} user(s) disabled. Data exported to {export['file_url']}.\n"
			f"The company {doc.company} was NOT deleted and neither was any of its data - "
			f"erasure is a separate, deliberate operation requiring a documented request."
		),
	)
	return {
		"status": "Terminated",
		"users_disabled": len(disabled),
		"export": export["file_url"],
		"company_retained": doc.company,
	}


def on_initial_payment_refunded(subscription):
	"""Phase 5's contract, implemented here.

	A refunded first payment must not leave a tenant provisioned and unpaid - but the
	answer is to suspend, not to delete. The company stays, the data stays, and a person
	decides what happens next.
	"""
	name = subscription if isinstance(subscription, str) else subscription.name
	tenant = frappe.db.get_value("Tenant", {"platform_subscription": name}, "name")
	if not tenant:
		return None

	reason = _("The initial payment was refunded, so the subscription is unpaid.")
	frappe.db.set_value(
		"Tenant", tenant, {"status": "Suspended", "status_reason": reason},
		update_modified=False,
	)
	for email in frappe.get_all("User", filters={"a3_sola_tenant": tenant}, pluck="name"):
		if email != "Administrator":
			frappe.db.set_value("User", email, "enabled", 0, update_modified=False)

	audit.record(
		"Compliance Setting Changed",
		f"Tenant suspended after an initial-payment refund",
		reference_doctype="Tenant",
		reference_name=tenant,
		platform_subscription=name,
		reason=reason,
		value_after="Suspended",
		detail=(
			"Access is off and the data is untouched. Somebody has to decide whether this "
			"becomes a termination - see docs/PROVISIONING_RUNBOOK.md."
		),
	)
	frappe.log_error(
		title="a3_sola: tenant suspended after refund",
		message=(
			f"Tenant {tenant} was suspended because the first payment on {name} was "
			f"refunded. Nothing has been deleted. Decide whether to reinstate or terminate."
		),
	)
	return tenant


@frappe.whitelist()
def tenant_dashboard(tenant):
	"""What the Tenant form's dashboard shows: everything about one customer, in one call."""
	require_role(OPERATOR_ROLES + ("Platform Billing Manager",), _("Viewing a tenant"))
	from a3_sola.api.entitlements import get_tenant_usage
	from a3_sola.api.onboarding import completion_percent

	doc = frappe.get_doc("Tenant", tenant)
	subscription = doc.platform_subscription
	return {
		"usage": get_tenant_usage(tenant),
		"onboarding_percent": completion_percent(tenant),
		"subscription": frappe.db.get_value(
			"Platform Subscription", subscription,
			["name", "status", "billing_cycle", "recurring_amount", "next_billing_date",
			 "collection_route", "lifetime_value"],
			as_dict=True,
		) if subscription else None,
		"invoices": frappe.get_all(
			"Subscription Invoice",
			filters={"platform_subscription": subscription} if subscription else {"name": ["is", "not set"]},
			fields=["name", "invoice_date", "grand_total", "payment_status"],
			order_by="invoice_date desc", limit_page_length=12,
		),
		"payments": frappe.get_all(
			"Payment Order",
			filters={"platform_subscription": subscription} if subscription else {"name": ["is", "not set"]},
			fields=["name", "total_amount", "status", "paid_on"],
			order_by="creation desc", limit_page_length=12,
		),
		"invitations": frappe.get_all(
			"Tenant Invitation", filters={"tenant": tenant},
			fields=["name", "invited_email", "status", "sent_on"],
			order_by="creation desc", limit_page_length=20,
		),
		"job": frappe.db.get_value(
			"Provisioning Job", {"tenant": tenant},
			["name", "status", "current_step", "duration_seconds", "requires_manual_intervention"],
			as_dict=True,
		),
	}
