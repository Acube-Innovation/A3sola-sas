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
from frappe.utils import flt

from a3_sola.api import eligibility
from a3_sola.api.settings import get_value
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (
	("lead", "Lead"),
	("solar_consumer", "Solar Consumer"),
	("design_estimate", "Solar Design Estimate"),
	("subsidy_scheme", "Subsidy Scheme"),
)
WAIVER_ROLES = ("Solar CRM Manager", "Solar Sales Manager", "System Manager")

#: The read-only snapshot the form shows. Filled from the Solar Consumer when there is one,
#: otherwise from the Lead - a check can be run before the consumer record exists.
SNAPSHOT_FIELDS = (
	"consumer_name", "mobile_no", "email_id", "consumer_category", "connection_type",
	"discom", "discom_section", "consumer_number", "roof_type", "capacity_kw", "avg_bill_amount",
)


class SubsidyEligibilityCheck(Document):
	def autoname(self):
		set_name(self, "eligibility_series_prefix", ".YYYY.-.#####", fallback="SOL-ELG")

	def validate(self):
		self.resolve_references()
		assert_same_company(self, LINKS)
		self.recompute()

	def resolve_references(self):
		"""Either reference is enough; the other is filled in where the link exists."""
		if not self.lead and not self.solar_consumer:
			frappe.throw(_("Select a Lead or a Solar Consumer to check eligibility for."))
		details = reference_details(self.lead, self.solar_consumer, self.design_estimate)
		for field in ("lead", "solar_consumer", "company", "subsidy_scheme", "design_estimate"):
			if not self.get(field) and details.get(field):
				self.set(field, details[field])
		for field in SNAPSHOT_FIELDS:
			self.set(field, details.get(field))

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
def get_reference_details(lead=None, solar_consumer=None, design_estimate=None):
	"""What the form fills in when a Lead or Solar Consumer is picked."""
	if lead:
		frappe.get_doc("Lead", lead).check_permission("read")
	if solar_consumer:
		frappe.get_doc("Solar Consumer", solar_consumer).check_permission("read")
	return reference_details(lead, solar_consumer, design_estimate)


def reference_details(lead=None, solar_consumer=None, design_estimate=None):
	"""Resolve both references and the consumer snapshot from whichever was given.

	A Lead that has been converted carries its Solar Consumer, and a Solar Consumer carries
	the Lead it came from, so giving either one is enough. The consumer is the richer and
	more current record, so it wins for every field it has a value for; the lead fills the
	gaps and stands in entirely when no consumer exists yet.
	"""
	out = {"lead": lead, "solar_consumer": solar_consumer}
	lead_doc = consumer_doc = None

	if solar_consumer and frappe.db.exists("Solar Consumer", solar_consumer):
		consumer_doc = frappe.get_cached_doc("Solar Consumer", solar_consumer)
		if not lead and consumer_doc.lead:
			out["lead"] = lead = consumer_doc.lead
	if lead and frappe.db.exists("Lead", lead):
		lead_doc = frappe.get_cached_doc("Lead", lead)
		if not consumer_doc and lead_doc.get("solar_consumer") and frappe.db.exists(
			"Solar Consumer", lead_doc.solar_consumer
		):
			out["solar_consumer"] = solar_consumer = lead_doc.solar_consumer
			consumer_doc = frappe.get_cached_doc("Solar Consumer", solar_consumer)

	from_lead = eligibility.consumer_view_from_lead(lead_doc) if lead_doc else frappe._dict()

	def pick(field, lead_field=None):
		value = consumer_doc.get(field) if consumer_doc else None
		return value if value not in (None, "") else from_lead.get(lead_field or field)

	out["company"] = pick("company")
	for field in ("consumer_name", "mobile_no", "email_id", "consumer_category", "connection_type",
			"discom", "discom_section", "consumer_number", "roof_type", "avg_bill_amount"):
		out[field] = pick(field)

	# The scheme: whatever the lead was qualified under, else the company default.
	out["subsidy_scheme"] = (lead_doc.get("subsidy_scheme") if lead_doc else None) or get_value(
		"default_subsidy_scheme"
	)

	# The estimate: the latest live one for the consumer, submitted preferred.
	if not design_estimate and solar_consumer:
		rows = frappe.get_all(
			"Solar Design Estimate",
			filters={"solar_consumer": solar_consumer, "docstatus": ["<", 2]},
			fields=["name", "final_capacity_kw"],
			order_by="docstatus desc, creation desc",
			limit=1,
		)
		if rows:
			design_estimate = rows[0].name
	out["design_estimate"] = design_estimate

	# Capacity: the estimate's final figure, else the size proposed on the lead.
	capacity = frappe.db.get_value("Solar Design Estimate", design_estimate, "final_capacity_kw") if design_estimate else None
	out["capacity_kw"] = flt(capacity) or flt(from_lead.get("capacity_kw"))
	return out


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
