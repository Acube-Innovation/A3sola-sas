# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
""""Log in as": seeing the portal exactly as someone else sees it, to help them.

Two levels:

* **Platform** - our own support staff (Platform Admin, Platform Tenant Manager) may log
  in as any user of any company, except other platform staff.
* **Company Admin** - a company's admin may log in as the people of their own company,
  except other admins and anyone who also works in another company (logging in as them
  would show the admin a company that is not theirs).

Every session needs a reason, has a time limit, is written to the audit trail at start
and end, and shows a banner with "Return to my account" on every page. Frappe's own
impersonation does the switching - so every Version written during the session records
who was really at the keyboard (`impersonated_by`) - and this module owns the rules
around it: who may, for how long, what is off limits meanwhile, and the way back.

The session is held in the database (Impersonation Session), not only in the cache, so
if the cache is lost the session ends rather than carrying on unchecked.
"""

import hashlib

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from a3_sola.api.settings import get_value

DOCTYPE = "Impersonation Session"
PLATFORM_ROLES = ("Platform Admin", "Platform Tenant Manager")
MIN_REASON = 15
CHOICES = (15, 30, 60, 120)

#: Off limits while viewing as someone: their credentials, their money, their companies,
#: and the desk. Prefix matches on the request path.
BLOCKED = (
	"/app",
	"/desk",
	"/update-password",
	"/api/method/a3_sola.api.memberships.switch_company",
	"/api/method/a3_sola.api.impersonation.start",
	"/api/method/a3_sola.api.console.start_impersonation",
	"/api/method/frappe.core.doctype.user.user.update_password",
	"/api/method/frappe.core.doctype.user.user.generate_keys",
	"/api/method/frappe.core.doctype.user.user.reset_otp_secret",
	"/api/method/frappe.core.doctype.user.user.reset_password",
	"/api/method/a3_sola.api.portal_users.set_password",
	"/api/method/a3_sola.api.portal_users.password_link",
	"/api/method/a3_sola.api.portal_users.welcome",
	"/api/method/a3_sola.api.payments",
	"/api/method/a3_sola.api.billing_portal",
	"/billing",
)


