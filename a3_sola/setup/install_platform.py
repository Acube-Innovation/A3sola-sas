# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Platform module setup: roles, and the marketing content the public site renders.

Every record here is real copy, not a placeholder. Marketing edits it in the desk; nothing
on the site is hardcoded in a template. Seeding is idempotent - existing records are left
alone, because the client will edit this copy and a re-run must not overwrite their work.
"""

import frappe
from frappe.utils import cint

PLATFORM_ROLES = [
	("Platform Marketing Manager", "Marketing content, FAQs and the public site. No access to signups or plans."),
	("Platform Sales", "Subscription signups and demo requests. Cannot edit plans or pricing."),
	("Platform Billing Executive", "View payments, invoices and dunning. Can issue payment links. No refunds, no settings."),
	("Platform Billing Manager", "Refund approval, reconciliation and mandate management."),
	("Platform Admin", "Plans, pricing, gateway credentials and everything the others can do."),
]

PLATFORM_ROLE_PROFILES = {
	"Platform Marketing": ["Platform Marketing Manager"],
	"Platform Sales": ["Platform Sales"],
	"Platform Billing": ["Platform Billing Executive"],
	"Platform Billing Management": ["Platform Billing Manager", "Platform Billing Executive"],
	"Platform Administration": [
		"Platform Admin", "Platform Sales", "Platform Marketing Manager",
		"Platform Billing Manager",
	],
}

# ----------------------------------------------------------------- content copy
#: (name, group, icon, order, one-line description, three bullets)
FEATURES = [
	(
		"Solar CRM & Lead Management", "Core", "🎯", 10,
		"Every enquiry in one pipeline, from the first WhatsApp message to the signed order.",
		[
			"Consumer records carrying the KSEB consumer number, connection type and sanctioned load",
			"Stage-wise pipeline with the follow-up list computed from what actually happened",
			"Duplicate detection on consumer number, so the same roof is never quoted twice",
		],
	),
	(
		"WhatsApp Outreach & Follow-up Automation", "Core", "💬", 20,
		"A four-step follow-up cadence that runs itself, sent from your salesperson's own number.",
		[
			"Four-step cadence with call-status tracking - answered, no answer, call back, not interested",
			"Templated messages with the quotation attached, sent from the salesperson's own number",
			"A follow-up-due list that is computed from the last contact, not remembered by anyone",
		],
	),
	(
		"Subsidy Eligibility & Scheme Management", "Core", "🏛️", 30,
		"Check PM Surya Ghar eligibility before you quote, and track the claim to disbursement.",
		[
			"Capacity slabs and subsidy caps held as scheme records, not as numbers in code",
			"Eligibility check covering consumer category, prior subsidy and sanctioned load",
			"Claim tracked from PCR upload through verification to the customer's bank account",
		],
	),
	(
		"Site Survey & System Design", "Core", "📐", 40,
		"Survey the roof once and let the design fall out of the measurements.",
		[
			"Shadow-free segment capture with usable area and orientation per segment",
			"Capacity recommended from consumption, roof area and sanctioned load together",
			"Structure and cable extras costed at survey, not discovered at installation",
		],
	),
	(
		"Quotation & Proposal Automation", "Core", "📄", 50,
		"A priced, branded proposal in the customer's hands the same day as the survey.",
		[
			"Package master with the makes, wattages and inverter options you actually stock",
			"Subsidy shown as a separate line so the customer sees gross, subsidy and net",
			"Approval workflow before anything priced leaves the building",
		],
	),
	(
		"Installation & Stage Tracking", "Operations", "🔧", 60,
		"Nineteen stages from order to subsidy, each with the evidence it cannot proceed without.",
		[
			"Every stage names the documents it needs, and refuses to advance without them",
			"Stages the job does not need - loan stages on a self-funded sale - are skipped with a reason",
			"Blocking party recorded, so you know whether you are waiting on the DISCOM or on yourself",
		],
	),
	(
		"KSEB & Bank Document Automation", "Operations", "📋", 70,
		"Eighteen statutory and bank documents generated from one record, with no field retyped.",
		[
			"Consumer-vendor agreement, national portal data sheet, vendor feasibility report and EHS checklist",
			"Bank covering letters, KSEB annexures 1 to 3, net meter request, testing checklist and the stamp-paper agreement",
			"Completion report and registration fee refund request - one context builder, so the consumer number is identical on all of them",
		],
	),
	(
		"DISCOM & Portal Liaison", "Operations", "🏢", 80,
		"Track what the DISCOM and the national portal owe you, and for how long.",
		[
			"Portal and DISCOM applications with their own status, query log and ageing",
			"Feasibility, registration and net meter allocation tracked as external dependencies",
			"An ageing report that names the section office and the days waiting",
		],
	),
	(
		"Serial & DCR Traceability", "Operations", "🔢", 90,
		"Every module and inverter serial recorded against the roof it is on.",
		[
			"Serial register per installation with make, wattage and DCR certificate number",
			"Duplicate serials refused across every tenant - the national portal does not care whose they were",
			"Replacement under warranty updates the register, so the DCR manifest never goes stale",
		],
	),
	(
		"Commissioning & Handover", "Operations", "✅", 100,
		"The protection settings, the certificate and the handover pack, captured once.",
		[
			"All seven protection settings with the proof the DISCOM asks for",
			"Performance ratio computed at commissioning against a calibrated irradiance reading",
			"Handover pack, user manual and customer training recorded as done or not done",
		],
	),
	(
		"O&M Contracts & Preventive Maintenance", "Service", "🛠️", 110,
		"The five-year obligation as a liability you can see, not a promise you hope to keep.",
		[
			"Five-year contract raised automatically at commissioning, with fifteen visits planned around the monsoon",
			"Warranty terms read per make - a Rayzon roof and a Vikram roof expire three years apart",
			"A provision accrued at commissioning and drawn down as visits actually happen",
		],
	),
	(
		"Service Desk & SLA Management", "Service", "🎫", 120,
		"Complaint handling you can prove, because the scheme can deactivate a vendor who cannot.",
		[
			"Response and resolution windows from the contract, not from a global default",
			"Escalation at 75, 100 and 150 percent of the window, each rung firing exactly once",
			"Reopen counting, root-cause capture and an SLA report built to be exported as evidence",
		],
	),
	(
		"Generation & Performance Monitoring", "Analytics", "📈", 130,
		"Know a system is underperforming before the customer tells you.",
		[
			"Readings imported straight from the inverter portal export, or captured on the visit",
			"Performance ratio against design expectation, prorated by the days elapsed",
			"The operational threshold and the contractual floor treated as the different things they are",
		],
	),
	(
		"Accounts, GST & Reporting", "Finance", "💰", 140,
		"Milestone billing, project margin and the subsidy treated correctly in the books.",
		[
			"Your own 70:20:10 terms as milestone templates, triggered by site progress",
			"Project cost re-derived from source documents - rework isolated, statutory fees kept out of margin",
			"The subsidy never on an invoice: it is a government transfer to the customer, not your revenue",
		],
	),
]

SOLUTIONS = [
	(
		"Rooftop Solar EPC", "🏠", 10,
		"Residential and small commercial rooftop, end to end - survey, subsidy, install, service.",
		"EPC companies running 10 to 200 residential rooftop installations a month under PM Surya Ghar.",
		[
			"Subsidy eligibility checked before the quotation goes out",
			"Every KSEB and bank document generated from one record",
			"The five-year O&M obligation tracked as a liability, not a promise",
		],
	),
	(
		"Solar Dealers & Distributors", "📦", 20,
		"Stock, dealer pricing and installation partners on one system.",
		"Distributors carrying module and inverter stock and appointing installation partners.",
		[
			"Package master holding the makes and wattages you actually carry",
			"Serial traceability from purchase receipt to the roof",
			"Partner-wise installation tracking without a second system",
		],
	),
	(
		"Commercial & Industrial EPC", "🏭", 30,
		"Larger capacities, CEIG approval, and margin you can see per project.",
		"C&I contractors working above 10 kWp where approvals and margin control both matter.",
		[
			"CEIG and statutory approvals as tracked stages with their own evidence",
			"Project costing re-derived from stock issues, labour hours and subcontractor invoices",
			"Milestone billing against progress, with collection and DSO per customer",
		],
	),
	(
		"O&M Service Providers", "🔧", 40,
		"Preventive visits, service tickets and performance obligations across a portfolio.",
		"Companies maintaining plants they did not necessarily install.",
		[
			"Visit calendars planned around the monsoon and marked missed when they are",
			"SLA compliance reporting built to be handed to an auditor",
			"Performance ratio per site, worst first, against the contractual floor",
		],
	),
	(
		"Multi-Branch Solar Groups", "🌐", 50,
		"Several companies, one system, and no data crossing between them.",
		"Groups operating in more than one district or state under separate legal entities.",
		[
			"Every record carries its company, and every query is filtered by it",
			"Masters seeded per company, so each branch has its own DISCOM and tariff data",
			"Consolidated reporting for the group without exposing one branch to another",
		],
	),
]

INTEGRATIONS = [
	("Razorpay", "Payments", "R", 10, "https://razorpay.com"),
	("UPI & NEFT", "Payments", "U", 20, None),
	("PM Surya Ghar National Portal", "Government & Utility", "P", 30, None),
	("KSEB", "Government & Utility", "K", 40, None),
	("Jan Samarth", "Government & Utility", "J", 50, None),
	("WhatsApp Business", "Messaging", "W", 60, None),
	("Email & SMS Gateways", "Messaging", "E", 70, None),
	("Tally", "Accounting & Tax", "T", 80, None),
	("GST e-Invoice & e-Way Bill", "Accounting & Tax", "G", 90, None),
	("Frappe Insights", "Analytics & BI", "F", 100, None),
	("Google Data Studio", "Analytics & BI", "D", 110, None),
	("Solinteg Portal", "Hardware & Monitoring", "S", 120, None),
	("SolarEdge Monitoring", "Hardware & Monitoring", "S", 130, None),
	("Hoymiles S-Miles Cloud", "Hardware & Monitoring", "H", 140, None),
]

STATS = [
	("18", "Statutory documents generated", 10),
	("19", "Tracked installation stages", 20),
	("5 yrs", "O&M obligation managed", 30),
	("100%", "Built on open-source ERPNext", 40),
]

# ------------------------------------------------------------------ commercials
#: The commercial model, mirroring the reference product. Note which module each capability
#: sits in - a prospect must not have to guess which tier generates their KSEB forms.
PLANS = [
	{
		"plan_code": "starter",
		"plan_name": "Starter",
		"tagline": "For EPCs getting off spreadsheets and WhatsApp groups.",
		"display_order": 10,
		"monthly_price": 3000,
		"annual_price": 30000,
		"annual_months_free": 2,
		"implementation_fee": 10000,
		"additional_user_price_monthly": 300,
		"additional_user_price_annual": 3000,
		"included_users": 5,
		"max_users": 25,
		"included_companies": 1,
		"storage_limit_gb": 25,
		"modules": ["Solar CRM", "Solar Operations"],
		"features": [
			("Solar CRM - leads, consumers, surveys and design estimates", 1),
			("WhatsApp outreach with the four-step follow-up cadence", 1),
			("Subsidy eligibility checks and scheme management", 1),
			("Quotations and branded proposals with approval", 1),
			("All 19 installation stages with document gating", 1),
			("All 18 KSEB and bank documents generated automatically", 1),
			("Serial and DCR traceability", 1),
			("Commissioning, handover and net metering agreement", 1),
			("5 users included, up to 25", 1),
			("Project costing, GST and milestone billing", 0),
			("Five-year O&M contracts, service desk and SLA", 0),
			("Generation and performance monitoring", 0),
		],
	},
	{
		"plan_code": "growth",
		"plan_name": "Growth",
		"tagline": "For EPCs who also have to bill it, service it and prove it.",
		"display_order": 20,
		"is_popular": 1,
		"monthly_price": 6000,
		"annual_price": 60000,
		"annual_months_free": 2,
		"implementation_fee": 10000,
		"additional_user_price_monthly": 200,
		"additional_user_price_annual": 2000,
		"included_users": 15,
		"max_users": 60,
		"included_companies": 2,
		"storage_limit_gb": 100,
		"inherits_from": "starter",
		"modules": ["Solar CRM", "Solar Operations", "Solar Projects"],
		"features": [
			("Everything in Starter", 1),
			("Project costing re-derived from stock, labour and subcontractors", 1),
			("Milestone billing on your own 70:20:10 terms", 1),
			("GST valuation rules and gated accounting postings", 1),
			("Subsidy receivable, statutory recovery and write-offs", 1),
			("Five-year O&M contracts with monsoon-aware visit plans", 1),
			("Service desk with contract-driven SLAs and escalation", 1),
			("Warranty claims traced to the serial on the roof", 1),
			("Generation monitoring against design and contractual floor", 1),
			("Customer portal for system details and service requests", 1),
			("15 users included, up to 60", 1),
			("Additional users at a lower rate than Starter", 1),
		],
	},
	{
		"plan_code": "enterprise",
		"plan_name": "Enterprise",
		"tagline": "For multi-branch groups and anyone who needs it their way.",
		"display_order": 30,
		"is_custom_pricing": 1,
		"included_users": 25,
		"max_users": 0,
		"included_companies": 0,
		"storage_limit_gb": 0,
		"inherits_from": "growth",
		"modules": ["Solar CRM", "Solar Operations", "Solar Projects"],
		"cta_text": "Talk to us",
		"features": [
			("Everything in Growth", 1),
			("Unlimited users and unlimited companies", 1),
			("Multi-branch consolidation with strict tenant isolation", 1),
			("Custom reports, dashboards and print formats", 1),
			("Data migration from your existing system", 1),
			("API access for your own integrations", 1),
			("Named implementation lead and priority support", 1),
			("On-site training for your team", 1),
		],
	},
]

FAQS = [
	(
		"Pricing", 10,
		"What is included in assisted implementation?",
		"<p>A named implementation lead configures your company, DISCOM sections, tariffs, "
		"packages and document templates against your own paperwork, imports your existing "
		"consumer and installation data, and trains your team. It is a one-time fee and it is "
		"<strong>waived entirely when you pay annually</strong>.</p>",
	),
	(
		"Pricing", 20,
		"Can I add users in the middle of a billing cycle?",
		"<p>Yes. Additional users are charged at your plan's per-user rate, pro-rated to the "
		"remainder of the current cycle. You are never asked to upgrade a whole tier because "
		"you hired one more surveyor.</p>",
	),
	(
		"Pricing", 30,
		"Is GST charged on the subscription?",
		"<p>Yes. Subscription fees attract GST at the applicable rate for SaaS in India, shown "
		"separately on your invoice. If you supply a GSTIN at signup, your invoice carries it "
		"so you can claim input credit.</p>",
	),
	(
		"Pricing", 40,
		"What happens if a payment fails?",
		"<p>We retry, and email you. Your data stays exactly where it is and your team keeps "
		"working during the grace period - we do not lock an EPC out of their own installation "
		"records over a failed card. If it stays unpaid past the grace period the account moves "
		"to read-only, and nothing is deleted.</p>",
	),
	(
		"Product", 50,
		"Which plan generates my KSEB and bank forms?",
		"<p><strong>Starter.</strong> Document automation, the KSEB annexures, the bank packs and "
		"the stamp-paper net metering agreement all sit in the Solar Operations module, which is "
		"included in Starter.</p><p>Accounting, GST, milestone billing and the five-year O&amp;M "
		"layer sit in Solar Projects, which is the Growth upgrade.</p>",
	),
	(
		"Product", 60,
		"Do I own my data, and can I export it?",
		"<p>It is your data. You can export any of it at any time as CSV or Excel from any list "
		"view, or through the REST API. If you leave, we provide a complete database export. "
		"The product is built on open-source ERPNext, so there is no proprietary format holding "
		"your records hostage.</p>",
	),
	(
		"Implementation", 70,
		"How do I upgrade or downgrade later?",
		"<p>Upgrading takes effect immediately - the new modules appear and you are charged the "
		"difference pro-rata. Downgrading takes effect at the end of your current cycle so you "
		"keep what you have paid for. Data from a module you drop is retained, not deleted, and "
		"comes back if you upgrade again.</p>",
	),
	(
		"Implementation", 80,
		"How long does it take to go live?",
		"<p>Most EPCs are running live enquiries within two weeks. Configuration of your packages, "
		"DISCOM sections and document templates takes about a week; data import and training take "
		"the second. You can start using the CRM on day one while the rest is set up.</p>",
	),
	(
		"Support", 90,
		"How do I cancel?",
		"<p>Email us or cancel from your account. Cancellation takes effect at the end of the "
		"cycle you have paid for - we do not cut service the moment you ask. You get a full "
		"database export, and we retain nothing beyond our statutory obligations.</p>",
	),
	(
		"Support", 100,
		"Is the subsidy module included in Starter?",
		"<p>Yes. Subsidy eligibility, scheme slabs, the national portal application and claim "
		"tracking through to disbursement are all in Starter. What Growth adds is the "
		"<em>accounting</em> side - the receivable when you fund a customer's subsidy gap, and "
		"its recovery or write-off.</p>",
	),
]

# ------------------------------------------------------------------- seeding
def set_home_page():
	"""`/` belongs to the desk; the public site lives at /a3sola.

	Frappe would otherwise serve whatever sits at `www/index.html`, and before the public
	pages were moved under `www/a3sola/` that was the marketing homepage - so signing in to
	the ERP meant first getting past a landing page. The pages moved, which frees `/`, and
	this points it where a logged-in user expects to land.
	"""
	settings = frappe.get_single("Website Settings")
	if settings.home_page in (None, "", "index"):
		settings.home_page = "app"
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
		return True
	return False


def setup():
	"""Platform is not tenant-scoped, so this runs once per site, not per company."""
	set_home_page()
	create_roles()
	seed_features()
	seed_solutions()
	seed_integrations()
	seed_stats()
	seed_plans()
	seed_faqs()
	seed_legal_pages()
	seed_dunning_policy()
	set_defaults()


def seed_dunning_policy():
	from a3_sola.api import dunning

	dunning.seed_default_policy()


def seed_legal_pages():
	from a3_sola.setup import legal_pages

	legal_pages.seed()


def create_roles():
	for role, _description in PLATFORM_ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
				"is_custom": 1,
				"search_bar": 1,
				"notifications": 1,
				"list_sidebar": 1,
				"bulk_actions": 1,
				"form_sidebar": 1,
				"timeline": 1,
				"dashboard": 1,
			}
		).insert(ignore_permissions=True)

	for profile, roles in PLATFORM_ROLE_PROFILES.items():
		available = [r for r in roles if frappe.db.exists("Role", r)]
		if not available or frappe.db.exists("Role Profile", profile):
			continue
		frappe.get_doc(
			{
				"doctype": "Role Profile",
				"role_profile": profile,
				"roles": [{"role": r} for r in available],
			}
		).insert(ignore_permissions=True)


def _insert(doctype, values, key_field, key_value):
	"""Idempotent by a natural key. Never overwrites copy the client has edited."""
	if frappe.db.exists(doctype, {key_field: key_value}):
		return None
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc.name


def seed_features():
	for name, group, icon, order, description, bullets in FEATURES:
		_insert(
			"Platform Feature",
			{
				"feature_name": name,
				"feature_group": group,
				"icon": icon,
				"display_order": order,
				"short_description": description,
				"card_bullets": [{"bullet_text": b} for b in bullets],
				"hero_headline": name,
				"hero_subtext": description,
				"body_content": "<p>{0}</p><ul>{1}</ul>".format(
					description, "".join(f"<li>{b}</li>" for b in bullets)
				),
				"cta_headline": "Ready to see it on your own jobs?",
				"cta_button_text": "Get started",
				"cta_button_link": "/get-started",
				"meta_description": description,
			},
			"feature_name",
			name,
		)


def seed_solutions():
	for name, icon, order, description, audience, outcomes in SOLUTIONS:
		_insert(
			"Platform Solution",
			{
				"solution_name": name,
				"icon": icon,
				"display_order": order,
				"short_description": description,
				"target_audience": audience,
				"key_outcomes": [{"bullet_text": o} for o in outcomes],
				"hero_headline": name,
				"hero_subtext": description,
				"body_content": f"<p>{description}</p><p>{audience}</p>",
				"cta_headline": "See it on your own numbers",
				"cta_button_text": "Book a demo",
				"cta_button_link": "/#contact",
				"meta_description": description,
			},
			"solution_name",
			name,
		)


def seed_integrations():
	for name, category, initial, order, url in INTEGRATIONS:
		_insert(
			"Platform Integration",
			{
				"integration_name": name,
				"category": category,
				"fallback_initial": initial,
				"display_order": order,
				"integration_url": url,
			},
			"integration_name",
			name,
		)


def seed_stats():
	for value, label, order in STATS:
		_insert(
			"Platform Stat",
			{"stat_value": value, "stat_label": label, "display_order": order},
			"stat_label",
			label,
		)


def seed_plans():
	created = {}
	for spec in PLANS:
		spec = dict(spec)
		modules = spec.pop("modules", [])
		features = spec.pop("features", [])
		inherits = spec.pop("inherits_from", None)
		name = _insert(
			"Subscription Plan",
			{
				**spec,
				"currency": "INR",
				"enabled_modules": [
					{"module_name": m, "is_enabled": 1} for m in modules
				],
				"features": [
					{"feature_text": text, "is_included": included, "display_order": (i + 1) * 10}
					for i, (text, included) in enumerate(features)
				],
			},
			"plan_code",
			spec["plan_code"],
		)
		if name:
			created[spec["plan_code"]] = (name, inherits)

	# Second pass: a plan can only inherit from one that already exists.
	for code, (name, inherits) in created.items():
		if not inherits:
			continue
		parent = frappe.db.get_value("Subscription Plan", {"plan_code": inherits}, "name")
		if parent:
			frappe.db.set_value(
				"Subscription Plan", name, "inherits_from_plan", parent, update_modified=False
			)


def seed_faqs():
	for group, order, question, answer in FAQS:
		_insert(
			"Platform FAQ",
			{
				"faq_group": group,
				"display_order": order,
				"question": question,
				"answer": answer,
			},
			"question",
			question,
		)


def set_defaults():
	"""Fill the Platform tab's brand and contact fields, once, without overwriting edits."""
	settings = frappe.get_single("A3 Sola Settings")
	defaults = {
		# product_name already exists on the General tab from Phase 1 - the Platform tab
		# reuses it rather than shadowing it with a second field of the same name.
		"product_tagline": "The solar EPC platform built on ERPNext",
		"company_legal_name": "Acube Innovations LLP",
		"partner_badge_text": "Official ERPNext Partner",
		"footer_tagline": "Built by Acube Innovations, an Official ERPNext Partner.",
		"meta_title": "a3 sola - run your entire solar business on one platform",
		"meta_description": (
			"Solar CRM, subsidy management, KSEB and bank document automation, installation "
			"tracking, milestone billing and five-year O&M - on one ERPNext-based platform."
		),
		"sales_email": "sales@acube.co",
		"parent_company_url": "https://acube.co",
		"maintenance_message": (
			"We are making a short improvement to the site and will be back within the hour."
		),
	}
	changed = False
	for fieldname, value in defaults.items():
		if not settings.get(fieldname):
			settings.set(fieldname, value)
			changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)

	claim_home_page()
	set_robots_txt()


