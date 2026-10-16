# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sending a document out: the proposal and the quotation to the customer, a procurement
task's purchase list (its BOM's material) to the supplier, and a work order - the job, with
its site, system, material and photographs - to its contractor.

Each page shows the same square buttons (templates/includes/portal_share.html): the PDF to
view and download, a WhatsApp chat and an email to the customer prefilled with a greeting,
and the device's share sheet for the file itself (public/js/portal_share.js). A WhatsApp or
mail link carries no file, so the click downloads the PDF to drop in, and the greeting also
carries a private link the customer opens it with: `shared_pdf`, keyed by an HMAC of the
document so it opens that one document and cannot be guessed.
"""

import hashlib
import hmac
from urllib.parse import quote

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, fmt_money

#: Who signs when the person sharing has no mobile number on their profile.
DEFAULT_SENDER = ("Shiju N K", "+91 9895778516")

SIGNATURE = """Best regards,

{sender}
Renewcore Innovations LLP
\U0001F4DE {phone}
Web: \U0001F310 www.renewcoreinnovations.com
- Facebook: https://www.facebook.com/renewcoreinnovations/
- Instagram: https://www.instagram.com/renewcoreinnovations/
- LinkedIn: https://www.linkedin.com/company/renewcore-innovations-llp
- Pinterest: https://www.pinterest.com/renewcoreinnovations/
- X: https://x.com/renewcore
- Tumblr: https://www.tumblr.com/blog/renewcoreinnovations
- Threads: https://www.threads.com/@renewcoreinnovations"""

#: The greetings, in WhatsApp's *bold*. {document} is how the PDF reaches them: attached,
#: or attached with its link as well.
MESSAGES = {
	"Solar Proposal": """Hi {name},

*Thank you for your interest in Renewcore Innovations LLP.* It was a pleasure discussing your solar requirements with you.

As promised, please find our formal *Solar Project Proposal* {document}

This proposal includes:
*Custom System Design:* Engineered specifically for your site and energy needs.
*Premium Technology:* High-efficiency modules with a 25-year performance warranty.
*End-to-End Support:* We handle all KSEB documentation, installation, and commissioning.
*Smart Monitoring:* Integrated remote monitoring to track your savings in real-time.

At *Renewcore*, we pride ourselves on delivering sustainable, long-term value and energy independence.
Please review the attached document. I will follow up with you shortly to answer any technical questions and discuss the next steps for your installation.

""" + SIGNATURE,
	"Quotation": """Hi {name},

*Thank you for choosing Renewcore Innovations LLP.* As discussed, please find our *Quotation {number}* for your solar power system {document}

*Quotation amount:* {amount}

The quotation covers the system as finalised in our proposal, along with all KSEB documentation, installation, and commissioning.

Please review the attached document. Once you confirm, we will share the next steps to schedule your installation.

""" + SIGNATURE,
}

# A procurement task's purchase list, to the supplier.
MESSAGES["Installation Task"] = """Hello {name},

Please find our *{list} purchase list* for the solar project *{project}* ({place}) {document}

Kindly confirm availability, price and the delivery date.

""" + SIGNATURE

# A work order, to its contractor (api/work_order_print).
MESSAGES["Installation Work Order"] = """Hello {name},

Please find *work order {number} - {kind}* for the solar project *{project}* ({place}) {document}

It has the customer's details, the site location, the system and the material - and, for an installation, the single line diagram. Kindly confirm the date you will start.

""" + SIGNATURE

#: The other papers a document sends besides its own: a purchase list's pending items - what
#: the first supplier could not give, for the next.
PENDING = "pending"

# A purchase list's pending items, to the next supplier.
MESSAGES[PENDING] = """Hello {name},

Please find the *pending items* of our *{list} purchase list* for the solar project *{project}* ({place}) {document}

These are the items still to be supplied. Kindly confirm availability, price and the delivery date.

""" + SIGNATURE

SUBJECTS = {
	"Installation Work Order": "Work Order {number} - {kind} - {project} - Renewcore Innovations LLP",
	"Solar Proposal": "Solar Project Proposal {number} - Renewcore Innovations LLP",
	"Quotation": "Quotation {number} - Renewcore Innovations LLP",
	"Installation Task": "{list} Purchase List - {project} - Renewcore Innovations LLP",
	PENDING: "{list} Pending Items - {project} - Renewcore Innovations LLP",
}

