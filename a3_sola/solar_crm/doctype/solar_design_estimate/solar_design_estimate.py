# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The analytical heart of Phase 1.

Every number on this document is computed by `a3_sola.api.*` and none is typed. In
particular no statutory fee, warranty term, regulatory threshold or yield figure may
appear as a literal here — they each have exactly one home and this document reads them.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from a3_sola.api import calculations, regulation, statutory
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_float
from a3_sola.solar_crm.doctype.solar_package.solar_package import (
	default_inverter,
	default_module,
	default_price,
	default_prices,
)

#: What a lead's consumption is assumed to be quoted against, since a lead records no
#: billing cycle of its own. Matches the Solar Consumer field default.
DEFAULT_BILLING_FREQUENCY = "Bimonthly"

LINKS = (
	("lead", "Lead"),
	("solar_consumer", "Solar Consumer"),
	("site_survey", "Site Survey"),
	("subsidy_scheme", "Subsidy Scheme"),
	("electricity_tariff", "Electricity Tariff"),
	("solar_package", "Solar Package"),
)


class SolarDesignEstimate(Document):
	def autoname(self):
		set_name(self, "design_series_prefix", ".YYYY.-.#####", fallback="SOL-DSN")

	def validate(self):
		self.resolve_subject()
		assert_same_company(self, LINKS)
		self.load_context()
		self.compute_sizing()
		self.compute_options()
		self.compute_generation_and_savings()
		self.compute_statutory()
		self.check_regulation()
		self.compute_commercials()
		self.validate_dcr()

	# ------------------------------------------------------------------ subject
	def resolve_subject(self):
		"""An estimate is raised against a lead or against its consumer - one is required.

		Early in the funnel there is no consumer yet: the enquiry has a DISCOM, a category
		and a rough bill, and that is enough to size a system and put a number in front of
		somebody. The consumer arrives with the survey, and with it the sanctioned load and
		the billing cycle. Both cases produce the same figures through the same code; the
		lead-only case simply has fewer constraints to bind against.
		"""
		if self.solar_consumer and not self.lead:
			# The consumer already knows the enquiry it came from; keep the chain intact.
			self.lead = frappe.db.get_value("Solar Consumer", self.solar_consumer, "lead")
		self.pull_from_lead()
		if not (self.lead or self.solar_consumer):
			frappe.throw(
				_("Select a Lead or a Solar Consumer for this estimate."),
				frappe.MandatoryError,
				title=_("Nothing to Estimate For"),
			)

	def pull_from_lead(self):
		"""Fill what the lead already knows, so picking a lead is one choice and not five.

		Only into empty fields: a value set on the estimate is a decision somebody made
		here, and re-deriving it from the lead on the next save would quietly undo it.
		"""
		if not self.lead:
			return
		lead = frappe.db.get_value(
			"Lead", self.lead, ["solar_consumer", "subsidy_scheme"], as_dict=True
		)
		if not lead:
			return

		if not self.solar_consumer and lead.solar_consumer:
			self.solar_consumer = lead.solar_consumer
		if not self.subsidy_scheme and lead.subsidy_scheme:
			self.subsidy_scheme = lead.subsidy_scheme

		# The tariff the DISCOM bills this consumer under, from whichever record has one.
		if not self.electricity_tariff:
			self.electricity_tariff = self.tariff_for_subject()

		# The survey, once one has been done for this consumer. The submitted one wins;
		# a draft survey is still being written and should not be quoted against.
		if not self.site_survey and self.solar_consumer:
			surveys = frappe.get_all(
				"Site Survey",
				filters={"solar_consumer": self.solar_consumer, "docstatus": ("<", 2)},
				fields=["name"], order_by="docstatus desc, creation desc", limit=1,
			)
			if surveys:
				self.site_survey = surveys[0].name

	def tariff_for_subject(self):
		"""The electricity tariff to size savings against, or None to leave it unset."""
		discom = None
		if self.solar_consumer:
			discom = frappe.db.get_value("Solar Consumer", self.solar_consumer, "discom")
		if not discom and self.lead:
			discom = frappe.db.get_value("Lead", self.lead, "discom")
		filters = {"is_active": 1} if frappe.get_meta("Electricity Tariff").has_field("is_active") else {}
		if discom and frappe.get_meta("Electricity Tariff").has_field("discom"):
			filters["discom"] = discom
		rows = frappe.get_all("Electricity Tariff", filters=filters, pluck="name",
		                      order_by="modified desc", limit=1)
		if not rows and filters:
			rows = frappe.get_all("Electricity Tariff", pluck="name", order_by="modified desc", limit=1)
		return rows[0] if rows else None

	def subject_context(self):
		"""The sizing inputs, from the consumer where there is one and the lead otherwise.

		Returned as one shape either way, so nothing downstream has to ask which it got.
		A lead carries its consumption per billing cycle rather than per year, and has no
		sanctioned load, so roof area and sanctioned load simply do not bind yet.
		"""
		if self.solar_consumer:
			c = frappe.get_cached_doc("Solar Consumer", self.solar_consumer)
			return frappe._dict(
				annual_consumption_units=flt(c.annual_consumption_units),
				consumer_category=c.consumer_category,
				connection_type=c.connection_type,
				discom=c.discom,
				discom_section=c.discom_section,
				sanctioned_load_kw=flt(c.sanctioned_load_kw),
				billing_frequency=c.billing_frequency,
			)

		lead = frappe.get_cached_doc("Lead", self.lead)
		cycles = 12 if (lead.get("billing_frequency") or DEFAULT_BILLING_FREQUENCY) == "Monthly" else 6
		return frappe._dict(
			annual_consumption_units=flt(lead.get("approx_consumption_units")) * cycles,
			consumer_category=lead.get("consumer_category"),
			connection_type=lead.get("connection_type"),
			discom=lead.get("discom"),
			discom_section=lead.get("discom_section"),
			# A lead has no sanctioned load on record, so that constraint does not bind.
			sanctioned_load_kw=0.0,
			billing_frequency=DEFAULT_BILLING_FREQUENCY,
		)

	# ------------------------------------------------------------------ context
	def load_context(self):
		self.subject = self.subject_context()
		self.survey = frappe.get_cached_doc("Site Survey", self.site_survey) if self.site_survey else None
		self.annual_consumption_units = flt(self.subject.annual_consumption_units)
		self.consumer_category = self.subject.consumer_category
		if not self.connection_type:
			self.connection_type = self.subject.connection_type
		if not self.specific_yield:
			override = 0.0
			if self.subject.discom_section:
				override = flt(
					frappe.db.get_value("DISCOM Section", self.subject.discom_section, "specific_yield_override")
				)
			self.specific_yield = override or get_float("default_specific_yield", 1500.0)
		self.average_shading_percent = flt(self.survey.average_shading_percent) if self.survey else 0.0

	# ------------------------------------------------------------------ sizing
	def compute_sizing(self):
		"""Constrain to the lower of consumption, roof and sanctioned load; name the binder."""
		roof_kw = flt(self.survey.total_usable_kw) if self.survey else 0.0
		sanctioned_kw = flt(self.subject.sanctioned_load_kw)

		sizing = calculations.recommend_capacity(
			self.annual_consumption_units, roof_kw, sanctioned_kw, self.specific_yield
		)
		self.consumption_based_capacity_kw = sizing["consumption_kw"]
		self.roof_limited_capacity_kw = sizing["roof_kw"]
		self.sanctioned_load_capacity_kw = sizing["sanctioned_kw"]
		self.recommended_capacity_kw = sizing["recommended_kw"]
		self.binding_constraint = sizing["binding_constraint"]

		if self.binding_constraint and not self.flags.in_test:
			frappe.msgprint(
				_("Sizing is bound by {0} at {1} kW.").format(
					frappe.bold(self.binding_constraint), self.recommended_capacity_kw
				),
				indicator="blue",
				alert=True,
			)

		if flt(self.override_capacity_kw):
			if roof_kw and flt(self.override_capacity_kw) > roof_kw:
				frappe.throw(
					_("Override of {0} kW exceeds the usable roof capacity of {1} kW from survey {2}.").format(
						self.override_capacity_kw, roof_kw, self.site_survey
					),
					title=_("Override Exceeds Roof"),
				)
			if sanctioned_kw and flt(self.override_capacity_kw) > sanctioned_kw:
				frappe.msgprint(
					_("Override of {0} kW exceeds the sanctioned load of {1} kW. A load enhancement will be required.").format(
						self.override_capacity_kw, sanctioned_kw
					),
					title=_("Above Sanctioned Load"),
					indicator="orange",
				)
			self.final_capacity_kw = flt(self.override_capacity_kw, 3)
		else:
			self.final_capacity_kw = self.recommended_capacity_kw

	# ------------------------------------------------------------------ options
	def compute_options(self):
		"""Roll each option's total and fetch its warranty from the make. Never typed."""
		self.seed_option_from_package()
		recommended = [row for row in self.options if row.is_recommended]
		if len(recommended) > 1:
			frappe.throw(
				_("Exactly one option may be flagged recommended; {0} are.").format(len(recommended)),
				title=_("Multiple Recommended Options"),
			)
		if self.options and not recommended:
			self.options[0].is_recommended = 1
			recommended = [self.options[0]]

		self.resolve_option_components()
		self.number_options()
		for row in self.options:
			row.total_option_cost = flt(row.system_cost) + flt(row.additional_structure_cost)
			if row.inverter_make:
				row.inverter_warranty_years = (
					frappe.db.get_value("Component Make", row.inverter_make, "product_warranty_years") or 0
				)

		self.recommended_option = recommended[0].option_name if recommended else None
		self.build_quoted_options()

	def recommended_row(self):
		for row in self.options:
			if row.is_recommended:
				return row
		return self.options[0] if self.options else None

	def resolve_option_components(self):
		"""Fill each option from the component and make chosen on it.

		A row states a component type and a make; everything priced follows from that.
		The package is the one this estimate is built on, narrowed to a package that
		actually carries that make where more than one is on file, and the cost is the
		package's price for that make. None of it is typed, so a price cannot drift from
		the package it is supposed to have come from.
		"""
		for row in self.options:
			if not row.component_make:
				continue
			make = frappe.db.get_value(
				"Component Make", row.component_make,
				["make_name", "component_type", "technology", "product_warranty_years"], as_dict=True,
			)
			if not make:
				continue
			if not row.component_type:
				row.component_type = make.component_type
			row.technology = make.technology

			package = package_for_component(
				row.component_make, make.component_type, self.solar_package,
				self.capacity_for_package(), self.connection_type,
			)
			if package:
				row.solar_package = package
			cost = package_price_for_make(row.solar_package, make.component_type, make.make_name)
			if cost is not None:
				row.system_cost = cost
			if not row.option_name:
				row.option_name = make.technology or make.make_name

			# The hidden module and inverter fields stay filled: the proposal, the
			# quotation builder and the print format all read them, and they are what a
			# customer-facing document says about the kit. They are no longer typed here.
			if make.component_type == "Inverter":
				row.inverter_make = row.component_make
				row.inverter_specification = make.technology
				row.inverter_count = cint(row.units) or 1
				row.inverter_warranty_years = make.product_warranty_years or 0
			elif make.component_type == "Module":
				row.module_make = row.component_make
				row.module_specification = make.technology
				row.module_count = cint(row.units) or 0

	def capacity_for_package(self):
		return flt(self.final_capacity_kw) or flt(self.override_capacity_kw) or flt(self.recommended_capacity_kw)

	def number_options(self):
		"""Number the options 1, 2, 3 within each component type, in row order.

		The numbering is per type because that is how the quote reads: three inverter
		options are Option 1, 2 and 3, and the modules start again at 1.
		"""
		counters = {}
		for row in self.options:
			key = row.component_type or ""
			counters[key] = counters.get(key, 0) + 1
			row.option_number = counters[key]

	def build_quoted_options(self):
		"""The customer-facing table, rebuilt from the options on every save.

		A presentation of the options and never a second place to type, so it is cleared
		and written fresh rather than merged - there is nothing here to preserve.
		"""
		self.set("quoted_options", [])
		serials, next_serial = {}, 0
		for row in self.options:
			kind = row.component_type or _("Other")
			if kind not in serials:
				next_serial += 1
				serials[kind] = next_serial
			self.append("quoted_options", {
				"sl_no": serials[kind],
				"component_type": kind,
				"option_label": _("Option {0}").format(row.option_number or 1),
				"option_description": row.option_name or row.technology or "",
				"make": frappe.db.get_value("Component Make", row.component_make, "make_name")
				        if row.component_make else "",
				"units": cint(row.units),
				"system_cost": flt(row.system_cost),
			})

	def seed_option_from_package(self):
		"""A package chosen with nothing quoted yet is a priced option waiting to happen.

		Estimating here is picking the predefined package that fits what the survey found,
		not composing a system from parts. So naming the package is enough to get a priced
		option, and the desk's Add Option dialog stays for quoting a second or third one
		beside it. Once anything at all is quoted this steps back and never touches the
		table again - it must not overwrite what somebody priced by hand.
		"""
		if self.options or not self.solar_package:
			return
		package = frappe.get_cached_doc("Solar Package", self.solar_package)
		module = default_module(package)
		inverter = default_inverter(package)
		price = default_price(package) or frappe._dict()
		self.append(
			"options",
			{
				"option_name": _("Option 1 - {0}").format(package.inverter_topology or _("Standard")),
				"inverter_topology": package.inverter_topology or "String",
				"solar_package": package.name,
				"is_recommended": 1,
				"system_cost": flt(price.get("system_cost")),
				"additional_structure_cost": flt(price.get("additional_structure_and_cable_cost")),
				"module_make": module.module_make if module else None,
				"module_specification": module.module_specification if module else None,
				"module_count": module.module_count if module else None,
				"inverter_make": inverter.inverter_make if inverter else None,
				"inverter_specification": inverter.inverter_specification if inverter else None,
				"inverter_count": inverter.inverter_count if inverter else None,
				"display_order": 1,
			},
		)

	# ---------------------------------------------------- generation & savings
	def compute_generation_and_savings(self):
		generation = calculations.estimate_generation(
			self.final_capacity_kw, self.specific_yield, self.average_shading_percent
		)
		self.estimated_annual_generation_kwh = generation["annual_generation_kwh"]
		self.estimated_monthly_generation_kwh = generation["monthly_generation_kwh"]

		band = calculations.estimate_daily_generation_band(
			self.final_capacity_kw, self.subject.discom_section
		)
		self.expected_daily_units_low = band["low_units_per_day"]
		self.expected_daily_units_high = band["high_units_per_day"]

		cycles = 12 if self.subject.billing_frequency == "Monthly" else 6
		self.units_offset_per_cycle = flt(self.estimated_annual_generation_kwh / cycles, 2) if cycles else 0.0

		tariff = self.electricity_tariff
		if tariff and self.annual_consumption_units:
			units_before = self.annual_consumption_units / cycles
			units_after = max(units_before - self.units_offset_per_cycle, 0)
			savings = calculations.calculate_savings(tariff, units_before, units_after)
			self.estimated_annual_savings = flt(savings["saving_amount"] * cycles, 2)
			self.savings_breakdown = json.dumps(savings, indent=1, default=str)
		else:
			self.estimated_annual_savings = 0.0
			self.savings_breakdown = None

	# ---------------------------------------------------------------- statutory
	def compute_statutory(self):
		"""Resolved from the fee schedule. A typed fee is never accepted."""
		fees = statutory.get_statutory_fees(
			self.subject.discom,
			self.connection_type or self.subject.connection_type or "Single Phase",
			self.final_capacity_kw,
			self.net_meter_mode or "Purchased by Customer",
			self.estimate_date,
			self.company,
		)
		self.kseb_application_fee = fees["application_fee_gross"]
		self.kseb_registration_fee = fees["registration_fee_gross"]
		self.kseb_registration_refundable = fees["registration_refundable"]
		self.net_meter_charge = fees["net_meter_charge"]
		self.net_meter_monthly_rental = fees["net_meter_monthly_rental"]
		self.net_meter_allocation_lead_days = fees["net_meter_allocation_lead_days"]
		self.statutory_total = fees["statutory_total"]
		self.statutory_breakdown = json.dumps(fees, indent=1, default=str)

	# --------------------------------------------------------------- regulation
	def check_regulation(self):
		"""Recomputed on every validate, so a lapsed stay changes the estimate without a deploy."""
		result = regulation.check_connection_type(
			self.final_capacity_kw,
			self.connection_type or self.subject.connection_type,
			self.subject.discom,
			self.estimate_date,
			self.company,
		)
		self.connection_type_compliant = 1 if result["compliant"] else 0
		self.required_connection_type = result["required_type"]
		self.regulation_message = result["message"]

		if not result["compliant"]:
			clause = frappe.db.get_value("Grid Regulation Rule", result["rule"], "customer_facing_clause")
			message = frappe.utils.strip_html(clause or "") or result["message"]
			if self.docstatus == 1 or self.flags.submitting:
				frappe.throw(message, title=_("Grid Regulation"))
			frappe.msgprint(message, title=_("Grid Regulation"), indicator="red")
		elif result.get("stayed") and result.get("message") and not self.flags.in_test:
			frappe.msgprint(result["message"], title=_("Grid Regulation Stayed"), indicator="orange")

	def before_submit(self):
		self.flags.submitting = True
		self.check_regulation()

	# -------------------------------------------------------------- commercials
	def compute_commercials(self):
		row = self.recommended_row()
		if row:
			self.gross_system_cost = flt(row.system_cost)
			if not self.solar_package and row.solar_package:
				self.solar_package = row.solar_package
		if self.survey and not flt(self.additional_civil_cost):
			self.additional_civil_cost = flt(self.survey.additional_civil_cost)

		option_extra = flt(row.additional_structure_cost) if row else 0.0
		self.total_project_cost = flt(self.gross_system_cost) + flt(self.additional_civil_cost) + option_extra

		subsidy = calculations.get_subsidy_amount(
			self.subsidy_scheme, self.final_capacity_kw, self.consumer_category
		) if self.subsidy_scheme else {"subsidy_amount": 0.0, "slab_used": None, "message": ""}
		self.applicable_subsidy_amount = flt(subsidy["subsidy_amount"])
		self.subsidy_slab_used = subsidy["slab_used"]

		self.net_cost_to_customer = flt(self.total_project_cost) - flt(self.applicable_subsidy_amount)
		self.cost_per_kw = (
			flt(self.total_project_cost / self.final_capacity_kw, 2) if self.final_capacity_kw else 0.0
		)

		cashflow = calculations.build_cashflow(
			self.total_project_cost,
			self.applicable_subsidy_amount,
			self.estimated_annual_generation_kwh,
			self.estimated_annual_savings,
		)
		self.simple_payback_years = cashflow["simple_payback_years"]
		self.lifetime_savings = cashflow["lifetime_savings"]
		self.set("cashflow", [])
		for entry in cashflow["rows"]:
			self.append("cashflow", entry)

	def validate_dcr(self):
		"""Only fires when a scheme requiring DCR is actually attached.

		A non-DCR package is legitimate for a commercial or unsubsidised job — the client's
		own 10 kWp proposal quotes non-DCR modules — so this must not be a blanket rule.
		"""
		if not self.subsidy_scheme:
			return
		scheme = frappe.get_cached_doc("Subsidy Scheme", self.subsidy_scheme)
		if not scheme.requires_dcr_modules:
			return
		row = self.recommended_row()
		package = (row.solar_package if row else None) or self.solar_package
		if not package:
			return
		if not frappe.db.get_value("Solar Package", package, "is_dcr_compliant"):
			frappe.throw(
				_("Scheme {0} requires DCR modules but package {1} is not DCR compliant.").format(
					frappe.bold(scheme.scheme_name), frappe.bold(package)
				),
				title=_("DCR Mismatch"),
			)

	def on_submit(self):
		# A lead-only estimate has no consumer status to advance yet; the consumer picks
		# the stage up when it is created from the lead.
		if self.solar_consumer:
			frappe.get_doc("Solar Consumer", self.solar_consumer).set_status("Designed")
		self.update_linked_opportunity()

	def update_linked_opportunity(self):
		if not self.solar_consumer:
			return
		opportunity = frappe.db.get_value(
			"Opportunity", {"solar_consumer": self.solar_consumer, "status": ["!=", "Lost"]}, "name"
		)
		if not opportunity:
			return
		frappe.db.set_value(
			"Opportunity",
			opportunity,
			{
				"solar_design_estimate": self.name,
				"capacity_kw": self.final_capacity_kw,
				"opportunity_amount": self.total_project_cost,
			},
			update_modified=False,
		)


