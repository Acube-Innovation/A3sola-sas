# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal register the client keeps in a spreadsheet today.

Their existing numbering survives the migration, because their WhatsApp history and their
bank correspondence already reference it: a running sequence per financial year with the
prefix RENC-PROP, and a generated file name built from sequence, series, date, capacity
and customer name.

A lead has exactly one proposal. Re-quoting does not raise a second document - it opens a
new version inside this one, because the customer experiences it as the same offer changing
rather than as two offers. Each version carries what was quoted, the PDF that went out, how
and when it was sent, and what the customer said back. The header mirrors the newest version
so a list or a report reads the current state without walking the table.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime

from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_settings, get_value

#: What `record_dispatch` accepts. Mirrors the Select on Solar Proposal Version, because a
#: whitelisted endpoint must never write a value the field itself does not offer.
DISPATCH_CHANNELS = ("WhatsApp", "Email", "Printed", "Hand Delivered")

#: What `record_response` accepts. The opening state is set by `_open_version` alone.
CLIENT_OUTCOMES = ("Accepted", "Revision Requested", "Rejected", "Lost")

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
		self.resolve_subject()
		self.fill_from_lead()
		self.fill_design_estimates()
		assert_same_company(self, LINKS)
		self.set_fiscal_year()
		self.pull_from_estimate()
		self.compose_file_name()
		self.sync_from_versions()

	def resolve_subject(self):
		"""Every proposal belongs to an enquiry, and every enquiry has one proposal.

		The lead is rarely typed - it is already known to the estimate this proposal quotes,
		or to the consumer that estimate is for - so it is filled in rather than asked for.
		"""
		first = self.design_estimates[0].solar_design_estimate if self.get("design_estimates") else None
		if not self.lead:
			if first or self.solar_design_estimate:
				self.lead = frappe.db.get_value("Solar Design Estimate", first or self.solar_design_estimate, "lead")
			if not self.lead and self.solar_consumer:
				self.lead = frappe.db.get_value("Solar Consumer", self.solar_consumer, "lead")
		if not (self.lead or self.solar_consumer):
			frappe.throw(
				_("Select a Lead or a Solar Consumer for this proposal."),
				frappe.MandatoryError,
				title=_("Nothing to Propose For"),
			)
		self.assert_single_per_lead()

	def fill_from_lead(self):
		"""Section 1 - who and where - from the lead, its consumer and its latest site survey.

		The site and connection fields are read-only here and always follow those records;
		the customer's name, mobile, email, location and district are filled only when blank,
		since they are what the proposal is addressed to and may be worded for it.
		"""
		values = proposal_defaults_for(self.lead, self.solar_consumer)
		if self.site_survey and self.solar_consumer:
			survey_consumer = frappe.db.get_value("Site Survey", self.site_survey, "solar_consumer")
			if survey_consumer and survey_consumer != self.solar_consumer:
				frappe.throw(_("Site survey {0} is of another consumer.").format(self.site_survey))
		for fieldname in SITE_FIELDS:
			if fieldname in values:
				self.set(fieldname, values.get(fieldname))
		for fieldname in ("solar_consumer", "site_survey", "customer_name", "mobile_no", "email_id", "location", "district"):
			if not self.get(fieldname) and values.get(fieldname):
				self.set(fieldname, values[fieldname])

	def fill_design_estimates(self):
		"""Every design estimate of the lead, oldest first, unless rows were chosen already.

		The first row is the base - what the proposal is generated from and what the others
		are compared with - so the Base Design Estimate field follows it. A row must be an
		estimate of this lead (or its consumer), and appear once.
		"""
		if not self.get("design_estimates"):
			names = lead_estimates(self.lead, self.solar_consumer)
			if self.solar_design_estimate and self.solar_design_estimate not in names:
				names.insert(0, self.solar_design_estimate)
			elif self.solar_design_estimate in names:
				# An estimate chosen before the table existed stays the base.
				names.remove(self.solar_design_estimate)
				names.insert(0, self.solar_design_estimate)
			for name in names:
				self.append("design_estimates", {"solar_design_estimate": name})

		seen = set()
		for row in self.design_estimates:
			if row.solar_design_estimate in seen:
				frappe.throw(_("Row {0}: design estimate {1} is listed twice.").format(row.idx, row.solar_design_estimate))
			seen.add(row.solar_design_estimate)
			est = frappe.db.get_value("Solar Design Estimate", row.solar_design_estimate,
				["lead", "solar_consumer", "estimate_date", "solar_package", "final_capacity_kw"], as_dict=True)
			if not est:
				continue
			if not _belongs(est, self.lead, self.solar_consumer):
				frappe.throw(_("Row {0}: design estimate {1} is for another customer.").format(row.idx, row.solar_design_estimate))
			row.estimate_date = est.estimate_date
			row.solar_package = est.solar_package
			row.capacity_kw = flt(est.final_capacity_kw)
			row.total_amount = flt(frappe.get_doc("Solar Design Estimate", row.solar_design_estimate).commercials()["total"])
			row.is_base = 1 if row.idx == 1 else 0
		if self.design_estimates:
			self.solar_design_estimate = self.design_estimates[0].solar_design_estimate

	def assert_single_per_lead(self):
		"""One proposal per lead. A re-quote is a version of it, not a second document."""
		if not self.lead:
			return
		existing = frappe.db.get_value(
			"Solar Proposal",
			{"lead": self.lead, "name": ["!=", self.name or ""], "docstatus": ["<", 2]},
			"name",
		)
		if existing:
			frappe.throw(
				_("Lead {0} already has proposal {1}. Open a new version on it rather than a second proposal.").format(
					self.lead, existing
				),
				title=_("Proposal Already Exists"),
			)

	def before_update_after_submit(self):
		"""Versions keep accruing after the proposal is issued, so the header must follow.

		Frappe runs `validate` only on a draft; a submitted document takes this path
		instead. Without it the header would freeze at whatever the proposal looked like
		on the day it was submitted, while the history underneath it moved on.
		"""
		self.sync_from_versions()

	def sync_from_versions(self):
		"""The header shows the newest version, so a list or a report reads current state.

		Nothing here is authoritative. Every value is a copy of the last row of the table,
		which is the record - the header exists because the proposal register, the number
		cards and the portal list all read flat fields.
		"""
		if not self.versions:
			self.current_version = 0
			return
		latest = self.versions[-1]
		self.current_version = latest.version_no
		self.proposal_pdf = latest.proposal_pdf
		self.proposal_file_name = latest.proposal_file_name or self.proposal_file_name
		self.sent_via = latest.sent_via or "Not Sent"
		self.sent_on = latest.sent_on
		self.sent_by = latest.sent_by
		self.lost_reason = latest.lost_reason
		self.status = _status_of(latest)

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


