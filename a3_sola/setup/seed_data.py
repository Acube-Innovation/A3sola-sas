# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Master seed data, traced to the client's operating documents.

Every figure below carries a SOURCE comment naming the document it came from. Where the
client's documents disagree with each other, the rule that their own arithmetic satisfies
is the one implemented, and the discrepancy is recorded in the fee schedule's notes for
them to confirm.
"""

# SOURCE: KSEB letters and forms across the client's live jobs.
DISCOM_SECTIONS = [
	("Athani", "Ernakulam"),
	("Vennala", "Ernakulam"),
	("Vazhakkala", "Ernakulam"),
	("Kodakara", "Thrissur"),
	("Koovappady", "Ernakulam"),
	("Vellangallur", "Thrissur"),
	("Angamaly", "Ernakulam"),
	("Aluva", "Ernakulam"),
	("Perumbavoor", "Ernakulam"),
	("Chalakudy", "Thrissur"),
	("Irinjalakuda", "Thrissur"),
	("Muvattupuzha", "Ernakulam"),
	("Kothamangalam", "Ernakulam"),
	("North Paravoor", "Ernakulam"),
	("Kakkanad", "Ernakulam"),
	("Fort Kochi", "Ernakulam"),
	("Kodungallur", "Thrissur"),
	("Cherthala", "Alappuzha"),
	("Changanassery", "Kottayam"),
]

# SOURCE: proposal templates - 250 sq ft for 3 kW, 350-400 for 5 kW, 800 for 10 kW.
ROOF_TYPES = [
	("RCC Flat", 1.0, 80.0, "Epoxy coated GI tubes for flat roof"),
	("Tiled Sloped", 1.15, 90.0, "Roof hook mounting on tiled roof"),
	("Metal Sheet", 1.10, 85.0, "L-foot mounting on trapezoidal sheet"),
	("Elevated Structure", 1.35, 75.0, "Epoxy coated GI tubes for flat roof with concrete pedestals"),
]

# SOURCE: PM Surya Ghar scheme. 1 kW = 30,000; 2 kW = 60,000; 3 kW and above = 78,000.
PMSG_SLABS = [
	(1.0, 1.99, "Fixed", 30000, 0),
	(2.0, 2.99, "Fixed", 60000, 0),
	(3.0, 10.0, "Fixed", 78000, 78000),
]

# Indicative KSEB domestic bimonthly telescopic slabs. MUST be verified against the
# current KSERC tariff order before go-live - see docs/CONFIGURATION.md.
KSEB_DOMESTIC_SLABS = [
	(0, 100, 3.25, 40, 0),
	(100, 200, 4.05, 0, 0),
	(200, 300, 5.10, 0, 0),
	(300, 400, 6.95, 0, 0),
	(400, 500, 8.20, 0, 0),
	(500, 1000000, 9.20, 0, 0),
]

# SOURCE: the client's current proposals.
#   Rayzon      - 15 years product, 30 years performance
#   Renewsys    - 12 years product, 30 years performance
#   Vikram      - 12 years product, 30 years performance
#   Solinteg    - 10 years (string inverter)
#   SolarEdge   -  8 years (inverter with optimiser)
#   Hoymiles    - 12 years (microinverter)
COMPONENT_MAKES = [
	# (make, component_type, technology, is_dcr, product_yrs, performance_yrs, floor10, floor25)
	("Rayzon", "Module", "Mono PERC Bifacial", 1, 15, 30, 90.0, 80.0),
	("Vikram", "Module", "Mono PERC Bifacial", 1, 12, 30, 90.0, 80.0),
	("Renewsys", "Module", "Mono PERC Bifacial", 1, 12, 30, 90.0, 80.0),
	("Solinteg", "Inverter", "String On-Grid", 0, 10, 0, 0, 0),
	("SolarEdge", "Inverter", "String with Optimiser", 0, 8, 0, 0, 0),
	("Hoymiles", "Inverter", "Microinverter", 0, 12, 0, 0, 0),
	("Polycab", "Inverter", "String On-Grid", 0, 7, 0, 0, 0),
	("Apollo", "Mounting Structure", "Epoxy coated GI tube", 0, 5, 0, 0, 0),
	("L&T", "Energy Meter", "Watt-hour meter", 0, 5, 0, 0, 0),
	("Apar", "Cable", "UV rated solar copper cable", 0, 5, 0, 0, 0),
	("Seichem", "Cable", "E-beam cross-linked DC cable", 0, 5, 0, 0, 0),
	("Mersen", "DCDB", "PV fuses and Type 2 SPD", 0, 5, 0, 0, 0),
	("Citel", "ACDB", "Type 2 AC SPD", 0, 5, 0, 0, 0),
	("ABB", "ACDB", "MCB", 0, 5, 0, 0, 0),
	("Eaton", "DCDB", "MCB", 0, 5, 0, 0, 0),
	("Excel Earthing", "Earthing", "Copper bonded chemical earthing", 0, 10, 0, 0, 0),
	("Excel Earthing", "Lightning Protection", "Spike air termination with chemical earth kit", 0, 10, 0, 0, 0),
]

# SOURCE: Master Data Macro.xlsm sheet 2 - the client's own specification codes, and the
# 10 kWp three-option proposal. Costs are left at zero for the client to populate; the
# workbook holds their live pricing and it is commercially sensitive.
#   code, name, kw, system, phase, topology, dcr, area, module spec, module make,
#   alt makes, wattage, count, inv1 spec, inv1 make, inv1 kw, inv1 n, inv2 spec,
#   inv2 make, inv2 kw, inv2 n, meters, earthing, la
SOLAR_PACKAGES = [
	("3Kw 1PH", "3 kWp Single Phase On-Grid", 3.0, "On-Grid", "Single Phase", "String", 1, 250,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 6,
	 "3kW Single Phase On-Grid with Online Monitoring", "Solinteg", 3.0, 1,
	 "3kW Single Phase On-Grid with Panel level optimizer and Online Monitoring", "SolarEdge", 3.0, 1,
	 1, 2, 1),
	("3Kw 1PH Micro", "3 kWp Single Phase Microinverter", 3.0, "On-Grid", "Single Phase", "Microinverter", 1, 250,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 6,
	 "1kW Single Phase On-Grid Microinverter", "Hoymiles", 1.0, 5, None, None, 0, 0, 1, 2, 1),
	("5KW 1PH", "5 kWp Single Phase On-Grid", 5.0, "On-Grid", "Single Phase", "String", 1, 350,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 9,
	 "5kW Single Phase On-Grid Inverter and Online Monitoring", "Polycab", 5.0, 1,
	 "5kW Single Phase On-Grid with Panel level optimizer", "SolarEdge", 5.0, 1, 1, 2, 1),
	("5KW 3PH", "5 kWp Three Phase On-Grid", 5.0, "On-Grid", "Three Phase", "String", 1, 350,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 9,
	 "5kW Three Phase On-Grid Inverter and Online Monitoring", "Solinteg", 5.0, 1,
	 "5kW Three Phase On-Grid with Panel level optimizer", "SolarEdge", 5.0, 1, 1, 2, 1),
	("5KW 1PH Micro", "5 kWp Single Phase Microinverter", 5.0, "On-Grid", "Single Phase", "Microinverter", 1, 350,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 9,
	 "1kW Single Phase On-Grid Microinverter", "Hoymiles", 1.0, 9, None, None, 0, 0, 1, 2, 1),
	("5KW 3PH Micro", "5 kWp Three Phase Microinverter", 5.0, "On-Grid", "Three Phase", "Microinverter", 1, 350,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 9,
	 "5kW Three Phase On-Grid Microinverter with 4 MPPT", "Hoymiles", 5.0, 1, None, None, 0, 0, 1, 2, 1),
	("5KW 1PH Hybrid", "5 kWp Single Phase Hybrid", 5.0, "Hybrid", "Single Phase", "Hybrid", 1, 350,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 9,
	 "5kW Single Phase Hybrid Inverter with Online Monitoring", "Solinteg", 5.0, 1, None, None, 0, 0, 1, 2, 1),
	("5KW 1PH Hybrid with 3Kwp", "5 kW Hybrid with 3 kWp Array", 3.0, "Hybrid", "Single Phase", "Hybrid", 1, 250,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 6,
	 "5kW Single Phase Hybrid Inverter with Online Monitoring", "Solinteg", 5.0, 1, None, None, 0, 0, 1, 2, 1),
	("8KW 3PH", "8 kWp Three Phase On-Grid", 8.0, "On-Grid", "Three Phase", "String", 1, 400,
	 "550 Wp Mono PERC Bifacial DCR", "Rayzon", "Rayzon/Vikram/Equivalent", 550, 15,
	 "8kW Three Phase On-Grid Inverter and Online Monitoring", "Solinteg", 8.0, 1,
	 "8kW Three Phase On-Grid with Panel level optimizer", "SolarEdge", 8.0, 1, 1, 2, 1),
	# SOURCE: 10kWp_3PH_NDCR.docx - non-DCR TopCon modules, three inverter options.
	("10KW 3PH Non-DCR", "10 kWp Three Phase Non-DCR", 10.0, "On-Grid", "Three Phase", "String", 0, 800,
	 "620 Wp TopCon Bifacial Non-DCR", "Rayzon", "Rayzon/Equivalent", 620, 16,
	 "10kW Three Phase On-Grid with Online Monitoring", "Solinteg", 10.0, 1,
	 "10kW Three Phase On-Grid with Panel level optimizer and Online Monitoring", "SolarEdge", 10.0, 1,
	 1, 3, 1),
]

# SOURCE: the client's proposal "Scope of Work" section.
SCOPE_OF_WORK = [
	("Company", "Engineering", "System design including civil, structural, electrical and mechanical components, with construction drawings and specifications."),
	("Company", "Procurement & Construction", "Procure equipment and materials, deliver to site, perform complete system installation and test all electrical components as per manufacturer specifications. Commission the system to full operability."),
	("Company", "DISCOM & Statutory", "Obtain the feasibility certificate from the local DISCOM section office and register the system. Coordinate testing and compliance verification, and coordinate replacement of the existing energy meter with a bi-directional net meter."),
	("Company", "Warranty & Support", "Free inspection for five years (three visits a year) and maintenance if required. Washing of solar panels is not included and is arranged by the client. Training will be provided."),
	("Company", "Post-Installation", "Training of the client's engineer, electrician or staff on working principles, safety measures and maintenance. Daily remote monitoring of the system via internet."),
	("Customer", "Storage & Access", "Provide access to the work site for delivery of equipment and materials before and during implementation. Provide suitable and secure storage. Facilitate access for the work crew seven days a week."),
	("Customer", "Local Consultation", "Facilitate interfacing with the client's engineer, electrician or staff. Provide copies of approved electrical schematics and building drawings if available. Obtain all statutory clearances required for the project."),
	("Customer", "Remote Monitoring", "Provide a wireless internet connection in the vicinity of the grid-tied inverter to facilitate remote monitoring."),
	("Customer", "Post-Installation", "Periodic cleaning of solar panels after completion of system installation, and water for cleaning."),
]

# SOURCE: Greeting message with quotation.docx - reproduced faithfully, with the WhatsApp
# bold markers preserved and every link moved into Settings.
GREETING_TEMPLATE = """Hi {{ first_name }},

