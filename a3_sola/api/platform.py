# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The Platform module's content and pricing layer.

Two jobs. First, resolving the content the public site renders, so that every section of
the marketing page comes from a record a marketer can edit rather than from a template a
developer has to redeploy. Second, pricing.

PRICING IS THE IMPORTANT HALF. `calculate_plan_total()` is the single source of truth for
what a plan costs, and it is pure: the same arguments always produce the same answer, and
it touches nothing. Phase 5 charges from a snapshot of its output rather than recomputing,
so the number a customer was shown is the number they are charged - even if marketing
changes the price the next morning.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, flt

CONTENT_CACHE_KEY = "a3_sola_platform_content"
PLAN_CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CYCLES = ("monthly", "annual")


# ------------------------------------------------------------------- settings
def site_settings():
	"""Everything the templates read from A3 Sola Settings.

	Deliberately not memoised on `frappe.local`: that outlives a cache clear, so a
	maintenance-mode switch or a changed price would not take effect until the worker
	recycled. `get_cached_doc` is already cached and is invalidated properly on save.
	"""
	return frappe.get_cached_doc("A3 Sola Settings")


def setting(fieldname, default=None):
	value = site_settings().get(fieldname)
	return value if value not in (None, "") else default


# -------------------------------------------------------------------- routing
def slugify(text):
	slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
	return slug or "page"


def resolve_route(prefix, route, title, name):
	"""Keep an existing route, or build one from the title. Never collide."""
	if route:
		candidate = route.strip("/")
		if not candidate.startswith(f"{prefix}/"):
			candidate = f"{prefix}/{slugify(candidate.split('/')[-1])}"
	else:
		candidate = f"{prefix}/{slugify(title)}"

	base, suffix = candidate, 1
	doctype = "Platform Feature" if prefix == "features" else "Platform Solution"
	while frappe.db.exists(doctype, {"route": candidate, "name": ["!=", name or ""]}):
		suffix += 1
		candidate = f"{base}-{suffix}"
	return candidate


def validate_bullets(rows, limit, label):
	if rows and len(rows) > limit:
		frappe.throw(
			_("A card shows at most {0} {1}; this record has {2}.").format(limit, label, len(rows)),
			title=_("Too Many Bullets"),
		)


def clear_content_cache():
	frappe.cache().delete_value(CONTENT_CACHE_KEY)


# -------------------------------------------------------------------- content
def published(doctype, fields, extra_filters=None, order_by="display_order asc, creation asc"):
	filters = {"is_published": 1}
	filters.update(extra_filters or {})
	return frappe.get_all(
		doctype, filters=filters, fields=fields, order_by=order_by, limit_page_length=0
	)


def homepage_features():
	return published(
		"Platform Feature",
		["name", "feature_name", "route", "icon", "short_description", "feature_group"],
		{"show_on_homepage": 1},
	)


def all_features():
	return published(
		"Platform Feature",
		["name", "feature_name", "route", "icon", "short_description", "feature_group"],
	)


def homepage_solutions():
	return published(
		"Platform Solution",
		["name", "solution_name", "route", "icon", "short_description"],
		{"show_on_homepage": 1},
	)


def all_solutions():
	return published(
		"Platform Solution",
		["name", "solution_name", "route", "icon", "short_description", "target_audience"],
	)


def stats():
	return published("Platform Stat", ["stat_value", "stat_label"])


def integrations_by_category():
	"""Grouped into columns, the way the site renders them."""
	rows = published(
		"Platform Integration",
		["name", "integration_name", "category", "logo", "fallback_initial", "integration_url"],
		order_by="category asc, display_order asc",
	)
	grouped = {}
	for row in rows:
		row["initial"] = row.fallback_initial or (row.integration_name or "?")[:1].upper()
		grouped.setdefault(row.category, []).append(row)
	return grouped


def faqs(group=None):
	extra = {"faq_group": group} if group else None
	return published("Platform FAQ", ["name", "question", "answer", "faq_group"], extra)


