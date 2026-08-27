# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Legal pages, seeded as editable Web Page records.

=============================================================================
THIS TEXT IS A FIRST DRAFT AND HAS NOT BEEN REVIEWED BY A LAWYER.

It is a starting point written to be substantive rather than empty, so that the
site is not shipped with placeholder text - not a substitute for advice. Before
go-live an Indian technology lawyer must review all three pages against the DPDP
Act 2023, the IT Act 2000 and the SPDI Rules 2011, and the draft banner must be
removed only once they have.

The pages render a visible banner saying exactly this. Do not remove the banner
without removing the reason for it.
=============================================================================
"""

import frappe

DRAFT_BANNER = (
	'<div class="a3s-draft"><strong>Draft for legal review.</strong> This text has been '
	"prepared as a first draft and has not yet been reviewed by a lawyer. It does not yet "
	"form a binding agreement. Please contact us with any question about it in the "
	"meantime.</div>"
)

PRIVACY = """
<p>This policy explains what personal data {company} collects when you use the
{product} website and product, why we collect it, how long we keep it and what you can
ask us to do with it.</p>

<h2>Who we are</h2>
<p>{company} operates {product}. For the purposes of the Digital Personal Data
Protection Act, 2023, we are the data fiduciary for the personal data described below.
You can reach us at <a href="mailto:{email}">{email}</a>.</p>

<h2>What we collect, and why</h2>
<h3>When you fill in a form on this site</h3>
<ul>
<li><strong>Your name, work email, phone number and company name.</strong> We need these
to reply to you. There is no way to run a sales conversation without them.</li>
<li><strong>Your approximate monthly installation volume.</strong> So we can tell you
honestly which plan fits rather than guessing.</li>
<li><strong>Your IP address and browser user agent.</strong> Recorded against a signup or
demo request to detect abuse of these public forms. They are deleted automatically once
the retention period configured in our system has passed.</li>
<li><strong>How you arrived here</strong> - the referring page and any campaign
parameters in the link you followed - so we know which of our efforts are worth
repeating.</li>
</ul>

<h3>When you become a customer</h3>
<p>Your subscription record holds your organisation's details, your billing information
and the users you create. Payment card details are handled entirely by our payment
gateway and never reach our servers.</p>

<h3>Data your business puts into the product</h3>
<p>The records you create in {product} - your customers, installations, documents and
accounts - belong to you. We process them only to provide the service, we do not sell
them, we do not use them to train anything, and we do not look at them except when you
ask us to help with a specific problem.</p>

<h2>Legal basis</h2>
<p>We process your data on the basis of the consent you give when you submit a form, and
on the basis of the contract between us once you become a customer. You can withdraw
consent at any time by emailing us.</p>

<h2>Who we share it with</h2>
<p>We share personal data only with the service providers we need to run the product -
our hosting provider, our email provider and our payment gateway - and only to the extent
each needs. We do not sell personal data to anyone, and we do not share it with
advertisers.</p>

<h2>How long we keep it</h2>
<ul>
<li><strong>Demo requests and unconverted signups:</strong> retained for our sales
follow-up, then deleted.</li>
<li><strong>IP address and user agent:</strong> purged automatically after the retention
period set in our system, which is measured in weeks, not years.</li>
<li><strong>Customer records:</strong> retained for the life of the contract and for as
long afterwards as Indian tax and company law require us to keep the associated
invoices.</li>
</ul>

<h2>Your rights</h2>
<p>You can ask us for a copy of the personal data we hold about you, ask us to correct
it, ask us to delete it, or withdraw your consent. Email
<a href="mailto:{email}">{email}</a> and we will respond within the period the law
allows. If you are not satisfied you may complain to the Data Protection Board of India.</p>

<h2>Cookies</h2>
<p>This site sets only the cookies needed for it to work, plus analytics cookies if you
consent to them. You can decline analytics and the site will work exactly the same.</p>

<h2>Changes</h2>
<p>If we change this policy we will change the date below and, where the change is
significant, tell customers by email.</p>
"""

TERMS = """
<p>These terms govern your use of {product}, operated by {company}. By signing up you
agree to them.</p>

<h2>The service</h2>
<p>{product} is a subscription software service for solar EPC businesses. What is
included in your subscription is set by the plan you choose, as described on our pricing
page at the time you sign up.</p>

<h2>Your account</h2>
<ul>
<li>You are responsible for the accuracy of the information you give us at signup.</li>
<li>You are responsible for your users, for what they do in the system, and for keeping
their credentials secure.</li>
<li>You must not use the service to break the law, to send unsolicited bulk messages, or
to attempt to reach another customer's data.</li>
</ul>

