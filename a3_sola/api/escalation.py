# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The daily escalation engine.

External delay must escalate, not just display. Seventy-five days at feasibility is normal
in Kerala and abnormal elsewhere, and net meter allocation runs two to four weeks - so the
SLA is per DISCOM, configurable, and a breach creates a chase task addressed to the named
Assistant Engineer on the DISCOM Section record rather than to a generic address.

Idempotent, safe to re-run, iterates companies explicitly, never issues an unfiltered query.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate, today

from a3_sola.api import stages
from a3_sola.api.settings import get_int, get_value


def daily_escalation():
	"""Registered through the Solar Operations registry, not written into hooks.py."""
	if not get_value("enable_sla_escalation"):
		return {}

	summary = {}
	for company in frappe.get_all("Company", pluck="name"):
		summary[company] = {
			"stage_breaches": _escalate_stage_breaches(company),
			"portal_overdue": _chase_portal_applications(company),
			"refunds": _chase_refunds(company),
			"loans": _chase_loan_disbursements(company),
			"claims": _chase_subsidy_claims(company),
		}
	frappe.logger("a3_sola").info({"event": "daily_escalation", "summary": summary})
	return summary


def _reminder_window():
	return get_int("escalation_reminder_days", 3) or 3


def _todo_exists(reference_type, reference_name, marker):
	"""One ToDo per breach per reminder window - never re-notify inside it."""
	since = add_days(today(), -_reminder_window())
	return frappe.db.exists(
		"ToDo",
		{
			"reference_type": reference_type,
			"reference_name": reference_name,
			"status": "Open",
			"date": [">=", since],
			"description": ["like", f"%{marker}%"],
		},
	)


def _raise_todo(owner, reference_type, reference_name, description, priority="Medium"):
	if not owner:
		owner = get_value("escalation_role") and _role_holder(get_value("escalation_role"))
	if not owner:
		return None
	return frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": owner,
			"date": today(),
			"priority": priority,
			"description": description,
			"reference_type": reference_type,
			"reference_name": reference_name,
		}
	).insert(ignore_permissions=True).name


def _role_holder(role):
	holders = frappe.get_all(
		"Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent", limit=1
	)
	return holders[0] if holders else None


def _escalate_stage_breaches(company):
	"""Recompute breach flags and chase the party actually holding the job up."""
	raised = 0
	installations = frappe.get_all(
		"Solar Installation",
		filters={
			"company": company,
			"docstatus": 1,
			"status": ["not in", ["Closed", "Cancelled"]],
		},
		pluck="name",
	)
	for name in installations:
		doc = frappe.get_doc("Solar Installation", name)
		stages.recompute(doc)
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)

		for row in doc.stages:
			if not row.is_sla_breached:
				continue
			marker = f"[SLA:{doc.name}:{row.stage_code}]"
			if _todo_exists("Solar Installation", doc.name, marker):
				continue
			owner = doc.project_manager or _role_holder(row.responsible_role)
			chase = _chase_target(doc, row)
			_raise_todo(
				owner,
				"Solar Installation",
				doc.name,
				_("{0} Stage {1} has been open {2} days against an SLA of {3}. Owner: {4}. {5}").format(
					marker, row.stage_name, row.days_in_stage, row.sla_days, row.owner_type, chase
				),
				priority="High",
			)
			raised += 1
	return raised


def _chase_target(installation, row):
	"""Name the person to chase - a section office, not an abstraction."""
	if row.owner_type != "DISCOM" or not installation.discom_section:
		return ""
	section = frappe.db.get_value(
		"DISCOM Section",
		installation.discom_section,
		["section_name", "assistant_engineer_name", "contact_number"],
		as_dict=True,
	)
	if not section:
		return ""
	return _("Chase {0} at the {1} section{2}.").format(
		section.assistant_engineer_name or _("the Assistant Engineer"),
		section.section_name,
		f" ({section.contact_number})" if section.contact_number else "",
	)


def _chase_portal_applications(company):
	"""DISCOM delay needs chasing, not just recording."""
	raised = 0
	rows = frappe.get_all(
		"Portal Application",
		filters={
			"company": company,
			"docstatus": 1,
			"application_status": ["in", ["Submitted", "Under Review", "Query Raised"]],
			"expected_response_date": ["<", today()],
		},
		fields=["name", "application_type", "expected_response_date", "owner", "solar_installation"],
	)
	for row in rows:
		marker = f"[PORTAL:{row.name}]"
		if _todo_exists("Portal Application", row.name, marker):
			continue
		days = date_diff(today(), getdate(row.expected_response_date))
		_raise_todo(
			row.owner,
			"Portal Application",
			row.name,
			_("{0} {1} has been pending {2} days past its expected response date.").format(
				marker, row.application_type, days
			),
			priority="High",
		)
		raised += 1
	return raised


def _chase_refunds(company):
	"""80% of the registration fee is real money and is currently tracked nowhere."""
	raised = 0
	window = get_int("refund_follow_up_days", 30) or 30
	rows = frappe.get_all(
		"Statutory Fee Payment",
		filters={
			"company": company,
			"docstatus": 1,
			"fee_type": "Registration Fee",
			"refund_status": ["in", ["Due", "Claimed"]],
		},
		fields=["name", "refund_claimed_on", "owner", "refundable_amount"],
	)
	for row in rows:
		if row.refund_claimed_on and date_diff(today(), getdate(row.refund_claimed_on)) < window:
			continue
		marker = f"[REFUND:{row.name}]"
		if _todo_exists("Statutory Fee Payment", row.name, marker):
			continue
		_raise_todo(
			row.owner,
			"Statutory Fee Payment",
			row.name,
			_("{0} Registration fee refund of {1} is outstanding.").format(
				marker, frappe.utils.fmt_money(row.refundable_amount, currency="INR")
			),
		)
		raised += 1
	return raised


def _chase_loan_disbursements(company):
	raised = 0
	rows = frappe.get_all(
		"Loan Application",
		filters={
			"company": company,
			"docstatus": 1,
			"status": ["in", ["Sanctioned", "Disbursed (Advance)"]],
		},
		fields=["name", "lender", "lender_branch", "outstanding", "owner"],
	)
	for row in rows:
		if not row.outstanding:
			continue
		marker = f"[LOAN:{row.name}]"
		if _todo_exists("Loan Application", row.name, marker):
			continue
		_raise_todo(
			row.owner,
			"Loan Application",
			row.name,
			_("{0} {1} outstanding from {2}, {3}.").format(
				marker,
				frappe.utils.fmt_money(row.outstanding, currency="INR"),
				row.lender,
				row.lender_branch,
			),
		)
		raised += 1
	return raised


def _chase_subsidy_claims(company):
	raised = 0
	threshold = get_int("subsidy_claim_follow_up_days", 45) or 45
	rows = frappe.get_all(
		"Subsidy Claim",
		filters={
			"company": company,
			"docstatus": 1,
			"claim_status": ["in", ["PCR Uploaded", "Under Verification"]],
		},
		fields=["name", "days_since_pcr", "solar_installation"],
	)
	for row in rows:
		if (row.days_since_pcr or 0) < threshold:
			continue
		marker = f"[CLAIM:{row.name}]"
		if _todo_exists("Subsidy Claim", row.name, marker):
			continue
		manager = frappe.db.get_value("Solar Installation", row.solar_installation, "project_manager")
		_raise_todo(
			manager,
			"Subsidy Claim",
			row.name,
			_("{0} Subsidy claim has been pending {1} days since PCR upload.").format(
				marker, row.days_since_pcr
			),
		)
		raised += 1
	return raised