def bullets_for(doctype, names, fieldname):
	"""Card bullets for many records in one query - never one query per card."""
	if not names:
		return {}
	rows = frappe.get_all(
		"Platform Bullet",
		filters={"parent": ["in", names], "parenttype": doctype, "parentfield": fieldname},
		fields=["parent", "bullet_text"],
		order_by="idx asc",
		limit_page_length=0,
	)
	out = {}
	for row in rows:
		out.setdefault(row.parent, []).append(row.bullet_text)
	return out


def sibling_content(doctype, name, limit=4):
	title_field = "feature_name" if doctype == "Platform Feature" else "solution_name"
	return frappe.get_all(
		doctype,
		filters={"is_published": 1, "name": ["!=", name]},
		fields=["name", title_field + " as title", "route", "icon", "short_description"],
		order_by="display_order asc",
		limit_page_length=limit,
	)


# -------------------------------------------------------------------- pricing
def get_published_plans():
	"""Plans in display order, with the annual arithmetic already done.

	The card needs three numbers the plan record does not store: what annual billing
	saves, what that works out to per month, and how many months are free. Computing them
	here keeps the template free of arithmetic and keeps one answer everywhere.
	"""
	plans = frappe.get_all(
		"Subscription Plan",
		filters={"is_published": 1, "is_active": 1},
		fields=[
			"name", "plan_name", "plan_code", "tagline", "display_order", "is_popular",
			"is_custom_pricing", "monthly_price", "annual_price", "annual_months_free",
			"currency", "implementation_fee", "implementation_free_on_annual",
			"additional_user_price_monthly", "additional_user_price_annual",
			"included_users", "max_users", "included_companies", "storage_limit_gb",
			"trial_days", "cta_text", "inherits_from_plan",
		],
		order_by="display_order asc, creation asc",
		limit_page_length=0,
	)
	if not plans:
		return []

	features = _plan_features([p.name for p in plans])
	modules = _plan_modules([p.name for p in plans])
	inherited = {
		p.name: p.plan_name for p in plans
	}

	for plan in plans:
		plan["features"] = features.get(plan.name, [])
		plan["modules"] = modules.get(plan.name, [])
		plan["inherits_from_name"] = inherited.get(plan.inherits_from_plan)

		monthly, annual = flt(plan.monthly_price), flt(plan.annual_price)
		plan["annual_equivalent"] = flt(monthly * 12, 2)
		plan["annual_saving"] = flt(max(plan["annual_equivalent"] - annual, 0), 2)
		plan["annual_effective_monthly"] = flt(annual / 12.0, 2) if annual else 0.0
		plan["months_free"] = cint(plan.annual_months_free)
	return plans


def _plan_features(names):
	rows = frappe.get_all(
		"Plan Feature",
		filters={"parent": ["in", names], "parenttype": "Subscription Plan"},
		fields=["parent", "feature_text", "is_included"],
		order_by="idx asc",
		limit_page_length=0,
	)
	out = {}
	for row in rows:
		out.setdefault(row.parent, []).append(
			{"text": row.feature_text, "included": bool(row.is_included)}
		)
	return out


def _plan_modules(names):
	rows = frappe.get_all(
		"Plan Module",
		filters={"parent": ["in", names], "parenttype": "Subscription Plan"},
		fields=["parent", "module_name", "is_enabled"],
		order_by="idx asc",
		limit_page_length=0,
	)
	out = {}
	for row in rows:
		if row.is_enabled:
			out.setdefault(row.parent, []).append(row.module_name)
	return out


