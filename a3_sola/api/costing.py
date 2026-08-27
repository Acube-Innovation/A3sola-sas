# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Job costing.

Costs are RE-DERIVED, never accumulated. `recalculate_project_costs` rebuilds every figure
from source documents, so there is no stored number that cannot be recomputed - and no
slow drift between the ledger and the project.

Two deliberate choices:

* Rework is its own category, isolated from base material and labour. It is the client's
  quality-cost signal and tells them whether a crew or a supplier is costing them margin.
* Statutory fees are a PASS-THROUGH, excluded from cost and margin. The company pays the
  DISCOM on the customer's behalf and recovers it against receipts; booking it as cost
  understates margin on every job.
"""

import frappe
from frappe import _
from frappe.utils import flt, today

from a3_sola.api.settings import get_float, get_settings

#: Cost buckets, in the order they appear on the Project.
CATEGORIES = (
	("material_cost", "Material"),
	("labour_cost", "Labour"),
	("subcontractor_cost", "Subcontractor"),
	("logistics_cost", "Logistics"),
	("liaison_and_statutory_cost", "Liaison"),
	("rework_cost", "Rework"),
	("om_cost_to_date", "O&M"),
)


def pass_through_categories():
	"""Categories excluded from cost and margin."""
	settings = get_settings()
	return {row.category_name for row in settings.cost_categories if row.is_pass_through}


@frappe.whitelist()
def recalculate_project_costs(project):
	"""Rebuild the cost entry table and every costing field from source documents."""
	doc = frappe.get_doc("Project", project)
	doc.check_permission("write")

	entries = []
	entries += _material_cost(doc)
	entries += _labour_cost(doc)
	entries += _subcontractor_cost(doc)
	entries += _expense_cost(doc)
	entries += _rework_cost(doc)
	entries += _om_cost(doc)
	statutory = _statutory_pass_through(doc)

	doc.set("cost_entries", [])
	for entry in entries:
		doc.append("cost_entries", entry)

	totals = {field: 0.0 for field, _label in CATEGORIES}
	label_to_field = {label: field for field, label in CATEGORIES}
	for entry in entries:
		field = label_to_field.get(entry["cost_category"])
		if field:
			totals[field] += flt(entry["amount"])

	for field, value in totals.items():
		doc.set(field, flt(value, 2))

	doc.statutory_pass_through = flt(statutory, 2)
	doc.total_direct_cost = flt(sum(totals.values()), 2)
	doc.overhead_allocated = flt(
		doc.total_direct_cost * get_float("overhead_recovery_percent", 0.0) / 100.0, 2
	)
	doc.total_cost = flt(doc.total_direct_cost + doc.overhead_allocated, 2)

	_margin(doc)

	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return {
		"total_cost": doc.total_cost,
		"gross_margin_amount": doc.gross_margin_amount,
		"gross_margin_percent": doc.gross_margin_percent,
		"entries": len(entries),
	}


def _margin(doc):
	"""Margin against billed revenue, and the variance against what sales quoted."""
	revenue = flt(doc.total_billed_amount) or flt(doc.gross_contract_value)
	doc.gross_margin_amount = flt(revenue - flt(doc.total_cost), 2)
	doc.gross_margin_percent = flt(doc.gross_margin_amount * 100.0 / revenue, 2) if revenue else 0.0

	capacity = flt(doc.capacity_kw)
	doc.cost_per_kw = flt(flt(doc.total_cost) / capacity, 2) if capacity else 0.0
	doc.margin_per_kw = flt(flt(doc.gross_margin_amount) / capacity, 2) if capacity else 0.0

	# Close the loop on the Phase 1 promise.
	quoted = _quoted_margin(doc)
	doc.quoted_margin_percent = flt(quoted, 2)
	doc.margin_variance_percent = flt(doc.gross_margin_percent - quoted, 2) if quoted else 0.0


def _quoted_margin(doc):
	"""The margin this job would have earned at the quoted price, on its actual cost.

	The design estimate records price, not cost, so a quoted-cost comparison is not
	available. Holding cost constant and swapping billed revenue for quoted price isolates
	the billing side of the gap - discount given, scope billed short, a milestone still
	unraised - from cost overrun, which the category variance already shows.
	"""
	quoted = _quoted_value(doc)
	if not quoted:
		return 0.0
	return flt((quoted - flt(doc.total_cost)) * 100.0 / quoted, 2)


def _quoted_value(doc):
	"""What sales put in front of the customer, before any negotiation."""
	if doc.solar_installation:
		estimate = frappe.db.get_value(
			"Solar Installation", doc.solar_installation, "solar_design_estimate"
		)
		if estimate:
			quoted = flt(
				frappe.db.get_value("Solar Design Estimate", estimate, "total_project_cost")
			)
			if quoted:
				return quoted
	return flt(doc.gross_contract_value)


def _installation_filter(doc):
	return doc.solar_installation


def _source_docs(doctype, doc, extra=None):
	filters = {"company": doc.company, "docstatus": 1}
	if doc.solar_installation and frappe.get_meta(doctype).has_field("solar_installation"):
		filters["solar_installation"] = doc.solar_installation
	elif frappe.get_meta(doctype).has_field("project"):
		filters["project"] = doc.name
	else:
		return []
	filters.update(extra or {})
	return frappe.get_all(doctype, filters=filters, pluck="name")


def _material_cost(doc):
	"""Valued at VALUATION rate, not selling rate."""
	entries = []
	for stock_entry in _source_docs("Stock Entry", doc):
		se = frappe.get_doc("Stock Entry", stock_entry)
		if se.stock_entry_type not in ("Material Issue", "Material Transfer"):
			continue
		amount = sum(flt(row.amount) for row in se.items)
		if amount:
			entries.append(
				_entry("Material", "Stock Entry", se.name, se.posting_date, amount, se.stock_entry_type)
			)

	for note in _source_docs("Delivery Note", doc):
		dn = frappe.get_doc("Delivery Note", note)
		amount = sum(flt(row.incoming_rate) * flt(row.qty) for row in dn.items)
		if amount:
			entries.append(_entry("Material", "Delivery Note", dn.name, dn.posting_date, amount))
	return entries


def _labour_cost(doc):
	"""Crew hours at the employee's cost rate, falling back to the Settings default."""
	if not doc.solar_installation:
		return []
	rate_default = get_float("default_labour_cost_per_hour", 0.0)
	rework_orders = _rectification_work_orders(doc)
	rows = frappe.db.sql(
		"""
		select wo.name, wo.actual_end_date, crew.technician, crew.actual_hours
		from `tabInstallation Work Order` wo
		join `tabWork Order Crew` crew on crew.parent = wo.name
		where wo.solar_installation = %s and wo.docstatus = 1 and crew.actual_hours > 0
		""",
		(doc.solar_installation,),
		as_dict=True,
	)
	# Rectification hours belong to Rework. Counting them here as well would both
	# double the total and hide what the rework actually cost.
	rows = [row for row in rows if row.name not in rework_orders]
	entries = []
	for row in rows:
		rate = _employee_rate(row.technician) or rate_default
		amount = flt(row.actual_hours) * flt(rate)
		if amount:
			entries.append(
				_entry(
					"Labour", "Installation Work Order", row.name,
					row.actual_end_date or today(), amount,
					f"{row.technician}: {flt(row.actual_hours)}h @ {flt(rate)}",
				)
			)
	return entries