#: Section 1's site and connection fields: read-only, always taken from the records.
SITE_FIELDS = ("tariff_code", "connection_type", "consumer_number", "discom", "discom_section",
	"taluk", "landmark", "google_location_url")


def lead_estimates(lead, solar_consumer=None):
	"""The lead's design estimates - draft or submitted - oldest first."""
	if not (lead or solar_consumer):
		return []
	# The lead decides; the consumer only for an estimate made without a lead.
	rows = frappe.get_all("Solar Design Estimate", filters={"docstatus": ["<", 2]},
		or_filters=[["lead", "=", lead or "__none__"], ["solar_consumer", "=", solar_consumer or "__none__"]],
		fields=["name", "lead", "solar_consumer"], order_by="creation asc")
	return [r.name for r in rows if _belongs(r, lead, solar_consumer)]


def _belongs(estimate, lead, solar_consumer):
	"""Whether an estimate is this customer's: by its lead, else by its consumer."""
	if lead and estimate.lead:
		return estimate.lead == lead
	if solar_consumer and estimate.solar_consumer:
		return estimate.solar_consumer == solar_consumer
	return True


def proposal_defaults_for(lead, solar_consumer=None):
	"""What section 1 holds for this lead: from the lead, its consumer and its site survey."""
	values = {}
	lead_doc = frappe.db.get_value("Lead", lead, ["lead_name", "company_name", "mobile_no", "email_id", "city",
		"district", "solar_consumer", "site_survey", "discom", "discom_section", "consumer_number",
		"connection_type"], as_dict=True) if lead else None
	consumer = solar_consumer or (lead_doc.solar_consumer if lead_doc else None)
	con = frappe.db.get_value("Solar Consumer", consumer, ["consumer_name", "mobile_no", "email_id", "site_survey",
		"tariff_category", "discom", "discom_section", "consumer_number", "connection_type", "taluk", "landmark",
		"google_location_url", "village", "local_body_name"], as_dict=True) if consumer else None
	survey = (con.site_survey if con else None) or (lead_doc.site_survey if lead_doc else None)
	pick = lambda field: (con.get(field) if con else None) or (lead_doc.get(field) if lead_doc and field in lead_doc else None)

	values["solar_consumer"] = consumer
	values["customer_name"] = (con.consumer_name if con else None) or (lead_doc.lead_name if lead_doc else None)
	values["mobile_no"] = pick("mobile_no")
	values["email_id"] = pick("email_id")
	values["site_survey"] = survey
	values["tariff_code"] = con.tariff_category if con else None
	values["discom"] = pick("discom")
	values["discom_section"] = pick("discom_section")
	values["consumer_number"] = pick("consumer_number")
	values["connection_type"] = pick("connection_type")
	values["taluk"] = con.taluk if con else None
	values["landmark"] = con.landmark if con else None
	values["google_location_url"] = con.google_location_url if con else None
	district = frappe.db.get_value("Indian District", lead_doc.district, "district_name") if lead_doc and lead_doc.district else None
	if not district and values["discom_section"]:
		district = frappe.db.get_value("DISCOM Section", values["discom_section"], "district")
	values["district"] = district
	place = (con.village or con.local_body_name) if con else None
	values["location"] = place or (lead_doc.city if lead_doc else None) or district
	return values


