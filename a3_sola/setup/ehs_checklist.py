# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The lender's EHS guidance checklist, transcribed verbatim.

Question text is stored exactly as the lender writes it, because it prints on the report
the bank receives. Do not paraphrase these when editing.

Source: the client's "RTS Vendor Feasibility Report PG 2" — the guidance checklist and
consumer education for verification of adequacy on Environmental, Health and Safety
requirements during appraisal and monitoring of a rooftop solar project funded under the
bank's residential rooftop solar programme.
"""

EHS_QUESTIONS = [
	# --- go / no-go ----------------------------------------------------------
	{
		"code": "EHS-GNG-01",
		"phase": "Go/No-Go",
		"expected": "Yes",
		"blocking": True,
		"text": (
			"Confirm that roofing material where the rooftop solar system is installed does not "
			"contain any carcinogenic material like broken or dilapidated asbestos."
		),
	},
	# --- proposal appraisal --------------------------------------------------
	{
		"code": "EHS-APP-01",
		"phase": "Proposal Appraisal",
		"expected": "",
		"text": (
			"Whether the proposal requires lopping/pruning of tree branches to ensure a shadow-free "
			"area on the roof. If yes, state whether permissions are obtained from competent "
			"authorities for periodic lopping/pruning of trees."
		),
	},
	{
		"code": "EHS-APP-02",
		"phase": "Proposal Appraisal",
		"expected": "Yes",
		"text": (
			"Whether access is available on a 24 x 365 basis (all days of the year irrespective of "
			"public holidays and Sundays)."
		),
	},
	{
		"code": "EHS-APP-03",
		"phase": "Proposal Appraisal",
		"expected": "Yes",
		"text": (
			"Whether structural safety of the building, present condition of roof for leakages "
			"and/or cracks and adequacy of roof drainage has been assessed."
		),
	},
	{
		"code": "EHS-APP-04",
		"phase": "Proposal Appraisal",
		"expected": "Yes",
		"text": (
			"Whether the consent from residents/owners/general body has been secured, and whether "
			"the residents are informed about the timelines of the construction process."
		),
	},
	{
		"code": "EHS-APP-05",
		"phase": "Proposal Appraisal",
		"expected": "Yes",
		"text": (
			"Whether the proposal includes estimated water requirements for washing of panels and "
			"dependable arrangements to draw or share water from the same water connection or "
			"overhead tanks with the owner of the building."
		),
	},
	{
		"code": "EHS-APP-06",
		"phase": "Proposal Appraisal",
		"expected": "",
		"text": (
			"Does the loan include financial assistance for batteries? If yes, an undertaking is "
			"required for compliance with the Batteries (Management) Rules 2021 and amendments."
		),
	},
	# --- installation and operation -----------------------------------------
	{
		"code": "EHS-INS-01",
		"phase": "Installation & Operation",
		"expected": "Yes",
		"text": (
			"Electrical Safety Approval: whether earthing of all plant and equipment components has "
			"been made and tested by an approved competent agency, with certification from the Chief "
			"Electrical Inspector to Government where applicable for the system size."
		),
	},
	# --- installer advisory --------------------------------------------------
	{
		"code": "EHS-ADV-01",
		"phase": "Installer Advisory",
		"expected": "",
		"text": (
			"Whether the installer has accreditation of ISO 14000 or OHSAS 18001, or has received "
			"any recognition for environmentally friendly initiatives or best EHS practices."
		),
	},
	{
		"code": "EHS-ADV-02",
		"phase": "Installer Advisory",
		"expected": "Yes",
		"text": (
			"All safety provisions like rubber mats, electric shock chart, first aid box, fire "
			"extinguishers to handle all types of fire (ABC type of required capacity) and sand "
			"buckets are provided/installed at appropriate locations."
		),
	},
	{
		"code": "EHS-ADV-03",
		"phase": "Installer Advisory",
		"expected": "Yes",
		"text": (
			"Provisions to provide safety wear like boots, hard hats (helmets), gloves and safety "
			"belts for personnel while working at heights have been included in the proposal."
		),
	},
	{
		"code": "EHS-ADV-04",
		"phase": "Installer Advisory",
		"expected": "Yes",
		"text": (
			"All personnel deployed for installation, operation and maintenance are provided with "
			"basic training in first aid and firefighting."
		),
	},
	{
		"code": "EHS-ADV-05",
		"phase": "Installer Advisory",
		"expected": "Yes",
		"text": (
			"All personnel deployed for installation, operation and maintenance (unskilled, "
			"semi-skilled and skilled) are paid at least minimum wages as per the applicable Minimum "
			"Wages Act of the Government of India."
		),
	},
	{
		"code": "EHS-ADV-06",
		"phase": "Installer Advisory",
		"expected": "Yes",
		"text": (
			"All personnel deployed for installation and O&M are covered under a workmen compensation "
			"insurance policy, the Employee Provident Fund Act, the Gratuity Act etc. as applicable."
		),
	},
	{
		"code": "EHS-ADV-07",
		"phase": "Installer Advisory",
		"expected": "Yes",
		"text": (
			"End consumers have been sensitised to the potential safety issues in installing rooftop "
			"solar plants."
		),
	},
]
