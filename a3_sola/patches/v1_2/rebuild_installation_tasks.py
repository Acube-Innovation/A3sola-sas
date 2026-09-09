# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every open installation gets the task list, built fresh.

A convenience, not a migration - decided with the user: the old twenty-stage chain is not
carried across. Each open job's stage rows are replaced by the thirty task rows of the
"Solar Installation Tasks" template, every register row that holds a file is kept and
re-attached to the matching expectation (or appended when there is none), and the task
documents the job already has - its sales order, agreement, loan, fee payments, portal
applications, work orders, commissioning report, claim - are linked back by the same rule
the live sync uses, quietly (no accounts ToDos, no auto-invoices). A comment on the job
says how many old rows were discarded.

Closed and cancelled jobs are left on their inactive template as history.
"""

import frappe
from frappe import _

KEPT_FIELDS = (
	"document_name", "attachment", "document_date", "document_reference_no", "is_verified",
	"verified_by", "verified_on", "solar_document_template", "source_doctype", "source_document", "remarks",
)


def execute():
	if not frappe.db.exists("DocType", "Installation Stage Template"):
		return None
	result = run()
	frappe.db.commit()
	print(
		f"a3_sola: {result['rebuilt']} installation(s) rebuilt on the task template, "
		f"{result['discarded']} old stage row(s) discarded, {result['skipped']} skipped"
	)
	return result


def run():
	from a3_sola.setup.install_ops import TASK_TEMPLATE_NAME

	rebuilt = discarded = skipped = 0
	for name in frappe.get_all(
		"Solar Installation",
		filters={"docstatus": ["<", 2], "status": ["not in", ["Closed", "Cancelled"]]},
		pluck="name",
		order_by="creation asc",
	):
		doc = frappe.get_doc("Solar Installation", name)
		template = frappe.db.get_value(
			"Installation Stage Template",
			{"template_name": TASK_TEMPLATE_NAME, "company": doc.company, "is_active": 1},
			"name",
		)
		if not template:
			skipped += 1
			continue
		if doc.stage_template == template and doc.stages and all(r.task_doctype for r in doc.stages):
			continue
		frappe.db.savepoint("a3s_rebuild")
		try:
			old_rows = rebuild_one(doc, template)
			rebuilt += 1
			discarded += old_rows
		except Exception:
			frappe.db.rollback(save_point="a3s_rebuild")
			skipped += 1
			frappe.log_error(frappe.get_traceback(), f"a3_sola: task rebuild failed for {name}")
	return {"rebuilt": rebuilt, "discarded": discarded, "skipped": skipped}


def rebuild_one(doc, template):
	from a3_sola.api import stages

	old_rows = len(doc.stages)
	kept = [r.as_dict() for r in doc.documents if r.attachment]
	doc.stage_template = template
	doc.set("stages", [])
	doc.set("documents", [])
	stages.build_stages(doc)
	for old in kept:
		match = next(
			(
				r for r in doc.documents
				if not r.attachment
				and (
					(old.get("solar_document_template") and r.solar_document_template == old["solar_document_template"])
					or r.document_name == old["document_name"]
				)
			),
			None,
		)
		values = {k: old.get(k) for k in KEPT_FIELDS}
		values["document_kind"] = old.get("document_kind") if old.get("document_kind") in ("Generated", "Uploaded") else "Uploaded"
		if match:
			match.update(values)
		else:
			values["stage_code"] = old.get("stage_code") if old.get("stage_code") in {r.stage_code for r in doc.stages} else "ORD"
			values["is_mandatory"] = 0
			doc.append("documents", values)
	doc.flags.ignore_validate_update_after_submit = True
	doc.flags.ignore_permissions = True
	# Only the task rows change here. A job whose masters have since been deleted (a purged
	# package or section) must still get its tasks; refusing it fixes nothing.
	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)
	relink(doc)
	doc.add_comment(
		"Comment",
		_("Tasks rebuilt on {0}: {1} old stage row(s) discarded, {2} document(s) kept, documents re-linked.").format(
			template, old_rows, len(kept)
		),
	)
	return old_rows


def relink(doc):
	"""Best effort: every task document already on the job claims its row, quietly."""
	from a3_sola.api import tasks

	previous = frappe.flags.a3s_replaying_triggers
	frappe.flags.a3s_replaying_triggers = True
	try:
		if doc.sales_order and frappe.db.exists("Sales Order", doc.sales_order):
			try:
				tasks.link_document(
					doc.name, "ORD", "Sales Order", doc.sales_order, status="Completed",
					actual_date=doc.order_date, silent=True,
				)
			except Exception:
				frappe.log_error(frappe.get_traceback(), f"a3_sola: relink order for {doc.name}")
		for doctype in tasks.TASK_DOCTYPES:
			if doctype == "Sales Order" or not frappe.db.exists("DocType", doctype):
				continue
			if not frappe.db.has_column(doctype, "solar_installation"):
				continue
			for name in frappe.get_all(
				doctype, filters={"solar_installation": doc.name, "docstatus": ["<", 2]}, pluck="name",
				order_by="creation asc",
			):
				try:
					tasks.sync_from_document(frappe.get_doc(doctype, name), None)
				except Exception:
					frappe.log_error(frappe.get_traceback(), f"a3_sola: relink {doctype} {name}")
	finally:
		frappe.flags.a3s_replaying_triggers = previous
