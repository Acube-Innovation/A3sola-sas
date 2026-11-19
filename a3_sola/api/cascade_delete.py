# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Delete one lead or one customer, and every record made for them.

From a Lead or a Solar Consumer the records that name it are gathered - and the records that
name those, down the chain: survey, estimate, eligibility check, proposal, quotation, sales
order, the project and its task documents, tasks, O&M. Each is cancelled if submitted and
deleted, deepest first, in one transaction: it all goes, or nothing does. Frappe keeps every
one in Deleted Documents, where an administrator can restore it.

Not deleted:
  * Submitted accounting - a Sales Invoice, Payment Entry, Journal Entry or Delivery Note.
    It is in the ledger and possibly in a filed return, so the delete is refused and the
    documents are named. A draft one is deleted with the rest.
  * A submitted Material Request, and any purchase, stock or other record that merely names
    the project: it stays, with that link cleared.
  * A Contact or Address also used by someone else: it stays, without this party's link.
  * A customer with a platform subscription or tenant: refused.
"""

import frappe
from frappe import _
from frappe.utils import cint

#: Deleted in this order - a record before the records it names.
CASCADE = (
	"Payment Entry", "Journal Entry", "Sales Invoice", "Delivery Note", "Material Request",
	"Generation Reading", "Solar OM Visit", "Service Ticket", "Solar Warranty Claim", "Solar OM Contract",
	"Statutory Fee Recovery", "Statutory Fee Payment", "Subsidy Claim", "Customer Review",
	"Net Metering Agreement", "Commissioning Report", "Document Pack", "Solar Agreement",
	"Material Dispatch Notice", "Installation Snag", "Installation Task", "Installation Work Order",
	"Expense Reimbursement", "Loan Application", "Portal Application", "Solar Billing Plan", "Solar Installation",
	"Task", "Project", "Sales Order", "Quotation", "Solar Proposal",
	"Additional Cable", "Additional Structure", "Special Discount",
	"Solar Design Estimate", "Subsidy Eligibility Check", "Site Survey", "Opportunity",
	"Solar Consumer", "Customer", "Lead",
)
CASCADE_SET = frozenset(CASCADE)
#: Deleted only as drafts (or cancelled); once submitted they are kept.
DRAFT_ONLY = frozenset(("Payment Entry", "Journal Entry", "Sales Invoice", "Delivery Note", "Material Request"))
#: Submitted, these refuse the delete: they are in the ledger.
BLOCK_SUBMITTED = frozenset(("Payment Entry", "Journal Entry", "Sales Invoice", "Delivery Note"))
#: A customer billed by the platform is a tenant, not a sales customer.
PLATFORM_BLOCKERS = ("Tenant", "Platform Subscription", "Subscription Invoice")
#: The parties a Contact or Address belongs to through its links table.
PARTIES = ("Lead", "Customer", "Solar Consumer")
#: The records a record names, gathered with it - a customer's lead, a project's job.
UPWARD = {"Solar Consumer": ("lead", "customer"), "Customer": ("lead_name",), "Solar Installation": ("project",)}
#: Frappe clears these itself when a record is deleted.
SKIP_PARENTS = frozenset(("Dynamic Link", "Communication Link", "Deleted Document", "Version", "Comment",
	"Communication", "ToDo", "File", "Activity Log", "View Log", "DocShare", "Document Follow", "Notification Log"))
DELETE_ROLES = ("System Manager", "Solar CRM Manager", "Solar Sales Manager")
ROOTS = {"Lead": "/a3solaportal/leads", "Solar Consumer": "/a3solaportal/consumers"}
LABELS = {"Solar Consumer": "Customer", "Customer": "ERPNext Customer", "Solar Installation": "Project",
	"Project": "ERPNext Project"}


# ------------------------------------------------------------------ who may
def can_delete(user=None):
	"""Admins and the sales and CRM managers - never a partner."""
	from a3_sola.api import partner_scope, portal_users

	user = user or frappe.session.user
	if user == "Administrator":
		return True
	if user == "Guest" or partner_scope.is_partner(user):
		return False
	if set(frappe.get_roles(user)) & set(DELETE_ROLES):
		return True
	return portal_users.is_user_admin(user)


def _load(doctype, name):
	if doctype not in ROOTS:
		frappe.throw(_("Only a lead or a customer can be deleted this way."))
	if not name or not frappe.db.exists(doctype, name):
		raise frappe.DoesNotExistError(_("That record does not exist."))
	doc = frappe.get_doc(doctype, name)
	# Read-checked, so the company and partner scope hold as everywhere else.
	doc.check_permission("read")
	if not can_delete():
		frappe.throw(_("You do not have permission to do that."), frappe.PermissionError)
	return doc


# ------------------------------------------------------------------ what goes
def _usable(dt):
	if not frappe.db.exists("DocType", dt):
		return False
	meta = frappe.get_meta(dt)
	return not (meta.issingle or meta.is_virtual)


def _sources(target):
	"""(parent, field, istable, doctype-field) for every field that can name a `target`.

	The doctype-field is set for a Dynamic Link: the field that holds the doctype it names.
	"""
	if not getattr(frappe.local, "a3s_cascade_sources", None):
		frappe.local.a3s_cascade_sources = {}
	cache = frappe.local.a3s_cascade_sources
	if target in cache:
		return cache[target]
	fields = []
	for src, parent_key in (("DocField", "parent"), ("Custom Field", "dt")):
		for f in frappe.get_all(src, filters={"fieldtype": "Link", "options": target},
				fields=[f"{parent_key} as parent", "fieldname"]):
			fields.append((f.parent, f.fieldname, None))
	fields += _dynamic_fields()
	out = []
	for parent, field, optfield in fields:
		if parent in SKIP_PARENTS or not _usable(parent):
			continue
		meta = frappe.get_meta(parent)
		if not meta.has_field(field) or (optfield and not meta.has_field(optfield)):
			continue
		out.append((parent, field, bool(meta.istable), optfield))
	cache[target] = out
	return out


def _cascade_tables():
	"""The child tables of the cascade's doctypes: a row in one names its record's chain."""
	if getattr(frappe.local, "a3s_cascade_tables", None) is None:
		frappe.local.a3s_cascade_tables = set(frappe.get_all("DocField", filters={
			"parent": ["in", list(CASCADE_SET)], "fieldtype": ["in", ["Table", "Table MultiSelect"]]}, pluck="options"))
	return frappe.local.a3s_cascade_tables


def _dynamic_fields():
	if getattr(frappe.local, "a3s_cascade_dynamic", None) is None:
		frappe.local.a3s_cascade_dynamic = [(f.parent, f.fieldname, f.options)
			for src, parent_key in (("DocField", "parent"), ("Custom Field", "dt"))
			for f in frappe.get_all(src, filters={"fieldtype": "Dynamic Link"},
				fields=[f"{parent_key} as parent", "fieldname", "options"])]
	return frappe.local.a3s_cascade_dynamic


def _referrers(target, names, cascade_only=False):
	"""Rows that name one of `names` of `target`: (doctype, name, field, (table, row) or None).

	`cascade_only`: only the cascade's own doctypes and their tables - the walk needs no more.
	"""
	out = []
	tables = _cascade_tables() if cascade_only else None
	for parent, field, istable, optfield in _sources(target):
		if cascade_only and parent not in CASCADE_SET and parent not in tables:
			continue
		out += _referrers_one(parent, field, istable, names, {optfield: target} if optfield else None)
	return out


def _referrers_one(parent, field, istable, names, extra=None):
	filters = {field: ["in", list(names)], **(extra or {})}
	if istable:
		return [(r.parenttype, r.parent, field, (parent, r.name))
			for r in frappe.get_all(parent, filters=filters, fields=["name", "parent", "parenttype"])]
	return [(parent, n, field, None) for n in frappe.get_all(parent, filters=filters, pluck="name")]


def collect(doctype, name):
	"""Everything that goes with this lead or customer, and what refuses or stays."""
	found = {dt: set() for dt in CASCADE}
	blockers, kept = [], set()
	frontier = {doctype: {name}}
	while frontier:
		added = {}
		for dt, names in frontier.items():
			found[dt] |= names
		for dt, names in frontier.items():
			# Up: the records this one names and belongs with.
			for field in UPWARD.get(dt, ()):
				for v in frappe.get_all(dt, filters={"name": ["in", list(names)]}, pluck=field):
					if v:
						target = frappe.get_meta(dt).get_field(field).options
						added.setdefault(target, set()).add(v)
			# Down: the records that name this one.
			for parent_dt, parent, _field, _row in _referrers(dt, names, cascade_only=True):
				if parent_dt in CASCADE_SET:
					added.setdefault(parent_dt, set()).add(parent)
		frontier = {}
		for dt, names in added.items():
			for n in names - found[dt]:
				if (dt, n) in kept or any(b["doctype"] == dt and b["name"] == n for b in blockers):
					continue
				if dt in DRAFT_ONLY and cint(frappe.db.get_value(dt, n, "docstatus")) == 1:
					if dt in BLOCK_SUBMITTED:
						blockers.append({"doctype": dt, "name": n, "reason": _("submitted, in the ledger")})
					else:
						kept.add((dt, n))
					continue
				frontier.setdefault(dt, set()).add(n)

	customers = found["Customer"]
	if customers:
		for parent_dt, parent, _field, _row in _referrers("Customer", customers):
			if parent_dt in PLATFORM_BLOCKERS:
				blockers.append({"doctype": parent_dt, "name": parent, "reason": _("a platform subscription")})
	return {"found": {dt: sorted(v) for dt, v in found.items() if v}, "blockers": blockers}


def _party_records(found):
	"""Contacts and Addresses: (to delete, to keep without this party's link)."""
	mine = {dt: set(found.get(dt, ())) for dt in PARTIES}
	out = {}
	for party_dt in ("Contact", "Address"):
		links = frappe.get_all("Dynamic Link", filters={"parenttype": party_dt,
			"link_doctype": ["in", list(PARTIES)], "link_name": ["in", [n for v in mine.values() for n in v] or [""]]},
			pluck="parent", distinct=True)
		delete, keep = [], []
		for record in links:
			all_links = frappe.get_all("Dynamic Link", filters={"parenttype": party_dt, "parent": record},
				fields=["link_doctype", "link_name"])
			ours = all(l.link_name in mine.get(l.link_doctype, ()) for l in all_links)
			used = any(parent_dt not in CASCADE_SET or parent not in found.get(parent_dt, ())
				for parent_dt, parent, _f, _r in _referrers(party_dt, [record]))
			(delete if ours and not used else keep).append(record)
		out[party_dt] = (delete, keep)
	return out


def _unlinks(found):
	"""Rows of records that stay but name a record that goes: their link is cleared."""
	out = []
	for target, names in found.items():
		for parent, field, istable, optfield in _sources(target):
			if optfield or parent in ("Contact", "Address"):
				continue
			for parent_dt, owner, f, row in _referrers_one(parent, field, istable, names):
				if parent_dt in CASCADE_SET and owner in found.get(parent_dt, ()):
					continue
				out.append((row[0], row[1], f) if row else (parent_dt, owner, f))
	return out


def _summary(doc, plan, parties):
	counts = [{"doctype": dt, "label": _(LABELS.get(dt, dt)), "count": len(plan["found"][dt])}
		for dt in reversed(CASCADE) if plan["found"].get(dt)]
	for party_dt in ("Contact", "Address"):
		if parties[party_dt][0]:
			counts.append({"doctype": party_dt, "label": _(party_dt), "count": len(parties[party_dt][0])})
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"title": doc.get("customer_name") or doc.get("lead_name") or doc.get("consumer_name") or doc.name,
		"counts": counts,
		"total": sum(c["count"] for c in counts),
		"blockers": plan["blockers"],
		"kept": {"contacts": len(parties["Contact"][1]), "addresses": len(parties["Address"][1])},
	}