@frappe.whitelist()
def proposal_defaults(lead=None, solar_consumer=None):
	"""Section 1 and the design estimates for a lead, for the form to fill as it is chosen."""
	if lead:
		frappe.has_permission("Lead", "read", lead, throw=True)
	values = proposal_defaults_for(lead, solar_consumer)
	estimates = lead_estimates(lead, values.get("solar_consumer"))
	return {"values": values, "site_fields": list(SITE_FIELDS), "estimates": [
		frappe.db.get_value("Solar Design Estimate", n, ["name", "estimate_date", "solar_package", "final_capacity_kw"], as_dict=True)
		for n in estimates
	]}


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


def _status_of(version):
	"""The header status a version implies. One place, so the two can never disagree."""
	outcome = version.outcome or "Awaiting Response"
	if outcome == "Accepted":
		return "Accepted"
	if outcome in ("Rejected", "Lost"):
		return "Lost"
	if version.sent_on:
		return "Sent"
	if version.proposal_pdf:
		return "Generated"
	return "Draft"


def _version_file_name(doc, version_no):
	"""Version one keeps the client's file-name convention exactly; later ones are marked.

	Their convention has no revision in it, because their spreadsheet only ever held one
	row per proposal. A second version still has to be a different file on disk and a
	different attachment, so it carries a suffix rather than silently overwriting the first.
	"""
	base = doc.proposal_file_name or doc.name
	return base if version_no <= 1 else f"{base}-R{version_no}"


def _open_version(doc, notes=None):
	"""Append a new version, snapshotting what is being quoted right now."""
	doc.pull_from_estimate()
	doc.compose_file_name()
	version_no = (doc.versions[-1].version_no if doc.versions else 0) + 1
	return doc.append(
		"versions",
		{
			"version_no": version_no,
			"version_date": now_datetime(),
			"solar_design_estimate": doc.solar_design_estimate,
			"capacity_label": doc.capacity_label,
			"capacity_kw": flt(doc.capacity_kw),
			"options_quoted": doc.options_quoted,
			"recommended_option_cost": flt(doc.recommended_option_cost),
			"proposal_file_name": _version_file_name(doc, version_no),
			"sent_via": "Not Sent",
			"outcome": "Awaiting Response",
			"notes": notes or None,
		},
	)


