# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Letting a tenant admin fill their own seats.

Provisioning creates the capacity, not the people. Guessing who else works at a company
from a signup form produces accounts nobody asked for, attached to addresses nobody
verified.

Three properties this module has to get right:

* **The quota is checked twice** - when the invitation is sent, and again when it is
  accepted. Seats fill between those two moments. Checking only at send time is how a
  five-seat tenant ends up with seven users, each of whom was legitimately invited.
* **The token is compared in constant time and dies on revocation.** A revoked invitation
  whose link still works is not revoked.
* **It never says whether an address already exists.** `accept_invitation` is a guest
  endpoint; an error that distinguishes "no such invitation" from "that person already has
  an account here" is an account enumeration oracle pointed at your entire customer base.
"""

import hmac

import frappe
from frappe import _
from frappe.utils import add_days, cint, now_datetime

from a3_sola.api import platform as platform_api
from a3_sola.api import ratelimit
from a3_sola.api.entitlements import assert_seat_available, get_tenant_usage, recalculate_usage
from a3_sola.api.settings import get_float, get_int, get_value

GENERIC_REFUSAL = "That invitation link is not valid. It may have expired or been withdrawn."


# ------------------------------------------------------------------- step 11
def seed_for_tenant(context):
	"""Open the seats. Creates invitations only for addresses the signup actually captured."""
	tenant = context.reload_tenant()
	usage = recalculate_usage(tenant.name)
	created = []
	for email in _team_emails_from_signup(context.signup):
		if email == (tenant.primary_contact_email or "").lower():
			continue
		try:
			created.append(create_invitation(tenant.name, email, silent=True))
		except frappe.ValidationError:
			# A seat shortfall here is not a provisioning failure. The admin can invite
			# whoever fits once they are in.
			context.note(f"Could not pre-create an invitation for {email}: no seat available.")
	return {
		"created_doctype": "Tenant Invitation",
		"created_name": f"{len(created)} invitation(s)",
		"remarks": _("{0} of {1} seats used, {2} available.").format(
			usage["used"], usage["quota"], usage["available"]
		),
	}


def _team_emails_from_signup(signup):
	"""Phase 4's form captures one contact today. Kept as a hook for when it captures more."""
	if not signup:
		return []
	extra = getattr(signup, "team_emails", None)
	if not extra:
		return []
	return [e.strip().lower() for e in str(extra).replace("\n", ",").split(",") if e.strip()]


# ------------------------------------------------------------------ creation
def create_invitation(tenant_name, email, invited_name=None, role_profile=None, silent=False):
	email = (email or "").strip().lower()
	if not email or "@" not in email:
		frappe.throw(_("Enter a valid email address."), title=_("Invalid Email"))

	tenant = frappe.get_doc("Tenant", tenant_name)
	if frappe.db.exists(
		"Tenant Invitation",
		{"tenant": tenant_name, "invited_email": email, "status": ["in", ["Pending", "Sent"]]},
	):
		frappe.throw(
			_("There is already an open invitation for {0}. Resend it rather than creating "
			  "a second one.").format(email),
			title=_("Already Invited"),
		)

	assert_seat_available(tenant_name, for_email=email)
	_assert_pending_cap(tenant)

	invitation = frappe.new_doc("Tenant Invitation")
	invitation.update(
		{
			"tenant": tenant_name,
			"invited_email": email,
			"invited_name": invited_name,
			"role_profile": role_profile or tenant.assigned_role_profile,
			"invited_by": frappe.session.user,
			"status": "Pending",
			"invitation_token": frappe.generate_hash(length=48),
			"token_expires_on": add_days(now_datetime(), get_int("invitation_expiry_days", 14) or 14),
		}
	)
	invitation.flags.ignore_permissions = True
	invitation.insert(ignore_permissions=True)
	recalculate_usage(tenant_name)
	if not silent:
		send(invitation.name)
	return invitation.name


def _assert_pending_cap(tenant):
	"""Allow inviting a little beyond the seat count, because people do not all reply.

	The quota still binds at acceptance - this only decides how many envelopes may be in
	the air at once.
	"""
	multiplier = get_float("max_pending_invitations_multiplier", 1.5) or 1.5
	cap = int(cint(tenant.user_quota) * multiplier)
	pending = frappe.db.count(
		"Tenant Invitation", {"tenant": tenant.name, "status": ["in", ["Pending", "Sent"]]}
	)
	if pending >= max(cap, 1):
		frappe.throw(
			_("There are already {0} invitations waiting to be accepted, which is as many "
			  "as this plan allows to be open at once. Revoke one that is not going to be "
			  "accepted, or wait for a reply.").format(pending),
			title=_("Too Many Open Invitations"),
		)


