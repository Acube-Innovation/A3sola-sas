# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal register the client keeps in a spreadsheet today.

Their existing numbering survives the migration, because their WhatsApp history and their
bank correspondence already reference it: a running sequence per financial year with the
prefix RENC-PROP, and a generated file name built from sequence, series, date, capacity
and customer name.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_settings, get_value

LINKS = (
	("lead", "Lead"),
	("solar_consumer", "Solar Consumer"),
	("solar_design_estimate", "Solar Design Estimate"),
)


class SolarProposal(Document):
	def autoname(self):
		"""Allocate the next sequence for the company and financial year, under a lock.

		Two things are going on, and they pull in different directions.

		**The sequence is per company**, because that is what the client references in their
		WhatsApp history and their bank correspondence, and because a tenant whose numbers
		skipped from 4 to 17 would be reading another tenant's activity out of the gaps.

		**The name must be unique across the site**, because it is a primary key. Those two
		facts collide the moment a second company exists: both allocate sequence 1 for the
		same year, both derive `RENC-PROP-26-27-0001`, and the second one fails to save.
		That is why the company abbreviation is in the name - the same suffix ERPNext puts
		on every account, warehouse and cost centre, for the same reason.

		The row lock covers the allocation itself: a max()+1 read races, and two salespeople
		generating at the same moment would otherwise take the same number.
		"""
		self.set_fiscal_year()
		prefix = get_value("proposal_series_prefix") or "RENC-PROP"
		fmt = get_value("proposal_fiscal_year_format") or "YY-YY"
		label = _fiscal_label(self.fiscal_year, fmt)
		series = f"{prefix}-{label}"

		frappe.db.sql(
			"select name from `tabSolar Proposal` where company=%s and fiscal_year=%s for update",
			(self.company, self.fiscal_year),
		)
		last = frappe.db.sql(
			"""select max(proposal_sequence) from `tabSolar Proposal`
			   where company=%s and fiscal_year=%s""",
			(self.company, self.fiscal_year),
		)[0][0]
		self.proposal_sequence = (last or 0) + 1
		self.name = _proposal_name(series, self.company, self.proposal_sequence)

		# Defence in depth. The lock makes the allocation atomic and the abbreviation makes
		# it unique, but a name that already exists must never be handed back regardless -
		# it would surface as an IntegrityError from deep inside the insert.
		guard = 0
		while frappe.db.exists("Solar Proposal", self.name):
			guard += 1
			self.proposal_sequence += 1
			self.name = _proposal_name(series, self.company, self.proposal_sequence)
			if guard > 999:
				frappe.throw(
					_("Could not allocate a free proposal number for {0}.").format(self.company)
				)

	def set_fiscal_year(self):
		if self.fiscal_year:
			return
		from erpnext.accounts.utils import get_fiscal_year

		self.fiscal_year = get_fiscal_year(self.proposal_date or frappe.utils.today(), as_dict=True).name

	def validate(self):
		assert_same_company(self, LINKS)
		self.set_fiscal_year()
		self.pull_from_estimate()
		self.compose_file_name()

	def pull_from_estimate(self):
		if not self.solar_design_estimate:
			return
		est = frappe.get_cached_doc("Solar Design Estimate", self.solar_design_estimate)
		self.capacity_kw = flt(est.final_capacity_kw)
		self.options_quoted = len(est.options)
		self.statutory_total = flt(est.statutory_total)

		row = None
		for option in est.options:
			if option.is_recommended:
				row = option
				break
		self.recommended_option_cost = flt(row.total_option_cost) if row else flt(est.total_project_cost)

		package = (row.solar_package if row else None) or est.solar_package
		if package:
			self.capacity_label = frappe.db.get_value("Solar Package", package, "specification_code")
		if not self.capacity_label:
			self.capacity_label = f"{flt(est.final_capacity_kw):g}KW"

		if not self.solar_consumer:
			self.solar_consumer = est.solar_consumer
		if self.solar_consumer and not self.customer_name:
			consumer = frappe.get_cached_doc("Solar Consumer", self.solar_consumer)
			self.customer_name = consumer.consumer_name
			self.mobile_no = consumer.mobile_no
			self.email_id = consumer.email_id

	def compose_file_name(self):
		"""The client's existing convention: sequence, series, date, capacity, customer."""
		pattern = get_value("proposal_file_name_pattern") or "{seq}-{series}-{date}-{capacity}-{customer_name}"
		prefix = get_value("proposal_series_prefix") or "RENC-PROP"
		fmt = get_value("proposal_fiscal_year_format") or "YY-YY"
		self.proposal_file_name = pattern.format(
			seq=self.proposal_sequence or "",
			series=f"{prefix}-{_fiscal_label(self.fiscal_year, fmt)}",
			date=getdate(self.proposal_date).strftime("%d.%m.%Y") if self.proposal_date else "",
			capacity=self.capacity_label or "",
			customer_name=self.customer_name or "",
		)

	def on_submit(self):
		if self.solar_consumer:
			frappe.get_doc("Solar Consumer", self.solar_consumer).set_status("Proposed")
		self.supersede_previous()

	def supersede_previous(self):
		"""A new proposal for the same consumer supersedes the previous one, with a link."""
		if not self.solar_consumer:
			return
		previous = frappe.get_all(
			"Solar Proposal",
			filters={
				"solar_consumer": self.solar_consumer,
				"name": ["!=", self.name],
				"docstatus": 1,
				"status": ["not in", ["Superseded", "Lost", "Accepted"]],
			},
			pluck="name",
		)
		for name in previous:
			frappe.db.set_value(
				"Solar Proposal", name, {"status": "Superseded", "superseded_by": self.name}, update_modified=False
			)


