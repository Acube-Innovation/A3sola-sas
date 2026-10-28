# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The inverter models of the client's master price list (Solar Inverters and Batteries
Master List, sheet Inverter), transcribed as given.

Each row: make, model, phase, category, capacity kW, units in the kit, rate, GST note,
warranty years, extension "upto" (years), extension rate, (optimizer model, price, qty),
kit includes. The sheet's "Warrantee extension upto" is the last year covered when it is
beyond the warranty (a micro kit's 12 years taken to 25), else the years it adds (a hybrid's
5 years taken 5 more).
"""

import frappe
from frappe.utils import cint

# Make on the sheet and category -> (Component Make, its Component Technology).
MAKES = {
	("Solinteg", "On-Grid"): ("Solinteg", "String On-Grid"),
	("Solinteg", "Hybrid"): ("Solinteg Hybrid", "Hybrid"),
	("SolarEdge", "On-Grid"): ("SolarEdge", "String with Optimiser"),
	("Hoymiles", "On-Grid"): ("Hoymiles", "Microinverter"),
}

INVERTER_MODELS = (
	('Solinteg', 'OGS-3.3K 02GS', 'Single Phase', 'On-Grid', 3.3, 1, 16800, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGS-5K', 'Single Phase', 'On-Grid', 5.0, 1, 30500, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGT-5K', 'Three Phase', 'On-Grid', 5.0, 1, 51800, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGT-6K', 'Three Phase', 'On-Grid', 6.0, 1, 53000, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGT-8K', 'Three Phase', 'On-Grid', 8.0, 1, 60900, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGT-10K', 'Three Phase', 'On-Grid', 10.0, 1, 58300, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGT-12K', 'Three Phase', 'On-Grid', 12.0, 1, 60200, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGT-15K', 'Three Phase', 'On-Grid', 15.0, 1, 64900, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGT-20K', 'Three Phase', 'On-Grid', 20.0, 1, 72000, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'OGT-25K', 'Three Phase', 'On-Grid', 25.0, 1, 76700, 'GST Extra', 10, 0, 0, None, None),
	('Solinteg', 'MHS-8K-30', 'Single Phase', 'Hybrid', 8.0, 1, 108050, 'GST @ 5%', 5, 5, 14046.5, None, None),
	('Solinteg', 'MHT-6k-25', 'Three Phase', 'Hybrid', 6.0, 1, 132750, 'GST @ 5%', 5, 5, 17257.5, None, None),
	('Solinteg', 'MHT-10K-40', 'Three Phase', 'Hybrid', 10.0, 1, 177480, 'GST @ 5%', 5, 5, 23072.4, None, None),
	('Solinteg', 'MHT-12K-40', 'Three Phase', 'Hybrid', 12.0, 1, 185200, 'GST @ 5%', 5, 5, 24076, None, None),
	('Solinteg', 'MHT-15K-40', 'Three Phase', 'Hybrid', 15.0, 1, 200650, 'GST @ 5%', 5, 5, 26084.5, None, None),
	('Solinteg', 'MHT-20K-40', 'Three Phase', 'Hybrid', 20.0, 1, 231500, 'GST @ 5%', 5, 5, 30095, None, None),
	('Solinteg', 'MHT-25-100', 'Three Phase', 'Hybrid', 25.0, 1, 416700, 'GST @ 5%', 5, 5, 54171, None, None),
	('Solinteg', 'MHT-30-100', 'Three Phase', 'Hybrid', 30.0, 1, 439850, 'GST @ 5%', 5, 5, 57180.5, None, None),
	('Solinteg', 'MHT-40-100', 'Three Phase', 'Hybrid', 40.0, 1, 478450, 'GST @ 5%', 5, 5, 62198.5, None, None),
	('Solinteg', 'MHT-50-100', 'Three Phase', 'Hybrid', 50.0, 1, 493900, 'GST @ 5%', 5, 5, 64207, None, None),
	('Solinteg', 'M2HS-5K (HOME ONE)', 'Single Phase', 'Hybrid', 5.0, 1, 84900, 'GST Extra', 10, 0, 0, None, None),
	('SolarEdge', 'SE3000H', 'Single Phase', 'On-Grid', 3.0, 1, 7908, 'GST @ 5%', 8, 0, 0, ('S1000', 1932, 6), None),
	('SolarEdge', 'SE4000H', 'Single Phase', 'On-Grid', 4.0, 1, 14476, 'GST @ 5%', 8, 0, 0, ('S1000', 1932, 7), None),
	('SolarEdge', 'SE5000H', 'Single Phase', 'On-Grid', 5.0, 1, 15112, 'GST @ 5%', 8, 0, 0, ('S1000', 1932, 9), None),
	('SolarEdge', 'SE5K', 'Three Phase', 'On-Grid', 5.0, 1, 27612, 'GST @ 5%', 8, 0, 0, ('S1000', 1932, 9), None),
	('SolarEdge', 'SE8K', 'Three Phase', 'On-Grid', 8.0, 1, 28952, 'GST @ 5%', 8, 0, 0, ('S1000', 1932, 14), None),
	('SolarEdge', 'SE10K', 'Three Phase', 'On-Grid', 10.0, 1, 29224, 'GST @ 5%', 8, 0, 0, ('S1000', 1932, 18), None),
	('Hoymiles', 'HM-1000', 'Single Phase', 'On-Grid', 1.0, 1, 10499, 'GST Extra', 12, 25, 2099.8, None, 'HM-1000 microinverter × 1 unit + DTU × 1 unit + Female Connector × 1 unit + Sealing Cap × 1 unit'),
	('Hoymiles', 'HM-1000', 'Single Phase', 'On-Grid', 2.0, 2, 18500, 'GST Extra', 12, 25, 3700, None, 'HM-1000 microinverter × 2 units + DTU × 1 unit + Female Connector × 1 unit + Sealing Cap × 1 unit'),
	('Hoymiles', 'HM-1000', 'Single Phase', 'On-Grid', 3.0, 3, 25500, 'GST Extra', 12, 25, 5100, None, 'HM-1000 microinverter × 3 units + DTU × 1 unit + Female Connector × 1 unit + Sealing Cap × 1 unit'),
	('Hoymiles', 'HM-1000', 'Single Phase', 'On-Grid', 4.0, 4, 32500, 'GST Extra', 12, 25, 6500, None, 'HM-1000 microinverter × 4 units + DTU × 1 unit + Female Connector × 1 unit + Sealing Cap × 1 unit'),
	('Hoymiles', 'HM-1000', 'Single Phase', 'On-Grid', 5.0, 5, 39500, 'GST Extra', 12, 25, 7900, None, 'HM-1000 microinverter × 5 units + DTU × 1 unit + Female Connector × 1 unit + Sealing Cap × 1 unit'),
	('Hoymiles', 'HM-1000', 'Single Phase', 'On-Grid', 6.0, 6, 46500, 'GST Extra', 12, 25, 9300, None, 'HM-1000 microinverter × 6 units + DTU × 1 unit + Female Connector × 1 unit + Sealing Cap × 1 unit'),
	('Hoymiles', 'HM-1000', 'Three Phase', 'On-Grid', 3.0, 3, 27000, 'GST Extra', 12, 25, 5400, None, 'HM-1000 microinverter × 3 units + DTU × 1 unit + Female Connector × 3 units + Sealing Cap × 3 units'),
	('Hoymiles', 'HM-1000', 'Three Phase', 'On-Grid', 4.0, 4, 34000, 'GST Extra', 12, 25, 6800, None, 'HM-1000 microinverter × 4 units + DTU × 1 unit + Female Connector × 3 units + Sealing Cap × 3 units'),
	('Hoymiles', 'HM-1000', 'Three Phase', 'On-Grid', 5.0, 5, 41000, 'GST Extra', 12, 25, 8200, None, 'HM-1000 microinverter × 5 units + DTU × 1 unit + Female Connector × 3 units + Sealing Cap × 3 units'),
	('Hoymiles', 'HM-1000', 'Three Phase', 'On-Grid', 6.0, 6, 48000, 'GST Extra', 12, 25, 9600, None, 'HM-1000 microinverter × 6 units + DTU × 1 unit + Female Connector × 3 units + Sealing Cap × 3 units'),
	('Hoymiles', 'HM-1000', 'Three Phase', 'On-Grid', 7.0, 7, 55000, 'GST Extra', 12, 25, 11000, None, 'HM-1000 microinverter × 7 units + DTU × 1 unit + Female Connector × 3 units + Sealing Cap × 3 units'),
	('Hoymiles', 'HM-1000', 'Three Phase', 'On-Grid', 8.0, 8, 62000, 'GST Extra', 12, 25, 12400, None, 'HM-1000 microinverter × 8 units + DTU × 1 unit + Female Connector × 3 units + Sealing Cap × 3 units'),
	('Hoymiles', 'HM-1000', 'Three Phase', 'On-Grid', 9.0, 9, 69000, 'GST Extra', 12, 25, 13800, None, 'HM-1000 microinverter × 9 units + DTU × 1 unit + Female Connector × 3 units + Sealing Cap × 3 units'),
	('Hoymiles', 'HM-1000', 'Three Phase', 'On-Grid', 10.0, 10, 76000, 'GST Extra', 12, 25, 15200, None, 'HM-1000 microinverter × 10 units + DTU × 1 unit + Female Connector × 3 units + Sealing Cap × 3 units'),
)


def extension_years(warranty, upto):
	"""Years an extension adds, from the sheet's "upto" figure."""
	warranty, upto = cint(warranty), cint(upto)
	return upto - warranty if upto > warranty else upto


