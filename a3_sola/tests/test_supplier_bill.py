# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A supplier's tax invoice is read into its lines, taxes and total, checked, and entered as a
Purchase Invoice on the job: the Supplier Invoice task (api/supplier_bill)."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from a3_sola.api import supplier_bill

# A Tally tax invoice's text as the PDF reader gives it, with made-up parties and figures.
BILL = """
                  TEST SUPPLIERS PRIVATE LIMITED 2026-27                                Invoice No.       e-Way Bill No.Dated
                  Ground Floor, Warehouse1                                              TSPL/26-27/0042      57200000000129-Oct-26
                  GSTIN/UIN: 32AAAAA1111A1Z1                                            Reference No. & Date.         Other References
                                                                                        TSPL/26-27/0042  dt. 29-Oct-26
Consignee (Ship to)

Anna Varghese                                                                           Dispatch Doc No.
Buyer (Bill to)
Test Buyer Llp
GSTIN/UIN         : 32BBBBB2222B2Z2
Sl                     Description of                                                    AmountHSN/SACGSTQuantityRateperDisc. %
No.                    Goods and Services                                                Rate
1  TESTSOL 565WP DCR MONO MODULE                                      85414300      5 %      2 Nos    10,000.00  Nos             20,000.00
      r1200000000000001
      r1200000000000002
2  TEST SOLAR GRID TIE INVERTER - 1PH & 1MPPT 3000                    85049090      5 %      1 Nos    16,000.00  Nos             16,000.00
   WATT WITH RMS
      3K0000000-0000-000000000P
3  4Sqmm Test Solar Cable Black                                       85446030     18 %   30.00 Mtr       50.00  Mtr               1,500.00
                                                                                                                       continued to page number  2
4  Test Earthing Compound 10Kg                                        382499       18 %    2 Bags       250.00   Bags                500.00
                                                                                                                 38,000.00
                                  Test Meter Testing Charge                    998346         18 %                         200.00
                                                                     CGST                                                1,098.00
                                                                     SGST                                                1,098.00
                                                         Rounded Off                                                         0.00
                                                                        Total                                     ₹ 40,396.00
Doc No.:  Tax Invoice - TSPL/26-27/0042
85414300  TESTSOL 565WP DCR MONO MODULE & Photovoltaic Cells        2  NOS      20,000.00     2.50+2.50
"""


# A plain bill from a small, unregistered supplier, as a photo's OCR reads it: no GSTIN, HSN or GST,
# the quantity lost to the table's border.
SIMPLE_BILL = """Tax Invoice
sem ~=1TEST STRUCTURE WORKS
4 zy EKM, ALUVA
42> Phone: 9000000000 Email: test@example.com
TECH ir canals State: 32-Kerala
Bill To: Invoice Details:
Renewcore Innovation LLP No; 7
Date: 03-10-2026
1 |S kw solar flat roof structure installation ( Philip) ee eee) % 2,700.00 2 13,500.00
Total : = 13,500.00
Received ; = 0.00
For TEST STRUCTURE WORKS:
Authorized Signatory
"""


# RIM's seller block and bank block, as its Tally bill prints them - a label and its value may
# fall on separate lines.
RIM_BLOCK = """                  RIM TEST COPY 2026-27                                   Invoice No.
                  Ground Floor, Warehouse1
                  Ground Floor, 2/26A, Pattoorkunnu Road,
                  Patturkunnu, Chowara, Ekm -683571
                  Kerala
                  India
                  GSTIN/UIN: 32KKKKK2222K2Z2
                  State Name :  Kerala, Code : 32
                  Contact : +91-97466 20666,77365 58111
                  E-Mail : billing.example@gmail.com
Company's Bank Details
A/c Holder's Name : RIM PROJECTS PRIVATE LIMITED
Bank Name
: ICICI BANK- 028905 004141
A/c No.
: 028905004141
Branch & IFS Code : Aluva & ICIC0000289
Company's PAN
: AAJCR8845G
SWIFT Code
: ICICINBBCTS
"""