#: Procurement tasks whose purchase list can be sent (api/purchase_list).
PURCHASE_TASKS = ("SPROC", "PROC")
def _part(doc, part):
	"""`part` checked against the document: "" (the document itself) or a purchase list's
	pending items."""
	part = (part or "").strip()
	if part and not (part == PENDING and _is_purchase_list(doc)):
		raise frappe.PermissionError(_("This document has no such part."))
	return part


def _is_purchase_list(doc):
	return doc.doctype == "Installation Task" and doc.get("task_code") in PURCHASE_TASKS


def _pdf(doc, part=""):
	"""The PDF that goes out for `doc` (or its `part`)."""
	from frappe.utils.pdf import get_pdf

	if doc.doctype == "Installation Work Order":
		from a3_sola.api import work_order_print

		return work_order_print.render(doc)[1]
	if _is_purchase_list(doc):
		from a3_sola.api import purchase_list

		return purchase_list.render(doc, pending=part == PENDING)[1]
	if doc.doctype == "Solar Installation":
		# A project shares one paper: the completion report data for its electrical contractor.
		from a3_sola.api import completion_print

		return completion_print.render(doc)[1]
	return get_pdf(frappe.get_print(doc.doctype, doc.name, print_format=_print_format(doc.doctype), doc=doc, no_letterhead=0))


def _sendable(doctype):
	return bool(_print_format(doctype)) or doctype in ("Installation Task", "Installation Work Order", "Solar Installation")


# ------------------------------------------------------------------ the customer's link
def share_key(doctype, name, part=""):
	"""The key that opens this document's PDF without a login: an HMAC of the doctype and
	name (and the part, for a part) with the site's encryption key, so it cannot be guessed
	or made for another document - or for another part of this one."""
	from frappe.utils.password import get_encryption_key

	secret = (get_encryption_key() + ":document-share").encode()
	message = "{0}|{1}".format(doctype, name) + ("|" + part if part else "")
	return hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()[:32]


def share_url(doctype, name, part=""):
	return frappe.utils.get_url("/api/method/a3_sola.api.portal_share.shared_pdf?doctype={0}&name={1}{2}&key={3}".format(
		quote(doctype), quote(name), "&part=" + quote(part) if part else "", share_key(doctype, name, part)))


def _print_format(doctype):
	if doctype == "Solar Proposal":
		from a3_sola.solar_crm.doctype.solar_proposal.solar_proposal import proposal_print_format

		return proposal_print_format()
	if doctype == "Quotation":
		return "Solar Quotation"
	return None


def issued(doc):
	"""Whether the document may go to the customer: a quotation once it is submitted, a
	proposal unless it is cancelled."""
	if doc.doctype == "Quotation":
		return cint(doc.docstatus) == 1
	if doc.doctype == "Installation Task":
		return _is_purchase_list(doc) and cint(doc.docstatus) < 2
	if doc.doctype == "Installation Work Order":
		return cint(doc.docstatus) < 2
	if doc.doctype == "Solar Installation":
		# The completion report data goes out once there are serials to give.
		return cint(doc.docstatus) < 2 and any(not r.is_replaced for r in doc.get("serials") or [])
	return cint(doc.docstatus) < 2


#: Why a document's buttons are held, as the page says it.
NOT_ISSUED = {"Quotation": "Submit the quotation first to view, download or send its PDF."}


def _file_name(doc, part=""):
	if doc.doctype == "Installation Work Order":
		from a3_sola.api import work_order_print

		return work_order_print.file_name(doc)
	if _is_purchase_list(doc):
		from a3_sola.api import purchase_list

		return purchase_list.file_name(doc, pending=part == PENDING)
	if doc.doctype == "Solar Installation":
		from a3_sola.api import completion_print

		return completion_print.file_name(doc)
	return "{0}.pdf".format(doc.get("proposal_file_name") or doc.name)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=30, seconds=60 * 60)
def shared_pdf(doctype, name, key, part=None):
	"""The document's PDF for the customer it was sent to, from the link in the message:
	the key stands in for a login (share_key), and only ever opens that one document - or
	the one part of it the key was made for."""
	part = (part or "").strip()
	if not (_sendable(doctype) and name and key and frappe.db.exists(doctype, name)
			and hmac.compare_digest(str(key), share_key(doctype, name, part))):
		raise frappe.PermissionError(_("This link is not valid."))
	doc = frappe.get_doc(doctype, name)
	part = _part(doc, part)
	if not issued(doc):
		raise frappe.PermissionError(_("This document is not available."))
	frappe.flags.ignore_print_permissions = True
	try:
		content = _pdf(doc, part)
	finally:
		frappe.flags.ignore_print_permissions = False
	frappe.local.response.filename = _file_name(doc, part)
	frappe.local.response.filecontent = content
	frappe.local.response.type = "pdf"


