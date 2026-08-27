# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Document templates, transcribed from the client's live forms.

Each carries a SOURCE note naming the document it reproduces, so a reviewer can diff them.
Wording is theirs; only the values are placeholders. Do not paraphrase when editing - these
are read at a counter by someone comparing them to a form they know.

Every value comes from `a3_sola.api.documents.get_document_context`, so the consumer number
on the bank letter and the consumer number on the DISCOM annexure cannot differ.
"""

# Shared fragments -------------------------------------------------------------
_LETTERHEAD = """<div style="text-align:right">{{ today }}</div>
<p>To,<br>
The Assistant Engineer,<br>
{{ discom_name }} Section,<br>
{{ section.section_name if section else "" }}</p>
<p>Sir,</p>"""

_SIGNOFF = """<p>Thanking You</p>
<p>Yours Faithfully</p>
<p><strong>{{ consumer.consumer_name }}</strong><br>{{ installation.consumer_number }}</p>"""

_EPC_SIGNOFF = """<p>Thanks &amp; Regards</p>
<p>For <strong>{{ company.registered_vendor_name or company.company_name }}</strong></p>
<p>{{ company.epc_authorised_signatory or "" }}<br>
{{ company.epc_signatory_designation or "Authorised Signatory" }}</p>"""

_EPC_BANK_BLOCK = """<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="35%"><strong>EPC Contractor Name &amp; Address:</strong></td>
      <td>{{ company.epc_name }},<br>{{ company.epc_address }}</td></tr>
  <tr><td><strong>A/c No:</strong></td><td>{{ company.payee_bank_account_no }}</td></tr>
  <tr><td><strong>Bank:</strong></td><td>{{ company.payee_bank_name }}</td></tr>
  <tr><td><strong>IFSC Code:</strong></td><td>{{ company.payee_bank_ifsc }}</td></tr>
</table>"""

TEMPLATES = [
	# ------------------------------------------------------------------ MNRE
	{
		"template_code": "MNRE-CONSUMER-VENDOR-AGREEMENT",
		"document_name": "Consumer-Vendor Agreement (PM Surya Ghar)",
		"category": "MNRE",
		"recipient": "Consumer",
		"stage_code": "ORD",
		"signatory": "Both",
		"notes": "SOURCE: 05_PMSGY Vendor Agreement.docx",
		"attachment_checklist": "",
		"body": """<h3 style="text-align:center">Agreement between Consumer &amp; Vendor for installation of grid connected
rooftop solar (RTS) project under PM &ndash; Surya Ghar: Muft Bijli Yojana</h3>
<p>This agreement is executed on {{ today }} for design, supply, installation, commissioning and
5-year comprehensive maintenance of the RTS project along with warranty under PM Surya Ghar:
Muft Bijli Yojana.</p>
<p><strong>Between</strong><br>
{{ consumer.consumer_name }} (Consumer), having address at {{ address_text }},
hereinafter referred to as the First Party</p>
<p><strong>And</strong><br>
{{ company.registered_vendor_name or company.company_name }} (Vendor) having its registered office at
{{ company.registered_vendor_address or company.epc_address }}, hereinafter referred to as the Second Party</p>

<p><strong>The First Party hereby undertakes to:</strong></p>
<ol>
<li>Submit the online application on the National Portal for the RTS project, apply for net metering
and system inspection, and upload the relevant documents.</li>
<li>Provide secure storage for the material delivered at the premises until handover.</li>
<li>Provide access to the rooftop during installation, operation and maintenance, testing, and for
meter reading from the solar meter and inverter.</li>
<li>Provide electricity during installation and water for cleaning the panels.</li>
<li>Report any malfunction of the plant to the Vendor during the warranty period.</li>
<li>Pay as per the payment schedule mutually agreed, including any additional amount for
customisation required by the building condition.</li>
</ol>

<p><strong>The Second Party hereby undertakes to:</strong></p>
<ol>
<li>Follow all standards and safety guidelines prescribed under state regulations and the technical
standards prescribed by MNRE, failing which the vendor is liable for blacklisting and other penal
action in accordance with the law.</li>
<li><strong>Site survey:</strong> site visit, survey and a detailed project report, including feasibility of
the roof, roof strength and shadow-free area.</li>
<li><strong>Design &amp; engineering:</strong> design of the plant with drawings and selection of components as
per the standards of the DISCOM, SERC and MNRE.</li>
<li><strong>Module and inverter:</strong> the solar modules, including the cells, shall be manufactured in
India. Modules and inverters shall conform to the relevant MNRE standards and specifications.</li>
<li><strong>Procurement &amp; supply:</strong> the complete system as per BIS/IS/IEC standards and the safety
guidelines for rooftop solar installations.</li>
<li><strong>Installation &amp; civil work:</strong> complete civil, structure and electrical work following all
safety and relevant BIS standards.</li>
<li><strong>Documentation:</strong> technical catalogues, warranty certificates, BIS certificates, serial
numbers, layout and electrical SLD, structure design and drawings.</li>
<li><strong>Project completion report:</strong> assisting the consumer in filing and uploading the signed
documents on the national portal.</li>
<li><strong>Warranty:</strong> the complete system shall be warranted for 5 years from the date of
commissioning by the DISCOM.</li>
<li><strong>Net meter &amp; grid connectivity:</strong> net meter supply, testing and approvals, and grid
connection of the plant, are in the scope of the vendor.</li>
<li><strong>Testing and commissioning:</strong> the vendor shall be present at the time of testing and
commissioning by the DISCOM.</li>
<li><strong>Operation &amp; maintenance:</strong> five years of comprehensive operation and maintenance,
including overhauling, wear and tear and regular health checks at proper intervals. The vendor
shall educate the consumer on best practice for cleaning the modules.</li>
<li><strong>Project cost and payment terms:</strong> the cost of the system shall be
{{ fmt_money(installation.gross_contract_value) }} plus DISCOM charges and net meter charges.</li>
<li><strong>Performance of plant:</strong> the Performance Ratio of the plant must be 75% at the time of
commissioning by the DISCOM or its authorised agency. The vendor must provide, on a returnable
basis, a radiation sensor with a valid calibration certificate from a NABL or international
laboratory at the time of commissioning. The vendor must maintain the PR of the plant until the
end of the warranty, i.e. 5 years from the date of commissioning.</li>
</ol>

