# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One of everything: the smallest dataset that shows the whole product working.

The demo generators build a *scenario* - a dozen leads at different stages, a job stuck at
DISCOM feasibility, another whose generation is sliding. That is right for a demo and wrong
for a starter dataset, where the point is to open a fresh database and see one real record
of each kind, joined up end to end, with nothing to wade through.

So this creates exactly one: one company with its masters, one user, one lead, one
consumer, one survey, one estimate, one eligibility check, one proposal, one installation,
one project with its billing plan and O&M contract, one signup, one subscription with its
order, invoice and mandate, one tenant with its provisioning job and invitation.

Every record is prefixed `Starter` or tagged, so it is obvious what came from here and
`teardown()` can take it all out again.

Idempotent throughout: running it twice creates nothing the second time. That matters
because it is wired to a patch, and a patch runs on every migrate.
"""

import frappe
from frappe.utils import add_days, add_months, cint, flt, getdate, now_datetime, today

TAG = "Starter"
COMPANY = "Starter Solar EPC"
COMPANY_ABBR = "SSE"
USER_EMAIL = "starter.engineer@example.com"

#: The starter user's password. Deliberately known and deliberately printed.
#:
#: Everywhere else in this product no password is ever set by the system - a tenant admin
#: and every invited user get a single-use reset link, because a system that can set a
#: password is a system whose logs and backups contain passwords.
#:
#: This one is the exception, and the reason is narrow: a starter dataset exists to be
#: logged into. A sample user nobody can sign in as is not sample data, it is a puzzle. The
#: exception is safe to make because this dataset never appears unless somebody asks for it
#: by name - `bench execute`, or `a3s_seed_starter_data` in the site config - and because
#: the account is inert: no Platform role, no tenant stamp, one company.
#:
#: It is still a real credential. Change it before anything faces the internet, and do not
#: enable the starter patch on a production site.
USER_PASSWORD = "a3sola-starter"

#: One login that can do every job. The app defines a role per job - a survey engineer who
#: sees no cost, a sales executive who sees no margin - and that separation is the point of
#: the permission model in a real deployment. For a starter dataset it is friction: nine
#: passwords to walk one pipeline. So this user holds the union of every operational role
#: and can drive the whole chain end to end on their own.
#:
#: What that costs, said plainly: this account cannot demonstrate the separation. If you
#: want to see that a Survey Engineer genuinely cannot read a cost figure, make a second
#: user with only the `Solar Survey` profile - the roles below are exactly the profiles the
#: app already ships, so any one of them can be granted on its own.
ALL_ROLE_PROFILES = (
	"Solar Tenant Administrator",   # company admin: settings, approvals, account mapping
	"Solar Sales Management",       # leads, consumers, proposals, pricing approval
	"Solar Survey",                 # site surveys including the lender EHS block
	"Solar Design",                 # design estimates and eligibility checks
	"Solar Operations Management",  # the nineteen stages, work orders, QC
	"Solar Documentation",          # KSEB portal, statutory fees, subsidy claims, documents
	"Solar Projects Management",    # costing, billing plans, statutory recovery
	"Solar Service Management",     # O&M contracts, visits, tickets, warranty
	"Solar Field Crew",             # the technician view of a work order
)

#: Retired. Sites seeded by an earlier version have these; `_retire_team_users` removes
#: them so one login is genuinely one login.
RETIRED_TEAM_DOMAIN = "@startersolar.example"

#: The chain is dated backwards from today, because a job cannot be ordered this morning
#: and commissioned last week. The project ERPNext opens on commissioning validates that
#: its end date follows its start, and the start is the order date.
SURVEYED_DAYS_AGO = 130
ESTIMATED_DAYS_AGO = 126
PROPOSED_DAYS_AGO = 124
QUOTED_DAYS_AGO = 122
ORDERED_DAYS_AGO = 120


def _dated(company, days_ago):
	"""`days_ago` before today, but never before the statutory fees took effect.

	The design estimate quotes the DISCOM's fee schedule as it stood on the estimate
	date, and refuses outright if no schedule was in force then. On a site set up this
	financial year the schedule starts on the first of April, so how far back the chain
	can be dated depends on when the site was set up - it is read, not assumed.
	"""
	wanted = getdate(add_days(today(), -days_ago))
	floor = frappe.db.get_value(
		"Statutory Fee Schedule",
		{"company": company, "is_active": 1},
		"effective_from",
		order_by="effective_from desc",
	)
	return max(wanted, getdate(floor)) if floor else wanted


def _log(message):
	print(f"  starter: {message}")


#: (key, doctype, builder). Order is dependency order - each step may use what the ones
#: before it produced, and nothing else.
STEPS = (
	("user", "User", lambda ctx: _user()),

	("lead", "Lead", lambda ctx: _lead(ctx["company"])),
	("consumer", "Solar Consumer", lambda ctx: _consumer(ctx["company"], ctx["lead"])),
	("customer", "Customer", lambda ctx: _customer(ctx["company"], ctx["consumer"])),
	("site_survey", "Site Survey", lambda ctx: _survey(ctx["company"], ctx["consumer"])),
	("design_estimate", "Solar Design Estimate",
		lambda ctx: _estimate(ctx["company"], ctx["consumer"], ctx["site_survey"])),
	("eligibility_check", "Subsidy Eligibility Check",
		lambda ctx: _eligibility(ctx["company"], ctx["consumer"], ctx["design_estimate"])),
	("proposal", "Solar Proposal",
		lambda ctx: _proposal(ctx["company"], ctx["design_estimate"], ctx["lead"], ctx["consumer"])),
	("quotation", "Quotation", lambda ctx: _quotation(
		ctx["company"], ctx["consumer"], ctx["design_estimate"],
		ctx["eligibility_check"], ctx["proposal"], ctx["customer"])),
	("sales_order", "Sales Order", lambda ctx: _sales_order(
		ctx["company"], ctx["customer"], ctx["quotation"])),
	("installation", "Solar Installation",
		lambda ctx: _installation(ctx["company"], ctx["design_estimate"], ctx["sales_order"])),
	("signup", "Subscription Signup", lambda ctx: _signup()),
	("demo_request", "Demo Request", lambda ctx: _demo_request()),
	("subscription", "Platform Subscription", lambda ctx: _subscription(ctx["signup"])),
	("tenant", "Tenant", lambda ctx: _tenant(ctx["company"], ctx["subscription"], ctx["signup"])),
)


def install(company=None):
	"""Build the starter dataset. Returns only what actually exists afterwards.

	Two rules, both learned the hard way:

	**Commit after every step.** A rollback inside one step otherwise discards every step
	before it, because they are all still in the same transaction. That produced a run
	which reported thirteen records and left five.

	**Verify before reporting.** Each name is read back from the database before it goes in
	the result. A seeder that claims records it did not create is worse than one that
	fails, and this one is built to be pointed at somebody else's database.
	"""
	frappe.flags.in_demo = True
	frappe.flags.a3s_demo_limit = 1
	made, failed, chain = {}, {}, {}
	try:
		_retire_team_users()
		context = {"company": company or _company()}
		made["company"] = context["company"]
		frappe.db.commit()

		for key, doctype, build in STEPS:
			try:
				name = build(context)
				frappe.db.commit()
			except Exception as exception:
				frappe.db.rollback()
				failed[key] = str(exception)[:200]
				context[key] = None
				continue
			# Read it back. If the step rolled itself back internally, the name it
			# returned points at nothing.
			if name and frappe.db.exists(doctype, name):
				context[key] = name
				made[key] = name
			else:
				context[key] = None
				failed[key] = "the record was not there afterwards"
		# The spine above is one record of each thing a person creates by hand. The rest of
		# the app's documents are produced by *doing the work* - advancing an installation
		# through its stages, commissioning it, taking a payment, provisioning a tenant -
		# so they are built by driving those flows rather than by fabricating rows. The
		# generators are already tested and already idempotent; run at a limit of one they
		# produce exactly one of each.
		# One job, taken from here to the last document it produces. This runs before the
		# generators below so the starter's own installation is the first commissioned one
		# on the site, and the reports that read "the earliest project" read this one.
		chain = _drive_chain(context)
		chain.update(_drive_platform_chain(context))
		frappe.db.commit()

		for label, build in (
			("operations", _drive_operations),
			("projects", _drive_projects),
			("payments", _drive_payments),
			("provisioning", _drive_provisioning),
		):
			try:
				build(context["company"])
				frappe.db.commit()
			except Exception as exception:
				frappe.db.rollback()
				failed[label] = str(exception)[:200]
	finally:
		frappe.flags.in_demo = False
		frappe.flags.a3s_demo_limit = None

	broken = {k: v for k, v in (chain or {}).items() if str(v).startswith("FAILED")}
	made["chain"] = {k: v for k, v in (chain or {}).items() if not str(v).startswith("FAILED")}
	if broken:
		failed.update(broken)

	_log("created " + ", ".join(f"{k}={v}" for k, v in made.items() if k != "chain"))
	_log("chain from the lead: " + ", ".join(f"{k}={v}" for k, v in made["chain"].items()))
	if failed:
		_log("NOT created: " + ", ".join(f"{k} ({why})" for k, why in failed.items()))
	coverage = report_coverage(made.get("company"))
	_log(f"documents with at least one record: {coverage['covered']} of {coverage['total']}")
	if coverage["missing"]:
		_log("no record yet for: " + ", ".join(coverage["missing"]))
	_log(f"sign in at /app as  {USER_EMAIL}  /  {USER_PASSWORD}")
	return {
		"created": made,
		"failed": failed,
		"coverage": coverage,
		"login": {"user": USER_EMAIL, "password": USER_PASSWORD},
	}


# ------------------------------------------------------------------ the chain
def _chain_stages(installation):
	"""The installation's own stage codes, in order.

	Not a fixed list: the stage template is resolved from the scheme, the system type and
	the consumer category, so two jobs at the same company can carry different chains. A
	hardcoded list quietly stops at the first code the template does not have.
	"""
	return [row.stage_code for row in installation.stages]


def _advance_all(installation):
	"""Walk the installation through every stage its template defines.

	The demo's `_advance` stops at the first stage that refuses, which is right for it -
	it is building jobs that are deliberately stuck. Here the point is to reach the end,
	and a stage can refuse for reasons that say nothing about the ones after it: a small
	array skips the electrical-inspector stage entirely, and stopping there would leave
	the job three stages short of commissioning. So every stage is attempted, and the
	ones that decline are stepped over.
	"""
	from a3_sola.api import stages
	from a3_sola.demo.generate_operations_demo import _evidence

	doc = frappe.get_doc("Solar Installation", installation)
	reached = []
	for code in _chain_stages(doc):
		frappe.db.savepoint("starter_stage")
		try:
			_evidence(doc, code)
			stages.advance_stage(doc.name, code, actual_date=today())
			reached.append(code)
		except Exception:
			frappe.db.rollback(save_point="starter_stage")
	return reached

CHAIN_TICKET = ("Low Generation", "Major", "Output down since the roof was cleaned.", "No Fault Found")


def _drive_chain(context):
	"""Take the starter's own installation the whole way, and nothing else.

	The point of this dataset is one job that can be walked from the Lead to the last
	document without ever landing on an unrelated record. The demo generators build
	breadth - several jobs in several states - but each of them picks its own consumer,
	so following a link out of the starter Lead would arrive somewhere else. This builds
	depth on the single job instead, and every step here is guarded, so it can run again
	on a database that already has some of it.

	Each stage is committed on its own. A step that fails leaves everything before it
	standing rather than unwinding the chain back to the Lead.
	"""
	from a3_sola.demo import generate_operations_demo as ops
	from a3_sola.demo import generate_projects_demo as pj

	company = context["company"]
	name = context.get("installation")
	if not name:
		return {"installation": None}

	built = {}

	def step(key, run):
		"""Run one link of the chain. A failure costs that link, not the chain."""
		try:
			value = run()
			frappe.db.commit()
			built[key] = value if isinstance(value, str) else "built"
		except Exception as exception:
			frappe.db.rollback()
			built[key] = f"FAILED: {str(exception)[:120]}"

	installation = frappe.get_doc("Solar Installation", name)

	# --- operations: the job is built, inspected and energised ---------------
	step("serials", lambda: ops._serials(installation) and None)
	step("fee_payment", lambda: ops._fee_payment(company, installation))
	step("portal_application", lambda: ops._raise_query(company, installation.name))
	step("loan_application", lambda: ops._make_loan(company, installation, disbursed=True))
	step("stages", lambda: ",".join(_advance_all(name)))
	installation = frappe.get_doc("Solar Installation", name)
	step("order_date", lambda: _order_predates_commissioning(name))
	step("commissioning", lambda: ops._commission(company, installation))
	# Whatever was waiting on the commissioning report can run now.
	step("stages_after_commissioning", lambda: ",".join(_advance_all(name)))

	# The snag comes after commissioning on purpose: an open major snag blocks the
	# project close-out, and a starter dataset that deadlocks itself is no use.
	step("snag", lambda: ops._snag(company, installation, "Minor", category="Cabling"))

	# --- projects: delivery, billing and the service history -----------------
	project = frappe.db.get_value(
		"Project", {"solar_installation": installation.name, "status": ["!=", "Cancelled"]}, "name"
	)
	if not project:
		built["project"] = "FAILED: commissioning did not open a project"
		return built

	built["project"] = project
	project_doc = frappe.get_doc("Project", project)
	contract = pj._contract(project_doc)
	built["billing_plan"] = (pj._plan(project_doc) or frappe._dict()).get("name") or "none"
	built["om_contract"] = contract.name if contract else "none"

	step("work_orders", lambda: pj._book_costs(company, project_doc))
	# Only now is there a work order for the snag to be rectified under.
	step("snag_rectification", lambda: _link_snag_to_work_order(installation.name))
	step("billing", lambda: pj._bill(project_doc, through=2))
	# No milestone invoice, deliberately. Drafting one needs an active GST valuation
	# rule with its items and tax templates attached, and the app ships that rule
	# inactive and empty because the valuation basis for a composite solar supply is
	# the client's CA's decision. The milestones are triggered and the plan's
	# Connections panel carries the + Sales Invoice button; raising it is the one step
	# of this chain a person has to take, once the treatment is confirmed.
	built["sales_invoice"] = "awaiting the GST valuation decision"
	step("subsidy_claim", lambda: pj._funded_gap_claim(company, project_doc, recovered=True))
	step("fee_recovery", lambda: _recover_fees(company, installation.name, project))

	if contract:
		step("om_visit", lambda: pj._visits(company, contract, done=2))
		step("service_ticket", lambda: pj._tickets(company, contract, (CHAIN_TICKET,)))
		step("warranty_claim", lambda: pj._warranty(company, contract, status="Replaced"))
		step("generation_reading", lambda: pj._readings(company, contract, [102, 99, 97, 95]))
		step("ticket_from_snag", lambda: _link_ticket_to_snag(installation.name, contract.name))

	step("costs", lambda: _recalculate(project))
	return built


def _drive_platform_chain(context):
	"""The other spine: one signup, taken to a live tenant with users invited.

	Same rule as the job chain - one of each, all on the same signup, so the
	Connections panel walks from the signup to the invitation without ever stepping
	onto an unrelated subscription.
	"""
	from a3_sola.demo import generate_payments_demo as pay

	built = {}
	signup = context.get("signup")
	subscription = context.get("subscription")
	tenant = context.get("tenant")
	if not subscription:
		return built

	def step(key, run):
		try:
			value = run()
			frappe.db.commit()
			built[key] = getattr(value, "name", value) if value else "none"
		except Exception as exception:
			frappe.db.rollback()
			built[key] = f"FAILED: {str(exception)[:120]}"

	doc = frappe.get_doc("Platform Subscription", subscription)
	company = context["company"]

	step("payment_mandate", lambda: pay._mandate_for(doc, "starter"))

	order = frappe.db.get_value(
		"Payment Order", {"platform_subscription": subscription, "docstatus": ["<", 2]}, "name"
	)
	if not order:
		step("payment_order", lambda: pay._order(doc, doc.current_period_start, doc.current_period_end, company))
		order = frappe.db.get_value(
			"Payment Order", {"platform_subscription": subscription, "docstatus": ["<", 2]}, "name"
		)
	else:
		built["payment_order"] = order

	if order:
		# The order is raised against the subscription; naming the signup as well is
		# what lets the Connections panel walk from the signup straight to it.
		if signup and not frappe.db.get_value("Payment Order", order, "subscription_signup"):
			frappe.db.set_value("Payment Order", order, "subscription_signup", signup, update_modified=False)
		order_doc = frappe.get_doc("Payment Order", order)
		if not frappe.db.exists("Payment Transaction", {"payment_order": order}):
			step("payment_transaction", lambda: pay._transaction(order_doc))
		if not frappe.db.exists("Subscription Invoice", {"payment_order": order}):
			step("subscription_invoice", lambda: pay._invoice(doc, order_doc, company))

	if tenant:
		step("provisioning_job", lambda: _provisioning_job(tenant, subscription, signup, order))
	return built


def _provisioning_job(tenant, subscription, signup, payment_order=None):
	"""The completed run that produced the tenant.

	Written rather than executed: the orchestrator would provision a second company,
	and the starter dataset deliberately has one. Every step is recorded as it actually
	ran for this tenant, so the job reads as the history of the record beside it.
	"""
	existing = frappe.db.get_value("Provisioning Job", {"tenant": tenant, "docstatus": ["<", 2]}, "name")
	if existing:
		return existing

	from a3_sola.api.provisioning import steps as step_module

	job = frappe.new_doc("Provisioning Job")
	job.update(
		{
			"tenant": tenant,
			"platform_subscription": subscription,
			"subscription_signup": signup,
			"payment_order": payment_order,
			"idempotency_key": f"starter::{tenant}",
			"triggered_by": "Payment Webhook",
			"triggered_on": now_datetime(),
			"started_on": now_datetime(),
			"completed_on": now_datetime(),
			"status": "Completed",
			"tenancy_strategy": "Multi Company",
			"attempt_number": 1,
			"duration_seconds": 11.4,
			"point_of_no_return_passed": 1,
			"progress_percent": 100,
		}
	)
	for step in step_module.steps():
		job.append(
			"steps",
			{
				"step_code": step.step_code,
				"step_name": step.step_name,
				"sequence": step.sequence,
				"is_reversible": cint(step.is_reversible),
				"status": "Completed",
				"duration_seconds": 0.8,
				"started_on": now_datetime(),
				"completed_on": now_datetime(),
			},
		)
	job.flags.ignore_permissions = True
	job.flags.ignore_mandatory = True
	job.insert(ignore_permissions=True)
	job.submit()
	frappe.db.set_value("Tenant", tenant, "provisioning_job", job.name, update_modified=False)
	return job.name




def _order_predates_commissioning(installation):
	"""Commissioning is recorded ten days ago, so the order cannot be newer than that.

	On a site whose statutory fee schedule only starts today the whole chain is dated
	today, and the project ERPNext opens would then end before it began. Pulling the
	order date back is the honest correction: the job was ordered first.
	"""
	ordered = frappe.db.get_value("Solar Installation", installation, "order_date")
	latest = getdate(add_days(today(), -11))
	if ordered and getdate(ordered) <= latest:
		return str(ordered)
	frappe.db.set_value("Solar Installation", installation, "order_date", latest, update_modified=False)
	return str(latest)


def _link_snag_to_work_order(installation):
	"""Point the snag at the work order that will put it right."""
	snag = frappe.db.get_value("Installation Snag", {"solar_installation": installation}, "name")
	order = frappe.db.get_value("Installation Work Order", {"solar_installation": installation}, "name")
	if not (snag and order):
		return "none"
	if frappe.db.get_value("Installation Snag", snag, "rectification_work_order"):
		return snag
	frappe.db.set_value("Installation Snag", snag, "rectification_work_order", order, update_modified=False)
	return snag


def _link_ticket_to_snag(installation, contract):
	"""The service ticket the snag turned into once the job was live."""
	snag = frappe.db.get_value("Installation Snag", {"solar_installation": installation}, "name")
	ticket = frappe.db.get_value("Service Ticket", {"om_contract": contract}, "name")
	if not (snag and ticket):
		return "none"
	if frappe.db.get_value("Service Ticket", ticket, "installation_snag"):
		return ticket
	frappe.db.set_value("Service Ticket", ticket, "installation_snag", snag, update_modified=False)
	return ticket


def _recover_fees(company, installation, project):
	"""The recovery record for the statutory fee the company fronted.

	The fee is paid long before there is a project to recover it against, so the link is
	made here rather than at payment time.
	"""
	payment = frappe.db.get_value(
		"Statutory Fee Payment", {"solar_installation": installation, "docstatus": 1}, "name"
	)
	if not payment:
		return "none"
	from a3_sola.api import recovery

	return recovery.sync_from_payment(frappe.get_doc("Statutory Fee Payment", payment), project)


def _recalculate(project):
	from a3_sola.api import costing

	costing.recalculate_project_costs(project)
	return project


# ------------------------------------------------------- doing the actual work
def _drive_operations(company):
	"""One installation taken through its stages, which is what creates the rest.

	A work order, a portal application, a fee payment, a subsidy claim, a snag, a loan, a
	net-metering agreement and a commissioning report are all consequences of moving a job
	forward. Fabricating them as rows would produce records that exist but do not hang
	together - a commissioning report for a job that was never installed.
	"""
	from a3_sola.demo import generate_operations_demo

	generate_operations_demo.run(company)


def _drive_projects(company):
	"""Commissioning creates the project, the billing plan and the O&M contract."""
	from a3_sola.demo import generate_projects_demo

	generate_projects_demo.run(company)


def _drive_payments(company):
	"""A subscription with its order, transaction, invoice, mandate and settlement."""
	from a3_sola.demo import generate_payments_demo

	generate_payments_demo.run(company)


def _drive_provisioning(company):
	"""A tenant with its provisioning job, invitation and isolation results."""
	from a3_sola.demo import generate_provisioning_demo

	generate_provisioning_demo.run(company)


def report_coverage(company=None):
	"""Which of the app's documents have at least one record, and which do not.

	Reported rather than asserted. Some documents only exist once something has genuinely
	happened - a refund needs a payment to reverse, a warranty claim needs a failed
	component - and a starter dataset that faked those would be teaching the wrong shape.
	Saying plainly what is empty is more useful than filling it with fiction.
	"""
	modules = ("Solar CRM", "Solar Operations", "Solar Projects", "Platform")
	covered, missing = [], []
	for doctype in frappe.get_all(
		"DocType", filters={"module": ["in", modules]}, pluck="name"
	):
		meta = frappe.get_meta(doctype)
		if meta.istable or meta.issingle:
			continue
		if frappe.db.count(doctype):
			covered.append(doctype)
		else:
			missing.append(doctype)
	return {
		"total": len(covered) + len(missing),
		"covered": len(covered),
		"missing": sorted(missing),
	}


# ---------------------------------------------------------------- foundation
def _company():
	"""One company, with a chart of accounts, a cost centre and every module master."""
	if frappe.db.exists("Company", COMPANY):
		company = COMPANY
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": COMPANY,
				"abbr": COMPANY_ABBR,
				"default_currency": "INR",
				"country": "India",
				"chart_of_accounts": "Standard",
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
		company = doc.name
		frappe.db.commit()

	# Without a default cost centre every Profit and Loss posting fails at submit, which
	# turns the first invoice anybody tries into a support question.
	if not frappe.db.get_value("Company", company, "cost_center"):
		try:
			frappe.get_doc("Company", company).create_default_cost_center()
		except Exception:
			frappe.db.rollback()
		main = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
		if main:
			frappe.db.set_value(
				"Company", company, {"cost_center": main, "round_off_cost_center": main},
				update_modified=False,
			)

	from a3_sola.setup import install as installer

	installer.seed_masters(company)
	frappe.db.commit()
	return company


#: The modules this user keeps. Everything else on the instance is hidden from them.
#:
#: A solar EPC administrator needs their own three modules plus the ERPNext ones the
#: workflow genuinely reaches into - invoicing, materials, the sales documents a proposal
#: becomes, and Project, which commissioning creates. They do not need Manufacturing,
#: Assets, Website, Integrations or the Build tools, and they must not have Platform:
#: that is the SaaS business's own data, not the customer's.
#: The only modules any of these users keeps. Everything a solar EPC does is reachable from
#: the three A3 Sola workspaces, so nothing else needs to be in the sidebar.
#:
#: The ERPNext documents the workflow genuinely reaches - Quotation, Sales Order, Item,
#: Warehouse, Stock Entry, Sales Invoice, Payment Entry, Journal Entry - are linked from
#: inside those workspaces instead. Blocking a module hides its workspace and removes no
#: permission, so opening one of those documents from an A3 Sola card works exactly as
#: before; there is simply one way in rather than two.
KEEP_MODULES = ("Solar CRM", "Solar Operations", "Solar Projects")

#: Deliberately absent from the list above, and why - so the next person does not add them
#: back thinking it was an oversight:
#:
#:   Core, Desk    the Users, Build and Welcome workspaces. Administration of the instance,
#:                 not of a company. Blocking a module hides the workspace and nothing
#:                 else - no permission is removed - so this costs the user nothing.
#:   CRM, Projects ERPNext's own versions of surfaces Solar CRM and Solar Projects already
#:                 provide. Two doors to the same room is worse than one.
#:   Platform      the SaaS business's own data. Never, for a customer-facing user.

#: Never, for a customer-facing user. Blocking is belt to the workspace's braces: the
#: workspace is role-gated too, and the doctypes refuse the records outright.
ALWAYS_BLOCK = ("Platform",)


def _user():
	"""The administrator of this company - not a junior with four roles.

	Given the tenant-administrator profile a provisioned customer's admin gets, confined to
	their own company by a User Permission, and with every module they have no business
	seeing hidden. Before this they held four operational roles and saw every workspace on
	the instance, Platform included.
	"""
	if frappe.db.exists("User", USER_EMAIL):
		_grant_company_admin(USER_EMAIL)
		return USER_EMAIL
	roles = set()
	for profile in ALL_ROLE_PROFILES:
		if frappe.db.exists("Role Profile", profile):
			roles |= {r.role for r in frappe.get_cached_doc("Role Profile", profile).roles}
	roles = sorted(r for r in roles if frappe.db.exists("Role", r))
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": USER_EMAIL,
			"first_name": "Starter",
			"last_name": "Engineer",
			"user_type": "System User",
			"enabled": 1,
			"send_welcome_email": 0,
			"roles": [{"role": r} for r in roles],
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.no_welcome_mail = True
	doc.insert(ignore_permissions=True)

	# See USER_PASSWORD: the one account in this product with a password the system knows.
	from frappe.utils.password import update_password

	update_password(doc.name, USER_PASSWORD)
	_grant_company_admin(doc.name)
	_log(f"sign in as {doc.name} / {USER_PASSWORD}")
	return doc.name


def _retire_team_users():
	"""Remove the per-role users an earlier version of this seeding created.

	They were nine logins for one pipeline. Everything they could do, the single user can.
	"""
	removed = []
	for email in frappe.get_all(
		"User", filters={"email": ["like", f"%{RETIRED_TEAM_DOMAIN}"]}, pluck="name"
	):
		try:
			frappe.db.delete("User Permission", {"user": email})
			frappe.db.delete("DefaultValue", {"parent": email})
			frappe.delete_doc("User", email, force=True, ignore_permissions=True,
			                  ignore_on_trash=True)
			removed.append(email)
		except Exception:
			frappe.db.rollback()
	if removed:
		frappe.db.commit()
		_log(f"retired {len(removed)} per-role user(s) - one login now does everything")
	return removed


def _grant_company_admin(email):
	"""Confine the user to this company and hide the modules they do not need.

	Idempotent, and applied on every run rather than only at creation - a user made by an
	earlier version of this seeding would otherwise keep the four junior roles and the
	full module list it gave them.
	"""
	wanted = set()
	for profile in ALL_ROLE_PROFILES:
		if frappe.db.exists("Role Profile", profile):
			wanted |= {r.role for r in frappe.get_cached_doc("Role Profile", profile).roles}
	if wanted:
		user = frappe.get_doc("User", email)
		held = {r.role for r in user.roles}
		for role in sorted(wanted - held):
			if frappe.db.exists("Role", role):
				user.append("roles", {"role": role})

		# Blocked modules decide what appears in the sidebar. Recomputed from scratch each
		# time so the list follows KEEP_MODULES rather than accumulating.
		user.set("block_modules", [])
		for module in sorted(frappe.get_all("Module Def", pluck="name")):
			if module in ALWAYS_BLOCK or module not in KEEP_MODULES:
				user.append("block_modules", {"module": module})

		user.flags.ignore_permissions = True
		user.flags.a3s_skip_quota = True
		user.save(ignore_permissions=True)

	# One company, and the permission that confines every query to it.
	if frappe.db.exists("Company", COMPANY):
		if not frappe.db.exists(
			"User Permission", {"user": email, "allow": "Company", "for_value": COMPANY}
		):
			permission = frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": COMPANY,
					"apply_to_all_doctypes": 1,
					"is_default": 1,
				}
			)
			permission.flags.ignore_permissions = True
			permission.insert(ignore_permissions=True)
		# `company`, scrubbed - Frappe reads the default under the scrubbed key and falls
		# back to the site-wide one when it is missing. See tenant_users._set_default_company.
		frappe.db.delete("DefaultValue", {"parent": email, "defkey": ["in", ["Company", "company"]]})
		frappe.defaults.set_user_default("company", COMPANY, email)
		frappe.clear_cache(user=email)


def _master(doctype, field, value, company):
	return frappe.db.get_value(doctype, {field: value, "company": company}, "name") or \
		frappe.db.get_value(doctype, {"company": company}, "name")


def _address(city="Ernakulam"):
	title = f"{TAG} Site {city}"
	existing = frappe.db.get_value("Address", {"address_title": title}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Address",
			"address_title": title,
			"address_type": "Billing",
			"address_line1": "Door 14/221, Market Road",
			"city": city,
			"state": "Kerala",
			"country": "India",
			"pincode": "683572",
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


# ------------------------------------------------------------------- phase 1
def _lead(company):
	name = f"{TAG} Enquiry"
	existing = frappe.db.get_value("Lead", {"lead_name": name}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Lead",
			"lead_name": name,
			"first_name": "Starter",
			"last_name": "Enquiry",
			"company_name": name,
			"mobile_no": "9847000101",
			"email_id": "starter.lead@example.com",
			"company": company,
			"status": "Open",
			"source": "Walk In",
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _consumer(company, lead=None):
	"""The consumer the lead converted into.

	Both ends of the link are written, the way the Create Solar Consumer button on the
	Lead writes them: the consumer carries `lead`, the lead carries `solar_consumer`.
	One without the other leaves the Connections panel on the Lead empty.
	"""
	name = f"{TAG} Consumer"
	existing = frappe.db.get_value(
		"Solar Consumer", {"consumer_name": name, "company": company}, "name"
	)
	if existing:
		_link_lead(lead, existing)
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Solar Consumer",
			"company": company,
			"consumer_name": name,
			"consumer_category": "Residential",
			"discom": _master("DISCOM", "discom_name", "KSEB", company),
			"discom_section": _master("DISCOM Section", "section_name", "Athani", company),
			"consumer_number": "1156500000001",
			"tariff_category": "LT-1/Single",
			"connection_type": "Single Phase",
			"connected_load_watts": 3000,
			"sanctioned_load_kw": 5,
			"avg_consumption_units": 320,
			"billing_frequency": "Bimonthly",
			"installation_address": _address(),
			"roof_type": _master("Roof Type", "roof_type", "RCC Flat", company),
			"local_body_type": "Panchayat",
			"local_body_name": "Nedumbassery",
			"village": "Athani",
			"survey_number": "142/3",
			"has_availed_prior_subsidy": 0,
			"bank_account_holder_name": name,
			"bank_account_no": "028901000123456",
			"bank_name": "ICICI Bank",
			"bank_branch": "Aluva",
			"bank_ifsc_code": "ICIC0000289",
			"lead": lead,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	_link_lead(lead, doc.name)
	return doc.name


def _link_lead(lead, consumer):
	"""Point the lead at its consumer. Read-only field, so it is set directly."""
	if lead and not frappe.db.get_value("Lead", lead, "solar_consumer"):
		frappe.db.set_value("Lead", lead, "solar_consumer", consumer, update_modified=False)


def _customer(company, consumer):
	"""The ERPNext Customer the consumer bills as. One, so invoicing has a party."""
	name = f"{TAG} Consumer"
	if frappe.db.exists("Customer", name):
		return name
	group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name,
			"customer_type": "Individual",
			"customer_group": group,
			"territory": territory,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _survey(company, consumer):
	existing = frappe.db.get_value(
		"Site Survey", {"solar_consumer": consumer, "company": company}, "name"
	)
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Site Survey",
			"company": company,
			"solar_consumer": consumer,
			"survey_date": _dated(company, SURVEYED_DAYS_AGO),
			"shadow_free_area_sqft": 420,
			"roof_condition": "Good",
			"roof_age_years": 6,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _estimate(company, consumer, survey=None):
	existing = frappe.db.get_value(
		"Solar Design Estimate", {"solar_consumer": consumer, "company": company}, "name"
	)
	if existing:
		return existing
	package = frappe.db.get_value(
		"Solar Package", {"company": company, "capacity_kw": 3}, "name"
	) or frappe.db.get_value("Solar Package", {"company": company}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Solar Design Estimate",
			"company": company,
			"solar_consumer": consumer,
			# The design is worked out from what the surveyor measured, and the
			# eligibility rules read the survey through this link.
			"site_survey": survey,
			"solar_package": package,
			"estimate_date": _dated(company, ESTIMATED_DAYS_AGO),
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	# A savepoint, not a rollback: submitting is a nice-to-have and its failure must not
	# take the estimate - or anything created before it - down with it.
	frappe.db.savepoint("starter_submit")
	try:
		doc.submit()
	except Exception:
		frappe.db.rollback(save_point="starter_submit")
	return doc.name


def _eligibility(company, consumer, estimate=None):
	existing = frappe.db.get_value(
		"Subsidy Eligibility Check", {"solar_consumer": consumer, "company": company}, "name"
	)
	if existing:
		return existing
	# The scheme the estimate priced against, not just any scheme on the company: a
	# Commercial scheme against a Residential connection fails ELG-01, and the quotation
	# then refuses to submit.
	scheme = frappe.db.get_value("Solar Design Estimate", estimate, "subsidy_scheme") if estimate else None
	if not scheme:
		category = frappe.db.get_value("Solar Consumer", consumer, "consumer_category")
		scheme = frappe.db.get_value(
			"Subsidy Scheme", {"company": company, "consumer_category": category}, "name"
		) or frappe.db.get_value(
			"Subsidy Scheme", {"company": company, "consumer_category": ["in", ["", None]]}, "name"
		) or frappe.db.get_value("Subsidy Scheme", {"company": company}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Subsidy Eligibility Check",
			"company": company,
			"solar_consumer": consumer,
			# Without this the check floats free of the design it was run against, and
			# the estimate's Connections panel has nothing under Eligibility.
			"design_estimate": estimate,
			"subsidy_scheme": scheme,
			"check_date": _dated(company, ESTIMATED_DAYS_AGO),
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _proposal(company, estimate, lead=None, consumer=None):
	if not estimate:
		return None
	existing = frappe.db.get_value(
		"Solar Proposal", {"solar_design_estimate": estimate, "company": company}, "name"
	)
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Solar Proposal",
			"company": company,
			"solar_design_estimate": estimate,
			"lead": lead,
			"solar_consumer": consumer,
			"proposal_date": _dated(company, PROPOSED_DAYS_AGO),
			"valid_till": add_days(_dated(company, PROPOSED_DAYS_AGO), 30),
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


# ------------------------------------------------------------------- phase 2
def _sales_item(company):
	"""One non-stock sales item, so a quotation has something to quote."""
	code = f"{TAG} Rooftop Solar Plant"
	if frappe.db.exists("Item", code):
		return code
	group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": group,
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_sales_item": 1,
			"description": "Grid-tied rooftop solar plant, supply and installation",
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return code


def _quotation(company, consumer, estimate, check, proposal, customer):
	"""The priced offer. Every solar figure on it is fetched from the estimate."""
	if not (consumer and estimate):
		return None
	existing = frappe.db.get_value(
		"Quotation", {"solar_consumer": consumer, "company": company, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		return existing

	design = frappe.get_doc("Solar Design Estimate", estimate)
	values = {
		"doctype": "Quotation",
		"company": company,
		"quotation_to": "Customer",
		"party_name": customer,
		"transaction_date": _dated(company, QUOTED_DAYS_AGO),
		"valid_till": add_days(_dated(company, QUOTED_DAYS_AGO), 30),
		"solar_consumer": consumer,
		"solar_design_estimate": estimate,
		"subsidy_eligibility_check": check,
		"solar_proposal": proposal,
		"items": [
			{
				"item_code": _sales_item(company),
				"qty": 1,
				"rate": flt(design.total_project_cost) or 215000,
				"description": "Grid-tied rooftop solar plant, supply and installation",
			}
		],
	}
	# One option is picked up on its own; more than one has to be named, and the
	# quotation refuses to validate until it is.
	if len(design.options) > 1:
		values["selected_option"] = design.options[0].option_name

	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	frappe.db.savepoint("starter_submit_quotation")
	try:
		doc.submit()
	except Exception as exception:
		frappe.db.rollback(save_point="starter_submit_quotation")
		_log(f"quotation {doc.name} left in draft: {exception}")
	return doc.name


def _sales_order(company, customer, quotation):
	"""The confirmed order. Submitting it is what opens the installation.

	This is deliberately the route the starter takes rather than building an
	installation straight off the estimate: submitting the order runs the real handoff,
	so the installation comes out carrying its quotation, order, estimate, eligibility
	check and proposal - which is what makes the chain walkable in both directions.
	"""
	if not quotation:
		return None
	if frappe.db.get_value("Quotation", quotation, "docstatus") != 1:
		_log("the quotation is not submitted, so no order can be raised from it")
		return None
	existing = frappe.db.get_value(
		"Sales Order",
		{"company": company, "docstatus": ["<", 2], "customer": customer},
		"name",
	)
	if existing:
		return existing

	q = frappe.get_doc("Quotation", quotation)
	doc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": company,
			"customer": customer,
			"transaction_date": _dated(company, ORDERED_DAYS_AGO),
			"delivery_date": add_days(_dated(company, ORDERED_DAYS_AGO), 60),
			"solar_consumer": q.solar_consumer,
			"items": [
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"rate": row.rate,
					"delivery_date": add_days(_dated(company, ORDERED_DAYS_AGO), 60),
					"prevdoc_docname": q.name,
				}
				for row in q.items
			],
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


def _installation(company, estimate, sales_order=None):
	"""The installation the order opened, or one built straight off the estimate.

	The order is the real route. The fallback exists only so the starter still produces
	an installation on a site where the quotation or the order could not be submitted.
	"""
	if sales_order:
		opened = frappe.db.get_value(
			"Solar Installation", {"sales_order": sales_order, "docstatus": ["<", 2]}, "name"
		)
		if opened:
			return opened
	if not estimate:
		return None
	existing = frappe.db.get_value(
		"Solar Installation", {"solar_design_estimate": estimate, "company": company}, "name"
	)
	if existing:
		return existing
	if not frappe.db.exists("Solar Design Estimate", estimate):
		raise frappe.ValidationError(
			f"the design estimate {estimate} does not exist, so there is nothing to install"
		)
	from a3_sola.demo.generate_operations_demo import make_installation

	# `make_installation` reads the estimate's fields, so it wants the document rather
	# than its name.
	installation = make_installation(company, frappe.get_doc("Solar Design Estimate", estimate))
	return installation.name


# ------------------------------------------------------------------- phase 4
def _signup():
	email = "starter.signup@example.com"
	existing = frappe.db.get_value("Subscription Signup", {"work_email": email}, "name")
	if existing:
		return existing
	plan = frappe.db.get_value("Subscription Plan", {"is_active": 1}, "name")
	if not plan:
		return None
	plan_doc = frappe.get_cached_doc("Subscription Plan", plan)
	doc = frappe.get_doc(
		{
			"doctype": "Subscription Signup",
			"full_name": "Starter Applicant",
			"work_email": email,
			"phone": "9847000102",
			"designation": "Managing Director",
			"organisation_name": f"{TAG} Solar EPC",
			"organisation_type": "Solar EPC",
			"city": "Kochi",
			"state": "Kerala",
			"country": "India",
			"subscription_plan": plan,
			"plan_code": plan_doc.plan_code,
			"billing_cycle": "Monthly",
			"total_users": plan_doc.included_users,
			"currency": "INR",
			"status": "Verified",
			"is_email_verified": 1,
			"verified_on": now_datetime(),
			"accepted_terms": 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _demo_request():
	"""The other half of the funnel: somebody who wants a conversation, not a card."""
	email = "starter.demo@example.com"
	existing = frappe.db.get_value("Demo Request", {"work_email": email}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Demo Request",
			"full_name": "Starter Prospect",
			"work_email": email,
			"phone": "9847000103",
			"organisation_name": f"{TAG} Prospect Solar",
			"city": "Thrissur",
			"state": "Kerala",
			"country": "India",
			"message": "We install about 20 rooftop systems a month and want to see the "
			           "subsidy tracking and the KSEB paperwork before we commit.",
			"status": "New",
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


# ------------------------------------------------------------------- phase 5
def _subscription(signup=None):
	organisation = f"{TAG} Solar EPC"
	existing = frappe.db.get_value(
		"Platform Subscription", {"organisation_name": organisation}, "name"
	)
	if existing:
		return existing
	plan = frappe.db.get_value("Subscription Plan", {"is_active": 1}, "name")
	if not plan:
		return None
	plan_doc = frappe.get_cached_doc("Subscription Plan", plan)
	subtotal = flt(plan_doc.monthly_price)
	doc = frappe.get_doc(
		{
			"doctype": "Platform Subscription",
			"subscription_signup": signup,
			"organisation_name": organisation,
			"primary_contact_email": "starter.signup@example.com",
			"primary_contact_phone": "9847000102",
			"subscription_plan": plan,
			"plan_code": plan_doc.plan_code,
			"billing_cycle": "Monthly",
			# Auto debit, so the chain has a mandate to hang off. An annual plan
			# collected by invoice never registers one.
			"collection_route": "Auto Debit",
			"included_users": plan_doc.included_users,
			"subtotal": subtotal,
			"tax_amount": round(subtotal * 0.18, 2),
			"currency": "INR",
			"state_code": "32",
			"place_of_supply": "Kerala",
			"start_date": today(),
			"current_period_start": today(),
			"current_period_end": add_days(add_months(today(), 1), -1),
			"next_billing_date": add_months(today(), 1),
			"status": "Active",
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name


# ------------------------------------------------------------------- phase 6
def _tenant(company, subscription, signup=None):
	if not subscription:
		return None
	organisation = f"{TAG} Solar EPC"
	existing = frappe.db.get_value("Tenant", {"tenant_name": organisation}, "name")
	if existing:
		return existing

	from a3_sola.api.provisioning import identifiers

	plan = frappe.db.get_value("Platform Subscription", subscription, "subscription_plan")
	plan_doc = frappe.get_cached_doc("Subscription Plan", plan) if plan else None
	tenant = frappe.new_doc("Tenant")
	tenant.update(
		{
			"tenant_name": organisation,
			"tenant_code": identifiers.generate_code(organisation),
			"platform_subscription": subscription,
			"subscription_signup": signup,
			"primary_contact_name": "Starter Applicant",
			"primary_contact_email": "starter.signup@example.com",
			"primary_contact_phone": "9847000102",
			"city": "Kochi",
			"state": "Kerala",
			"state_code": "32",
			"country": "India",
			"tenancy_strategy": "Multi Company",
			"subscription_plan": plan,
			"plan_code": plan_doc.plan_code if plan_doc else None,
			"included_users": plan_doc.included_users if plan_doc else 5,
			"user_quota": plan_doc.included_users if plan_doc else 5,
			"status": "Provisioning",
		}
	)
	if plan_doc:
		for row in plan_doc.enabled_modules:
			tenant.append(
				"enabled_modules",
				{"module_name": row.module_name, "is_enabled": row.is_enabled},
			)
	tenant.flags.ignore_permissions = True
	tenant.insert(ignore_permissions=True)
	tenant.submit()

	# Pointed at the company this dataset already built, rather than provisioning a second
	# one - a starter dataset that doubles the company count is not a starter dataset.
	tenant.db_set("company", company, update_modified=False)
	if not frappe.db.get_value("Company", company, "a3_sola_tenant"):
		frappe.db.set_value("Company", company, "a3_sola_tenant", tenant.name,
		                    update_modified=False)
	tenant.db_set({"status": "Active", "activated_on": now_datetime(),
	               "provisioned_on": now_datetime()}, update_modified=False)

	from a3_sola.api.onboarding import build_checklist

	build_checklist(tenant.name)
	_invitation(tenant.name)
	return tenant.name


def _invitation(tenant):
	email = "starter.colleague@example.com"
	if frappe.db.exists("Tenant Invitation", {"tenant": tenant, "invited_email": email}):
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Tenant Invitation",
			"tenant": tenant,
			"invited_email": email,
			"invited_name": "Starter Colleague",
			"status": "Pending",
			"invitation_token": frappe.generate_hash(length=48),
			"token_expires_on": add_days(now_datetime(), 14),
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


# ------------------------------------------------------------------ teardown
def _starter_subscriptions():
	"""The subscription names this dataset owns. Empty list matches nothing, which is
	what teardown should do on a database it was never installed on."""
	return frappe.get_all(
		"Platform Subscription", filters={"organisation_name": f"{TAG} Solar EPC"}, pluck="name"
	) or [""]


def _starter_payment_orders():
	subscriptions = _starter_subscriptions()
	return frappe.get_all(
		"Payment Order", filters={"platform_subscription": ["in", subscriptions]}, pluck="name"
	) or [""]


def teardown():
	"""Remove everything `install` created. Leaves the company's chart of accounts alone."""
	frappe.flags.in_demo = True
	removed = []
	for doctype, filters in (
		# Platform spine, leaf first: an invitation cannot outlive its tenant, and a
		# tenant cannot be removed while its provisioning job still points at it.
		("Tenant Invitation", {"invited_email": "starter.colleague@example.com"}),
		("Provisioning Job", {"idempotency_key": ["like", "starter::%"]}),
		("Tenant", {"tenant_name": f"{TAG} Solar EPC"}),
		("Payment Transaction", {"payment_order": ["in", _starter_payment_orders()]}),
		("Subscription Invoice", {"platform_subscription": ["in", _starter_subscriptions()]}),
		("Payment Order", {"platform_subscription": ["in", _starter_subscriptions()]}),
		("Payment Mandate", {"platform_subscription": ["in", _starter_subscriptions()]}),
		("Platform Subscription", {"organisation_name": f"{TAG} Solar EPC"}),
		("Subscription Signup", {"work_email": "starter.signup@example.com"}),
		("Demo Request", {"work_email": "starter.demo@example.com"}),
		# Delivery and service, leaf first.
		("Generation Reading", {"company": COMPANY}),
		("Solar Warranty Claim", {"company": COMPANY}),
		("Service Ticket", {"company": COMPANY}),
		("Solar OM Visit", {"company": COMPANY}),
		("Solar OM Contract", {"company": COMPANY}),
		("Statutory Fee Recovery", {"company": COMPANY}),
		("Solar Billing Plan", {"company": COMPANY}),
		("Project", {"company": COMPANY}),
		# Execution and statutory.
		("Installation Snag", {"company": COMPANY}),
		("Installation Work Order", {"company": COMPANY}),
		("Net Metering Agreement", {"company": COMPANY}),
		("Commissioning Report", {"company": COMPANY}),
		("Subsidy Claim", {"company": COMPANY}),
		("Loan Application", {"company": COMPANY}),
		("Statutory Fee Payment", {"company": COMPANY}),
		("Portal Application", {"company": COMPANY}),
		("Solar Installation", {"company": COMPANY}),
		# Selling.
		("Sales Invoice", {"company": COMPANY}),
		("Sales Order", {"company": COMPANY}),
		("Quotation", {"company": COMPANY}),
		("Solar Proposal", {"company": COMPANY}),
		("Subsidy Eligibility Check", {"company": COMPANY}),
		("Solar Design Estimate", {"company": COMPANY}),
		("Site Survey", {"company": COMPANY}),
		("Solar Consumer", {"company": COMPANY}),
		("Customer", {"customer_name": f"{TAG} Consumer"}),
		("Item", {"item_code": f"{TAG} Rooftop Solar Plant"}),
		("Lead", {"lead_name": f"{TAG} Enquiry"}),
		("User", {"email": USER_EMAIL}),
		("User", {"email": ["like", f"%{RETIRED_TEAM_DOMAIN}"]}),
	):
		if not frappe.db.exists("DocType", doctype):
			continue
		for name in frappe.get_all(doctype, filters=filters, pluck="name"):
			try:
				if frappe.get_meta(doctype).is_submittable:
					frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
				frappe.delete_doc(doctype, name, force=True, ignore_permissions=True,
				                  ignore_on_trash=True)
				removed.append(f"{doctype} {name}")
			except Exception:
				frappe.db.rollback()
	frappe.db.commit()
	_log(f"removed {len(removed)} record(s). The company {COMPANY} was left in place.")
	return removed