# ------------------------------------------------------------------ sending by email
def _as_html(text):
	"""The greeting as an email body: WhatsApp's *bold* as bold, lines and links kept."""
	import re

	from frappe.utils import escape_html

	html = escape_html(text or "")
	html = re.sub(r"\*([^*\n]+)\*", r"<b>\1</b>", html)
	html = re.sub(r"(https?://[^\s<]+)", r'<a href="\1">\1</a>', html)
	return html.replace("\n", "<br>")


def _outgoing_account(doctype):
	"""The mailbox the site sends from - Renewcore's, set up once in ERPNext - or None."""
	from frappe.email.doctype.email_account.email_account import EmailAccount

	account = EmailAccount.find_outgoing(match_by_doctype=doctype)
	# A placeholder (the test accounts, or the dummy Frappe makes while email is muted) is none.
	where = "{0} {1}".format(account.get("smtp_server") or "", account.get("email_id") or "") if account else ""
	if not account or not account.get("email_id") or "example.com" in where or "test.com" in where:
		return None
	return account


@frappe.whitelist(methods=["POST"])
def send_email(doctype, name, recipients, subject, message, cc=None, part=None):
	"""Email the document's PDF to the customer from the site's mailbox, the greeting as
	the body, and keep a copy on the record's timeline. A proposal's dispatch is recorded on
	its current version, as sent by email."""
	from frappe.core.doctype.communication.email import make

	if not _sendable(doctype):
		frappe.throw(_("{0} cannot be sent from here.").format(doctype))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	part = _part(doc, part)
	if not issued(doc):
		frappe.throw(_(NOT_ISSUED.get(doctype) or "This document cannot be sent."), title=_("Not Issued Yet"))
	recipients = ", ".join(r.strip() for r in (recipients or "").replace(";", ",").split(",") if r.strip())
	if not recipients:
		frappe.throw(_("Enter the email address to send it to."), title=_("No Recipient"))
	for address in recipients.split(", "):
		frappe.utils.validate_email_address(address, throw=True)
	account = _outgoing_account(doctype)
	if not account:
		frappe.throw(
			_("No mailbox is set up to send from. In ERPNext, open Email Account, add the company's mailbox "
			  "(sales@renewcoreinnovations.com) with Enable Outgoing and Default Outgoing ticked, then try again."),
			title=_("Email Not Set Up"),
		)
	# The PDF made here, so it carries the name a download has.
	pdf = _pdf(doc, part)
	make(
		doctype=doctype, name=name, content=_as_html(message), subject=subject, recipients=recipients, cc=cc or None,
		sender=account.email_id, sender_full_name=account.get("name"), send_email=True,
		attachments=[{"fname": _file_name(doc, part), "fcontent": pdf}], now=True,
	)
	if doctype == "Solar Proposal":
		from a3_sola.solar_crm.doctype.solar_proposal import solar_proposal

		doc = frappe.get_doc(doctype, name)
		current = doc.versions[-1] if doc.versions else None
		if current and not current.sent_on:
			solar_proposal.record_dispatch(name, "Email")
	return {"sent_to": recipients}


# ------------------------------------------------------------------ the buttons
def _sender():
	"""The signature: the person sharing, from their profile, else the default sender."""
	user = frappe.db.get_value("User", frappe.session.user, ["full_name", "mobile_no", "phone"], as_dict=True) or frappe._dict()
	mobile = user.mobile_no or user.phone
	return (user.full_name or DEFAULT_SENDER[0], mobile) if mobile else DEFAULT_SENDER