<table border="1" cellpadding="6" cellspacing="0" width="100%">
  <tr><th></th><th>First Party</th><th>Second Party</th></tr>
  <tr><td>Signature</td><td height="50"></td><td></td></tr>
  <tr><td>Name</td><td>{{ consumer.consumer_name }}</td>
      <td>{{ company.registered_vendor_name or company.company_name }}</td></tr>
  <tr><td>Address</td><td>{{ address_text }}</td>
      <td>{{ company.registered_vendor_address or company.epc_address }}</td></tr>
  <tr><td>Date</td><td>{{ today }}</td><td>{{ today }}</td></tr>
</table>""",
	},
	{
		"template_code": "NP-APPLICATION",
		"document_name": "National Portal Application Data Sheet",
		"category": "National Portal",
		"recipient": "National Portal",
		"stage_code": "NPA",
		"notes": "Data sheet for keying into pmsuryaghar.gov.in. Never automate the portal.",
		"body": """<h3>National Portal Application &ndash; Data Sheet</h3>
<p class="text-muted">Prepared for manual submission. Do not automate the portal.</p>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="40%">Name of the Consumer</td><td>{{ consumer.consumer_name }}</td></tr>
  <tr><td>DISCOM Consumer ID</td><td>{{ installation.consumer_number }}</td></tr>
  <tr><td>DISCOM ID</td><td>{{ installation.discom_id or "" }}</td></tr>
  <tr><td>DISCOM</td><td>{{ discom_name }}</td></tr>
  <tr><td>Electrical Section</td><td>{{ section.section_name if section else "" }}</td></tr>
  <tr><td>Address for Installation</td><td>{{ address_text }}</td></tr>
  <tr><td>District</td><td>{{ section.district if section else "" }}</td></tr>
  <tr><td>State</td><td>Kerala</td></tr>
  <tr><td>Consumer Category</td><td>{{ consumer.consumer_category }}</td></tr>
  <tr><td>Connection Type</td><td>{{ consumer.connection_type }}</td></tr>
  <tr><td>Sanctioned Load</td><td>{{ consumer.sanctioned_load_kw }} kW</td></tr>
  <tr><td>RTS Capacity Applied</td><td>{{ installation.capacity_kw }} kW</td></tr>
  <tr><td>Registered Vendor</td><td>{{ company.registered_vendor_name }}</td></tr>
  <tr><td>Vendor Registration No</td><td>{{ company.mnre_vendor_registration_no or "" }}</td></tr>
  <tr><td>Consumer Bank Account</td><td>{{ consumer.bank_account_no or "" }}</td></tr>
  <tr><td>IFSC</td><td>{{ consumer.bank_ifsc_code or "" }}</td></tr>
</table>""",
	},
	{
		"template_code": "NP-COMPLETION-REPORT",
		"document_name": "Project Completion Report (National Portal)",
		"category": "National Portal",
		"recipient": "National Portal",
		"stage_code": "PCR",
		"signatory": "Both",
		"notes": "SOURCE: the PCR data the client uploads after commissioning.",
		"body": """<h3 style="text-align:center">Project Completion Report</h3>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="40%">Consumer Name</td><td>{{ consumer.consumer_name }}</td></tr>
  <tr><td>Consumer Number</td><td>{{ installation.consumer_number }}</td></tr>
  <tr><td>Portal Application ID</td><td>{{ installation.national_portal_application_id or "" }}</td></tr>
  <tr><td>Installed Capacity</td><td>{{ installation.capacity_kw }} kWp</td></tr>
  <tr><td>Commissioning Date</td>
      <td>{{ frappe.utils.formatdate(commissioning.commissioning_date, "dd-MM-yyyy") if commissioning else "" }}</td></tr>
  <tr><td>Commissioning Certificate No</td><td>{{ commissioning.commissioning_certificate_no if commissioning else "" }}</td></tr>
  <tr><td>Net Meter Serial</td><td>{{ commissioning.net_meter_serial_no if commissioning else "" }}</td></tr>
  <tr><td>SPIN</td><td>{{ installation.spin or "" }}</td></tr>
  <tr><td>Performance Ratio at Commissioning</td>
      <td>{{ commissioning.performance_ratio_at_commissioning if commissioning else "" }}%</td></tr>
</table>
<h4>Module Serial Numbers</h4>
<p>{{ module_serials | join(", ") }}</p>
<h4>Inverter Serial Numbers</h4>
<p>{{ inverter_serials | join(", ") }}</p>
""" + _EPC_SIGNOFF,
	},
]

# ------------------------------------------------------------------------ bank
TEMPLATES += [
	{
		"template_code": "BANK-COVERING-LOAN",
		"document_name": "Bank Covering Letter - Loan Application",
		"category": "Bank",
		"recipient": "Bank Manager",
		"stage_code": "LOAN",
		"source_doctype": "Loan Application",
		"notes": "SOURCE: 01_Bank Covering Letter_Loan.docx",
		"attachment_checklist": "Vendor feasibility report\nEHS guidance checklist\nProject proposal\nCustomer KYC",
		"body": """<div style="text-align:right">{{ today }}</div>
<p>To,<br>The Manager,<br>{{ loan.lender if loan else "" }}, {{ loan.lender_branch if loan else "" }}</p>
<p><strong>Sub: Submission of documents towards Loan Application for Solar Power Plant.</strong></p>
<p>Dear Sir,</p>
<p>The documents towards the loan application of the following customer are submitted herewith.</p>
<ul>
  <li>Customer Name &ndash; {{ consumer.consumer_name }}</li>
  <li>Loan Sanction No. &ndash; {{ loan.loan_sanction_no if loan else "" }}</li>
  <li>Jan Samarth ID &ndash; {{ loan.jan_samarth_id if loan else "" }}</li>
  <li>{{ discom_name }} Consumer No. &ndash; {{ installation.consumer_number }}</li>
</ul>
<p>Please process the loan and transfer the amount to the following account of our EPC Company:</p>
""" + _EPC_BANK_BLOCK + """
<p>Please contact us at the below for any further clarification:</p>
<p>Mob &ndash; {{ company.epc_contact_no }}<br>E-mail &ndash; {{ company.epc_email }}</p>
""" + _EPC_SIGNOFF,
	},
	{
		"template_code": "BANK-VENDOR-FEASIBILITY",
		"document_name": "Residential Rooftop Solar Vendor Feasibility Report",
		"category": "Bank",
		"recipient": "Bank Manager",
		"stage_code": "VFR",
		"source_doctype": "Loan Application",
		"signatory": "Authorised Signatory",
		"requires_company_seal": 1,
		"notes": "SOURCE: 02_Vendor Feasiility Report.docx",
		"body": """<h3 style="text-align:center">Residential Roof Top Solar Installation<br>Vendor Feasibility Report</h3>