@frappe.whitelist(allow_guest=True)
def calculate_plan_total(plan_code, cycle="monthly", additional_users=0):
	"""What this plan actually costs. The single source of truth for every price shown.

	Pure by design: it reads the plan and computes, and changes nothing. Phase 5 calls it
	once at signup and snapshots the answer onto the Subscription Signup, then charges the
	snapshot. It must never recompute from the live plan at payment time - a price change
	between signup and payment would otherwise silently charge a different number than the
	one the applicant agreed to.
	"""
	cycle = (cycle or "monthly").strip().lower()
	if cycle not in CYCLES:
		frappe.throw(_("Billing cycle must be monthly or annual."), title=_("Unknown Cycle"))

	plan = _plan_for_code(plan_code)
	additional_users = max(cint(additional_users), 0)

	if plan.is_custom_pricing:
		# There is no number to give. Saying "0" would be worse than saying so.
		return {
			"plan_code": plan.plan_code,
			"plan_name": plan.plan_name,
			"cycle": cycle,
			"is_custom_pricing": True,
			"currency": plan.currency,
			"contact_sales": True,
			"message": _("Pricing for {0} is agreed with our team.").format(plan.plan_name),
			"line_items": [],
			"base_amount": 0.0,
			"additional_user_amount": 0.0,
			"additional_user_rate": 0.0,
			"implementation_fee": 0.0,
			"implementation_fee_waived": False,
			"implementation_fee_list": 0.0,
			"subtotal": 0.0,
			# Same shape as a priced result: a caller reading tax_amount should get a
			# number, not a KeyError, whichever kind of plan it asked about.
			"tax_amount": 0.0,
			"total_amount": 0.0,
			"included_users": cint(plan.included_users),
			"additional_users": additional_users,
			"total_users": cint(plan.included_users) + additional_users,
		}

	_validate_additional_users(plan, additional_users)

	annual = cycle == "annual"
	base = flt(plan.annual_price if annual else plan.monthly_price, 2)
	per_user = flt(
		plan.additional_user_price_annual if annual else plan.additional_user_price_monthly, 2
	)
	user_amount = flt(per_user * additional_users, 2)

	fee = flt(plan.implementation_fee, 2)
	waived = bool(annual and plan.implementation_free_on_annual)
	implementation = 0.0 if waived else fee

	suffix = _("year") if annual else _("month")
	line_items = [
		{
			"label": _("{0} plan - {1} users").format(plan.plan_name, cint(plan.included_users)),
			"detail": _("Billed per {0}").format(suffix),
			"amount": base,
		}
	]
	if additional_users:
		line_items.append(
			{
				"label": _("{0} additional users").format(additional_users),
				"detail": _("{0} per user per {1}").format(per_user, suffix),
				"amount": user_amount,
			}
		)
	if fee:
		line_items.append(
			{
				"label": _("Assisted implementation"),
				"detail": _("Waived on annual billing") if waived else _("One-time"),
				"amount": implementation,
				"waived": waived,
				"struck_amount": fee if waived else None,
			}
		)

	subtotal = flt(base + user_amount + implementation, 2)
	return {
		"plan_code": plan.plan_code,
		"plan_name": plan.plan_name,
		"cycle": cycle,
		"is_custom_pricing": False,
		"contact_sales": False,
		"currency": plan.currency,
		"base_amount": base,
		"additional_user_amount": user_amount,
		"additional_user_rate": per_user,
		"implementation_fee": implementation,
		"implementation_fee_waived": waived,
		"implementation_fee_list": fee,
		"subtotal": subtotal,
		# Tax is settled in Phase 5 against the customer's GSTIN and place of supply.
		"tax_amount": 0.0,
		"total_amount": subtotal,
		"included_users": cint(plan.included_users),
		"additional_users": additional_users,
		"total_users": cint(plan.included_users) + additional_users,
		"line_items": line_items,
	}


def _plan_for_code(plan_code):
	code = (plan_code or "").strip().lower()
	name = frappe.db.get_value(
		"Subscription Plan", {"plan_code": code, "is_active": 1}, "name"
	)
	if not name:
		frappe.throw(_("No active plan called {0}.").format(code or "?"), title=_("Unknown Plan"))
	return frappe.get_cached_doc("Subscription Plan", name)


def _validate_additional_users(plan, additional_users):
	limit = cint(plan.max_users)
	if not limit:
		return
	total = cint(plan.included_users) + additional_users
	if total > limit:
		frappe.throw(
			_("{0} allows at most {1} users; {2} were requested.").format(
				plan.plan_name, limit, total
			),
			title=_("Too Many Users"),
		)


# ----------------------------------------------------------- website context
#: Where the primary nav points. Anchors on the homepage, absolute links elsewhere.
NAV_ITEMS = (
	("Features", "#features", "/features"),
	("Solutions", "#solutions", "/solutions"),
	("Platform", "#platform", "/#platform"),
	("Integrations", "#integrations", "/#integrations"),
	("Pricing", "/pricing", "/pricing"),
	("Contact", "#contact", "/#contact"),
)