@frappe.whitelist()
def compare_packages(design_estimate):
	"""Run the calculation across every active package within +/- 2 kW of the recommendation."""
	doc = frappe.get_doc("Solar Design Estimate", design_estimate)
	doc.check_permission("read")
	target = flt(doc.final_capacity_kw)

	packages = frappe.get_all(
		"Solar Package",
		filters={
			"is_active": 1,
			"company": doc.company,
			"capacity_kw": ["between", [target - 2, target + 2]],
		},
		fields=["name", "specification_code", "package_name", "capacity_kw", "is_dcr_compliant"],
		order_by="capacity_kw",
	)
	# The price is the default configuration's, fetched for the whole comparison at once.
	prices = default_prices([p.name for p in packages])

	rows = []
	for pkg in packages:
		subsidy = (
			calculations.get_subsidy_amount(doc.subsidy_scheme, pkg.capacity_kw, doc.consumer_category)
			if doc.subsidy_scheme
			else {"subsidy_amount": 0.0}
		)
		generation = calculations.estimate_generation(
			pkg.capacity_kw, doc.specific_yield, doc.average_shading_percent
		)
		cost = flt((prices.get(pkg.name) or {}).get("system_cost"))
		net = cost - flt(subsidy["subsidy_amount"])
		annual_savings = (
			flt(doc.estimated_annual_savings) * (flt(pkg.capacity_kw) / flt(doc.final_capacity_kw))
			if doc.final_capacity_kw
			else 0.0
		)
		cashflow = calculations.build_cashflow(cost, subsidy["subsidy_amount"], generation["annual_generation_kwh"], annual_savings)
		rows.append(
			{
				"package": pkg.name,
				"specification_code": pkg.specification_code,
				"capacity_kw": pkg.capacity_kw,
				"is_dcr_compliant": pkg.is_dcr_compliant,
				"cost": cost,
				"subsidy": flt(subsidy["subsidy_amount"]),
				"net_cost": net,
				"annual_generation_kwh": generation["annual_generation_kwh"],
				"annual_savings": flt(annual_savings, 2),
				"payback_years": cashflow["simple_payback_years"],
			}
		)
	return rows