def _current_version(doc):
	return doc.versions[-1] if doc.versions else None


def _save_version_change(doc):
	"""Persist a version change, on a submitted proposal as much as a draft one.

	Every field on a version is written by code and read-only on the form, and the table
	is allow-on-submit, so the guard that would refuse this is only protecting fields that
	nobody can type into. The history has to keep growing after the proposal is issued -
	that is the whole point of it.
	"""
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()
	return doc


@frappe.whitelist()
def add_version(solar_proposal, solar_design_estimate=None, notes=None):
	"""Re-quote: open a new version of this proposal rather than a second proposal.

	Pass a design estimate to quote a different one - a revised system after the customer
	asked for a bigger array, say. The previous version stays exactly as it was sent.
	"""
	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("write")
	if solar_design_estimate:
		doc.solar_design_estimate = solar_design_estimate
	row = _open_version(doc, notes)
	_save_version_change(doc)
	return {"version_no": row.version_no, "status": doc.status}


@frappe.whitelist()
def record_dispatch(solar_proposal, sent_via="WhatsApp", client_reference=None):
	"""Record that this version went to the customer, and advance the lead's cadence."""
	if sent_via not in DISPATCH_CHANNELS:
		frappe.throw(
			_("{0} is not a way this proposal can be sent.").format(sent_via), title=_("Unknown Channel")
		)
	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("write")

	version = _current_version(doc) or _open_version(doc)
	version.sent_via = sent_via
	version.sent_on = now_datetime()
	version.sent_by = frappe.session.user
	if client_reference:
		version.notes = client_reference
	_save_version_change(doc)

	if doc.lead:
		from a3_sola.api import outreach

		outreach.log_outreach(
			doc.lead,
			channel=sent_via if sent_via in ("WhatsApp", "Email") else "Email",
			outreach_step="Completed: Proposal Sent",
			call_status="Not Applicable",
			outcome=_("Proposal {0} version {1} sent").format(doc.name, version.version_no),
		)
	return {"version_no": version.version_no, "status": doc.status}


@frappe.whitelist()
def record_response(solar_proposal, outcome, client_comments=None, lost_reason=None):
	"""Record what the customer said about the version they were sent.

	Accepting is what makes a commercial quotation possible; it is recorded here rather
	than on the estimate because it is a thing the customer said about a document that
	was sent to them on a date, and that belongs with the dispatch record.
	"""
	if outcome not in CLIENT_OUTCOMES:
		frappe.throw(_("{0} is not a recognised outcome.").format(outcome), title=_("Unknown Outcome"))
	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("write")

	version = _current_version(doc)
	if not version:
		frappe.throw(
			_("Nothing has been sent to the customer yet, so there is no response to record."),
			title=_("No Version Issued"),
		)
	if outcome in ("Rejected", "Lost") and not (lost_reason or "").strip():
		frappe.throw(_("Give the reason this proposal was lost."), frappe.MandatoryError)

	version.outcome = outcome
	version.responded_on = now_datetime()
	version.client_comments = (client_comments or "").strip() or None
	version.lost_reason = (lost_reason or "").strip() or None if outcome in ("Rejected", "Lost") else None
	_save_version_change(doc)
	return {"version_no": version.version_no, "status": doc.status}


