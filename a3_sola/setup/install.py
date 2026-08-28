# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Install and migrate hooks.

Everything here is idempotent - it checks before it inserts - so `after_migrate` can
re-run it safely and a partially seeded site converges rather than erroring.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from a3_sola.setup import (
	dashboard,
	dashboard_ops,
	dashboard_projects,
	install_ops,
	dashboard_platform,
	install_platform,
	install_provisioning,
	install_projects,
	seed_data,
)
from a3_sola.setup.custom_fields import CUSTOM_FIELDS, MODULE
from a3_sola.setup.custom_fields_ops import CUSTOM_FIELDS as OPS_CUSTOM_FIELDS
from a3_sola.setup.custom_fields_ops import MODULE as OPS_MODULE
from a3_sola.setup.custom_fields_projects import CUSTOM_FIELDS as PROJ_CUSTOM_FIELDS
from a3_sola.setup.custom_fields_projects import MODULE as PROJ_MODULE
from a3_sola.setup.roles import create_roles


def after_install():
	"""A fresh install must seed completely, so failures here are fatal and loud."""
	setup()


def after_migrate():
	"""Seeding is data, not schema. It must never be able to abort a migration.

	If it could, one bad master record would roll back the whole schema sync - which is
	exactly how this app first failed to install. Log loudly and let the migration finish;
	`bench execute a3_sola.setup.install.setup` re-runs it.
	"""
	try:
		setup()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "a3_sola: master seeding failed during migrate")
		print(
			"\n a3_sola: master seeding failed and was skipped. The migration completed.\n"
			"   Re-run it with: bench --site <site> execute a3_sola.setup.install.setup\n"
		)


def setup():
	"""Create roles, install custom fields and seed masters. Idempotent throughout."""
	create_roles()
	frappe.db.commit()
	install_custom_fields()
	frappe.db.commit()
	# Backfill the singleton BEFORE any module seeding touches it. A later phase's new
	# mandatory field would otherwise block the first save that module attempts.
	backfill_settings_defaults()
	seed_all_companies()
	seed_settings()
	# Platform is not tenant-scoped: it is the product's own marketing and funnel data,
	# so it seeds once per site rather than once per company.
	install_platform.setup()
	install_provisioning.setup()
	frappe.db.commit()
	dashboard.install()
	dashboard_ops.install()
	dashboard_projects.install()
	dashboard_platform.install()
	frappe.db.commit()


def backfill_settings_defaults():
	"""Apply defaults for any newly added settings field, once, before anything saves."""
	from a3_sola.solar_crm.doctype.a3_sola_settings.a3_sola_settings import (
		repair_dangling_links,
		repair_orphan_company_rows,
	)

	# Before the first save, not after. Frappe validates every link on every save, so one
	# setting pointing at a deleted record makes the whole singleton unsaveable - and with
	# it this function, the seeding it drives, and provisioning.
	repair_orphan_company_rows()
	repair_dangling_links()
	settings = frappe.get_single("A3 Sola Settings")
	filled = apply_field_defaults(settings)
	if filled:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
		frappe.db.commit()
	return filled


def seed_all_companies():
	"""Seed every existing company, not just the default one.

	When a later phase adds a module, tenants created before it have none of its masters -
	no stage chain, no document templates - and their next job fails at creation. Backfill
	them all; it is idempotent, so this is cheap.
	"""
	seeded = []
	for company in frappe.get_all("Company", pluck="name"):
		seed_masters(company)
		seeded.append(company)
	return seeded


def install_custom_fields():
	from a3_sola.setup.custom_fields_platform import PLATFORM_CUSTOM_FIELDS

	for definitions, module in (
		(CUSTOM_FIELDS, MODULE),
		(OPS_CUSTOM_FIELDS, OPS_MODULE),
		(PROJ_CUSTOM_FIELDS, PROJ_MODULE),
		(PLATFORM_CUSTOM_FIELDS, "Platform"),
	):
		create_custom_fields(definitions, ignore_validate=True)
		# Tag them to their module so `bench export-fixtures` stays module-scoped.
		for doctype, fields in definitions.items():
			for field in fields:
				name = f"{doctype}-{field['fieldname']}"
				if frappe.db.exists("Custom Field", name):
					frappe.db.set_value("Custom Field", name, "module", module, update_modified=False)