def seed_inverter_models(company):
	"""Create the sheet's models that are missing. Idempotent; a model edited since is kept."""
	from a3_sola.setup.install import _insert, _technology

	for make, model, phase, category, capacity, units, rate, gst, warranty, upto, ext_rate, optimizer, kit in INVERTER_MODELS:
		make_name, technology = MAKES[(make, category)]
		make_id = frappe.db.get_value(
			"Component Make", {"make_name": make_name, "component_type": "Inverter", "company": company})
		if not make_id:
			make_id = _insert({
				"doctype": "Component Make", "make_name": make_name, "component_type": "Inverter",
				"technology": _technology(technology, "Inverter", company), "is_active": 1,
				"product_warranty_years": warranty, "company": company,
			}).name
		doc = frappe.get_doc({
			"doctype": "Inverter Model", "inverter_make": make_id, "model_name": model,
			"inverter_phase": phase, "category": category, "capacity_kw": capacity, "units": units,
			"rate": rate, "gst_note": gst, "gst_percent": 5 if "5%" in gst else 0,
			"warranty_years": warranty, "extension_available": 1 if upto else 0,
			"extension_years": extension_years(warranty, upto), "extension_rate": ext_rate,
			"kit_includes": kit, "is_active": 1,
		})
		if optimizer:
			doc.optimizer_model, doc.optimizer_price, doc.optimizer_qty = optimizer
		doc.autoname()
		if frappe.db.exists("Inverter Model", doc.name):
			continue
		doc.insert(ignore_permissions=True, set_name=doc.name)
