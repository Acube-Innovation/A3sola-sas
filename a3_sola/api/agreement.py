# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The net-metering agreement's body text, generated from the chain.

The agreement is a legal instrument written on stamp paper, so its wording is fixed and
lives here as code rather than as seed data a tenant could quietly alter. What varies is
the handful of particulars - who, where, how large, which section - and every one of them
is already recorded upstream on the Lead, the Solar Consumer, the Site Survey, the Design
Estimate, the Solar Installation and the Commissioning Report. Nothing here is re-typed.

Generation is idempotent: running it twice on unchanged sources produces byte-identical
text, which is what lets `is_edited` mean something.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate, now_datetime
from frappe.utils.html_utils import sanitize_html

TITLE = "Agreement for Connecting Solar Energy System to The Distribution System of The Licensee"

#: Voltage recited in Schedule I, by the consumer's connection type. The agreement states
#: the supply voltage, not the phase, so the mapping belongs here and not in a Select.
SUPPLY_VOLTAGE = {
	"Single Phase": "230V, Single Phase",
	"Three Phase": "400V, Three Phase",
}

BLANK = "…………………………"

PREAMBLE = """\
<p>This Memorandum of Agreement is made on {day} day of {month} Year {year} at {place}
between the eligible consumer <b>{consumer_name}</b> residing at {permanent_address} as first
party and the <b>{licensee}</b>, {incorporation} having its registered office at
{registered_office}, represented by {representative} Here in after referred to as
&ldquo;{licensee_short}&rdquo; (which expression shall unless excluded by or repugnant to the
context or meaning thereof, be deemed to include its successors, representatives and assignees)
as second party of the agreement; Whereas, the consumer has installed a solar energy system at
the premises owned and possessed by him and has requested {licensee_short} to provide
connectivity to the said plant.</p>

<p>The {licensee_short} agrees to provide to the consumer, a Solar Plant Identification Number
(SPIN) <b>{spin}</b> as scheduled in the agreement for the electricity generated from the above
plant having capacity <b>{capacity}</b> as per conditions of this agreement and the regulations
or orders issued by the Kerala State Regulatory Commission, from time to time;</p>

<p>And whereas the consumer has in addition to those automatic and inbuilt isolation devices
within the inverter and external manual relays installed, a manually operated isolating switch
and associated equipment with sufficient safeguards between the solar energy system and the
distribution system of {licensee_short} to prevent injection of electricity from his solar
energy system to the distribution system of the licensee when the distribution system is
de-energized;</p>

<p>And whereas, the consumer has assured that in case of a power outage in the system of
{licensee_short}, his/her plant will not inject power into the distribution system of the
licensee and has produced separately the documents substantiating this assurance which form
part of this agreement, as if incorporated herein;</p>

<p>And whereas, the consumer has undertaken that all the equipment connected to the distribution
system comply with relevant international (IEEE/IEC) or Indian Standards (BIS) and that
installation of electrical equipment complies with the relevant provisions of the Central
Electricity Authority (Measures relating to Safety and Electric Supply) Regulations, 2010;</p>

<p>And whereas, the consumer undertakes that he/she is in possession of all the necessary
approvals and clearances, including sanction from Electrical Inspector, as specified in relevant
regulations for connecting the solar energy system to the distribution system for commissioning
the solar energy system.</p>

<p>And whereas, the consumer has provided the solar meter and the net meter at his/her cost,
which has been tested, certified and installed by {licensee_short}.</p>

<p>Now, therefore, both the parties hereby agree as follows:</p>"""