#: Pages that stay up during maintenance. Legal text has to remain reachable - somebody
#: may be relying on it, and a maintenance banner is not a substitute for a privacy policy.
MAINTENANCE_EXEMPT_PREFIXES = ("legal/", "legal")

#: Routes that must never be indexed. robots.txt says so too; this is the second lock.
NO_INDEX_ROUTES = (
	"get-started",
	"verify-email",
	"thank-you",
)


def update_website_context(context):
	"""Attach the platform chrome to every website request.

	Registered as a global website context hook rather than called page by page, so a page
	added later cannot accidentally skip it - which matters most for maintenance mode,
	where a missed call would leave a page publicly reachable that should not be.
	"""
	settings = site_settings()
	route = (getattr(frappe.local, "request", None) and frappe.local.request.path or "").strip("/")
	route = route or (context.get("route") or "").strip("/")

	context.platform_settings = settings
	context.current_year = frappe.utils.now_datetime().year
	context.site_url = frappe.utils.get_url()
	context.canonical_url = frappe.utils.get_url(route)
	context.home_prefix = "" if route in ("", "index") else "/"
	context.nav_items = [
		{"label": label, "href": home if route in ("", "index") else away}
		for label, home, away in NAV_ITEMS
	]
	context.maintenance_active = bool(
		settings.maintenance_mode and not route.startswith(MAINTENANCE_EXEMPT_PREFIXES)
	)
	context.no_index = any(
		route == r or route.startswith(r + "/") for r in NO_INDEX_ROUTES
	)
	context.organization_schema = organization_schema(settings)
	return context


def organization_schema(settings=None):
	settings = settings or site_settings()
	import json

	data = {
		"@context": "https://schema.org",
		"@type": "Organization",
		"name": settings.company_legal_name or settings.product_name or "a3 sola",
		"url": frappe.utils.get_url(),
		"description": settings.meta_description or "",
	}
	if settings.brand_logo:
		data["logo"] = frappe.utils.get_url(settings.brand_logo)
	if settings.sales_email or settings.sales_phone:
		contact = {"@type": "ContactPoint", "contactType": "sales"}
		if settings.sales_email:
			contact["email"] = settings.sales_email
		if settings.sales_phone:
			contact["telephone"] = settings.sales_phone
		data["contactPoint"] = [contact]
	if settings.parent_company_url:
		data["parentOrganization"] = {
			"@type": "Organization", "url": settings.parent_company_url
		}
	return json.dumps(data, indent=None)


# --------------------------------------------------------------- page context
#: The domain deep-dive tiles. Editable in Settings would mean six more fields for four
#: tiles; a small content doctype would mean a doctype for four rows. These live here and
#: are reported as the one place a marketer needs a developer - see docs/CONTENT_GUIDE.md.
DOMAIN_TILES = (
	(
		"Subsidy Eligibility & Slabs",
		"Capacity slabs, subsidy caps and consumer categories held as scheme records.",
		"Check eligibility before you quote, not after the customer has signed.",
	),
	(
		"DISCOM & Portal Application Tracking",
		"Feasibility, registration and net meter allocation tracked as external dependencies.",
		"An ageing report that names the section office and the days you have been waiting.",
	),
	(
		"DCR Serial Traceability",
		"Every module and inverter serial recorded against the roof it is on.",
		"Duplicates refused across every tenant, because the national portal does not care whose they were.",
	),
	(
		"Five-Year O&M Compliance",
		"The obligation raised at commissioning, with visits planned around the monsoon.",
		"Complaint handling you can prove, because the scheme can deactivate a vendor who cannot.",
	),
)

#: The ERPNext backbone tiles.
BACKBONE_TILES = (
	("CRM & Contacts", "Leads, opportunities and the customer record, shared with your solar pipeline."),
	("Accounts & GST", "Full double-entry accounting, GST returns and e-invoicing."),
	("Stock & Purchase", "Modules and inverters valued properly, from purchase receipt to the roof."),
	("HR & Payroll", "Your crew, their hours and their payroll, costing straight into the job."),
	("Multi-Company", "Several legal entities, one system, and no data crossing between them."),
	("Open REST APIs", "Everything the desk can do, your own systems can do too."),
)