<ol>
  <li>Name of the Consumer: <strong>{{ consumer.consumer_name }}</strong></li>
  <li>Discom Consumer ID: {{ installation.consumer_number }}</li>
  <li>Discom ID: {{ installation.discom_id or "" }}</li>
  <li>PM Surya Shakti Portal ID: {{ installation.national_portal_application_id or "" }}</li>
  <li>Jan Samarth ID: {{ loan.jan_samarth_id if loan else "" }}</li>
  <li>Address for Installation: {{ address_text }}</li>
  <li>District of Installation: {{ section.district if section else "" }}</li>
  <li>State of Installation: Kerala</li>
  <li>Pin Code of Installation: {{ address.pincode if address else "" }}</li>
  <li>Name of the Bank Branch from where finance for SRT is sought:
      {{ loan.lender if loan else "" }}, {{ loan.lender_branch if loan else "" }}</li>
  <li>OEM Name: {{ company.registered_vendor_name }}</li>
  <li>EPC Contractor Name &amp; Address: {{ company.epc_name }}, {{ company.epc_address }}</li>
  <li>EPC Contractor Bank Details: {{ company.payee_bank_name }}, {{ company.payee_bank_branch }}<br>
      A/c No: {{ company.payee_bank_account_no }} &nbsp;&nbsp; IFSC Code: {{ company.payee_bank_ifsc }}</li>
  <li>RTS Capacity in KW applied: {{ loan.capacity_applied_kw if loan else installation.capacity_kw }} kW</li>
  <li>Actual RTS Capacity to be installed: {{ installation.capacity_kw }} kW</li>
  <li>Feasibility Report Status: <strong>{{ (loan.feasibility_status if loan else "FEASIBLE") | upper }}</strong></li>
  <li>Project Cost (all inclusive): {{ (loan.project_cost_all_inclusive if loan else installation.gross_contract_value) | int }}</li>
</ol>
<table width="100%"><tr>
  <td>Date: {{ today }}<br>Place: {{ section.district if section else "" }}</td>
  <td style="text-align:right">Signature of Authorized Person of Vendor with Stamp</td>
</tr></table>""",
	},
	{
		"template_code": "BANK-EHS-CHECKLIST",
		"document_name": "EHS Guidance Checklist",
		"category": "Bank",
		"recipient": "Bank Manager",
		"stage_code": "VFR",
		"signatory": "Authorised Signatory",
		"notes": "SOURCE: RTS Vendor Feasibility Report PG 2.docx. Rendered from the Phase 1 site survey.",
		"body": """<h4>Guidance Checklist and Consumer Education for verification of adequacy on Environmental,
Health, and Safety (EHS) requirements during appraisal and monitoring</h4>
<p class="text-muted">(Installation and Operation phases) of an individual rooftop solar project
funded under the Rooftop Solar Program for the Residential Sector.</p>
<p><strong>Consumer:</strong> {{ consumer.consumer_name }} &nbsp;|&nbsp;
<strong>Consumer No:</strong> {{ installation.consumer_number }} &nbsp;|&nbsp;
<strong>Capacity:</strong> {{ installation.capacity_kw }} kW</p>
{% for phase in ["Go/No-Go", "Proposal Appraisal", "Installation & Operation", "Installer Advisory"] %}
  {% set rows = ehs | selectattr("phase", "equalto", phase) | list %}
  {% if rows %}
  <h4>{{ phase }}</h4>
  <table border="1" cellpadding="5" cellspacing="0" width="100%">
    <tr><th width="6%">S. No.</th><th>EHS Requirement</th><th width="14%">Status</th><th width="22%">Remarks</th></tr>
    {% for row in rows %}
    <tr><td>{{ loop.index }}</td><td>{{ row.question }}</td>
        <td>{{ row.response or "" }}</td><td>{{ row.remarks or "" }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}
{% endfor %}
<p><strong>Overall EHS status:</strong> {{ survey.ehs_overall_status if survey else "" }}
{% if survey and survey.ehs_conditions %}&mdash; {{ survey.ehs_conditions }}{% endif %}</p>
<table width="100%"><tr>
  <td>Date: {{ today }}<br>Place: {{ section.district if section else "" }}</td>
  <td style="text-align:right">Signature of Authorized Person of Vendor with Stamp</td>
</tr></table>""",
	},
	{
		"template_code": "BANK-COMPLETION-REPORT",
		"document_name": "Project Completion Report (Bank)",
		"category": "Bank",
		"recipient": "Bank Manager",
		"stage_code": "BCOM",
		"signatory": "Authorised Signatory",
		"requires_company_seal": 1,
		"notes": "SOURCE: 03_Completion Report for Bank.docx and 06_DATA FOR COMPLETION REPORT.docx",
		"body": """<h3 style="text-align:center">PROJECT COMPLETION REPORT</h3>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><th colspan="4" style="background:#eee">Vendor Data</th></tr>
  <tr><td width="25%">Name of Vendor</td><td colspan="3">{{ company.registered_vendor_name }}</td></tr>
  <tr><td>Address</td><td colspan="3">{{ company.registered_vendor_address }}</td></tr>
  <tr><td>Contact No</td><td colspan="3">{{ company.registered_vendor_contact or company.epc_contact_no }}</td></tr>
  <tr><td>E-mail</td><td colspan="3">{{ company.registered_vendor_email or company.epc_email }}</td></tr>
  <tr><td>Name of the EPC</td><td colspan="3">{{ company.epc_name }}</td></tr>
  <tr><td>E-mail ID</td><td colspan="3">{{ company.epc_email }}</td></tr>

  <tr><th colspan="4" style="background:#eee">Customer Data</th></tr>
  <tr><td>Name of the Customer</td><td colspan="3">{{ consumer.consumer_name }}</td></tr>
  <tr><td>Address</td><td colspan="3">{{ address_text }}</td></tr>
  <tr><td>Contact Number</td><td colspan="3">{{ consumer.mobile_no or "" }}</td></tr>
  <tr><td>EB Consumer No.</td><td colspan="3">{{ installation.consumer_number }}</td></tr>
  <tr><td>Electrical Section Office</td><td colspan="3">{{ section.section_name if section else "" }}</td></tr>

  <tr><th colspan="4" style="background:#eee">Details of SPV Power Plant</th></tr>
  <tr><td>Installed Capacity:</td><td>{{ installation.capacity_kw }} kWp</td>
      <td width="20%">Make of PCU:</td>
      <td>{{ frappe.db.get_value("Component Make", installation.inverter_make, "make_name") or "" }}</td></tr>
  <tr><td>Type of SPV Plant:</td><td>{{ installation.system_type }}</td>
      <td>Type:</td><td>{{ installation.system_type }}</td></tr>
  <tr><td>Types of SPV Module:</td>
      <td>{{ package.module_specification if package else "" }}</td>
      <td>Capacity:</td><td>{{ installation.inverter_capacity_kw }} kW</td></tr>
  <tr><td>Make of SPV Modules:</td>
      <td>{{ frappe.db.get_value("Component Make", installation.module_make, "make_name") or "" }}</td>
      <td></td><td></td></tr>
  <tr><td>Rating of each module:</td><td>{{ installation.module_wattage | int }}</td><td></td><td></td></tr>
  <tr><td>No. of modules:</td><td>{{ installation.module_count }}</td><td></td><td></td></tr>