#: The operative clauses, in the order and wording of the executed instrument. Only
#: {licensee_short} and {validity_years} vary; everything else is the regulation talking.
CLAUSES = [
	"The net-metering connection shall be governed by the provisions contained in the Kerala "
	"State Electricity Regulatory Commission (Grid Interactive Distributed Solar Energy Systems) "
	"Regulations 2014 as amended from time to time and also subject to the condition that the "
	"solar energy system meets the requirement as per the provisions contained in Central "
	"Electricity Authority (Technical Standard for Connectivity of the Distributed Generation "
	"Resources) Regulations, 2013.",

	"{licensee_short} shall have the sole authority to decide, based on the results of necessary "
	"studies, the interface/interconnection point to the solar energy system.",

	"The validity of the agreement will be {validity_years} years from the date of this agreement.",

	"If the consumer&rsquo;s solar energy system either causes damage to and/or produces adverse "
	"effects affecting other consumers or assets of {licensee_short}, the consumer will have to "
	"disconnect the solar energy system immediately from the distribution system, upon direction "
	"from the {licensee_short} and correct the defect at his own expense, prior to reconnection.",

	"{licensee_short} shall have access to the net metering equipment and disconnecting means for "
	"the solar energy system in all required situations.",

	"{licensee_short} shall have the right to disconnect solar energy system from the distribution "
	"system of the licensee in emergency, if it is found that at that point in time providing "
	"service through the net metering system is not safe to the grid as a whole.",

	"(a) The consumer indemnifies {licensee_short} for the damages or adverse effects, if any, from "
	"the negligence or intentional defective operation in the connection and operation of the solar "
	"energy system of the consumer.<br>(b) {licensee_short} indemnifies the consumer for the damages "
	"or adverse effects, if any, from the negligence or intentional defective operation in the "
	"connection and operation of the distribution system of {licensee_short}.",

	"{licensee_short} shall not be liable for delivery to or re-energization by the eligible consumer "
	"of any fiscal or other incentives provided by the Central/State Government or any other authority.",

	"All the commercial settlements under this agreement shall follow the provisions of the Kerala "
	"State Electricity Regulatory Commission (Grid Interactive Distributed Solar Energy Systems) "
	"Regulations, 2014.",

	"The consumer may terminate this agreement after giving thirty days (30 days) clear notice in "
	"writing to the authorized authority of the licensee.",

	"{licensee_short} has the right to terminate this agreement at any point in time after giving "
	"30 days&rsquo; prior notice, if the consumer breaches any terms of this agreement and in cases "
	"where such breaches could be rectified and the same are not provided/informed within 30 days of "
	"written notice from {licensee_short} about the breach.",

	"The consumer agrees that upon termination of this agreement, he must disconnect the solar energy "
	"system from distribution system of {licensee_short} in a timely manner to the satisfaction of "
	"{licensee_short}.",

	"The consumer shall have the right to bank and use the electricity generated and injected in "
	"excess over his/her full consumption, into the distribution system of the licensee by the solar "
	"energy system, subject to the conditions specified in the Kerala State Electricity Regulatory "
	"Commission (Grid Interactive Distributed Solar Energy Systems) Regulations, 2014.",

	"The consumer shall have the right to open access for wheeling the electricity generated in "
	"excess by 500 units over the consumption, by the solar energy system, installed in the premises "
	"of the consumer detailed under item II of the schedule attached and shall be used in the "
	"premises owned by the consumer and in the order of preference as detailed under item III of the "
	"attached schedule.",

	"The licensee shall within seven days from the date of execution of this agreement commission the "
	"solar energy system.",

	"The licensee shall pay for the net energy banked by the consumer at the end of the settlement "
	"period at the average pooled purchase cost of electricity as approved by the Commission for that "
	"year, as provided for in the Kerala State Electricity Regulatory Commission (Grid Interactive "
	"Distributed Solar Energy Systems) Regulations, 2014.",
]

ATTESTATION = """\
<p>In witness whereof the said <b>{consumer_name}</b> (1st party) and the said
<b>{representative}</b> (2nd party) have hereunto signed at {place} the day and year first
above written.</p>"""


# --------------------------------------------------------------------------- sources


def pull_sources(doc):
	"""Fill the schedules from the chain. Every value here has an upstream owner.

	Only blanks are filled, so a correction typed on the agreement survives a regenerate.
	Called from `Solar Agreement.validate`, and safe to call repeatedly.
	"""
	installation = frappe.get_cached_doc("Solar Installation", doc.solar_installation)
	consumer = (
		frappe.get_cached_doc("Solar Consumer", installation.solar_consumer)
		if installation.solar_consumer
		else None
	)
	estimate = _estimate(doc, installation, consumer)
	survey = _survey(doc, estimate, consumer)

	doc.solar_consumer = installation.solar_consumer
	# Not `or`: a new document arrives carrying the session's default company, which is
	# whichever tenant the user last looked at. The agreement belongs to the installation.
	doc.company = installation.company
	doc.solar_design_estimate = doc.solar_design_estimate or installation.solar_design_estimate
	doc.site_survey = doc.site_survey or (survey and survey.name)
	doc.solar_design_estimate = doc.solar_design_estimate or (estimate and estimate.name)
	doc.lead = doc.lead or (estimate and estimate.lead) or (consumer and consumer.lead)
	doc.discom = doc.discom or installation.discom or (consumer and consumer.discom)

	_fill_second_party(doc)
	_fill_schedule_1(doc, consumer)
	_fill_schedule_2(doc, installation, consumer, survey)
	return doc


