# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Rule-based subsidy eligibility with auditable waivers.

Results are recomputed on every validate and the child table is overwritten - the result
must never be settable by hand. Waivers are stored and reapplied, so a recomputation does
not silently revoke a manager's decision.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from a3_sola.api import eligibility
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("solar_consumer", "Solar Consumer"),
	("design_estimate", "Solar Design Estimate"),
	("subsidy_scheme", "Subsidy Scheme"),
)
WAIVER_ROLES = ("Solar CRM Manager", "Solar Sales Manager", "System Manager")


class SubsidyEligibilityCheck(Document):
	def autoname(self):
		set_name(self, "eligibility_series_prefix", ".YYYY.-.#####", fallback="SOL-ELG")

	def validate(self):
		assert_same_company(self, LINKS)
		self.recompute()

	def recompute(self):
		"""Overwrite the rule table from the registry, reapplying stored waivers."""
		waivers = {
			row.rule_code: (row.waived_by, row.waiver_reason)
			for row in self.rule_results
			if row.result == "Waived"
		}

		self.set("rule_results", [])
		for entry in eligibility.evaluate(self):
			if entry["rule_code"] in waivers and entry["result"] == "Fail":
				waived_by, reason = waivers[entry["rule_code"]]
				entry["result"] = "Waived"
				entry["waived_by"] = waived_by
				entry["waiver_reason"] = reason
			self.append("rule_results", entry)

		self.overall_result = eligibility.overall_result(self.rule_results)


@frappe.whitelist()
def waive_rule(eligibility_check, rule_code, reason):
	"""Waive one failing rule. Manager-only, reason mandatory, stamped and auditable."""
	if not reason or not reason.strip():
		frappe.throw(_("A waiver reason is mandatory."))

	roles = set(frappe.get_roles())
	if not roles.intersection(WAIVER_ROLES):
		frappe.throw(
			_("Only {0} may waive an eligibility rule.").format(", ".join(WAIVER_ROLES)),
			frappe.PermissionError,
		)

	doc = frappe.get_doc("Subsidy Eligibility Check", eligibility_check)
	doc.check_permission("write")

	found = False
	for row in doc.rule_results:
		if row.rule_code == rule_code:
			if row.result not in ("Fail", "Waived"):
				frappe.throw(_("Rule {0} is not failing; there is nothing to waive.").format(rule_code))
			row.result = "Waived"
			row.waived_by = frappe.session.user
			row.waiver_reason = reason.strip()
			found = True
			break
	if not found:
		frappe.throw(_("Rule {0} is not present on this check.").format(rule_code))

	doc.overall_result = eligibility.overall_result(doc.rule_results)
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	doc.add_comment(
		"Comment",
		_("Rule {0} waived by {1}: {2}").format(rule_code, frappe.session.user, reason.strip()),
	)
	return doc.overall_result
