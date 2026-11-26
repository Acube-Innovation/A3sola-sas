# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal a visitor registered at an event receives on WhatsApp, in place of a brochure.

It is the company's own proposal - a Solar Design Estimate and a Solar Proposal of the
visitor's lead, printed as every proposal is (Solar Proposal Document) - made from what the
visitor told the form: their name, district and bill. The bill sized the system and chose the
package (api/instant_estimate); of that package's Pricing Options the lowest priced one is
quoted, as the one option of the proposal.

The design estimate is made while the form is sent (`prepare`), and the figures the visitor
sees on the thank-you page are read from it - the price, subsidy and size the PDF prints. The
visitor's link prints the proposal live (`pdf_for`); the PDF filed on the proposal for staff
is rendered in the background (`queue`).

A lead has one proposal. A visitor who registers again with another bill has the proposal made
for them re-quoted to the new size - while it has not gone to them; one that has, or one staff
made, is theirs as it stands, and the thank-you page shows its figures.
"""

import json

import frappe
from frappe.utils import flt, today

from a3_sola.api.instant_estimate import lowest_option

LEAD = "Lead"
PROPOSAL = "Solar Proposal"
ESTIMATE = "Solar Design Estimate"
#: Marks the option row of an estimate made here, so a later registration may re-quote it.
MARK = "From the visitor's event registration"


def proposal_of(lead):
	"""The lead's proposal (draft or issued), or None."""
	return frappe.db.get_value(PROPOSAL, {"lead": lead, "docstatus": ["<", 2]}, "name") if lead else None


def can_make(lead):
	"""Whether a proposal can be made for this lead from its event estimate: a home on the grid,
	on-grid or hybrid, priced on a package of its system (an off-grid system, or a shop or a
	factory, is designed by our engineer after a visit). An estimate saved before packages were
	chosen by system - a battery one without `system_type` - was priced on an on-grid package:
	no proposal from it."""
	est = _estimate(lead)
	if est and est.get("battery") and est.get("system_type") != "Hybrid":
		return False
	return bool(est and est.get("package") and not est.get("larger")
		and (lead.get("a3s_interest") or "Home") == "Home" and frappe.db.exists("Solar Package", est["package"]))


def has_proposal(lead):
	"""Whether the visitor has, or can be given, a proposal - what their link and message offer.
	Never while their estimate is custom (no package covers it): our engineer designs that one,
	even if an earlier visit left them a proposal."""
	if (_estimate(lead) or {}).get("custom"):
		return False
	return bool(proposal_of(lead.name) or can_make(lead))


def queue(proposal, after_commit=True):
	"""Render the proposal's PDF in the background - after this request commits - by the
	proposal's own job (solar_proposal.auto_generate), which a saved design estimate queues as
	well, so the two are one. It runs as the proposal's owner, who may print it: the job runs as
	whoever queued it, and a visitor is a Guest."""
	user = frappe.session.user
	owner = frappe.db.get_value(PROPOSAL, proposal, "owner")
	if owner:
		frappe.set_user(owner)
	try:
		frappe.enqueue("a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.auto_generate", queue="short",
			job_id=f"proposal-pdf::{proposal}", deduplicate=True, enqueue_after_commit=after_commit,
			solar_proposal=proposal)
	finally:
		frappe.set_user(user)


def prepare(lead):
	"""The lead's proposal and design estimate made, or re-quoted to its latest event estimate
	(see the module), without the PDF: {proposal, figures, changed}, or None when there is no
	proposal for this visitor. `figures` are the proposal's own - what its PDF prints.

	A re-quote saves the design estimate only: the proposal follows it when its PDF is filed
	by its own job (queued by that save), the one thing here that saves it.

	Run as the event's lead owner - they own what is made, as they own the lead - and with the
	lead locked, so the form and an early click make one, not two. A failure is logged and
	undone, leaving the registration as it was."""
	if not frappe.db.exists(LEAD, lead):
		return None
	frappe.db.sql("select name from `tabLead` where name=%s for update", lead)
	doc = frappe.get_doc(LEAD, lead)
	existing = proposal_of(lead)
	if not existing and not can_make(doc):
		return None
	owner = frappe.db.get_value("Solar Event", doc.a3s_event, "lead_owner") if doc.get("a3s_event") else None
	user = frappe.session.user
	frappe.db.savepoint("event_proposal")
	if owner:
		frappe.set_user(owner)
	try:
		changed = False
		if existing:
			proposal = frappe.get_doc(PROPOSAL, existing)
			estimate = _ours(proposal)
			changed = bool(estimate and can_make(doc) and _requote(doc, estimate))
		else:
			proposal = _make_proposal(doc, _make_estimate(doc))
			changed = True
		figures = _figures(proposal)
	except Exception:
		frappe.db.rollback(save_point="event_proposal")
		frappe.log_error(frappe.get_traceback(), f"a3_sola: event proposal for {lead}")
		return None
	finally:
		frappe.set_user(user)
	return {"proposal": proposal.name, "figures": figures, "changed": changed}