def _estimate(doc, installation, consumer):
	name = doc.solar_design_estimate or installation.solar_design_estimate
	if not name and consumer:
		name = frappe.db.get_value(
			"Solar Design Estimate",
			{"solar_consumer": consumer.name, "docstatus": ["<", 2]},
			"name",
			order_by="creation desc",
		)
	return frappe.get_cached_doc("Solar Design Estimate", name) if name else None


def _survey(doc, estimate, consumer):
	name = doc.site_survey or (estimate and estimate.site_survey)
	if not name and consumer:
		name = frappe.db.get_value(
			"Site Survey",
			{"solar_consumer": consumer.name, "docstatus": ["<", 2]},
			"name",
			order_by="creation desc",
		)
	return frappe.get_cached_doc("Site Survey", name) if name else None


def _fill_second_party(doc):
	"""The licensee signs under its legal name, which the DISCOM record holds."""
	if not doc.discom:
		return
	legal, office, recital, discom_name = frappe.db.get_value(
		"DISCOM",
		doc.discom,
		["legal_name", "registered_office", "incorporation_recital", "discom_name"],
	) or (None, None, None, None)
	# `doc.discom` is an autonamed series, never a name anyone would sign under.
	doc.second_party_legal_name = doc.second_party_legal_name or legal or discom_name
	doc.second_party_office = doc.second_party_office or office
	doc.second_party_incorporation = doc.second_party_incorporation or recital


def _fill_schedule_1(doc, consumer):
	if not consumer:
		return
	doc.consumer_name = doc.consumer_name or consumer.consumer_name
	doc.permanent_address = doc.permanent_address or address_text(consumer.installation_address)
	if not doc.consumer_number_and_category:
		doc.consumer_number_and_category = " / ".join(
			p for p in (consumer.consumer_number, consumer.tariff_category or consumer.consumer_category) if p
		)
	doc.supply_voltage = doc.supply_voltage or SUPPLY_VOLTAGE.get(consumer.connection_type)
	if not doc.connected_load_or_contract_demand:
		doc.connected_load_or_contract_demand = _load_text(consumer)


def _load_text(consumer):
	"""Connected load for LT, contract demand for HT - the agreement asks for either."""
	if consumer.sanctioned_load_kw:
		return f"{flt(consumer.sanctioned_load_kw):g}kW"
	if consumer.connected_load_watts:
		return f"{flt(consumer.connected_load_watts) / 1000:g}kW"
	return None


def _fill_schedule_2(doc, installation, consumer, survey):
	doc.installation_address = doc.installation_address or (
		consumer and address_text(consumer.installation_address)
	)
	doc.spin = doc.spin or installation.spin or (consumer and consumer.spin)
	doc.plant_capacity_kwp = doc.plant_capacity_kwp or flt(installation.capacity_kw)
	if not doc.electrical_section and installation.discom_section:
		doc.electrical_section = frappe.db.get_value(
			"DISCOM Section", installation.discom_section, "section_name"
		)

	if doc.commissioning_report:
		report = frappe.get_cached_doc("Commissioning Report", doc.commissioning_report)
		doc.solar_meter_number = doc.solar_meter_number or report.net_meter_serial_no
		doc.solar_meter_make = doc.solar_meter_make or report.net_meter_make
		# `not` rather than `is None`: a Float field is 0.0 on a new document, never None,
		# so an `is None` test would have filled this exactly never.
		if not doc.solar_meter_initial_reading:
			doc.solar_meter_initial_reading = flt(report.initial_export_reading)
	# The meter *type* is a property of the meter, not of the commissioning, so it comes
	# from the survey whether or not the job has been commissioned.
	if not doc.solar_meter_type and survey:
		doc.solar_meter_type = survey.existing_meter_type

	if consumer:
		doc.local_body_type = doc.local_body_type or consumer.local_body_type
		doc.local_body_name = doc.local_body_name or consumer.local_body_name
		doc.village = doc.village or consumer.village
		doc.survey_number = doc.survey_number or consumer.survey_number
		doc.gps_coordinates = doc.gps_coordinates or consumer.gps_coordinates or _gps(consumer)