# --------------------------------------------------------------------- API
@frappe.whitelist()
def invite(tenant, email, invited_name=None, role_profile=None):
	"""Called by the tenant admin from their own seats page."""
	_assert_tenant_admin(tenant)
	if not ratelimit.check("tenant_invite", frappe.session.user, "invite_rate_limit", 30, 3600):
		frappe.throw(_("Too many invitations sent just now. Try again shortly."),
		             title=_("Slow Down"))
	return create_invitation(tenant, email, invited_name, role_profile)


@frappe.whitelist()
def resend(invitation_name):
	invitation = frappe.get_doc("Tenant Invitation", invitation_name)
	_assert_tenant_admin(invitation.tenant)
	if invitation.status not in ("Pending", "Sent"):
		frappe.throw(_("Only an open invitation can be resent."), title=_("Cannot Resend"))
	invitation.db_set(
		{
			"token_expires_on": add_days(now_datetime(), get_int("invitation_expiry_days", 14) or 14),
			"resend_count": cint(invitation.resend_count) + 1,
		},
		update_modified=False,
	)
	return send(invitation_name)


@frappe.whitelist()
def revoke(invitation_name, reason=None):
	"""Kills the token immediately. A revoked link that still works is not revoked."""
	invitation = frappe.get_doc("Tenant Invitation", invitation_name)
	_assert_tenant_admin(invitation.tenant)
	if invitation.status == "Accepted":
		frappe.throw(
			_("This invitation was already accepted. Disable the user instead."),
			title=_("Already Accepted"),
		)
	invitation.db_set(
		{
			"status": "Revoked",
			"invitation_token": None,
			"revoked_by": frappe.session.user,
			"revoked_on": now_datetime(),
			"revocation_reason": (reason or "")[:500],
		},
		update_modified=False,
	)
	recalculate_usage(invitation.tenant)
	return invitation.status


def send(invitation_name):
	invitation = frappe.get_doc("Tenant Invitation", invitation_name)
	invitation.db_set({"status": "Sent", "sent_on": now_datetime()}, update_modified=False)
	if frappe.flags.in_test or frappe.flags.in_demo:
		return invitation.status
	tenant = frappe.get_cached_doc("Tenant", invitation.tenant)
	try:
		frappe.sendmail(
			recipients=[invitation.invited_email],
			subject=_("You have been invited to {0}").format(tenant.tenant_name),
			message=frappe.render_template(
				"a3_sola/templates/emails/tenant_invitation.html",
				{
					"tenant": tenant,
					"invitation": invitation,
					"accept_url": frappe.utils.get_url(
						f"{platform_api.route('accept-invitation')}"
						f"?token={invitation.invitation_token}"
					),
					"product_name": get_value("product_name") or "a3 sola",
					"expiry_days": get_int("invitation_expiry_days", 14) or 14,
				},
			),
			reference_doctype=invitation.doctype,
			reference_name=invitation.name,
			now=False,
		)
	except Exception:
		frappe.log_error(
			title="a3_sola: invitation email not sent",
			message=f"{invitation.name}\n\n{frappe.get_traceback()}",
		)
	return invitation.status


@frappe.whitelist(allow_guest=True, methods=["POST"])
def accept_invitation(token, full_name=None):
	"""Turn an invitation into a user. Guest endpoint, so every failure looks identical."""
	if not ratelimit.check("invitation_accept", frappe.local.request_ip or "unknown",
	                       "invite_accept_rate_limit", 20, 3600):
		frappe.throw(_("Too many attempts. Try again shortly."), title=_("Slow Down"))

	invitation = _resolve_token(token)
	tenant = frappe.get_doc("Tenant", invitation.tenant)

	if tenant.status != "Active":
		_fail(invitation, _("The workspace is not active."))

	# Re-checked here, not only at send time. Seats fill in between.
	usage = get_tenant_usage(tenant.name)
	if usage["available_ignoring_pending"] <= 0:
		_fail(
			invitation,
			_("All {0} seats were taken before this invitation was accepted.").format(usage["quota"]),
			notify_admin=True,
		)

	email = invitation.invited_email
	if frappe.db.exists("User", email):
		# Never say so to the caller - see the module docstring.
		_fail(invitation, _("An account already exists for this address."), notify_admin=True)

	from a3_sola.api import tenant_users

	user = tenant_users.provision_invited_user(invitation)
	invitation.db_set(
		{
			"status": "Accepted",
			"accepted_on": now_datetime(),
			"created_user": user,
			"invitation_token": None,
		},
		update_modified=False,
	)
	recalculate_usage(tenant.name)
	link = tenant_users.password_reset_link(user)
	frappe.flags.commit = True
	return {"status": "ok", "set_password_url": link["url"]}


