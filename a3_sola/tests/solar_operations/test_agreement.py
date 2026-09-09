# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The stamp paper, and the agreement generated onto it.

Two things are being protected here. The stamp paper stage is status-only, so nothing may
gate it - the moment somebody adds a checklist to STMP the errand stops being an errand.
And the agreement body is generated, never typed, so generation must be idempotent, must
draw every particular from upstream, and must refuse to silently discard a hand edit.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from a3_sola.api import agreement as builder
from a3_sola.setup import seed_stages
from a3_sola.solar_operations.doctype.solar_agreement import solar_agreement as ctl
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_tasks import as_user


def make_agreement(installation, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Solar Agreement",
			"solar_installation": installation.name,
			"agreement_date": today(),
		}
	)
	doc.update(kwargs)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc


def buy_paper(doc, **kwargs):
	ctl.record_stamp_paper(
		doc.name,
		purchased_on=kwargs.get("purchased_on", today()),
		serial_no=kwargs.get("serial_no", "KL/2026/AB 000001"),
		value=kwargs.get("value", 200),
		vendor=kwargs.get("vendor", "Sub Treasury"),
	)
	doc.reload()
	return doc


class TestStampPaperStage(FrappeTestCase):
	def test_the_stamp_paper_is_a_task_executed_in_the_agreement(self):
		"""The errand lives on the agreement: buying the paper is recorded there, nowhere else."""
		task = seed_stages.by_code("STMP")
		self.assertIsNotNone(task)
		self.assertEqual(task["task_doctype"], "Solar Agreement")
		self.assertEqual(task["applicability"], "Always")

	def test_the_task_expects_no_mandatory_document(self):
		"""Status only. Its data sheet and scan are optional evidence, not gates."""
		task = seed_stages.by_code("STMP")
		self.assertFalse([d for d in task["documents"] if d[1]])

	def test_installation_chain_includes_the_stage(self):
		installation = make_installation()
		self.assertIn("STMP", [row.stage_code for row in installation.stages])

	def test_recording_the_paper_completes_the_stage(self):
		installation = make_installation()
		doc = buy_paper(make_agreement(installation))
		self.assertEqual(doc.stamp_paper_status, "Purchased")
		installation.reload()
		row = next(r for r in installation.stages if r.stage_code == "STMP")
		self.assertEqual(row.status, "Completed")
		self.assertEqual(row.external_reference, "KL/2026/AB 000001")

	def test_the_paper_cannot_be_bought_twice(self):
		doc = buy_paper(make_agreement(make_installation()))
		with self.assertRaises(frappe.ValidationError):
			ctl.record_stamp_paper(doc.name)

	def test_the_paper_cannot_postdate_the_agreement(self):
		installation = make_installation()
		doc = make_agreement(installation, agreement_date=today())
		doc.stamp_paper_status = "Purchased"
		doc.stamp_paper_purchased_on = add_days(today(), 1)
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestGeneration(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		self.doc = make_agreement(self.installation)

	def test_nothing_generates_before_the_paper_is_bought(self):
		with self.assertRaises(frappe.ValidationError):
			builder.generate(self.doc.name)

	def test_the_body_carries_the_particulars_from_upstream(self):
		buy_paper(self.doc)
		text = builder.generate(self.doc.name)
		self.doc.reload()
		self.assertIn(self.doc.consumer_name, text)
		self.assertIn(f"{self.doc.plant_capacity_kwp:g}kWp", text)
		self.assertIn(builder.TITLE, text)
		self.assertIn("25 years", text)

	def test_generation_is_idempotent(self):
		"""`is_edited` only means something if unchanged sources produce unchanged text."""
		buy_paper(self.doc)
		builder.generate(self.doc.name)
		self.doc.reload()
		self.assertFalse(self.doc.is_edited)
		self.assertEqual(
			builder._normalise(self.doc.agreement_text),
			builder._normalise(builder.render(self.doc)),
		)
		self.doc.save(ignore_permissions=True)
		self.doc.reload()
		self.assertFalse(self.doc.is_edited)

	def test_every_clause_is_rendered(self):
		buy_paper(self.doc)
		text = builder.generate(self.doc.name)
		self.assertEqual(text.count("<li>"), len(builder.CLAUSES))

	def test_a_hand_edit_is_not_discarded_silently(self):
		buy_paper(self.doc)
		builder.generate(self.doc.name)
		self.doc.reload()
		self.doc.agreement_text += "<p>Negotiated rider.</p>"
		self.doc.save(ignore_permissions=True)
		self.doc.reload()
		self.assertTrue(self.doc.is_edited)
		with self.assertRaises(frappe.ValidationError):
			builder.generate(self.doc.name)
		builder.generate(self.doc.name, force=1)
		self.doc.reload()
		self.assertFalse(self.doc.is_edited)
		self.assertNotIn("Negotiated rider", self.doc.agreement_text)

	def test_the_licensee_is_named_not_referenced(self):
		"""The second party signs under a legal name; a record id is not a party."""
		buy_paper(self.doc)
		text = builder.generate(self.doc.name)
		self.doc.reload()
		self.assertTrue(self.doc.discom)
		self.assertNotIn(self.doc.discom, text)
		self.assertIn(self.doc.second_party_legal_name, text)

	def test_a_licensee_with_no_legal_name_prints_a_blank_not_a_record_id(self):
		buy_paper(self.doc)
		self.doc.second_party_legal_name = None
		text = builder.render(self.doc)
		self.assertNotIn(self.doc.discom, text)
		self.assertIn(builder.BLANK, text)

	def test_the_company_follows_the_installation_not_the_session(self):
		self.assertEqual(self.doc.company, self.installation.company)


class TestExecution(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		self.doc = buy_paper(make_agreement(self.installation))
		builder.generate(self.doc.name)
		self.doc.reload()

	def test_submitting_needs_a_spin(self):
		self.doc.spin = None
		self.doc.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			self.doc.submit()

	def test_submitting_stamps_the_spin_onto_the_chain(self):
		self.doc.spin = "SPINTEST00001"
		self.doc.save(ignore_permissions=True)
		self.doc.submit()
		self.assertEqual(
			frappe.db.get_value("Solar Installation", self.installation.name, "spin"),
			"SPINTEST00001",
		)

	def test_only_one_agreement_may_be_executed(self):
		self.doc.spin = "SPINTEST00002"
		self.doc.save(ignore_permissions=True)
		self.doc.submit()
		# The refusal lands on insert, before a second draft can exist to be corrected.
		with self.assertRaises(frappe.ValidationError):
			make_agreement(self.installation)

	def test_wheeling_may_not_point_at_the_consumers_own_supply(self):
		own = frappe.db.get_value("Solar Consumer", self.doc.solar_consumer, "consumer_number")
		self.doc.append(
			"wheeling_preferences",
			{"preference_order": 1, "consumer_number": own, "tariff": "LT-1A"},
		)
		with self.assertRaises(frappe.ValidationError):
			self.doc.save(ignore_permissions=True)


class TestPrintFormat(FrappeTestCase):
	def test_the_three_schedules_are_printed(self):
		installation = make_installation()
		doc = buy_paper(make_agreement(installation))
		builder.generate(doc.name)
		html = frappe.get_print("Solar Agreement", doc.name, print_format="Solar Agreement")
		for probe in (
			"Schedule to Solar Net Metering Agreement",
			"Permanent address of the consumer",
			"Address of the premises where the solar energy system is installed",
			"Solar Plant Identification Number (SPIN)",
			"Order of preferred premises",
			"Preference 3",
			"1st Party",
		):
			self.assertIn(probe, html, f"the print format lost: {probe}")


def execute(installation, spin="SPINTEST00009"):
	"""An executed agreement: paper bought, text generated, SPIN recorded, submitted."""
	doc = buy_paper(make_agreement(installation))
	builder.generate(doc.name)
	doc.reload()
	doc.spin = spin
	doc.save(ignore_permissions=True)
	doc.submit()
	return doc


class TestTermination(FrappeTestCase):
	"""Termination is the one thing that happens to an executed agreement, so it is
	recorded on it - never by deleting it - and only a manager may do it."""

	def setUp(self):
		self.installation = make_installation()
		self.doc = execute(self.installation)
		self.addCleanup(frappe.set_user, "Administrator")

	def test_termination_needs_a_party_and_a_reason(self):
		with self.assertRaises(frappe.ValidationError):
			ctl.terminate(self.doc.name, "Consumer", "  ")
		with self.assertRaises(frappe.ValidationError):
			ctl.terminate(self.doc.name, None, "Premises sold")

	def test_only_a_manager_may_terminate(self):
		as_user("agreement.exec@example.com", ["Solar Operations Executive"])
		with self.assertRaises(frappe.PermissionError):
			ctl.terminate(self.doc.name, "Consumer", "Premises sold")

	def test_a_draft_cannot_be_terminated(self):
		other = make_agreement(make_installation())
		with self.assertRaises(frappe.ValidationError):
			ctl.terminate(other.name, "Consumer", "Changed their mind")

	def test_a_terminated_agreement_is_recorded_and_makes_room_for_another(self):
		ctl.terminate(self.doc.name, "Consumer", "Premises sold")
		self.doc.reload()
		self.assertEqual(
			(self.doc.is_terminated, self.doc.terminated_by, self.doc.terminated_on, self.doc.termination_reason),
			(1, "Consumer", getdate(today()), "Premises sold"),
		)
		with self.assertRaises(frappe.ValidationError):
			ctl.terminate(self.doc.name, "DISCOM", "Again")
		# The refusal used to land on the second draft's insert; a terminated one no longer competes.
		again = make_agreement(self.installation)
		self.assertTrue(again.name)


class TestStampPaperDataSheet(FrappeTestCase):
	def test_the_sheet_is_made_before_the_paper_is_bought_and_registered_under_the_task(self):
		installation = make_installation()
		doc = make_agreement(installation)
		result = ctl.generate_stamp_paper_data(doc.name)
		doc.reload()
		self.assertEqual(doc.stamp_paper_data_sheet, result["file_url"])
		job = frappe.get_doc("Solar Installation", installation.name)
		row = next(r for r in job.documents if r.attachment == result["file_url"])
		self.assertEqual(
			(row.stage_code, row.source_doctype, row.source_document), ("STMP", "Solar Agreement", doc.name)
		)


class TestMigrationFromNetMetering(FrappeTestCase):
	"""The retired doctype's records become Solar Agreements, executed when they pass the
	same gates a hand-made one must."""

	def make_retired(self, installation, **kwargs):
		values = {
			"doctype": "Net Metering Agreement",
			"company": installation.company,
			"solar_installation": installation.name,
			"agreement_date": today(),
			"place_of_execution": "Ernakulam",
			"witness_1_name": "K. Rajan",
			"spin": "SPINMIG000001",
			"stamp_paper_serial": "KL/2026/XY 000009",
			"ht_feeder_details": "11 kV Athani feeder",
			"wheeling_preferences": [{"preference_order": 1, "consumer_number": "1155000099999", "tariff": "LT-1A"}],
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.allow_retired = True
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def test_the_retired_doctype_refuses_new_records(self):
		installation = make_installation()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Net Metering Agreement",
					"company": installation.company,
					"solar_installation": installation.name,
					"agreement_date": today(),
				}
			).insert(ignore_permissions=True)

	def test_an_executed_record_becomes_an_executed_solar_agreement_once(self):
		from a3_sola.patches.v1_2 import migrate_net_metering_agreement_into_solar_agreement as patch

		installation = make_installation()
		nma = self.make_retired(installation)
		nma.submit()
		self.assertEqual(patch.run()["migrated"], 1)
		name = frappe.db.get_value("Solar Agreement", {"migrated_from": nma.name}, "name")
		doc = frappe.get_doc("Solar Agreement", name)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(
			(doc.spin, doc.first_party_witness_1, doc.ht_feeder_details, doc.stamp_paper_status, doc.stamp_paper_serial),
			("SPINMIG000001", "K. Rajan", "11 kV Athani feeder", "Purchased", "KL/2026/XY 000009"),
		)
		self.assertEqual([r.consumer_number for r in doc.wheeling_preferences], ["1155000099999"])
		self.assertTrue(doc.agreement_text)
		self.assertEqual(patch.run()["migrated"], 0)

	def test_a_record_that_cannot_execute_is_kept_as_a_draft_with_the_reason(self):
		from a3_sola.patches.v1_2 import migrate_net_metering_agreement_into_solar_agreement as patch

		patch.run()  # whatever the site already holds is settled before this test's record
		installation = make_installation()
		nma = self.make_retired(installation)
		nma.submit()
		# An executed agreement already on the job: the copy must not become a second one.
		frappe.db.set_value("Net Metering Agreement", nma.name, "spin", "", update_modified=False)
		execute(installation, spin="SPINMIG000002")
		result = patch.run()
		self.assertEqual((result["migrated"], result["skipped"]), (0, 1))
		self.assertFalse(frappe.db.exists("Solar Agreement", {"migrated_from": nma.name}))
		self.assertEqual(patch.run()["skipped"], 0)  # noted once, not on every run
