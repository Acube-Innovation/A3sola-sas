# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Runtime naming-series prefixes.

Every transaction series in this app reads its prefix from A3 Sola Settings at autoname
time, so a tenant can rebrand a prefix without a code change and without a migration.
"""

import frappe
from frappe.model.naming import make_autoname

from a3_sola.api.settings import get_value


def set_name(doc, prefix_field, pattern=".YYYY.-.#####", fallback=""):
	"""Name `doc` from the prefix held in A3 Sola Settings.

	Args:
	        doc: the document being named.
	        prefix_field: the fieldname on A3 Sola Settings holding the prefix.
	        pattern: the series suffix appended to the prefix.
	        fallback: prefix used when Settings has no value (fresh install, tests).
	"""
	prefix = get_value(prefix_field) or fallback
	if not prefix:
		frappe.throw(
			frappe._("Naming prefix {0} is not set in A3 Sola Settings.").format(
				frappe.bold(prefix_field)
			)
		)
	doc.name = make_autoname(f"{prefix}-{pattern}", doc=doc)
	return doc.name