def _price_for(package, module, inverter):
	"""The price row for this module and inverter, whatever boards it names.

	Boards are not part of what the estimate offers - the customer chooses an inverter, not
	a DCDB - so a row matching on the two that are offered is the right answer. Falls back
	to the package's default price, because an option with no price at all is worse than
	one priced as the package normally is.
	"""
	wanted_module = module.module_specification if module else None
	wanted_inverter = inverter.inverter_specification if inverter else None
	for row in package.prices or []:
		if row.module == wanted_module and row.inverter == wanted_inverter:
			return row
	return default_price(package)


@frappe.whitelist()
def add_option_from_package(design_estimate, solar_package, inverter_option="1", option_name=None):
	"""Append a priced option from a package, using one of its inverter options.

	`inverter_option` is the position in the package's inverter table, counting from one -
	it was the 1 or 2 of the old fixed pair, and it now reaches a third option as well.
	Out of range falls back to the package's default rather than failing: the caller is a
	button, and an estimate with the wrong inverter is easier to fix than one that refused.

	This is how a three-option proposal like the client's 10 kWp document gets built in
	three clicks instead of three documents.
	"""
	doc = frappe.get_doc("Solar Design Estimate", design_estimate)
	doc.check_permission("write")
	pkg = frappe.get_cached_doc("Solar Package", solar_package)

	position = cint(inverter_option)
	rows = pkg.inverters or []
	chosen = rows[position - 1] if 0 < position <= len(rows) else default_inverter(pkg)
	module = default_module(pkg)
	# The price of the configuration this option names, not of the package.
	price = _price_for(pkg, module, chosen) or frappe._dict()

	doc.append(
		"options",
		{
			"option_name": option_name or f"Option {len(doc.options) + 1} - {pkg.inverter_topology}",
			"inverter_topology": pkg.inverter_topology,
			"solar_package": pkg.name,
			"module_make": module.module_make if module else None,
			"module_specification": module.module_specification if module else None,
			"module_count": module.module_count if module else None,
			"inverter_make": chosen.inverter_make if chosen else None,
			"inverter_specification": chosen.inverter_specification if chosen else None,
			"inverter_count": chosen.inverter_count if chosen else None,
			"system_cost": flt(price.get("system_cost")),
			"additional_structure_cost": flt(price.get("additional_structure_and_cable_cost")),
			"display_order": len(doc.options) + 1,
			"is_recommended": 1 if not doc.options else 0,
		},
	)
	doc.save()
	return doc.name