</table>
<h4>PV Module Serial Numbers</h4>
<p>{{ module_serials | join(", ") }}</p>
<h4>Inverter Serial Number</h4>
<p>{{ inverter_serials | join(", ") }}</p>
<table width="100%"><tr>
  <td>Sign and Seal of the Vendor</td>
  <td style="text-align:right">Date: {{ today }}</td>
</tr></table>""",
	},
	{
		"template_code": "BANK-COVERING-COMPLETION",
		"document_name": "Bank Covering Letter - Balance Transfer",
		"category": "Bank",
		"recipient": "Bank Manager",
		"stage_code": "BCOM",
		"source_doctype": "Loan Application",
		"notes": "SOURCE: 04_Bank Covering Letter_Completion.docx",
		"attachment_checklist": "Completion report\nInstallation pictures\nInvoice",
		"body": """<div style="text-align:right">{{ today }}</div>
<p>To,<br>The Manager,<br>{{ loan.lender if loan else "" }}, {{ loan.lender_branch if loan else "" }}</p>
<p><strong>Sub: Request for transfer of balance amount &ndash; Solar Loan under PM Surya Ghar Scheme reg.</strong></p>
<p>Dear Sir,</p>
<p>Further to receipt of the advance amount, we have completed the installation of the solar plant.
The completion report, installation pictures and invoice are submitted herewith.</p>
<ul>
  <li>Customer Name &ndash; {{ consumer.consumer_name }}</li>
  <li>Loan Sanction No. &ndash; {{ loan.loan_sanction_no if loan else "" }}</li>
  <li>{{ discom_name }} Consumer No. &ndash; {{ installation.consumer_number }}</li>
</ul>
<p>Please transfer the balance amount
{% if loan and loan.outstanding %}of {{ fmt_money(loan.outstanding) }}{% endif %}.</p>
<p>Please contact us at the below for any further clarification:</p>
<p>Mob &ndash; {{ company.epc_contact_no }}<br>E-mail &ndash; {{ company.epc_email }}</p>
""" + _EPC_SIGNOFF,
	},
]

# ------------------------------------------------------------------------ KSEB
TEMPLATES += [
	{
		"template_code": "KSEB-COVERING-COMPLETION",
		"document_name": "Covering Letter to the Assistant Engineer - Registration and Completion",
		"category": "KSEB",
		"recipient": "Assistant Engineer",
		"stage_code": "KTST",
		"signatory": "Consumer",
		"notes": "SOURCE: To The Asst. Engineer-Covering Letter.docx",
		"attachment_checklist": (
			"Annexure 2 signed\n"
			"Annexure 3 for completion along with the following attachments\n"
			"Panel datasheet and BIS certificate\n"
			"Inverter datasheet and BIS certificate\n"
			"Test cum completion certificate with single line diagram along with panel and inverter serial numbers\n"
			"Installation checklist\n"
			"Solar meter calibration certificate\n"
			"Solar agreement on stamp paper signed"
		),
		"body": _LETTERHEAD + """
<p><strong>Sub: Submission of Documents for Solar Plant Registration and Completion Report</strong></p>
<p>Further to obtaining feasibility for installation of a {{ installation.capacity_kw }} kWp solar plant
under service connection bearing Consumer No. {{ installation.consumer_number }} at my residence located at
{{ address_text }}, the plant installation has been completed.</p>
<p>The following documents are hereby submitted:</p>
<ol>
{% for line in (template.attachment_checklist or "").split("\n") %}{% if line.strip() %}
  <li>{{ line.strip() }}</li>
{% endif %}{% endfor %}
</ol>
<p>Please do the needful for commissioning of the solar plant.</p>
""" + _SIGNOFF,
	},
	{
		"template_code": "KSEB-NETMETER-REQUEST",
		"document_name": "Request for Allocation of Bidirectional Meter",
		"category": "KSEB",
		"recipient": "Assistant Engineer",
		"stage_code": "NMTR",
		"signatory": "Consumer",
		"notes": "SOURCE: To The Asst. Engineer-Net Meter.docx",
		"body": _LETTERHEAD + """
<p><strong>Sub: Request for allocation of Bi-directional Meter (Net-Meter) for Solar Plant</strong></p>
<p>I have a service connection bearing Consumer No. {{ installation.consumer_number }} under the category
{{ consumer.tariff_category or "" }} at my residence located at {{ address_text }}.</p>
<p>I am installing a {{ installation.capacity_kw }} kWp solar power plant and have procured the solar
energy meter on my own.</p>
<p>I hereby submit a request for allocation of a {{ consumer.connection_type }} bidirectional meter
(net meter) for this project.</p>
<p>Please do the needful.</p>
""" + _SIGNOFF,
	},
	{
		"template_code": "KSEB-REFUND-REQUEST",
		"document_name": "Request for Refund of Registration Fee",
		"category": "KSEB",
		"recipient": "Assistant Engineer",
		"stage_code": "RFND",
		"signatory": "Consumer",
		"notes": "SOURCE: To The Asst. Engineer_Refund.docx",
		"attachment_checklist": "Cancelled cheque",
		"body": _LETTERHEAD + """
<p><strong>Sub: Refund of Registration Fee paid for solar connectivity at consumer No.
{{ installation.consumer_number }} and addition of bank account to records.</strong></p>
<p>I had installed a {{ installation.capacity_kw }} kWp grid connected solar power plant at my building
located at {{ address_text }} under the service connection bearing consumer No.
{{ installation.consumer_number }}. The registration fee was paid and the plant was commissioned and
connected to the grid.</p>
<p>As per guidelines, 80% of the registration fee paid is refundable. Hence, it is hereby requested
to refund {{ fmt_money(installation.kseb_registration_refundable) }} to my bank account as below:</p>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="40%">Bank Account Number</td><td>{{ consumer.bank_account_no or "" }}</td></tr>
  <tr><td>Name of Account Holder</td><td>{{ consumer.bank_account_holder_name or consumer.consumer_name }}</td></tr>
  <tr><td>Bank</td><td>{{ consumer.bank_name or "" }}</td></tr>
  <tr><td>Branch</td><td>{{ consumer.bank_branch or "" }}</td></tr>
  <tr><td>IFSC Code</td><td>{{ consumer.bank_ifsc_code or "" }}</td></tr>