# ------------------------------------------------------------------ the calls
@frappe.whitelist(methods=["POST"])
def preview(doctype, name):
	"""What a delete would remove, and what would refuse it."""
	doc = _load(doctype, name)
	plan = collect(doc.doctype, doc.name)
	return _summary(doc, plan, _party_records(plan["found"]))


@frappe.whitelist(methods=["POST"])
def delete(doctype, name, confirm=None):
	"""Delete the lead or customer and everything gathered with it, or nothing at all.

	The Delete button is the confirmation. `confirm` is ignored: an older page still sends it.
	"""
	doc = _load(doctype, name)
	plan = collect(doc.doctype, doc.name)
	if plan["blockers"]:
		frappe.throw(_("{0} cannot be deleted: {1}. Cancel those in ERPNext first.").format(
			doc.name, ", ".join(f"{b['doctype']} {b['name']}" for b in plan["blockers"])), title=_("Not deleted"))
	found = plan["found"]
	parties = _party_records(found)
	summary = _summary(doc, plan, parties)
	run(found, parties)
	return {"deleted": summary["counts"], "total": summary["total"], "redirect": ROOTS[doctype]}


def run(found, parties):
	"""Clear the links of what stays, then cancel and delete what goes, deepest first.

	Any error raises, and the request's rollback undoes the lot. Files are taken off the
	records here but off the disk only once that has committed - a rollback cannot bring
	back a file already removed.
	"""
	files = _detach_files(found)
	for dt, name, field in _unlinks(found):
		frappe.db.set_value(dt, name, field, None, update_modified=False)
	mine = {dt: set(found.get(dt, ())) for dt in PARTIES}
	for party_dt, (_delete, keep) in parties.items():
		for record in keep:
			party = frappe.get_doc(party_dt, record)
			party.set("links", [l for l in party.links if l.link_name not in mine.get(l.link_doctype, ())])
			party.flags.ignore_permissions = True
			party.flags.ignore_mandatory = True
			party.save()
	# Contacts and Addresses first: ERPNext's Customer on_trash re-saves an address still
	# linked to it, which fails once the Solar Consumer it also names is gone. Every field
	# naming one is cleared before it goes - the records deleted after it too: a task
	# document's on_trash saves its project, whose Site Address would then name nothing.
	for party_dt, (delete, _keep) in parties.items():
		if not delete:
			continue
		for parent_dt, owner, field, row in _referrers(party_dt, delete):
			dt, name = row if row else (parent_dt, owner)
			frappe.db.set_value(dt, name, field, None, update_modified=False)
	for party_dt, (delete, _keep) in parties.items():
		for record in delete:
			if frappe.db.exists(party_dt, record):
				frappe.delete_doc(party_dt, record, force=True, ignore_permissions=True)
	for dt in CASCADE:
		for name in found.get(dt, ()):
			if not frappe.db.exists(dt, name):
				continue
			_cancel(dt, name)
			frappe.delete_doc(dt, name, force=True, ignore_permissions=True)
	frappe.db.after_commit.add(lambda: _remove_from_disk(files))


