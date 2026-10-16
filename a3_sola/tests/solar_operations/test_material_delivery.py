# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Material reaches the site from the vendor's door or through the company godown; Material
Dispatch follows the procurement tasks' methods."""

from io import BytesIO

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader

from a3_sola.api import material_delivery as md
from a3_sola.api import portal_crud, purchase_list
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestMaterialDelivery(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.job = make_installation()
		self.task = {}
		for code in md.PROCUREMENT:
			made = portal_crud.create_record(slug="installation-tasks", source_dt="Solar Installation",
				source=self.job.name, source_task=code,
				__items=frappe.as_json([{"material": "Pipe A", "qty": 4, "uom": "Nos"}]))
			self.task[code] = made["name"]

	def dispatch(self):
		row = next(r for r in frappe.get_doc("Solar Installation", self.job.name).stages if r.stage_code == md.DISPATCH)
		return row.status, row.skip_reason

	def set_method(self, code, method):
		task = frappe.get_doc("Installation Task", self.task[code])
		task.delivery_method = method
		task.save(ignore_permissions=True)
		return task

	def test_dispatch_is_skipped_only_while_everything_ships_from_the_vendor(self):
		for code in md.PROCUREMENT:
			self.set_method(code, md.VENDOR)
		self.assertEqual(self.dispatch(), ("Skipped", md.SKIP_REASON))
		self.set_method("PROC", md.GODOWN)
		self.assertEqual(self.dispatch(), ("Pending", None))

	def test_a_dispatch_skipped_by_hand_stays_skipped(self):
		inst = frappe.get_doc("Solar Installation", self.job.name)
		row = next(r for r in inst.stages if r.stage_code == md.DISPATCH)
		row.status, row.skip_reason = "Skipped", "Customer collected it"
		inst.flags.ignore_validate_update_after_submit = True
		inst.save(ignore_permissions=True)
		self.set_method("PROC", md.GODOWN)
		self.assertEqual(self.dispatch(), ("Skipped", "Customer collected it"))

	def test_ship_to_follows_the_method(self):
		vendor = self.set_method("SPROC", md.VENDOR)
		consumer = frappe.db.get_value("Solar Installation", self.job.name, "consumer_name")
		self.assertIn(consumer, vendor.ship_to)
		godown = self.set_method("SPROC", md.GODOWN)
		self.assertTrue(godown.ship_to.startswith("Company godown"))
		self.assertEqual(godown.bill_to, vendor.bill_to)
		text = " ".join(PdfReader(BytesIO(purchase_list.render(godown)[1])).pages[0].extract_text().split())
		self.assertIn("Company godown", text)
		self.assertIn("From company godown", text)