@frappe.whitelist()
def generate_proposal(solar_proposal):
	"""Render the PDF, name it on the client's convention, and render the greeting message."""
	from frappe.utils.pdf import get_pdf
	from frappe.utils.print_format import download_pdf  # noqa: F401  (ensures print deps load)

	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("write")

	# The first Generate is what opens version one; there is no document to send before it.
	version = _current_version(doc)
	if not version:
		version = _open_version(doc)
		_save_version_change(doc)
		version = _current_version(doc)

	html = frappe.get_print(doc.doctype, doc.name, print_format="Solar Proposal", no_letterhead=0)
	pdf = get_pdf(html)

	file_name = f"{version.proposal_file_name or doc.proposal_file_name or doc.name}.pdf"
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

	version.proposal_pdf = file_doc.file_url
	doc.greeting_message = render_greeting(doc)
	# `sync_from_versions` puts the PDF and the status on the header from this row.
	_save_version_change(doc)
	return {"file_url": file_doc.file_url, "file_name": file_name, "version_no": version.version_no}


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
	"""Record dispatch of the current version. Kept as the name the desk already calls."""
	record_dispatch(solar_proposal, sent_via=sent_via)
	return frappe.db.get_value("Solar Proposal", solar_proposal, "status")


@frappe.whitelist()
def create_quotation(solar_proposal):
	"""Raise the commercial quotation for the version the customer accepted.

	The proposal is the offer; the quotation is what books it. This does not price anything
	itself - it hands the accepted version's estimate to the same builder the portal's cost
	estimate screen uses, so the items, the taxes and the solar figures are produced exactly
	once and in one place.
	"""
	from a3_sola.api import cost_estimate

	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("read")
	frappe.has_permission("Quotation", "create", throw=True)

	version = _current_version(doc)
	if not version or version.outcome != "Accepted":
		frappe.throw(
			_("Record the customer's acceptance on the current version before raising a quotation."),
			title=_("Not Accepted Yet"),
		)

	existing = frappe.db.get_value("Quotation", {"solar_proposal": doc.name, "docstatus": ["<", 2]}, "name")
	if existing:
		return {"name": existing, "route": cost_estimate.route_of(existing), "existing": True}

	estimate_name = version.solar_design_estimate or doc.solar_design_estimate
	if not estimate_name:
		frappe.throw(_("This version quotes no design estimate."), frappe.MandatoryError)
	estimate = frappe.get_doc("Solar Design Estimate", estimate_name)

	quotation_to, party_name = _quotation_party(doc)
	option = _recommended_option(estimate)

	payload = {
		"company": doc.company,
		"quotation_to": quotation_to,
		"party_name": party_name,
		"solar_consumer": doc.solar_consumer,
		"solar_design_estimate": estimate.name,
		"solar_proposal": doc.name,
		"selected_option": option.option_name if option else None,
		"solar_package": (option.solar_package if option else None) or estimate.solar_package,
		"items": [
			{
				"solar_package": (option.solar_package if option else None) or estimate.solar_package,
				"package_option": option.option_name if option else None,
				"qty": 1,
				"rate": flt(option.total_option_cost) if option else flt(estimate.total_project_cost),
				"description": _("{0} - {1}").format(doc.capacity_label or "", option.option_name if option else "")
				.strip(" -")
				or None,
			}
		],
	}
	summary = cost_estimate.save(payload)
	return {"name": summary["name"], "route": cost_estimate.route_of(summary["name"]), "existing": False}


def _quotation_party(doc):
	"""Who the quotation is addressed to: the consumer's customer if there is one, else the lead."""
	if doc.solar_consumer:
		customer = frappe.db.get_value("Solar Consumer", doc.solar_consumer, "customer")
		if customer:
			return "Customer", customer
	if doc.lead:
		return "Lead", doc.lead
	frappe.throw(
		_("This proposal has neither a customer nor a lead to address a quotation to."),
		frappe.MandatoryError,
		title=_("Nobody to Quote"),
	)


def _recommended_option(estimate):
	for option in estimate.options:
		if option.is_recommended:
			return option
	return estimate.options[0] if estimate.options else None


@frappe.whitelist()
def get_whatsapp_link(solar_proposal):
	"""A wa.me deep link prefilled with the greeting, so sending is one tap."""
	from a3_sola.api import outreach

	doc = frappe.get_doc("Solar Proposal", solar_proposal)
	doc.check_permission("read")
	message = doc.greeting_message or render_greeting(doc)
	return outreach.whatsapp_link(doc.mobile_no, message)