# ------------------------------------------------------------------ who may
def is_platform_staff(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	if user == "Guest":
		return False
	return bool(set(frappe.get_roles(user)) & set(PLATFORM_ROLES))


def working_company(user):
	"""The company a user is working in: their active membership's, else their default."""
	from a3_sola.api import memberships

	return memberships.active_company(user) or frappe.defaults.get_user_default("Company", user=user) or \
		frappe.db.get_single_value("Global Defaults", "default_company")


def target_companies(user):
	"""The companies a person works in (enabled memberships, else their company permissions)."""
	from a3_sola.api import memberships

	rows = memberships.memberships(user)
	if rows:
		return [r.company for r in rows]
	return memberships.company_permissions(user) or [frappe.db.get_single_value("Global Defaults", "default_company")]


def _is_admin_in(user, company):
	from a3_sola.api import memberships
	from a3_sola.api.portal_users import is_user_admin

	m = memberships.get_membership(user, company)
	if m:
		return cint(m.is_admin) and cint(m.enabled)
	return is_user_admin(user)


def can_impersonate(operator, target, company=None):
	"""(level, company, None) when allowed, else (None, None, reason). The reason is for logs and
	tests; callers show only "Not permitted"."""
	from a3_sola.api import memberships

	def no(why):
		return None, None, why

	if not target or target == operator or target in ("Administrator", "Guest"):
		return no("not a target")
	if frappe.session.data.get("impersonated_by"):
		return no("already viewing as someone")
	if not frappe.db.get_value("User", target, "enabled"):
		return no("target disabled")
	if active_for_target(target):
		return no("target already has a session open")
	if memberships.is_protected_user(target):
		return no("target is platform staff or an instance System Manager")
	companies = target_companies(target)
	if is_platform_staff(operator):
		company = company or memberships.active_company(target) or companies[0]
		if company not in companies:
			return no("target does not work in that company")
		return "Platform", company, None
	if not cint(get_value("company_admin_impersonation_enabled", 1)):
		return no("company admin impersonation is turned off")
	mine = working_company(operator)
	if company and company != mine:
		return no("not the admin's company")
	company = mine
	if not company or not _is_admin_in(operator, company):
		return no("not an admin")
	if companies != [company]:
		return no("target works in another company too")
	if _is_admin_in(target, company):
		return no("target is an admin")
	return "Company Admin", company, None


def _refuse():
	frappe.throw(_("Not permitted"), frappe.PermissionError, title=_("Not Permitted"))


def minutes_for(level, minutes):
	cap = cint(get_value("impersonation_max_minutes", 120)) or 120
	if level == "Company Admin":
		cap = min(cap, cint(get_value("company_admin_impersonation_max_minutes", 60)) or 60)
	return max(5, min(cint(minutes) or 30, cap))


# ------------------------------------------------------------------ session lookup
def _hash(sid):
	return hashlib.sha256((sid or "").encode()).hexdigest()


def _row_for_session():
	data = frappe.session.data
	name = data.get("a3s_impersonation")
	if not name or not data.get("impersonated_by"):
		return None
	row = frappe.db.get_value(DOCTYPE, name, ["name", "operator", "target", "company", "level", "status",
		"expires_on", "sid_hash", "started_on"], as_dict=True)
	if not row or row.sid_hash != _hash(frappe.session.sid) or row.target != frappe.session.user:
		return frappe._dict(name=name, status="Missing")
	return row


def current():
	"""The open session in this browser, for the banner; None when not viewing as anyone."""
	if not frappe.session.data.get("a3s_impersonation"):
		return None
	row = _row_for_session()
	if not row or row.status != "Open":
		return None
	company = frappe.db.get_value("Company", row.company, "company_name") or row.company
	return {"name": row.name, "operator": row.operator, "operator_name": frappe.utils.get_fullname(row.operator),
		"target": row.target, "target_name": frappe.utils.get_fullname(row.target), "company": row.company,
		"company_name": company, "level": row.level, "expires_on": str(row.expires_on),
		"expires_iso": get_datetime(row.expires_on).isoformat(),
		"expires_label": frappe.utils.format_datetime(row.expires_on, "h:mm a")}


def active_for_target(user):
	return frappe.db.get_value(DOCTYPE, {"target": user, "status": "Open",
		"expires_on": [">", now_datetime()]}, "name")


# ------------------------------------------------------------------ start
@frappe.whitelist(methods=["POST"])
def start(user, reason, minutes=30, company=None, notify_user=None):
	"""Log in as `user`. Ends the operator's own session; "Return to my account" brings it back."""
	from a3_sola.api import memberships
	from a3_sola.api.lifecycle import gate

	operator = frappe.session.user
	if operator == "Guest" or frappe.get_request_header("Authorization"):
		_refuse()  # a browser session only: never from an API key or token
	reason = (reason or "").strip()
	if len(reason) < MIN_REASON:
		frappe.throw(_("Say why - at least {0} characters. It is kept in the audit trail and shown to the person.")
			.format(MIN_REASON), title=_("Reason Required"))
	level, company, why = can_impersonate(operator, user, company)
	if not level:
		frappe.logger("a3_sola").info({"event": "impersonation_refused", "operator": operator, "target": user,
			"why": why})
		_refuse()
	if cint(frappe.conf.get("deny_multiple_sessions")) or cint(
			frappe.db.get_system_setting("deny_multiple_sessions")):
		frappe.throw(_("This site allows one session per person, so logging in as {0} would sign them out "
			"everywhere. Ask them to sign out first, or turn off \"Deny multiple sessions\".").format(user))
	if memberships.active_company(user) not in (None, company):
		# Platform level only (a company admin's target works in one company): the account is
		# moved to the company being looked at, and the person is told below.
		memberships.apply_membership(user, company, force=True)
	if gate.gate_for(user) == "Blocked":
		frappe.throw(_("{0}'s company is paused, so its pages cannot be opened.").format(user))

	minutes = minutes_for(level, minutes)
	now = now_datetime()
	row = frappe.get_doc({"doctype": DOCTYPE, "operator": operator, "target": user, "company": company,
		"tenant": frappe.db.get_value("Company", company, "a3_sola_tenant")
			if frappe.get_meta("Company").has_field("a3_sola_tenant") else None,
		"level": level, "status": "Open", "reason": reason, "started_on": now,
		"expires_on": add_to_date(now, minutes=minutes), "source_ip": frappe.local.request_ip})
	row.insert(ignore_permissions=True)
	row.db_set("audit_start", _audit("Support Session Started", row,
		f"{level} level, {minutes} minutes, from {frappe.local.request_ip or 'unknown'}"), update_modified=False)
	_notify(row, notify_user)
	frappe.get_doc({"doctype": "Activity Log", "user": user, "status": "Success", "operation": "Impersonate",
		"subject": _("{0} logged in as {1}").format(operator, user)}).insert(ignore_permissions=True, ignore_links=True)

	old_sid = frappe.session.sid
	frappe.flags.a3s_impersonating = True
	try:
		frappe.local.login_manager.impersonate(user)
	finally:
		frappe.flags.a3s_impersonating = False
	data = frappe.local.session_obj.data.data
	data["a3s_impersonation"] = row.name
	data["a3s_company"] = company
	frappe.local.session_obj.update(force=True)
	row.db_set("sid_hash", _hash(frappe.session.sid), update_modified=False)
	frappe.sessions.delete_session(old_sid, user=operator, reason="Logged in as another user")
	frappe.db.commit()
	return {"redirect": "/a3solaportal/dashboard", "name": row.name}


def _audit(entry_type, row, detail):
	from a3_sola.api import audit

	company = frappe.db.get_value("Company", row.company, "company_name") or row.company
	return audit.record(entry_type=entry_type, subject=f"{row.operator} as {row.target} at {company}",
		reason=row.reason, reference_doctype=DOCTYPE, reference_name=row.name, detail=detail, actor=row.operator)


def _notify(row, notify_user=None):
	"""The person is told in the app, and by e-mail when asked; the tenant as for any support session."""
	operator = frappe.utils.get_fullname(row.operator)
	try:
		note = frappe.new_doc("Notification Log", for_user=row.target, from_user=row.operator,
			subject=_("{0} logged in as you until {1}. Reason: {2}").format(operator,
				frappe.utils.format_datetime(row.expires_on, "d MMM, h:mm a"), row.reason))
		note.set("type", "Alert")
		note.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "a3_sola: impersonation notification")
	tell = cint(notify_user) if notify_user not in (None, "") else cint(get_value("notify_user_on_impersonation", 1))
	if tell:
		try:
			frappe.sendmail(recipients=[row.target], subject=_("{0} logged in as you").format(operator),
				message=_("<p>{0} logged in to your portal account to help you, from {1} until {2}.</p>"
					"<p>Why: {3}</p><p>Everything done meanwhile is recorded as done by {0} on your behalf. "
					"If you were not expecting this, tell your administrator.</p>").format(
					frappe.utils.escape_html(operator), frappe.utils.format_datetime(row.started_on, "d MMM, h:mm a"),
					frappe.utils.format_datetime(row.expires_on, "h:mm a"), frappe.utils.escape_html(row.reason)))
			row.db_set("user_notified", 1, update_modified=False)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "a3_sola: impersonation e-mail")
	if row.level == "Platform" and row.tenant:
		from a3_sola.api.console import _tell_the_tenant

		tenant = frappe.db.get_value("Tenant", row.tenant, ["admin_user", "tenant_name", "primary_contact_email"],
			as_dict=True)
		if tenant and _tell_the_tenant(tenant, {"tenant": row.tenant, "operator": row.operator, "reason": row.reason,
				"started": str(row.started_on), "expires": str(row.expires_on)}):
			row.db_set("tenant_notified", 1, update_modified=False)


