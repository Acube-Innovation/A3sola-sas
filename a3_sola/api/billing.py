# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Milestone billing.

The client bills 70% as advance with the purchase order, 20% after delivery and
installation, and 10% after commissioning - with an important variant: where the net meter
is availed from the DISCOM rather than purchased, the final 10% follows submission of the
completion documents, because DISCOM allocation runs two to four weeks and they cannot hold
the balance that long. Both are seeded templates, so the choice is configuration.

ABSOLUTE RULE: the subsidy never appears on a customer invoice as a line item, a discount
or a tax. The customer is invoiced the gross contract value across the milestones; the
subsidy is a separate government transfer to the customer.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, today

from a3_sola.api import gst
from a3_sola.api.settings import get_value

FORBIDDEN_WORD = "subsidy"


# ------------------------------------------------------------ template resolution
def resolve_template(company, consumer_category=None, net_meter_mode=None, is_financed=False):
	"""Pick the milestone template matching the job's funding and meter arrangement."""
	candidates = frappe.get_all(
		"Billing Milestone Template",
		filters={"company": company, "is_active": 1},
		fields=[
			"name", "applicable_consumer_category", "applicable_net_meter_mode",
			"applicable_funding", "is_default",
		],
	)
	if not candidates:
		return None

	funding = "Financed" if is_financed else "Self Funded"

	def score(row):
		points = 0
		if row.applicable_funding == funding:
			points += 4
		elif row.applicable_funding not in ("Any", None, ""):
			return -100
		if net_meter_mode and row.applicable_net_meter_mode == net_meter_mode:
			points += 3
		elif row.applicable_net_meter_mode not in ("Any", None, ""):
			return -100
		if consumer_category and row.applicable_consumer_category == consumer_category:
			points += 1
		if row.is_default:
			points += 1
		return points

	best = max(candidates, key=score)
	if score(best) < 0:
		best = next((c for c in candidates if c.is_default), None)
	return best.name if best else None


def build_plan(plan):
	"""Populate milestones from the template and verify they total the contract value."""
	if plan.milestones:
		return plan
	if not plan.milestone_template:
		plan.milestone_template = resolve_template(
			plan.company, plan.consumer_category, plan.net_meter_mode, plan.is_financed
		)
	if not plan.milestone_template:
		frappe.throw(
			_("No billing milestone template matches this job. A billing plan cannot be built without one."),
			title=_("Milestone Template Missing"),
		)

	template = frappe.get_cached_doc("Billing Milestone Template", plan.milestone_template)
	contract = flt(plan.gross_contract_value)
	for row in template.milestones:
		amount = flt(contract * flt(row.percentage) / 100.0, 2)
		plan.append(
			"milestones",
			{
				"milestone_name": row.milestone_name,
				"trigger_type": row.trigger_type,
				"trigger_stage_code": row.trigger_stage_code,
				"percentage": row.percentage,
				"milestone_amount": amount,
				"funding_source": row.funding_source,
				"due_date": add_days(today(), int(row.credit_days or 0)),
				"remarks": row.description,
			},
		)
	return plan


def recompute_summary(plan):
	"""Rebuild every summary figure from the linked invoices and payments."""
	total_planned = total_triggered = total_invoiced = total_collected = 0.0

	for row in plan.milestones:
		total_planned += flt(row.milestone_amount)
		if row.is_triggered:
			total_triggered += flt(row.milestone_amount)
		if row.sales_invoice and frappe.db.exists("Sales Invoice", row.sales_invoice):
			invoice = frappe.db.get_value(
				"Sales Invoice",
				row.sales_invoice,
				["grand_total", "outstanding_amount", "status", "docstatus"],
				as_dict=True,
			)
			row.invoice_status = invoice.status
			if invoice.docstatus == 1:
				row.invoiced_amount = flt(invoice.grand_total)
				row.outstanding = flt(invoice.outstanding_amount)
				row.paid_amount = flt(invoice.grand_total) - flt(invoice.outstanding_amount)
				total_invoiced += row.invoiced_amount
				total_collected += row.paid_amount
		else:
			row.invoiced_amount = row.paid_amount = row.outstanding = 0

	plan.total_planned = flt(total_planned, 2)
	plan.total_triggered = flt(total_triggered, 2)
	plan.total_invoiced = flt(total_invoiced, 2)
	plan.total_collected = flt(total_collected, 2)
	plan.total_outstanding = flt(total_invoiced - total_collected, 2)
	plan.unbilled_balance = flt(flt(plan.gross_contract_value) - total_invoiced, 2)
	plan.billing_completion_percent = (
		flt(total_invoiced * 100.0 / flt(plan.gross_contract_value), 2)
		if flt(plan.gross_contract_value)
		else 0.0
	)
	plan.net_payable_by_customer = flt(
		flt(plan.gross_contract_value) - flt(plan.expected_subsidy_amount), 2
	)
	_recompute_statutory(plan)
	return plan


