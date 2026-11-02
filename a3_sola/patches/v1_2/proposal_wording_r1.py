# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The proposal's standing wording as the client's revised proposal (RENC/PROP/26-27/089_R1)
has it - the general terms, the delivery schedule and the scope of work in A3 Sola Settings.
Each is replaced only while it is still the text the app first seeded: wording a site has
edited is its own, and is left as it is."""

import frappe

from a3_sola.setup import seed_data

#: What the app seeded before this patch.
OLD_TERMS = "<ol>\n<li>The above price is for a normal flat roof type mounting structure. If additional structure work is required for a sheet roof or a raised platform, the same will be chargeable extra.</li>\n<li>Load enhancement or three phase conversion, if required, will be extra.</li>\n<li>The above offer includes documentation, DISCOM testing and all other formalities till commissioning of the system with the net meter. Cabling up to the DISCOM metering point is also considered.</li>\n<li>Subsidy documentation will be carried out by the company. The subsidy will be credited to the customer's bank account subject to approval by MNRE.</li>\n<li>The project will be executed under the name of the registered vendor on the MNRE portal.</li>\n<li>DISCOM fees are not included. 80% of the registration amount without GST will be refunded after commissioning of the plant.</li>\n<li>Remote monitoring of the system via internet: Wi-Fi data logger included. Internet connectivity is to be provided by the customer.</li>\n</ol>"
OLD_SCHEDULE = '<ul>\n<li>Supply of materials: within 7 days from the date of advance payment.</li>\n<li>Installation: within 7 to 15 days from the date of delivery of materials.</li>\n<li>Commissioning: within 1 week from completion of installation where the net meter is purchased by the customer; 2 to 4 weeks where the net meter is availed from the DISCOM.</li>\n</ul>'
OLD_SCOPE = [('Company', 'Engineering', 'System design including civil, structural, electrical and mechanical components, with construction drawings and specifications.'), ('Company', 'Procurement & Construction', 'Procure equipment and materials, deliver to site, perform complete system installation and test all electrical components as per manufacturer specifications. Commission the system to full operability.'), ('Company', 'DISCOM & Statutory', 'Obtain the feasibility certificate from the local DISCOM section office and register the system. Coordinate testing and compliance verification, and coordinate replacement of the existing energy meter with a bi-directional net meter.'), ('Company', 'Warranty & Support', 'Free inspection for five years (three visits a year) and maintenance if required. Washing of solar panels is not included and is arranged by the client. Training will be provided.'), ('Company', 'Post-Installation', "Training of the client's engineer, electrician or staff on working principles, safety measures and maintenance. Daily remote monitoring of the system via internet."), ('Customer', 'Storage & Access', 'Provide access to the work site for delivery of equipment and materials before and during implementation. Provide suitable and secure storage. Facilitate access for the work crew seven days a week.'), ('Customer', 'Local Consultation', "Facilitate interfacing with the client's engineer, electrician or staff. Provide copies of approved electrical schematics and building drawings if available. Obtain all statutory clearances required for the project."), ('Customer', 'Remote Monitoring', 'Provide a wireless internet connection in the vicinity of the grid-tied inverter to facilitate remote monitoring.'), ('Customer', 'Post-Installation', 'Periodic cleaning of solar panels after completion of system installation, and water for cleaning.')]


def _same(a, b):
	return " ".join((a or "").split()) == " ".join((b or "").split())


def execute():
	settings = frappe.get_single("A3 Sola Settings")
	changed = False
	for field, old, new in (("terms_and_conditions_text", OLD_TERMS, seed_data.PROPOSAL_TERMS),
			("delivery_schedule_text", OLD_SCHEDULE, seed_data.PROPOSAL_DELIVERY_SCHEDULE)):
		if _same(settings.get(field), old):
			settings.set(field, new)
			changed = True
	rows = [(r.responsibility, r.category, r.scope_text) for r in sorted(settings.scope_of_work, key=lambda r: r.idx)]
	if len(rows) == len(OLD_SCOPE) and all(a[:2] == tuple(b[:2]) and _same(a[2], b[2]) for a, b in zip(rows, OLD_SCOPE)):
		settings.set("scope_of_work", [])
		for index, (responsibility, category, text) in enumerate(seed_data.SCOPE_OF_WORK, start=1):
			settings.append("scope_of_work", {"responsibility": responsibility, "category": category,
				"scope_text": text, "display_order": index})
		changed = True
	if changed:
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.db.commit()
