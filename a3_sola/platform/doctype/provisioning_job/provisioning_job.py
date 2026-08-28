# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""One provisioning run, and the operations surface for when it goes wrong.

"Provisioned with Errors" has to be a workable state rather than a dead end, because it is
the state that happens at three in the afternoon when a customer is waiting. So the actions
here are the ones an operator actually needs: resume from where it stopped, retry the one
step that failed, skip a step that is not mandatory, roll back while that is still safe,
and mark the whole thing resolved with a note about what was done.

Roll Back is deliberately unavailable once the point of no return has been passed, and the
refusal says why rather than just greying out.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from a3_sola.api.naming import set_name
from a3_sola.api.permissions import require_role

OPERATOR_ROLES = (
	"Platform Provisioning Operator",
	"Platform Tenant Manager",
	"Platform Admin",
	"System Manager",
)
MANAGER_ROLES = ("Platform Tenant Manager", "Platform Admin", "System Manager")


class ProvisioningJob(Document):
	def autoname(self):
		set_name(self, "provisioning_job_series_prefix", ".YYYY.-.#####", fallback="PROV")

	def validate(self):
		self.progress_percent = self.computed_progress()

	def computed_progress(self):
		if not self.steps:
			return 0
		done = sum(1 for row in self.steps if row.status in ("Completed", "Skipped"))
		return round(done * 100.0 / len(self.steps), 1)

	# -------------------------------------------------------------- desk actions
	@frappe.whitelist()
	def resume(self):
		"""Continue from the first step that is not Completed."""
		require_role(OPERATOR_ROLES, _("Resuming provisioning"))
		from a3_sola.api.provisioning import orchestrator

		if self.status == "Completed":
			frappe.throw(_("This job already completed."), title=_("Nothing to Resume"))
		return orchestrator.enqueue(self.platform_subscription, "Retry", force=True)

	@frappe.whitelist()
	def retry_step(self, step_code):
		"""Re-run one step. Everything after it is left alone."""
		require_role(OPERATOR_ROLES, _("Retrying a provisioning step"))
		row = self._step(step_code)
		frappe.db.set_value(
			"Provisioning Step Log", row.name,
			{"status": "Pending", "error_message": None, "error_traceback": None},
			update_modified=False,
		)
		frappe.db.commit()
		from a3_sola.api.provisioning import orchestrator

		return orchestrator.enqueue(self.platform_subscription, "Retry", force=True)

	@frappe.whitelist()
	def skip_step(self, step_code, reason):
		"""Step over a non-mandatory step, on the record, with a reason.

		Mandatory steps are refused outright. A skipped CREATE_COMPANY produces a tenant
		with no workspace and a green job, which is the worst combination available.
		"""
		require_role(MANAGER_ROLES, _("Skipping a provisioning step"))
		reason = (reason or "").strip()
		if len(reason) < 10:
			frappe.throw(
				_("Say why this step is being skipped, in a sentence. It stays on the record."),
				title=_("A Reason is Required"),
			)
		from a3_sola.api.provisioning import steps as step_module

		step = step_module.step_for(step_code)
		if not step:
			frappe.throw(_("No such step."), title=_("Unknown Step"))
		if step.is_mandatory:
			frappe.throw(
				_("{0} is mandatory and cannot be skipped. A tenant missing it is not a "
				  "working tenant.").format(step.step_name),
				title=_("Cannot Skip"),
			)
		row = self._step(step_code)
		frappe.db.set_value(
			"Provisioning Step Log", row.name,
			{"status": "Skipped", "remarks": reason[:500], "completed_on": now_datetime()},
			update_modified=False,
		)
		frappe.db.commit()
		return "Skipped"

	@frappe.whitelist()
	def roll_back(self):
		"""Only while it is still safe. Past the line this refuses and explains why."""
		require_role(MANAGER_ROLES, _("Rolling back provisioning"))
		if cint(self.point_of_no_return_passed):
			frappe.throw(
				_("This job passed the point of no return - a user account exists. Rolling "
				  "back now would mean deleting auth state and possibly a company with "
				  "data, which this product never does automatically. Work through "
				  "docs/PROVISIONING_RUNBOOK.md instead."),
				title=_("Cannot Roll Back"),
			)
		from a3_sola.api.provisioning import orchestrator
		from a3_sola.api.provisioning.context import ProvisioningContext
		from a3_sola.api.provisioning.strategies import get_strategy

		subscription = frappe.get_doc("Platform Subscription", self.platform_subscription)
		context = ProvisioningContext(subscription, job=self, triggered_by="Manual")
		if self.tenant and frappe.db.exists("Tenant", self.tenant):
			context.tenant = frappe.get_doc("Tenant", self.tenant)
			context.company = context.tenant.company
		context.strategy = get_strategy(self.tenancy_strategy or "Multi Company")
		clean = orchestrator._rollback(self, context)
		self.db_set(
			{"status": "Rolled Back" if clean else "Failed",
			 "requires_manual_intervention": 0 if clean else 1},
			update_modified=False,
		)
		frappe.db.commit()
		return self.status

	@frappe.whitelist()
	def mark_resolved(self, notes):
		require_role(OPERATOR_ROLES, _("Resolving a provisioning job"))
		notes = (notes or "").strip()
		if len(notes) < 10:
			frappe.throw(
				_("Write down what you did. The next person to see this job needs to know."),
				title=_("Notes Required"),
			)
		self.db_set(
			{
				"requires_manual_intervention": 0,
				"intervention_notes": notes[:2000],
				"resolved_by": frappe.session.user,
				"resolved_on": now_datetime(),
			},
			update_modified=False,
		)
		return "Resolved"

	def _step(self, step_code):
		for row in self.steps:
			if row.step_code == step_code:
				return row
		frappe.throw(_("This job has no step {0}.").format(step_code), title=_("Unknown Step"))


@frappe.whitelist()
def health():
	"""Every job waiting on a human, oldest first - because the oldest is the worst."""
	require_role(OPERATOR_ROLES, _("Viewing provisioning health"))
	return frappe.get_all(
		"Provisioning Job",
		filters={"requires_manual_intervention": 1, "resolved_on": ["is", "not set"]},
		fields=["name", "tenant", "platform_subscription", "status", "current_step",
		        "failure_summary", "point_of_no_return_passed", "modified"],
		order_by="modified asc",
		limit_page_length=200,
	)
