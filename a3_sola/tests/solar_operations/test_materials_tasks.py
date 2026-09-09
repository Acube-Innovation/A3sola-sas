# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Procurement and dispatch are ERPNext documents wearing a task."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import materials
from a3_sola.tests.solar_operations.fixtures import make_installation
from a3_sola.tests.solar_operations.test_tasks import task_row
from a3_sola.tests.test_quotation import ensure_item


def give_the_package_items(installation):
	"""The shared test package has makes, not items; procurement needs items to order."""
	package = frappe.get_doc("Solar Package", installation.solar_package)
	if any(row.item for row in package.components):
		return package
	# Structure and cable, not modules: a module item on a DCR package must itself be flagged
	# DCR on the Item master, and that guard is not what this test is about.
	package.append("components", {"component_type": "Mounting Structure", "item": ensure_item("Solar Test Structure 3kW"), "qty": 1})
	package.append("components", {"component_type": "DC Cable", "item": ensure_item("Solar Test DC Cable 4sqmm"), "qty": 60})
	package.flags.ignore_permissions = True
	package.save(ignore_permissions=True)
	frappe.clear_document_cache("Solar Package", package.name)
	return package


def ensure_supplier(company):
	name = "Test Solar Supplier"
	if not frappe.db.exists("Supplier", name):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": "All Supplier Groups"}).insert(ignore_permissions=True)
	return name


class TestProcurement(FrappeTestCase):
	def setUp(self):
		self.installation = make_installation()
		give_the_package_items(self.installation)

	def test_a_purchase_order_is_raised_from_the_bill_of_materials_and_starts_the_task(self):
		consumer = frappe.get_doc("Solar Consumer", self.installation.solar_consumer)
		consumer.google_location_url = "https://maps.app.goo.gl/site"
		consumer.landmark = "Behind the school"
		consumer.save(ignore_permissions=True)
		name = materials.create_purchase_order(self.installation.name, ensure_supplier(self.installation.company))
		order = frappe.get_doc("Purchase Order", name)
		self.assertTrue(order.items)
		self.assertEqual(order.solar_installation, self.installation.name)
		self.assertEqual(order.site_google_location, "https://maps.app.goo.gl/site")
		self.assertEqual(order.site_landmark, "Behind the school")
		row, _doc = task_row(self.installation, "PROC")
		self.assertEqual((row.status, row.task_document), ("In Progress", name))

	def test_bom_lines_are_printable(self):
		lines = materials.bom_lines(self.installation)
		self.assertTrue(lines)
		self.assertTrue(all(l["qty"] > 0 for l in lines))


class TestDispatch(FrappeTestCase):
	def test_a_job_without_an_order_cannot_be_delivered(self):
		installation = make_installation()
		with self.assertRaises(frappe.ValidationError):
			materials.create_delivery_note(installation.name)
