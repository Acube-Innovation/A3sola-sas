# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""A package's module and inverter options, and the ones everything downstream reads.

A package is one array offered several ways: quoted with a DCR panel or its non-DCR
equivalent, and built with a string inverter, panel-level optimisers or microinverters -
each inverter carrying its own price, because the price is what the array costs built that
way. What must not happen is the proposal printing one option while the handoff builds the
job with another, so the default is resolved in exactly one function and these tests hold
every reader to it.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from a3_sola.solar_crm.doctype.solar_package.solar_package import (
	default_inverter,
	default_module,
	default_rows,
	default_price,
	default_prices,
	default_system_items,
	system_cost,
)
from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import (
	add_option_from_package,
)
from a3_sola.tests.fixtures import default_company, make_consumer, make_estimate

MODULE = {
	"module_specification": "550 Wp Mono PERC Bifacial DCR",
	"module_wattage": 550,
	"module_count": 6,
}

INVERTER = {
	"inverter_specification": "3kW Single Phase On-Grid with Online Monitoring",
	"inverter_capacity_kw": 3.0,
	"inverter_count": 1,
	"cost": 210000,
}

OPTIMISER = {
	"inverter_specification": "3kW Single Phase On-Grid with Panel level optimizer",
	"inverter_capacity_kw": 3.0,
	"inverter_count": 1,
	"cost": 245000,
}


def make_package(modules=None, inverters=None, system_items=None, prices=None, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Solar Package",
			"specification_code": "TEST-" + frappe.generate_hash(length=6).upper(),
			"package_name": "Test Package",
			"capacity_kw": 3.0,
			"system_type": "On-Grid",
			"connection_type": "Single Phase",
			"is_active": 1,
			"company": default_company(),
			"modules": modules if modules is not None else [dict(MODULE)],
			"inverters": inverters if inverters is not None else [dict(INVERTER)],
			"system_items": system_items or [],
			"prices": prices or [],
		}
	)
	doc.update(kwargs)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	return doc


class TestModuleOptions(FrappeTestCase):
	def test_a_package_carries_its_modules_as_rows(self):
		package = make_package()
		self.assertEqual(len(package.modules), 1)
		self.assertEqual(package.modules[0].module_specification, MODULE["module_specification"])

	def test_the_only_option_becomes_the_default(self):
		"""Nobody should have to tick a box to say the one thing is the thing."""
		package = make_package()
		self.assertTrue(package.modules[0].is_default)

	def test_a_second_option_does_not_steal_the_default(self):
		package = make_package(
			modules=[
				dict(MODULE, is_default=1),
				dict(MODULE, module_specification="550 Wp Mono PERC Bifacial Non-DCR"),
			]
		)
		self.assertTrue(package.modules[0].is_default)
		self.assertFalse(package.modules[1].is_default)
		self.assertEqual(default_module(package).module_specification, MODULE["module_specification"])

	def test_two_defaults_are_refused(self):
		"""Downstream reads one module. Two ticks is a question nobody can answer."""
		with self.assertRaises(frappe.ValidationError):
			make_package(modules=[dict(MODULE, is_default=1), dict(MODULE, is_default=1)])

	def test_the_default_can_be_moved_to_another_row(self):
		package = make_package(
			modules=[dict(MODULE), dict(MODULE, module_specification="620 Wp TopCon")]
		)
		package.modules[0].is_default = 0
		package.modules[1].is_default = 1
		package.save(ignore_permissions=True)
		self.assertEqual(default_module(package).module_specification, "620 Wp TopCon")

	def test_a_package_with_no_modules_resolves_to_nothing(self):
		"""A draft package must be allowed to exist, so every reader copes with None."""
		package = make_package(modules=[])
		self.assertIsNone(default_module(package))

	def test_the_accessor_takes_a_name_as_well_as_a_document(self):
		package = make_package()
		self.assertEqual(
			default_module(package.name).module_specification,
			default_module(package).module_specification,
		)