def _recompute_statutory(plan):
	"""Reimbursement and refund sit outside the contract value entirely."""
	if not plan.solar_installation:
		return
	rows = frappe.get_all(
		"Statutory Fee Payment",
		filters={"solar_installation": plan.solar_installation, "docstatus": 1},
		fields=[
			"amount_gross", "paid_by", "reimbursed_amount", "refundable_amount",
			"refund_received_amount",
		],
	)
	paid = sum(flt(r.amount_gross) for r in rows if r.paid_by == "Company on Behalf of Customer")
	reimbursed = sum(flt(r.reimbursed_amount) for r in rows)
	plan.statutory_fees_paid_by_company = flt(paid, 2)
	plan.statutory_reimbursed = flt(reimbursed, 2)
	plan.statutory_outstanding = flt(paid - reimbursed, 2)
	plan.registration_refund_expected = flt(sum(flt(r.refundable_amount) for r in rows), 2)
	plan.registration_refund_received = flt(sum(flt(r.refund_received_amount) for r in rows), 2)


# ------------------------------------------------------------------- triggering
#: Trigger types that name a task without carrying its code.
IMPLIED_TRIGGER_CODES = {"On Order": "ORD", "On Commissioning": "COMM"}
#: Old chain codes still found on templates and untriggered plans, and the task they mean.
TRIGGER_CODE_MAP = {"INST": "IWOI", "KTST": "KFORMS", "AGMT": "STMP", "PCR": "SUBREQ"}


def _milestone_matches(row, task_code):
	if row.trigger_stage_code:
		return TRIGGER_CODE_MAP.get(row.trigger_stage_code, row.trigger_stage_code) == task_code
	return IMPLIED_TRIGGER_CODES.get(row.trigger_type) == task_code


def ensure_plan_for_installation(installation, replay=True):
	"""The job's billing plan, created at the order so the advance milestone exists when
	the advance is collected. Idempotent. Returns the plan name, or None when the job
	cannot carry one yet (no customer, no contract value, no milestone template).

	`replay` fires the milestones of tasks already completed - a job picked up mid-way -
	without the accounts ToDos or auto-invoices a live completion would raise.
	"""
	doc = (
		frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	)
	existing = frappe.db.get_value(
		"Solar Billing Plan", {"solar_installation": doc.name, "docstatus": ["<", 2]}, "name"
	)
	if existing:
		return existing
	if not (doc.customer and flt(doc.gross_contract_value)):
		return None
	consumer_category = frappe.db.get_value("Solar Consumer", doc.solar_consumer, "consumer_category")
	plan = frappe.get_doc(
		{
			"doctype": "Solar Billing Plan",
			"company": doc.company,
			"project": doc.get("project") or None,
			"solar_installation": doc.name,
			"customer": doc.customer,
			"sales_order": doc.sales_order,
			"consumer_category": consumer_category,
			"net_meter_mode": doc.net_meter_mode,
			"is_financed": doc.is_financed,
			"gross_contract_value": doc.gross_contract_value,
			"expected_subsidy_amount": doc.expected_subsidy_amount,
		}
	)
	plan.flags.ignore_permissions = True
	try:
		plan.insert(ignore_permissions=True)
		plan.submit()
	except frappe.ValidationError:
		frappe.log_error(frappe.get_traceback(), f"a3_sola: billing plan for {doc.name}")
		return None
	if replay:
		replay_completed_tasks(doc)
	return plan.name


