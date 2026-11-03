# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sharing a task's document: a link that opens that one document of that one task, until it
expires, and nothing else (api/task_share)."""

from urllib.parse import parse_qs, urlsplit

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import task_share
from a3_sola.tests.solar_operations.fixtures import make_installation


class TestTaskShare(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.installation = make_installation()
		self.urls = sorted(task_share._urls(self.installation, "FRM1"))
		if not self.urls:
			self.skipTest("Form 1 lists no document to share on this site.")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def args(self, url):
		q = parse_qs(urlsplit(task_share.share_link(self.installation.name, "FRM1", url)["link"]).query)
		return {k: v[0] for k, v in q.items()}

	def test_only_the_tasks_own_documents_are_shared(self):
		with self.assertRaises(frappe.PermissionError):
			task_share.share_link(self.installation.name, "FRM1", "/private/files/someone-else.pdf")

	def test_the_link_opens_its_document_and_no_other(self):
		a = self.args(self.urls[0])
		self.assertEqual(a["u"], self.urls[0])
		frappe.set_user("Guest")
		task_share.shared_document(**a)
		self.assertTrue(frappe.local.response.filecontent)
		self.assertEqual(frappe.session.user, "Guest")
		for tampered in ({**a, "u": "/private/files/other.pdf"}, {**a, "t": "NPA"}, {**a, "e": "2099-01-01"}):
			with self.assertRaises(frappe.PermissionError):
				task_share.shared_document(**tampered)

	def test_an_expired_link_does_not_open(self):
		a = self.args(self.urls[0])
		a["e"] = "2020-01-01"
		a["k"] = task_share._key(a["i"], a["t"], a["u"], a["e"])
		with self.assertRaises(frappe.PermissionError):
			task_share.shared_document(**a)
