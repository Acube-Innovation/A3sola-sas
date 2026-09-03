# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Housekeeping that keeps the monitoring itself readable."""

import frappe

from a3_sola.api.settings import get_int


def purge_error_log():
	"""Daily. Frappe keeps error logs forever; this site's grew to half the database.

	That is two problems, and the second is the worse one: a log nobody can read is a log
	nobody reads, and the entry that mattered is in there somewhere.
	"""
	from a3_sola.api.monitoring import errors

	days = get_int("error_log_retention_days", 30) or 30
	result = errors.purge_old(days=days)
	frappe.logger("a3_sola").info({"event": "error_log_purged", **result})
	return result