*Thank you for your interest in {{ settings.product_name }}.* It was a pleasure discussing your solar requirements with you.

As promised, please find our formal *Solar Project Proposal* attached.

This proposal includes:
*Custom System Design:* Engineered specifically for your site and energy needs.
*Premium Technology:* High-efficiency modules with a 25-year performance warranty.
*End-to-End Support:* We handle all KSEB documentation, installation, and commissioning.
*Smart Monitoring:* Integrated remote monitoring to track your savings in real-time.

At *{{ settings.product_name }}*, we pride ourselves on delivering sustainable, long-term value and energy independence.
Please review the attached document. I will follow up with you shortly to answer any technical questions and discuss the next steps for your installation."""

OUTREACH_TEMPLATES = [
	("First Contact", "WhatsApp", "Step 1: First Contact",
	 "Hi {{ first_name }},\n\nThank you for your enquiry about rooftop solar. I would like to understand your "
	 "requirement briefly - your average monthly electricity bill and roof type - so we can propose the right "
	 "system size for you.\n\nWhen would be a good time for a short call?"),
	("24 Hour Nudge", "WhatsApp", "Step 2: 24hr Nudge",
	 "Hi {{ first_name }},\n\nFollowing up on my message yesterday about your rooftop solar enquiry. "
	 "A two-minute call is enough for me to give you an indicative system size and cost.\n\n"
	 "Shall I call you this evening?"),
	("Value and ROI", "WhatsApp", "Step 3: Value/ROI",
	 "Hi {{ first_name }},\n\nA quick note on what rooftop solar returns.\n\n"
	 "*Government subsidy:* residential systems qualify for central financial assistance, credited directly "
	 "to your bank account after commissioning.\n"
	 "*Savings:* Kerala's telescopic tariff means the units you stop buying are the most expensive ones, so "
	 "the saving per unit is higher than your average rate.\n"
	 "*Warranty:* 25-year module performance warranty and five years of comprehensive support.\n\n"
	 "I can put exact figures for your bill into a proposal - shall I?"),
	("Breakup and Close", "WhatsApp", "Step 4: Breakup/Close",
	 "Hi {{ first_name }},\n\nI have not been able to reach you, so I will stop following up for now and "
	 "leave this with you.\n\nIf rooftop solar is something you want to revisit - this year or next - just "
	 "message me and I will pick it up from here. Thank you for your time."),
	("Proposal Sent", "WhatsApp", "Completed: Proposal Sent", GREETING_TEMPLATE),
]

# SOURCE: the client's social presence, as listed in their greeting message.
BRAND_LINKS = [
	("Facebook", "https://www.facebook.com/renewcoreinnovations/"),
	("Instagram", "https://www.instagram.com/renewcoreinnovations/"),
	("LinkedIn", "https://www.linkedin.com/company/renewcore-innovations-llp"),
	("Pinterest", "https://www.pinterest.com/renewcoreinnovations/"),
	("X", "https://x.com/renewcore"),
	("Tumblr", "https://www.tumblr.com/blog/renewcoreinnovations"),
	("Threads", "https://www.threads.com/@renewcoreinnovations"),
]

# SOURCE: the client's proposal general terms. The three-phase clause is NOT here - it is
# rendered from the Grid Regulation Rule so it can never go stale.
PROPOSAL_TERMS = """<ol>
<li>The above price is for a normal flat roof type mounting structure. If additional structure work is required for a sheet roof or a raised platform, the same will be chargeable extra.</li>
<li>Load enhancement or three phase conversion, if required, will be extra.</li>
<li>The above offer includes documentation, DISCOM testing and all other formalities till commissioning of the system with the net meter. Cabling up to the DISCOM metering point is also considered.</li>
<li>Subsidy documentation will be carried out by the company. The subsidy will be credited to the customer's bank account subject to approval by MNRE.</li>
<li>The project will be executed under the name of the registered vendor on the MNRE portal.</li>
<li>DISCOM fees are not included. 80% of the registration amount without GST will be refunded after commissioning of the plant.</li>
<li>Remote monitoring of the system via internet: Wi-Fi data logger included. Internet connectivity is to be provided by the customer.</li>
</ol>"""

PROPOSAL_COVERING_LETTER = """<p>Dear Sir/Madam,</p>
<p>We thank you for your interest evinced in a renewable energy solution from us. We are pleased to submit our proposal for a solar power project aimed at delivering sustainable energy solutions tailored to your environmental goals.</p>
<p>Our team specialises in end-to-end solar project development, including feasibility studies, permitting, engineering, procurement, construction, and grid integration.</p>
<p>This proposal outlines a custom-designed solar power system suited to your site requirements and energy consumption profile. The project is expected to deliver long-term cost savings, reduce carbon emissions, and increase energy independence - all aligned with your vision for a sustainable future.</p>
<p>We look forward to the opportunity to collaborate and are confident in our ability to bring this project to life efficiently and professionally.</p>
<p>Please feel free to reach out with any questions or to schedule a follow-up discussion.</p>"""

PROPOSAL_DELIVERY_SCHEDULE = """<ul>
<li>Supply of materials: within 7 days from the date of advance payment.</li>
<li>Installation: within 7 to 15 days from the date of delivery of materials.</li>
<li>Commissioning: within 1 week from completion of installation where the net meter is purchased by the customer; 2 to 4 weeks where the net meter is availed from the DISCOM.</li>
</ul>"""

SUBSIDY_NOTE = """<p><strong>Government subsidy.</strong> The amount shown is the central financial assistance expected
under the scheme. It is paid by the government <em>directly to the customer's bank account after commissioning</em>.
It is not a discount on this proposal, it is not deducted from any invoice, and it is subject to approval by MNRE.</p>"""

GST_NOTE = """<p>The quoted price is inclusive of applicable GST. Solar EPC is treated as a composite supply and the
valuation basis must be confirmed with the company's chartered accountant before invoicing.</p>"""