def package_for_component(component_make, component_type, current_package, capacity_kw, connection_type):
	"""The package to price this component against.

	The estimate's own package when it already carries this make, because that is the
	system being quoted. Otherwise a package of the same size and phase that does carry
	it - a microinverter option is a different package from a string one, and choosing
	the make is how a person picks between them.
	"""
	if current_package and _package_has_make(current_package, component_make):
		return current_package

	filters = {"is_active": 1}
	if capacity_kw:
		filters["capacity_kw"] = capacity_kw
	if connection_type:
		filters["connection_type"] = connection_type
	candidates = frappe.get_all("Solar Package", filters=filters, pluck="name",
	                            order_by="modified desc", limit_page_length=0)
	for name in candidates:
		if _package_has_make(name, component_make):
			return name
	return current_package


def _package_has_make(package, component_make):
	return bool(frappe.db.exists(
		"Solar Package Component", {"parent": package, "make": component_make}
	))


#: Which column of a package's price row carries which component type's make.
PRICE_COLUMN = {
	"Module": "module", "Inverter": "inverter", "DCDB": "dcdb",
	"ACDB": "acdb", "Energy Meter": "energy_meter",
}


def package_price_for_make(package, component_type, make_name):
	"""The package's system cost for this make, or None when it does not price it.

	A package's price rows are one per combination of makes, so the cost of choosing
	Solinteg over SolarEdge is a different row rather than a different package. None
	rather than zero when nothing matches: zero is a price, and a missing price is not.
	"""
	if not package or not make_name:
		return None
	column = PRICE_COLUMN.get(component_type)
	if not column:
		return None
	rows = frappe.get_all(
		"Solar Package Price", filters={"parent": package, column: make_name},
		fields=["system_cost"], order_by="idx", limit=1,
	)
	return flt(rows[0].system_cost) if rows else None