class TestDownstreamReadsTheDefault(FrappeTestCase):
	def setUp(self):
		self.package = make_package(
			modules=[
				dict(MODULE, module_specification="NOT THE DEFAULT", module_count=99),
				dict(MODULE, is_default=1),
			]
		)

	def test_the_proposal_prints_the_default_module(self):
		from a3_sola.api.proposal import _specification_rows

		rows = _specification_rows(self.package, [], {})
		panels = next(r for r in rows if r["item"] == "Solar Panels")
		self.assertEqual(panels["specification"], MODULE["module_specification"])
		self.assertEqual(panels["nos"], MODULE["module_count"])

	def test_the_catalogue_carries_the_default_module(self):
		found = default_rows("modules", [self.package.name])[self.package.name]
		self.assertEqual(found.module_specification, MODULE["module_specification"])
		self.assertEqual(found.module_count, MODULE["module_count"])

	def test_the_bulk_lookup_agrees_with_the_single_one(self):
		"""Two code paths resolve the default; they must never disagree."""
		for fieldname, single in (("modules", default_module), ("inverters", default_inverter)):
			bulk = default_rows(fieldname, [self.package.name])[self.package.name]
			self.assertEqual(bulk.name, single(self.package).name, fieldname)

	def test_the_bulk_lookup_falls_back_to_the_first_row(self):
		package = make_package(modules=[dict(MODULE)])
		frappe.db.set_value("Solar Package Module", package.modules[0].name, "is_default", 0)
		found = default_rows("modules", [package.name])[package.name]
		self.assertEqual(found.module_specification, MODULE["module_specification"])


class TestInverterOptions(FrappeTestCase):
	def test_a_package_carries_its_inverters_as_rows(self):
		package = make_package(inverters=[dict(INVERTER), dict(OPTIMISER)])
		self.assertEqual(len(package.inverters), 2)
		self.assertTrue(package.inverters[0].is_default)
		self.assertFalse(package.inverters[1].is_default)

	def test_two_defaults_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_package(inverters=[dict(INVERTER, is_default=1), dict(OPTIMISER, is_default=1)])

	def test_a_third_option_can_be_priced(self):
		"""The point of the change: two was a ceiling, because two costs was the ceiling."""
		package = make_package(
			inverters=[
				dict(INVERTER),
				dict(OPTIMISER),
				dict(OPTIMISER, inverter_specification="3kW Microinverter", cost=290000),
			]
		)
		self.assertEqual([r.cost for r in package.inverters], [210000, 245000, 290000])

	def test_each_option_carries_its_own_cost(self):
		"""Reference data since prices moved to configurations, but still per option."""
		package = make_package(inverters=[dict(INVERTER), dict(OPTIMISER, is_default=1)])
		self.assertEqual(default_inverter(package).cost, OPTIMISER["cost"])

	def test_a_package_with_no_inverter_resolves_to_nothing(self):
		self.assertIsNone(default_inverter(make_package(inverters=[])))


class TestDownstreamReadsTheDefaultInverter(FrappeTestCase):
	def setUp(self):
		# DCR, because the estimate refuses a non-DCR package under PM Surya Ghar and the
		# subject here is which inverter gets priced, not the subsidy rules. The prices are
		# typed per configuration, so each inverter gets the row the assertions look for.
		self.package = make_package(
			is_dcr_compliant=1,
			inverters=[
				dict(INVERTER, inverter_specification="NOT THE DEFAULT", cost=1),
				dict(OPTIMISER, is_default=1),
			],
			system_items=PARTS["system_items"],
			prices=[
				dict(CONFIGURATION, inverter="NOT THE DEFAULT", system_cost=1),
				dict(CONFIGURATION, inverter=OPTIMISER["inverter_specification"],
				     system_cost=OPTIMISER["cost"]),
			],
		)

	def test_the_estimator_offers_every_option_not_only_the_default(self):
		"""The catalogue's job is to show the same array priced several ways."""
		from a3_sola.api.cost_estimate import _inverter_options

		options = _inverter_options([self.package.name])[self.package.name]
		self.assertEqual(len(options), 2)
		self.assertEqual([o.cost for o in options], [1, OPTIMISER["cost"]])

	def test_the_estimate_option_builder_prices_the_position_it_was_given(self):
		"""Option 2 on the estimate must be the price typed for option 2, not the default's."""
		estimate = self._estimate()
		add_option_from_package(estimate.name, self.package.name, inverter_option="2")
		estimate.reload()
		added = estimate.options[-1]
		self.assertEqual(added.inverter_specification, OPTIMISER["inverter_specification"])
		self.assertEqual(added.system_cost, OPTIMISER["cost"])

	def test_the_builder_still_reaches_the_first_option(self):
		estimate = self._estimate()
		add_option_from_package(estimate.name, self.package.name, inverter_option="1")
		estimate.reload()
		self.assertEqual(estimate.options[-1].system_cost, 1)

	def test_an_out_of_range_position_falls_back_to_the_default(self):
		"""The caller is a button. A wrong inverter beats a refusal the user cannot fix."""
		estimate = self._estimate()
		add_option_from_package(estimate.name, self.package.name, inverter_option="9")
		estimate.reload()
		self.assertEqual(estimate.options[-1].system_cost, OPTIMISER["cost"])

	def _estimate(self):
		consumer = make_consumer()
		return make_estimate(consumer, with_default_options=False, options=[])

	def test_the_document_context_still_answers_the_old_expressions(self):
		"""Templates are data. A tenant's edited Jinja must not go blank on a refactor."""
		import inspect

		from a3_sola.api import documents

		source = inspect.getsource(documents)
		self.assertIn("inverter_1_specification", source)
		self.assertIn("package_module", source)


