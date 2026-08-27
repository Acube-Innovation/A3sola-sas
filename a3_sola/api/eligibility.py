# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The subsidy eligibility rule registry.

Rules are functions in a registry, not branches in a controller, so a new rule is a new
function and a scheme change is not a controller rewrite. Every rule returns
(result, remarks) where result is Pass / Fail / Not Applicable.
"""

import frappe
from frappe import _
from frappe.utils import flt

from a3_sola.api import regulation

RULES = []


def rule(code, description, order=0):
	"""Register an eligibility rule."""

	def decorator(fn):
		RULES.append({"code": code, "description": description, "order": order, "fn": fn})
		RULES.sort(key=lambda r: (r["order"], r["code"]))
		return fn

	return decorator


class Context:
	"""Everything a rule may inspect, resolved once."""

	def __init__(self, check):
		self.check = check
		self.consumer = frappe.get_cached_doc("Solar Consumer", check.solar_consumer)
		self.scheme = frappe.get_cached_doc("Subsidy Scheme", check.subsidy_scheme) if check.subsidy_scheme else None
		self.estimate = (
			frappe.get_cached_doc("Solar Design Estimate", check.design_estimate)
			if check.design_estimate
			else None
		)
		self.survey = None
		if self.estimate and self.estimate.site_survey:
			self.survey = frappe.get_cached_doc("Site Survey", self.estimate.site_survey)
		self.package = None
		if self.estimate:
			pkg = self.estimate.solar_package
			if not pkg:
				for row in self.estimate.options:
					if row.is_recommended and row.solar_package:
						pkg = row.solar_package
						break
			if pkg and frappe.db.exists("Solar Package", pkg):
				self.package = frappe.get_cached_doc("Solar Package", pkg)

	@property
	def capacity_kw(self):
		return flt(self.estimate.final_capacity_kw) if self.estimate else 0.0


@rule("ELG-01", "Consumer category matches the scheme's eligible category.", 1)
def _category(ctx):
	if not ctx.scheme:
		return "Not Applicable", _("No scheme selected.")
	if not ctx.scheme.consumer_category:
		return "Pass", _("Scheme has no category restriction.")
	if ctx.consumer.consumer_category == ctx.scheme.consumer_category:
		return "Pass", _("{0} connection.").format(ctx.consumer.consumer_category)
	return "Fail", _("Scheme covers {0}; this connection is {1}.").format(
		ctx.scheme.consumer_category, ctx.consumer.consumer_category
	)


@rule("ELG-02", "No prior central subsidy availed on this connection.", 2)
def _prior_subsidy(ctx):
	if ctx.consumer.has_availed_prior_subsidy:
		return "Fail", _("Prior subsidy recorded: {0} ({1}).").format(
			ctx.consumer.prior_scheme_name or _("scheme not stated"),
			ctx.consumer.prior_subsidy_year or _("year not stated"),
		)
	return "Pass", _("No prior central subsidy on this connection.")


@rule("ELG-03", "Final capacity is within the scheme's maximum eligible capacity.", 3)
def _capacity(ctx):
	if not ctx.scheme or not ctx.scheme.max_eligible_capacity_kw:
		return "Not Applicable", _("Scheme sets no capacity ceiling.")
	if not ctx.estimate:
		return "Not Applicable", _("No design estimate linked.")
	if ctx.capacity_kw <= flt(ctx.scheme.max_eligible_capacity_kw):
		return "Pass", _("{0} kW is within the {1} kW ceiling.").format(
			ctx.capacity_kw, ctx.scheme.max_eligible_capacity_kw
		)
	return "Fail", _("{0} kW exceeds the {1} kW ceiling; subsidy applies only up to the ceiling.").format(
		ctx.capacity_kw, ctx.scheme.max_eligible_capacity_kw
	)


@rule("ELG-04", "Selected package is DCR compliant when the scheme requires it.", 4)
def _dcr(ctx):
	if not ctx.scheme or not ctx.scheme.requires_dcr_modules:
		return "Not Applicable", _("Scheme does not require DCR modules.")
	if not ctx.package:
		return "Fail", _("No package selected, so DCR compliance cannot be established.")
	if ctx.package.is_dcr_compliant:
		return "Pass", _("Package {0} is DCR compliant.").format(ctx.package.name)
	return "Fail", _("Package {0} is not DCR compliant but {1} requires it.").format(
		ctx.package.name, ctx.scheme.scheme_name
	)


@rule("ELG-05", "Scheme is active and today falls within its effective dates.", 5)
def _scheme_active(ctx):
	if not ctx.scheme:
		return "Not Applicable", _("No scheme selected.")
	today = frappe.utils.today()
	if not ctx.scheme.is_active:
		return "Fail", _("Scheme {0} is not active.").format(ctx.scheme.scheme_name)
	if ctx.scheme.effective_from and str(ctx.scheme.effective_from) > today:
		return "Fail", _("Scheme takes effect on {0}.").format(ctx.scheme.effective_from)
	if ctx.scheme.effective_to and str(ctx.scheme.effective_to) < today:
		return "Fail", _("Scheme expired on {0}.").format(ctx.scheme.effective_to)
	return "Pass", _("Scheme is active today.")


@rule("ELG-06", "Consumer number and DISCOM are both populated.", 6)
def _connection(ctx):
	missing = [
		label
		for label, value in ((_("Consumer Number"), ctx.consumer.consumer_number), (_("DISCOM"), ctx.consumer.discom))
		if not value
	]
	if missing:
		return "Fail", _("Missing: {0}.").format(", ".join(missing))
	return "Pass", _("Consumer {0} on {1}.").format(ctx.consumer.consumer_number, ctx.consumer.discom)


@rule("ELG-07", "Installation address is present and matches the consumer's district.", 7)
def _address(ctx):
	if not ctx.consumer.installation_address:
		return "Fail", _("No installation address on the consumer record.")
	district = frappe.db.get_value("DISCOM Section", ctx.consumer.discom_section, "district")
	if not district:
		return "Pass", _("Address present; no district recorded on the section to compare.")
	city = frappe.db.get_value("Address", ctx.consumer.installation_address, "city") or ""
	state = frappe.db.get_value("Address", ctx.consumer.installation_address, "state") or ""
	haystack = f"{city} {state}".lower()
	if district.lower() in haystack or not city:
		return "Pass", _("Address present in {0}.").format(district)
	return "Fail", _("Address city {0} does not match the section district {1}.").format(city, district)


@rule("ELG-08", "Connection type satisfies the grid regulation in force for this capacity.", 8)
def _phase(ctx):
	if not ctx.estimate:
		return "Not Applicable", _("No design estimate linked.")
	# Evaluate as of the check's own date: a back-dated check must reflect the law that
	# applied then, not the law today.
	res = regulation.check_connection_type(
		ctx.capacity_kw,
		ctx.consumer.connection_type,
		ctx.consumer.discom,
		on_date=ctx.check.check_date,
		company=ctx.check.company,
	)
	if res.get("stayed"):
		# A court stay must not fail every quotation.
		return "Not Applicable", res.get("message") or _("Requirement stayed.")
	if res.get("compliant"):
		return "Pass", _("{0} connection is compliant at {1} kW.").format(
			ctx.consumer.connection_type or _("Unspecified"), ctx.capacity_kw
		)
	return "Fail", res.get("message") or _("Connection type is not compliant.")


@rule("ELG-09", "Consumer bank account captured for the Direct Benefit Transfer.", 9)
def _bank(ctx):
	missing = [
		label
		for label, value in (
			(_("Account Holder Name"), ctx.consumer.bank_account_holder_name),
			(_("Account Number"), ctx.consumer.bank_account_no),
			(_("IFSC Code"), ctx.consumer.bank_ifsc_code),
		)
		if not value
	]
	if missing:
		return "Fail", _(
			"Missing {0}. Without these the subsidy cannot be transferred and the 80% registration refund cannot be claimed."
		).format(", ".join(missing))
	return "Pass", _("Bank details on file for DBT and the registration refund.")


@rule("ELG-10", "Site survey EHS status is not Blocked.", 10)
def _ehs(ctx):
	if not ctx.survey:
		return "Not Applicable", _("No site survey linked.")
	if ctx.survey.ehs_overall_status == "Blocked":
		return "Fail", _("Survey {0} is EHS-blocked: {1}").format(
			ctx.survey.name, ctx.survey.ehs_conditions or _("go/no-go criterion failed")
		)
	return "Pass", _("EHS status: {0}.").format(ctx.survey.ehs_overall_status or _("not assessed"))


@rule("ELG-11", "Lender, branch and sanction reference recorded where the sale is financed.", 11)
def _finance(ctx):
	quotation = frappe.db.get_value(
		"Quotation",
		{"solar_consumer": ctx.consumer.name, "docstatus": ["<", 2], "is_financed": 1},
		["name", "lender", "lender_branch", "jan_samarth_id", "loan_sanction_no"],
		as_dict=True,
	)
	if not quotation:
		return "Not Applicable", _("Self-funded sale.")
	missing = [
		label
		for label, value in (
			(_("Lender"), quotation.lender),
			(_("Branch"), quotation.lender_branch),
			(_("Jan Samarth / Sanction Reference"), quotation.jan_samarth_id or quotation.loan_sanction_no),
		)
		if not value
	]
	if missing:
		return "Fail", _("Financed sale missing {0}.").format(", ".join(missing))
	return "Pass", _("Financed via {0}, {1}.").format(quotation.lender, quotation.lender_branch)


def evaluate(check):
	"""Run every registered rule against a Subsidy Eligibility Check.

	Returns a list of dicts. Results are never settable by hand - the caller overwrites the
	child table with this, reapplying any stored waivers.
	"""
	ctx = Context(check)
	results = []
	for entry in RULES:
		try:
			result, remarks = entry["fn"](ctx)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Eligibility rule {entry['code']} failed")
			result, remarks = "Not Applicable", _("Rule could not be evaluated; see the error log.")
		results.append(
			{
				"rule_code": entry["code"],
				"rule_description": entry["description"],
				"result": result,
				"remarks": remarks,
			}
		)
	return results


def overall_result(rows):
	"""Not Eligible on any unwaived failure; Eligible with Conditions on any waiver."""
	results = [r.get("result") if isinstance(r, dict) else r.result for r in rows]
	if "Fail" in results:
		return "Not Eligible"
	if "Waived" in results:
		return "Eligible with Conditions"
	return "Eligible"