</table>
<p>Further, the amount towards settlement of annual excess banked units may also be credited to the
above-mentioned account.</p>
<p>A cancelled cheque is attached. Please do the needful.</p>
""" + _SIGNOFF,
	},
	{
		"template_code": "KSEB-FORM-1",
		"document_name": "Annexure / Form 1",
		"category": "KSEB",
		"recipient": "Assistant Engineer",
		"stage_code": "KTST",
		"signatory": "Consumer",
		"notes": "SOURCE: KSEBL Form 1.docx",
		"body": """<h4 style="text-align:center">Annexure 1</h4>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="6%">1</td><td width="34%">Consumer details</td>
      <td>{{ consumer.consumer_name }} / {{ installation.consumer_number }} /
          {{ consumer.tariff_category or "" }} / {{ address_text }} / {{ consumer.mobile_no or "" }}</td></tr>
  <tr><td>2</td><td>Electrical Section</td><td>{{ section.section_name if section else "" }}</td></tr>
  <tr><td>3</td><td>Sanctioned / connected load</td>
      <td>{{ consumer.sanctioned_load_kw }} kW / {{ consumer.connected_load_watts | int }} W</td></tr>
  <tr><td>4</td><td>Capacity of the solar plant</td><td>{{ installation.capacity_kw }} kWp</td></tr>
  <tr><td>5</td><td>Type of installation</td><td>Rooftop</td></tr>
  <tr><td>6</td><td>Date of application</td><td>{{ today }}</td></tr>
</table>
<p><strong>Panel</strong> &ndash; {{ frappe.db.get_value("Component Make", installation.module_make, "make_name") or "" }}
   {{ installation.module_wattage | int }}Wp &times; {{ installation.module_count }} Nos</p>
<p><strong>Inverter</strong> &ndash; {{ installation.inverter_capacity_kw }} kW {{ consumer.connection_type }}</p>
""" + _SIGNOFF,
	},
	{
		"template_code": "KSEB-FORM-2",
		"document_name": "Annexure / Form 2",
		"category": "KSEB",
		"recipient": "Assistant Engineer",
		"stage_code": "KTST",
		"signatory": "Consumer",
		"notes": "SOURCE: KSEBL Form 2.docx",
		"body": """<h4 style="text-align:center">Annexure 2</h4>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="6%">1</td><td width="44%">Consumer details</td>
      <td>{{ consumer.consumer_name }} / {{ installation.consumer_number }} /
          {{ consumer.tariff_category or "" }} / {{ address_text }} / {{ consumer.mobile_no or "" }}</td></tr>
  <tr><td>2</td><td>Capacity of the plant</td><td>{{ installation.capacity_kw }} kWp</td></tr>
  <tr><td>3</td><td>Installation completed</td><td>Yes</td></tr>
  <tr><td>4</td><td>Whether the plant is ready for testing</td><td>Yes</td></tr>
  <tr><td>5</td><td>Meter arrangement</td>
      <td>Solar Meter &ndash; Yes /
          Net Meter &ndash; {% if installation.net_meter_mode == "Availed from DISCOM on Rental" %}From the DISCOM (Request Attached){% else %}Procured by the consumer{% endif %}</td></tr>
  <tr><td>6</td><td>Earthing provided as per standards</td><td>Yes</td></tr>
  <tr><td>7</td><td>Date</td><td>{{ today }}</td></tr>
</table>
""" + _SIGNOFF,
	},
	{
		"template_code": "KSEB-FORM-3",
		"document_name": "Annexure / Form 3",
		"category": "KSEB",
		"recipient": "Assistant Engineer",
		"stage_code": "KTST",
		"signatory": "Consumer",
		"notes": "SOURCE: KSEBL Form 3.docx",
		"body": """<h4 style="text-align:center">Annexure 3 &ndash; Completion</h4>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="6%">1</td><td width="54%">Installation completed as per the approved scheme</td><td>Yes</td></tr>
  <tr><td>2</td><td>All wiring connections completed</td><td>Yes</td></tr>
  <tr><td>3</td><td>Earthing provided for the installation as per standards</td><td>Yes</td></tr>
  <tr><td>4</td><td>Inverter protection settings verified</td><td>Yes</td></tr>
  <tr><td>5</td><td>Completion certificate submitted to the electrical section</td><td>Yes</td></tr>
  <tr><td>6</td><td>Energisation approval obtained from the Electrical Inspector</td>
      <td>{{ commissioning.energisation_approval_from_ei if commissioning else "Not Applicable" }}</td></tr>
  <tr><td>7</td><td>Date</td><td>{{ today }}</td></tr>
</table>
""" + _SIGNOFF,
	},
	{
		"template_code": "KSEB-TESTING-CHECKLIST",
		"document_name": "Installation and Inverter Testing Checklist",
		"category": "KSEB",
		"recipient": "Assistant Engineer",
		"stage_code": "KTST",
		"source_doctype": "Commissioning Report",
		"signatory": "Consumer",
		"notes": "SOURCE: KSEB/CHECKLIST.xlsx - the form the Assistant Engineer inspects against.",
		"body": """<h4 style="text-align:center">DETAILS OF INSTALLATION &amp; CHECKLIST TO BE FURNISHED ALONG WITH
