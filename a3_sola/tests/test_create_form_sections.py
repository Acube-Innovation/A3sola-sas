# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A create form asked to be in columns (the customer's) shows its fields under the headings the
ERPNext form gives them, in the form's order; the others stay one plain grid."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.www.a3solaportal.collections import form_extra, form_fields, form_sections, get_collection


class TestCreateFormSections(FrappeTestCase):
	def test_the_customer_form_follows_the_desk_sections(self):
		cfg = get_collection("consumers")
		self.assertEqual(cfg.get("form_columns"), 4)
		meta = frappe.get_meta(cfg["doctype"])
		fields, _ = form_fields(meta, {}, form_extra(cfg, meta))
		sections = form_sections(meta, fields)
		where = {f["fieldname"]: s["label"] for s in sections for f in s["fields"]}
		self.assertEqual(where["consumer_name"], meta.get_field("sb_1").label)
		self.assertEqual(where["site_city"], meta.get_field("sb_address").label)
		# The address asked for when it is not the site's sits under Permanent Address, whose
		# second Section Break has no heading of its own.
		self.assertEqual(where["permanent_city"], where["permanent_address_same"])
		self.assertEqual(where["consumer_number"], meta.get_field("sb_3").label)
		# Every field is placed once, none lost.
		self.assertEqual(sorted(where), sorted(f["fieldname"] for f in fields))
		labels = [s["label"] for s in sections]
		self.assertEqual(len(labels), len(set(labels)))

	def test_a_form_without_columns_is_not_sectioned(self):
		self.assertFalse(get_collection("site-surveys").get("form_columns"))
