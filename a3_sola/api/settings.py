# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Cached access to the single settings doctype.

There is exactly one settings singleton in this product — "A3 Sola Settings". Phases 2 to
7 add tabs to it. Nothing may create a second one.
"""

import frappe

SETTINGS_DOCTYPE = "A3 Sola Settings"


def get_settings():
	"""Return the cached A3 Sola Settings single document."""
	return frappe.get_cached_doc(SETTINGS_DOCTYPE)


def get_value(fieldname, default=None):
	"""Return one settings value, falling back to `default` when unset."""
	value = frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)
	if value in (None, "", 0) and default is not None:
		# 0 is a legitimate value for Check and Int fields, so only fall back on
		# genuinely empty values.
		if value == 0 and isinstance(default, bool | int) and not isinstance(default, bool):
			return value
		if value in (None, ""):
			return default
	return value


def get_float(fieldname, default=0.0):
	value = frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)
	try:
		value = float(value)
	except (TypeError, ValueError):
		return default
	return value if value else default


def get_int(fieldname, default=0):
	value = frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def precision():
	"""Rounding precision used by every monetary and float computation in the app."""
	return get_int("rounding_precision", 2) or 2
