# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""How a procurement task's material reaches the site.

Two ways, chosen on each procurement task (Structure Material Procurement, Material
Procurement): the vendor ships straight to the customer and bills the company - vendor door
shipping - or the vendor delivers to the company godown and the company dispatches it from
there. The bill always goes to the company; the material goes to the customer's site, or to
the godown (the company's own address).

Material Dispatch is the godown's delivery to the customer, so when every procurement task
on a job ships from the vendor's door there is nothing to dispatch: the task is skipped, with
its reason, and comes back the moment any material goes through the godown.
"""

import frappe
from frappe import _

VENDOR = "Vendor door shipping"
GODOWN = "From company godown"
PROCUREMENT = ("SPROC", "PROC")
DISPATCH = "DISP"
#: Why Material Dispatch is skipped - and the mark that it was skipped here, not by hand.
SKIP_REASON = "Shipped by the vendor to the customer"


def company_lines(company):
	"""The company as the bill (and the godown) reads it: name, address, phone, email."""
	c = frappe.db.get_value("Company", company, ["company_name", "epc_name", "epc_address", "epc_contact_no", "epc_email"],
		as_dict=True) or frappe._dict()
	return [c.epc_name or c.company_name or company, (c.epc_address or "").strip(),
		_("Phone: {0}").format(c.epc_contact_no) if c.epc_contact_no else "",
		_("Email: {0}").format(c.epc_email) if c.epc_email else ""]


def site(inst):
	"""(name, address, mobile, (lat, lng) or None) of the customer's site."""
	from a3_sola.api import documents, purchase_list

	text = frappe.db.get_value("Solar Consumer", inst.solar_consumer, "installation_site_address") if inst.get("solar_consumer") else None
	if not text:
		address = frappe.get_doc("Address", inst.installation_address) if inst.get("installation_address") else None
		text = documents._address_text(address) if address else documents._party_address(None, inst)
	return inst.consumer_name or inst.name, text or "", inst.get("consumer_mobile") or "", purchase_list.location(inst)


def blocks(task, inst=None):
	"""(bill_to, ship_to) of a procurement task, as text one part to a line."""
	inst = inst or frappe.get_doc("Solar Installation", task.solar_installation)
	bill = company_lines(inst.company)
	if task.get("delivery_method") == GODOWN:
		ship = [_("Company godown")] + bill
	else:
		name, address, mobile, point = site(inst)
		ship = [name, address, _("Phone: {0}").format(mobile) if mobile else "",
			_("Location: {0}, {1}").format(round(point[0], 5), round(point[1], 5)) if point else ""]
	join = lambda lines: "\n".join(line for line in lines if line) or None  # noqa: E731
	return join(bill), join(ship)


def sync_dispatch(installation):
	"""Skip Material Dispatch while every procurement task ships from the vendor's door, and put
	it back when any goes through the godown. A dispatch done, or skipped by hand, stays."""
	from a3_sola.api import stages

	inst = frappe.get_doc("Solar Installation", installation) if isinstance(installation, str) else installation
	row = next((r for r in inst.stages if r.stage_code == DISPATCH), None)
	if not row:
		return None
	methods = []
	for code in PROCUREMENT:
		stage = next((r for r in inst.stages if r.stage_code == code), None)
		if not stage or stage.status == "Skipped":
			continue
		task = frappe.get_all("Installation Task", filters={"solar_installation": inst.name, "task_code": code,
			"docstatus": ["<", 2]}, fields=["delivery_method"], order_by="creation desc", limit=1)
		methods.append(task[0].delivery_method if task else None)
	vendor_only = bool(methods) and all(m == VENDOR for m in methods)
	if vendor_only and row.status == "Pending":
		row.status, row.skip_reason = "Skipped", SKIP_REASON
		stages._save(inst, _("{0} skipped: the material is shipped by the vendor straight to the customer.").format(row.stage_name))
		return "Skipped"
	if not vendor_only and row.status == "Skipped" and row.skip_reason == SKIP_REASON:
		row.status, row.skip_reason = "Pending", None
		stages._save(inst, _("{0} is needed again: material goes through the company godown.").format(row.stage_name))
		return "Pending"
	return None
