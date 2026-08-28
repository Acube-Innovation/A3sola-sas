# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The provisioning steps, in reversibility order.

The order is the design. Everything cheap and undoable runs first; the irreversible steps
run last and only once everything before them has succeeded. That is not the same as being
atomic - ERPNext cannot cleanly delete a Company that has transactions, and creating a User
mutates auth state - and pretending otherwise is how a "rollback" ends up deleting the
wrong company. So there is a line in this file, and it means something:

    steps 01-08   reversible. A failure here rolls back and leaves the system as it was.
    ── point of no return ──
    steps 09-14   irreversible. A failure here stops, shouts, and waits for a human.

Adding a step is one class and one entry in ORDER. It is never an edit to a long function,
because a long function is how step ordering quietly stops matching the ordering somebody
documented.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from a3_sola.api.provisioning import blueprint as blueprint_api
from a3_sola.api.provisioning import identifiers
from a3_sola.api.settings import get_value

REGISTRY = {}


def register(cls):
	REGISTRY[cls.step_code] = cls
	return cls


class ProvisioningStep:
	step_code = ""
	step_name = ""
	sequence = 0
	is_reversible = True
	is_point_of_no_return = False
	is_mandatory = True

	def execute(self, context):
		raise NotImplementedError(f"{self.step_code} has no execute")

	def rollback(self, context, step_log):
		"""Undo what execute did. Only ever called for reversible steps."""
		return None


# ============================================================ reversible prefix
@register
class ValidatePayment(ProvisioningStep):
	step_code = "01_VALIDATE_PAYMENT"
	step_name = "Validate payment and entitlements"
	sequence = 10

	def execute(self, context):
		subscription = context.subscription
		order = _first_paid_order(subscription)
		if not order:
			frappe.throw(
				_("No paid Payment Order exists for this subscription, so there is nothing "
				  "to provision against."),
				title=_("Payment Not Confirmed"),
			)
		context.payment_order = order

		if not _webhook_confirmed(order):
			frappe.throw(
				_("The payment for {0} was confirmed by the browser callback only. "
				  "Provisioning waits for the gateway's own webhook - a callback is a hint, "
				  "and provisioning a tenant off a hint is how you give one away.").format(
					order.name
				),
				title=_("Awaiting Webhook Confirmation"),
			)

		if order.status != "Paid":
			frappe.throw(
				_("Payment Order {0} is {1}, not Paid.").format(order.name, order.status),
				title=_("Payment Not Confirmed"),
			)

		signup = None
		if order.subscription_signup:
			signup = frappe.get_doc("Subscription Signup", order.subscription_signup)
		elif subscription.subscription_signup:
			signup = frappe.get_doc("Subscription Signup", subscription.subscription_signup)
		if not signup:
			frappe.throw(
				_("This subscription has no signup, so there is no organisation to provision."),
				title=_("No Signup"),
			)
		if not cint(signup.is_email_verified):
			frappe.throw(
				_("The applicant's email address was never verified. Provisioning would "
				  "send the admin password link to an address nobody has proved they own."),
				title=_("Email Not Verified"),
			)
		context.signup = signup

		plan_name = signup.subscription_plan or subscription.subscription_plan
		if not plan_name or not frappe.db.exists("Subscription Plan", plan_name):
			frappe.throw(
				_("The subscription plan could not be resolved, so there are no "
				  "entitlements to provision from."),
				title=_("Plan Not Resolvable"),
			)
		context.snapshot_entitlements(plan_name, additional_users=cint(signup.additional_users))
		return {"created_doctype": "Payment Order", "created_name": order.name}


@register
class ReserveIdentifier(ProvisioningStep):
	step_code = "02_RESERVE_IDENTIFIER"
	step_name = "Reserve the tenant identifier"
	sequence = 20

	def execute(self, context):
		signup = context.signup
		code = identifiers.generate_code(signup.organisation_name or signup.full_name)
		identifiers.validate_code(code)
		context.artefacts["tenant_code"] = code
		context.job.db_set("current_step", self.step_code, update_modified=False)
		return {"created_doctype": "Tenant Code", "created_name": code}

	def rollback(self, context, step_log):
		# Nothing is written until step 03, so releasing the reservation is dropping it.
		context.artefacts.pop("tenant_code", None)


