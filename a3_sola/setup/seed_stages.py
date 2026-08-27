# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The stage chain, transcribed from the client's actual paper trail.

Nineteen stages, not a generic twelve. Five are controlled by external parties the company
cannot chase directly, and that is exactly where working capital is trapped.

Conditional stages are created as Skipped with their reason recorded rather than omitted,
so an auditor asking why there is no inspectorate certificate sees the answer on the record.
"""

#: code, name, owner, sla_days, mandatory, applicability, threshold, checklist, description
RESIDENTIAL_CHAIN = [
	("ORD", "Order Received", "Internal", 2, 1, "Always", 0,
	 "Signed consumer-vendor agreement under the scheme"),
	("NPA", "National Portal Application", "Internal", 3, 1, "Always", 0,
	 "Application filed on the national portal; acknowledgement received"),
	("FEAS", "Feasibility Approval", "DISCOM", 45, 1, "Always", 0,
	 "Technical feasibility approval from the DISCOM section office"),
	("VFR", "Vendor Feasibility Report to Lender", "Internal", 3, 1, "Financed Sales Only", 0,
	 "Signed vendor feasibility report and EHS checklist for the bank"),
	("LOAN", "Loan Sanction & Advance", "Bank", 15, 1, "Financed Sales Only", 0,
	 "Sanction number recorded and the advance tranche credited"),
	("DSGN", "Design Freeze", "Internal", 5, 1, "Always", 0,
	 "Approved single line diagram and structure drawing"),
	("PROC", "Material Procurement", "Internal", 10, 1, "Always", 0, "Purchase receipt"),
	("DISP", "Material Dispatch", "Internal", 3, 1, "Always", 0, "Delivery note and serial manifest"),
	("INST", "Installation", "Internal", 5, 1, "Always", 0, "Completion log and photographs"),
	("CEIG", "Inspectorate Approval", "Inspectorate", 15, 1, "Above Capacity Threshold", 10,
	 "Chief Electrical Inspectorate certificate, where the capacity requires one"),
	("KREG", "DISCOM Registration Fee Paid", "Internal", 2, 1, "Always", 0, "Registration fee receipt"),
	("NMTR", "Net Meter Request & Allocation", "DISCOM", 21, 1, "Always", 0,
	 "Request letter filed; meter allocated or procured"),
	("KTST", "DISCOM Inspection & Pre-Energisation Test", "DISCOM", 10, 1, "Always", 0,
	 "Signed testing checklist with the inverter protection settings"),
	("AGMT", "Net Metering Agreement Executed", "Internal", 5, 1, "Always", 0,
	 "Agreement on stamp paper with SPIN and the full schedule"),
	("COMM", "Commissioning", "DISCOM", 10, 1, "Always", 0,
	 "Commissioning certificate, net meter serial and date"),
	("BCOM", "Completion Report to Lender", "Internal", 3, 1, "Financed Sales Only", 0,
	 "Completion report, photographs and invoice; balance requested"),
	("PCR", "PCR Upload", "Internal", 3, 1, "Subsidised Only", 0,
	 "Project completion report acknowledged on the national portal"),
	("DBT", "Subsidy Disbursed", "Government", 45, 1, "Subsidised Only", 0,
	 "Direct benefit transfer confirmed to the consumer's account"),
	("RFND", "Registration Fee Refund", "DISCOM", 45, 0, "Always", 0,
	 "80% of the registration base credited"),
]

COMMERCIAL_CHAIN = [
	code
	for code in (
		"ORD", "DSGN", "PROC", "DISP", "INST", "CEIG", "KREG", "NMTR", "KTST", "AGMT", "COMM", "RFND"
	)
]

#: stage code -> (checklist template name, [(document, mandatory, generated_template_code)])
CHECKLISTS = {
	"ORD": ("Order Received", [
		("Signed consumer-vendor agreement", 1, "MNRE-CONSUMER-VENDOR-AGREEMENT"),
		("Customer purchase order", 0, None),
	]),
	"NPA": ("National Portal Application", [
		("National portal application data sheet", 1, "NP-APPLICATION"),
		("Portal acknowledgement", 1, None),
	]),
	"FEAS": ("Feasibility Approval", [("Feasibility approval letter", 1, None)]),
	"VFR": ("Vendor Feasibility Report", [
		("Residential rooftop solar vendor feasibility report", 1, "BANK-VENDOR-FEASIBILITY"),
		("EHS guidance checklist", 1, "BANK-EHS-CHECKLIST"),
	]),
	"LOAN": ("Loan Sanction", [
		("Bank covering letter - loan application", 1, "BANK-COVERING-LOAN"),
		("Sanction letter", 1, None),
		("Advance credit advice", 1, None),
	]),
	"DSGN": ("Design Freeze", [
		("Approved single line diagram", 1, None),
		("Structure drawing", 1, None),
	]),
	"PROC": ("Material Procurement", [("Purchase receipt", 1, None)]),
	"DISP": ("Material Dispatch", [
		("Delivery note", 1, None),
		("Serial manifest", 1, None),
	]),
	"INST": ("Installation", [
		("Installation photographs", 1, None),
		("Completion log", 1, None),
	]),
	"CEIG": ("Inspectorate Approval", [("Electrical inspectorate certificate", 1, None)]),
	"KREG": ("Registration Fee", [("Registration fee receipt", 1, None)]),
	"NMTR": ("Net Meter Request", [
		("Request for allocation of bidirectional meter", 1, "KSEB-NETMETER-REQUEST"),
		("Meter allocation record or purchase invoice", 1, None),
	]),
	"KTST": ("DISCOM Inspection", [
		("Installation and inverter testing checklist", 1, "KSEB-TESTING-CHECKLIST"),
		("Covering letter to the Assistant Engineer", 1, "KSEB-COVERING-COMPLETION"),
		("Annexure / Form 1", 1, "KSEB-FORM-1"),
		("Annexure / Form 2", 1, "KSEB-FORM-2"),
		("Annexure / Form 3", 1, "KSEB-FORM-3"),
	]),
	"AGMT": ("Net Metering Agreement", [
		("Net metering agreement on stamp paper", 1, "KSEB-NETMETER-AGREEMENT"),
		("Solar meter calibration certificate", 1, None),
	]),
	"COMM": ("Commissioning", [
		("Commissioning certificate", 1, None),
		("Customer handover pack", 0, "CUST-HANDOVER-PACK"),
	]),
	"BCOM": ("Completion Report to Lender", [
		("Project completion report", 1, "BANK-COMPLETION-REPORT"),
		("Bank covering letter - balance transfer", 1, "BANK-COVERING-COMPLETION"),
		("Installation photographs", 1, None),
		("Invoice", 1, None),
	]),
	"PCR": ("PCR Upload", [
		("Project completion report (national portal)", 1, "NP-COMPLETION-REPORT"),
		("Portal acknowledgement", 1, None),
	]),
	"DBT": ("Subsidy Disbursement", [("Subsidy credit confirmation", 1, None)]),
	"RFND": ("Registration Fee Refund", [
		("Request for refund of registration fee", 1, "KSEB-REFUND-REQUEST"),
		("Cancelled cheque", 1, None),
	]),
}
