# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Reimbursements from the portal: raised from a task card on the project board, and a
task's claims listed in its Documents panel. Approving, rejecting and paying are the
Expense Reimbursement controller's own calls."""

import frappe
from frappe import _
from frappe.utils.file_manager import get_max_file_size

from a3_sola.api.stages import _get_stage
from a3_sola.solar_operations.doctype.expense_reimbursement import expense_reimbursement
from a3_sola.www.a3solaportal.collections import record_route

DOCTYPE = "Expense Reimbursement"


@frappe.whitelist(methods=["POST"])
def raise_claim(installation, task_code, amount=None, description=None, expense_date=None, remarks=None):
	"""Claim back what was paid for one of the job's tasks, with the receipt posted as `file`
	when there is one. Returns the claim and where it is."""
	inst = frappe.get_doc("Solar Installation", installation)
	inst.check_permission("read")
	row = _get_stage(inst, task_code)
	if not (description or "").strip():
		description = row.stage_name
	claim = expense_reimbursement.raise_claim(
		inst.name, task_code, amount, description, expense_date=expense_date, remarks=remarks,
		source_doctype=row.task_doctype if row.task_document else None, source_document=row.task_document or None,
	)
	posted = frappe.request.files.get("file") if frappe.request and frappe.request.files else None
	if posted:
		content = posted.stream.read()
		if len(content) > get_max_file_size():
			frappe.throw(_("{0} is larger than {1} MB.").format(posted.filename, get_max_file_size() // (1024 * 1024)),
				frappe.ValidationError)
		try:
			file = frappe.get_doc({
				"doctype": "File", "file_name": posted.filename, "content": content, "is_private": 1,
				"attached_to_doctype": DOCTYPE, "attached_to_name": claim.name, "attached_to_field": "receipt",
			}).insert(ignore_permissions=True)
		except frappe.ValidationError:
			raise
		except Exception:
			frappe.throw(_("{0} could not be read. If it is a PDF, it may be damaged - save it again and retry.").format(
				posted.filename), frappe.ValidationError)
		claim.db_set("receipt", file.file_url)
	return {"name": claim.name, "route": record_route("reimbursements", claim.name), "status": claim.status}


def claims_for(installation, task_code):
	"""The task's claims, newest first, as the Documents panel lists them."""
	rows = frappe.get_all(
		DOCTYPE, filters={"solar_installation": installation, "task_code": task_code},
		fields=["name", "claimant_name", "claimant", "amount", "status", "expense_date", "description"],
		order_by="creation desc",
	)
	return [{
		"name": r.name, "route": record_route("reimbursements", r.name), "status": r.status,
		"who": r.claimant_name or r.claimant, "amount": frappe.utils.fmt_money(r.amount, currency="INR"),
		"description": r.description,
	} for r in rows]
