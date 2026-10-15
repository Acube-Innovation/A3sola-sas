# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The bank covering letter and vendor feasibility report, laid out as the Word files are
and reading the loan application's own fields.

Templates are data a company may have edited, so a body is replaced only while it is still
the one first seeded (by its hash); an edited body stays, as it is.
"""

import hashlib

import frappe

from a3_sola.setup.seed_documents import TEMPLATES

#: md5 of each body as first seeded.
SEEDED = {
	"BANK-COVERING-LOAN": "3ea07c8cd5f59566826a93dbac669e7f",
	"BANK-VENDOR-FEASIBILITY": "4b5c5f440bf50566a62ebc452c5caca8",
}


def execute():
	replace_seeded(SEEDED)


def replace_seeded(seeded_bodies):
	"""Give each template in `seeded_bodies` ({code: md5 of a body as seeded}) today's seed
	body, where its body is still that one; bump its version."""
	bodies = {t["template_code"]: t["body"] for t in TEMPLATES if t["template_code"] in seeded_bodies}
	for code, seeded in seeded_bodies.items():
		for row in frappe.get_all(
			"Solar Document Template", filters={"template_code": code}, fields=["name", "body_template", "version"]
		):
			if hashlib.md5((row.body_template or "").encode()).hexdigest() != seeded:
				continue
			frappe.db.set_value(
				"Solar Document Template", row.name,
				{"body_template": bodies[code], "version": (row.version or 1) + 1},
				update_modified=False,
			)