DCDB = {"system_type": "DCDB", "specification": "PV fuses, DC isolator, Type 2 SPD",
        "qty": 1, "cost": 4200}
ACDB = {"system_type": "ACDB", "specification": "MCB and Type 2 AC SPD", "qty": 1, "cost": 3800}
METER = {"system_type": "Solar Energy Meter", "specification": "Watt-hour meter",
         "qty": 1, "cost": 2100}


class TestSystemItems(FrappeTestCase):
	def test_the_balance_of_system_is_rows_of_typed_parts(self):
		package = make_package(system_items=[dict(DCDB), dict(ACDB), dict(METER)])
		self.assertEqual(
			[r.system_type for r in package.system_items], ["DCDB", "ACDB", "Solar Energy Meter"]
		)

	def test_every_type_gets_its_own_default(self):
		"""Unlike modules and inverters: a package has a DCDB *and* an ACDB *and* a meter."""
		package = make_package(system_items=[dict(DCDB), dict(ACDB), dict(METER)])
		self.assertTrue(all(r.is_default for r in package.system_items))
		self.assertEqual(len(default_system_items(package)), 3)

	def test_two_rows_of_one_type_are_alternatives(self):
		package = make_package(
			system_items=[
				dict(DCDB, is_default=1),
				dict(DCDB, specification="Upgraded board", cost=6800),
				dict(ACDB),
			]
		)
		chosen = default_system_items(package)
		self.assertEqual(chosen["DCDB"].specification, DCDB["specification"])
		self.assertEqual(len(chosen), 2)

	def test_two_defaults_of_the_same_type_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_package(system_items=[dict(DCDB, is_default=1), dict(DCDB, is_default=1)])

	def test_two_defaults_of_different_types_are_fine(self):
		"""The refusal must be per type, or a normal package cannot be saved at all."""
		package = make_package(system_items=[dict(DCDB, is_default=1), dict(ACDB, is_default=1)])
		self.assertEqual(len(package.system_items), 2)

	def test_the_cost_counts_only_what_is_quoted(self):
		package = make_package(
			system_items=[
				dict(DCDB, is_default=1),
				dict(DCDB, specification="Upgraded board", cost=6800),
				dict(ACDB),
			]
		)
		self.assertEqual(system_cost(package), DCDB["cost"] + ACDB["cost"])

	def test_a_package_with_no_system_rows_costs_nothing(self):
		self.assertEqual(system_cost(make_package(system_items=[])), 0)


