# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Every published solution, with who each one is for."""

from a3_sola.api import platform

no_cache = 1


def get_context(context):
	context.no_cache = 1
	solutions = platform.all_solutions()
	context.solutions = solutions
	context.outcomes = platform.bullets_for(
		"Platform Solution", [s.name for s in solutions], "key_outcomes"
	)
	context.page_meta_title = "Solutions - who a3 sola is built for"
	context.page_meta_description = (
		"Rooftop EPCs, dealers and distributors, C&I contractors, O&M providers and "
		"multi-branch solar groups."
	)
	return context