# A scanned tax invoice whose table gives CGST, SGST and IGST in columns (Vashi's layout), as its
# OCR reads it - the columns run together, a line's description and serials around its row - and
# the transporter's duplicate after it. Made-up parties and figures.
COLUMN_BILL = """Test Integrated Solutions Limited
"4 e (Formerly Known as Test Electricals Limited)

VY Test

X1/686, Test Buildings, HMT Ring Road, Kalamassery, Ernakulam, ,
Ernakulam, Kerala - 683503

Tax Invoice E-Way No - 562000000004

Original for Recipient

GST Invoice No.
2700000023

GST No.: 32AAAAA3333A1ZV, PAN: AAAAA3333A, CIN: U31904MH1991PLC000000, TAN: MUMV00000E
Toll Free No :1800-2000000 , Website: www.example.com , Email: sales@example.com

GST Invoice Date
16-10-2026

Place of Supply :- Kerala Bill To : TEST BUYER LLP
14/204 A FIRST FLOOR , TEST NAGAR , AT
Ship To : ANNA VARGHESE HANI , NEDUMBASSERY ,,
GST Registration No : 32BBBBB2222B2Z2 Delivery Type.: GDWN - Godown Delivery
Kerala, IN State Code : 32 LR No. & Date: Name : Hdfe Bank
PAN No: Vehicle No.: KL16U0000 AIC no.TEST78100000037
Aadhar No: Transporter: IFSC: HDFC0000240
Contact Details : Sales Order No.: 1000000070 WT: 500.00 Branch Address WORLI
Contact No : 9000000001 In favour of Test Integrated Solutions Limited.
Sr | HSN/ SAC Item Code / Product Description Quantity} UOM Rate Discount Cash et Rate / | Total Net CGST SGST/UTGST IGST Line Total
No Code % Discount %| Per Unit Price Rate Amount Rate Amount Rate Amount

Test Solar l-TEST620N-TOPCON-G2G-BF

Test 620 N TOPCON G2G NDCR

R1300000000 000001/R1300000000000002/

2 | 85414300 R1300000000000003/R1300000000000004/ 4 EA | 8680.00 | 0.00 0.00 8680.00 |34720.00} 2.50 868.00 2.50 | 868.00 0.00 0.00 36456.00

R1300000000 000005

Packed By: DIRECT DISPATCH Total
Checked By: DIRECT DISPATCH

4.00 34720.00 868.00 868.00 0.00 36456.00

Invoice Total: 36456.00

Whether the tax is payable on Reverse Remark : For Test Integrated Solutions Limited,

Test Integrated Solutions Limited
Duplicate for IRN Ack No -
Ship To : SOMEONE ELSE
2 | 85414300 R1300000000000003/R1300000000000004/ 4 EA | 8680.00 | 0.00 0.00 8680.00 |34720.00} 2.50 868.00 2.50 | 868.00 0.00 0.00 36456.00
"""