THE REQUEST FOR TESTING SOLAR INVERTERS</h4>
{% set c = commissioning %}
<table border="1" cellpadding="4" cellspacing="0" width="100%">
  <tr><td width="5%">1</td><td width="45%">NAME OF ELECTRICAL DIVISION &amp; SUB DIVISION</td>
      <td>{{ c.electrical_division if c else "" }} / {{ c.electrical_subdivision if c else "" }}</td></tr>
  <tr><td>2</td><td>NAME OF ELECTRICAL SECTION</td><td>{{ c.electrical_section if c else "" }}</td></tr>
  <tr><td>3</td><td>CONSUMER NO.</td><td>{{ installation.consumer_number }}</td></tr>
  <tr><td>4</td><td>TARIFF</td><td>{{ c.tariff_category if c else "" }}</td></tr>
  <tr><td>5</td><td>CONNECTED LOAD</td><td>{{ (c.connected_load_watts if c else 0) | int }} Watts</td></tr>
  <tr><td>6</td><td>NAME OF SOLAR PLANT OWNER</td><td>{{ c.plant_owner_name if c else consumer.consumer_name }}</td></tr>
  <tr><td>7</td><td>ADDRESS</td><td>{{ address_text }}</td></tr>
  <tr><td>8</td><td>EMAIL ID</td><td>{{ c.consumer_email if c else "" }}</td></tr>
  <tr><td>9</td><td>CONTACT PHONE NO. OF CONSUMER</td><td>{{ c.consumer_contact_no if c else "" }}</td></tr>
  <tr><td>10</td><td>ALTERNATE CONTACT NO.</td><td>{{ c.alternate_contact_no if c else "" }}</td></tr>
  <tr><td>11</td><td>BANK DETAILS &ndash; Bank / Account No. / IFSC</td>
      <td>{{ c.consumer_bank_name if c else "" }} / {{ c.consumer_bank_account_no if c else "" }} /
          {{ c.consumer_bank_ifsc if c else "" }}</td></tr>
  <tr><td>12</td><td>NAME &amp; ADDRESS OF SUPPLIER/INSTALLER</td>
      <td>{{ c.installer_name if c else "" }}, {{ c.installer_address if c else "" }}</td></tr>
  <tr><td>13</td><td>EMAIL ID</td><td>{{ c.installer_email if c else "" }}</td></tr>
  <tr><td>14</td><td>CONTACT PHONE NO. OF INSTALLER</td><td>{{ c.installer_contact_no if c else "" }}</td></tr>
</table>

<h4>PLANT DETAILS</h4>
<table border="1" cellpadding="4" cellspacing="0" width="100%">
  <tr><td width="5%">1</td><td width="45%">TYPE OF PLANT</td><td>{{ c.plant_type if c else "" }}</td></tr>
  <tr><td>2</td><td>TOTAL CAPACITY OF SOLAR PLANT</td><td>{{ c.total_capacity_kwp if c else "" }} KWp</td></tr>
  <tr><td></td><td>NUMBER OF PANELS</td><td>{{ c.module_count if c else "" }} NOS.</td></tr>
  <tr><td></td><td>INDIVIDUAL CAPACITY</td>
      <td>{{ (c.module_wattage if c else 0) | int }} Wp ({{ c.module_make if c else "" }})</td></tr>
  <tr><td>3</td><td>MAKE &amp; SERIAL NUMBER OF INVERTERS</td>
      <td>{{ c.inverter_make if c else "" }}, {{ c.inverter_serial_no if c else "" }}</td></tr>
  <tr><td></td><td>INVERTER TYPE SINGLE PHASE/THREE PHASE</td><td>{{ c.inverter_phase if c else "" }}</td></tr>
  <tr><td></td><td>INVERTER CAPACITY</td><td>{{ c.inverter_capacity_kw if c else "" }} KW</td></tr>
  <tr><td>4</td><td>DC INPUT VOLTAGE</td><td>{{ (c.dc_input_voltage if c else 0) | int }}</td></tr>
  <tr><td>5</td><td>NUMBER OF INVERTERS</td><td>{{ c.inverter_count if c else "" }}</td></tr>
  <tr><td>6</td><td>IF THE INVERTER IS OF HYBRID TYPE, WHETHER THE SCHEME CONFIRMS TO THE SCHEME
      APPROVED BY CE (REES)</td>
      <td>{% if c and c.plant_type == "Hybrid" %}{{ "YES" if c.hybrid_scheme_conforms_to_ce_rees else "NO" }}{% else %}NOT APPLICABLE{% endif %}</td></tr>
  <tr><td>7</td><td>WHETHER COMPLETION CERTIFICATE SUBMITTED IN ELE. SECTION</td>
      <td>{{ "YES" if c and c.completion_certificate_submitted_to_section else "NO" }}</td></tr>
  <tr><td>8</td><td>WHETHER ENERGISATION APPROVAL OBTAINED FROM ELE. INSPECTORATE</td>
      <td>{{ (c.energisation_approval_from_ei if c else "NOT APPLICABLE") | upper }}</td></tr>
  <tr><td>9</td><td>DETAILS OF ENERGISATION APPROVAL BY EI</td>
      <td>{{ c.energisation_approval_details if c else "" }}</td></tr>
  <tr><td>10</td><td>WHETHER DC ISOLATOR PROVIDED ON INCOMING SIDE OF INVERTER</td>
      <td>{{ "YES" if c and c.dc_isolator_on_inverter_incoming else "NO" }}</td></tr>
  <tr><td>11</td><td>WHETHER VISUAL ISOLATOR PROVIDED BEFORE CONNECTIVITY POINT</td>
      <td>{{ "YES" if c and c.visual_isolator_before_connectivity_point else "NO" }}</td></tr>
  <tr><td>12</td><td>WHETHER ALL WIRING CONNECTIONS AS PER THE APPROVED SCHEME ARE COMPLETED</td>
      <td>{{ "YES" if c and c.wiring_as_per_approved_scheme else "NO" }}</td></tr>
  <tr><td>13</td><td>WHETHER EARTHING PROVIDED FOR INSTALLATION AS PER STANDARDS (SEPARATE EARTHING
      FOR AC DB, DC DB, STRUCTURE &amp; PANELS, LA &amp; BODY OF INVERTER, ISOLATOR ETC.)</td>
      <td>{% if c and c.earthing_provided_ac_db and c.earthing_provided_dc_db and
             c.earthing_provided_structure_and_panels and c.earthing_provided_la_and_inverter_body and
             c.earthing_provided_isolator %}YES{% else %}NO{% endif %}</td></tr>
  <tr><td>14</td><td>WHETHER THE INVERTER IS EQUIPPED WITH THE FOLLOWING PROTECTION FUNCTIONS</td>
      <td>{{ "YES" if c and c.protection_settings else "NO" }}</td></tr>
</table>

<h4>INVERTER PROTECTION SETTINGS</h4>
<table border="1" cellpadding="4" cellspacing="0" width="100%">
  <tr><th>Protection Function</th><th width="12%">Provided</th><th width="18%">Setting</th>
      <th width="14%">Trip Time</th><th width="26%">Proof</th></tr>
  {% for row in (c.protection_settings if c else []) %}
  <tr><td>{{ row.protection_function }}</td>
      <td>{{ "YES" if row.is_provided else "NO" }}</td>
      <td>{{ row.setting_value or "" }} {{ row.setting_unit or "" }}</td>
      <td>{{ row.trip_time or "" }}</td>
      <td>{{ row.proof_type or "" }}</td></tr>
  {% endfor %}