@register
class CreateTenantRecord(ProvisioningStep):
	step_code = "03_CREATE_TENANT_RECORD"
	step_name = "Create the tenant record"
	sequence = 30

	def execute(self, context):
		signup = context.signup
		entitlements = context.entitlements
		code = context.artefacts.get("tenant_code")

		tenant = frappe.new_doc("Tenant")
		# Frappe fills a field literally named `company` with the session's default
		# company. On a Tenant that is actively wrong: a brand new tenant has no company
		# until step 05 creates one, and inheriting the operator's own would make step 05
		# decide the workspace "already existed" and seed a customer's masters into
		# somebody else's ledger.
		tenant.company = None
		tenant.update(
			{
				"tenant_name": identifiers.sanitise_name(signup.organisation_name)
				or identifiers.sanitise_name(signup.full_name),
				"tenant_code": code,
				"status": "Provisioning",
				"platform_subscription": context.subscription.name,
				"subscription_signup": signup.name,
				"primary_contact_name": identifiers.sanitise_name(signup.full_name, 100),
				"primary_contact_email": (signup.work_email or "").strip().lower(),
				"primary_contact_phone": identifiers.sanitise_name(signup.phone, 20),
				"billing_email": (signup.work_email or "").strip().lower(),
				"city": identifiers.sanitise_name(signup.city, 60),
				"state": signup.state,
				"country": signup.country or get_value("provisioning_default_country"),
				"gstin": (signup.gstin or "").strip().upper() or None,
				# Snapshotted, never re-read from Settings later.
				"tenancy_strategy": get_value("tenancy_strategy") or "Multi Company",
				"company": None,
			}
		)
		if signup.state:
			from a3_sola.api import tax

			tenant.state_code = tax.state_code_for(signup.state)
		tenant.update(
			{key: entitlements[key] for key in (
				"subscription_plan", "plan_code", "included_users", "additional_users",
				"user_quota", "max_companies", "storage_limit_gb", "assigned_role_profile",
			)}
		)
		for row in entitlements["enabled_modules"]:
			tenant.append("enabled_modules", row)
		tenant.flags.ignore_permissions = True
		tenant.insert(ignore_permissions=True)
		tenant.submit()

		context.tenant = tenant
		context.job.db_set("tenant", tenant.name, update_modified=False)
		context.record(self.step_code, "Tenant", tenant.name)
		return {"created_doctype": "Tenant", "created_name": tenant.name}

	def rollback(self, context, step_log):
		name = step_log.created_name
		if not name or not frappe.db.exists("Tenant", name):
			return
		tenant = frappe.get_doc("Tenant", name)
		if tenant.company:
			frappe.throw(
				_("Tenant {0} already has a company and will not be deleted automatically.").format(name)
			)
		# The job points at the tenant, and Frappe refuses to cancel a document something
		# links to. Drop the link first - the job's own step log still records what was
		# created and then unwound, so nothing about the history is lost.
		if context.job:
			frappe.db.set_value("Provisioning Job", context.job.name, "tenant", None,
			                    update_modified=False)
			context.job.tenant = None
		frappe.db.set_value("Tenant", name, "docstatus", 2, update_modified=False)
		frappe.delete_doc("Tenant", name, force=True, ignore_permissions=True,
		                  ignore_on_trash=True)
		context.tenant = None


@register
class ResolveBlueprint(ProvisioningStep):
	step_code = "04_RESOLVE_BLUEPRINT"
	step_name = "Resolve the blueprint"
	sequence = 40

	def execute(self, context):
		name = blueprint_api.resolve_blueprint(context.entitlements.get("subscription_plan"))
		if not name:
			context.note(
				"No active Tenant Blueprint was found. The tenant will get its structural "
				"masters but nothing blueprint-driven."
			)
		context.blueprint = name
		context.job.db_set("blueprint", name, update_modified=False)
		if name:
			notes = frappe.db.get_value("Tenant Blueprint", name, "post_provision_notes")
			if notes and context.tenant:
				context.tenant.db_set("post_provision_notes", notes, update_modified=False)
		return {"created_doctype": "Tenant Blueprint", "created_name": name or ""}

	def rollback(self, context, step_log):
		context.blueprint = None
		if context.job:
			context.job.db_set("blueprint", None, update_modified=False)


@register
class CreateCompany(ProvisioningStep):
	step_code = "05_CREATE_COMPANY"
	step_name = "Create the company"
	sequence = 50

	def execute(self, context):
		return context.strategy.create_company(context)

	def rollback(self, context, step_log):
		return context.strategy.rollback_company(context, step_log)


@register
class CreateStructures(ProvisioningStep):
	step_code = "06_CREATE_STRUCTURES"
	step_name = "Create cost centres, warehouses and groups"
	sequence = 60

	def execute(self, context):
		return context.strategy.create_structures(context)

	def rollback(self, context, step_log):
		return context.strategy.rollback_structures(context, step_log)


@register
class SeedMasters(ProvisioningStep):
	step_code = "07_SEED_MASTERS"
	step_name = "Seed the module masters"
	sequence = 70

	def execute(self, context):
		return context.strategy.seed_masters(context)

	def rollback(self, context, step_log):
		return context.strategy.rollback_masters(context, step_log)


@register
class ApplyEntitlements(ProvisioningStep):
	step_code = "08_APPLY_ENTITLEMENTS"
	step_name = "Apply the entitlements"
	sequence = 80

	def execute(self, context):
		from a3_sola.api import entitlements as entitlements_api

		return entitlements_api.apply_to_tenant(context)

	def rollback(self, context, step_log):
		from a3_sola.api import entitlements as entitlements_api

		return entitlements_api.clear_applied(context)


