# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One way a package is priced: built with one of its panels, one of its inverters and (on an
Off-Grid or Hybrid package) one of its batteries, at a package cost. The rows are the package's
price list - an estimate is priced at the row for the panel, inverter and battery it is built
with (solar_package.pricing_option)."""

from frappe.model.document import Document


class SolarPackagePricingOption(Document):
	pass
