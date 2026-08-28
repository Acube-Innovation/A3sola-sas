# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""How much demo data to build.

The generators hold realistic, hand-written records - real Kerala districts, real KSEB
sections, plausible consumption figures - and there are more of them than anyone needs to
look at. This is the knob that says how many of each to actually create.

Five is the default because five is enough to see a list view do its job, a report group
something, and a filter exclude something, without producing a database nobody can read.
Ask for more when you want to see pagination or a chart with a shape.
"""

import frappe

DEFAULT = 5


def limit():
	"""How many of each kind to build. Set `frappe.flags.a3s_demo_limit` to change it."""
	value = getattr(frappe.flags, "a3s_demo_limit", None)
	try:
		value = int(value)
	except (TypeError, ValueError):
		return DEFAULT
	return value if value > 0 else DEFAULT


def take(items, count=None):
	"""The first `count` of a demo list - or of the configured limit."""
	return list(items)[: (count or limit())]
