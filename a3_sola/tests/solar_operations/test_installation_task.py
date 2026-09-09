# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The shared task document: a status, an assignee, a date, a cost and its evidence."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today

from a3_sola.solar_operations.doctype.installation_task import installation_task as ctl
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_tasks import as_user, make_task, task_row


class TestInstallationTask(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_the_company_is_the_installations_not_the_sessions(self):
		other = frappe.get_all("Company", filters={"name": ["!=", self.installation.company]}, pluck="name", limit=1)
		task = make_task(self.installation, "FRM1", company=other[0] if other else None)
		self.assertEqual(task.company, self.installation.company)

	def test_a_task_the_job_does_not_have_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_task(self.installation, "FRM1", task_code="OTHER", task_name=None)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Installation Task", "solar_installation": self.installation.name, "task_code": "ADV",
				 "task_name": "x"}
			).run_method("validate_task_code") if False else make_task(self.installation, "OTHER", task_name="")

	def test_a_task_that_runs_elsewhere_is_refused_here(self):
		"""COMM runs in a Commissioning Report; a generic task pretending to be it is refused."""
		doc = frappe.get_doc(
			{"doctype": "Installation Task", "solar_installation": self.installation.name, "task_code": "FRM1"}
		)
		doc.task_code = "COMM"
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)
		self.assertIn("not here", str(ctx.exception))

	def test_one_open_document_per_task(self):
		make_task(self.installation, "FRM1")
		with self.assertRaises(frappe.ValidationError):
			make_task(self.installation, "FRM1")

	def test_the_task_name_comes_from_the_installations_row(self):
		task = make_task(self.installation, "KTST")
		self.assertEqual(task.task_name, "DISCOM Inspection & Pre-Energisation Test")

	def test_completion_needs_the_tasks_evidence(self):
		task = make_task(self.installation, "CCERT")
		with self.assertRaises(frappe.ValidationError) as ctx:
			ctl.complete(task.name)
		self.assertIn("Certificate", str(ctx.exception))

		task.certificate = "/files/cc.pdf"
		task.certificate_no = "CC-9"
		task.save(ignore_permissions=True)
		ctl.complete(task.name)
		row, _doc = task_row(self.installation, "CCERT")
		self.assertEqual(row.status, "Completed")

	def test_generating_a_document_attaches_it_here_and_registers_it_on_the_job(self):
		task = make_task(self.installation, "FRM1")
		result = ctl.generate(task.name, "KSEB-FORM-1")
		task.reload()
		self.assertEqual(len(task.generated), 1)
		self.assertEqual(task.generated[0].file, result["file_url"])
		self.assertEqual(task.status, "In Progress")
		_row, doc = task_row(self.installation, "FRM1")
		reg = next(r for r in doc.documents if r.attachment == result["file_url"])
		self.assertEqual((reg.source_doctype, reg.source_document, reg.stage_code), ("Installation Task", task.name, "FRM1"))

		ctl.generate(task.name, "KSEB-FORM-1")
		task.reload()
		self.assertEqual(len(task.generated), 1, "regenerating replaces, it does not duplicate")

	def test_document_choices_lists_only_installed_templates(self):
		task = make_task(self.installation, "FRM1")
		codes = [c["code"] for c in ctl.document_choices(task.name)]
		self.assertEqual(codes, ["KSEB-FORM-1"])

	def test_attaching_evidence_registers_it(self):
		task = make_task(self.installation, "KTST")
		ctl.attach_evidence(task.name, "Signed checklist", "/files/chk.pdf", reference_no="AE/22")
		_row, doc = task_row(self.installation, "KTST")
		reg = next(r for r in doc.documents if r.source_document == task.name)
		self.assertEqual((reg.document_name, reg.document_reference_no), ("Signed checklist", "AE/22"))

	def test_skipping_a_mandatory_task_from_the_document_needs_a_manager(self):
		task = make_task(self.installation, "FRM1")
		as_user("ops.exec@example.com", ["Solar Operations Executive"])
		with self.assertRaises(frappe.PermissionError):
			ctl.skip(task.name, "Not needed")

	def test_skipping_from_the_document_skips_the_row(self):
		task = make_task(self.installation, "KTST")
		ctl.skip(task.name, "Section office waived the inspection")
		row, _doc = task_row(self.installation, "KTST")
		self.assertEqual((row.status, row.skip_reason), ("Skipped", "Section office waived the inspection"))

	def test_money_is_invisible_below_permlevel_one(self):
		meta = frappe.get_meta("Installation Task")
		for field in ("cost", "amount", "meter_cost"):
			self.assertEqual(meta.get_field(field).permlevel, 1, field)

	def test_pulling_a_bank_tranche_copies_the_loan_figure(self):
		installation = make_installation(is_financed=1)
		loan = frappe.get_doc(
			{
				"doctype": "Loan Application",
				"solar_installation": installation.name,
				"company": installation.company,
				"lender": "SBI",
				"lender_branch": "Aluva",
				"status": "Sanctioned",
				"disbursements": [
					{"tranche": "Advance", "amount": 150500, "utr_or_reference": "UTR-77", "disbursement_date": today()}
				],
			}
		).insert(ignore_permissions=True)
		task = make_task(installation, "ADV")
		out = ctl.pull_loan_tranche(task.name)
		task.reload()
		self.assertEqual(out["amount"], 150500)
		self.assertEqual((task.payer, task.loan_application, task.payment_reference), ("Bank", loan.name, "UTR-77"))

	def test_a_self_funded_job_has_no_tranche_to_pull(self):
		task = make_task(self.installation, "ADV")
		with self.assertRaises(frappe.ValidationError):
			ctl.pull_loan_tranche(task.name)
