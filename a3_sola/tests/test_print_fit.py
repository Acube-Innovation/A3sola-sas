# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal's inner pages are fixed A4 frames that clip what runs past the footer, so
what varies in length - the letter, 3.2's components, 3.4's terms - is fitted to them."""

from frappe.tests.utils import FrappeTestCase

from a3_sola.api import print_cover

OPTION = "9.92kWp with 620Wp DCR Solar Panels by Rayzon, 10kW Three Phase String On-Grid Inverter by Solinteg."


def letter(points, place="Kochi"):
	return {"date": "29.10.2026", "to": "Shanal", "place": place, "dear": "Dear Sir/Madam,",
		"opening": list(print_cover.LETTER_OPENING), "closing": list(print_cover.LETTER_CLOSING),
		"intro": "Please find enclosed our offer with the following options:", "points": points,
		"company_name": "Acube Innovations", "signatory": "Nevil Jose", "designation": "Managing Partner"}


class TestLetterFit(FrappeTestCase):
	def test_a_short_letter_keeps_the_full_size(self):
		# A revised proposal's short letter: no address block, introduction or opening.
		short = dict(letter([OPTION]), short=True, opening=[], closing=list(print_cover.REVISED_CLOSING))
		self.assertEqual(print_cover._letter_pt(short), print_cover.LETTER_MAX_PT)

	def test_a_full_one_option_letter_is_set_to_clear_the_footer(self):
		# At the full size its signature ran into the footer (RENC-PROP-26-27-RIL-0002): a size down.
		pt = print_cover._letter_pt(letter([OPTION]))
		self.assertLess(pt, print_cover.LETTER_MAX_PT)
		self.assertGreaterEqual(pt, 11.5)

	def test_more_options_set_the_letter_smaller_but_never_below_the_minimum(self):
		one = print_cover._letter_pt(letter([OPTION]))
		three = print_cover._letter_pt(letter(["Option {0}: {1}".format(i, OPTION) for i in (1, 2, 3)]))
		self.assertLess(three, one)
		self.assertEqual(print_cover._letter_pt(letter([OPTION] * 40)), print_cover.LETTER_MIN_PT)

	def test_the_chosen_size_fits_the_column(self):
		doc = letter(["Option {0}: {1}".format(i, OPTION) for i in (1, 2, 3)])
		pt = print_cover._letter_pt(doc)
		self.assertLessEqual(print_cover._letter_height(doc, pt), print_cover.LETTER_ROOM_PT)
		self.assertGreater(print_cover._letter_height(doc, pt + 0.25), print_cover.LETTER_ROOM_PT)


class TestComponentPages(FrappeTestCase):
	SUMMARY = {"rows": [("Site Location", "Residence Building in Kochi, Ernakulam")] * 7}

	def row(self, **kw):
		return dict({"item": "DCDB", "spec": "With PV fuses at input, DC isolator and Type 2 DC SPD", "make": "Eaton", "nos": 1}, **kw)

	def test_a_long_table_runs_on_and_numbers_continue(self):
		out = print_cover.component_pages(self.SUMMARY, {"rows": [self.row() for _ in range(20)]})
		self.assertTrue(out["under_summary"])
		self.assertGreater(len(out["pages"]), 1)
		self.assertEqual(sum(len(p["rows"]) for p in out["pages"]), 20)
		self.assertEqual(out["pages"][1]["start"], len(out["pages"][0]["rows"]) + 1)

	def test_a_group_of_spanned_rows_is_never_split(self):
		group = [self.row(span=3)] + [self.row(spanned=True) for _ in range(2)]
		rows = [self.row() for _ in range(3)] + group + [self.row()]
		for page in print_cover.component_pages(self.SUMMARY, {"rows": rows})["pages"]:
			self.assertFalse(page["rows"][0].get("spanned"))

	def test_a_spanned_group_counts_as_one_item(self):
		group = [self.row(span=2), self.row(spanned=True)]
		rows = [self.row() for _ in range(2)] + group + [self.row() for _ in range(12)]
		pages = print_cover.component_pages(self.SUMMARY, {"rows": rows})["pages"]
		items = 0
		for page in pages:
			self.assertEqual(page["start"], items + 1)
			items += sum(1 for r in page["rows"] if not r.get("spanned"))
		self.assertEqual(items, 15)

	def test_no_rows_no_pages(self):
		self.assertEqual(print_cover.component_pages(self.SUMMARY, {"rows": []}), {"under_summary": True, "pages": []})


class TestFlowPages(FrappeTestCase):
	"""The terms to the way forward run on page after page, as many sections to a page as fit."""

	def rest(self, terms, scope_rows=4):
		row = {"category": "Engineering", "text": "System design including civil, structural and electrical components."}
		return {"terms_html": "<ul>" + "".join("<li>{0}</li>".format(t) for t in terms) + "</ul>", "validity": "",
			"payment_terms": list(print_cover.PAYMENT_TERMS), "bank": [("PAN", "X")] * 3,
			"bank_credentials": [("Bank", "X")] * 4, "payment_qr": "", "schedule_html": "<ul><li>Supply: 7 days.</li></ul>",
			"warranty_items": [{"text": "System Warranty shall be for 5 years.", "sub": []}],
			"scope": {"company": [row] * scope_rows, "customer": [row] * scope_rows}, "way_forward": list(print_cover.WAY_FORWARD)}

	def test_every_section_is_laid_out_once_in_order(self):
		pages = print_cover.flow_pages(self.rest(["The price is for a flat roof."] * 3))
		self.assertEqual([key for page in pages for key in page], list(print_cover.FLOW))

	def test_short_terms_share_the_page_with_the_payment_terms(self):
		pages = print_cover.flow_pages(self.rest(["The price is for a flat roof."] * 3))
		self.assertEqual(pages[0][:2], ["terms", "payment"])

	def test_long_terms_turn_the_payment_terms_to_the_next_page(self):
		pages = print_cover.flow_pages(self.rest(["x " * 80] * 9))
		self.assertEqual(pages[0], ["terms"])
		self.assertEqual(pages[1][0], "payment")
