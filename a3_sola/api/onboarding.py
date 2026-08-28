# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The welcome, and the list of things provisioning deliberately did not guess.

Provisioning seeds a lot. What it does not do is decide anything that would be expensive
to get wrong on the customer's behalf: which ledger accounts the money posts to, whether
the seeded tariff matches the current regulator's order, whether their CA agrees with the
GST treatment. Every one of those is a judgement call with a real consequence, and a
guessed answer is worse than an empty field because nobody goes back to check a field that
already looks filled in.

So they become a checklist the tenant sees on first login, with the critical ones surfaced
as a banner until they are done.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from a3_sola.api.settings import get_value

#: (code, title, why it matters, critical, route)
TASKS = (
	(
		"ACCOUNT_MAPPING",
		"Map your ledger accounts with your accountant",
		"Provisioning deliberately left every account blank. A guessed mapping posts money "
		"to the wrong ledger and nobody notices until a reconciliation. Nothing posts to "
		"accounts until this is done, so it costs you nothing to take your time - but "
		"invoicing will not reach your books until it is.",
		1,
		"/account-mapping",
	),
	(
		"VERIFY_TARIFF",
		"Verify the electricity tariff against the current tariff order",
		"A representative tariff was seeded so the savings calculation works on day one. "
		"Tariff orders change, and a stale rate makes every proposal's savings figure "
		"wrong in a way the customer will notice after they have signed.",
		1,
		"/app/electricity-tariff",
	),
	(
		"CONFIRM_GST",
		"Confirm the GST valuation with your CA before enabling postings",
		"The seeded valuation rule is inactive on purpose. The 70:30 blended treatment is "
		"one reading of the rules; your CA's is the one that matters, and it is theirs to "
		"sign off before anything reaches a return.",
		1,
		"/app/solar-gst-valuation-rule",
	),
	(
		"CHECK_DISCOM",
		"Check your DISCOM and its sections",
		"KSEB and its sections are seeded for Kerala. Anywhere else, a placeholder was "
		"created and needs replacing with your own distribution company before the first "
		"portal application.",
		0,
		"/app/discom",
	),
	(
		"BRANDING",
		"Upload your logo and letterhead",
		"Every generated document - proposals, work orders, completion reports - carries "
		"your letterhead. Until you upload one they go out plain.",
		0,
		"/app/letter-head",
	),
	(
		"INVITE_TEAM",
		"Invite your team",
		"Your plan includes seats that nobody is using yet.",
		0,
		"/seats",
	),
	(
		"REVIEW_PACKAGES",
		"Review the starter packages and your own pricing",
		"Packages at 1, 2, 3 and 5 kW were seeded with representative pricing so you can "
		"quote immediately. They are a starting point, not your price list.",
		0,
		"/app/solar-package",
	),
)


# ------------------------------------------------------------------- step 13
def welcome(context):
	tenant = context.reload_tenant()
	build_checklist(tenant.name)
	sent = send_welcome_email(tenant.name, context.artefacts.get("password_reset_link"))
	notify_sales(tenant.name)
	return {
		"created_doctype": "Onboarding",
		"created_name": tenant.name,
		"remarks": _("Checklist built; welcome {0}.").format(_("sent") if sent else _("skipped")),
	}


def build_checklist(tenant_name):
	tenant = frappe.get_doc("Tenant", tenant_name)
	existing = {row.task_code for row in tenant.onboarding_tasks}
	added = 0
	for code, title, detail, critical, route in TASKS:
		if code in existing:
			continue
		tenant.append(
			"onboarding_tasks",
			{
				"task_code": code,
				"task_title": title,
				"task_detail": detail,
				"is_critical": critical,
				"route": route,
			},
		)
		added += 1
	if added:
		tenant.flags.ignore_permissions = True
		tenant.flags.ignore_validate_update_after_submit = True
		tenant.save(ignore_permissions=True)
	return added


