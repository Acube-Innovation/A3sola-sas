# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Form 2 and Form 3 are two submissions: Form 2 within thirty days of the Form 1 fee, with no
agreement, then its fee, then Form 3 with the executed agreement. Each names the section's
Assistant Engineer and phone, asks the dates Form 1 does, and keeps the cost off the portal."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.patches.v1_2 import split_form2_form3
from a3_sola.solar_operations.doctype.document_pack import document_pack as ctl
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_document_pack import make_pack
from a3_sola.tests.solar_operations.test_tasks import task_row
from a3_sola.www.a3solaportal import collections


class TestForm2Form3(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()
		self.section = frappe.db.get_value("Solar Installation", self.installation.name, "discom_section")

	def codes(self):
		return [r.stage_code for r in frappe.get_doc("Solar Installation", self.installation.name).stages]

	def test_form2_its_fee_then_form3(self):
		codes = self.codes()
		order = [codes.index(c) for c in ("FRM2", "F2PAY", "KFORMS")]
		self.assertEqual(order, sorted(order))
		names = {r.stage_code: r.stage_name for r in frappe.get_doc("Solar Installation", self.installation.name).stages}
		self.assertEqual((names["FRM2"], names["KFORMS"]), ("Form 2 Submission", "Form 3 Submission"))

	def test_form2_holds_only_form2_and_needs_no_agreement(self):
		self.assertEqual(ctl.PACKS["KSEB Form 2"]["items"], ["KSEB-FORM-2"])
		self.assertNotIn("KSEB-FORM-2", ctl.PACKS["KSEB Form 3"]["items"])
		self.assertIn("@agreement_print", ctl.PACKS["KSEB Form 3"]["items"])
		pack = make_pack(self.installation, "KSEB Form 2")
		self.assertEqual((pack.task_code, pack.solar_agreement), ("FRM2", None))
		row, _doc = task_row(self.installation, "FRM2")
		self.assertEqual((row.status, row.task_document), ("In Progress", pack.name))
		agreement = frappe.get_meta("Document Pack").get_field("solar_agreement")
		self.assertEqual(agreement.mandatory_depends_on, "eval:doc.pack_type=='KSEB Form 3'")

	def test_form2_completes_on_the_acknowledgement(self):
		pack = make_pack(self.installation, "KSEB Form 2")
		pack.append("uploads", {"document_name": "Form 2 signed", "attachment": "/files/form2.pdf"})
		pack.save(ignore_permissions=True)
		ctl.mark_acknowledged(pack.name, acknowledgement_no="AE/F2/0001")
		ctl.complete(pack.name)
		row, _doc = task_row(self.installation, "FRM2")
		self.assertEqual(row.status, "Completed")

	def test_the_sections_engineer_and_phone_are_taken(self):
		frappe.db.set_value("DISCOM Section", self.section,
			{"assistant_engineer_name": "Smt. Latha K.", "assistant_engineer_phone": "9447000001"})
		pack = make_pack(self.installation, "KSEB Form 2")
		self.assertEqual((pack.ae_name, pack.ae_phone), ("Smt. Latha K.", "9447000001"))

	def test_an_engineer_named_on_the_pack_fills_a_blank_section_only(self):
		frappe.db.set_value("DISCOM Section", self.section,
			{"assistant_engineer_name": None, "assistant_engineer_phone": None})
		make_pack(self.installation, "KSEB Form 2", ae_name="Sri. Anil", ae_phone="9447000002")
		self.assertEqual(frappe.db.get_value("DISCOM Section", self.section,
			["assistant_engineer_name", "assistant_engineer_phone"]), ("Sri. Anil", "9447000002"))
		make_pack(self.installation, "KSEB Form 3", ae_name="Someone Else", ae_phone="9000000000")
		self.assertEqual(frappe.db.get_value("DISCOM Section", self.section, "assistant_engineer_name"), "Sri. Anil")

	def test_the_portal_form_has_the_dates_above_remarks_and_no_cost(self):
		frappe.db.set_value("DISCOM Section", self.section,
			{"assistant_engineer_name": "Smt. Latha K.", "assistant_engineer_phone": "9447000001"})
		values = collections.task_source("document-packs", self.installation.name, "FRM2")
		doc, groups = collections.task_form_groups("document-packs", values, "Form 2 Submission")
		collections.apply_prefill(doc, groups)
		fields = [f for g in groups for s in g["sections"] for f in s["fields"]]
		names = [f["fieldname"] for f in fields]
		self.assertNotIn("task_cost", names)
		self.assertEqual(names[-4:], ["due_date", "started_on", "completed_on", "remarks"])
		spec = {f["fieldname"]: f for f in fields}
		self.assertEqual(spec["solar_agreement"]["show_when"], "pack_type=KSEB Form 3")
		self.assertEqual((spec["ae_name"].get("prefill"), spec["ae_phone"].get("prefill")), ("Smt. Latha K.", "9447000001"))

	def test_the_patch_adds_form2_to_a_running_job(self):
		inst = frappe.get_doc("Solar Installation", self.installation.name)
		inst.stages = [r for r in inst.stages if r.stage_code != "FRM2"]
		for row in inst.documents:
			if row.stage_code == "FRM2":
				row.stage_code = "KFORMS"
		next(r for r in inst.stages if r.stage_code == "KFORMS").status = "Completed"
		template = frappe.get_doc("Installation Stage Template", inst.stage_template)
		source = next(r for r in template.stages if r.stage_code == "FRM2")
		order = {r.stage_code: r.display_order or r.idx for r in template.stages}
		split_form2_form3.split(inst, source, order)
		codes = [r.stage_code for r in inst.stages]
		self.assertLess(codes.index("FRM2"), codes.index("F2PAY"))
		self.assertLess(codes.index("F2PAY"), codes.index("KFORMS"))
		form2 = next(r for r in inst.stages if r.stage_code == "FRM2")
		self.assertEqual(form2.status, "Skipped")
		self.assertEqual({r.document_name for r in inst.documents if r.stage_code == "FRM2"},
			set(split_form2_form3.FORM2_DOCUMENTS))
