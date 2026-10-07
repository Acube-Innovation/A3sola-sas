# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The analytical heart of Phase 1.

Every number on this document is computed by `a3_sola.api.*` and none is typed. In
particular no statutory fee, warranty term, regulatory threshold or yield figure may
appear as a literal here — they each have exactly one home and this document reads them.
"""

import json
import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from a3_sola.api import calculations, regulation, statutory
from a3_sola.api.expenses import fill_expense_tables
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_float, get_value
from a3_sola.solar_crm.doctype.balance_of_system_package.balance_of_system_package import package_for
from a3_sola.solar_crm.doctype.component_technology.component_technology import technology_name
from a3_sola.solar_crm.doctype.solar_package.solar_package import (
	default_inverter,
	default_module,
	default_price,
	default_prices,
	default_system_items,
	inverter_phase,
	inverters_for_phase,
	package_phases,
)

#: The package and sizing fields a sizing option row carries, and the recommended row sets.
SIZING_FIELDS = (
	"connection_type", "override_capacity_kw", "subsidy_option", "subsidy_scheme", "solar_package", "system_type",
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
		self.apply_sizing_options()
		self.resolve_subject()
		assert_same_company(self, LINKS)
		self.load_context()
		self.compute_sizing()
		self.fill_from_package()
		self.compute_panels()
		self.compute_inverters()
		self.compute_batteries()
		self.compute_balance_of_system()
		self.price_equipment()
		self.compute_options()
		self.compute_generation_and_savings()
		self.compute_statutory()
		self.compute_expenses()
		self.build_quoted_options()
		self.check_regulation()
		self.compute_commercials()
		self.validate_subsidy_conditions()

	# ---------------------------------------------------------- sizing options
	def apply_sizing_options(self):
		"""Make the recommended sizing option the estimate's own package and sizing.

		An estimate may offer several combinations of package and sizing side by side. The
		system, the commercials and every check are worked out for one of them - the
		recommended row - so its values are copied into the header fields that all of that
		already reads. An estimate with no rows yet gets one from its header, so the table
		always says what the estimate is built on.
		"""
		if not self.get("sizing_options"):
			if self.solar_package or flt(self.override_capacity_kw) or self.connection_type:
				self.append("sizing_options", {field: self.get(field) for field in SIZING_FIELDS})
				self.sizing_options[0].is_recommended = 1
			return

		recommended = [row for row in self.sizing_options if row.is_recommended]
		if len(recommended) > 1:
			frappe.throw(
				_("Only one sizing option can be recommended; rows {0} are.").format(
					", ".join(str(row.idx) for row in recommended)
				),
				title=_("Sizing Options"),
			)
		if not recommended:
			self.sizing_options[0].is_recommended = 1
			recommended = [self.sizing_options[0]]

		problems = []
		for row in self.sizing_options:
			if row.subsidy_option != "With Subsidy":
				row.subsidy_scheme = None
			elif row.system_type == "Off-Grid":
				problems.append(_("Row {0}: with subsidy, the system cannot be Off-Grid.").format(row.idx))
			if flt(row.override_capacity_kw) < 0:
				problems.append(_("Row {0}: capacity cannot be negative.").format(row.idx))
			if row.solar_package and row.connection_type:
				phases = package_phases(row.solar_package)
				if phases and row.connection_type not in phases:
					problems.append(_("Row {0}: package {1} has no {2} inverter; it is for {3}.").format(
						row.idx, row.solar_package, row.connection_type, " / ".join(sorted(phases))))
		if problems:
			frappe.throw("<br>".join(problems), title=_("Sizing Options"))

		for field in SIZING_FIELDS:
			self.set(field, recommended[0].get(field))

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
		if self.subsidy_option == "Without Subsidy":
			# An unsubsidised job carries no scheme, so nothing downstream prices one in.
			self.subsidy_scheme = None
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
		if not self.subsidy_scheme and lead.subsidy_scheme and self.subsidy_option != "Without Subsidy":
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
				tariff_category=c.tariff_category,
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
			# A lead records no tariff category; it arrives with the consumer.
			tariff_category=None,
		)

	# ------------------------------------------------------------------ context
	def load_context(self):
		self.subject = self.subject_context()
		self.survey = frappe.get_cached_doc("Site Survey", self.site_survey) if self.site_survey else None
		self.annual_consumption_units = flt(self.subject.annual_consumption_units)
		self.consumer_category = self.subject.consumer_category
		self.tariff_category = self.subject.tariff_category
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
		if not self.roof_type:
			self.roof_type = (self.survey.get("roof_type") if self.survey else None) or (
				frappe.db.get_value("Solar Consumer", self.solar_consumer, "roof_type") if self.solar_consumer else None
			)

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
	def fill_from_package(self):
		"""Start the System & Options tables from the chosen package's default kit.

		Picking a package on the details step is picking its panels and inverter, so the
		system step should open with them in place rather than empty. Done once per package
		choice - `equipment_package` remembers which package the tables were filled from -
		so rows changed or removed afterwards stay as left, and choosing a different package
		replaces them with that package's kit. Counts and amounts are then worked out as for
		any typed row; the panel and inverter counts are the package's.
		"""
		if not self.solar_package or self.equipment_package == self.solar_package:
			return
		package = frappe.get_cached_doc("Solar Package", self.solar_package)

		def make_of(name):
			if not name:
				return None
			return frappe.db.get_value("Component Make", name, ["technology", "is_dcr"], as_dict=True)

		module = default_module(package)
		module_make = make_of(module.module_make) if module else None
		self.set("panels", [])
		if module and module_make and module_make.technology and flt(module.module_wattage):
			self.append("panels", {
				"panel_type": "DCR" if module_make.is_dcr or package.is_dcr_compliant else "Non-DCR",
				"panel_capacity_wp": module.module_wattage,
				"panel_count": cint(module.module_count) or None,
				"panel_variant": module_make.technology,
				"panel_make": module.module_make,
			})

		# The package's default inverter for this connection, else the first of its phase.
		matching = inverters_for_phase(package, self.connection_type)
		inverter = next((row for row in matching if row.is_default), None) or (matching[0] if matching else None)
		inverter_make = make_of(inverter.inverter_make) if inverter else None
		self.set("inverters", [])
		if inverter and inverter_make and inverter_make.technology and flt(inverter.inverter_capacity_kw):
			self.append("inverters", {
				"inverter_type": inverter_make.technology,
				"inverter_capacity_kw": inverter.inverter_capacity_kw,
				"inverter_count": cint(inverter.inverter_count) or None,
				"inverter_phase": inverter_phase(package, inverter) or None,
				"inverter_make": inverter.inverter_make,
			})

		if self.system_type in ("Off-Grid", "Hybrid"):
			self.set("batteries", [])
			for row in package.get("batteries") or []:
				values = row.as_dict()
				for key in ("name", "parent", "parentfield", "parenttype", "idx", "doctype", "owner", "creation", "modified", "modified_by", "docstatus"):
					values.pop(key, None)
				self.append("batteries", values)

		# The balance of system follows the inverter it is filled for, below.
		self.bos_basis = None
		self.equipment_package = self.solar_package

	def compute_panels(self):
		"""Panels needed to reach the proposed size, always rounded up (18.15 is 19), unless
		the row says how many."""
		for row in self.get("panels"):
			mismatch = make_mismatch(row.panel_make, row.panel_variant)
			if mismatch:
				frappe.throw(
					_("Solar panel row {0}: {1}").format(row.idx, mismatch), title=_("Panel Make Mismatch")
				)
			if row.panel_make and not row.panel_type:
				is_dcr = frappe.db.get_value("Component Make", row.panel_make, "is_dcr")
				row.panel_type = "DCR" if is_dcr else "Non-DCR"
			# A count typed on the row stands; otherwise enough panels to reach the proposed size.
			row.nos = cint(row.panel_count) or unit_count(flt(self.final_capacity_kw) * 1000, row.panel_capacity_wp)
			row.total_capacity_kwp = flt(cint(row.nos) * flt(row.panel_capacity_wp) / 1000, 3)

	def compute_inverters(self):
		"""Inverters to carry the panels, sized and phased within the limits in settings.

		Each row is counted against the whole array: total panel capacity over the row's
		capacity, rounded up. The row's total must then sit between the min and max factor
		of the panel capacity, and each inverter's phase must suit the consumer's connection.
		"""
		if not self.get("inverters"):
			return
		panel_kwp = self.panel_capacity_kwp()
		min_factor = get_float("inverter_min_capacity_factor", 0.85)
		max_factor = get_float("inverter_max_capacity_factor", 2.0)
		phase_limit = get_float("single_phase_inverter_max_kw", 5.0)

		problems = []
		for row in self.inverters:
			# A count typed on the row (or carried from the package) stands.
			row.nos = cint(row.inverter_count) or unit_count(panel_kwp, row.inverter_capacity_kw)
			row.total_capacity_kw = flt(cint(row.nos) * flt(row.inverter_capacity_kw), 3)
			# The phase limit is per inverter: 7 x 1 kW micros are seven small units.
			unit_kw = flt(row.inverter_capacity_kw)
			if not row.inverter_phase:
				above = unit_kw > phase_limit
				row.inverter_phase = "Three Phase" if self.connection_type == "Three Phase" and above else "Single Phase"

			mismatch = make_mismatch(row.inverter_make, row.inverter_type)
			if mismatch:
				problems.append(_("Row {0}: {1}").format(row.idx, mismatch))

			if panel_kwp:
				low, high = flt(panel_kwp * min_factor, 3), flt(panel_kwp * max_factor, 3)
				if not (low <= flt(row.total_capacity_kw) <= high):
					problems.append(
						_("Row {0}: {1} kW of inverters is outside {2} to {3} kW for {4} kWp of panels.").format(
							row.idx, row.total_capacity_kw, low, high, panel_kwp
						)
					)

			if self.connection_type == "Single Phase":
				if row.inverter_phase != "Single Phase":
					problems.append(_("Row {0}: a single phase user needs a single phase inverter.").format(row.idx))
				if unit_kw > phase_limit:
					problems.append(
						_("Row {0}: a single phase user is allowed inverters up to {1} kW; this is {2} kW.").format(
							row.idx, phase_limit, unit_kw
						)
					)
			elif self.connection_type == "Three Phase":
				if unit_kw > phase_limit and row.inverter_phase != "Three Phase":
					problems.append(
						_("Row {0}: an inverter above {1} kW for a three phase user must be three phase.").format(
							row.idx, phase_limit
						)
					)

		if problems:
			frappe.throw("<br>".join(problems), title=_("Inverter Sizing"))

	def panel_capacity_kwp(self):
		"""Total capacity of the panels designed in, in kWp."""
		return flt(sum(flt(row.total_capacity_kwp) for row in self.get("panels")), 3)

	def inverter_capacity_kw(self):
		"""Total capacity of the first inverter row, which the whole design follows."""
		inverter = next((row for row in self.get("inverters") if flt(row.total_capacity_kw)), None)
		return flt(inverter.total_capacity_kw) if inverter else 0.0

	def compute_batteries(self):
		"""Batteries belong to off-grid and hybrid systems only; the count is typed."""
		if not self.get("batteries"):
			return
		if self.system_type not in ("Off-Grid", "Hybrid"):
			# The section is hidden for On-Grid, so rows left behind would be invisible.
			self.set("batteries", [])
			frappe.msgprint(
				_("Batteries removed: they apply only to Off-Grid and Hybrid systems."),
				title=_("Battery"),
				indicator="orange",
			)
			return
		for row in self.batteries:
			mismatch = make_mismatch(row.battery_make, row.battery_variant)
			if mismatch:
				frappe.throw(_("Battery row {0}: {1}").format(row.idx, mismatch), title=_("Battery Make Mismatch"))
			if not row.battery_phase:
				row.battery_phase = self.connection_type or "Single Phase"
			row.total_energy_kwh = flt(
				flt(row.battery_voltage) * flt(row.battery_capacity_ah) * cint(row.nos) / 1000, 3
			)

	def compute_balance_of_system(self):
		"""Copy the Balance of System Package for the first inverter's type and capacity.

		The package is the one whose inverter capacity band holds this design's inverter
		capacity (the first inverter row's units times its kW), so a 3 kW and a 10 kW job get
		the cables, DB and earthing sized for each. Refilled only when the package or the
		inverter phase changes, so edits made here to specifications or numbers survive every
		other save. The Solar Energy Meter row taken is the one of the inverter's phase.
		"""
		inverter = next((row for row in self.get("inverters") if row.inverter_type), None)
		if not inverter:
			return
		capacity = flt(inverter.total_capacity_kw) or flt(inverter.inverter_capacity_kw)
		package = package_for(inverter.inverter_type, self.company, capacity)
		if not package and self.solar_package:
			# No package for this inverter capacity: the chosen solar package's own balance
			# of system is the next best answer, and better than an empty section.
			self.fill_bos_from_solar_package(inverter)
			return
		if not package:
			self.bos_package = None
			self.bos_basis = None
			self.set("bos_items", [])
			if not self.flags.in_test:
				frappe.msgprint(
					_("No active Balance of System Package for inverter type {0} at {1} kW.").format(
						frappe.bold(technology_name(inverter.inverter_type)), "{0:g}".format(capacity)
					),
					title=_("Balance of System"),
					indicator="orange",
				)
			return

		basis = f"{package}|{inverter.inverter_phase or ''}"
		if basis == self.bos_basis and self.get("bos_items"):
			return
		self.bos_package = package
		self.bos_basis = basis
		self.set("bos_items", [])
		for item in frappe.get_doc("Balance of System Package", package).items:
			if item.phase and item.phase != inverter.inverter_phase:
				continue
			self.append(
				"bos_items",
				{
					"item": item.item,
					"phase": item.phase,
					"specification": item.specification,
					"make": item.make,
					"numbers": item.numbers,
				},
			)

	def fill_bos_from_solar_package(self, inverter):
		"""The solar package's default balance-of-system parts, one per type, as BOS rows.

		Refilled, like the BOS package, only when its basis changes, so edits survive saves.
		"""
		basis = f"solar-package:{self.solar_package}|{inverter.inverter_phase or ''}"
		if basis == self.bos_basis and self.get("bos_items"):
			return
		options = frappe.get_meta("Design Estimate BOS Item").get_field("item").options or ""
		allowed = {o for o in options.split("\n") if o}
		self.bos_package = None
		self.bos_basis = basis
		self.set("bos_items", [])
		for item, row in default_system_items(self.solar_package).items():
			if item not in allowed:
				continue
			self.append("bos_items", {
				"item": item,
				"phase": (inverter.inverter_phase or self.connection_type) if item == "Solar Energy Meter" else None,
				"specification": row.specification,
				"make": row.make,
				"numbers": row.qty,
			})

	def price_equipment(self):
		"""Each equipment row's amount is its rate times its count.

		A row with no rate of its own is priced from the backend: a panel at the solar
		package's rate for that module, an inverter at the package's rate for that inverter,
		a balance-of-system part at its Balance of System Package's rate. A rate typed on
		the row is the row's and is kept; clearing it brings the backend price back.
		"""
		self.price_rows_from_backend()
		for table, count in EQUIPMENT_COUNT.items():
			for row in self.get(table):
				row.amount = flt(flt(row.rate) * flt(row.get(count)), 2)

	def price_rows_from_backend(self):
		# Read fresh, not from the cache: these are prices, and a stale copy prices wrongly.
		package = frappe.get_doc("Solar Package", self.solar_package) if self.solar_package else None
		if package:
			modules = package.get("modules") or []
			for row in self.get("panels"):
				if flt(row.rate):
					continue
				match = (
					next((m for m in modules if m.module_make == row.panel_make
						and flt(m.module_wattage) == flt(row.panel_capacity_wp)), None)
					or next((m for m in modules if m.module_make == row.panel_make), None)
				)
				if match and flt(match.rate):
					row.rate = flt(match.rate)
			inverters = package.get("inverters") or []
			for row in self.get("inverters"):
				if flt(row.rate):
					continue
				same_make = [i for i in inverters if i.inverter_make == row.inverter_make]
				match = (
					next((i for i in same_make if flt(i.inverter_capacity_kw) == flt(row.inverter_capacity_kw)
						and (not row.inverter_phase or inverter_phase(package, i) == row.inverter_phase)), None)
					or next((i for i in same_make if flt(i.inverter_capacity_kw) == flt(row.inverter_capacity_kw)), None)
				)
				if match and flt(match.unit_rate):
					row.rate = flt(match.unit_rate)

		bos_rates = {}
		if self.bos_package and frappe.db.exists("Balance of System Package", self.bos_package):
			for item in frappe.get_cached_doc("Balance of System Package", self.bos_package).items:
				if flt(item.rate):
					bos_rates.setdefault((item.item, item.phase or ""), flt(item.rate))
		elif package:
			# Filled from the solar package's own parts: their cost is the line's, per its qty.
			for item, part in default_system_items(package).items():
				if flt(part.cost):
					bos_rates[(item, "")] = flt(part.cost) / (flt(part.qty) or 1)
		for row in self.get("bos_items"):
			if flt(row.rate):
				continue
			rate = bos_rates.get((row.item, row.phase or "")) or bos_rates.get((row.item, ""))
			if rate:
				row.rate = rate

	def commercials(self):
		"""Each System & Options table's total, the tax on them and the grand total.

		The additional structure, cable and special discount raised against the estimate
		follow its own tables, the discount taken off. Tax is the Estimate GST % in A3 Sola Settings on everything but the KSEB fees, which
		the fee schedule already resolves gross.
		"""
		lines = [
			{"key": table, "label": label, "amount": flt(sum(flt(row.amount) for row in self.get(table)), 2)}
			for table, label in COMMERCIAL_LINES
			if table != "batteries" or self.get("batteries")
		]
		lines += [
			{"key": key, "label": doctype, "amount": self.linked_charge(doctype) * sign or 0.0}
			for key, doctype, sign in LINKED_CHARGES
		]
		subtotal = flt(sum(line["amount"] for line in lines), 2)
		taxable = flt(subtotal - sum(line["amount"] for line in lines if line["key"] == "kseb_expenses"), 2)
		gst_percent = get_float("estimate_gst_percent", 0.0)
		gst_amount = flt(taxable * gst_percent / 100, 2)
		return {
			"lines": lines,
			"subtotal": subtotal,
			"taxable": taxable,
			"gst_percent": gst_percent,
			"gst_amount": gst_amount,
			"total": flt(subtotal + gst_amount, 2),
		}

	def linked_charge(self, doctype):
		"""The total of the records of `doctype` raised against this estimate."""
		if self.is_new():
			return 0.0
		amounts = frappe.get_all(doctype, filters={"solar_design_estimate": self.name}, pluck="total_amount")
		return flt(sum(flt(a) for a in amounts), 2)

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

		for row in self.options:
			# Rows priced on a whole package carry no make to read a type from; like the
			# seeded option they are the package's inverter alternatives.
			if not row.component_type and not row.component_make:
				row.component_type = "Inverter"
		self.resolve_option_components()
		self.number_options()
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
			# The make links to a technology record; the option keeps its readable name.
			make.technology = technology_name(make.technology)
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
		"""The customer-facing table: every row of the System & Options tab, one line each.

		A presentation of those tables and never a second place to type, so it is cleared
		and written fresh rather than merged - there is nothing here to preserve. Each
		component keeps one serial number across its lines.
		"""
		make = lambda name: frappe.db.get_value("Component Make", name, "make_name") if name else ""
		join = lambda *parts: " ".join(str(part) for part in parts if part)

		lines = []
		for row in self.get("panels"):
			lines.append((_("Solar Panel"), _("Solar PV Module"),
				join(row.panel_type, row.panel_capacity_wp and f"{flt(row.panel_capacity_wp):g} Wp", technology_name(row.panel_variant)),
				make(row.panel_make), row.nos, 0))
		for row in self.get("inverters"):
			lines.append((_("Inverter"), technology_name(row.inverter_type) or _("Inverter"),
				join(row.inverter_capacity_kw and f"{flt(row.inverter_capacity_kw):g} kW", row.inverter_phase),
				make(row.inverter_make), row.nos, 0))
		for row in self.get("batteries"):
			lines.append((_("Battery"), technology_name(row.battery_variant) or _("Battery"),
				join(row.battery_voltage and f"{flt(row.battery_voltage):g} V",
					row.battery_capacity_ah and f"{flt(row.battery_capacity_ah):g} Ah", row.battery_phase),
				make(row.battery_make), row.nos, 0))
		for row in self.get("bos_items"):
			lines.append((_("Balance of System"), row.item, row.specification, make(row.make), row.numbers, 0))
		for row in self.get("kseb_expenses"):
			lines.append((_("KSEB Expenses"), row.particulars, "", "", 0, row.amount))
		for row in self.get("mounting_expenses"):
			lines.append((_("Mounting Structure"), row.item, row.specification, make(row.make), row.capacity_kw, row.amount))
		for row in self.get("installation_expenses"):
			lines.append((_("Installation"), row.item, row.specification, "", 0, row.amount))

		self.set("quoted_options", [])
		serials = {}
		for component, item, specification, make_name, units, amount in lines:
			serials.setdefault(component, len(serials) + 1)
			self.append("quoted_options", {
				"sl_no": serials[component],
				"component_type": component,
				"option_label": item,
				"option_description": specification or "",
				"make": make_name or "",
				"units": flt(units),
				"system_cost": flt(amount),
			})

	def seed_option_from_package(self):
		"""A package's inverter alternatives are the estimate's priced options.

		Estimating here is picking the predefined package that fits what the survey found,
		not composing a system from parts. So naming the package is enough: each of its
		inverter alternatives becomes an option, priced as the package prices it - the same
		options and prices the quotation offers - with the package's default recommended.

		Options taken from the package carry no component make; they are rewritten from the
		package on every save, so they follow a change of package or of its prices, and the
		one recommended stays recommended while its make is still offered. An option added
		by hand (the desk's Add Option dialog) carries a make, and once there is one this
		steps back and never touches the table: it must not overwrite what somebody priced.
		"""
		if any(row.component_make for row in self.options):
			return
		if not self.solar_package:
			self.set("options", [])
			return
		recommended = self.flags.get("recommend_inverter_make") or next(
			(row.inverter_make for row in self.options if row.is_recommended), None
		)
		package = frappe.get_cached_doc("Solar Package", self.solar_package)
		module = default_module(package)
		price = default_price(package) or frappe._dict()
		# The alternatives unticked on the design step are not offered, so they are not options.
		excluded = self.excluded_makes()
		alternatives = [
			row for row in package_inverter_alternatives(package, self.connection_type)
			if row.inverter_make not in excluded
		]
		if not any(row.inverter_make == recommended for row in alternatives):
			recommended = next((row.inverter_make for row in alternatives if row.is_default), None)
		makes = {
			m.name: m.make_name
			for m in frappe.get_all("Component Make", filters={"name": ["in", [r.inverter_make for r in alternatives if r.inverter_make]]},
				fields=["name", "make_name"])
		}
		self.set("options", [])
		for n, row in enumerate(alternatives, start=1):
			self.append("options", {
				"option_name": _("Option {0} - {1}").format(n, makes.get(row.inverter_make) or package.inverter_topology or _("Standard")),
				"component_type": "Inverter",
				"inverter_topology": package.inverter_topology or "String",
				"solar_package": package.name,
				"is_recommended": 1 if row.inverter_make == recommended else 0,
				# The inverter row's cost is the package price built with that inverter; the
				# default row's may be left blank, the price table then holds it.
				"system_cost": flt(row.cost) or (flt(price.get("system_cost")) if row.is_default else 0.0),
				"additional_structure_cost": flt(price.get("additional_structure_and_cable_cost")),
				"module_make": module.module_make if module else None,
				"module_specification": module.module_specification if module else None,
				"module_count": module.module_count if module else None,
				"inverter_make": row.inverter_make,
				"inverter_specification": row.inverter_specification,
				"inverter_count": row.inverter_count,
				"display_order": n,
			})
		if self.options and not any(row.is_recommended for row in self.options):
			self.options[0].is_recommended = 1

	def excluded_makes(self):
		"""The package inverter alternatives not offered on this estimate, as make names."""
		return {line.strip() for line in (self.excluded_inverter_makes or "").splitlines() if line.strip()}

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
		"""Resolved from the fee schedule. A typed fee is never accepted.

		Registration is charged on the inverter capacity once inverters are designed in,
		and on the proposed system size until then.
		"""
		fees = statutory.get_statutory_fees(
			self.subject.discom,
			self.connection_type or self.subject.connection_type or "Single Phase",
			self.inverter_capacity_kw() or self.final_capacity_kw,
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

	def compute_expenses(self):
		"""KSEB fees as the schedule resolved them; mounting and installation by roof type."""
		fill_expense_tables(
			self,
			roof_type=self.roof_type,
			panel_kw=self.panel_capacity_kwp() or flt(self.final_capacity_kw),
			fees={
				"application_fee": self.kseb_application_fee,
				"registration_fee": self.kseb_registration_fee,
				"net_meter_charge": self.net_meter_charge,
			},
		)

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

	def validate_subsidy_conditions(self):
		"""A subsidised job must be LT-1A, DCR, within the size cap and not off-grid.

		None of this applies without subsidy: a non-DCR package or a larger system is
		legitimate for a commercial or unsubsidised job — the client's own 10 kWp proposal
		quotes non-DCR modules. The tariff category and size cap live in A3 Sola Settings.
		"""
		if self.subsidy_option != "With Subsidy":
			return

		problems = []
		required_tariff = get_value("subsidy_tariff_category", "LT-1A")
		if self.tariff_category:
			if _normalise_tariff(self.tariff_category) != _normalise_tariff(required_tariff):
				problems.append(
					_("Consumer tariff category is {0}; subsidy needs {1}.").format(
						frappe.bold(self.tariff_category), frappe.bold(required_tariff)
					)
				)
		elif self.solar_consumer and not self.flags.in_test:
			# Not yet recorded is not the same as wrong; say so without blocking the save.
			frappe.msgprint(
				_("Consumer {0} has no tariff category recorded; subsidy needs {1}.").format(
					frappe.bold(self.solar_consumer), frappe.bold(required_tariff)
				),
				title=_("Subsidy Conditions"),
				indicator="orange",
			)

		row = self.recommended_row()
		package = (row.solar_package if row else None) or self.solar_package
		if package and not frappe.db.get_value("Solar Package", package, "is_dcr_compliant"):
			problems.append(
				_("Package {0} is not DCR compliant; subsidy needs DCR panels.").format(frappe.bold(package))
			)

		for row in self.get("panels"):
			if row.panel_type == "Non-DCR":
				problems.append(
					_("Solar panel row {0} is Non-DCR; subsidy needs DCR panels.").format(row.idx)
				)

		max_kw = get_float("subsidy_max_capacity_kw", 10.0)
		if flt(self.final_capacity_kw) > max_kw:
			problems.append(
				_("Proposed system size is {0} kW; subsidy allows at most {1} kW.").format(
					frappe.bold(flt(self.final_capacity_kw, 3)), frappe.bold(max_kw)
				)
			)

		if self.system_type == "Off-Grid":
			problems.append(_("An Off-Grid system is not eligible for subsidy."))

		if problems:
			frappe.throw(
				"<br>".join(problems)
				+ "<br><br>"
				+ _("Fix these, or set Subsidy to Without Subsidy."),
				title=_("Subsidy Conditions Not Met"),
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


# The equipment tables priced per unit, and the field holding each row's count.
EQUIPMENT_COUNT = {"panels": "nos", "inverters": "nos", "batteries": "nos", "bos_items": "numbers"}

# The commercials, one line per System & Options table, in the order the tab shows them.
COMMERCIAL_LINES = (
	("panels", "Solar Panel"),
	("inverters", "Inverter"),
	("batteries", "Battery"),
	("bos_items", "Balance of System"),
	("kseb_expenses", "KSEB Expenses"),
	("mounting_expenses", "Mounting Structure Expenses"),
	("installation_expenses", "Installation Expenses"),
)

# Charges kept in their own records, raised against the estimate, and priced after its own
# tables: (commercials key, doctype, sign). A discount takes away.
LINKED_CHARGES = (
	("additional_structure", "Additional Structure", 1),
	("additional_cable", "Additional Cable", 1),
	("special_discount", "Special Discount", -1),
)


# Inverter technology names as the package's topology choices.
TOPOLOGY_BY_TECHNOLOGY = {
	"String On-Grid": "String",
	"String with Optimiser": "String with Optimiser",
	"Microinverter": "Microinverter",
}


@frappe.whitelist()
def package_values_from_estimate(doc):
	"""A new Solar Package's values, drawn from an estimate's System & Options tab.

	Takes the form's document as it stands, saved or not, and saves nothing: the desk opens
	the result as an unsaved package for the user to review. The expense tables travel as
	they are; the package refreshes their computed rows on its own save.
	"""
	frappe.has_permission("Solar Package", "create", throw=True)
	estimate = frappe.get_doc(frappe.parse_json(doc))
	make = lambda name: frappe.db.get_value("Component Make", name, "make_name") if name else ""
	join = lambda *parts: " ".join(str(part) for part in parts if part)

	kw = flt(estimate.override_capacity_kw) or flt(estimate.final_capacity_kw) or estimate.panel_capacity_kwp()
	connection = estimate.connection_type or "Single Phase"
	system_type = estimate.system_type or "On-Grid"
	first_inverter = next((row for row in estimate.get("inverters") if row.inverter_type), None)
	topology = (
		"Hybrid" if system_type == "Hybrid"
		else TOPOLOGY_BY_TECHNOLOGY.get(technology_name(first_inverter.inverter_type)) if first_inverter
		else None
	) or "String"
	panels = estimate.get("panels")

	values = {
		"package_name": _("{0} kWp {1} {2}").format(f"{kw:g}", connection, system_type),
		"specification_code": join(f"{kw:g}KW", "3PH" if connection == "Three Phase" else "1PH",
			topology if topology != "String" else ""),
		"capacity_kw": kw,
		"system_type": system_type,
		"connection_type": connection,
		"inverter_topology": topology,
		"is_dcr_compliant": 1 if panels and all(row.panel_type == "DCR" for row in panels) else 0,
		"company": estimate.company,
		"roof_type": estimate.roof_type,
		"modules": [
			{
				"module_specification": join(row.panel_type, row.panel_capacity_wp and f"{flt(row.panel_capacity_wp):g} Wp",
					technology_name(row.panel_variant)) or _("Solar PV Module"),
				"module_make": row.panel_make,
				"module_wattage": row.panel_capacity_wp,
				"module_count": row.nos,
			}
			for row in panels
		],
		"inverters": [
			{
				"inverter_specification": join(technology_name(row.inverter_type),
					row.inverter_capacity_kw and f"{flt(row.inverter_capacity_kw):g} kW", row.inverter_phase) or _("Inverter"),
				"inverter_make": row.inverter_make,
				"inverter_capacity_kw": row.inverter_capacity_kw,
				"inverter_count": row.nos,
			}
			for row in estimate.get("inverters")
		],
		"system_items": [
			{"system_type": row.item, "specification": row.specification, "make": row.make, "qty": row.numbers}
			for row in estimate.get("bos_items")
		],
	}
	for table in ("batteries", "kseb_expenses", "mounting_expenses", "installation_expenses"):
		values[table] = [
			{df.fieldname: row.get(df.fieldname) for df in row.meta.fields if df.fieldtype not in ("Section Break", "Column Break")}
			for row in estimate.get(table)
		]
	return values


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


def make_mismatch(make, technology):
	"""Why `make` does not belong under `technology`, or None when it does or either is unset."""
	if not (make and technology):
		return None
	make_name, make_technology = frappe.db.get_value("Component Make", make, ["make_name", "technology"])
	if make_technology == technology:
		return None
	return _("make {0} is not a {1} make.").format(frappe.bold(make_name), frappe.bold(technology_name(technology)))


def unit_count(required, unit_size):
	"""Whole units of `unit_size` to cover `required`, rounded up: 18.15 is 19."""
	if not (flt(required) and flt(unit_size)):
		return 0
	# Round first so 5500 W of 550 Wp panels is 10, not 11 from float noise.
	return math.ceil(round(flt(required) / flt(unit_size), 6))


def _normalise_tariff(value):
	"""LT-1A, lt 1a and LT1A are the same category as written on different forms."""
	return "".join(ch for ch in (value or "").upper() if ch.isalnum())


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


def package_inverter_alternatives(package, phase=None):
	"""A package's inverter rows that are offered as options: the default, and any other
	with a specification or a price - the same rows the quotation lists - narrowed to the
	inverters for this connection type when one is given."""
	return [
		row for row in inverters_for_phase(package, phase)
		if row.is_default or row.inverter_specification or flt(row.cost)
	]


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