def default_company():
	company = frappe.defaults.get_global_default("company")
	if company:
		return company
	companies = frappe.get_all("Company", pluck="name", limit=1)
	return companies[0] if companies else None


def _exists(doctype, filters):
	"""Does this master already exist FOR THIS COMPANY?

	Every caller passes a company, and that is load-bearing rather than tidy. A check
	written without one - `{"roof_type": "RCC Flat Roof"}` - is true as soon as any tenant
	on the instance has that roof type, so the second tenant provisioned gets none at all
	and their first site survey has nothing to choose from. The seeding then reports
	success, because from its point of view the record does exist.
	"""
	return frappe.db.exists(doctype, filters)


def _insert(doc):
	document = frappe.get_doc(doc)
	document.flags.ignore_permissions = True
	document.flags.ignore_mandatory = True
	document.insert(ignore_permissions=True)
	return document


# --------------------------------------------------------------------- masters
def seed_masters(company=None):
	"""Seed every master this app needs, for one company. Idempotent."""
	company = company or default_company()
	if not company:
		frappe.log_error(
			title="a3_sola: master seeding skipped",
			message="No Company exists yet, so there is nothing to seed masters against.",
		)
		return

	discom = seed_discom(company)
	seed_discom_sections(company, discom)
	seed_roof_types(company)
	schemes = seed_subsidy_schemes(company)
	tariff = seed_tariff(company, discom)
	fee_schedule = seed_fee_schedule(company, discom)
	seed_regulation_rules(company, discom)
	seed_component_makes(company)
	seed_outreach_templates(company)
	seed_packages(company)
	install_ops.setup(company)
	install_projects.setup(company)
	return {
		"company": company,
		"discom": discom,
		"scheme": schemes[0] if schemes else None,
		"tariff": tariff,
		"fee_schedule": fee_schedule,
	}


def seed_discom(company):
	name = _exists("DISCOM", {"discom_name": "KSEB", "company": company})
	if name:
		return name
	return _insert(
		{
			"doctype": "DISCOM",
			"discom_name": "KSEB",
			"state": "Kerala",
			"portal_url": "https://pmsuryaghar.gov.in",
			"company": company,
			"portal_id_regex": r"^NP-[A-Z]+\d{2}-\d+$",
			"net_metering_notes": (
				"Net meter may be purchased by the consumer or availed from KSEBL on monthly "
				"rental; KSEBL allocation typically takes two to four weeks."
			),
		}
	).name


def seed_discom_sections(company, discom):
	for section, district in seed_data.DISCOM_SECTIONS:
		if _exists("DISCOM Section", {"section_name": section, "discom": discom, "company": company}):
			continue
		_insert(
			{
				"doctype": "DISCOM Section",
				"section_name": section,
				"discom": discom,
				"district": district,
				"company": company,
				"feasibility_sla_days": 45,
				"net_meter_sla_days": 21,
			}
		)


def seed_roof_types(company):
	for roof, multiplier, area, structure in seed_data.ROOF_TYPES:
		if _exists("Roof Type", {"roof_type": roof, "company": company}):
			continue
		_insert(
			{
				"doctype": "Roof Type",
				"roof_type": roof,
				"structure_cost_multiplier": multiplier,
				"area_per_kw_sqft": area,
				"typical_tilt_degrees": 11,
				"mounting_structure_specification": structure,
				"company": company,
			}
		)


def seed_subsidy_schemes(company):
	created = []
	name = _exists("Subsidy Scheme", {"scheme_name": "PM Surya Ghar: Muft Bijli Yojana", "company": company})
	if not name:
		doc = _insert(
			{
				"doctype": "Subsidy Scheme",
				"scheme_name": "PM Surya Ghar: Muft Bijli Yojana",
				"issuing_authority": "MNRE",
				"consumer_category": "Residential",
				"requires_dcr_modules": 1,
				"max_eligible_capacity_kw": 10,
				"is_active": 1,
				"company": company,
				"slabs": [
					{
						"capacity_from_kw": low,
						"capacity_to_kw": high,
						"calculation_basis": basis,
						"subsidy_amount": amount,
						"max_subsidy_cap": cap,
					}
					for low, high, basis, amount, cap in seed_data.PMSG_SLABS
				],
			}
		)
		name = doc.name
	created.append(name)

	if not _exists("Subsidy Scheme", {"scheme_name": "No Subsidy (Commercial)", "company": company}):
		created.append(
			_insert(
				{
					"doctype": "Subsidy Scheme",
					"scheme_name": "No Subsidy (Commercial)",
					"issuing_authority": "-",
					"consumer_category": "Commercial",
					"is_active": 1,
					"company": company,
				}
			).name
		)
	return created


