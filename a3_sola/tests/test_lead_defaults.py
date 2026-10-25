# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A new lead starts as a client, from social media, in process, a product enquiry - on the
desk, on the portal's create form, and on its edit form while it has none of them yet."""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import leads
from a3_sola.setup.custom_fields import DEFAULT_LEAD_SOURCE

EXPECTED = {"type": "Client", "source": DEFAULT_LEAD_SOURCE, "qualification_status": "In Process",
	"request_type": "Product Enquiry"}


class TestLeadDefaults(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def created(self, **values):
		r = leads.create_lead(lead_name="Lead Default Test", mobile_no="9000000002", loan_required="No", **values)
		return frappe.get_doc("Lead", r["name"])

	def test_the_desk_starts_a_lead_on_the_defaults(self):
		doc = frappe.new_doc("Lead")
		self.assertEqual({f: doc.get(f) for f in EXPECTED}, EXPECTED)
		self.assertTrue(frappe.db.exists("Lead Source", DEFAULT_LEAD_SOURCE))

	def test_the_portal_creates_a_lead_on_the_defaults(self):
		doc = self.created()
		self.assertEqual({f: doc.get(f) for f in EXPECTED}, EXPECTED)

	def test_a_choice_on_the_create_form_is_kept(self):
		doc = self.created(type="Consultant", qualification_status="Qualified", request_type="Other", source="Walk In"
			if frappe.db.exists("Lead Source", "Walk In") else None)
		self.assertEqual((doc.type, doc.qualification_status, doc.request_type), ("Consultant", "Qualified", "Other"))

	def test_a_choice_not_in_the_options_falls_back_to_the_default(self):
		self.assertEqual(self.created(type="Nonsense").type, "Client")

	def test_the_edit_form_starts_a_blank_field_on_its_default(self):
		doc = self.created()
		doc.db_set({f: None for f in EXPECTED})
		values = {s["fieldname"]: s["value"] for sec in leads.edit_fields(frappe.get_doc("Lead", doc.name)) for s in sec["fields"]}
		self.assertEqual({f: values[f] for f in EXPECTED}, EXPECTED)

	def test_the_edit_form_keeps_what_the_lead_has(self):
		doc = self.created(type="Channel Partner")
		values = {s["fieldname"]: s["value"] for sec in leads.edit_fields(frappe.get_doc("Lead", doc.name)) for s in sec["fields"]}
		self.assertEqual(values["type"], "Channel Partner")


class TestLeadOutreachDefaults(FrappeTestCase):
	"""A new lead is in discussion, its call connected, its last message today; a Solar Proposal
	for it puts it on the 24-hour nudge and has it followed up the next day - edited, the day
	after the edit."""

	def setUp(self):
		frappe.set_user("Administrator")
		r = leads.create_lead(lead_name="Outreach Default Test", mobile_no="9000000004", loan_required="No")
		self.lead = r["name"]

	def lead_doc(self):
		return frappe.get_doc("Lead", self.lead)

	def proposal(self, insert):
		return frappe._dict(name="TEST-PROP", lead=self.lead, flags=frappe._dict(in_insert=insert))

	def test_a_new_lead_starts_in_discussion_connected_today(self):
		doc = self.lead_doc()
		self.assertEqual((doc.solar_lead_status, doc.call_status, str(doc.last_message_date)),
			("In Discussion", "Connected", frappe.utils.today()))
		self.assertEqual(frappe.new_doc("Lead").solar_lead_status, "In Discussion")
		self.assertEqual(doc.outreach_stage, "Step 1: First Contact")
		self.assertEqual(frappe.new_doc("Lead").outreach_stage, "Step 1: First Contact")

	def test_a_proposal_puts_the_lead_on_the_nudge_followed_up_next_day(self):
		from a3_sola.api import outreach

		outreach.note_proposal(self.proposal(insert=True))
		doc = self.lead_doc()
		self.assertEqual(doc.outreach_stage, "Step 2: 24hr Nudge")
		self.assertEqual(str(doc.next_followup_date), frappe.utils.add_days(frappe.utils.today(), 1))

	def test_an_edited_proposal_moves_the_follow_up_to_the_day_after_the_edit(self):
		from unittest.mock import patch

		from a3_sola.api import outreach

		outreach.note_proposal(self.proposal(insert=True))
		later = frappe.utils.add_days(frappe.utils.today(), 3)
		with patch.object(outreach, "today", return_value=later):
			outreach.note_proposal(self.proposal(insert=False))
		doc = self.lead_doc()
		self.assertEqual(str(doc.next_followup_date), frappe.utils.add_days(later, 1))
		self.assertEqual(doc.outreach_stage, "Step 2: 24hr Nudge")

	def test_the_proposal_hooks_are_wired(self):
		hooks = frappe.get_hooks("doc_events").get("Solar Proposal", {})
		for event in ("on_update", "on_submit", "on_update_after_submit"):
			self.assertIn("a3_sola.api.outreach.note_proposal", hooks.get(event, []))
		self.assertNotIn("note_on_lead", str(frappe.get_hooks("doc_events").get("Quotation", {})))

	def test_a_contact_logged_after_the_proposal_moves_the_lead_on(self):
		from a3_sola.api import outreach

		doc = frappe._dict(outreach_stage=None, next_followup_date=None, proposal_created_on="2026-10-01",
			proposal_updated_on="2026-10-01")
		outreach.apply_proposal(doc, frappe.utils.getdate("2026-10-05"))
		self.assertIsNone(doc.outreach_stage)
		outreach.apply_proposal(doc, frappe.utils.getdate("2026-09-30"))
		self.assertEqual((doc.outreach_stage, str(doc.next_followup_date)), ("Step 2: 24hr Nudge", "2026-10-02"))


class TestLeadListFollowUp(FrappeTestCase):
	"""The Leads list's Follow Up view shows each lead's outreach stage and next follow-up."""

	def test_each_row_carries_its_stage_and_next_follow_up(self):
		from a3_sola.www.a3solaportal.leads.index import lead_rows

		frappe.set_user("Administrator")
		name = leads.create_lead(lead_name="Follow Up Row Test", mobile_no="9000000006", loan_required="No")["name"]
		frappe.db.set_value("Lead", name, "next_followup_date", frappe.utils.add_days(frappe.utils.today(), 2))
		row = next(r for r in lead_rows({"name": name}))
		self.assertEqual(row["outreach_stage"], "Step 1: First Contact")
		self.assertTrue(row["next_followup"])
		self.assertFalse(row["followup_due"])
