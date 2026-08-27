# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Preventive visits, warranty claims and the O&M provision."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_years, flt, getdate, today

from a3_sola.api import om
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_projects.fixtures import (
	commissioned_project,
	make_visit,
	om_contract,
)

PASSING_CHECKLIST = [(item, category, "OK") for item, category in om.VISIT_CHECKLIST]


class TestPreventiveVisits(FrappeTestCase):
	def setUp(self):
		project, self.installation, _ = commissioned_project()
		self.project = project
		self.contract = om_contract(project)

	def test_the_visit_plan_avoids_the_monsoon(self):
		"""June to September in Kerala. A cleaning visit then is wasted."""
		monsoon = {6, 7, 8, 9}
		months = {getdate(row.scheduled_date).month for row in self.contract.visit_plan}
		self.assertFalse(
			months & monsoon, f"visits scheduled in the monsoon: {sorted(months & monsoon)}"
		)

	def test_the_plan_spans_the_whole_obligation(self):
		dates = [getdate(row.scheduled_date) for row in self.contract.visit_plan]
		self.assertGreaterEqual(min(dates), getdate(self.contract.start_date))
		self.assertLessEqual(max(dates), getdate(self.contract.end_date))

	def test_a_visit_records_its_checklist_outcome(self):
		visit = make_visit(self.contract, checklist=PASSING_CHECKLIST)
		visit.submit()
		visit.reload()
		self.assertEqual(visit.items_ok, len(PASSING_CHECKLIST))
		self.assertEqual(visit.items_defect, 0)

	def test_a_defect_on_a_visit_is_counted(self):
		checklist = list(PASSING_CHECKLIST)
		checklist[0] = (checklist[0][0], checklist[0][1], "Defect")
		visit = make_visit(self.contract, checklist=checklist)
		visit.submit()
		visit.reload()
		self.assertEqual(visit.items_defect, 1)
		self.assertEqual(visit.items_ok, len(checklist) - 1)

	def test_visit_cost_rolls_into_the_project(self):
		from a3_sola.api import costing

		visit = make_visit(self.contract, checklist=PASSING_CHECKLIST, travel_km=40)
		visit.labour_cost = 800
		visit.material_cost = 200
		visit.submit()
		costing.recalculate_project_costs(self.project.name)
		self.project.reload()
		self.assertGreater(self.project.om_cost_to_date, 0)
		self.assertIn("O&M", {row.cost_category for row in self.project.cost_entries})

	def test_module_washing_is_chargeable_and_water_is_the_customers(self):
		"""Straight from the client's scope of work."""
		coverage = {row.coverage_item: row for row in self.contract.coverage}
		washing = coverage["Module washing"]
		self.assertEqual(washing.coverage_type, "Chargeable")
		self.assertIn("water", (washing.description or "").lower())

	def test_a_missed_visit_is_marked_not_forgotten(self):
		row = self.contract.visit_plan[0]
		frappe.db.set_value(
			"Solar OM Visit Plan", row.name, "scheduled_date", add_days(today(), -60),
			update_modified=False,
		)
		om.mark_due_and_missed_visits()
		self.contract.reload()
		self.assertEqual(self.contract.visit_plan[0].status, "Missed")


class TestOMProvision(FrappeTestCase):
	def setUp(self):
		project, self.installation, _ = commissioned_project()
		self.project = project
		self.contract = om_contract(project)

	def test_provision_is_a_percentage_of_contract_value(self):
		percent = flt(frappe.db.get_single_value("A3 Sola Settings", "om_provision_percent"))
		expected = flt(flt(self.installation.gross_contract_value) * percent / 100.0, 2)
		self.assertEqual(flt(self.contract.om_provision_allocated, 2), expected)

	def test_a_visit_releases_against_the_provision(self):
		visit = make_visit(self.contract, checklist=PASSING_CHECKLIST)
		visit.labour_cost = 500
		visit.submit()
		self.contract.reload()
		self.assertLess(
			flt(self.contract.om_provision_balance, 2),
			flt(self.contract.om_provision_allocated, 2),
			"the visit cost did not draw down the provision",
		)