#: Signup routes must never be indexed - a crawler walking /verify-email burns
#: verification tokens, and an order summary in a search index is somebody's details in a
#: search index. Frappe renders robots.txt from Website Settings, so it stays editable.
ROBOTS_TXT = """User-agent: *
Disallow: /get-started
Disallow: /verify-email
Disallow: /thank-you
Disallow: /checkout
Disallow: /payment-status
Disallow: /billing
Disallow: /api/
Disallow: /app/
Disallow: /private/
Allow: /
"""


def set_robots_txt():
	website = frappe.get_single("Website Settings")
	if website.robots_txt:
		return
	website.robots_txt = ROBOTS_TXT + f"\nSitemap: {frappe.utils.get_url('/sitemap.xml')}\n"
	website.flags.ignore_permissions = True
	website.flags.ignore_mandatory = True
	website.save(ignore_permissions=True)


def claim_home_page():
	"""Serve the marketing site at /.

	Frappe sends a guest to /login when no home page is configured, which would put a
	login form where the product's front page belongs. Set through Website Settings rather
	than the `home_page` hook so the client can change it without a deploy, and only when
	nothing has claimed it - never overwriting a deliberate choice.
	"""
	website = frappe.get_single("Website Settings")
	if website.home_page:
		return
	website.home_page = "index"
	website.flags.ignore_permissions = True
	website.flags.ignore_mandatory = True
	website.save(ignore_permissions=True)
	frappe.cache.delete_key("home_page")
