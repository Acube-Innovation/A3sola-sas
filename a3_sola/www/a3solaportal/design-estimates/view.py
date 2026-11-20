# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""View page for one design estimate. All logic is shared; this only names the slug."""

import frappe
from frappe import _

from a3_sola.www.a3solaportal import require_login
from a3_sola.www.a3solaportal.collections import record_route
from a3_sola.www.a3solaportal.collections import detail_context

no_cache = 1


def get_context(context):
	name = (frappe.form_dict.get("name") or "").strip()
	require_login(record_route("design-estimates", name) if name else "/a3solaportal/design-estimates")
	detail_context(context, "design-estimates", name)
	context.design_proposal = design_proposal(name)
	# The customer's site survey, while there is none: assigned to a survey engineer, as on
	# the customer's page (api/survey_assignment).
	context.survey_consumer = frappe.db.get_value("Solar Design Estimate", name, "solar_consumer") if name else None
	if context.survey_consumer:
		from a3_sola.api import survey_assignment

		context.survey_assign = survey_assignment.state(frappe.get_doc("Solar Consumer", context.survey_consumer))
		context.csrf_token = frappe.sessions.get_csrf_token()
	if context.design_proposal or context.get("survey_assign"):
		# Next steps leads with these, before the chain's step.
		context.chain_lead_template = "templates/includes/portal_estimate_next.html"
	return context


def design_proposal(name):
	"""The design proposal this estimate's design is in, to open - else, for someone who may
	make one, the design page's Proposal tab, where it is made from the saved options."""
	from a3_sola.api import portal_estimate, portal_proposal

	if not name or not frappe.db.exists("Solar Design Estimate", name):
		return None
	doc = frappe.get_doc("Solar Design Estimate", name)
	if doc.docstatus == 2:
		return None
	root = portal_estimate.root_of(doc)
	existing = portal_proposal.proposal_of(root)
	if existing and frappe.has_permission("Solar Proposal", "read", existing):
		return {"label": _("Open design proposal"), "route": record_route("proposals", existing)}
	if frappe.has_permission("Solar Proposal", "create"):
		return {"label": _("Create design proposal"), "route": portal_estimate.design_route(root.name) + "?tab=proposal"}
	return None