def _gps(consumer):
	if consumer.latitude and consumer.longitude:
		return f"{flt(consumer.latitude):.6f}, {flt(consumer.longitude):.6f}"
	return None


def address_text(address):
	"""One-line address, the way the agreement recites it."""
	if not address:
		return ""
	doc = frappe.get_cached_doc("Address", address)
	parts = [doc.address_line1, doc.address_line2, doc.city, doc.state, doc.pincode]
	return ", ".join(str(p).strip() for p in parts if p)


# --------------------------------------------------------------------------- render


def build_context(doc):
	"""Every substitution the body makes, resolved once."""
	date = getdate(doc.agreement_date) if doc.agreement_date else None
	# Never `doc.discom`: that is a record id, and a record id is not a party to anything.
	# A blank prints as a line for someone to complete, which is the honest failure.
	licensee = doc.second_party_legal_name or BLANK
	return {
		"day": _ordinal(date.day) if date else BLANK,
		"month": formatdate(date, "MMMM") if date else BLANK,
		"year": date.year if date else BLANK,
		"place": doc.place_of_execution or BLANK,
		"consumer_name": doc.consumer_name or BLANK,
		"permanent_address": doc.permanent_address or BLANK,
		"licensee": licensee,
		"licensee_short": _short(licensee),
		"incorporation": doc.second_party_incorporation or "",
		"registered_office": doc.second_party_office or BLANK,
		# The honorific belongs to the value, not to the sentence: an officer who is a
		# Smt must not be printed as a Shri because the template said so.
		"representative": doc.discom_representative_name or f"Shri {BLANK}",
		"spin": doc.spin or BLANK,
		"capacity": f"{flt(doc.plant_capacity_kwp):g}kWp" if doc.plant_capacity_kwp else BLANK,
		"validity_years": cint(doc.validity_years) or 25,
	}


def _short(licensee):
	"""KSEB Limited, not Kerala State Electricity Board Limited, once the parties are named."""
	if "Kerala State Electricity Board" in licensee:
		return "KSEB Limited"
	return licensee


def _ordinal(day):
	suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
	return f"{day}{suffix}"


def render(doc):
	"""The agreement body as HTML: preamble, numbered clauses, attestation.

	The schedules are deliberately absent - they are the doctype's own fields, so the
	print format renders them as tables and they stay editable and reportable.

	The output is put through the same sanitiser the Text Editor field applies on save.
	Without that, generation would never equal what was stored - bleach rewrites a style
	attribute cosmetically - and `is_edited` would fire on text nobody had touched.
	"""
	context = build_context(doc)
	clauses = "\n".join(f"<li>{clause.format(**context)}</li>" for clause in CLAUSES)
	html = "\n".join(
		[
			f'<p style="text-align:center"><b>{TITLE}</b></p>',
			PREAMBLE.format(**context),
			f"<ol>\n{clauses}\n</ol>",
			ATTESTATION.format(**context),
		]
	)
	return sanitize_html(html, linkify=True)


def is_edited(doc):
	"""True when the stored text is not what generation would now produce."""
	return _normalise(doc.agreement_text) != _normalise(render(doc))


def _normalise(html):
	return " ".join((html or "").split())


# --------------------------------------------------------------------------- action


@frappe.whitelist()
def generate(agreement, force=0):
	"""Regenerate the body from the current sources.

	Refuses to overwrite hand-edited text unless `force`, because the edit may be the
	negotiated wording and it exists nowhere else.
	"""
	doc = frappe.get_doc("Solar Agreement", agreement)
	doc.check_permission("write")

	if doc.docstatus != 0:
		frappe.throw(_("A submitted agreement cannot be regenerated. Amend it instead."))
	if doc.stamp_paper_status != "Purchased":
		frappe.throw(
			_("Record the stamp paper first. The agreement is written on it, so there is nothing "
			  "to generate until it is bought."),
			title=_("Stamp Paper Not Purchased"),
		)
	if doc.agreement_text and doc.is_edited and not cint(force):
		frappe.throw(
			_("This text was edited after it was generated. Regenerating discards those edits."),
			title=_("Edited Text"),
			exc=frappe.ValidationError,
		)

	pull_sources(doc)
	doc.agreement_text = render(doc)
	doc.generated_on = now_datetime()
	doc.generated_by = frappe.session.user
	doc.is_edited = 0
	doc.save()
	return doc.agreement_text