def _detach_files(found):
	"""The records' File rows, deleted from the table; their files stay on disk for now."""
	names = []
	for dt, records in found.items():
		names += frappe.get_all("File", filters={"attached_to_doctype": dt,
			"attached_to_name": ["in", list(records)], "is_folder": 0}, pluck="name")
	files = [frappe.get_doc("File", n) for n in names]
	if names:
		frappe.db.delete("File", {"name": ["in", names]})
	return files


def _remove_from_disk(files):
	"""Each file off the disk, unless another File row still uses it (a copy on a kept record)."""
	for f in files:
		shared = {"content_hash": f.content_hash} if f.content_hash else {"file_url": f.file_url}
		if not f.file_url or frappe.db.exists("File", shared):
			continue
		try:
			f.delete_file_data_content()
		except Exception:
			frappe.log_error(title=f"Cascade delete: file {f.file_url} not removed")


def _cancel(dt, name):
	"""Cancelled, so it can be deleted - by its own cancel, or marked cancelled where that refuses
	(its cancel reaching for a record already gone)."""
	if cint(frappe.db.get_value(dt, name, "docstatus")) != 1:
		return
	frappe.db.savepoint("a3s_cascade_cancel")
	try:
		doc = frappe.get_doc(dt, name)
		doc.flags.ignore_links = True
		doc.flags.ignore_permissions = True
		doc.cancel()
	except Exception:
		frappe.db.rollback(save_point="a3s_cascade_cancel")
		frappe.clear_messages()
		frappe.db.set_value(dt, name, "docstatus", 2, update_modified=False)
		for table in frappe.get_meta(dt).get_table_fields():
			frappe.db.set_value(table.options, {"parent": name, "parenttype": dt}, "docstatus", 2, update_modified=False)