def _proposal_name(series, company, sequence):
	"""`RENC-PROP-26-27-SSE-0001` - series, company, number.

	The company code sits before the number so one company's proposals sort together, and
	so the number itself still reads as the sequence the client quotes.
	"""
	abbr = frappe.get_cached_value("Company", company, "abbr") if company else None
	abbr = (abbr or "").strip().upper()
	return f"{series}-{abbr}-{sequence:04d}" if abbr else f"{series}-{sequence:04d}"


def _fiscal_label(fiscal_year, fmt):
	"""2026-2027 -> '26-27' (YY-YY) or '2026-27' (YYYY-YY)."""
	if not fiscal_year:
		return ""
	parts = str(fiscal_year).split("-")
	if len(parts) != 2:
		return str(fiscal_year)
	start, end = parts[0].strip(), parts[1].strip()
	if fmt == "YYYY-YY":
		return f"{start}-{end[-2:]}"
	return f"{start[-2:]}-{end[-2:]}"


@frappe.whitelist()
def generate_proposal(solar_proposal):
	"""Render the PDF, name it on the client's convention, and render the greeting message."""
	from frappe.utils.pdf import get_pdf
	from frappe.utils.print_format import download_pdf  # noqa: F401  (ensures print deps load)

	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("write")

	html = frappe.get_print(doc.doctype, doc.name, print_format="Solar Proposal", no_letterhead=0)
	pdf = get_pdf(html)

	file_name = f"{doc.proposal_file_name or doc.name}.pdf"
	existing = frappe.get_all(
		"File", filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "file_name": file_name}
	)
	for row in existing:
		frappe.delete_doc("File", row.name, ignore_permissions=True)

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": pdf,
		}
	).insert(ignore_permissions=True)

	doc.db_set("proposal_pdf", file_doc.file_url, update_modified=False)
	doc.db_set("greeting_message", render_greeting(doc), update_modified=False)
	doc.db_set("status", "Generated", update_modified=False)
	return {"file_url": file_doc.file_url, "file_name": file_name}


def render_greeting(doc):
	"""The message the client pastes into WhatsApp, with their formatting preserved."""
	from a3_sola.api import outreach

	template = frappe.db.get_value(
		"Outreach Message Template",
		{"step_name": "Completed: Proposal Sent", "channel": "WhatsApp", "is_active": 1, "company": doc.company},
		"name",
	) or frappe.db.get_value(
		"Outreach Message Template",
		{"step_name": "Completed: Proposal Sent", "channel": "WhatsApp", "is_active": 1},
		"name",
	)
	if not template:
		return ""
	return outreach.render_message(template, doc, {"proposal": doc, "first_name": (doc.customer_name or "").split(" ")[0]})


@frappe.whitelist()
def mark_sent(solar_proposal, sent_via="WhatsApp"):
	"""Record dispatch, advance the lead's cadence and log the outreach."""
	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("write")

	doc.db_set("sent_via", sent_via, update_modified=False)
	doc.db_set("sent_on", now_datetime(), update_modified=False)
	doc.db_set("sent_by", frappe.session.user, update_modified=False)
	doc.db_set("status", "Sent", update_modified=False)

	if doc.lead:
		from a3_sola.api import outreach

		outreach.log_outreach(
			doc.lead,
			channel=sent_via if sent_via in ("WhatsApp", "Email") else "Email",
			outreach_step="Completed: Proposal Sent",
			call_status="Not Applicable",
			outcome=_("Proposal {0} sent").format(doc.name),
		)
	return doc.status


@frappe.whitelist()
def get_whatsapp_link(solar_proposal):
	"""A wa.me deep link prefilled with the greeting, so sending is one tap."""
	from a3_sola.api import outreach

	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("read")
	message = doc.greeting_message or render_greeting(doc)
	return outreach.whatsapp_link(doc.mobile_no, message)