</table>
<p class="text-muted">The supplier / installer shall provide any of the following in proof of the
settings provided in the inverter: the actual setting as displayed on the inverter HMI or downloaded
to a device; a factory test certificate issued by the OEM or a NABL accredited lab showing the serial
number of the inverter and the protection function settings; or a report of on-site testing carried
out with a calibrated test kit, witnessed by the DISCOM.</p>

<p>ALL THE STATEMENTS FURNISHED ABOVE ARE TRUE AND CORRECT</p>
<table width="100%"><tr><td>DATE: {{ today }}</td>
  <td style="text-align:right">SIGNATURE OF CONSUMER / INSTALLER</td></tr></table>""",
	},
	{
		"template_code": "KSEB-NETMETER-AGREEMENT",
		"document_name": "Net Metering Agreement (Stamp Paper)",
		"category": "KSEB",
		"recipient": "Assistant Engineer",
		"stage_code": "AGMT",
		"source_doctype": "Net Metering Agreement",
		"requires_stamp_paper": 1,
		"signatory": "Consumer and Two Witnesses",
		"notes": "SOURCE: KSEB Agreement.docx, including the full schedule.",
		"body": """<h3 style="text-align:center">Agreement for Connecting Solar Energy System to
The Distribution System of The Licensee</h3>
{% set a = agreement %}
<p>This Memorandum of Agreement is made on {{ today }} at
{{ a.place_of_execution if a else "" }} between the eligible consumer
<strong>{{ consumer.consumer_name }}</strong> residing at {{ address_text }} as first party and
the {{ discom_name }}, represented by
{{ a.discom_representative_name if a else "" }}, hereinafter referred to as the Licensee, as second
party.</p>
<p>Whereas the consumer has installed a solar energy system at the premises owned and possessed by
them and has requested the Licensee to provide connectivity to the said plant. The Licensee agrees
to provide the consumer a Solar Plant Identification Number (SPIN)
<strong>{{ a.spin if a else installation.spin or "" }}</strong> for the electricity generated from the
above plant having capacity <strong>{{ installation.capacity_kw }} kWp</strong>, as per the conditions
of this agreement and the regulations or orders issued by the State Regulatory Commission.</p>
<p>The validity of this agreement is 25 years from its date. The consumer may terminate this
agreement after giving thirty (30) days' clear notice in writing. The Licensee has the right to
terminate at any time after giving 30 days' prior notice if the consumer breaches any term.</p>

<h4>SCHEDULE &ndash; Item I: Particulars of the consumer</h4>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="45%">Name of the consumer</td><td>{{ a.consumer_name if a else consumer.consumer_name }}</td></tr>
  <tr><td>Permanent address of the consumer</td><td>{{ a.permanent_address if a else address_text }}</td></tr>
  <tr><td>Consumer number / Code &amp; Category</td><td>{{ a.consumer_number_and_category if a else "" }}</td></tr>
  <tr><td>Voltage at which supply is availed</td><td>{{ a.supply_voltage if a else "" }}</td></tr>
  <tr><td>Connected load / Contract demand</td><td>{{ a.connected_load_or_contract_demand if a else "" }}</td></tr>
</table>

<h4>Item II: Details of premises where the solar energy system is installed</h4>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="45%">Address of the premises</td><td>{{ a.installation_address if a else address_text }}</td></tr>
  <tr><td>Solar meter details</td><td>{{ a.solar_meter_type if a else "Unidirectional Energy Meter" }}</td></tr>
  <tr><td>Meter No &amp; Make</td>
      <td>{{ a.solar_meter_number if a else "" }} / {{ a.solar_meter_make if a else "" }}</td></tr>
  <tr><td>Initial Reading</td><td>{{ a.solar_meter_initial_reading if a else "" }}</td></tr>
  <tr><td>Solar Plant Identification Number (SPIN)</td><td>{{ a.spin if a else "" }}</td></tr>
  <tr><td>Capacity of the solar energy system</td><td>{{ a.plant_capacity_kwp if a else installation.capacity_kw }} kWp</td></tr>
  <tr><td>Name of Electrical Section</td><td>{{ a.electrical_section if a else "" }}</td></tr>
  <tr><td>Details of Distribution Transformer and HT feeder (for HT prosumer)</td>
      <td>{{ a.distribution_transformer_details if a else "" }} {{ a.ht_feeder_details if a else "" }}</td></tr>
  <tr><td>Name of Corporation / Municipality / Panchayath</td>
      <td>{{ a.local_body_type if a else "" }} &ndash; {{ a.local_body_name if a else "" }}</td></tr>
  <tr><td>Village &amp; Survey Number</td>
      <td>{{ a.village if a else "" }} / {{ a.survey_number if a else "" }}</td></tr>
  <tr><td>GPS details of the location</td><td>{{ a.gps_coordinates if a else "" }}</td></tr>
</table>

<h4>Item III: Premises to which excess energy is to be wheeled</h4>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><th>Order of preference</th><th>Consumer Number</th><th>Tariff</th><th>Electrical Section</th></tr>
  {% for row in (a.wheeling_preferences if a else []) %}
  <tr><td>Preference {{ row.preference_order }}</td><td>{{ row.consumer_number }}</td>
      <td>{{ row.tariff or "" }}</td><td>{{ row.electrical_section or "" }}</td></tr>
  {% else %}
  <tr><td>Preference 1</td><td></td><td></td><td></td></tr>
  <tr><td>Preference 2</td><td></td><td></td><td></td></tr>
  <tr><td>Preference 3</td><td></td><td></td><td></td></tr>
  {% endfor %}
</table>

<table width="100%" style="margin-top:30px">
  <tr><td width="50%">Sd/ &ndash; 1st Party<br><br>
      Witness 1 &hellip;&hellip;&hellip;&hellip;&hellip;<br>{{ a.witness_1_name if a else "" }}<br><br>
      Witness 2 &hellip;&hellip;&hellip;&hellip;&hellip;<br>{{ a.witness_2_name if a else "" }}</td>
      <td>Sd/ &ndash; 2nd Party<br><br>Witness 1 &hellip;&hellip;&hellip;&hellip;&hellip;<br><br>
      Witness 2 &hellip;&hellip;&hellip;&hellip;&hellip;</td></tr>
