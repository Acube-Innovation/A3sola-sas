# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Leads from a Google Sheet: checked first, nothing saved; then new ones added - none twice -
or existing ones updated, found by Lead ID, mobile number or email, a blank cell changing
nothing. The sheet is read as its link's CSV export; here the read is stood in for."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.api import lead_import

SHEET = "https://docs.google.com/spreadsheets/d/1AbC_test-sheet/edit#gid=42"


def csv_of(*rows):
	return "\n".join(",".join(f'"{c}"' for c in row) for row in rows)


class SheetCase:
	"""A sheet stood in for, its leads - and campaigns - tagged and removed after."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.tag = frappe.generate_hash(length=6)
		# Ten digits of their own, so no lead already on the site has them.
		self.phones = [f"9{abs(hash(self.tag + str(i))) % 10**9:09d}" for i in range(4)]

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Lead", filters={"lead_name": ["like", f"%{self.tag}%"]}, pluck="name"):
			frappe.delete_doc("Lead", name, force=True, ignore_permissions=True)
		for name in frappe.get_all("Campaign", filters={"campaign_name": ["like", f"%{self.tag}%"]}, pluck="name"):
			frappe.delete_doc("Campaign", name, force=True, ignore_permissions=True)

	def check(self, text, mode="add", **campaign):
		with patch.object(lead_import, "fetch", return_value=text):
			return lead_import.preview(url=SHEET, mode=mode, **campaign)

	def run_all(self, token):
		results, start = [], 0
		while True:
			out = lead_import.run(token=token, start=start)
			results += out["results"]
			if out["done"]:
				return results
			start = out["next"]


class TestLeadImport(SheetCase, FrappeTestCase):
	def test_the_link_is_read_as_its_tabs_csv(self):
		self.assertEqual(lead_import.export_url(SHEET),
			"https://docs.google.com/spreadsheets/d/1AbC_test-sheet/export?format=csv&gid=42")
		self.assertTrue(lead_import.export_url("https://docs.google.com/spreadsheets/d/1AbC/edit?usp=sharing").endswith("export?format=csv"))
		with self.assertRaises(frappe.ValidationError):
			lead_import.export_url("https://example.com/spreadsheets/d/1AbC")

	def test_columns_are_found_by_label_name_or_alias(self):
		cols, ignored = lead_import.columns(["Lead ID", "Full Name", "Mobile", "Email ID", "Loan Required", "Favourite colour"],
			lead_import.field_specs())
		self.assertEqual(cols, ["id", "lead_name", "mobile_no", "email_id", "loan_required", None])
		self.assertEqual(ignored, ["Favourite colour"])
		# A Meta lead export: its "id" is Meta's, not a lead's; its names are snake_case.
		cols, _ignored = lead_import.columns(["id", "full_name", "phone_number", "lead_status", "campaign_name"], lead_import.field_specs())
		self.assertEqual(cols, [None, "lead_name", "mobile_no", "solar_lead_status", "campaign_name"])

	def test_phone_numbers_are_kept_as_ten_digits(self):
		for raw in ("p:+919847012345", "+91 98470 12345", "9847012345.0", "09847012345", "98470-12345"):
			self.assertEqual(lead_import._phone(raw), "9847012345", raw)
		self.assertEqual(lead_import._phone("+44 20 7946 0958"), "+44 20 7946 0958")

	def test_new_leads_are_added_once_with_the_forms_values(self):
		text = csv_of(
			["Name", "Mobile", "Loan Required", "Source", "State", "District", "Next Follow Up Date", "Monthly Bill"],
			[f"Asha {self.tag}", self.phones[0], "yes", "walk in", "Kerala", "Thrissur", "09/11/2026", "₹2,400"],
			[f"Biju {self.tag}", self.phones[1], "No", "", "", "", "", ""],
			[f"Biju again {self.tag}", self.phones[1], "No", "", "", "", "", ""],
			[f"Chinnu {self.tag}", self.phones[2], "", "", "", "", "", ""],
			[f"Devi {self.tag}", self.phones[3], "No", "Billboard", "", "", "", ""],
		)
		out = self.check(text)
		will = {r["row"]: (r["action"], " ".join(r["errors"])) for r in out["rows"]}
		self.assertEqual(will[2][0], "add")
		self.assertEqual(will[3][0], "add")
		self.assertIn("Same mobile number", will[4][1])
		# The loan may wait: not known yet is no reason to skip a lead.
		self.assertEqual(will[5][0], "add")
		self.assertIn("Billboard", will[6][1])
		self.assertEqual(out["counts"]["add"], 3)
		# Checking saved nothing.
		self.assertFalse(frappe.db.exists("Lead", {"lead_name": f"Asha {self.tag}"}))

		results = self.run_all(out["token"])
		self.assertTrue(all(r["ok"] for r in results), results)
		self.assertFalse(frappe.db.get_value("Lead", {"lead_name": f"Chinnu {self.tag}"}, "loan_required"))
		asha = frappe.get_doc("Lead", {"lead_name": f"Asha {self.tag}"})
		self.assertEqual((asha.loan_required, asha.source, asha.district, str(asha.next_followup_date), asha.avg_monthly_bill),
			("Yes", "Walk In", "Thrissur, Kerala", "2026-11-09", 2400))
		# The form's defaults where the sheet said nothing - as a lead not contacted yet.
		self.assertEqual((asha.status, asha.type, asha.solar_lead_status, asha.call_status, asha.last_message_date),
			("Lead", "Client", "New", None, None))

		# The same sheet again adds nobody twice.
		again = self.check(text)
		self.assertEqual(again["counts"]["add"], 0)
		self.assertIn("Already a lead", " ".join(again["rows"][0]["errors"]))

	def test_existing_leads_are_updated_by_id_or_mobile_and_blanks_change_nothing(self):
		self.run_all(self.check(csv_of(["Name", "Mobile", "Loan Required", "City"],
			[f"Eapen {self.tag}", self.phones[0], "No", "Kochi"], [f"Fathima {self.tag}", self.phones[1], "No", "Kollam"]))["token"])
		eapen = frappe.db.get_value("Lead", {"lead_name": f"Eapen {self.tag}"})
		out = self.check(csv_of(
			["Lead ID", "Mobile", "City", "Loan Required", "Status"],
			[eapen, "", "Aluva", "", "Interested"],
			["", self.phones[1], "", "No", ""],
			["", self.phones[3], "Thrissur", "", ""],
		), mode="update")
		will = {r["row"]: r for r in out["rows"]}
		self.assertEqual((will[2]["action"], will[2]["lead"]), ("update", eapen))
		self.assertEqual(sorted(will[2]["changes"]), ["City / Town", "Status"])
		self.assertEqual(will[3]["action"], "same")
		self.assertEqual(will[4]["action"], "skip")
		self.run_all(out["token"])
		doc = frappe.get_doc("Lead", eapen)
		self.assertEqual((doc.city, doc.status, doc.loan_required, doc.mobile_no), ("Aluva", "Interested", "No", self.phones[0]))

	def test_a_row_that_fails_to_save_does_not_stop_the_rest(self):
		out = self.check(csv_of(["Name", "Mobile", "Loan Required"],
			[f"Gopi {self.tag}", self.phones[0], "No"], [f"Hari {self.tag}", self.phones[1], "No"]))
		real = lead_import._add

		def add(values):
			if values.get("lead_name", "").startswith("Gopi"):
				frappe.throw("No room")
			return real(values)

		with patch.object(lead_import, "_add", side_effect=add):
			results = self.run_all(out["token"])
		self.assertEqual([(r["row"], r["ok"]) for r in results], [(2, False), (3, True)])
		self.assertIn("No room", results[0]["error"])
		self.assertTrue(frappe.db.exists("Lead", {"lead_name": f"Hari {self.tag}"}))

	def test_someone_without_lead_rights_may_not_import(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			self.check(csv_of(["Name"], ["Nobody"]))


class TestLeadImportCampaign(SheetCase, FrappeTestCase):
	"""The campaign the imported leads go in."""

	def test_a_new_campaign_is_made_when_the_import_runs_and_holds_every_lead(self):
		title = f"Sheet Campaign {self.tag}"
		other = frappe.get_doc({"doctype": "Campaign", "campaign_name": f"Own Campaign {self.tag}"}).insert()
		out = self.check(csv_of(["Name", "Mobile", "Loan Required", "Campaign Name"],
			[f"Indu {self.tag}", self.phones[0], "No", ""], [f"Jose {self.tag}", self.phones[1], "No", other.campaign_name]),
			new_campaign=title)
		self.assertEqual((out["campaign"], out["campaign_is_new"]), (title, True))
		self.assertFalse(frappe.db.exists("Campaign", {"campaign_name": title}), "checking makes nothing")
		self.run_all(out["token"])
		made = frappe.db.get_value("Campaign", {"campaign_name": title})
		self.assertTrue(made)
		self.assertEqual(frappe.db.get_value("Lead", {"lead_name": f"Indu {self.tag}"}, "campaign_name"), made)
		# A row naming its own campaign keeps it.
		self.assertEqual(frappe.db.get_value("Lead", {"lead_name": f"Jose {self.tag}"}, "campaign_name"), other.name)

	def test_an_existing_campaign_goes_on_updated_leads_too(self):
		camp = frappe.get_doc({"doctype": "Campaign", "campaign_name": f"Spring {self.tag}"}).insert()
		self.run_all(self.check(csv_of(["Name", "Mobile", "Loan Required"], [f"Kavya {self.tag}", self.phones[0], "No"]))["token"])
		out = self.check(csv_of(["Mobile", "City"], [self.phones[0], ""]), mode="update", campaign=camp.name)
		self.assertEqual(out["rows"][0]["action"], "update")
		self.assertIn("Campaign", " ".join(out["rows"][0]["changes"]))
		self.run_all(out["token"])
		self.assertEqual(frappe.db.get_value("Lead", {"lead_name": f"Kavya {self.tag}"}, "campaign_name"), camp.name)
		with self.assertRaises(frappe.ValidationError):
			self.check(csv_of(["Mobile"], [self.phones[0]]), mode="update", campaign="No Such Campaign")

	def test_a_sheet_calling_its_leads_new_adds_them_as_new(self):
		out = self.check(csv_of(["Name", "Mobile", "Loan Required", "Status", "lead_status"],
			[f"Lalu {self.tag}", f"p:+91{self.phones[0]}", "No", "New", "CREATED"], [f"Mini {self.tag}", self.phones[1], "No", "Interested", ""]))
		self.assertEqual(out["counts"]["add"], 2, out["rows"])
		self.run_all(out["token"])
		self.assertEqual(frappe.db.get_value("Lead", {"lead_name": f"Lalu {self.tag}"}, ["status", "solar_lead_status", "mobile_no"]),
			("Lead", "New", self.phones[0]))
		# A status the sheet gives is kept.
		self.assertEqual(frappe.db.get_value("Lead", {"lead_name": f"Mini {self.tag}"}, "status"), "Interested")
