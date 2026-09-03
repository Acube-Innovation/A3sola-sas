# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Defence in depth: a suspended tenant cannot slip through another door.

Disabling users is the primary mechanism and it is enough on its own for the desk. This
gate exists for everything that does not go through a login: an API key, a personal access
token, a session that was already open, a route that reads the user another way.

THE ONE RULE THAT MATTERS MORE THAN BLOCKING

A suspended tenant MUST still be able to reach the billing portal and pay. Locking a
customer out of the page that ends their suspension is the worst bug this phase could
ship, so the allowlist below is checked before anything else, and it has its own tests.
"""

import frappe
from frappe import _

from a3_sola.api.entitlements import INTERNAL_PLATFORM_ROLES, TENANT_FIELD

#: Paths a blocked tenant may always reach. Ordered by how badly it would hurt to get one
#: of them wrong.
ALWAYS_ALLOWED = (
	# 1. Paying. The entire point of the suspension is to be reversed by this.
	"/billing",
	"/api/method/a3_sola.api.payments",
	"/api/method/a3_sola.api.webhooks",
	"/payment-status",
	"/a3sola/checkout",
	"/a3sola/payment-status",
	# 2. Getting back in, and getting help.
	"/login",
	"/api/method/login",
	"/api/method/logout",
	"/update-password",
	"/api/method/frappe.core.doctype.user.user.reset_password",
	"/api/method/frappe.www.login",
	# 3. The machinery a browser needs to render either of the above.
	"/assets",
	"/files",
	"/api/method/frappe.client.get_js",
	"/api/method/frappe.realtime",
	"/socket.io",
	"/app/subscription-suspended",
)

#: Roles that belong to your own business. A holder is never gated, whatever a stray
#: tenant stamp says.
NEVER_GATED_ROLES = set(INTERNAL_PLATFORM_ROLES) | {"Administrator"}

CACHE_KEY = "a3s_user_gate"


def enforce():
	"""`before_request`. Cheap on every request, decisive on the few that matter."""
	request = getattr(frappe.local, "request", None)
	if not request:
		return
	user = frappe.session.user
	if user in ("Guest", "Administrator", None):
		return

	path = request.path or ""
	if _allowed(path):
		return

	state = gate_for(user)
	if state in (None, "Full", "Banner"):
		return
	if state == "Read Only":
		# Reading is never blocked. The write block is enforced at the document, not the
		# request, so a tenant can still open, search, report and print.
		frappe.local.a3s_read_only = True
		return

	_refuse(state)


def gate_for(user):
	"""This user's access gate, from a single cached lookup.

	Cached per user in a hash that any state change clears, because a restored customer
	who stays locked out until a cache expires has not been restored.
	"""
	if not user or user in ("Guest", "Administrator"):
		return "Full"
	cached = frappe.cache().hget(CACHE_KEY, user)
	if cached is not None:
		return cached

	state = _resolve(user)
	frappe.cache().hset(CACHE_KEY, user, state)
	return state


def _resolve(user):
	tenant = frappe.db.get_value("User", user, TENANT_FIELD)
	if not tenant:
		# Internal staff carry no stamp and are never gated.
		return "Full"
	if set(frappe.get_roles(user)) & NEVER_GATED_ROLES:
		return "Full"
	return frappe.db.get_value("Tenant", tenant, "access_gate") or "Full"


def _allowed(path):
	return any(path.startswith(prefix) for prefix in ALWAYS_ALLOWED)


def _refuse(state):
	"""A branded message with a way out, not a bare permission error."""
	from frappe.utils import get_url

	frappe.throw(
		_("Access to A3 Sola is paused for your organisation because of an unpaid "
		  "invoice. Nothing has been deleted - your data and your team's permissions are "
		  "exactly as you left them, and access returns the moment payment clears. "
		  "Settle it at {0}.").format(f"{get_url()}/billing"),
		frappe.PermissionError,
		title=_("Subscription Paused"),
	)


def block_writes(doc, method=None):
	"""Read Only: reading and reporting stay open, changing anything does not.

	Registered on `*` so a doctype added later cannot slip past it. Deliberately narrow -
	it refuses submit, cancel, amend and update-after-submit, and leaves ordinary reads,
	reports and printing alone, so a restricted tenant can still retrieve their own data
	and print an invoice.
	"""
	user = frappe.session.user
	if user in ("Administrator", "Guest") or frappe.flags.in_install or frappe.flags.in_migrate:
		return
	if gate_for(user) != "Read Only":
		return
	frappe.throw(
		_("Your subscription is past due, so A3 Sola is read-only for now. You can still "
		  "open, search, report and print everything - you cannot submit or change "
		  "documents until the balance is settled."),
		frappe.PermissionError,
		title=_("Read Only"),
	)


def on_session_creation(login_manager=None):
	"""Second gate, at login. Cheaper than the request gate and catches the common case."""
	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		return
	if gate_for(user) == "Blocked":
		_refuse("Blocked")


def invalidate(user=None, tenant=None):
	"""Drop cached gates. Called by every access change."""
	if user:
		frappe.cache().hdel(CACHE_KEY, user)
		return
	if tenant:
		for name in frappe.get_all("User", filters={TENANT_FIELD: tenant}, pluck="name"):
			frappe.cache().hdel(CACHE_KEY, name)
		return
	frappe.cache().delete_value(CACHE_KEY)