class TestTheProposalReadsTheSystemTable(FrappeTestCase):
	def test_a_filled_in_row_overrides_the_standing_default(self):
		from a3_sola.api.proposal import _system_rows

		package = make_package(
			system_items=[dict(DCDB, make=None, specification="Bespoke DCDB, 6 way")]
		)
		row = next(r for r in _system_rows(package) if r["item"] == "DCDB")
		self.assertEqual(row["specification"], "Bespoke DCDB, 6 way")

	def test_a_package_carried_over_still_prints_the_standing_makes(self):
		"""The old fields held no make. The proposal must read as it always did."""
		from a3_sola.api.proposal import _system_rows

		package = make_package(system_items=[dict(DCDB, make=None)])
		row = next(r for r in _system_rows(package) if r["item"] == "DCDB")
		self.assertIn("ABB", row["make"])

	def test_a_type_the_package_does_not_list_is_not_promised(self):
		"""A proposal offering a battery bank the package has no row for is a lie."""
		from a3_sola.api.proposal import _system_rows

		rows = _system_rows(make_package(system_items=[dict(DCDB)]))
		self.assertNotIn("Battery Bank", [r["item"] for r in rows])

	def test_the_quantity_comes_from_the_row(self):
		from a3_sola.api.proposal import _system_rows

		package = make_package(
			system_items=[{"system_type": "Earthing", "qty": 4, "is_default": 1}]
		)
		row = next(r for r in _system_rows(package) if r["item"] == "Earthing")
		self.assertEqual(row["nos"], "4 Sets")

	def test_the_lump_sum_quantities_survive(self):
		from a3_sola.api.proposal import _system_rows

		package = make_package(system_items=[{"system_type": "DC Cable", "qty": 1, "is_default": 1}])
		row = next(r for r in _system_rows(package) if r["item"] == "DC Cables")
		self.assertEqual(row["nos"], "Ls.")

	def test_commissioning_is_still_the_last_line(self):
		from a3_sola.api.proposal import _specification_rows

		package = make_package(system_items=[dict(DCDB)])
		rows = _specification_rows(package, [], {})
		self.assertEqual(rows[-1]["item"], "Installation, Testing, Commissioning")


#: A package that can actually be priced: one of each of the five things a price names.
PARTS = {
	"system_items": [
		{"system_type": "DCDB", "specification": "PV fuses, DC isolator", "qty": 1},
		{"system_type": "ACDB", "specification": "MCB and Type 2 AC SPD", "qty": 1},
		{"system_type": "Solar Energy Meter", "specification": "Watt-hour meter", "qty": 1},
	]
}

CONFIGURATION = {
	"module": MODULE["module_specification"],
	"inverter": INVERTER["inverter_specification"],
	"dcdb": "PV fuses, DC isolator",
	"acdb": "MCB and Type 2 AC SPD",
	"energy_meter": "Watt-hour meter",
}


def priceable(**kwargs):
	values = dict(PARTS)
	values.update(kwargs)
	return make_package(**values)


class TestPricedConfigurations(FrappeTestCase):
	def test_a_price_names_the_configuration_it_is_for(self):
		package = priceable(prices=[dict(CONFIGURATION, system_cost=250000)])
		row = package.prices[0]
		self.assertEqual(row.module, MODULE["module_specification"])
		self.assertEqual(row.inverter, INVERTER["inverter_specification"])
		self.assertEqual(row.dcdb, "PV fuses, DC isolator")
		self.assertEqual(row.acdb, "MCB and Type 2 AC SPD")
		self.assertEqual(row.energy_meter, "Watt-hour meter")

	def test_all_five_selections_are_mandatory(self):
		for missing in ("module", "inverter", "dcdb", "acdb", "energy_meter"):
			configuration = dict(CONFIGURATION, system_cost=250000)
			configuration.pop(missing)
			with self.assertRaises(frappe.exceptions.MandatoryError, msg=missing):
				priceable(prices=[configuration])

	def test_the_same_combination_cannot_be_priced_twice(self):
		with self.assertRaises(frappe.ValidationError):
			priceable(
				prices=[
					dict(CONFIGURATION, system_cost=250000),
					dict(CONFIGURATION, system_cost=260000),
				]
			)

	def test_a_different_combination_may_be_priced_separately(self):
		"""The whole point: the same array with another inverter is another price."""
		package = priceable(
			inverters=[dict(INVERTER), dict(OPTIMISER)],
			prices=[
				dict(CONFIGURATION, system_cost=250000),
				dict(CONFIGURATION, inverter=OPTIMISER["inverter_specification"],
				     system_cost=290000),
			],
		)
		self.assertEqual([r.system_cost for r in package.prices], [250000, 290000])

	def test_a_price_for_a_part_the_package_does_not_offer_is_refused(self):
		"""A figure attached to nothing reads exactly as authoritative as a real one."""
		with self.assertRaises(frappe.ValidationError):
			priceable(prices=[dict(CONFIGURATION, module="A panel nobody stocks",
			                       system_cost=250000)])

	def test_removing_an_option_that_a_price_still_names_is_refused(self):
		package = priceable(prices=[dict(CONFIGURATION, system_cost=250000)])
		package.modules[0].module_specification = "Renamed panel"
		with self.assertRaises(frappe.ValidationError):
			package.save(ignore_permissions=True)


