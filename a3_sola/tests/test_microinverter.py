# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A micro-inverter system has no DCDB, and the proposal lists every option's inverter.

The proposal offers a job several ways - a string inverter, optimisers, micro inverters - and
3.2 lists each option's inverter, the micro one starred. Where the inverter is a micro
inverter the DCDB is 0: on the design, the package, the papers and the procurement list."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import microinverter, print_cover, purchase_list
from a3_sola.tests.fixtures import make_consumer, make_estimate, package


def technology(name):
	return frappe.db.get_value("Component Technology", {"technology_name": name})


class TestMicroinverter(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.micro = technology(microinverter.MICROINVERTER)
		if not self.micro:
			self.skipTest("no Microinverter technology on this site")

	def test_the_dcdb_is_named_as_the_bom_names_it(self):
		self.assertTrue(microinverter.is_dcdb("DCDB"))
		self.assertTrue(microinverter.is_dcdb("1/1 DCDB Strider Mersen SPD"))
		self.assertFalse(microinverter.is_dcdb("ACDB"))
		self.assertFalse(microinverter.is_dcdb(None))

	def test_only_the_priced_inverter_counts(self):
		doc = frappe._dict(inverters=[frappe._dict(inverter_type=self.micro, is_option=1)])
		self.assertFalse(microinverter.uses_microinverter(doc))
		doc.inverters[0].is_option = 0
		self.assertTrue(microinverter.uses_microinverter(doc))

	def test_a_micro_design_has_no_dcdb_and_a_switch_refills_it(self):
		doc = frappe.get_doc({"doctype": "Solar Design Estimate",
			"inverters": [{"inverter_type": self.micro, "is_option": 0}],
			"bos_items": [{"item": "DCDB", "numbers": 1}, {"item": "ACDB", "numbers": 1}]})
		doc.no_dcdb_for_microinverter()
		self.assertEqual([r.numbers for r in doc.bos_items], [0, 1])
		self.assertEqual(doc.micro_basis(), "|micro")
		doc.inverters[0].inverter_type = technology("String On-Grid")
		self.assertEqual(doc.micro_basis(), "")

	def test_a_micro_package_has_no_dcdb(self):
		doc = frappe.get_doc({"doctype": "Solar Package", "inverter_topology": microinverter.MICROINVERTER,
			"system_items": [{"system_type": "DCDB", "qty": 1}, {"system_type": "ACDB", "qty": 1}]})
		doc.no_dcdb_for_microinverter()
		self.assertEqual([r.qty for r in doc.system_items], [0, 1])

	def options(self, count):
		consumer = make_consumer()
		estimates = [make_estimate(consumer, solar_package=package("3Kw 1PH", consumer.company)) for _ in range(count)]
		if not all(any(not r.is_option for r in e.inverters) for e in estimates):
			self.skipTest("the package fills no inverter on this site")
		return consumer, estimates

	def make_micro(self, estimate):
		row = next(r for r in estimate.inverters if not r.is_option)
		frappe.db.set_value("Design Estimate Inverter", row.name, "inverter_type", self.micro)

	def proposal(self, consumer, estimates):
		return frappe._dict(company=consumer.company, solar_design_estimate=estimates[0].name,
			design_estimates=[frappe._dict(solar_design_estimate=e.name) for e in estimates])

	def test_the_proposal_lists_each_options_inverter_the_micro_one_starred(self):
		consumer, estimates = self.options(2)
		self.make_micro(estimates[1])
		out = print_cover.print_components(self.proposal(consumer, estimates))
		inverters = [r for r in out["rows"] if r["item"] == "Solar PV Inverter"]
		self.assertEqual(len(inverters), 2)
		self.assertTrue(inverters[0]["spec"].startswith("Option 1: "))
		self.assertFalse(inverters[0]["spec"].endswith("*"))
		self.assertTrue(inverters[1]["spec"].startswith("Option 2: ") and inverters[1]["spec"].endswith(" *"))
		# One item: the first row's Sl. No. and description span the options' rows.
		self.assertEqual((inverters[0].get("span"), inverters[1].get("spanned")), (2, True))
		self.assertEqual(next(r["nos"] for r in out["rows"] if r["item"] == "DCDB"), "1 (0*)")
		self.assertEqual(out["notes"], [microinverter.NOTE])

	def test_a_micro_quotation_has_no_dcdb(self):
		consumer, estimates = self.options(1)
		self.make_micro(estimates[0])
		out = print_cover.print_components(self.proposal(consumer, estimates))
		inverter = next(r for r in out["rows"] if r["item"] == "Solar PV Inverter")
		self.assertFalse(inverter["spec"].startswith("Option"))
		self.assertTrue(inverter["spec"].endswith(" *"))
		self.assertEqual(next(r["nos"] for r in out["rows"] if r["item"] == "DCDB"), "0*")

	def test_a_string_proposal_prints_as_before(self):
		consumer, estimates = self.options(1)
		out = print_cover.print_components(self.proposal(consumer, estimates))
		self.assertEqual(out["notes"], [])
		self.assertNotIn("*", next(r["nos"] for r in out["rows"] if r["item"] == "DCDB"))

	def test_the_purchase_list_buys_no_dcdb_for_a_micro_job(self):
		task = frappe._dict(task_code="PROC", solar_installation="JOB", remarks="", material_bom="B", materials=[
			frappe._dict(material="1/1 DCDB Strider Mersen SPD", uom="Nos", qty=0),
			frappe._dict(material="Panel 550Wp", uom="Nos", qty=6)])
		with patch.object(microinverter, "uses_microinverter", return_value=True):
			out = purchase_list.lines(task)
		self.assertEqual([r["material"] for r in out["rows"]], ["1/1 DCDB Strider Mersen SPD *", "Panel 550Wp"])
		self.assertEqual(out["remarks"], [microinverter.NOTE])
		with patch.object(microinverter, "uses_microinverter", return_value=False):
			self.assertEqual(purchase_list.lines(task)["remarks"], [])
