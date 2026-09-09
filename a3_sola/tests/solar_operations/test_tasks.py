# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Documents drive tasks.

The thing being protected: nothing in a controller advances a task any more. A task row
changes because the document that carries it out was saved, submitted or cancelled, and
one hook - `tasks.sync_from_document` - reads the row's new state off it. These tests hold
that hook to each doctype's rule, and hold the by-hand transitions to their refusals.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from a3_sola.api import tasks
from a3_sola.solar_operations.doctype.portal_application.portal_application import approve
from a3_sola.tests.solar_operations.fixtures import make_installation


def task_row(installation, code):
	doc = frappe.get_doc("Solar Installation", installation.name)
	return next(r for r in doc.stages if r.stage_code == code), doc


def make_task(installation, code, **kwargs):
	values = {"doctype": "Installation Task", "solar_installation": installation.name, "task_code": code}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


def make_fee(installation, fee_type, **kwargs):
	values = {
		"doctype": "Statutory Fee Payment",
		"solar_installation": installation.name,
		"company": installation.company,
		"fee_type": fee_type,
		"paid_by": "Customer Directly",
		"payment_date": today(),
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


def make_application(installation, application_type, **kwargs):
	values = {
		"doctype": "Portal Application",
		"solar_installation": installation.name,
		"company": installation.company,
		"application_type": application_type,
		"application_number": "APP-" + frappe.generate_hash(length=6).upper(),
		"application_date": today(),
		"application_status": "Submitted",
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


def make_work_order(installation, work_order_type, **kwargs):
	values = {
		"doctype": "Installation Work Order",
		"solar_installation": installation.name,
		"company": installation.company,
		"work_order_type": work_order_type,
		"work_order_kind": kwargs.pop("work_order_kind", "Structure" if work_order_type == "Structure Erection" else "Installation"),
		"planned_start_date": today(),
		"planned_end_date": add_days(today(), 2),
		"safety_briefing_done": 1,
		"ppe_verified": 1,
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.flags.ignore_permissions = True
	return doc.insert(ignore_permissions=True)


def as_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
	frappe.set_user(email)


class TestDocumentsDriveTasks(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_creating_a_task_document_claims_the_row(self):
		task = make_task(self.installation, "FRM1")
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual(row.status, "In Progress")
		self.assertEqual((row.task_doctype, row.task_document), ("Installation Task", task.name))
		self.assertTrue(row.actual_start_date)

	def test_only_a_submitted_document_completes_the_row(self):
		task = make_task(self.installation, "FRM1", uploads=[{"document_name": "Form 1", "attachment": "/files/f1.pdf"}])
		task.status = "Completed"
		task.save(ignore_permissions=True)
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual(row.status, "In Progress", "a draft marked Completed is not done yet")

		task.submit()
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual(row.status, "Completed")
		self.assertEqual(str(row.actual_completion_date), today())
		self.assertEqual(row.completed_by, frappe.session.user)

	def test_cancelling_the_document_gives_the_row_back(self):
		task = make_task(self.installation, "FRM1", uploads=[{"document_name": "Form 1", "attachment": "/files/f1.pdf"}])
		task.status = "Completed"
		task.save(ignore_permissions=True)
		task.submit()
		task.cancel()
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual(row.status, "Pending")
		self.assertFalse(row.task_document)
		self.assertFalse(row.actual_completion_date)

	def test_the_upload_lands_in_the_register_naming_the_task(self):
		task = make_task(self.installation, "CCERT", certificate="/files/cc.pdf", certificate_no="CC-1")
		_row, doc = task_row(self.installation, "CCERT")
		reg = next(r for r in doc.documents if r.source_document == task.name)
		self.assertEqual(reg.attachment, "/files/cc.pdf")
		self.assertEqual(reg.stage_code, "CCERT")
		self.assertEqual(reg.document_kind, "Uploaded")

	def test_a_fee_payment_completes_its_fee_task_and_rolls_the_cost(self):
		fee = make_fee(self.installation, "Application Fee")
		row, _doc = task_row(self.installation, "F1PAY")
		self.assertEqual(row.status, "In Progress")
		fee.submit()
		row, doc = task_row(self.installation, "F1PAY")
		self.assertEqual(row.status, "Completed")
		self.assertEqual(row.task_document, fee.name)
		self.assertGreater(row.cost, 0, "the resolved fee is the task's cost")
		self.assertEqual(row.cost, fee.amount_gross)

	def test_paying_the_form1_fee_opens_the_thirty_day_window_for_form2(self):
		fee = make_fee(self.installation, "Application Fee")
		fee.submit()
		kforms, doc = task_row(self.installation, "KFORMS")
		self.assertEqual(str(doc.form2_due_on), add_days(today(), 30))
		self.assertEqual(str(kforms.due_date), add_days(today(), 30))

	def test_the_registration_fee_is_the_form2_payment(self):
		make_fee(self.installation, "Registration Fee").submit()
		row, _doc = task_row(self.installation, "F2PAY")
		self.assertEqual(row.status, "Completed")

	def test_a_portal_application_maps_by_type_blocks_on_a_query_and_completes_on_approval(self):
		application = make_application(self.installation, "National Portal")
		row, _doc = task_row(self.installation, "NPA")
		self.assertEqual((row.status, row.task_document), ("In Progress", application.name))

		application.submit()
		application.application_status = "Query Raised"
		application.append(
			"queries", {"query_date": today(), "query_description": "Load sanction letter unreadable", "is_resolved": 0}
		)
		application.flags.ignore_validate_update_after_submit = True
		application.save(ignore_permissions=True)
		row, _doc = task_row(self.installation, "NPA")
		self.assertEqual(row.status, "Blocked")
		self.assertIn("unreadable", row.blocked_reason)

		application.approval_attachment = "/files/approval.pdf"
		application.flags.ignore_validate_update_after_submit = True
		application.save(ignore_permissions=True)
		approve(application.name, approval_number="NP-OK-1")
		row, doc = task_row(self.installation, "NPA")
		self.assertEqual(row.status, "Completed")
		self.assertEqual(row.external_reference, "NP-OK-1")
		self.assertTrue(any(r.source_document == application.name for r in doc.documents))

	def test_a_second_document_does_not_steal_a_row_another_live_one_holds(self):
		first = make_application(self.installation, "National Portal")
		make_application(self.installation, "National Portal")
		row, _doc = task_row(self.installation, "NPA")
		self.assertEqual(row.task_document, first.name)

	def test_the_work_order_type_decides_which_task_it_is(self):
		make_work_order(self.installation, "Structure Erection")
		make_work_order(self.installation, "Module Mounting")
		structure, _doc = task_row(self.installation, "IWOS")
		install, _doc = task_row(self.installation, "IWOI")
		self.assertEqual(structure.status, "In Progress")
		self.assertEqual(install.status, "In Progress")
		self.assertNotEqual(structure.task_document, install.task_document)

	def test_a_document_for_a_skipped_task_puts_it_back(self):
		installation = make_installation(is_financed=0)
		row, _doc = task_row(installation, "LOAN")
		self.assertEqual(row.status, "Skipped")
		frappe.get_doc(
			{
				"doctype": "Loan Application",
				"solar_installation": installation.name,
				"company": installation.company,
				"lender": "SBI",
				"lender_branch": "Aluva",
				"status": "Documents Submitted",
			}
		).insert(ignore_permissions=True)
		row, _doc = task_row(installation, "LOAN")
		self.assertEqual(row.status, "In Progress")
		self.assertFalse(row.skip_reason)

	def test_a_subsidy_claim_owns_three_rows_and_starts_only_the_request(self):
		claim = frappe.get_doc(
			{
				"doctype": "Subsidy Claim",
				"company": self.installation.company,
				"solar_installation": self.installation.name,
				"expected_subsidy_amount": 78000,
				"claim_model": "Customer Claims Directly",
			}
		).insert(ignore_permissions=True)
		for code, status in (("SUBREQ", "In Progress"), ("CORR", "Pending"), ("DBT", "In Progress")):
			row, _doc = task_row(self.installation, code)
			self.assertEqual(row.status, status, code)
			self.assertEqual(row.task_document, claim.name, code)


class TestTheTaskButton(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def test_a_linked_document_is_what_opens(self):
		task = make_task(self.installation, "FRM1")
		target = tasks.open_task(self.installation.name, "FRM1")
		self.assertEqual((target["doctype"], target["name"]), ("Installation Task", task.name))

	def test_an_unlinked_document_of_the_right_kind_is_found(self):
		fee = make_fee(self.installation, "Registration Fee")
		# pretend the link was lost
		row, doc = task_row(self.installation, "F2PAY")
		row.task_document = None
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
		target = tasks.open_task(self.installation.name, "F2PAY")
		self.assertEqual(target["name"], fee.name)

	def test_nothing_yet_means_a_new_document_prefilled(self):
		frappe.db.set_single_value("A3 Sola Settings", "auto_create_fee_payment_on_stage", 0)
		target = tasks.open_task(self.installation.name, "F1PAY")
		self.assertIsNone(target["name"])
		self.assertEqual(target["doctype"], "Statutory Fee Payment")
		self.assertEqual(target["route_options"]["fee_type"], "Application Fee")
		self.assertEqual(target["route_options"]["solar_installation"], self.installation.name)

	def test_the_fee_setting_makes_the_button_insert_the_draft_itself(self):
		"""Settings.auto_create_fee_payment_on_stage, implemented at last: the draft exists,
		prefilled and saveable, before the user ever sees it."""
		frappe.db.set_single_value("A3 Sola Settings", "auto_create_fee_payment_on_stage", 1)
		target = tasks.open_task(self.installation.name, "F1PAY")
		self.assertTrue(target["name"])
		draft = frappe.get_doc("Statutory Fee Payment", target["name"])
		self.assertEqual((draft.fee_type, draft.docstatus), ("Application Fee", 0))
		row, _doc = task_row(self.installation, "F1PAY")
		self.assertEqual(row.task_document, draft.name)

	def test_the_order_task_opens_the_order_or_nothing(self):
		target = tasks.open_task(self.installation.name, "ORD")
		self.assertEqual(target["doctype"], "Sales Order")
		self.assertIsNone(target["name"])
		self.assertIsNone(target["route_options"])


class TestTransitionsByHand(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_completing_by_hand_needs_no_document(self):
		tasks.complete_task(self.installation.name, "KTST", external_reference="AE visit")
		row, _doc = task_row(self.installation, "KTST")
		self.assertEqual(row.status, "Completed")
		self.assertEqual(row.external_reference, "AE visit")

	def test_completing_by_hand_is_refused_when_a_document_holds_the_task(self):
		make_task(self.installation, "FRM1")
		as_user("ops.exec@example.com", ["Solar Operations Executive"])
		with self.assertRaises(frappe.ValidationError) as ctx:
			tasks.complete_task(self.installation.name, "FRM1")
		self.assertIn("Complete it there", str(ctx.exception))

	def test_a_manager_may_still_complete_over_a_document(self):
		make_task(self.installation, "FRM1")
		tasks.complete_task(self.installation.name, "FRM1")
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual(row.status, "Completed")

	def test_skipping_a_mandatory_task_needs_a_manager(self):
		as_user("ops.exec@example.com", ["Solar Operations Executive"])
		with self.assertRaises(frappe.PermissionError):
			tasks.skip_task(self.installation.name, "FRM1", "Not needed")

	def test_skipping_is_refused_while_a_document_holds_the_task(self):
		make_task(self.installation, "FRM1")
		with self.assertRaises(frappe.ValidationError):
			tasks.skip_task(self.installation.name, "FRM1", "Not needed")

	def test_skip_and_unskip(self):
		tasks.skip_task(self.installation.name, "REVIEW", "Customer declined")
		row, _doc = task_row(self.installation, "REVIEW")
		self.assertEqual((row.status, row.skip_reason), ("Skipped", "Customer declined"))
		tasks.unskip_task(self.installation.name, "REVIEW")
		row, _doc = task_row(self.installation, "REVIEW")
		self.assertEqual(row.status, "Pending")

	def test_block_and_unblock_any_row(self):
		tasks.block_task(self.installation.name, "KFORMS", "Section office closed")
		row, doc = task_row(self.installation, "KFORMS")
		self.assertEqual((row.status, doc.status), ("Blocked", "Blocked"))
		tasks.unblock_task(self.installation.name, "KFORMS", "Reopened Monday")
		row, _doc = task_row(self.installation, "KFORMS")
		self.assertEqual(row.status, "Pending", "no document holds it, so it goes back to Pending")

	def test_reopen_resets_one_row_only(self):
		tasks.complete_task(self.installation.name, "FRM1", silent=True)
		tasks.complete_task(self.installation.name, "KTST", silent=True)
		tasks.reopen_task(self.installation.name, "FRM1", "Wrong consumer number on the form")
		frm1, _doc = task_row(self.installation, "FRM1")
		ktst, _doc = task_row(self.installation, "KTST")
		self.assertEqual(frm1.status, "Pending")
		self.assertEqual(ktst.status, "Completed")

	def test_assigning_sets_the_row(self):
		tasks.assign_task(self.installation.name, "FRM1", "Administrator", add_days(today(), 2))
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual(row.assigned_to, "Administrator")
		self.assertEqual(str(row.due_date), add_days(today(), 2))
		self.assertEqual(row.assigned_by, "Administrator")


class TestStatusFollowsTasks(FrappeTestCase):
	def test_commissioning_and_disbursement_set_the_job_status(self):
		installation = make_installation()
		tasks.complete_task(installation.name, "COMM", silent=True)
		self.assertEqual(frappe.db.get_value("Solar Installation", installation.name, "status"), "Commissioned")
		tasks.complete_task(installation.name, "DBT", silent=True)
		self.assertEqual(frappe.db.get_value("Solar Installation", installation.name, "status"), "Subsidy Claimed")


class TestDeletedTaskDocuments(FrappeTestCase):
	"""A task document can vanish behind the engine's back; the job must never point at nothing."""

	def setUp(self):
		self.installation = make_installation()

	def _task(self, code="FRM1"):
		doc = frappe.get_doc({"doctype": "Installation Task", "solar_installation": self.installation.name, "task_code": code})
		doc.flags.ignore_permissions = True
		return doc.insert(ignore_permissions=True)

	def test_deleting_the_document_releases_its_row(self):
		task = self._task()
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual((row.status, row.task_document), ("In Progress", task.name))
		frappe.delete_doc("Installation Task", task.name, force=True, ignore_permissions=True)
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual((row.status, row.task_document), ("Pending", None))

	def test_a_link_to_nothing_heals_on_save_and_is_not_rendered(self):
		from a3_sola.solar_operations.doctype.solar_installation.solar_installation import get_task_grid_html

		task = self._task()
		# A hard delete that bypasses the engine, as a purge or a raw delete would.
		frappe.db.delete("Installation Task", {"name": task.name})
		frappe.db.delete("Task Attachment", {"parent": task.name})
		frappe.db.delete("Task Generated Document", {"parent": task.name})
		frappe.clear_document_cache("Installation Task", task.name)
		self.assertNotIn(task.name, get_task_grid_html(self.installation.name))
		doc = frappe.get_doc("Solar Installation", self.installation.name)
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)  # used to fail: Could not find Row #n: Document
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual((row.status, row.task_document), ("Pending", None))
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": self.installation.name, "content": ["like", "%no longer exist%"]}))

	def test_a_document_from_another_company_claims_nothing(self):
		other = frappe.db.get_value("Company", {"name": ["!=", self.installation.company]}, "name")
		doc = frappe.get_doc({"doctype": "Installation Task", "solar_installation": self.installation.name,
		                      "task_code": "FRM1", "company": other})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate = True  # the way an isolation probe seeds its bare rows
		doc.flags.ignore_links = True
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
		row, _doc = task_row(self.installation, "FRM1")
		self.assertEqual((row.status, row.task_document), ("Pending", None))
