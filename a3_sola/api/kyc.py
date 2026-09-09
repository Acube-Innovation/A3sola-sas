# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Know Your Customer: what the order needs from the consumer before the job opens.

The bill, the PAN, both faces of the Aadhaar, a bank proof, the pre-installation photograph
and - when the loan is big enough to make the bank ask - an income tax return or a land tax
receipt. They live on the Solar Consumer, because a consumer is KYC'd once; the sales order
fetches and shows them, and the job registers them under its first task.

Aadhaar numbers are personal data with a law behind them. Only the last four digits are kept.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api.settings import get_float, get_value

REQUIRED_ALWAYS = ("KSEB Bill", "PAN", "Aadhaar Front", "Aadhaar Back", "Pre-Installation Photo")
BANK_PROOF = ("Bank Passbook", "Cancelled Cheque")
LOAN_PROOF = ("Income Tax Return", "Land Tax Receipt")
REQUIRED_FIELDS = (
	("email_id", "Email ID"),
	("landmark", "Landmark"),
	("taluk", "Taluk"),
	("google_location_url", "Google location"),
)


def status(consumer, loan_amount=0):
	"""What a consumer has and what is still missing, for a given loan size."""
	held = {row.kyc_type for row in consumer.get("kyc_documents") or [] if row.attachment}
	missing = [kind for kind in REQUIRED_ALWAYS if kind not in held]
	if not (held & set(BANK_PROOF)) and not consumer.get("cancelled_cheque"):
		missing.append(_("Bank passbook or cancelled cheque"))
	threshold = get_float("kyc_itr_threshold_amount") or 200000
	if flt(loan_amount) > threshold and not (held & set(LOAN_PROOF)):
		missing.append(_("Income tax return or land tax receipt (loan above {0})").format(
			frappe.utils.fmt_money(threshold, currency="INR")))
	for field, label in REQUIRED_FIELDS:
		if not consumer.get(field):
			missing.append(label)
	return {
		"rows": [
			{"kyc_type": r.kyc_type, "attachment": r.attachment, "document_no": r.document_no,
			 "document_date": r.document_date, "is_verified": r.is_verified}
			for r in consumer.get("kyc_documents") or []
		],
		"missing": missing,
		"complete": not missing,
		"loan_amount": flt(loan_amount),
	}


def loan_amount_for(sales_order=None, consumer=None):
	"""How much the customer is borrowing, from the quotation the order came from."""
	if sales_order:
		doc = sales_order if not isinstance(sales_order, str) else frappe.get_doc("Sales Order", sales_order)
		quotations = {row.prevdoc_docname for row in doc.items if row.get("prevdoc_docname")}
		for quotation in quotations:
			financed, amount = frappe.db.get_value("Quotation", quotation, ["is_financed", "sanctioned_amount"]) or (0, 0)
			if financed:
				return flt(amount)
	if consumer:
		amount = frappe.db.get_value(
			"Loan Application", {"solar_consumer": consumer, "docstatus": ["<", 2]}, "sanctioned_amount",
			order_by="creation desc",
		)
		return flt(amount)
	return 0.0


def stamp(consumer):
	"""Called from the consumer's validate: derive the summary, mask the Aadhaar."""
	for row in consumer.get("kyc_documents") or []:
		if row.kyc_type in ("Aadhaar Front", "Aadhaar Back") and row.document_no:
			digits = re.sub(r"\D", "", row.document_no)
			if len(digits) > 4:
				row.document_no = "XXXX XXXX " + digits[-4:]
		if row.is_verified and not row.verified_by:
			row.verified_by = frappe.session.user
			row.verified_on = frappe.utils.now_datetime()
		elif not row.is_verified:
			row.verified_by = None
			row.verified_on = None
	if not consumer.get("google_location_url") and consumer.get("latitude") and consumer.get("longitude"):
		consumer.google_location_url = f"https://maps.google.com/?q={flt(consumer.latitude, 6)},{flt(consumer.longitude, 6)}"
	result = status(consumer, loan_amount_for(consumer=consumer.name if not consumer.is_new() else None))
	consumer.kyc_status = "Complete" if result["complete"] else "Incomplete"
	consumer.kyc_missing = ", ".join(str(m) for m in result["missing"]) or None


@frappe.whitelist()
def get_kyc_status(solar_consumer, sales_order=None):
	consumer = frappe.get_doc("Solar Consumer", solar_consumer)
	consumer.check_permission("read")
	return status(consumer, loan_amount_for(sales_order=sales_order, consumer=solar_consumer))


def warn_missing_on_sales_order(doc, method=None):
	"""Sales Order validate: say what is missing. Block only when Settings says to.

	Warn by default because an order is taken on a kitchen table with the bill in hand
	and the Aadhaar photographed that evening; refusing the order over it would move the
	paperwork problem onto the sale.
	"""
	consumer = doc.get("solar_consumer")
	if not consumer:
		return
	result = status(frappe.get_doc("Solar Consumer", consumer), loan_amount_for(sales_order=doc))
	if doc.meta.has_field("kyc_status"):
		doc.kyc_status = _("Complete") if result["complete"] else _("Missing: {0}").format(
			", ".join(str(m) for m in result["missing"]))
	if result["complete"]:
		return
	message = _("KYC incomplete for {0}: {1}").format(consumer, ", ".join(str(m) for m in result["missing"]))
	if get_value("block_sales_order_without_kyc"):
		frappe.throw(message, title=_("KYC Incomplete"))
	frappe.msgprint(message, title=_("KYC Incomplete"), indicator="orange")


def register_for_installation(installation):
	"""Every KYC file of the job's consumer, into the job's register under the order task."""
	from a3_sola.api import documents

	inst = installation if not isinstance(installation, str) else frappe.get_doc("Solar Installation", installation)
	if not inst.solar_consumer:
		return 0
	consumer = frappe.get_doc("Solar Consumer", inst.solar_consumer)
	count = 0
	for row in consumer.get("kyc_documents") or []:
		if not row.attachment:
			continue
		documents.register_document(
			inst, "ORD", "Solar Consumer", consumer.name, f"KYC - {row.kyc_type}", row.attachment,
			kind="Uploaded", reference_no=row.document_no, document_date=row.document_date, save=False,
		)
		count += 1
	if count:
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
	return count


def sync_register(doc, method=None):
	"""Solar Consumer on_update: a KYC file added later still reaches every open job."""
	before = doc.get_doc_before_save()
	if before is not None:
		then = {(r.kyc_type, r.attachment) for r in before.get("kyc_documents") or []}
		now = {(r.kyc_type, r.attachment) for r in doc.get("kyc_documents") or []}
		if then == now:
			return
	for name in frappe.get_all(
		"Solar Installation", filters={"solar_consumer": doc.name, "docstatus": ["<", 2]}, pluck="name"
	):
		register_for_installation(name)