def seed_tariff(company, discom):
	name = _exists("Electricity Tariff", {"tariff_name": "KSEB Domestic Bimonthly", "company": company})
	if name:
		return name
	return _insert(
		{
			"doctype": "Electricity Tariff",
			"tariff_name": "KSEB Domestic Bimonthly",
			"discom": discom,
			"consumer_category": "Residential",
			"billing_frequency": "Bimonthly",
			"effective_from": "2026-04-01",
			"is_active": 1,
			"company": company,
			"slabs": [
				{
					"units_from": low,
					"units_to": high,
					"rate_per_unit": rate,
					"fixed_charge": fixed,
					"duty_percent": duty,
				}
				for low, high, rate, fixed, duty in seed_data.KSEB_DOMESTIC_SLABS
			],
		}
	).name


def seed_fee_schedule(company, discom):
	name = _exists("Statutory Fee Schedule", {"schedule_name": "KSEB 2026-27", "company": company})
	if name:
		return name
	return _insert(
		{
			"doctype": "Statutory Fee Schedule",
			"schedule_name": "KSEB 2026-27",
			"discom": discom,
			"effective_from": "2026-04-01",
			"is_active": 1,
			"company": company,
			# SOURCE: the client's 3 kW proposal, the only template whose arithmetic is
			# internally consistent - Rs 1,000/kW + 18% GST = Rs 3,540, with 80% of the
			# Rs 3,000 base = Rs 2,400 refundable.
			"application_fee_base": 1000,
			"application_fee_gst_applicable": 1,
			"application_fee_gst_percent": 18,
			"registration_fee_per_kw": 1000,
			"registration_fee_gst_percent": 18,
			"registration_refund_percent": 80,
			"refund_computed_on": "Base Amount",
			"net_meter_charges": [
				{
					"connection_type": "Single Phase",
					"supply_mode": "Purchased by Customer",
					"charge_amount": 5000,
				},
				{
					"connection_type": "Three Phase",
					"supply_mode": "Purchased by Customer",
					"charge_amount": 10000,
				},
				{
					"connection_type": "Single Phase",
					"supply_mode": "Availed from DISCOM on Rental",
					"monthly_rental": 0,
					"allocation_lead_days": 21,
				},
				{
					"connection_type": "Three Phase",
					"supply_mode": "Availed from DISCOM on Rental",
					"monthly_rental": 0,
					"allocation_lead_days": 21,
				},
			],
			"notes": (
				"<p><strong>Open with the client before go-live.</strong> The statutory figures printed on the "
				"existing proposal templates disagree with each other. The 3 kW template states Rs 3,540 charged "
				"with Rs 2,400 refundable, which is exactly Rs 1,000/kW + 18% GST with 80% of the base refunded - "
				"the rule seeded here. The 5 kW and 8 kW templates state Rs 8,288, which is not derivable from any "
				"rule. The 10 kW template states Rs 11,800 charged (correct) with Rs 4,000 refundable, which "
				"should be Rs 8,000. Confirm the correct figures and the monthly rental for a DISCOM-supplied net "
				"meter, then update this schedule.</p>"
			),
		}
	).name


def seed_regulation_rules(company, discom):
	if _exists("Grid Regulation Rule", {"rule_code": "KSERC-3PH-ABOVE-3KW", "company": company}):
		return
	_insert(
		{
			"doctype": "Grid Regulation Rule",
			"rule_code": "KSERC-3PH-ABOVE-3KW",
			"rule_name": "Three-phase connection required above 3 kW",
			"discom": discom,
			"regulator": "KSERC",
			"rule_type": "Phase Requirement",
			"threshold_kw": 3,
			"required_connection_type": "Three Phase",
			"notified_on": "2025-11-06",
			"effective_from": "2025-11-06",
			"is_stayed": 1,
			"stay_authority": "High Court of Kerala",
			"stayed_from": "2025-11-06",
			"stayed_until": "2026-05-22",
			"company": company,
			# SOURCE: the sentence the client's proposals already print.
			"customer_facing_clause": (
				"<p>As per new KSERC regulations, solar plants above 3 kW shall be three-phase. However, the "
				"regulation notified on 06.11.2025 has been stayed by the High Court till 22.05.2026. Based on "
				"the status of the regulation, a three phase or single phase system may have to be chosen.</p>"
			),
		}
	)


