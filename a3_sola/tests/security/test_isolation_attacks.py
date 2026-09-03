# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The adversarial isolation suite.

Every other test in this app asks "does this work?". This one asks "can I get at somebody
else's data?", and the only acceptable answer is no, from every direction, at every role
level, for every doctype the registries know about.

ANY SUCCESS FAILS THE RUN. Not a warning, not a report entry to triage later - the suite
fails, because a cross-tenant read in a product where two solar EPCs share an instance is
business-ending for the customer and relationship-ending for the vendor.

The counts are printed on every run so the evidence is a number rather than a claim.
"""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api.security import attacks, audit
from a3_sola.api.security.attacks import BLOCKED, LEAKED, SKIPPED
from a3_sola.tests.security import fixtures

ARTEFACT = "isolation_audit.json"


class IsolationAttackSuite(FrappeTestCase):
	"""Three tenants, users at three role levels, every vector against every other."""

	tenants = {}
	results = None

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		fixtures.purge()
		cls.tenants = {
			tag: fixtures.build(tag, index)
			for index, tag in enumerate(("A", "B", "C"), start=1)
		}
		# Committed on purpose. The attacks run as other users through code paths that
		# commit, and an uncommitted fixture is invisible to them.
		frappe.db.commit()
		cls.results = cls._run_everything()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		fixtures.purge()
		frappe.db.commit()
		super().tearDownClass()

	@classmethod
	def _run_everything(cls):
		attempts = []
		pairs = [("A", "B"), ("B", "C"), ("C", "A")]
		for own, foreign in pairs:
			mine, theirs = cls.tenants[own], cls.tenants[foreign]
			for level, actor in mine["users"].items():
				attempts.extend(audit.run_attack_suite(
					actor, mine["company"], theirs["company"],
					own_tenant=mine["tenant"], foreign_tenant=theirs["tenant"],
					# Writes included: proving a foreign write is refused matters more
					# than proving a read is, and this is a disposable test database.
					read_only=False,
					# One role level does the full doctype sweep; the other two do a
					# sample, because three full sweeps take minutes and add nothing -
					# the permission model does not vary by doctype per role.
					doctype_limit=None if level == "admin" else 12,
				))
		result = audit.summarise(attempts)
		cls._write_artefact(result)
		print("\n" + audit.render_summary(result) + "\n")
		return result

	@classmethod
	def _write_artefact(cls, result):
		path = os.path.join(frappe.get_site_path("private", "files"), ARTEFACT)
		try:
			os.makedirs(os.path.dirname(path), exist_ok=True)
			with open(path, "w") as handle:
				json.dump(result, handle, indent=1, default=str)
			print(f"isolation evidence written to {path}")
		except Exception as exception:
			print(f"could not write the evidence artefact: {exception}")

	# ------------------------------------------------------------------ the bar
	def test_no_attempt_returned_foreign_data(self):
		"""The whole suite in one assertion. Everything else is diagnostics."""
		leaks = self.results["leaks"]
		self.assertEqual(
			self.results["leaked"], 0,
			"CROSS-TENANT ACCESS SUCCEEDED - this is a Blocker:\n"
			+ "\n".join(
				f"  {l['vector']} / {l['doctype']} as {l['actor']} -> {l['target']}"
				f" ({l['detail']})" for l in leaks[:30]
			),
		)

	def test_the_suite_actually_attempted_something(self):
		"""A suite that silently attempts nothing passes for the wrong reason.

		This is the guard against exactly that: a fixture that failed to build, a registry
		that returned nothing, an exception swallowed somewhere. Zero leaks out of zero
		attempts is not evidence.
		"""
		self.assertGreater(self.results["attempts"], 500,
		                   f"only {self.results['attempts']} attempts were made")
		self.assertGreater(self.results["blocked"], 400,
		                   "almost everything was skipped rather than blocked")

	def test_every_company_scoped_doctype_was_covered(self):
		"""A doctype added in a later phase must be attacked without anybody adding it here."""
		scoped = set(attacks.company_scoped_doctypes())
		covered = set(self.results["by_doctype"])
		missing = sorted(scoped - covered)
		self.assertEqual(missing, [], f"these doctypes were never attacked: {missing}")

	def test_all_seventeen_vector_families_ran(self):
		families = {
			"list_view", "direct_get", "client.get", "client.get_list", "client.get_value",
			"client.get_count", "report_foreign_filter", "report_no_filter", "link_search",
			"search_widget", "print_view", "private_file", "export", "bulk_set_value",
			"bulk_delete", "dashboard_aggregate", "global_search", "comments", "versions",
			"activity", "whitelisted_method", "group_by_company", "platform_private",
		}
		ran = set(self.results["by_vector"])
		missing = sorted(families - ran)
		self.assertEqual(missing, [], f"these vectors never ran: {missing}")

	def test_platform_private_records_are_unreachable(self):
		"""Your own tenant list, payment orders and settings, from a customer's account."""
		rows = self.results["by_vector"].get("platform_private")
		self.assertTrue(rows, "the platform-private vector did not run")
		self.assertEqual(rows[LEAKED], 0)

	def test_link_search_suggests_no_foreign_names(self):
		"""Named separately because it leaks NAMES even when reads are blocked, and a
		consumer number is itself commercially sensitive."""
		for vector in ("link_search", "search_widget"):
			rows = self.results["by_vector"].get(vector)
			if rows:
				self.assertEqual(rows[LEAKED], 0, f"{vector} suggested foreign records")

	def test_no_report_returns_foreign_rows_with_no_filter_at_all(self):
		"""The commoner and worse bug: a report that refuses an explicit foreign company
		but returns every company when asked for none."""
		rows = self.results["by_vector"].get("report_no_filter")
		self.assertTrue(rows, "reports were never run without a filter")
		self.assertEqual(rows[LEAKED], 0)

	def test_no_whitelisted_method_answers_for_a_foreign_reference(self):
		rows = self.results["by_vector"].get("whitelisted_method")
		self.assertTrue(rows, "the whitelisted-method sweep did not run")
		self.assertEqual(rows[LEAKED], 0)

	def test_no_privilege_escalation_succeeded(self):
		for vector in ("escalate_platform_role", "remove_own_user_permission",
		               "raise_own_quota", "read_settings_singleton", "read_foreign_tenant",
		               "read_gateway_credentials"):
			rows = self.results["by_vector"].get(vector)
			if rows:
				self.assertEqual(rows[LEAKED], 0, f"{vector} succeeded")

	def test_the_suite_detects_isolation_that_is_actually_broken(self):
		"""The negative control, and the most important test in this file.

		Every other assertion here says "the attacks found nothing". That is only evidence
		if the attacks would find something when there is something to find. A suite whose
		vectors all fail for an unrelated reason - a typo'd doctype name, an exception
		swallowed in a helper, a fixture that built nothing - reports a clean run and
		proves precisely nothing.

		So: deliberately break one user's isolation by removing the User Permission that IS
		the boundary, re-run a slice of the suite, and require it to LEAK. If this test
		ever passes silently, the clean runs above are worthless.
		"""
		from a3_sola.api.security import attacks

		mine, theirs = self.tenants["A"], self.tenants["B"]
		actor = mine["users"]["admin"]
		permissions = frappe.get_all(
			"User Permission", filters={"user": actor, "allow": "Company"}, pluck="name")
		self.assertTrue(permissions, "the fixture did not create the boundary to remove")

		removed = []
		try:
			for name in permissions:
				removed.append(frappe.get_doc("User Permission", name).as_dict())
				frappe.delete_doc("User Permission", name, force=True,
				                  ignore_permissions=True)
			frappe.clear_cache(user=actor)
			frappe.db.commit()

			broken = audit.run_attack_suite(
				actor, mine["company"], theirs["company"],
				own_tenant=mine["tenant"], foreign_tenant=theirs["tenant"],
				read_only=True, doctype_limit=12,
			)
			result = audit.summarise(broken)
			self.assertGreater(
				result["leaked"], 0,
				"isolation was deliberately removed and the suite still found nothing - "
				"the attacks are not actually attacking anything",
			)
			print(f"\nnegative control: {result['leaked']} leak(s) detected with the "
			      f"boundary removed, as expected")
		finally:
			for row in removed:
				frappe.get_doc({
					"doctype": "User Permission", "user": row["user"],
					"allow": row["allow"], "for_value": row["for_value"],
					"apply_to_all_doctypes": row.get("apply_to_all_doctypes", 1),
				}).insert(ignore_permissions=True)
			frappe.clear_cache(user=actor)
			frappe.db.commit()

	def test_what_could_not_be_covered_is_stated(self):
		"""Skipped is not the same as passed, and the report has to say which is which."""
		self.assertIsInstance(self.results["skipped_detail"], list)
		print(f"\nnot attempted ({self.results['skipped']}):")
		for line in self.results["skipped_detail"][:20]:
			print(f"  {line}")