def send_welcome_email(tenant_name, reset_link=None):
	if not cint(get_value("provisioning_send_welcome_email", 1)):
		return False
	if frappe.flags.in_test or frappe.flags.in_demo:
		return False
	tenant = frappe.get_doc("Tenant", tenant_name)
	from a3_sola.api import tenant_users

	link = reset_link or tenant_users.password_reset_link(tenant.admin_user)
	template = get_value("welcome_email_template")
	product = get_value("product_name") or "a3 sola"
	try:
		if template and frappe.db.exists("Email Template", template):
			doc = frappe.get_doc("Email Template", template)
			subject = frappe.render_template(doc.subject, {"tenant": tenant})
			message = frappe.render_template(doc.response, {"tenant": tenant, "link": link})
		else:
			subject = _("Your {0} workspace is ready").format(product)
			message = frappe.render_template(
				"a3_sola/templates/emails/tenant_welcome.html",
				{
					"tenant": tenant,
					"set_password_url": link["url"],
					"expiry_hours": link["expires_in_hours"],
					"modules": _module_labels(tenant),
					"tasks": [t for t in TASKS if t[3]][:3],
					"product_name": product,
					"company_legal_name": get_value("company_legal_name") or "",
					"sales_email": get_value("sales_email"),
				},
			)
		frappe.sendmail(
			recipients=[tenant.primary_contact_email],
			subject=subject,
			message=message,
			reference_doctype=tenant.doctype,
			reference_name=tenant.name,
			now=False,
		)
		return True
	except Exception:
		frappe.log_error(
			title="a3_sola: welcome email not sent",
			message=f"{tenant_name}\n\n{frappe.get_traceback()}",
		)
		return False


def _module_labels(tenant):
	return [row.module_name for row in tenant.enabled_modules if cint(row.is_enabled)]


def notify_sales(tenant_name):
	recipient = get_value("sales_email")
	if not recipient or frappe.flags.in_test or frappe.flags.in_demo:
		return False
	tenant = frappe.get_cached_doc("Tenant", tenant_name)
	try:
		frappe.sendmail(
			recipients=[recipient],
			subject=_("Tenant live: {0}").format(tenant.tenant_name),
			message=(
				f"<p><b>{frappe.utils.escape_html(tenant.tenant_name)}</b> is live.</p>"
				f"<ul><li>Plan: {frappe.utils.escape_html(tenant.plan_code or '')}</li>"
				f"<li>Seats: {cint(tenant.user_quota)}</li>"
				f"<li>Admin: {frappe.utils.escape_html(tenant.primary_contact_email or '')}</li>"
				f"<li>Company: {frappe.utils.escape_html(tenant.company or '')}</li></ul>"
			),
			reference_doctype=tenant.doctype,
			reference_name=tenant.name,
			now=False,
		)
		return True
	except Exception:
		frappe.log_error(title="a3_sola: tenant live notice", message=frappe.get_traceback())
		return False


# --------------------------------------------------------------- the surface
@frappe.whitelist()
def my_checklist():
	"""What the tenant's own onboarding page reads."""
	from a3_sola.api.entitlements import tenant_of

	tenant_name = tenant_of()
	if not tenant_name:
		return {"tenant": None, "tasks": [], "outstanding_critical": 0}
	tenant = frappe.get_cached_doc("Tenant", tenant_name)
	tasks = [
		{
			"code": row.task_code,
			"title": row.task_title,
			"detail": row.task_detail,
			"critical": cint(row.is_critical),
			"route": row.route,
			"done": cint(row.is_complete),
		}
		for row in tenant.onboarding_tasks
	]
	return {
		"tenant": tenant.tenant_name,
		"notes": tenant.post_provision_notes,
		"tasks": tasks,
		"completed": sum(1 for t in tasks if t["done"]),
		"total": len(tasks),
		"outstanding_critical": sum(1 for t in tasks if t["critical"] and not t["done"]),
	}


@frappe.whitelist()
def complete_task(task_code):
	from a3_sola.api.entitlements import tenant_of

	tenant_name = tenant_of()
	if not tenant_name:
		frappe.throw(_("This page is for workspace users."), frappe.PermissionError)
	tenant = frappe.get_doc("Tenant", tenant_name)
	for row in tenant.onboarding_tasks:
		if row.task_code == task_code:
			frappe.db.set_value(
				"Tenant Onboarding Task", row.name,
				{"is_complete": 1, "completed_on": now_datetime(),
				 "completed_by": frappe.session.user},
				update_modified=False,
			)
			frappe.flags.commit = True
			return {"status": "ok", "code": task_code}
	frappe.throw(_("No such setup task."), title=_("Unknown Task"))


def completion_percent(tenant_name):
	rows = frappe.get_all(
		"Tenant Onboarding Task",
		filters={"parent": tenant_name, "parenttype": "Tenant"},
		fields=["is_complete", "is_critical"],
	)
	if not rows:
		return 0.0
	done = sum(1 for r in rows if cint(r.is_complete))
	return round(done * 100.0 / len(rows), 1)