def replay_completed_tasks(installation):
	"""Fire what has already happened, quietly: no ToDos, no invoices."""
	doc = (
		frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	)
	previous = frappe.flags.a3s_replaying_triggers
	frappe.flags.a3s_replaying_triggers = True
	try:
		for row in doc.stages:
			if row.status == "Completed":
				on_stage_completed(doc.name, row.stage_code)
		for task in frappe.get_all(
			"Installation Task",
			filters={"solar_installation": doc.name, "docstatus": 1, "status": "Completed",
			         "task_code": ["in", ["ADV", "BAL"]], "payer": "Bank"},
			fields=["name", "task_code", "amount", "payment_reference"],
		):
			if flt(task.amount):
				on_loan_disbursed(
					doc.name, "Advance" if task.task_code == "ADV" else "Balance", task.amount,
					task.payment_reference or task.name,
				)
	finally:
		frappe.flags.a3s_replaying_triggers = previous


def on_stage_completed(installation, stage_code):
	"""Mark the mapped milestone triggered when a task completes."""
	plans = frappe.get_all(
		"Solar Billing Plan",
		filters={"solar_installation": installation, "docstatus": 1},
		pluck="name",
	)
	replaying = bool(frappe.flags.a3s_replaying_triggers)
	for name in plans:
		plan = frappe.get_doc("Solar Billing Plan", name)
		changed = False
		for row in plan.milestones:
			if row.is_triggered or row.trigger_type in ("On Date", "Manual", "On Loan Disbursement"):
				continue
			if not _milestone_matches(row, stage_code):
				continue
			row.is_triggered = 1
			row.triggered_on = today()
			changed = True
			if replaying:
				continue
			_notify_accounts(plan, row)
			if get_value("auto_create_invoice_on_milestone"):
				try:
					create_milestone_invoice(plan.name, row.milestone_name)
				except Exception:
					frappe.log_error(frappe.get_traceback(), f"a3_sola: milestone invoice {plan.name}")
		if changed:
			recompute_summary(plan)
			plan.flags.ignore_validate_update_after_submit = True
			plan.save(ignore_permissions=True)


def on_loan_disbursed(installation, tranche, amount, reference):
	"""Settle a lender-funded milestone against a Phase 2 disbursement tranche.

	An amount mismatch is flagged for review rather than guessed at.
	"""
	plans = frappe.get_all(
		"Solar Billing Plan",
		filters={"solar_installation": installation, "docstatus": 1},
		pluck="name",
	)
	for name in plans:
		plan = frappe.get_doc("Solar Billing Plan", name)
		# The advance settles the first lender-funded milestone, the balance the last.
		lender_rows = [r for r in plan.milestones if r.funding_source == "Lender"]
		if not lender_rows:
			continue
		target = lender_rows[0] if tranche == "Advance" else lender_rows[-1]
		if target.matched_disbursement:
			continue

		target.is_triggered = 1
		target.triggered_on = today()
		target.matched_disbursement = reference
		if abs(flt(amount) - flt(target.milestone_amount)) > 1:
			target.remarks = _(
				"Tranche {0} of {1} does not match the milestone amount {2} - review before invoicing."
			).format(reference, flt(amount), flt(target.milestone_amount))
			frappe.msgprint(target.remarks, title=_("Disbursement Mismatch"), indicator="orange")

		recompute_summary(plan)
		plan.flags.ignore_validate_update_after_submit = True
		plan.save(ignore_permissions=True)


def _notify_accounts(plan, row):
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"date": today(),
			"priority": "Medium",
			"description": _("Milestone {0} triggered on {1} - {2} is now billable.").format(
				row.milestone_name, plan.project or plan.solar_installation,
				frappe.utils.fmt_money(row.milestone_amount, currency="INR")
			),
			"reference_type": "Solar Billing Plan",
			"reference_name": plan.name,
		}
	).insert(ignore_permissions=True)