def seed_component_makes(company):
	for make, ctype, tech, is_dcr, product, performance, floor10, floor25 in seed_data.COMPONENT_MAKES:
		if _exists("Component Make", {"make_name": make, "component_type": ctype, "company": company}):
			continue
		_insert(
			{
				"doctype": "Component Make",
				"make_name": make,
				"component_type": ctype,
				"technology": tech,
				"is_dcr": is_dcr,
				"product_warranty_years": product,
				"performance_warranty_years": performance,
				"performance_floor_10yr_percent": floor10,
				"performance_floor_25yr_percent": floor25,
				"company": company,
			}
		)


def seed_outreach_templates(company):
	for title, channel, step, body in seed_data.OUTREACH_TEMPLATES:
		if _exists("Outreach Message Template", {"template_name": title, "company": company}):
			continue
		_insert(
			{
				"doctype": "Outreach Message Template",
				"template_name": title,
				"channel": channel,
				"step_name": step,
				"message_body": body,
				"include_signature": 1,
				"include_social_links": 1,
				"attach_proposal": 1 if step == "Completed: Proposal Sent" else 0,
				"is_active": 1,
				"company": company,
			}
		)


def seed_packages(company):
	for row in seed_data.SOLAR_PACKAGES:
		(
			code, name, kw, system, phase, topology, dcr, area,
			mod_spec, mod_make, mod_alt, wattage, count,
			i1_spec, i1_make, i1_kw, i1_n, i2_spec, i2_make, i2_kw, i2_n,
			meters, earthing, la,
		) = row
		if _exists("Solar Package", {"specification_code": code, "company": company}):
			continue
		_insert(
			{
				"doctype": "Solar Package",
				"specification_code": code,
				"package_name": name,
				"capacity_kw": kw,
				"system_type": system,
				"connection_type": phase,
				"inverter_topology": topology,
				"is_dcr_compliant": dcr,
				"area_required_sqft": area,
				"module_specification": mod_spec,
				"module_make": _make(mod_make, "Module"),
				"module_alternate_makes": mod_alt,
				"module_wattage": wattage,
				"module_count": count,
				"inverter_1_specification": i1_spec,
				"inverter_1_make": _make(i1_make, "Inverter"),
				"inverter_1_capacity_kw": i1_kw,
				"inverter_1_count": i1_n,
				"inverter_2_specification": i2_spec,
				"inverter_2_make": _make(i2_make, "Inverter"),
				"inverter_2_capacity_kw": i2_kw,
				"inverter_2_count": i2_n,
				"solar_energy_meter_count": meters,
				"earthing_sets": earthing,
				"lightning_protection_sets": la,
				"dcdb_specification": "With PV fuses at input, DC isolator and Type 2 DC SPD in IP65 rated enclosure",
				"acdb_specification": "With MCB and Type 2 AC SPD in PC/ABS/CRCA IP54 rated enclosure",
				"dc_cable_specification": "UV rated solar copper cable with e-beam cross linked sheath and insulation",
				"ac_cable_specification": "PVC/XLPE aluminium",
				"mounting_structure_specification": "Epoxy coated GI tubes for flat roof",
				"warranty_years": 5,
				"is_active": 1,
				"company": company,
			}
		)


def _make(make_name, component_type):
	if not make_name:
		return None
	return frappe.db.get_value("Component Make", {"make_name": make_name, "component_type": component_type}, "name")


# -------------------------------------------------------------------- settings
#: Fieldnames already initialised on the settings singleton, stored as a Frappe default.
#: A Check field defaults to 0 in the database, so "is it empty?" cannot distinguish a
#: never-initialised field from one the user deliberately switched off. Recording what has
#: been initialised is the only way to backfill a new Check field exactly once - and
#: getting this wrong left the serial uniqueness guard silently disabled.
INITIALISED_KEY = "a3_sola_initialised_settings_fields"

