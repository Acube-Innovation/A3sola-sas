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
from frappe.utils import flt

from a3_sola.api import calculations, regulation, statutory
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_float

LINKS = (
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
		assert_same_company(self, LINKS)
		self.load_context()
		self.compute_sizing()
		self.compute_options()
		self.compute_generation_and_savings()
		self.compute_statutory()
		self.check_regulation()
		self.compute_commercials()
		self.validate_dcr()

	# ------------------------------------------------------------------ context
	def load_context(self):
		self.consumer = frappe.get_cached_doc("Solar Consumer", self.solar_consumer)
		self.survey = frappe.get_cached_doc("Site Survey", self.site_survey) if self.site_survey else None
		self.annual_consumption_units = flt(self.consumer.annual_consumption_units)
		self.consumer_category = self.consumer.consumer_category
		if not self.connection_type:
			self.connection_type = self.consumer.connection_type
		if not self.specific_yield:
			override = 0.0
			if self.consumer.discom_section:
				override = flt(
					frappe.db.get_value("DISCOM Section", self.consumer.discom_section, "specific_yield_override")
				)
			self.specific_yield = override or get_float("default_specific_yield", 1500.0)
		self.average_shading_percent = flt(self.survey.average_shading_percent) if self.survey else 0.0

	# ------------------------------------------------------------------ sizing
	def compute_sizing(self):
		"""Constrain to the lower of consumption, roof and sanctioned load; name the binder."""
		roof_kw = flt(self.survey.total_usable_kw) if self.survey else 0.0
		sanctioned_kw = flt(self.consumer.sanctioned_load_kw)

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
		recommended = [row for row in self.options if row.is_recommended]
		if len(recommended) > 1:
			frappe.throw(
				_("Exactly one option may be flagged recommended; {0} are.").format(len(recommended)),
				title=_("Multiple Recommended Options"),
			)
		if self.options and not recommended:
			self.options[0].is_recommended = 1
			recommended = [self.options[0]]

		for row in self.options:
			row.total_option_cost = flt(row.system_cost) + flt(row.additional_structure_cost)
			if row.inverter_make:
				row.inverter_warranty_years = (
					frappe.db.get_value("Component Make", row.inverter_make, "product_warranty_years") or 0
				)

		self.recommended_option = recommended[0].option_name if recommended else None

	def recommended_row(self):
		for row in self.options:
			if row.is_recommended:
				return row
		return self.options[0] if self.options else None

	# ---------------------------------------------------- generation & savings
	def compute_generation_and_savings(self):
		generation = calculations.estimate_generation(
			self.final_capacity_kw, self.specific_yield, self.average_shading_percent
		)
		self.estimated_annual_generation_kwh = generation["annual_generation_kwh"]
		self.estimated_monthly_generation_kwh = generation["monthly_generation_kwh"]

		band = calculations.estimate_daily_generation_band(
			self.final_capacity_kw, self.consumer.discom_section
		)
		self.expected_daily_units_low = band["low_units_per_day"]
		self.expected_daily_units_high = band["high_units_per_day"]

		cycles = 12 if self.consumer.billing_frequency == "Monthly" else 6
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
			self.consumer.discom,
			self.connection_type or self.consumer.connection_type or "Single Phase",
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
			self.connection_type or self.consumer.connection_type,
			self.consumer.discom,
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
		frappe.get_doc("Solar Consumer", self.solar_consumer).set_status("Designed")
		self.update_linked_opportunity()

	def update_linked_opportunity(self):
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
		fields=["name", "specification_code", "package_name", "capacity_kw", "cost_option_1", "is_dcr_compliant"],
		order_by="capacity_kw",
	)

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
		cost = flt(pkg.cost_option_1)
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


@frappe.whitelist()
def add_option_from_package(design_estimate, solar_package, inverter_option="1", option_name=None):
	"""Append a priced option from a package, using inverter option 1 or 2.

	This is how a three-option proposal like the client's 10 kWp document gets built in
	three clicks instead of three documents.
	"""
	doc = frappe.get_doc("Solar Design Estimate", design_estimate)
	doc.check_permission("write")
	pkg = frappe.get_cached_doc("Solar Package", solar_package)

	suffix = str(inverter_option)
	make = pkg.get(f"inverter_{suffix}_make")
	spec = pkg.get(f"inverter_{suffix}_specification")
	count = pkg.get(f"inverter_{suffix}_count")
	cost = flt(pkg.cost_option_2) if suffix == "2" and flt(pkg.cost_option_2) else flt(pkg.cost_option_1)

	doc.append(
		"options",
		{
			"option_name": option_name or f"Option {len(doc.options) + 1} - {pkg.inverter_topology}",
			"inverter_topology": pkg.inverter_topology,
			"solar_package": pkg.name,
			"module_make": pkg.module_make,
			"module_specification": pkg.module_specification,
			"module_count": pkg.module_count,
			"inverter_make": make,
			"inverter_specification": spec,
			"inverter_count": count,
			"system_cost": cost,
			"additional_structure_cost": flt(pkg.additional_structure_and_cable_cost),
			"display_order": len(doc.options) + 1,
			"is_recommended": 1 if not doc.options else 0,
		},
	)
	doc.save()
	return doc.name