# ══════════════════════════════ POINT OF NO RETURN ══════════════════════════════
# Everything below mutates auth state or sends mail. A failure past this line produces a
# loud, human-owned "Provisioned with Errors" and never a destructive cleanup.


@register
class CreateAdminUser(ProvisioningStep):
	step_code = "09_CREATE_ADMIN_USER"
	step_name = "Create the tenant administrator"
	sequence = 90
	is_reversible = False
	is_point_of_no_return = True

	def execute(self, context):
		return context.strategy.create_admin(context)


@register
class AssignPermissions(ProvisioningStep):
	step_code = "10_ASSIGN_PERMISSIONS"
	step_name = "Assign roles and user permissions"
	sequence = 100
	is_reversible = False

	def execute(self, context):
		from a3_sola.api import tenant_users

		return tenant_users.assign_admin_permissions(context)


@register
class CreateInvitations(ProvisioningStep):
	step_code = "11_CREATE_INVITATIONS"
	step_name = "Open the remaining seats"
	sequence = 110
	is_reversible = False
	is_mandatory = False

	def execute(self, context):
		from a3_sola.api import invitations

		return invitations.seed_for_tenant(context)


@register
class VerifyIsolation(ProvisioningStep):
	step_code = "12_VERIFY_ISOLATION"
	step_name = "Verify tenant isolation"
	sequence = 120
	is_reversible = False

	def execute(self, context):
		return context.strategy.verify_isolation(context)


@register
class SendWelcome(ProvisioningStep):
	step_code = "13_SEND_WELCOME"
	step_name = "Send the welcome and build the checklist"
	sequence = 130
	is_reversible = False
	is_mandatory = False

	def execute(self, context):
		from a3_sola.api import onboarding

		return onboarding.welcome(context)


@register
class Activate(ProvisioningStep):
	step_code = "14_ACTIVATE"
	step_name = "Activate the tenant"
	sequence = 140
	is_reversible = False

	def execute(self, context):
		from a3_sola.api import activation

		return activation.activate(context)


#: The order provisioning runs in. Adding a step means adding its class above and its code
#: here - and thinking about which side of the point-of-no-return line it belongs on.
ORDER = [
	"01_VALIDATE_PAYMENT",
	"02_RESERVE_IDENTIFIER",
	"03_CREATE_TENANT_RECORD",
	"04_RESOLVE_BLUEPRINT",
	"05_CREATE_COMPANY",
	"06_CREATE_STRUCTURES",
	"07_SEED_MASTERS",
	"08_APPLY_ENTITLEMENTS",
	"09_CREATE_ADMIN_USER",
	"10_ASSIGN_PERMISSIONS",
	"11_CREATE_INVITATIONS",
	"12_VERIFY_ISOLATION",
	"13_SEND_WELCOME",
	"14_ACTIVATE",
]


def steps():
	return [REGISTRY[code]() for code in ORDER]


def step_for(code):
	cls = REGISTRY.get(code)
	return cls() if cls else None


def first_irreversible_sequence():
	for code in ORDER:
		step = REGISTRY[code]
		if step.is_point_of_no_return:
			return step.sequence
	return None


# ------------------------------------------------------------------- helpers
def _first_paid_order(subscription):
	"""The subscription's first successful payment - the one that buys the workspace.

	Explicitly the FIRST, ordered by when it was paid. A renewal must never provision a
	second tenant, and reading "the paid order" without ordering would eventually pick one.
	"""
	rows = frappe.get_all(
		"Payment Order",
		filters={"platform_subscription": subscription.name, "status": "Paid", "docstatus": ["<", 2]},
		fields=["name", "paid_on"],
		order_by="paid_on asc, creation asc",
		limit=1,
	)
	if rows:
		return frappe.get_doc("Payment Order", rows[0].name)
	if subscription.subscription_signup:
		rows = frappe.get_all(
			"Payment Order",
			filters={"subscription_signup": subscription.subscription_signup, "status": "Paid"},
			fields=["name"],
			order_by="paid_on asc, creation asc",
			limit=1,
		)
		if rows:
			return frappe.get_doc("Payment Order", rows[0].name)
	return None


def _webhook_confirmed(order):
	"""Did the gateway itself tell us, or only the customer's browser?

	A checkout callback is signed, so it is not forgeable - but it is sent by a party with
	an interest in the answer, and it arrives before the money is settled. The webhook is
	the gateway's own statement. Provisioning waits for it.
	"""
	return bool(
		frappe.db.exists(
			"Payment Transaction",
			{
				"payment_order": order.name,
				"status": ["in", ["Captured", "Authorized"]],
				"verification_method": ["in", ["Webhook", "Gateway Fetch", "Manual Override"]],
			},
		)
	)


def is_first_payment(order):
	"""True when this order is the earliest paid one on its subscription."""
	if not order.platform_subscription:
		return True
	earlier = frappe.get_all(
		"Payment Order",
		filters={
			"platform_subscription": order.platform_subscription,
			"status": "Paid",
			"name": ["!=", order.name],
			"paid_on": ["<", order.paid_on or now_datetime()],
		},
		limit=1,
	)
	return not earlier