def _recipient(doc, part=""):
	"""(name, mobile, email) of who the document goes to: the customer - or, for a purchase
	list, the supplier named on the task (blank, to type when it is sent, when none is)."""
	if doc.doctype in ("Installation Work Order", "Solar Installation"):
		contractor = doc.get("solar_contractor") if doc.doctype == "Installation Work Order" else doc.get("electrical_contractor")
		row = frappe.db.get_value("Solar Contractor", contractor, ["contractor_name", "mobile_no", "email_id"],
			as_dict=True) if contractor else None
		return (row.contractor_name, row.mobile_no or "", row.email_id or "") if row else ("", "", "")
	if _is_purchase_list(doc):
		# The pending items go to the supplier asked for them, else the first one again.
		supplier = (doc.get("pending_supplier") if part == PENDING else None) or doc.get("supplier")
		if not supplier:
			return "", "", ""
		row = frappe.db.get_value("Supplier", supplier, ["supplier_name", "mobile_no", "email_id"], as_dict=True) or {}
		return row.get("supplier_name") or supplier, row.get("mobile_no") or "", row.get("email_id") or ""
	if doc.doctype == "Solar Proposal":
		return doc.get("customer_name") or "", doc.get("mobile_no") or "", doc.get("email_id") or ""
	# A quotation keeps its contact only when one was picked: else the proposal it came
	# from, the consumer, and the customer or lead it is addressed to, in that order.
	name, mobile, email = "", doc.get("contact_mobile") or "", doc.get("contact_email") or ""
	sources = []
	if doc.get("solar_proposal"):
		sources.append(("Solar Proposal", doc.solar_proposal, "customer_name", "mobile_no", "email_id"))
	if doc.get("solar_consumer"):
		sources.append(("Solar Consumer", doc.solar_consumer, "consumer_name", "mobile_no", "email_id"))
	if doc.get("quotation_to") == "Customer" and doc.get("party_name"):
		sources.append(("Customer", doc.party_name, "customer_name", "mobile_no", "email_id"))
	elif doc.get("quotation_to") == "Lead" and doc.get("party_name"):
		sources.append(("Lead", doc.party_name, "lead_name", "mobile_no", "email_id"))
	for doctype, docname, name_field, mobile_field, email_field in sources:
		row = frappe.db.get_value(doctype, docname, [name_field, mobile_field, email_field], as_dict=True)
		if not row:
			continue
		name = name or row.get(name_field) or ""
		mobile = mobile or row.get(mobile_field) or ""
		email = email or row.get(email_field) or ""
	return name or doc.get("customer_name") or "", mobile, email


def share_links(doc, pdf_route, part=""):
	"""The share buttons' routes and the greeting, for a Solar Proposal or a Quotation.

	`pdf_route` is the page's own PDF endpoint (behind the login): View opens it, Download
	saves it, and the WhatsApp and email clicks download it to drop into the message."""
	from a3_sola.api.outreach import whatsapp_link

	part = _part(doc, part)
	name, mobile, email = _recipient(doc, part)
	sender, phone = _sender()
	amount = doc.get("rounded_total") or doc.get("grand_total")
	values = {
		"name": name or "Sir/Madam", "sender": sender, "phone": phone, "number": doc.name,
		"amount": fmt_money(amount, currency=doc.get("currency") or "INR") if amount else "",
	}
	if doc.doctype == "Installation Work Order":
		inst = frappe.db.get_value("Solar Installation", doc.solar_installation,
			["name", "consumer_name", "solar_consumer"], as_dict=True)
		place = frappe.db.get_value("Solar Consumer", inst.solar_consumer, "site_city") if inst.solar_consumer else None
		values.update(kind=doc.work_order_kind or "Installation", project=inst.name,
			place=", ".join(filter(None, [inst.consumer_name, place])) or inst.name)
	if _is_purchase_list(doc):
		from a3_sola.api.purchase_list import TITLES

		inst = frappe.db.get_value("Solar Installation", doc.solar_installation,
			["name", "consumer_name", "solar_consumer"], as_dict=True)
		place = frappe.db.get_value("Solar Consumer", inst.solar_consumer, "site_city") if inst.solar_consumer else None
		values.update(list=TITLES[doc.task_code], project=inst.name,
			place=", ".join(filter(None, [inst.consumer_name, place])) or inst.name)
	template = MESSAGES[PENDING if part == PENDING else doc.doctype]
	link = share_url(doc.doctype, doc.name, part)
	attached = template.format(document="attached.", **values)
	# Sent with the PDF dropped in beside it, and its link as well, for a phone that will
	# not open the file.
	linked = template.format(document="attached.\nYou can also open it here: " + link, **values)
	subject = SUBJECTS[PENDING if part == PENDING else doc.doctype].format(**values)
	whatsapp = whatsapp_link(mobile, linked) if mobile else "https://wa.me/?text=" + quote(linked)
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"part": part,
		# Shown, but not usable, until the document may go out (a draft quotation).
		"locked": not issued(doc),
		"locked_note": NOT_ISSUED.get(doc.doctype) or "",
		# The email's own text: the greeting with the PDF attached (so no link), its *bold*
		# kept - the email shows it bold (_as_html).
		"email_message": attached,
		"view": pdf_route,
		"download": pdf_route + "&download=1",
		"file_name": _file_name(doc, part),
		"whatsapp": whatsapp,
		"whatsapp_to": mobile,
		"email_to": email,
		"subject": subject,
		"message": attached,
		"link": link,
	}
