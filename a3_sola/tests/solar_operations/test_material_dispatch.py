# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The serial details go to the electrical contractor, and the job records that they did."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.solar_operations.doctype.material_dispatch_notice import material_dispatch_notice as ctl
from a3_sola.tests.solar_operations.fixtures import capture_serials, make_installation
from a3_sola.tests.solar_operations.test_contractor_and_work_orders import make_contractor
from a3_sola.tests.solar_operations.test_tasks import task_row


def make_notice(installation, contractor=None, **kwargs):
	values = {
		"doctype": "Material Dispatch Notice",
		"solar_installation": installation.name,
		"solar_contractor": (contractor or make_contractor(company=installation.company)).name,
	}
	values.update(kwargs)
	return frappe.get_doc(values).insert(ignore_permissions=True)


class TestMaterialDispatchNotice(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_creating_the_notice_starts_the_task(self):
		notice = make_notice(self.installation)
		row, _doc = task_row(self.installation, "MATL")
		self.assertEqual((row.status, row.task_document), ("In Progress", notice.name))

	def test_the_snapshot_is_the_installations_serials(self):
		capture_serials(self.installation, modules=6, inverters=1)
		notice = make_notice(self.installation)
		self.assertEqual(ctl.pull_serials(notice.name), 7)
		notice.reload()
		self.assertEqual(len([r for r in notice.serials if r.component_type == "Module"]), 6)

	def test_a_snapshot_does_not_trip_the_duplicate_serial_guard(self):
		"""The same serial legitimately appears on the job and on the notice sent about it."""
		capture_serials(self.installation, modules=2, inverters=1)
		notice = make_notice(self.installation)
		ctl.pull_serials(notice.name)
		installation = frappe.get_doc("Solar Installation", self.installation.name)
		installation.flags.ignore_validate_update_after_submit = True
		installation.save(ignore_permissions=True)  # the register re-validates its own serials

	def test_the_data_sheet_lists_the_snapshot_and_registers_on_the_job(self):
		capture_serials(self.installation, modules=3, inverters=1)
		notice = make_notice(self.installation)
		result = ctl.generate(notice.name)
		notice.reload()
		self.assertEqual(notice.completion_data_sheet, result["file_url"])
		_row, doc = task_row(self.installation, "MATL")
		reg = next(r for r in doc.documents if r.attachment == result["file_url"])
		self.assertEqual((reg.source_doctype, reg.source_document), ("Material Dispatch Notice", notice.name))

	def test_sending_needs_serials_and_an_address(self):
		contractor = make_contractor(company=self.installation.company, email_id=None)
		notice = make_notice(self.installation, contractor=contractor)
		with self.assertRaises(frappe.ValidationError) as ctx:
			ctl.send(notice.name)
		self.assertIn("serial", str(ctx.exception).lower())
		capture_serials(self.installation, modules=2, inverters=1)
		ctl.pull_serials(notice.name)
		with self.assertRaises(frappe.ValidationError) as ctx:
			ctl.send(notice.name)
		self.assertIn("email", str(ctx.exception).lower())

	def test_sending_records_the_email_completes_the_task_and_submits(self):
		capture_serials(self.installation, modules=2, inverters=1)
		notice = make_notice(self.installation)
		ctl.pull_serials(notice.name)
		ctl.send(notice.name)
		notice.reload()
		self.assertEqual((notice.docstatus, notice.status, notice.sent_to), (1, "Completed", "sparks@example.com"))
		self.assertTrue(notice.sent_on)
		self.assertTrue(frappe.db.exists("Communication", {"reference_doctype": "Material Dispatch Notice",
		                                                   "reference_name": notice.name}))
		row, _doc = task_row(self.installation, "MATL")
		self.assertEqual(row.status, "Completed")
		self.assertEqual(row.external_reference, "sparks@example.com")

	def test_an_unsent_notice_cannot_be_submitted(self):
		notice = make_notice(self.installation)
		notice.status = "Completed"
		with self.assertRaises(frappe.ValidationError):
			notice.submit()