</table>""",
	},
	# -------------------------------------------------------------------- customer
	{
		"template_code": "CUST-COMMISSIONING-CERTIFICATE",
		"document_name": "Commissioning Certificate",
		"category": "Customer",
		"recipient": "Consumer",
		"stage_code": "COMM",
		"source_doctype": "Commissioning Report",
		"signatory": "Authorised Signatory",
		"notes": "Customer-facing certificate issued at handover.",
		"body": """<h3 style="text-align:center">Commissioning Certificate</h3>
{% set c = commissioning %}
<p>This is to certify that the grid connected rooftop solar power plant described below has been
installed, tested and commissioned in accordance with the standards of the
{{ discom_name }} and the Electrical Inspectorate.</p>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="40%">Consumer</td><td>{{ consumer.consumer_name }}</td></tr>
  <tr><td>Consumer Number</td><td>{{ installation.consumer_number }}</td></tr>
  <tr><td>Installation Address</td><td>{{ address_text }}</td></tr>
  <tr><td>Installed Capacity</td><td>{{ installation.capacity_kw }} kWp</td></tr>
  <tr><td>Commissioning Date</td>
      <td>{{ frappe.utils.formatdate(c.commissioning_date, "dd-MM-yyyy") if c else "" }}</td></tr>
  <tr><td>Commissioning Certificate No</td><td>{{ c.commissioning_certificate_no if c else "" }}</td></tr>
  <tr><td>Net Meter Serial</td><td>{{ c.net_meter_serial_no if c else "" }}</td></tr>
  <tr><td>SPIN</td><td>{{ installation.spin or "" }}</td></tr>
  <tr><td>Performance Ratio at Commissioning</td>
      <td>{{ c.performance_ratio_at_commissioning if c else "" }}%</td></tr>
  <tr><td>Warranty Period</td>
      <td>{{ frappe.utils.formatdate(installation.warranty_start_date, "dd-MM-yyyy") }} to
          {{ frappe.utils.formatdate(installation.warranty_end_date, "dd-MM-yyyy") }}</td></tr>
</table>
""" + _EPC_SIGNOFF,
	},
	{
		"template_code": "CUST-HANDOVER-PACK",
		"document_name": "Customer Handover Pack",
		"category": "Customer",
		"recipient": "Consumer",
		"stage_code": "COMM",
		"signatory": "Both",
		"notes": "Warranty by make, net meter details and the O&M contact.",
		"body": """<h3 style="text-align:center">Customer Handover Pack</h3>
{% set c = commissioning %}
<p><strong>{{ consumer.consumer_name }}</strong> &nbsp;|&nbsp; {{ installation.consumer_number }}
&nbsp;|&nbsp; {{ installation.capacity_kw }} kWp &nbsp;|&nbsp; {{ address_text }}</p>

<h4>Your System</h4>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><td width="40%">Modules</td>
      <td>{{ frappe.db.get_value("Component Make", installation.module_make, "make_name") or "" }}
          {{ installation.module_wattage | int }} Wp &times; {{ installation.module_count }}</td></tr>
  <tr><td>Inverter</td>
      <td>{{ frappe.db.get_value("Component Make", installation.inverter_make, "make_name") or "" }}
          {{ installation.inverter_capacity_kw }} kW {{ installation.connection_type }}</td></tr>
  <tr><td>Net Meter</td><td>{{ c.net_meter_serial_no if c else "" }}
          ({{ c.net_meter_make if c else "" }})</td></tr>
  <tr><td>SPIN</td><td>{{ installation.spin or "" }}</td></tr>
</table>

<h4>Warranty</h4>
<table border="1" cellpadding="5" cellspacing="0" width="100%">
  <tr><th>Component</th><th>Make</th><th>Terms</th></tr>
  {% for make_field, label in [(installation.module_make, "Solar PV Modules"),
                               (installation.inverter_make, "Inverter")] %}
    {% if make_field %}
      {% set m = frappe.get_doc("Component Make", make_field) %}
      <tr><td>{{ label }}</td><td>{{ m.make_name }}</td>
          <td>{% if m.product_warranty_years %}{{ m.product_warranty_years }} years product warranty{% endif %}
              {% if m.performance_warranty_years %}, {{ m.performance_warranty_years }} years performance warranty{% endif %}</td></tr>
    {% endif %}
  {% endfor %}
  <tr><td>System (workmanship)</td><td>&mdash;</td>
      <td>{{ frappe.utils.formatdate(installation.warranty_start_date, "dd-MM-yyyy") }} to
          {{ frappe.utils.formatdate(installation.warranty_end_date, "dd-MM-yyyy") }}</td></tr>
</table>

<h4>Service &amp; Maintenance</h4>
<p>Your system is covered by comprehensive operation and maintenance for five years from the date of
commissioning. Please contact us at {{ company.epc_contact_no }} or {{ company.epc_email }} to report
any issue.</p>
<p class="text-muted">Periodic cleaning of the modules and water for cleaning are arranged by you.
We will advise you on best practice at handover.</p>
""" + _EPC_SIGNOFF,
	},
]

#: Which templates belong to which set.
TEMPLATE_SETS = {
	"PM Surya Ghar Residential - Financed": [
		"MNRE-CONSUMER-VENDOR-AGREEMENT", "NP-APPLICATION", "BANK-VENDOR-FEASIBILITY",
		"BANK-EHS-CHECKLIST", "BANK-COVERING-LOAN", "KSEB-NETMETER-REQUEST",
		"KSEB-TESTING-CHECKLIST", "KSEB-COVERING-COMPLETION", "KSEB-FORM-1", "KSEB-FORM-2",
		"KSEB-FORM-3", "KSEB-NETMETER-AGREEMENT", "CUST-COMMISSIONING-CERTIFICATE",
		"CUST-HANDOVER-PACK", "BANK-COMPLETION-REPORT", "BANK-COVERING-COMPLETION",
		"NP-COMPLETION-REPORT", "KSEB-REFUND-REQUEST",
	],
	"PM Surya Ghar Residential - Self Funded": [
		"MNRE-CONSUMER-VENDOR-AGREEMENT", "NP-APPLICATION", "KSEB-NETMETER-REQUEST",
		"KSEB-TESTING-CHECKLIST", "KSEB-COVERING-COMPLETION", "KSEB-FORM-1", "KSEB-FORM-2",
		"KSEB-FORM-3", "KSEB-NETMETER-AGREEMENT", "CUST-COMMISSIONING-CERTIFICATE",
		"CUST-HANDOVER-PACK", "NP-COMPLETION-REPORT", "KSEB-REFUND-REQUEST",
	],
	"Commercial / Non-Subsidy": [
		"KSEB-NETMETER-REQUEST", "KSEB-TESTING-CHECKLIST", "KSEB-COVERING-COMPLETION",
		"KSEB-FORM-1", "KSEB-FORM-2", "KSEB-FORM-3", "KSEB-NETMETER-AGREEMENT",
		"CUST-COMMISSIONING-CERTIFICATE", "CUST-HANDOVER-PACK", "KSEB-REFUND-REQUEST",
	],
}