#: The three apps in the closing section.
APP_TILES = (
	("Customer Portal", "📱", "System details, warranty dates by make, generation against the band you quoted, and a form to raise a service request."),
	("Field App", "🔦", "Surveys, installation logs, O&M visit checklists and photo capture, on the roof and offline-tolerant."),
	("Owner Dashboard", "📊", "Pipeline, project margin, SLA compliance and the performance obligation, on a phone."),
)


def homepage_context(context):
	"""Everything the homepage renders. All of it from records a marketer can edit."""
	features = homepage_features()
	solutions = homepage_solutions()
	context.features = features
	context.feature_bullets = bullets_for("Platform Feature", [f.name for f in features], "card_bullets")
	context.solutions = solutions
	context.stats = stats()
	context.integrations = integrations_by_category()
	context.plans = get_published_plans()
	context.domain_tiles = DOMAIN_TILES
	context.backbone_tiles = BACKBONE_TILES
	context.app_tiles = APP_TILES
	context.installation_volumes = INSTALLATION_VOLUMES
	return context


#: Shared by the demo form and the signup form, so the two never drift apart.
INSTALLATION_VOLUMES = ("Under 10", "10-50", "50-200", "Over 200")


def breadcrumb_schema(trail):
	"""BreadcrumbList JSON-LD for a detail page."""
	import json

	return json.dumps(
		{
			"@context": "https://schema.org",
			"@type": "BreadcrumbList",
			"itemListElement": [
				{
					"@type": "ListItem",
					"position": index + 1,
					"name": label,
					"item": frappe.utils.get_url(route) if route else None,
				}
				for index, (label, route) in enumerate(trail)
			],
		}
	)


def faq_schema(rows):
	"""FAQPage JSON-LD. Google shows these, so the answers have to be the real ones."""
	import json
	import re

	return json.dumps(
		{
			"@context": "https://schema.org",
			"@type": "FAQPage",
			"mainEntity": [
				{
					"@type": "Question",
					"name": row.question,
					"acceptedAnswer": {
						"@type": "Answer",
						"text": re.sub(r"<[^>]+>", " ", row.answer or "").strip(),
					},
				}
				for row in rows
			],
		}
	)


def software_schema(plans):
	"""SoftwareApplication with offers, for the pricing page."""
	import json

	settings = site_settings()
	offers = [
		{
			"@type": "Offer",
			"name": plan["plan_name"],
			"price": str(plan["monthly_price"]),
			"priceCurrency": plan["currency"],
		}
		for plan in plans
		if not plan["is_custom_pricing"]
	]
	return json.dumps(
		{
			"@context": "https://schema.org",
			"@type": "SoftwareApplication",
			"name": settings.product_name or "a3 sola",
			"applicationCategory": "BusinessApplication",
			"operatingSystem": "Web",
			"description": settings.meta_description or "",
			"offers": offers,
		}
	)


def legal_page_context(context, page_key):
	"""Render a legal page inside the site's own chrome.

	The text lives in a Platform Legal Page record so a lawyer's corrections can be
	applied from the desk without a deploy. The draft banner is driven by the record's
	own review flag, so it disappears when the review happens - not when somebody
	remembers to delete a hardcoded warning.
	"""
	page = frappe.db.get_value(
		"Platform Legal Page",
		{"page_key": page_key, "is_published": 1},
		[
			"name", "title", "body", "meta_title", "meta_description", "modified",
			"reviewed_by_lawyer", "reviewed_by", "reviewed_on",
		],
		as_dict=True,
	)
	if not page:
		raise frappe.DoesNotExistError

	context.no_cache = 1
	context.legal_title = page.title
	context.legal_body = page.body
	context.legal_updated = page.modified
	context.legal_is_draft = not page.reviewed_by_lawyer
	context.legal_reviewed_by = page.reviewed_by
	context.legal_reviewed_on = page.reviewed_on
	context.page_meta_title = page.meta_title or page.title
	context.page_meta_description = page.meta_description
	return context


def email_context(extra=None):
	"""Brand values every transactional email needs."""
	settings = site_settings()
	context = {
		"product_name": settings.product_name or "a3 sola",
		"company_legal_name": settings.company_legal_name or "Acube Innovations LLP",
		"sales_email": settings.sales_email,
		"site_url": frappe.utils.get_url(),
	}
	context.update(extra or {})
	return context
