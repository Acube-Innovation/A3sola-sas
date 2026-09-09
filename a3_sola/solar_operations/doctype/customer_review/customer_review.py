# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The customer's word on the job, and whether it reached Google.

One review per installation. Collecting it is the REVIEW task; the Google review is the
GREV task on the same record - requested with a one-tap link, marked posted with the
screenshot, or declined, which skips the task rather than leaving it hanging.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from a3_sola.api import documents
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_value

LINKS = (
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
)
DEFAULT_MESSAGE = (
	"Dear {consumer_name}, thank you for choosing {company_name} for your rooftop solar plant. "
	"If you are happy with the work, a Google review would mean a lot to us: {review_url}"
)


class CustomerReview(Document):
	def autoname(self):
		set_name(self, "customer_review_series_prefix", ".YYYY.-.#####", fallback="SOL-REV")

	def validate(self):
		self.company = frappe.db.get_value("Solar Installation", self.solar_installation, "company")
		assert_same_company(self, LINKS)
		self.validate_one_per_installation()
		if not self.assigned_by:
			self.assigned_by = frappe.session.user
		if not self.assigned_on:
			self.assigned_on = today()
		if self.status == "Completed":
			if not ((self.review_text or "").strip() or self.media):
				frappe.throw(
					_("A completed review carries the customer's words or their photos. Record at least one."),
					title=_("Nothing Recorded"),
				)
			self.review_date = self.review_date or today()
			self.collected_by = self.collected_by or frappe.session.user
			self.completed_on = self.completed_on or today()

	def validate_one_per_installation(self):
		other = frappe.db.get_value(
			"Customer Review",
			{"solar_installation": self.solar_installation, "docstatus": ["<", 2], "name": ["!=", self.name]},
			"name",
		)
		if other:
			frappe.throw(
				_("{0} already has a review, {1}.").format(
					self.solar_installation, frappe.utils.get_link_to_form("Customer Review", other)
				)
			)

	def before_submit(self):
		if self.status not in ("Completed", "Skipped"):
			frappe.throw(_("Set the status to Completed (or Skipped, with a reason) before submitting."))
		if self.status == "Skipped" and not (self.skip_reason or "").strip():
			frappe.throw(_("A reason is mandatory when skipping the review."))

	def on_submit(self):
		for row in self.media:
			if row.file:
				documents.register_document(
					self.solar_installation, "REVIEW", self.doctype, self.name,
					_("Review {0}").format((row.media_type or "media").lower()) + (f" - {row.caption}" if row.caption else ""),
					row.file, kind="Uploaded", document_date=row.taken_on,
				)


# ------------------------------------------------------------------ form actions
def _load(review):
	doc = frappe.get_doc("Customer Review", review)
	doc.check_permission("write")
	return doc


def _save(doc):
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()
	return doc


def review_message(doc):
	url = frappe.db.get_value("Company", doc.company, "google_review_url")
	if not url:
		frappe.throw(
			_("Set the Google Review Link on company {0} first.").format(doc.company), title=_("No Review Link")
		)
	template = get_value("google_review_message") or DEFAULT_MESSAGE
	return template.format(
		consumer_name=doc.consumer_name or _("Customer"),
		company_name=frappe.db.get_value("Company", doc.company, "epc_name") or doc.company,
		review_url=url,
	), url


@frappe.whitelist()
def request_review(review, via="WhatsApp"):
	"""The review link, one tap away. Returns the wa.me link (or the mailto) and records the ask."""
	from a3_sola.api.outreach import whatsapp_link

	doc = _load(review)
	message, url = review_message(doc)
	consumer = frappe.db.get_value("Solar Consumer", doc.solar_consumer, ["mobile_no", "email_id"], as_dict=True) or frappe._dict()
	if via == "Email":
		import urllib.parse

		if not consumer.email_id:
			frappe.throw(_("The consumer has no email address."))
		link = f"mailto:{consumer.email_id}?subject={urllib.parse.quote(_('A quick review?'))}&body={urllib.parse.quote(message)}"
	elif via == "WhatsApp":
		if not consumer.mobile_no:
			frappe.throw(_("The consumer has no mobile number."))
		link = whatsapp_link(consumer.mobile_no, message)
	else:
		link = url
	if doc.google_review_status in ("Not Requested", None, ""):
		doc.google_review_status = "Requested"
	doc.requested_on = today()
	doc.requested_via = via
	_save(doc)
	return {"link": link, "message": message, "review_url": url}


@frappe.whitelist()
def mark_posted(review, link=None, screenshot=None, posted_on=None):
	doc = _load(review)
	if not (link or screenshot):
		frappe.throw(_("Record the review link or attach a screenshot as proof."))
	doc.google_review_status = "Posted"
	doc.posted_on = posted_on or today()
	doc.google_review_link = link or doc.google_review_link
	doc.google_review_screenshot = screenshot or doc.google_review_screenshot
	doc.decline_reason = None
	_save(doc)
	return doc.name


@frappe.whitelist()
def mark_declined(review, reason=None):
	"""The customer said no. The Google task is skipped, not left open forever."""
	if not (reason or "").strip():
		frappe.throw(_("Say why the customer declined."))
	doc = _load(review)
	doc.google_review_status = "Declined"
	doc.decline_reason = reason.strip()
	_save(doc)
	return doc.name


@frappe.whitelist()
def complete(review):
	doc = _load(review)
	if doc.docstatus != 0:
		frappe.throw(_("{0} is already submitted.").format(doc.name))
	doc.status = "Completed"
	doc.save()
	doc.submit()
	return doc.name
