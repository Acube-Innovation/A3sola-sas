# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A procurement task's purchase list is sent to the supplier by WhatsApp or email."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import portal_crud, portal_share
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestPurchaseListShare(FrappeTestCase):
	def setUp(self):
		self.job = make_installation()
		self.task = {}
		for code in ("SPROC", "PROC"):
			made = portal_crud.create_record(slug="installation-tasks", source_dt="Solar Installation",
				source=self.job.name, source_task=code,
				__items=frappe.as_json([{"material": "Pipe A", "qty": 4, "uom": "Nos"}]))
			self.task[code] = frappe.get_doc("Installation Task", made["name"])

	def test_both_procurement_tasks_can_send_their_list(self):
		for code, title in (("SPROC", "Structure Material"), ("PROC", "Material")):
			links = portal_share.share_links(self.task[code], "/x")
			self.assertIn(title, links["subject"])
			self.assertIn(title + " purchase list", links["message"])
			self.assertTrue(links["whatsapp"].startswith("https://wa.me/"))
			self.assertFalse(links["locked"])
			self.assertTrue(portal_share._pdf(self.task[code]).startswith(b"%PDF"))

	def test_the_supplier_link_opens_only_with_its_key(self):
		name = self.task["PROC"].name
		frappe.local.request_ip = "127.0.0.1"  # the link is rate-limited by the caller's address
		with self.assertRaises(frappe.PermissionError):
			portal_share.shared_pdf("Installation Task", name, "not-the-key")

	def test_email_needs_a_recipient(self):
		with self.assertRaises(frappe.ValidationError):
			portal_share.send_email("Installation Task", self.task["SPROC"].name, "", "s", "m")


class TestPendingItems(FrappeTestCase):
	"""The whole list goes to the supplier; what they could not give is marked Pending Qty and
	moves off the list into Pending Items - its own list, for the next supplier - and back onto
	the list when ticked Received. The task waits until nothing is pending."""

	def setUp(self):
		self.job = make_installation()
		made = portal_crud.create_record(slug="installation-tasks", source_dt="Solar Installation",
			source=self.job.name, source_task="PROC", __items=frappe.as_json([
				{"material": "Pipe A", "qty": 4, "uom": "Nos"}, {"material": "Clamp B", "qty": 10, "uom": "Nos"}]))
		self.task = frappe.get_doc("Installation Task", made["name"])

	def mark(self, *pending):
		for row, qty in zip(self.task.materials, pending):
			row.pending_qty = qty
		self.task.save(ignore_permissions=True)

	def supplier(self, name, mobile, email):
		if not frappe.db.exists("Supplier", name):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": frappe.db.get_value(
				"Supplier Group", {}, "name"), "mobile_no": mobile, "email_id": email}).insert(ignore_permissions=True)
		return name

	def test_the_shortfall_moves_off_the_list_into_pending_items(self):
		from a3_sola.api import purchase_list

		self.mark(0, 3)
		self.assertEqual([(r.material, r.qty, r.pending_qty) for r in self.task.materials],
			[("Pipe A", 4, 0), ("Clamp B", 7, 0)])
		self.assertEqual([(r.material, r.qty, r.received) for r in self.task.pending_items], [("Clamp B", 3, 0)])
		out = purchase_list.lines(self.task, pending=True)
		self.assertEqual(out["rows"], [{"material": "Clamp B", "uom": "Nos", "qty": 3}])
		self.assertIn("Pending Items", out["title"])
		self.assertTrue(portal_share._pdf(self.task, portal_share.PENDING).startswith(b"%PDF"))
		# Short again: added to the item already pending.
		self.mark(0, 2)
		self.assertEqual([(r.material, r.qty) for r in self.task.pending_items], [("Clamp B", 5)])

	def test_received_puts_it_back_on_the_list_and_off_the_pending_list(self):
		from a3_sola.api import purchase_list

		self.mark(0, 3)
		row = self.task.pending_items[0].name
		purchase_list.receive_pending(self.task.name, row, 1)
		self.task.reload()
		self.assertEqual(self.task.materials[1].qty, 10)
		self.assertTrue(self.task.pending_items[0].received)
		self.assertEqual(purchase_list.pending_rows(self.task), [])
		purchase_list.receive_pending(self.task.name, row, 0)
		self.task.reload()
		self.assertEqual((self.task.materials[1].qty, len(purchase_list.pending_rows(self.task))), (7, 1))

	def test_nothing_pending_nothing_to_send(self):
		from a3_sola.api import purchase_list

		with self.assertRaises(frappe.ValidationError):
			purchase_list.render(self.task, pending=True)

	def test_a_pending_quantity_cannot_exceed_the_list(self):
		with self.assertRaises(frappe.ValidationError):
			self.mark(5)

	def test_the_pending_list_goes_to_the_next_supplier(self):
		first = self.supplier("First Steel Co", "9000011111", "first@steel.in")
		second = self.supplier("Second Steel Co", "9000033333", "second@steel.in")
		self.task.supplier, self.task.pending_supplier = first, second
		self.mark(2, 0)
		full = portal_share.share_links(self.task, "/x")
		pending = portal_share.share_links(self.task, "/y", part=portal_share.PENDING)
		self.assertEqual(full["email_to"], "first@steel.in")
		self.assertEqual((pending["email_to"], pending["whatsapp_to"]), ("second@steel.in", "9000033333"))
		self.assertIn("pending items", pending["message"])
		self.assertIn("Pending Items", pending["subject"])

	def test_each_link_opens_only_its_own_list(self):
		self.mark(2, 0)
		name = self.task.name
		frappe.local.request_ip = "127.0.0.1"
		full_key = portal_share.share_key("Installation Task", name)
		pending_key = portal_share.share_key("Installation Task", name, portal_share.PENDING)
		self.assertNotEqual(full_key, pending_key)
		portal_share.shared_pdf("Installation Task", name, pending_key, part=portal_share.PENDING)
		self.assertIn(" - Pending Items ", frappe.local.response.filename)  # the customer first
		with self.assertRaises(frappe.PermissionError):
			portal_share.shared_pdf("Installation Task", name, full_key, part=portal_share.PENDING)
		with self.assertRaises(frappe.PermissionError):
			portal_share.shared_pdf("Installation Task", name, pending_key, part="something-else")

	def test_the_task_waits_for_the_pending_items(self):
		from a3_sola.api import purchase_list

		self.mark(0, 3)
		self.task.status = "Completed"
		with self.assertRaises(frappe.ValidationError):
			self.task.save(ignore_permissions=True)
		self.task.reload()
		purchase_list.receive_pending(self.task.name, self.task.pending_items[0].name, 1)
		self.task.reload()
		self.task.status = "Completed"
		self.task.save(ignore_permissions=True)