<h2>Fees and payment</h2>
<ul>
<li>Subscription fees are payable in advance, monthly or annually, as you select.</li>
<li>Fees are exclusive of GST, which is charged at the applicable rate.</li>
<li>The one-time implementation fee is charged at signup, and is waived on annual
billing.</li>
<li>Additional users are charged pro-rata from the date they are added.</li>
<li>If a payment fails we will retry and notify you. Your data remains intact and your
team keeps working during the grace period. After that the account moves to read-only.
Nothing is deleted.</li>
</ul>

<h2>Your data</h2>
<p>The data you put into {product} is yours. We claim no ownership of it. You may export
it at any time from the product or through the API. If you leave, we will provide a
complete export.</p>

<h2>Availability</h2>
<p>We aim to keep the service available at all times but we do not promise it will never
be interrupted. Planned maintenance is notified in advance where practicable.</p>

<h2>Support</h2>
<p>Support is provided by email during Indian business hours, at the level your plan
describes.</p>

<h2>Term and cancellation</h2>
<p>Your subscription continues until you cancel it. Cancellation takes effect at the end
of the cycle you have already paid for; we do not cut service off the moment you ask. See
our refund policy for what happens to money already paid.</p>

<h2>Suspension</h2>
<p>We may suspend an account that is being used to break the law, to attack the service,
or to reach another customer's data. Where we can, we will tell you first.</p>

<h2>Liability</h2>
<p>Our total liability to you in any twelve-month period is limited to the fees you paid
us in that period. We are not liable for indirect or consequential loss. Nothing in these
terms limits liability that cannot be limited under Indian law.</p>

<h2>Governing law</h2>
<p>These terms are governed by the laws of India, and the courts of Ernakulam, Kerala
have exclusive jurisdiction.</p>

<h2>Changes</h2>
<p>We may change these terms. Where a change materially affects you we will give at least
thirty days' notice by email, and you may cancel before it takes effect.</p>
"""

REFUND = """
<p>This policy explains when we refund subscription fees for {product}.</p>

<h2>The short version</h2>
<p>If the product does not do what we told you it does, tell us within thirty days of
signing up and we will refund you in full. After that, subscriptions are not refundable
for the period already paid, but you can cancel at any time and will not be charged
again.</p>

<h2>Thirty-day guarantee</h2>
<p>If you are not satisfied within the first thirty days of your first subscription
period, email <a href="mailto:{email}">{email}</a> and we will refund the subscription
fee in full. We will ask why - not to talk you out of it, but because we would rather fix
the reason.</p>

<h2>After thirty days</h2>
<ul>
<li><strong>Monthly plans:</strong> cancel at any time. Your subscription runs to the end
of the month you have paid for and is not renewed. The current month is not refunded.</li>
<li><strong>Annual plans:</strong> cancel at any time. The remainder of the annual term
is not refunded, because the annual price already carries two months free.</li>
</ul>

<h2>The implementation fee</h2>
<p>The one-time implementation fee covers work our team does for you. Once that work has
started it is not refundable. If you cancel before it starts, it is refunded in full.</p>

<h2>Additional users</h2>
<p>Users removed mid-cycle are not refunded for the remainder of that cycle, but you are
not charged for them in the next one.</p>

<h2>If we cancel</h2>
<p>If we discontinue the service or terminate your account for any reason other than your
breach of our terms, we refund the unused portion of what you have paid, pro-rata.</p>

<h2>How refunds are paid</h2>
<p>Refunds go back to the original payment method within seven to ten working days of
approval. GST already remitted is refunded in line with GST rules.</p>

<h2>Asking for a refund</h2>
<p>Email <a href="mailto:{email}">{email}</a> from the address on the account. Tell us
what happened. We will answer within three working days.</p>
"""

PAGES = (
	("privacy", "Privacy Policy", PRIVACY),
	("terms", "Terms of Service", TERMS),
	("refund-policy", "Refund Policy", REFUND),
)


def seed():
	"""Idempotent. Never overwrites text a lawyer may already have corrected."""
	settings = frappe.get_cached_doc("A3 Sola Settings")
	context = {
		"company": settings.company_legal_name or "Acube Innovations LLP",
		"product": settings.product_name or "a3 sola",
		"email": settings.sales_email or "sales@acube.co",
	}
	for key, title, body in PAGES:
		if frappe.db.exists("Platform Legal Page", key):
			continue
		doc = frappe.get_doc(
			{
				"doctype": "Platform Legal Page",
				"page_key": key,
				"title": title,
				"is_published": 1,
				"reviewed_by_lawyer": 0,
				"body": body.format(**context),
				"meta_title": f"{title} - {context['product']}",
				"meta_description": (
					f"{title} for {context['product']}, operated by {context['company']}."
				),
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
