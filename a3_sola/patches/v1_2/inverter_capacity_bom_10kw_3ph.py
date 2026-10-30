# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The 10 kW three phase material BOM, from the delivery note of Lijo Kurian's job: two Hoymiles
MIT-5000-S inverters and the balance of system, listed in A3 Sola Settings by inverter capacity.

The data ships in `a3_sola/data/inverter_capacity_boms_10kw_3ph.json`."""

import json
import os

from a3_sola.patches.v1_2.inverter_capacity_material_boms import add_templates

DATA = os.path.join(os.path.dirname(__file__), "..", "..", "data", "inverter_capacity_boms_10kw_3ph.json")


def execute():
	add_templates(json.load(open(DATA, encoding="utf-8")))
