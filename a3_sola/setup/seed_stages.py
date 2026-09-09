# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The thirty tasks of a rooftop job, transcribed from how the client actually works.

Not a chain. The old model ran twenty stages in a fixed order and would not let the next
one start until the previous one had its evidence; the client buys the stamp paper while the
portal registration is pending and pays the Form 1 fee whenever the section office is open.
So these are independent tasks: any of them can be done at any time, each is executed in the
document that represents it (`task_doctype`), and the installation records which document
did the work.

Tasks a job does not need are created as Skipped with the reason recorded rather than
omitted - an auditor asking why there is no inspectorate certificate sees the answer on the
record - and a skipped task can be un-skipped the moment somebody opens a document for it.

Every task lists the documents it is expected to produce. Those become rows in the
installation's document register; nothing gates on them any more.
"""

#: Roles that own tasks by default. The assignee is prefilled from the first holder.
OPS = "Solar Operations Executive"
DOCS = "Solar Documentation Officer"
SITE = "Solar Site Engineer"
LIAISON = "Solar Liaison Officer"


def _task(code, name, owner_type, sla_days, task_doctype, *, role=OPS, is_mandatory=1,
          applicability="Always", threshold_kw=0, task_type=None, due_anchor_task=None,
          due_anchor_days=0, documents=(), description=""):
	return {
		"code": code,
		"name": name,
		"owner_type": owner_type,
		"sla_days": sla_days,
		"task_doctype": task_doctype,
		"task_type": task_type,
		"default_assignee_role": role,
		"is_mandatory": is_mandatory,
		"applicability": applicability,
		"threshold_kw": threshold_kw,
		"due_anchor_task": due_anchor_task,
		"due_anchor_days": due_anchor_days,
		"documents": list(documents),
		"description": description,
	}


TASKS = [
	_task("ORD", "Order Received", "Internal", 1, "Sales Order",
	      documents=[("Signed consumer-vendor agreement", 1, "MNRE-CONSUMER-VENDOR-AGREEMENT"),
	                 ("Customer KYC documents", 1, None), ("Sales order", 0, None)],
	      description="The sales order is submitted and the job opens. KYC documents are fetched "
	                  "from the consumer record onto the order."),
	_task("FRM1", "Form 1 Generation", "Internal", 2, "Installation Task", role=DOCS,
	      task_type="FRM1", documents=[("Annexure / Form 1", 1, "KSEB-FORM-1")],
	      description="KSEBL Form 1 generated and submitted to the section office."),
	_task("F1PAY", "Form 1 Payment", "Internal", 2, "Statutory Fee Payment",
	      task_type="Application Fee", documents=[("Application fee receipt", 1, None)],
	      description="Application fee paid. Paying it starts the thirty-day window for Form 2."),
	_task("NPA", "PM Surya Ghar Portal Registration", "Internal", 3, "Portal Application", role=DOCS,
	      applicability="Subsidised Only", task_type="National Portal",
	      documents=[("National portal application data sheet", 1, "NP-APPLICATION"),
	                 ("Portal acknowledgement", 1, None)],
	      description="Consumer registered on the national portal; application id recorded."),
	_task("LOAN", "Loan Documents", "Bank", 15, "Loan Application", role=DOCS,
	      applicability="Financed Sales Only",
	      documents=[("Bank covering letter - loan application", 1, "BANK-COVERING-LOAN"),
	                 ("Vendor feasibility report", 1, "BANK-VENDOR-FEASIBILITY"),
	                 ("EHS guidance checklist", 1, "BANK-EHS-CHECKLIST"),
	                 ("Project proposal", 0, None), ("Sanction letter", 1, None)],
	      description="Covering letter, feasibility report and proposal sent to the lender; "
	                  "sanction recorded."),
	_task("ADV", "Advance Payment", "Customer", 5, "Installation Task", task_type="ADV",
	      documents=[("Advance receipt or bank advice", 0, None)],
	      description="Advance received - from the customer, or from the bank once the loan "
	                  "is sanctioned."),
	_task("STMP", "Stamp Paper Purchase", "Internal", 3, "Solar Agreement",
	      documents=[("Stamp paper data sheet", 0, "STAMP-PAPER-DATA"), ("Stamp paper scan", 0, None)],
	      description="Stamp paper bought for the net-metering agreement; serial and value recorded."),
	_task("DSGN", "Design Freeze", "Internal", 3, "Installation Task", role=SITE, task_type="DSGN",
	      documents=[("Bill of materials", 1, "BOM-SUMMARY"), ("Approved single line diagram", 0, None),
	                 ("Structure drawing", 0, None)],
	      description="Bill of materials verified and frozen; BOM issued as PDF."),
	_task("IWOS", "Work Order - Structure", "Internal", 5, "Installation Work Order", role=SITE,
	      task_type="Structure", documents=[("Structure photographs", 0, None)],
	      description="Structure erection ordered to employees or a contractor."),
	_task("PROC", "Material Procurement", "Internal", 7, "Purchase Order",
	      documents=[("Purchase order", 0, None), ("Purchase receipt", 0, None)],
	      description="Purchase order raised from the bill of materials, delivered to the site "
	                  "location captured at survey."),
	_task("DISP", "Material Dispatch", "Internal", 2, "Delivery Note",
	      documents=[("Delivery note", 0, None), ("Serial manifest", 0, None)],
	      description="Materials dispatched to the customer site with serial numbers recorded."),
	_task("MATL", "Serials to Electrical Contractor", "Internal", 1, "Material Dispatch Notice",
	      is_mandatory=0, documents=[("Completion report data sheet", 1, "COMPLETION-REPORT-DATA")],
	      description="Material and serial details mailed to the electrical contractor in the "
	                  "completion-report format."),
	_task("CCERT", "Completion Certificate from Contractor", "Contractor", 5, "Installation Task",
	      role=SITE, task_type="CCERT", documents=[("Completion certificate", 1, None)],
	      description="Completion certificate received from the electrical contractor."),
	_task("IWOI", "Work Order - Installation", "Internal", 5, "Installation Work Order", role=SITE,
	      task_type="Installation", documents=[("Geo-tagged installation photographs", 1, None)],
	      description="Installation ordered and executed; photographs carry GPS coordinates."),
	_task("PORTUPD", "Installation Update on Portal", "Internal", 2, "Installation Task", role=DOCS,
	      applicability="Subsidised Only", task_type="PORTUPD",
	      documents=[("DCR certificate", 1, None), ("Portal acknowledgement", 0, None)],
	      description="Installation details updated on the national portal with the DCR document."),
	_task("CEIG", "Inspectorate Approval", "Inspectorate", 15, "Portal Application", role=LIAISON,
	      applicability="Above Capacity Threshold", threshold_kw=10,
	      task_type="Electrical Inspectorate",
	      documents=[("Electrical inspectorate certificate", 1, None)],
	      description="Chief Electrical Inspectorate approval, where the capacity requires one."),
	_task("KFORMS", "Form 2 & 3 Submission", "Internal", 3, "Document Pack", role=DOCS,
	      task_type="KSEB Submission", due_anchor_task="F1PAY", due_anchor_days=30,
	      documents=[("Net metering agreement", 1, "KSEB-NETMETER-AGREEMENT"),
	                 ("Annexure / Form 2", 1, "KSEB-FORM-2"), ("Annexure / Form 3", 1, "KSEB-FORM-3"),
	                 ("Covering letter to the Assistant Engineer", 1, "KSEB-COVERING-COMPLETION"),
	                 ("Request for allocation of bidirectional meter", 1, "KSEB-NETMETER-REQUEST"),
	                 ("Installation and inverter testing checklist", 1, "KSEB-TESTING-CHECKLIST"),
	                 ("AE acknowledged Form 2", 0, None), ("AE acknowledged Form 3", 0, None)],
	      description="Agreement, Forms 2 and 3, covering letters and checklist generated and "
	                  "submitted to the section office within thirty days of the Form 1 fee."),
	_task("F2PAY", "Form 2 Payment", "Internal", 2, "Statutory Fee Payment",
	      task_type="Registration Fee", documents=[("Registration fee receipt", 1, None)],
	      description="Registration fee paid; eighty percent of the base is refundable later."),
	_task("COMM", "Commissioning", "DISCOM", 10, "Commissioning Report", role=SITE,
	      documents=[("Commissioning certificate", 1, None),
	                 ("Commissioning certificate (customer)", 0, "CUST-COMMISSIONING-CERTIFICATE"),
	                 ("Customer handover pack", 0, "CUST-HANDOVER-PACK")],
	      description="Plant commissioned; certificate, net meter serial and readings recorded."),
	_task("KTST", "DISCOM Inspection & Pre-Energisation Test", "DISCOM", 10, "Installation Task",
	      role=LIAISON, task_type="KTST", documents=[("Signed testing checklist", 0, None)],
	      description="Section office inspects the installation and witnesses the protection tests."),
	_task("MTR", "Meter Purchase", "DISCOM", 7, "Installation Task", role=LIAISON,
	      applicability="Net Meter Purchased Only", task_type="MTR",
	      documents=[("Meter invoice or allocation record", 0, None), ("Meter test certificate", 0, None)],
	      description="Net meter bought from KSEB or a vendor; make and serial recorded."),
	_task("MTRPAY", "Meter Payment", "Internal", 2, "Statutory Fee Payment",
	      applicability="Net Meter Purchased Only", task_type="Net Meter Charge",
	      documents=[("Meter payment receipt", 1, None)],
	      description="Meter charge paid and the cost recorded against the job."),
	_task("BCOM", "Bank Completion Documents", "Bank", 5, "Document Pack", role=DOCS,
	      applicability="Financed Sales Only", task_type="Bank Completion Pack",
	      documents=[("Project completion report (bank)", 1, "BANK-COMPLETION-REPORT"),
	                 ("Bank covering letter - balance transfer", 1, "BANK-COVERING-COMPLETION"),
	                 ("Consumer-vendor agreement", 0, "MNRE-CONSUMER-VENDOR-AGREEMENT"),
	                 ("Completion report data sheet", 0, "COMPLETION-REPORT-DATA"),
	                 ("Geo-tagged photograph collage", 1, None), ("Invoice", 1, None)],
	      description="Completion report, covering letter, agreement and photo collage sent to the "
	                  "lender for the balance."),
	_task("BAL", "Balance Payment", "Customer", 7, "Installation Task", task_type="BAL",
	      documents=[("Balance receipt or bank advice", 0, None)],
	      description="Balance received from the customer or the bank."),
	_task("CFILE", "Completion File for Customer", "Internal", 3, "Document Pack", role=DOCS,
	      task_type="Customer Completion File",
	      documents=[("Quotation", 0, None), ("Work orders", 0, None),
	                 ("Customer account statement", 0, "CUSTOMER-STATEMENT"), ("Invoice", 0, None),
	                 ("Company warranty certificate", 1, "WARRANTY-CERTIFICATE"),
	                 ("Manufacturer warranty certificate - modules", 0, None),
	                 ("Manufacturer warranty certificate - inverter", 0, None),
	                 ("Escalation, service and sales contacts", 0, "CUSTOMER-CONTACTS"),
	                 ("Request for refund of registration fee", 0, "KSEB-REFUND-REQUEST")],
	      description="Everything the customer keeps: quotation, work orders, statement, invoice, "
	                  "warranties, contacts and the KSEB refund request."),
	_task("REVIEW", "Customer Review", "Customer", 7, "Customer Review", is_mandatory=0,
	      documents=[("Review photographs and videos", 0, None)],
	      description="The customer's review collected as text, photographs and video."),
	_task("SUBREQ", "Subsidy Request", "Government", 30, "Subsidy Claim", role=DOCS,
	      applicability="Subsidised Only",
	      documents=[("Project completion report (national portal)", 1, "NP-COMPLETION-REPORT"),
	                 ("Portal acknowledgement", 0, None), ("Customer bank confirmation", 0, None)],
	      description="Subsidy claimed on the portal after commissioning."),
	_task("CORR", "Rejection Correction", "Internal", 3, "Subsidy Claim", role=DOCS,
	      is_mandatory=0, applicability="Subsidised Only",
	      documents=[("Correction proof", 0, None)],
	      description="A rejected or queried claim corrected and resubmitted."),
	_task("DBT", "Subsidy Disbursement", "Government", 45, "Subsidy Claim", role=DOCS,
	      applicability="Subsidised Only", documents=[("Subsidy credit confirmation", 1, None)],
	      description="Direct benefit transfer confirmed to the consumer's account."),
	_task("GREV", "Google Review", "Customer", 7, "Customer Review", is_mandatory=0,
	      documents=[("Google review screenshot", 0, None)],
	      description="The customer asked to post a Google review; posted or declined recorded."),
]

TASK_CODES = [task["code"] for task in TASKS]

#: Every task up to and including commissioning, in seed order - what a demo job that is
#: "fully commissioned" has done. Tasks a particular job pre-skips simply stay skipped.
CODES_TO_COMMISSIONING = TASK_CODES[: TASK_CODES.index("COMM") + 1]

#: Task codes that share one executing document, keyed by the document that owns them. The
#: engine reads these to know that one Subsidy Claim answers for three task rows.
SHARED_DOCUMENT_CODES = {
	"Subsidy Claim": ("SUBREQ", "CORR", "DBT"),
	"Customer Review": ("REVIEW", "GREV"),
}


def by_code(code):
	for task in TASKS:
		if task["code"] == code:
			return task
	return None


def checklists():
	"""{code: (name, [(document, mandatory, template_code)])} for every task that produces documents.

	These are expectations for the document register, not gates: the engine no longer
	refuses to complete a task over a missing attachment.
	"""
	return {
		task["code"]: (task["name"], task["documents"])
		for task in TASKS
		if task["documents"]
	}