# ------------------------------------------------------------------ end
def _close(row, how):
	if not row or not row.get("name") or not frappe.db.exists(DOCTYPE, row.name):
		return
	if frappe.db.get_value(DOCTYPE, row.name, "status") != "Open":
		return
	doc = frappe.get_doc(DOCTYPE, row.name)
	doc.db_set({"status": "Ended", "ended_on": now_datetime(), "end_reason": how}, update_modified=False)
	entry = {"Expired": "Support Session Expired", "Revoked": "Support Session Revoked"}.get(how, "Support Session Ended")
	doc.db_set("audit_end", _audit(entry, doc, f"Ended: {how}."), update_modified=False)


@frappe.whitelist(methods=["POST"])
def end():
	""""Return to my account"."""
	row = _row_for_session()
	if not row:
		_refuse()
	cur = frappe.session.sid
	if row.status != "Open":
		_close(row, "Expired")
		_sign_out(cur)
		return {"redirect": "/a3solaportal/login"}
	operator = row.operator
	_close(row, "Returned")
	back = frappe.db.get_value("User", operator, "enabled") and (is_platform_staff(operator)
		or _is_admin_in(operator, row.company))
	if back:
		frappe.local.login_manager.login_as(operator)
		frappe.sessions.delete_session(cur, user=row.target, reason="Returned to own account")
		frappe.db.commit()
		return {"redirect": "/a3solaportal/users" if row.level == "Company Admin" else "/a3solaportal/support"}
	_sign_out(cur)
	return {"redirect": "/a3solaportal/login"}


def _sign_out(sid):
	frappe.sessions.delete_session(sid, reason="Support session ended")
	frappe.local.login_manager.login_as_guest()
	frappe.db.commit()


@frappe.whitelist(methods=["POST"])
def revoke(name, reason=None):
	"""Platform staff: end someone's open session now."""
	if not is_platform_staff():
		_refuse()
	row = frappe.db.get_value(DOCTYPE, name, ["name", "sid_hash", "target", "status"], as_dict=True)
	if not row or row.status != "Open":
		return {"ok": True}
	_close(row, "Revoked")
	_drop_sessions(row)
	return {"ok": True}