class TestSupplierBill(FrappeTestCase):
	def test_a_bill_with_tax_columns_is_read_once(self):
		p = supplier_bill.parse(COLUMN_BILL)
		self.assertEqual((p["supplier_name"], p["supplier_gstin"], p["buyer_gstin"], p["bill_no"], p["bill_date"]),
			("Test Integrated Solutions Limited", "32AAAAA3333A1ZV", "32BBBBB2222B2Z2", "2700000023", "2026-10-16"))
		self.assertEqual(len(p["lines"]), 1)  # the duplicate copy is not read again
		line = p["lines"][0]
		self.assertEqual((line["description"], line["hsn"], line["qty"], line["rate"], line["amount"], line["gst_rate"]),
			("Test Solar I-TEST620N-TOPCON-G2G-BF Test 620 N TOPCON G2G NDCR", "85414300", 4, 8680, 34720, 5))
		self.assertEqual(line["serials"], ["R1300000000000001", "R1300000000000002", "R1300000000000003",
			"R1300000000000004", "R1300000000000005"])
		self.assertEqual((p["cgst"], p["sgst"], p["igst"], p["total"]), (868, 868, 0, 36456))
		self.assertEqual(supplier_bill.check(p), [])
		self.assertTrue(p["consignee"].startswith("ANNA VARGHESE"))
		d = p["supplier_details"]
		self.assertEqual((d["address_line1"], d["pincode"], d["city"], d["state"]),
			("X1/686, Test Buildings, HMT Ring Road, Kalamassery, Ernakulam", "683503", "Ernakulam", "Kerala"))
		self.assertEqual((d["phone"], d["email"], d["pan"]), ("1800-2000000", "sales@example.com", "AAAAA3333A"))
		self.assertEqual((d["bank_name"], d["account_no"], d["ifsc"], d["branch"], d["account_holder"]),
			("HDFC Bank", "TEST78100000037", "HDFC0000240", "WORLI", "Test Integrated Solutions Limited"))

	def test_the_sellers_details_are_read_for_a_new_supplier(self):
		d = supplier_bill.supplier_details(RIM_BLOCK, {"supplier_name": "RIM TEST COPY", "supplier_gstin": "32KKKKK2222K2Z2"})
		self.assertEqual((d["address_line1"], d["pincode"], d["city"], d["state"], d["state_code"]),
			("Ground Floor, Warehouse1", "683571", "Ekm", "Kerala", "32"))
		self.assertEqual((d["phone"], d["email"], d["pan"]), ("+91-97466 20666", "billing.example@gmail.com", "AAJCR8845G"))
		self.assertEqual((d["account_holder"], d["bank_name"], d["account_no"], d["branch"], d["ifsc"], d["swift"]),
			("RIM PROJECTS PRIVATE LIMITED", "ICICI BANK", "028905004141", "Aluva", "ICIC0000289", "ICICINBBCTS"))
		plain = supplier_bill.parse(SIMPLE_BILL)["supplier_details"]
		self.assertEqual((plain["city"], plain["state"], plain["phone"], plain["gst_category"]), ("ALUVA", "Kerala", "9000000000", "Unregistered"))

	def test_a_plain_bill_is_read_by_its_labels(self):
		p = supplier_bill.parse(SIMPLE_BILL)
		self.assertEqual((p["supplier_name"], p.get("supplier_gstin"), p["bill_no"], p["bill_date"], p["total"]),
			("TEST STRUCTURE WORKS", None, "7", "2026-10-03", 13500))
		self.assertEqual([(l["description"], l["qty"], l["rate"], l["amount"], l["gst_rate"]) for l in p["lines"]],
			[("5 kw solar flat roof structure installation ( Philip)", 5, 2700, 13500, 0)])
		self.assertEqual(supplier_bill.check(p), [])

	def test_the_bill_is_read_by_its_layout(self):
		p = supplier_bill.parse(BILL)
		self.assertEqual(p["supplier_name"], "TEST SUPPLIERS PRIVATE LIMITED")
		self.assertEqual((p["supplier_gstin"], p["buyer_gstin"]), ("32AAAAA1111A1Z1", "32BBBBB2222B2Z2"))
		self.assertEqual((p["bill_no"], p["bill_date"]), ("TSPL/26-27/0042", "2026-10-29"))
		self.assertEqual(len(p["lines"]), 4)  # the e-way bill's goods after the total are not read
		module, inverter, cable, compound = p["lines"]
		self.assertEqual((module["hsn"], module["gst_rate"], module["qty"], module["rate"], module["amount"]),
			("85414300", 5, 2, 10000, 20000))
		self.assertEqual(module["serials"], ["r1200000000000001", "r1200000000000002"])
		# The description runs on to the next line; the serial under it is its own.
		self.assertEqual(inverter["description"], "TEST SOLAR GRID TIE INVERTER - 1PH & 1MPPT 3000 WATT WITH RMS")
		self.assertEqual(inverter["serials"], ["3K0000000-0000-000000000P"])
		self.assertEqual((cable["qty"], cable["uom"]), (30, "Mtr"))
		self.assertEqual(compound["serials"], [])  # the page subtotal under it is no serial
		self.assertEqual(p["charges"], [{"description": "Test Meter Testing Charge", "hsn": "998346", "gst_rate": 18,
			"qty": 1, "uom": "Nos", "rate": 200, "amount": 200, "serials": []}])
		self.assertEqual((p["cgst"], p["sgst"], p["igst"], p["round_off"], p["total"]), (1098, 1098, 0, 0, 40396))

	def test_the_consignee_is_the_customer_the_bill_is_for(self):
		self.assertEqual(supplier_bill.parse(BILL)["consignee"], "Anna Varghese")

	def test_a_bill_that_adds_up_has_no_warnings(self):
		self.assertEqual(supplier_bill.check(supplier_bill.parse(BILL)), [])

	def test_a_bill_that_does_not_add_up_is_said(self):
		p = supplier_bill.parse(BILL)
		p["total"] = 41396
		self.assertTrue(any("bill's total" in w for w in supplier_bill.check(p)))

	def test_a_rounding_taken_off_is_negative(self):
		text = BILL.replace("Rounded Off                                                         0.00",
			"Less :                                                 Rounded Off              (-)0.28")
		self.assertEqual(supplier_bill.parse(text)["round_off"], -0.28)

	def test_units_are_erpnexts(self):
		self.assertEqual(supplier_bill._uom("Mtr"), "Meter")
		self.assertEqual(supplier_bill._uom("Nos"), "Nos")
		self.assertEqual(supplier_bill._uom("Widgets"), "Nos")