# --------------------------------------------------------------------- invoicing
@frappe.whitelist()
def create_milestone_invoice(billing_plan, milestone_name):
	"""Build a DRAFT Sales Invoice for one milestone. NEVER auto-submit."""
	plan = frappe.get_doc("Solar Billing Plan", billing_plan)
	plan.check_permission("write")

	row = next((r for r in plan.milestones if r.milestone_name == milestone_name), None)
	if not row:
		frappe.throw(_("Milestone {0} is not on this plan.").format(milestone_name))
	if row.sales_invoice and frappe.db.exists("Sales Invoice", row.sales_invoice):
		return row.sales_invoice
	if not row.is_triggered:
		frappe.throw(_("Milestone {0} has not been triggered yet.").format(milestone_name))

	_check_predecessors(plan, row)

	rule = plan.gst_valuation_rule or gst.resolve_valuation(plan.company, plan.consumer_category)
	capacity = (
		frappe.db.get_value("Solar Installation", plan.solar_installation, "capacity_kw")
		if plan.solar_installation
		else None
	)
	items = gst.build_invoice_items(plan.project, row.milestone_amount, rule, capacity_kw=capacity)

	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": plan.company,
			"customer": plan.customer,
			"posting_date": today(),
			"due_date": row.due_date or today(),
			"project": plan.project or None,
			"solar_installation": plan.solar_installation,
			"solar_billing_plan": plan.name,
			"billing_milestone": row.milestone_name,
			"items": items,
		}
	)
	invoice.flags.ignore_permissions = True
	invoice.insert(ignore_permissions=True)

	row.sales_invoice = invoice.name
	row.invoice_status = "Draft"
	recompute_summary(plan)
	plan.flags.ignore_validate_update_after_submit = True
	plan.save(ignore_permissions=True)
	return invoice.name


def _check_predecessors(plan, row):
	"""Block a milestone whose predecessor is untriggered, unless a manager overrides."""
	index = plan.milestones.index(row)
	pending = [r.milestone_name for r in plan.milestones[:index] if not r.is_triggered]
	if not pending:
		return
	if not set(frappe.get_roles()).intersection(("Accounts Manager", "System Manager")):
		frappe.throw(
			_("Milestone {0} cannot be invoiced while {1} is still untriggered.").format(
				row.milestone_name, ", ".join(pending)
			),
			title=_("Out of Sequence"),
		)
	plan.add_comment(
		"Comment",
		_("{0} invoiced out of sequence by {1}; {2} still untriggered.").format(
			row.milestone_name, frappe.session.user, ", ".join(pending)
		),
	)


@frappe.whitelist()
def create_statutory_reimbursement_invoice(billing_plan):
	"""Bill the statutory fees the company fronted, OUTSIDE the composite supply."""
	plan = frappe.get_doc("Solar Billing Plan", billing_plan)
	plan.check_permission("write")

	outstanding = flt(plan.statutory_outstanding)
	if outstanding <= 0:
		frappe.throw(_("There is no outstanding statutory reimbursement on this plan."))

	receipts = frappe.get_all(
		"Statutory Fee Payment",
		filters={
			"solar_installation": plan.solar_installation,
			"docstatus": 1,
			"paid_by": "Company on Behalf of Customer",
		},
		pluck="payment_reference",
	)
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": plan.company,
			"customer": plan.customer,
			"posting_date": today(),
			"project": plan.project,
			"solar_billing_plan": plan.name,
			"is_statutory_reimbursement": 1,
			"items": [gst.build_reimbursement_item(outstanding, ", ".join(filter(None, receipts)))],
		}
	)
	invoice.flags.ignore_permissions = True
	invoice.insert(ignore_permissions=True)
	return invoice.name