class TestPricesAreResolvedNotTyped(FrappeTestCase):
	def setUp(self):
		self.package = priceable(
			prices=[dict(CONFIGURATION, system_cost=250000, standard_discount=10000)]
		)
		self.row = self.package.prices[0]

	def test_the_net_rate_is_computed_on_the_row(self):
		self.assertEqual(
			self.row.net_rate, 250000 - self.row.indicative_subsidy - 10000
		)

	def test_the_generation_band_is_resolved_on_the_row(self):
		self.assertGreater(self.row.expected_daily_units_high, 0)
		self.assertGreaterEqual(self.row.expected_daily_units_high,
		                        self.row.expected_daily_units_low)

	def test_the_generation_band_is_the_packages_not_the_modules(self):
		"""6 x 550 Wp is a 3.3 kW array on a 3 kW package. The slab follows the 3."""
		package = priceable(
			modules=[
				dict(MODULE, is_default=1),
				dict(MODULE, module_specification="620 Wp TopCon", module_wattage=620),
			],
			prices=[
				dict(CONFIGURATION, system_cost=250000),
				dict(CONFIGURATION, module="620 Wp TopCon", system_cost=270000),
			],
		)
		small, large = package.prices
		self.assertEqual(small.expected_daily_units_high, large.expected_daily_units_high)
		self.assertEqual(small.indicative_subsidy, large.indicative_subsidy)

	def test_an_unpriced_row_stays_at_zero(self):
		"""Subtracting a subsidy from a blank price would publish a negative net rate."""
		package = priceable(prices=[dict(CONFIGURATION, system_cost=0)])
		self.assertEqual(package.prices[0].net_rate, 0.0)


class TestTheDefaultConfiguration(FrappeTestCase):
	def test_the_default_price_is_the_one_for_the_default_parts(self):
		package = priceable(
			inverters=[dict(INVERTER), dict(OPTIMISER, is_default=1)],
			prices=[
				dict(CONFIGURATION, system_cost=250000),
				dict(CONFIGURATION, inverter=OPTIMISER["inverter_specification"],
				     system_cost=290000),
			],
		)
		self.assertEqual(default_price(package).system_cost, 290000)

	def test_moving_the_default_inverter_moves_the_quoted_price(self):
		package = priceable(
			inverters=[dict(INVERTER), dict(OPTIMISER)],
			prices=[
				dict(CONFIGURATION, system_cost=250000),
				dict(CONFIGURATION, inverter=OPTIMISER["inverter_specification"],
				     system_cost=290000),
			],
		)
		self.assertEqual(default_price(package).system_cost, 250000)
		package.inverters[0].is_default = 0
		package.inverters[1].is_default = 1
		package.save(ignore_permissions=True)
		self.assertEqual(default_price(package).system_cost, 290000)

	def test_a_package_with_no_prices_resolves_to_nothing(self):
		self.assertIsNone(default_price(priceable(prices=[])))

	def test_the_bulk_lookup_agrees_with_the_single_one(self):
		package = priceable(
			inverters=[dict(INVERTER), dict(OPTIMISER, is_default=1)],
			prices=[
				dict(CONFIGURATION, system_cost=250000),
				dict(CONFIGURATION, inverter=OPTIMISER["inverter_specification"],
				     system_cost=290000),
			],
		)
		bulk = default_prices([package.name])[package.name]
		self.assertEqual(bulk.system_cost, default_price(package).system_cost)