class TestWarrantyClaims(FrappeTestCase):
	def setUp(self):
		project, self.installation, _ = commissioned_project()
		self.project = project
		self.contract = om_contract(project)
		self.installation.reload()
		self.serial = next(
			row.serial_no for row in self.installation.serials if row.component_type == "Module"
		)

	def _claim(self, **kwargs):
		values = {
			"doctype": "Solar Warranty Claim",
			"company": self.contract.company,
			"om_contract": self.contract.name,
			"component_type": "Module",
			"serial_no": self.serial,
			"failure_date": today(),
			"failure_description": "Cell cracking visible under EL, output down 40%.",
			"claim_status": "Draft",
			"claim_basis": "Product",
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc

	def test_expiry_uses_this_makes_term_not_a_constant(self):
		"""Rayzon modules are 15-year product, so a claim today is comfortably inside."""
		claim = self._claim()
		self.assertEqual(claim.warranty_years_applicable, 15)
		self.assertEqual(
			getdate(claim.warranty_expiry_date),
			add_years(getdate(self.contract.start_date), 15),
		)
		self.assertTrue(claim.is_within_warranty)

	def test_performance_basis_uses_the_longer_term(self):
		claim = self._claim(claim_basis="Performance")
		self.assertEqual(claim.warranty_years_applicable, 30)

	def test_a_failure_after_expiry_is_flagged(self):
		claim = self._claim(failure_date=add_years(getdate(self.contract.start_date), 16))
		self.assertFalse(claim.is_within_warranty)

	def test_a_serial_from_another_installation_is_refused(self):
		other = make_installation()
		from a3_sola.tests.solar_operations.fixtures import capture_serials

		capture_serials(other, modules=2, inverters=1)
		other.reload()
		foreign = next(row.serial_no for row in other.serials if row.component_type == "Module")
		with self.assertRaises(frappe.ValidationError):
			self._claim(serial_no=foreign)

	def test_an_unregistered_serial_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._claim(serial_no="NOT-A-REAL-SERIAL")

	def test_cost_borne_is_the_unrecovered_balance(self):
		claim = self._claim()
		claim.claim_value = 12000
		claim.save(ignore_permissions=True)
		claim.submit()
		claim.reload()
		claim.amount_recovered = 9000
		claim.flags.ignore_validate_update_after_submit = True
		claim.save(ignore_permissions=True)
		claim.reload()
		self.assertEqual(flt(claim.cost_borne_by_company, 2), 3000.00)

	def test_a_replacement_updates_the_serial_register(self):
		"""Traceability has to survive the swap or the DCR manifest goes stale."""
		claim = self._claim()
		claim.submit()
		claim.reload()
		claim.claim_status = "Replaced"
		claim.replacement_serial_no = "RPL-0001"
		claim.replacement_installed_on = today()
		claim.flags.ignore_validate_update_after_submit = True
		claim.save(ignore_permissions=True)

		self.installation.reload()
		old = next(r for r in self.installation.serials if r.serial_no == self.serial)
		self.assertTrue(old.is_replaced)
		self.assertEqual(old.replaced_by_serial, "RPL-0001")
		new = next(r for r in self.installation.serials if r.serial_no == "RPL-0001")
		self.assertEqual(new.component_type, old.component_type)
		self.assertEqual(new.dcr_certificate_no, old.dcr_certificate_no)


class TestRenewals(FrappeTestCase):
	def test_an_expiring_contract_becomes_an_opportunity(self):
		project, installation, _ = commissioned_project()
		contract = om_contract(project)
		window = frappe.db.get_single_value("A3 Sola Settings", "contract_expiry_window_days") or 90
		frappe.db.set_value(
			"Solar OM Contract", contract.name, "end_date", add_days(today(), int(window) - 1),
			update_modified=False,
		)
		om.detect_renewals()
		self.assertTrue(
			frappe.db.exists("Opportunity", {"om_contract": contract.name}),
			"no renewal opportunity raised",
		)

	def test_renewals_are_not_raised_twice(self):
		project, installation, _ = commissioned_project()
		contract = om_contract(project)
		window = frappe.db.get_single_value("A3 Sola Settings", "contract_expiry_window_days") or 90
		frappe.db.set_value(
			"Solar OM Contract", contract.name, "end_date", add_days(today(), int(window) - 1),
			update_modified=False,
		)
		om.detect_renewals()
		om.detect_renewals()
		self.assertEqual(frappe.db.count("Opportunity", {"om_contract": contract.name}), 1)


class TestContractRenewal(FrappeTestCase):
	def setUp(self):
		project, self.installation, _ = commissioned_project()
		self.project = project
		self.contract = om_contract(project)

	def test_renewal_creates_a_paid_successor(self):
		successor = frappe.get_doc("Solar OM Contract", om.renew_contract(self.contract.name, years=2))
		self.assertEqual(successor.contract_type, "AMC (Paid Renewal)")
		self.assertEqual(successor.duration_years, 2)
		self.assertEqual(successor.renewed_from, self.contract.name)

	def test_the_successor_starts_the_day_after_the_predecessor_ends(self):
		successor = frappe.get_doc("Solar OM Contract", om.renew_contract(self.contract.name))
		self.assertEqual(
			getdate(successor.start_date), add_days(getdate(self.contract.end_date), 1)
		)

	def test_coverage_and_service_levels_carry_across(self):
		"""The customer keeps what they are used to; nobody retypes twelve rows."""
		successor = frappe.get_doc("Solar OM Contract", om.renew_contract(self.contract.name))
		before = {(r.coverage_item, r.coverage_type) for r in self.contract.coverage}
		after = {(r.coverage_item, r.coverage_type) for r in successor.coverage}
		self.assertEqual(before, after)
		self.assertEqual(
			successor.critical_response_hours, self.contract.critical_response_hours
		)
		self.assertEqual(
			successor.preventive_visits_per_year, self.contract.preventive_visits_per_year
		)

	def test_the_predecessor_is_marked_renewed_and_linked(self):
		successor = om.renew_contract(self.contract.name)
		self.contract.reload()
		self.assertEqual(self.contract.status, "Renewed")
		self.assertEqual(self.contract.renewed_to, successor)

	def test_renewing_twice_returns_the_same_successor(self):
		first = om.renew_contract(self.contract.name)
		second = om.renew_contract(self.contract.name)
		self.assertEqual(first, second)
		self.assertEqual(
			frappe.db.count("Solar OM Contract", {"project": self.project.name, "docstatus": 1}), 2
		)

	def test_the_successor_has_its_own_visit_plan(self):
		successor = frappe.get_doc("Solar OM Contract", om.renew_contract(self.contract.name, years=1))
		self.assertTrue(successor.visit_plan)
		self.assertEqual(len(successor.visit_plan), successor.preventive_visits_per_year)

	def test_a_draft_contract_cannot_be_renewed(self):
		draft = frappe.copy_doc(self.contract)
		draft.project = None
		draft.flags.ignore_permissions = True
		draft.flags.ignore_mandatory = True
		draft.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			om.renew_contract(draft.name)