# ---------------------------------------------------------------- the hard rule
def reject_subsidy_on_invoice(doc, method=None):
	"""THE ABSOLUTE RULE.

	The subsidy is a government transfer to the customer after commissioning. It is not our
	revenue, not our liability and not a discount, and it must never appear on an invoice.
	"""
	for row in doc.get("items") or []:
		haystack = " ".join(str(v or "") for v in (row.item_name, row.description, row.item_code)).lower()
		if FORBIDDEN_WORD in haystack:
			frappe.throw(
				_("Item row {0} mentions a subsidy. The subsidy is a government transfer to the "
				  "customer after commissioning - it can never be an item, a tax or a discount "
				  "on an invoice.").format(row.idx),
				title=_("Subsidy on an Invoice"),
			)
	for row in doc.get("taxes") or []:
		if FORBIDDEN_WORD in str(row.description or "").lower():
			frappe.throw(
				_("Tax row {0} mentions a subsidy. The subsidy can never appear in the taxes table.").format(
					row.idx
				),
				title=_("Subsidy on an Invoice"),
			)


def refresh_billing_summaries():
	"""Nightly, per company. Registered through the module registry."""
	summary = {}
	for company in frappe.get_all("Company", pluck="name"):
		plans = frappe.get_all(
			"Solar Billing Plan", filters={"company": company, "docstatus": 1}, pluck="name"
		)
		for name in plans:
			plan = frappe.get_doc("Solar Billing Plan", name)
			recompute_summary(plan)
			plan.flags.ignore_validate_update_after_submit = True
			plan.save(ignore_permissions=True)
		summary[company] = len(plans)
	return summary


# --------------------------------------------------------------------- the customer's statement
def customer_statement(inst):
	"""What the customer was billed and what was received, as a running ledger - the
	Statement of Account in the customer's completion file.

	ERPNext's invoices and the payments allocated to them first; receipts recorded on the
	advance and balance tasks count only when no Payment Entry stands behind them, so a
	payment is never shown twice.
	"""
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"solar_installation": inst.name, "docstatus": 1},
		fields=["name", "posting_date", "grand_total"],
		order_by="posting_date asc",
		ignore_permissions=True,
	)
	rows = [
		{"date": i.posting_date, "particulars": _("Invoice {0}").format(i.name), "debit": flt(i.grand_total), "credit": 0}
		for i in invoices
	]
	if invoices:
		for ref in frappe.get_all(
			"Payment Entry Reference",
			filters={
				"reference_doctype": "Sales Invoice",
				"reference_name": ["in", [i.name for i in invoices]],
				"docstatus": 1,
			},
			fields=["parent", "allocated_amount"],
			ignore_permissions=True,
		):
			entry = frappe.db.get_value(
				"Payment Entry", ref.parent, ["posting_date", "mode_of_payment"], as_dict=True
			) or frappe._dict()
			mode = f" ({entry.mode_of_payment})" if entry.mode_of_payment else ""
			rows.append(
				{"date": entry.posting_date, "particulars": _("Payment {0}{1}").format(ref.parent, mode),
				 "debit": 0, "credit": flt(ref.allocated_amount)}
			)
	for task in frappe.get_all(
		"Installation Task",
		filters={"solar_installation": inst.name, "docstatus": 1, "task_code": ["in", ["ADV", "BAL"]], "status": "Completed"},
		fields=["task_code", "amount", "paid_on", "payer", "payment_mode", "payment_entry"],
		ignore_permissions=True,
	):
		if task.payment_entry or not flt(task.amount):
			continue
		label = _("Advance received") if task.task_code == "ADV" else _("Balance received")
		mode = f" ({task.payment_mode})" if task.payment_mode else ""
		rows.append(
			{"date": task.paid_on, "particulars": f"{label} - {task.payer or _('Customer')}{mode}",
			 "debit": 0, "credit": flt(task.amount)}
		)
	if not invoices and flt(inst.gross_contract_value):
		rows.insert(
			0, {"date": inst.order_date, "particulars": _("Contract value"), "debit": flt(inst.gross_contract_value), "credit": 0}
		)
	rows.sort(key=lambda r: str(r["date"] or ""))
	balance = 0.0
	for row in rows:
		balance += row["debit"] - row["credit"]
		row["balance"] = balance
		row["date"] = frappe.utils.formatdate(row["date"], "dd-MM-yyyy") if row["date"] else ""
	return frappe._dict(
		rows=rows,
		total_invoiced=sum(r["debit"] for r in rows),
		total_received=sum(r["credit"] for r in rows),
		balance=balance,
	)
