# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Registering at an event by QR code (Solar Event): the public form makes one lead of the
event's company, owner and source; a repeat visitor updates it; the honeypot, a closed event
and a missing consent save nothing; papers are sniffed; the stall screen never sees a
number; the brochure link names only its own lead; and the instant estimate sizes sensibly
(api/event_registration, api/event_screen, api/instant_estimate)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime, today

from a3_sola.api import event_registration as reg
from a3_sola.api import event_screen, instant_estimate, ratelimit

MOBILE = "9000012301"


class TestEventRegistration(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ratelimit.reset_all()
		company = frappe.db.get_value("Company", {}, "name")
		district = frappe.db.get_value("Indian District", {"state": reg.STATE}, "name")
		if not (company and district):
			self.skipTest("No company or Kerala district on this site.")
		self.district = district
		self.event = frappe.get_doc({"doctype": "Solar Event", "event_name": "Test Event Registration Expo",
			"company": company, "lead_owner": "Administrator", "whatsapp_number": "9847012345"}).insert()

	def tearDown(self):
		frappe.form_dict.clear()
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def submit(self, **values):
		data = {"key": self.event.public_key, "full_name": "Test Visitor Name", "mobile_no": MOBILE,
			"district": self.district, "interest": "Home", "whatsapp_consent": 1}
		data.update(values)
		frappe.form_dict.clear()
		frappe.form_dict.update(data)
		return reg.submit()

	def lead(self):
		return frappe.get_doc("Lead", reg.find_lead(self.event.company, MOBILE))

	def test_a_registration_is_a_lead_of_the_event(self):
		r = self.submit(call_time="Evening")
		self.assertTrue(r["ok"] and r["created"])
		lead = self.lead()
		self.assertEqual((lead.company, lead.lead_owner, lead.owner, lead.a3s_event, lead.campaign_name),
			(self.event.company, "Administrator", "Administrator", self.event.name, self.event.campaign))
		self.assertEqual(lead.source, self.event.lead_source)
		self.assertEqual((lead.first_name, lead.mobile_no, lead.whatsapp_no), ("Test", MOBILE, MOBILE))
		self.assertTrue(lead.a3s_whatsapp_consent)
		self.assertEqual(str(lead.next_followup_date), today())
		self.assertEqual([r.channel for r in lead.outreach_log], ["Walk-in"])

	def test_the_same_number_again_updates_the_lead(self):
		self.submit()
		self.submit(full_name="Another Name", mobile_no="+91 " + MOBILE, bill_amount=3000)
		leads = frappe.get_all("Lead", filters={"mobile_no": MOBILE})
		self.assertEqual(len(leads), 1)
		lead = self.lead()
		self.assertEqual(lead.first_name, "Test")  # what the lead has stays
		self.assertEqual(len(lead.outreach_log), 2)

	def test_a_visit_without_a_bill_keeps_the_estimate(self):
		self.submit(bill_amount=4000)
		before = self.lead().a3s_estimate
		self.submit()
		self.assertEqual(self.lead().a3s_estimate, before)

	def test_the_honeypot_closed_events_and_no_consent_save_nothing(self):
		r = self.submit(website_url="http://spam.example")
		self.assertTrue(r["ok"])
		self.assertIsNone(reg.find_lead(self.event.company, MOBILE))
		with self.assertRaises(frappe.ValidationError):
			self.submit(whatsapp_consent=0)
		with self.assertRaises(frappe.ValidationError):
			self.submit(mobile_no="12345")
		with self.assertRaises(frappe.ValidationError):
			self.submit(district="Nowhere")
		self.event.db_set("is_active", 0)
		with self.assertRaises(frappe.ValidationError):
			self.submit()
		self.assertIsNone(reg.find_lead(self.event.company, MOBILE))

	def test_uploads_are_told_by_their_bytes(self):
		self.assertEqual(reg.sniff(b"%PDF-1.7 ..."), "pdf")
		self.assertEqual(reg.sniff(b"\xff\xd8\xff\xe0...."), "jpeg")
		self.assertEqual(reg.sniff(b"\x89PNG\r\n\x1a\n...."), "png")
		self.assertEqual(reg.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp")
		self.assertIsNone(reg.sniff(b"<html><script>"))
		self.assertIsNone(reg.sniff(b"MZ\x90\x00"))
		with self.assertRaises(frappe.ValidationError):
			reg._check_pdf(b"%PDF-1.4 broken", "PAN")

	def test_the_stall_screen_never_sees_a_number(self):
		self.submit(bill_amount=4000)
		feed = event_screen.feed(self.event.display_key)
		self.assertEqual(feed["counters"]["total"], 1)
		self.assertIn("Test Visitor Name", feed["ticker"])
		self.assertNotIn(MOBILE, json.dumps(feed))
		with self.assertRaises(frappe.PermissionError):
			event_screen.feed(self.event.public_key)  # the QR's key never opens the screen

	def test_a_slow_registration_still_reaches_the_screen(self):
		"""A registration is stamped when it starts and seen only once it is saved - with papers
		on a phone, seconds later. A poll in between moves the screen on; the next must still
		bring the welcome."""
		from frappe.utils import add_to_date, now_datetime

		first = event_screen.feed(self.event.display_key)
		self.submit(bill_amount=4000)
		lead = self.lead()
		started = add_to_date(get_datetime(first["now"]), seconds=-5)
		lead.db_set("a3s_registered_on", started, update_modified=False)
		later = event_screen.feed(self.event.display_key, after=first["now"])
		self.assertIn(("welcome", lead.name), [(i["kind"], i["id"]) for i in later["items"]])

	def test_a_visitor_who_asks_is_not_named_on_the_screen(self):
		self.submit(show_on_screen=0, bill_amount=4000)
		feed = event_screen.feed(self.event.display_key)
		welcome = next(i for i in feed["items"] if i["kind"] == "welcome")
		self.assertEqual((welcome["name"], welcome["estimate"], welcome["hidden"]), ("", None, 1))
		self.assertNotIn("Test Visitor Name", feed["ticker"])

	def test_the_brochure_link_names_only_its_own_lead(self):
		self.submit()
		lead = self.lead().name
		ref = reg.visitor_ref(lead)
		self.assertEqual(reg.lead_of_ref(ref), lead)
		self.assertIsNone(reg.lead_of_ref(lead + ".0000000000"))
		self.assertIsNone(reg.lead_of_ref("CRM-LEAD-0000-00000." + ref.rsplit(".", 1)[1]))

	def test_the_welcome_message_is_filled_in(self):
		self.submit(call_time="Morning")
		text = reg.welcome_text(self.event, self.lead())
		self.assertIn("Hello Test", text)
		self.assertIn(self.event.event_name, text)
		self.assertIn("in the morning", text)
		self.assertNotIn("{", text)


class TestInstantEstimate(FrappeTestCase):
	def test_the_smallest_size_that_covers_the_need_single_phase_first(self):
		d = frappe._dict
		packages = [d(name="a", capacity_kw=3, connection_type="Three Phase", price=230000),
			d(name="b", capacity_kw=3, connection_type="Single Phase", price=240000),
			d(name="c", capacity_kw=5, connection_type="Single Phase", price=310000)]
		self.assertEqual(instant_estimate.pick(packages, 2.4)[0].name, "b")
		self.assertEqual(instant_estimate.pick(packages, 4.1)[0].name, "c")
		chosen, larger = instant_estimate.pick(packages, 9)
		self.assertEqual((chosen.name, larger), ("c", True))
		self.assertEqual(instant_estimate.pick([], 3), (None, False))

	def test_rupees_are_grouped_the_indian_way(self):
		self.assertEqual(instant_estimate.inr(216600), "2,16,600")
		self.assertEqual(instant_estimate.inr(12345678), "1,23,45,678")
		self.assertEqual(instant_estimate.inr(950), "950")

	def test_no_bill_no_estimate(self):
		self.assertIsNone(instant_estimate.estimate(frappe.db.get_value("Company", {}, "name"), 0))
