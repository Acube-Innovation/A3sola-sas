# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Inverter Topology is each inverter option's own - the first thing its row asks - and the
package's is its default option's: one package quotes a string inverter and a micro inverter
side by side."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.tests.fixtures import make_consumer, make_estimate, package


class TestInverterTopology(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.consumer = make_consumer()
		self.pkg = frappe.get_doc("Solar Package", package("3Kw 1PH", self.consumer.company))
		self.assertTrue(self.pkg.inverters, "the test package needs an inverter option")

	def two_options(self):
		"""The package with a second inverter option, a micro inverter, beside its default."""
		first = self.pkg.inverters[0]
		for row in self.pkg.inverters:
			row.is_default = 1 if row is first else 0
		first.inverter_topology = "String"
		self.pkg.append("inverters", {"inverter_topology": "Microinverter", "inverter_specification": "Micro inverter x 6",
			"inverter_make": first.inverter_make, "inverter_count": 6, "cost": first.cost})
		self.pkg.save()
		return self.pkg

	def test_a_blank_row_takes_the_packages_and_the_package_follows_its_default(self):
		self.pkg.inverter_topology = "String with Optimiser"
		for row in self.pkg.inverters:
			row.inverter_topology = None
		self.pkg.save()
		self.assertEqual({r.inverter_topology for r in self.pkg.inverters}, {"String with Optimiser"})
		default = next(r for r in self.pkg.inverters if r.is_default)
		default.inverter_topology = "Microinverter"
		self.pkg.save()
		self.assertEqual(self.pkg.inverter_topology, "Microinverter")
		# A micro-inverter default still drops the DCDB.
		self.assertFalse([r for r in self.pkg.system_items if r.system_type == "DCDB" and r.qty])

	def test_an_option_from_the_second_inverter_is_built_its_way(self):
		from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import add_option_from_package

		pkg = self.two_options()
		self.assertEqual(pkg.inverter_topology, "String")
		est = make_estimate(self.consumer, with_default_options=False, options=[])
		add_option_from_package(est.name, pkg.name, inverter_option=str(len(pkg.inverters)))
		option = frappe.get_doc("Solar Design Estimate", est.name).options[-1]
		self.assertEqual(option.inverter_topology, "Microinverter")
		self.assertIn("Microinverter", option.option_name)

	def test_the_portal_asks_it_first_on_the_inverter_row_not_on_the_package(self):
		from a3_sola.api import portal_packages

		self.assertEqual(portal_packages._table("inverters")["columns"][0]["fieldname"], "inverter_topology")
		self.assertTrue(portal_packages._table("inverters")["columns"][0]["reqd"])
		fields = [f for tab in portal_packages._layout() for f in tab["fields"]]
		self.assertNotIn("inverter_topology", fields)
