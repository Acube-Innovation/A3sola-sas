# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Platform demo data: a funnel with something in every stage.

Extends the single demo generator rather than adding a second one. The point is that every
report has real shape - a funnel that leaks somewhere, sources that convert at different
rates, and a demo pipeline with something overdue in it.

Nothing here goes through the public API, deliberately: the demo must not be shaped by the
rate limiter, and the rate limiter must not be worn down by the demo.
"""

import frappe
from frappe.utils import add_days, add_to_date, now_datetime, today

from a3_sola.api import platform

from a3_sola.demo.scale import take

#: Four sources with deliberately different quality, so the acquisition report has a story.
SOURCES = (
	("google", "cpc", "kerala-solar-epc"),
	("linkedin", "social", "epc-founders"),
	("referral", "partner", "installer-network"),
	("direct", "none", ""),
)

ORGANISATIONS = (
	("Suryodaya Solar", "Anil Menon", "Managing Director", "Ernakulam", "10-50"),
	("Greenvolt Energy", "Priya Raghavan", "Founder", "Thrissur", "Under 10"),
	("Keralasun EPC", "Mohammed Ashraf", "Partner", "Kozhikode", "50-200"),
	("Bright Roof Systems", "Deepa Nair", "Operations Head", "Kollam", "10-50"),
	("Vayu Solar Works", "Sanjay Pillai", "Director", "Alappuzha", "Under 10"),
	("Nova Renewables", "Fathima Beevi", "CEO", "Kannur", "50-200"),
	("Anantha Power", "Rajeev Varma", "Managing Partner", "Palakkad", "10-50"),
	("Coastal Solar", "Meera Krishnan", "Founder", "Kasaragod", "Under 10"),
	("Sahya Energy", "Vinod Thomas", "Director", "Idukki", "10-50"),
	("Malabar Solar Co", "Shabana Rasheed", "Partner", "Malappuram", "50-200"),
	("Periyar Green Power", "Arun Joseph", "CEO", "Ernakulam", "Over 200"),
	("Kuttanad Solar", "Lakshmi Devi", "Owner", "Alappuzha", "Under 10"),
	("Highrange Renewables", "Tony Sebastian", "Director", "Idukki", "10-50"),
	("Backwater Energy", "Nisha Kumari", "Founder", "Kottayam", "Under 10"),
	("Western Ghats Solar", "Hari Prasad", "Partner", "Wayanad", "10-50"),
	("Arabian Sun Systems", "Zainab Ali", "Managing Director", "Kozhikode", "50-200"),
	("Cardamom Hills Solar", "George Mathew", "Owner", "Idukki", "Under 10"),
	("Chalakudy Power", "Remya Suresh", "Operations Head", "Thrissur", "10-50"),
	("Vembanad Energy", "Faisal Khan", "Director", "Kottayam", "50-200"),
	("Silent Valley Solar", "Aparna Menon", "Founder", "Palakkad", "Under 10"),
)

DEMO_ORGANISATIONS = (
	("Trivandrum Solar Hub", "Gopakumar S", "Under 10", "New"),
	("Ponnani Energy", "Salim Muhammed", "10-50", "New"),
	("Attingal Renewables", "Divya Prakash", "Under 10", "Contacted"),
	("Kochi Rooftop Co", "Manoj Kurian", "50-200", "Contacted"),
	("Nilambur Green", "Ayesha Sultana", "10-50", "Demo Scheduled"),
	("Cherthala Solar", "Biju Panicker", "Under 10", "Demo Scheduled"),
	("Guruvayur Power", "Nandini Iyer", "10-50", "Demo Completed"),
	("Varkala Energy", "Suresh Babu", "Under 10", "Demo Completed"),
	("Munnar Highlands Solar", "Elizabeth John", "50-200", "Converted"),
	("Kozhikode Beach Solar", "Abdul Nazar", "10-50", "Not Interested"),
	("Payyanur Renewables", "Sreeja Menon", "Under 10", "Not Interested"),
	("Cheap SEO Backlinks", "Bulk Sender", "Over 200", "Spam"),
)

#: Twenty signups spread deliberately: three abandoned, two payment-failed, and the rest
#: distributed so the funnel report shows a real drop-off rather than a straight line.
STATUS_PLAN = (
	("Active", "growth", "Annual", 5),
	("Active", "starter", "Annual", 0),
	("Paid", "growth", "Monthly", 3),
	("Paid", "starter", "Annual", 2),
	("Provisioning", "growth", "Annual", 8),
	("Payment Failed", "starter", "Monthly", 0),
	("Payment Failed", "growth", "Monthly", 4),
	("Awaiting Payment", "growth", "Annual", 2),
	("Awaiting Payment", "starter", "Monthly", 1),
	("Awaiting Payment", "starter", "Annual", 0),
	("Verified", "growth", "Monthly", 6),
	("Verified", "starter", "Monthly", 0),
	("Verified", "starter", "Annual", 3),
	("Verified", "growth", "Annual", 0),
	("Awaiting Email Verification", "starter", "Monthly", 0),
	("Awaiting Email Verification", "growth", "Annual", 2),
	("Awaiting Email Verification", "starter", "Annual", 1),
	("Abandoned", "starter", "Monthly", 0),
	("Abandoned", "growth", "Monthly", 0),
	("Abandoned", "starter", "Annual", 4),
)

VERIFIED_STATUSES = (
	"Verified", "Awaiting Payment", "Payment Failed", "Paid", "Provisioning", "Active",
)


def _log(message):
	print(f"  {message}")


def _email(organisation):
	slug = "".join(c for c in organisation.lower() if c.isalnum() or c == " ").replace(" ", "")
	return f"contact@{slug}.example"


def run(company=None):
	"""Build the funnel demo. Idempotent."""
	if frappe.db.exists("Subscription Signup", {"work_email": ["like", "%.example"]}):
		_log("platform demo already built")
		return

	created = 0
	for index, (status, plan_code, cycle, extra_users) in enumerate(take(STATUS_PLAN)):
		organisation, contact, designation, city, volume = ORGANISATIONS[index]
		source, medium, campaign = SOURCES[index % len(SOURCES)]
		# Spread the ages so the abandonment job and the ageing reports have something
		# to act on rather than twenty records all created this minute.
		age_days = 2 + index * 3

		plan = frappe.db.get_value("Subscription Plan", {"plan_code": plan_code}, "name")
		if not plan:
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Subscription Signup",
				"full_name": contact,
				"work_email": _email(organisation),
				"phone": f"98{47000000 + index * 137:08d}"[:10],
				"designation": designation,
				"organisation_name": organisation,
				"organisation_type": "Solar EPC",
				"city": city,
				"state": "Kerala",
				"country": "India",
				"approximate_monthly_installations": volume,
				"subscription_plan": plan,
				"plan_code": plan_code,
				"billing_cycle": cycle,
				"additional_users": extra_users,
				"accepted_terms": 1,
				"marketing_consent": 1 if index % 3 else 0,
				"source": "website",
				"utm_source": source,
				"utm_medium": medium,
				"utm_campaign": campaign,
				"landing_page": "/pricing",
				"ip_address": f"103.21.{index}.{10 + index}",
				"user_agent": "Mozilla/5.0 (demo)",
			}
		)
		doc.snapshot_price()
		doc.log_event("Created", "Signup submitted from the public site.")
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)

		_shape(doc, status, age_days)
		created += 1

	frappe.db.commit()
	_log(f"{created} subscription signups across every funnel stage")
	_demo_requests()


def _shape(doc, status, age_days):
	"""Walk a signup to where it should be, writing the event log as it goes."""
	created_at = add_to_date(now_datetime(), days=-age_days)

	doc.set_status("Awaiting Email Verification")
	if status in VERIFIED_STATUSES:
		doc.is_email_verified = 1
		doc.verified_on = add_to_date(created_at, hours=3)
		doc.verification_token = None
		doc.token_expires_on = None
		doc.set_status("Verified", details="Email address confirmed.")

	if status in ("Awaiting Payment", "Payment Failed", "Paid", "Provisioning", "Active"):
		doc.set_status("Awaiting Payment", details="Applicant reached the payment step.")
	if status == "Payment Failed":
		doc.set_status(
			"Payment Failed", reason="Card declined by the issuing bank.",
			details="Gateway reported a declined transaction.",
		)
	if status in ("Paid", "Provisioning", "Active"):
		doc.payment_completed_on = add_to_date(created_at, days=1)
		doc.set_status("Paid", details="Payment received.")
	if status in ("Provisioning", "Active"):
		doc.set_status("Provisioning", details="Tenant provisioning started.")
	if status == "Active":
		doc.set_status("Active", details="Tenant is live.")
	if status == "Abandoned":
		doc.verification_token = None
		doc.token_expires_on = None
		doc.set_status(
			"Abandoned", reason="Email never verified within the window.",
			details="Marked abandoned by the daily job.",
		)

	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)

	# Backdated last, and in SQL: `creation` is a constant to the ORM, and changing it
	# before the saves above would make every one of them refuse. Demo data needs the
	# spread of ages or the ageing and abandonment reports show nothing.
	frappe.db.sql(
		"update `tabSubscription Signup` set creation = %s where name = %s",
		(created_at, doc.name),
	)


def _demo_requests():
	created = 0
	for index, (organisation, contact, volume, status) in enumerate(DEMO_ORGANISATIONS):
		source, medium, campaign = SOURCES[index % len(SOURCES)]
		doc = frappe.get_doc(
			{
				"doctype": "Demo Request",
				"full_name": contact,
				"work_email": _email(organisation),
				"phone": f"97{44000000 + index * 211:08d}"[:10],
				"organisation_name": organisation,
				"approximate_monthly_installations": volume,
				"message": "We are on spreadsheets and WhatsApp and it has stopped scaling.",
				"status": status,
				"source": "website",
				"utm_source": source,
				"utm_medium": medium,
				"utm_campaign": campaign,
				"ip_address": f"49.207.{index}.{20 + index}",
				"user_agent": "Mozilla/5.0 (demo)",
				# One overdue follow-up, so the pipeline report has something to flag.
				"follow_up_date": add_days(today(), -3 if index == 2 else 4),
			}
		)
		doc.flags.ignore_permissions = True
		# The demo must not send twenty emails to whoever is on sales@.
		doc.flags.in_demo = True
		frappe.flags.in_demo = True
		doc.insert(ignore_permissions=True)
		if status != "New":
			frappe.db.set_value(
				"Demo Request", doc.name, "first_contacted_on",
				add_to_date(now_datetime(), days=-(index % 4) - 1), update_modified=False,
			)
		created += 1
	frappe.flags.in_demo = False
	frappe.db.commit()
	_log(f"{created} demo requests across the pipeline")


def teardown():
	for doctype in ("Subscription Signup", "Demo Request"):
		for name in frappe.get_all(
			doctype, filters={"work_email": ["like", "%.example"]}, pluck="name"
		):
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.flags.ignore_permissions = True
				doc.flags.ignore_links = True
				doc.cancel()
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		_log(f"removed {doctype}")
	frappe.db.commit()
