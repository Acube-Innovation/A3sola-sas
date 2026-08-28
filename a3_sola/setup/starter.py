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
from frappe.utils import add_days, add_months, flt, now_datetime, today

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


def _log(message):
	print(f"  starter: {message}")


#: (key, doctype, builder). Order is dependency order - each step may use what the ones
#: before it produced, and nothing else.
STEPS = (
	("user", "User", lambda ctx: _user()),
	("lead", "Lead", lambda ctx: _lead(ctx["company"])),
	("consumer", "Solar Consumer", lambda ctx: _consumer(ctx["company"])),
	("customer", "Customer", lambda ctx: _customer(ctx["company"], ctx["consumer"])),
	("site_survey", "Site Survey", lambda ctx: _survey(ctx["company"], ctx["consumer"])),
	("design_estimate", "Solar Design Estimate", lambda ctx: _estimate(ctx["company"], ctx["consumer"])),
	("eligibility_check", "Subsidy Eligibility Check", lambda ctx: _eligibility(ctx["company"], ctx["consumer"])),
	("proposal", "Solar Proposal", lambda ctx: _proposal(ctx["company"], ctx["design_estimate"])),
	("installation", "Solar Installation", lambda ctx: _installation(ctx["company"], ctx["design_estimate"])),
	("signup", "Subscription Signup", lambda ctx: _signup()),
	("demo_request", "Demo Request", lambda ctx: _demo_request()),
	("subscription", "Platform Subscription", lambda ctx: _subscription()),
	("tenant", "Tenant", lambda ctx: _tenant(ctx["company"], ctx["subscription"])),
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
	made, failed = {}, {}
	try:
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

	_log("created " + ", ".join(f"{k}={v}" for k, v in made.items()))
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


def _user():
	"""One user, holding the roles a working solar engineer needs and nothing more."""
	if frappe.db.exists("User", USER_EMAIL):
		return USER_EMAIL
	roles = [
		r for r in (
			"Solar Sales Executive", "Solar Survey Engineer", "Solar Design Engineer",
			"Solar Operations Executive",
		)
		if frappe.db.exists("Role", r)
	]
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
	_log(f"sign in as {doc.name} / {USER_PASSWORD}")
	return doc.name


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


def _consumer(company):
	name = f"{TAG} Consumer"
	existing = frappe.db.get_value(
		"Solar Consumer", {"consumer_name": name, "company": company}, "name"
	)
	if existing:
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
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


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
			"survey_date": today(),
			"shadow_free_area_sqft": 420,
			"roof_condition": "Good",
			"roof_age_years": 6,
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _estimate(company, consumer):
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
			"solar_package": package,
			"estimate_date": today(),
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


def _eligibility(company, consumer):
	existing = frappe.db.get_value(
		"Subsidy Eligibility Check", {"solar_consumer": consumer, "company": company}, "name"
	)
	if existing:
		return existing
	scheme = frappe.db.get_value("Subsidy Scheme", {"company": company}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Subsidy Eligibility Check",
			"company": company,
			"solar_consumer": consumer,
			"subsidy_scheme": scheme,
			"check_date": today(),
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _proposal(company, estimate):
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
			"proposal_date": today(),
			"valid_till": add_days(today(), 30),
		}
	)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.insert(ignore_permissions=True)
	return doc.name


# ------------------------------------------------------------------- phase 2
def _installation(company, estimate):
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
	from a3_sola.demo.generate_operations_demo import _advance, make_installation

	# `make_installation` reads the estimate's fields, so it wants the document rather
	# than its name.
	installation = make_installation(company, frappe.get_doc("Solar Design Estimate", estimate))
	# Three stages in: ordered, no-objection applied for, awaiting DISCOM feasibility.
	# Far enough to show the stage chain working, short of the paperwork a real job needs.
	_advance(installation, ["ORD", "NPA", "FEAS"])
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
def _subscription():
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
			"organisation_name": organisation,
			"primary_contact_email": "starter.signup@example.com",
			"primary_contact_phone": "9847000102",
			"subscription_plan": plan,
			"plan_code": plan_doc.plan_code,
			"billing_cycle": "Monthly",
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
def _tenant(company, subscription):
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
def teardown():
	"""Remove everything `install` created. Leaves the company's chart of accounts alone."""
	frappe.flags.in_demo = True
	removed = []
	for doctype, filters in (
		("Tenant Invitation", {"invited_email": "starter.colleague@example.com"}),
		("Tenant", {"tenant_name": f"{TAG} Solar EPC"}),
		("Platform Subscription", {"organisation_name": f"{TAG} Solar EPC"}),
		("Subscription Signup", {"work_email": "starter.signup@example.com"}),
		("Demo Request", {"work_email": "starter.demo@example.com"}),
		("Solar Installation", {"company": COMPANY}),
		("Solar Proposal", {"company": COMPANY}),
		("Subsidy Eligibility Check", {"company": COMPANY}),
		("Solar Design Estimate", {"company": COMPANY}),
		("Site Survey", {"company": COMPANY}),
		("Solar Consumer", {"company": COMPANY}),
		("Customer", {"customer_name": f"{TAG} Consumer"}),
		("Lead", {"lead_name": f"{TAG} Enquiry"}),
		("User", {"email": USER_EMAIL}),
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