class TestSupplierBillEntered(FrappeTestCase):
	"""The bill in ERPNext's tax format: the invoice's purchase tax template, each line's item
	tax template, ERPNext's own calculation - on the company's GST templates."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.job = frappe.db.get_value("Installation Stage Log", {"stage_code": supplier_bill.CODE,
			"parenttype": "Solar Installation"}, "parent")
		if not self.job:
			raise unittest.SkipTest("No job with a Supplier Invoice task to enter a bill on.")
		self.inst = frappe.get_doc("Solar Installation", self.job)
		self.in_state = supplier_bill.default_template(self.inst.company, "32AAAAA1111A1Z1")
		if not (self.in_state and supplier_bill.item_template_for(self.inst.company, 5)
				and supplier_bill.item_template_for(self.inst.company, 18)):
			raise unittest.SkipTest("The company has no GST tax templates.")
		self.bill = supplier_bill.parse(BILL)
		self.ensure(self.bill["supplier_name"], self.bill["supplier_gstin"])
		for row in self.bill["lines"] + self.bill["charges"]:
			row["item_tax_template"] = supplier_bill.item_template_for(self.inst.company, row["gst_rate"])

	def tearDown(self):
		frappe.db.rollback()

	def ensure(self, name, gstin):
		"""The supplier, as the page creates it from its invoice before the bill is entered."""
		return supplier_bill.create_supplier(self.job, frappe.as_json({"supplier_name": name, "gstin": gstin or ""}))["supplier"]

	def data(self, **extra):
		p = self.bill
		return {"supplier_name": p["supplier_name"], "supplier_gstin": p["supplier_gstin"], "bill_no": p["bill_no"],
			"bill_date": p["bill_date"], "tax_template": self.in_state, "lines": p["lines"] + p["charges"],
			"name_confirmed": 1, **extra}

	def test_each_line_is_taxed_at_its_own_rate(self):
		calc = supplier_bill._calculation(supplier_bill._build(self.inst, frappe._dict(self.data())), self.bill)
		module, cable = calc["lines"][0], calc["lines"][2]
		self.assertEqual([t["rate"] for t in module["taxes"]], [2.5, 2.5])  # GST 5%: CGST + SGST
		self.assertEqual([t["rate"] for t in cable["taxes"]], [9, 9])  # GST 18%
		self.assertEqual([t["amount"] for t in calc["taxes"]], [1098, 1098])
		self.assertEqual((calc["net_total"], calc["rounded_total"]), (38200, 40396))
		self.assertEqual(calc["warnings"], [])

	def test_an_out_of_state_supplier_pays_igst(self):
		out = supplier_bill.default_template(self.inst.company, "29AAAAA1111A1Z1")
		self.assertNotEqual(out, self.in_state)
		calc = supplier_bill._calculation(supplier_bill._build(self.inst, frappe._dict(self.data(tax_template=out))))
		self.assertEqual(len(calc["taxes"]), 1)
		self.assertEqual(calc["lines"][0]["taxes"][0]["rate"], 5)  # IGST at the line's whole rate
		self.assertEqual(calc["total_taxes"], 2196)

	def test_a_bill_for_another_customer_needs_confirming(self):
		other = dict(self.data(), consignee="Somebody Else Entirely", name_confirmed=0)
		if supplier_bill.name_check(self.inst, other["consignee"])["matches"]:
			raise unittest.SkipTest("The job's customer has that name.")
		with self.assertRaises(frappe.ValidationError):
			supplier_bill.create(self.job, frappe.as_json(other))
		made = supplier_bill.create(self.job, frappe.as_json(dict(other, name_confirmed=1)))
		self.assertIn("confirmation", frappe.db.get_value("Purchase Invoice", made["name"], "remarks"))
		frappe.db.rollback()

	def test_the_bill_is_entered_once_as_a_submitted_purchase_invoice(self):
		data = self.data()
		made = supplier_bill.create(self.job, frappe.as_json(data))
		pi = frappe.get_doc("Purchase Invoice", made["name"])
		self.assertEqual((pi.docstatus, pi.solar_installation, pi.a3s_material_bill, pi.bill_no), (1, self.job, 1, "TSPL/26-27/0042"))
		self.assertEqual(pi.taxes_and_charges, self.in_state)
		self.assertEqual([t.charge_type for t in pi.taxes], ["On Net Total", "On Net Total"])
		self.assertEqual(pi.items[0].item_tax_template, supplier_bill.item_template_for(self.inst.company, 5))
		self.assertEqual(pi.rounded_total, 40396)
		self.assertEqual(frappe.db.get_value("Supplier", pi.supplier, "tax_id"), "32AAAAA1111A1Z1")
		self.assertIn("r1200000000000001", pi.items[0].description)
		with self.assertRaises(frappe.ValidationError):
			supplier_bill.create(self.job, frappe.as_json(data))  # the same bill twice
		frappe.db.rollback()

	def paid(self, **extra):
		account = frappe.db.get_value("Account", {"company": self.inst.company, "account_type": "Bank", "is_group": 0}, "name")
		if not account or not frappe.db.exists("Mode of Payment", "NEFT/RTGS"):
			raise unittest.SkipTest("No bank account or NEFT/RTGS mode to pay from.")
		return {"status": "Paid", "mode": "NEFT/RTGS", "account": account, "paid_on": frappe.utils.today(), **extra}

	def test_neft_then_upi_come_first(self):
		modes = [m["name"] for m in supplier_bill.payment_choices(self.inst.company)["modes"]]
		self.assertEqual(modes[:2], ["NEFT/RTGS", "UPI"])
		self.assertEqual(supplier_bill.payment_choices(self.inst.company)["default_mode"], "NEFT/RTGS")

	def test_a_paid_bill_needs_a_transaction_number_or_proof(self):
		with self.assertRaises(frappe.ValidationError):
			supplier_bill.create(self.job, frappe.as_json(self.data(payment=self.paid())))
		self.assertFalse(frappe.db.exists("Purchase Invoice", {"bill_no": "TSPL/26-27/0042", "docstatus": 1}))

	def test_a_bill_entered_paid_is_paid_in_erpnext(self):
		made = supplier_bill.create(self.job, frappe.as_json(self.data(payment=self.paid(reference_no="UTR-TEST-1"))))
		pi = frappe.get_doc("Purchase Invoice", made["name"])
		self.assertEqual((pi.status, pi.outstanding_amount), ("Paid", 0))
		pe = frappe.get_doc("Payment Entry", made["payment_entry"])
		self.assertEqual((pe.docstatus, pe.payment_type, pe.reference_no, pe.mode_of_payment), (1, "Pay", "UTR-TEST-1", "NEFT/RTGS"))
		frappe.db.rollback()

	def test_an_unpaid_bill_is_marked_paid_once(self):
		made = supplier_bill.create(self.job, frappe.as_json(self.data()))
		self.assertEqual(frappe.db.get_value("Purchase Invoice", made["name"], "status"), "Unpaid")
		# A proof alone stands as the reference.
		pe = supplier_bill._pay(frappe.get_doc("Purchase Invoice", made["name"]), frappe._dict(self.paid()), ("utr.txt", b"UTR proof"))
		self.assertEqual(frappe.db.get_value("Payment Entry", pe, "reference_no"), "Proof attached: utr.txt")
		self.assertTrue(frappe.db.exists("File", {"attached_to_doctype": "Payment Entry", "attached_to_name": pe}))
		self.assertEqual(frappe.db.get_value("Purchase Invoice", made["name"], "status"), "Paid")
		with self.assertRaises(frappe.ValidationError):
			supplier_bill.mark_paid(self.job, made["name"], frappe.as_json(self.paid(reference_no="X")))
		frappe.db.rollback()

	def test_an_employee_paid_bill_is_paid_from_reimbursement_and_claimed(self):
		if not supplier_bill.reimbursement_account(self.inst.company):
			raise unittest.SkipTest("The company has no Employee Reimbursement account.")
		made = supplier_bill.create(self.job, frappe.as_json(self.data()))
		with self.assertRaises(frappe.ValidationError):  # who paid it, and how much
			supplier_bill.mark_paid(self.job, made["name"], frappe.as_json(self.paid(account="Reimbursement", reference_no="R1")))
		s = supplier_bill.mark_paid(self.job, made["name"], frappe.as_json(self.paid(account="Reimbursement", reference_no="R1",
			claimant="Administrator", amount=10000)))
		bill = next(b for b in s["bills"] if b["name"] == made["name"])
		self.assertEqual((bill["status"], bill["outstanding"]), ("Partly Paid", 40396 - 10000))
		pay = bill["payments"][0]
		self.assertEqual(frappe.db.get_value("Payment Entry", pay["name"], "paid_from"), supplier_bill.reimbursement_account(self.inst.company))
		claim = frappe.get_doc("Expense Reimbursement", pay["claim"]["name"])
		self.assertEqual((claim.claimant, claim.amount, claim.status, claim.source_document), ("Administrator", 10000, "Pending Approval", made["name"]))
		with self.assertRaises(frappe.ValidationError):  # more than is due
			supplier_bill.mark_paid(self.job, made["name"], frappe.as_json(self.paid(account="Reimbursement", reference_no="R2",
				claimant="Administrator", amount=40000)))

	def test_the_material_statement_adds_up_every_suppliers_bill(self):
		first = supplier_bill.create(self.job, frappe.as_json(self.data(payment=self.paid(reference_no="UTR-STMT"))))
		self.ensure("SECOND TEST SUPPLIERS", "32CCCCC3333C3Z3")
		other = self.data(supplier_name="SECOND TEST SUPPLIERS", supplier_gstin="32CCCCC3333C3Z3", bill_no="SECOND/0001")
		second = supplier_bill.create(self.job, frappe.as_json(other))
		s = supplier_bill.statement(self.job)
		ours = [b for b in s["bills"] if b["invoice"] in (first["name"], second["name"])]
		self.assertEqual(len(ours), 2)
		self.assertEqual(len({b["supplier"] for b in ours}), 2)
		# Each bill 40,396 (38,200 taxable + 2,196 GST); the whole adds them up.
		self.assertEqual([b["total"] for b in ours], [40396, 40396])
		self.assertEqual(s["total"], flt(sum(b["total"] for b in s["bills"]), 2))
		self.assertEqual(s["paid"] + s["due"], s["total"])
		by_rate = {slab["rate"]: slab for slab in s["slabs"]}
		self.assertEqual(flt(sum(slab["tax"] for slab in s["slabs"]), 2), s["tax"])
		self.assertIn(5, by_rate)
		self.assertIn(18, by_rate)
		self.assertTrue(supplier_bill.render_statement(self.job).startswith(b"%PDF"))

	def bill_from(self, name, gstin, bill_no, **extra):
		self.ensure(name, gstin)
		return supplier_bill.create(self.job, frappe.as_json(self.data(supplier_name=name, supplier_gstin=gstin, bill_no=bill_no, **extra)))["name"]

	def test_a_bill_goes_to_the_supplier_its_gstin_names(self):
		first = self.bill_from("SAME NAME TRADERS", "32DDDDD4444D4Z4", "SN-1")
		other = self.bill_from("SAME NAME TRADERS", "32EEEEE5555E5Z5", "SN-2")  # same name, another GSTIN: another firm
		a, b = (frappe.db.get_value("Purchase Invoice", n, "supplier") for n in (first, other))
		self.assertNotEqual(a, b)
		self.assertEqual(frappe.db.get_value("Supplier", b, "tax_id"), "32EEEEE5555E5Z5")
		again = self.bill_from("SAME NAME TRADERS", "32DDDDD4444D4Z4", "SN-3")
		self.assertEqual(frappe.db.get_value("Purchase Invoice", again, "supplier"), a)

	def test_a_supplier_known_by_name_alone_takes_the_bills_gstin(self):
		frappe.get_doc({"doctype": "Supplier", "supplier_name": "NAME ONLY SUPPLIES", "supplier_group": "All Supplier Groups"}).insert()
		made = self.bill_from("NAME ONLY SUPPLIES", "32FFFFF6666F6Z6", "NO-1")
		self.assertEqual(frappe.db.get_value("Purchase Invoice", made, "supplier"), "NAME ONLY SUPPLIES")
		self.assertEqual(frappe.db.get_value("Supplier", "NAME ONLY SUPPLIES", "tax_id"), "32FFFFF6666F6Z6")

	def test_each_supplier_is_listed_and_paid_on_its_own(self):
		a1 = self.bill_from("PAY ME FIRST", "32GGGGG7777G7Z7", "PA-1")
		a2 = self.bill_from("PAY ME FIRST", "32GGGGG7777G7Z7", "PA-2")
		b1 = self.bill_from("PAY ME LATER", "32HHHHH8888H8Z8", "PB-1")
		s = supplier_bill.state(self.job)
		card = {c["name"]: c for c in s["suppliers"]}
		self.assertEqual((len(card["PAY ME FIRST"]["bills"]), card["PAY ME FIRST"]["due"]), (2, 2 * 40396))
		self.assertEqual(card["PAY ME LATER"]["due"], 40396)
		supplier_bill.pay_supplier(self.job, card["PAY ME FIRST"]["supplier"], frappe.as_json(self.paid(reference_no="UTR-PA")))
		refs = frappe.get_all("Payment Entry Reference", {"reference_name": ["in", [a1, a2]], "docstatus": 1}, pluck="parent")
		self.assertEqual(len(refs), 2)
		self.assertEqual(len(set(refs)), 1)  # one payment to that supplier, for both its bills
		self.assertEqual(frappe.db.get_value("Purchase Invoice", b1, "status"), "Unpaid")  # the other supplier still owed
		by = {r["supplier"]: r for r in supplier_bill.statement(self.job)["by_supplier"]}
		self.assertEqual((by["PAY ME FIRST"]["due"], by["PAY ME LATER"]["due"]), (0, 40396))

	def test_a_bill_from_a_supplier_not_in_erpnext_waits_for_it(self):
		with self.assertRaises(frappe.ValidationError):
			supplier_bill.create(self.job, frappe.as_json(self.data(supplier_name="NOT YET A SUPPLIER", supplier_gstin="32JJJJJ1111J1Z1",
				bill_no="NY-1")))

	def test_a_supplier_is_made_from_its_invoice(self):
		details = dict(supplier_bill.supplier_details(RIM_BLOCK, {"supplier_name": "RIM TEST COPY", "supplier_gstin": "32KKKKK2222K2Z2"}),
			supplier_name="RIM TEST COPY", gstin="32KKKKK2222K2Z2")
		made = supplier_bill.create_supplier(self.job, frappe.as_json(details))
		sup = frappe.get_doc("Supplier", made["supplier"])
		self.assertEqual((sup.tax_id, sup.get("pan"), sup.get("gst_category")), ("32KKKKK2222K2Z2", "AAJCR8845G", "Registered Regular"))
		address = frappe.get_doc("Address", sup.supplier_primary_address)
		self.assertEqual((address.pincode, address.state, address.links[0].link_name), ("683571", "Kerala", sup.name))
		self.assertTrue(sup.supplier_primary_contact)
		self.assertEqual(frappe.db.get_value("Bank Account", {"party": sup.name}, ["bank", "bank_account_no", "branch_code"]),
			("ICICI BANK", "028905004141", "ICIC0000289"))
		self.assertTrue(supplier_bill.create_supplier(self.job, frappe.as_json(details))["existed"])  # not twice

	def test_a_suppliers_details_are_changed_in_erpnext(self):
		made = supplier_bill.create_supplier(self.job, frappe.as_json({"supplier_name": "EDIT ME TRADERS", "gstin": "32LLLLL3333L3Z3"}))
		profile = supplier_bill.supplier_profile(self.job, made["supplier"])
		self.assertEqual(profile["details"]["gstin"], "32LLLLL3333L3Z3")
		account = {"bank_name": "TEST BANK OF EDITS", "account_no": "111122223333", "ifsc": "TEST0001234", "account_holder": "EDIT ME TRADERS"}
		details = dict(profile["details"], address_line1="1 Main Road", city="Aluva", state="Kerala", pincode="683101",
			phone="9000000001", email="edit@example.com", bank_accounts=[account])
		after = supplier_bill.update_supplier(self.job, made["supplier"], frappe.as_json(details))["details"]
		self.assertEqual((after["city"], after["pincode"], after["phone"], after["bank_accounts"][0]["account_no"], after["bank_accounts"][0]["ifsc"]),
			("Aluva", "683101", "9000000001", "111122223333", "TEST0001234"))
		# A new IFSC changes the one account, never adds a second.
		changed = dict(after["bank_accounts"][0], ifsc="TEST0005678")
		after = supplier_bill.update_supplier(self.job, made["supplier"], frappe.as_json(dict(details, bank_accounts=[changed])))["details"]
		self.assertEqual(after["bank_accounts"][0]["ifsc"], "TEST0005678")
		self.assertEqual(frappe.db.count("Bank Account", {"party": made["supplier"]}), 1)
		with self.assertRaises(frappe.ValidationError):  # another supplier's GSTIN
			supplier_bill.update_supplier(self.job, made["supplier"], frappe.as_json(dict(details, gstin=self.bill["supplier_gstin"])))

	def test_a_supplier_keeps_several_bank_accounts_and_is_paid_into_one(self):
		sup = self.ensure("MANY BANKS TRADERS", "32MMMMM4444M4Z4")
		accounts = [{"bank_name": "TEST BANK ONE", "account_no": "111100001111", "ifsc": "TEST0000001", "is_default": 0},
			{"bank_name": "TEST BANK TWO", "account_no": "222200002222", "ifsc": "TEST0000002", "is_default": 1}]
		details = dict(supplier_bill.supplier_profile(self.job, sup)["details"], bank_accounts=accounts)
		after = supplier_bill.update_supplier(self.job, sup, frappe.as_json(details))["details"]["bank_accounts"]
		self.assertEqual([(a["account_no"], a["is_default"]) for a in after], [("222200002222", 1), ("111100001111", 0)])
		# The same account no. again is that account; an invoice's other account is added to the one supplier.
		supplier_bill.update_supplier(self.job, sup, frappe.as_json(dict(details, bank_accounts=accounts + [{"bank_name": "TEST BANK ONE", "account_no": "1111 0000 1111"}])))
		self.assertEqual(len(supplier_bill.bank_accounts(sup)), 2)
		added = supplier_bill.add_bank_account(self.job, sup, frappe.as_json({"bank_name": "TEST BANK THREE", "account_no": "333300003333"}))
		self.assertEqual(len(added["bank_accounts"]), 3)
		self.assertEqual(len(supplier_bill.add_bank_account(self.job, sup, frappe.as_json({"bank_name": "TEST BANK THREE", "account_no": "333300003333"}))["bank_accounts"]), 3)
		# Paid into the account chosen - only one of the supplier's own.
		made = self.bill_from("MANY BANKS TRADERS", "32MMMMM4444M4Z4", "MB-1")
		one = next(a["name"] for a in supplier_bill.bank_accounts(sup) if a["account_no"] == "111100001111")
		supplier_bill.mark_paid(self.job, made, frappe.as_json(self.paid(reference_no="UTR-MB", party_bank_account=one)))
		pe = frappe.get_all("Payment Entry Reference", {"reference_name": made, "docstatus": 1}, pluck="parent")[0]
		self.assertEqual(frappe.db.get_value("Payment Entry", pe, "party_bank_account"), one)
		with self.assertRaises(frappe.ValidationError):
			supplier_bill._party_account(sup, "Renewcore Receipts - RIL")