def pdf_for(lead):
	"""(file name, bytes) of the visitor's proposal as it stands - made now if the form could
	not make it - or None when there is none for them.

	Printed live from the proposal and its design estimate, as a customer's shared link prints
	it (api/portal_share): always the design as it is now, and nothing saved, so it never meets
	the background render that files the PDF on the proposal for staff (`queue`)."""
	from a3_sola.api import portal_share

	name = proposal_of(lead) or (prepare(lead) or {}).get("proposal")
	if not name:
		return None
	frappe.db.commit()  # what the form saved, read as it is now (repeatable read)
	doc = frappe.get_doc(PROPOSAL, name)
	if doc.docstatus == 0 and _ours(doc):
		# Its header as its design is now, in memory: a re-quote saved the estimate only.
		doc.fill_design_estimates()
		doc.pull_from_estimate()
	frappe.flags.ignore_print_permissions = True
	try:
		content = portal_share._pdf(doc)
	finally:
		frappe.flags.ignore_print_permissions = False
	from a3_sola.api.portal_proposal import customer_file_name

	return customer_file_name(doc), content


def _estimate(lead):
	raw = lead.get("a3s_estimate")
	try:
		return json.loads(raw) if raw else None
	except ValueError:
		return None


def _sizing(lead):
	"""The option row - and the estimate's header - for the lead's event estimate: its package
	at the lowest Pricing Options row."""
	est = _estimate(lead)
	package = frappe.get_cached_doc("Solar Package", est["package"])
	phase = est.get("connection_type") or package.connection_type or "Single Phase"
	option = lowest_option(package.name, phase)
	return {"solar_package": package.name, "connection_type": phase, "override_capacity_kw": flt(package.capacity_kw),
		# The visitor's answer, where the package allows it: only a DCR package has the subsidy.
		"subsidy_option": "With Subsidy" if package.is_dcr_compliant and est.get("subsidy_option") != "Without Subsidy"
			else "Without Subsidy",
		"system_type": package.system_type or "On-Grid", "pricing_option": option.name if option else None}


def _make_estimate(lead):
	sizing = _sizing(lead)
	doc = frappe.new_doc(ESTIMATE)
	doc.update({"company": lead.company, "lead": lead.name, "estimate_date": today(), "consumer_category": "Residential",
		**{k: v for k, v in sizing.items() if k != "pricing_option"}})
	doc.append("sizing_options", {**sizing, "is_recommended": 1, "option_notes": MARK})
	_save(doc)
	return doc


def _ours(proposal):
	"""The design estimate of a proposal made here and not yet gone to the visitor - the one it
	quotes, marked - else None: that proposal is not to be re-quoted."""
	from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import _current_version, version_is_out

	if proposal.docstatus != 0 or version_is_out(_current_version(proposal)) or len(proposal.design_estimates) != 1:
		return None
	estimate = frappe.get_doc(ESTIMATE, proposal.design_estimates[0].solar_design_estimate)
	row = estimate.recommended_sizing_row()
	if estimate.docstatus != 0 or not row or not (row.option_notes or "").startswith(MARK):
		return None
	return estimate


def _requote(lead, estimate):
	"""The estimate moved to the lead's latest event estimate; False when it already is."""
	sizing = _sizing(lead)
	row = estimate.recommended_sizing_row()
	if all(row.get(k) == v for k, v in sizing.items() if k != "override_capacity_kw") \
			and flt(row.override_capacity_kw) == sizing["override_capacity_kw"]:
		return False
	row.update(sizing)
	# The header too: a header that differs from before the save is written into the row.
	estimate.update({k: v for k, v in sizing.items() if k != "pricing_option"})
	estimate.estimate_date = today()
	_save(estimate)
	return True


def _save(doc):
	doc.flags.ignore_permissions = True
	doc.flags.in_test = True  # no "sizing is bound by" alert: nobody is looking at a form
	if doc.is_new():
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)
	doc.flags.in_test = False


def _make_proposal(lead, estimate):
	"""The lead's proposal, quoting the one estimate; its PDF is made after."""
	doc = frappe.new_doc(PROPOSAL)
	doc.update({"company": lead.company, "lead": lead.name, "proposal_date": today()})
	doc.append("design_estimates", {"solar_design_estimate": estimate.name})
	doc.flags.ignore_permissions = True
	doc.flags.from_auto_generate = True  # queued by the form (`queue`), as its owner
	doc.insert(ignore_permissions=True)
	if frappe.get_meta(LEAD).has_field("solar_proposal") and not lead.get("solar_proposal"):
		frappe.db.set_value(LEAD, lead.name, "solar_proposal", doc.name, update_modified=False)
	return doc


def _figures(proposal):
	"""What the proposal's PDF prints: its size (kWp) and, from its base design estimate's
	commercials, the price, the subsidy and the price after it."""
	estimate = frappe.get_doc(ESTIMATE, proposal.solar_design_estimate)
	price = flt(estimate.commercials().get("total")) or flt(estimate.total_project_cost)
	subsidy = flt(estimate.applicable_subsidy_amount) if estimate.subsidy_option == "With Subsidy" else 0.0
	return {"kw": round(flt(estimate.final_capacity_kw), 2), "price": round(price), "subsidy": round(subsidy),
		"net": round(price - subsidy)}