def _drop_sessions(row):
	# Sessions is a table, not a doctype.
	for (sid,) in frappe.db.sql("select sid from `tabSessions` where user = %s", row.target):
		if _hash(sid) == row.sid_hash:
			frappe.sessions.delete_session(sid, user=row.target, reason="Support session ended")


# ------------------------------------------------------------------ hooks
def enforce():
	"""`before_request`: the clock, the company lock and the off-limits list."""
	if frappe.session.user in ("Guest", None) or not frappe.session.data.get("a3s_impersonation"):
		return
	request = getattr(frappe.local, "request", None)
	path = (request.path if request else "") or ""
	row = _row_for_session()
	expired = not row or row.status != "Open" or get_datetime(row.expires_on) <= now_datetime()
	if not expired:
		from a3_sola.api import memberships

		active = memberships.active_company(row.target)
		if active and active != row.company:
			_close(row, "Target Changed")
			expired = True
	if expired:
		if row and row.get("status") == "Open":
			_close(row, "Expired")
		sid = frappe.session.sid
		frappe.sessions.delete_session(sid, reason="Support session ended")
		frappe.local.login_manager.login_as_guest()
		frappe.db.commit()
		if path.startswith("/api/"):
			frappe.throw(_("The support session has ended. Sign in again."), frappe.AuthenticationError,
				title=_("Session Ended"))
		return  # a page: it now sees a guest and sends them to sign in
	if path.startswith("/api/method/a3_sola.api.impersonation.end") or path.startswith("/api/method/logout"):
		return
	if any(path == p or path.startswith(p + "/") or (p.startswith("/api/method/") and path.startswith(p))
			for p in BLOCKED):
		frappe.throw(_("Not available while you are viewing as someone else. Return to your own account first."),
			frappe.PermissionError, title=_("Not While Viewing As"))


def on_logout(login_manager=None):
	if frappe.session.data.get("a3s_impersonation"):
		row = _row_for_session()
		if row and row.status == "Open":
			_close(row, "Logged Out")


def expire_stale():
	"""Every five minutes: close sessions past their time that nobody clicked in since."""
	for row in frappe.get_all(DOCTYPE, filters={"status": "Open", "expires_on": ["<=", now_datetime()]},
			fields=["name", "sid_hash", "target", "status", "operator", "company", "reason"]):
		_close(row, "Expired")
		_drop_sessions(row)
	frappe.db.commit()


# ------------------------------------------------------------------ the support page
@frappe.whitelist()
def search(query=None, limit=30):
	"""Platform staff: people to log in as, across every company."""
	if not is_platform_staff():
		_refuse()
	from a3_sola.api import memberships
	from a3_sola.api.portal_users import type_of

	needle = f"%{(query or '').strip()}%"
	users = frappe.get_all("User", filters={"enabled": 1, "name": ["not in", ["Administrator", "Guest"]]},
		or_filters={"name": ["like", needle], "full_name": ["like", needle]},
		fields=["name", "full_name", "role_profile_name", "enabled", "user_type"], limit=cint(limit) or 30,
		order_by="full_name asc")
	out = []
	for u in users:
		if memberships.is_protected_user(u.name):
			continue
		rows = memberships.memberships(u.name)
		companies = [{"company": r.company, "company_name": r.company_name, "type": r.portal_type,
			"is_active": r.is_active} for r in rows] or [{"company": c, "company_name":
			frappe.db.get_value("Company", c, "company_name") or c, "type": type_of(u), "is_active": True}
			for c in target_companies(u.name) if c]
		out.append({"name": u.name, "full_name": u.full_name or u.name, "companies": companies,
			"open": bool(active_for_target(u.name))})
	return out


@frappe.whitelist()
def sessions(open_only=0, limit=50):
	"""Platform staff see every session; a company admin, those in their own company."""
	filters = {}
	if cint(open_only):
		filters["status"] = "Open"
	if not is_platform_staff():
		company = working_company(frappe.session.user)
		if not _is_admin_in(frappe.session.user, company):
			_refuse()
		filters["company"] = company
	rows = frappe.get_all(DOCTYPE, filters=filters, fields=["name", "operator", "target", "company", "level", "status",
		"reason", "started_on", "expires_on", "ended_on", "end_reason"], order_by="started_on desc",
		limit=cint(limit) or 50)
	for r in rows:
		r.operator_name = frappe.utils.get_fullname(r.operator)
		r.target_name = frappe.utils.get_fullname(r.target)
		r.company_name = frappe.db.get_value("Company", r.company, "company_name") or r.company
		for f in ("started_on", "expires_on", "ended_on"):
			r[f] = frappe.utils.format_datetime(r[f], "d MMM yyyy, h:mm a") if r[f] else ""
	return rows
