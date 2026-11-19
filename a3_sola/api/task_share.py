# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sharing one of a task's documents from the board's Documents panel - by WhatsApp, e-mail,
the phone's share sheet or a copied link - to someone who has no login: the bank, KSEB, the
customer.

A task's files are private and its papers are printed live, so neither opens for them. The
panel asks for a share link instead (`share_link`): a link to `shared_document`, keyed by an HMAC of the
project, the task, the document's own link and an expiry, so it opens that one document of
that one task until it expires, and cannot be made for another. Opening it checks again that
the document is still one of the task's: a file removed since no longer opens.
"""

import hashlib
import hmac
from datetime import timedelta
from urllib.parse import parse_qsl, quote, urlsplit

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, get_url, getdate, today

#: How long a shared link opens.
DAYS = 30


def _key(installation, task_code, url, expires):
	from frappe.utils.password import get_encryption_key

	secret = (get_encryption_key() + ":task-document-share").encode()
	message = "|".join([installation, task_code, url, expires])
	return hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()[:40]


def _names(inst, task_code):
	"""Every document link the task's panel shows - its files, and its papers as printed, signed
	or not, to view or download - with what the document is called. A file of a checklist row
	(the Aadhaar's front and back) goes by its own label."""
	from a3_sola.api.portal_tasks import _panel

	out = {}
	for d in _panel(inst, task_code).get("documents") or []:
		for p in d.get("prints") or []:
			for u in (p["url"], p["url"] + "&signed=1", p["url"] + "&signed=0"):
				out.setdefault(u, d.get("name"))
		for f in d.get("files") or []:
			if f.get("url"):
				out.setdefault(f["url"], f.get("label") or d.get("name"))
		if d.get("file_url"):
			out.setdefault(d["file_url"], d.get("name"))
	return out


def _urls(inst, task_code):
	"""Every document link the task's panel shows."""
	return set(_names(inst, task_code))


def _name(inst, task_code, url):
	"""What the document is called, for its message and its file."""
	return _names(inst, task_code).get(url) or _("Document")


def _link(installation, task_code, url, expires):
	return get_url("/api/method/a3_sola.api.task_share.shared_document?i={0}&t={1}&e={2}&u={3}&k={4}".format(
		quote(installation), quote(task_code), expires, quote(url, safe=""), _key(installation, task_code, url, expires)))


@frappe.whitelist(methods=["POST"])
def share_link(installation, task_code, url):
	"""A link that opens this one document of the task without a login, for DAYS days, and the
	message to send it with."""
	from a3_sola.api.portal_tasks import _job
	from a3_sola.api.portal_share import SIGNATURE, _sender


	inst = _job(installation, "read")
	if url not in _urls(inst, task_code):
		frappe.throw(_("That is not one of this task's documents."), frappe.PermissionError)
	expires = str(getdate(today()) + timedelta(days=DAYS))
	link = _link(installation, task_code, url, expires)
	name = _name(inst, task_code, url)
	customer = inst.get("consumer_name") or inst.get("lead_name") or inst.name
	sender, phone = _sender()
	message = _("Dear Sir/Madam,\n\nPlease find the {0} for {1} at the link below. It opens until {2}.\n\n{3}\n\n").format(
		name, customer, frappe.utils.formatdate(expires, "dd MMM yyyy"), link) + SIGNATURE.format(sender=sender, phone=phone)
	return {"link": link, "name": name, "subject": _("{0} - {1}").format(name, customer), "message": message,
		"expires": expires, "file_name": _file_name(name, url)}


@frappe.whitelist(methods=["POST"])
def share_links(installation, task_code, urls):
	"""Links for several of the task's documents at once - the panel's Share, every document
	ticked - and one message that lists them, each opening for DAYS days without a login."""
	from a3_sola.api.portal_tasks import _job
	from a3_sola.api.portal_share import SIGNATURE, _sender

	urls = frappe.parse_json(urls) if isinstance(urls, str) else urls
	urls = list(dict.fromkeys(u for u in urls or [] if u))
	if not urls:
		frappe.throw(_("Choose at least one document to share."))
	inst = _job(installation, "read")
	names = _names(inst, task_code)
	if any(u not in names for u in urls):
		frappe.throw(_("That is not one of this task's documents."), frappe.PermissionError)
	expires = str(getdate(today()) + timedelta(days=DAYS))
	docs = [{"url": u, "name": names[u], "link": _link(installation, task_code, u, expires),
		"file_name": _file_name(names[u], u)} for u in urls]
	customer = inst.get("consumer_name") or inst.get("lead_name") or inst.name
	task = frappe.db.get_value("Installation Task", {"solar_installation": inst.name, "task_code": task_code}, "task_name")
	sender, phone = _sender()
	listed = "\n\n".join("{0}. {1}\n{2}".format(i, d["name"], d["link"]) for i, d in enumerate(docs, 1))
	message = _("Dear Sir/Madam,\n\nPlease find the documents for {0} at the links below. They open until {1}.\n\n{2}\n\n").format(
		customer, frappe.utils.formatdate(expires, "dd MMM yyyy"), listed) + SIGNATURE.format(sender=sender, phone=phone)
	subject = _("{0} - {1}").format(task or _("Documents"), customer)
	return {"documents": docs, "subject": subject, "message": message, "expires": expires}


def _file_name(name, url):
	path = urlsplit(url).path
	if path.startswith("/api/method/"):
		return "{0}.pdf".format(name)
	return path.rsplit("/", 1)[-1] or name


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=60, seconds=60 * 60)
def shared_document(i, t, e, u, k):
	"""The shared document, for whoever has the link: a file as it was filed, a paper as the
	system prints it now."""
	if not (i and t and e and u and k) or not hmac.compare_digest(str(k), _key(i, t, u, e)):
		raise frappe.PermissionError(_("This link is not valid."))
	if getdate(today()) > getdate(e):
		raise frappe.PermissionError(_("This link has expired. Ask for the document to be shared again."))
	if not frappe.db.exists("Solar Installation", i):
		raise frappe.PermissionError(_("This document is no longer available."))
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		inst = frappe.get_doc("Solar Installation", i)
		if u not in _urls(inst, t):
			raise frappe.PermissionError(_("This document is no longer available."))
		name = _name(inst, t, u)
		parts = urlsplit(u)
		if parts.path.startswith("/api/method/"):
			# A paper printed live: its own print method, as the panel opens it.
			method = parts.path[len("/api/method/"):]
			args = dict(parse_qsl(parts.query))
			frappe.call(frappe.get_attr(method), **args)
			frappe.local.response.filename = _file_name(name, u)
		else:
			file = frappe.get_doc("File", {"file_url": parts.path})
			frappe.local.response.filename = file.file_name or _file_name(name, u)
			frappe.local.response.filecontent = file.get_content()
			frappe.local.response.type = "download"
		if frappe.local.response.get("type") == "download" and not cint(dict(parse_qsl(parts.query)).get("download")):
			frappe.local.response.display_content_as = "inline"
	finally:
		frappe.set_user(user)