def employee_rate(employee):
	"""Hourly cost from the employee's CTC, over a 2080-hour year."""
	if not employee:
		return 0.0
	ctc = flt(frappe.db.get_value("Employee", employee, "ctc"))
	return flt(ctc / 2080.0, 2) if ctc else 0.0


#: Kept for the internal call sites that predate the public name.
_employee_rate = employee_rate


def _subcontractor_cost(doc):
	entries = []
	for invoice in _source_docs("Purchase Invoice", doc):
		pi = frappe.get_doc("Purchase Invoice", invoice)
		entries.append(
			_entry("Subcontractor", "Purchase Invoice", pi.name, pi.posting_date, flt(pi.base_net_total))
		)
	return entries


def _expense_cost(doc):
	"""Logistics and liaison, by the expense claim's own category.

	Expense Claim belongs to HRMS, which this app does not require. Where it is not
	installed there are simply no claims to cost, and costing carries on without it.
	"""
	entries = []
	if not frappe.db.exists("DocType", "Expense Claim"):
		return entries
	claims = frappe.get_all(
		"Expense Claim",
		filters={"company": doc.company, "project": doc.name, "docstatus": 1},
		pluck="name",
	)
	for claim in claims:
		ec = frappe.get_doc("Expense Claim", claim)
		for row in ec.expenses:
			category = "Logistics" if "travel" in (row.expense_type or "").lower() else "Liaison"
			entries.append(
				_entry(category, "Expense Claim", ec.name, ec.posting_date, flt(row.sanctioned_amount),
				       row.expense_type)
			)
	return entries