SKIP_FIELDTYPES = ("Table", "Section Break", "Column Break", "Tab Break", "HTML", "Attach", "Attach Image")


def apply_field_defaults(settings):
	"""Backfill defaults for fields added since the singleton was created, exactly once.

	A doctype default applies to NEW documents only, so every field a later phase adds to
	the settings singleton would otherwise stay empty - and a mandatory one would break the
	next save. Phases 3 to 7 add more tabs here; this keeps that safe.
	"""
	initialised = set(filter(None, (frappe.db.get_default(INITIALISED_KEY) or "").split(",")))
	filled = []

	for field in settings.meta.fields:
		if not field.default or field.fieldtype in SKIP_FIELDTYPES:
			continue
		if field.fieldname in initialised:
			continue
		current = settings.get(field.fieldname)
		is_empty = current in (None, "") or (field.fieldtype == "Check" and not current)
		if is_empty:
			settings.set(field.fieldname, field.default)
			filled.append(field.fieldname)
		initialised.add(field.fieldname)

	frappe.db.set_default(INITIALISED_KEY, ",".join(sorted(initialised)))
	return filled


def seed_settings():
	"""Populate the singleton with defaults and the client's proposal text blocks."""
	settings = frappe.get_single("A3 Sola Settings")
	company = default_company()
	apply_field_defaults(settings)

	defaults = {
		"product_name": "Renewcore Innovations LLP",
		"brand_website": "https://www.renewcoreinnovations.com",
		"default_discom": frappe.db.get_value("DISCOM", {"discom_name": "KSEB"}, "name"),
		"default_subsidy_scheme": frappe.db.get_value(
			"Subsidy Scheme", {"scheme_name": "PM Surya Ghar: Muft Bijli Yojana"}, "name"
		),
		"default_tariff": frappe.db.get_value("Electricity Tariff", {"tariff_name": "KSEB Domestic Bimonthly"}, "name"),
		"default_fee_schedule": frappe.db.get_value(
			"Statutory Fee Schedule", {"schedule_name": "KSEB 2026-27"}, "name"
		),
		"covering_letter_text": seed_data.PROPOSAL_COVERING_LETTER,
		"terms_and_conditions_text": seed_data.PROPOSAL_TERMS,
		"delivery_schedule_text": seed_data.PROPOSAL_DELIVERY_SCHEDULE,
		"subsidy_note_text": seed_data.SUBSIDY_NOTE,
		"gst_treatment_note": seed_data.GST_NOTE,
		"company_scope_label": "Our Scope",
		"customer_scope_label": "Client's Scope",
		"outreach_signature": "Best regards,\n\nRenewcore Innovations LLP",
	}
	for field, value in defaults.items():
		if value and not settings.get(field):
			settings.set(field, value)

	if not settings.scope_of_work:
		for index, (responsibility, category, text) in enumerate(seed_data.SCOPE_OF_WORK, start=1):
			settings.append(
				"scope_of_work",
				{
					"responsibility": responsibility,
					"category": category,
					"scope_text": text,
					"display_order": index,
				},
			)

	if not settings.brand_social_links:
		for index, (label, url) in enumerate(seed_data.BRAND_LINKS, start=1):
			settings.append(
				"brand_social_links",
				{"link_label": label, "link_url": url, "display_order": index, "show_in_message": 1},
			)

	if not settings.outreach_cadence:
		cadence = [
			("Step 1: First Contact", 0, "First Contact"),
			("Step 2: 24hr Nudge", 1, "24 Hour Nudge"),
			("Step 3: Value/ROI", 3, "Value and ROI"),
			("Step 4: Breakup/Close", 5, "Breakup and Close"),
			("Completed: Proposal Sent", 3, "Proposal Sent"),
		]
		for step, offset, template_title in cadence:
			settings.append(
				"outreach_cadence",
				{
					"step_name": step,
					"offset_days_from_previous": offset,
					"message_template": frappe.db.get_value(
						"Outreach Message Template", {"template_name": template_title}, "name"
					),
					"is_terminal": 1 if step == "Step 4: Breakup/Close" else 0,
				},
			)

	settings.flags.ignore_permissions = True
	settings.save(ignore_permissions=True)
	if company:
		frappe.db.set_default("company", company)