def _resolve_token(token):
	"""Constant-time comparison against open invitations, and one generic refusal."""
	token = (token or "").strip()
	if not token:
		frappe.throw(_(GENERIC_REFUSAL), title=_("Invitation Not Valid"))
	candidates = frappe.get_all(
		"Tenant Invitation",
		filters={"status": ["in", ["Pending", "Sent"]]},
		fields=["name", "invitation_token", "token_expires_on"],
	)
	match = None
	for row in candidates:
		if row.invitation_token and hmac.compare_digest(str(row.invitation_token), token):
			match = row
			break
	if not match:
		frappe.throw(_(GENERIC_REFUSAL), title=_("Invitation Not Valid"))
	if match.token_expires_on and match.token_expires_on < now_datetime():
		frappe.db.set_value("Tenant Invitation", match.name, "status", "Expired",
		                    update_modified=False)
		frappe.flags.commit = True
		frappe.throw(_(GENERIC_REFUSAL), title=_("Invitation Not Valid"))
	return frappe.get_doc("Tenant Invitation", match.name)


def _fail(invitation, reason, notify_admin=False):
	invitation.db_set(
		{"status": "Failed", "failure_reason": str(reason)[:500], "invitation_token": None},
		update_modified=False,
	)
	frappe.flags.commit = True
	if notify_admin:
		_notify_admin_of_failure(invitation, reason)
	frappe.throw(_(GENERIC_REFUSAL), title=_("Invitation Not Valid"))


def _notify_admin_of_failure(invitation, reason):
	"""The invitee gets a generic message; the tenant admin gets the real one."""
	admin = frappe.db.get_value("Tenant", invitation.tenant, "admin_user")
	if not admin or frappe.flags.in_test or frappe.flags.in_demo:
		return
	try:
		frappe.sendmail(
			recipients=[admin],
			subject=_("An invitation could not be accepted"),
			message=(
				f"<p>The invitation to <b>{frappe.utils.escape_html(invitation.invited_email)}</b> "
				f"could not be completed.</p><p>{frappe.utils.escape_html(str(reason))}</p>"
			),
			reference_doctype=invitation.doctype,
			reference_name=invitation.name,
			now=False,
		)
	except Exception:
		frappe.log_error(title="a3_sola: invitation failure notice", message=frappe.get_traceback())


def expire_stale_invitations():
	"""Daily. An invitation past its date should say Expired rather than Sent."""
	stale = frappe.get_all(
		"Tenant Invitation",
		filters={"status": ["in", ["Pending", "Sent"]], "token_expires_on": ["<", now_datetime()]},
		fields=["name", "tenant"],
	)
	for row in stale:
		frappe.db.set_value(
			"Tenant Invitation", row.name,
			{"status": "Expired", "invitation_token": None},
			update_modified=False,
		)
	for tenant in {row.tenant for row in stale}:
		recalculate_usage(tenant)
	frappe.db.commit()
	return {"expired": len(stale)}


def _assert_tenant_admin(tenant_name):
	"""Only this tenant's own admin, or your staff, may touch its invitations."""
	from a3_sola.api.entitlements import tenant_of

	user = frappe.session.user
	if user == "Administrator":
		return True
	staff_roles = {"Platform Admin", "Platform Tenant Manager", "System Manager"}
	if staff_roles & set(frappe.get_roles(user)):
		return True
	if tenant_of(user) == tenant_name and frappe.db.get_value("Tenant", tenant_name, "admin_user") == user:
		return True
	frappe.throw(
		_("Only the workspace administrator can manage invitations."),
		frappe.PermissionError,
		title=_("Not Permitted"),
	)


@frappe.whitelist()
def my_seats():
	"""What the tenant admin's own seats page shows."""
	from a3_sola.api.entitlements import tenant_of

	tenant_name = tenant_of()
	if not tenant_name:
		frappe.throw(_("This page is for workspace administrators."), frappe.PermissionError)
	_assert_tenant_admin(tenant_name)
	tenant = frappe.get_cached_doc("Tenant", tenant_name)
	usage = get_tenant_usage(tenant_name)
	return {
		"tenant_id": tenant.name,
		"tenant": tenant.tenant_name,
		"usage": usage,
		"users": frappe.get_all(
			"User", filters={"a3_sola_tenant": tenant_name},
			fields=["name as email", "full_name", "enabled"], order_by="creation asc",
		),
		"invitations": frappe.get_all(
			"Tenant Invitation",
			filters={"tenant": tenant_name},
			fields=["name", "invited_email", "invited_name", "status", "sent_on",
			        "token_expires_on", "resend_count"],
			order_by="creation desc", limit_page_length=100,
		),
	}