def _rectification_work_orders(doc):
	"""Work orders raised to rectify a snag, by work order name."""
	if not doc.solar_installation:
		return {}
	return {
		row.rectification_work_order: row
		for row in frappe.get_all(
			"Installation Snag",
			filters={
				"solar_installation": doc.solar_installation,
				"docstatus": ["<", 2],
				"rectification_work_order": ["is", "set"],
			},
			fields=["name", "rectification_work_order", "reported_on", "severity"],
		)
	}


def _rework_cost(doc):
	"""Costs attributable to snags and their rectification work orders.

	Valued exactly as installation labour is - the crew's own cost rate - so that the
	rework figure is comparable with the labour it is being weighed against.
	"""
	entries = []
	rate_default = get_float("default_labour_cost_per_hour", 0.0)
	for work_order, snag in _rectification_work_orders(doc).items():
		crew = frappe.get_all(
			"Work Order Crew",
			filters={"parent": work_order, "parenttype": "Installation Work Order"},
			fields=["technician", "actual_hours"],
		)
		amount = sum(
			flt(row.actual_hours) * (_employee_rate(row.technician) or rate_default) for row in crew
		)
		if amount:
			entries.append(
				_entry("Rework", "Installation Snag", snag.name, snag.reported_on, amount,
				       f"{snag.severity} rectification on {work_order}")
			)
	return entries


def _om_cost(doc):
	"""Fed by O&M visits once the contract is running."""
	entries = []
	visits = frappe.get_all(
		"Solar OM Visit",
		filters={"project": doc.name, "docstatus": 1},
		fields=["name", "visit_date", "total_visit_cost", "visit_type"],
	)
	for visit in visits:
		if flt(visit.total_visit_cost):
			entries.append(
				_entry("O&M", "Solar OM Visit", visit.name, visit.visit_date,
				       flt(visit.total_visit_cost), visit.visit_type)
			)
	return entries


def _statutory_pass_through(doc):
	"""Reported separately so it is visible without polluting margin."""
	if not doc.solar_installation:
		return 0.0
	total = frappe.db.sql(
		"""
		select sum(amount_gross) from `tabStatutory Fee Payment`
		where solar_installation = %s and docstatus = 1
		  and paid_by = 'Company on Behalf of Customer'
		""",
		(doc.solar_installation,),
	)[0][0]
	return flt(total)


def _entry(category, source_doctype, source_document, posting_date, amount, remarks=None):
	return {
		"cost_category": category,
		"source_doctype": source_doctype,
		"source_document": source_document,
		"posting_date": posting_date or today(),
		"amount": flt(amount, 2),
		"remarks": remarks,
	}


def nightly_cost_refresh():
	"""Rebuild costs for every open project, per company. Registered in the module registry."""
	summary = {}
	for company in frappe.get_all("Company", pluck="name"):
		projects = frappe.get_all(
			"Project",
			filters={"company": company, "status": ["!=", "Cancelled"], "solar_installation": ["is", "set"]},
			pluck="name",
		)
		for project in projects:
			try:
				recalculate_project_costs(project)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"a3_sola: cost refresh {project}")
		summary[company] = len(projects)
	frappe.logger("a3_sola").info({"event": "nightly_cost_refresh", "summary": summary})
	return summary
