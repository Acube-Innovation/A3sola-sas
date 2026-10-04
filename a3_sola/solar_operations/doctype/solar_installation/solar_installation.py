# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The central record of the Operations module.

Status, current stage, progress and blocking party are derived on every save and are never
settable by hand.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from a3_sola.api import documents, installation_lead, serials, stages, statutory
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate import unit_count
from a3_sola.solar_crm.doctype.solar_package.solar_package import (
	default_inverter,
	default_module,
)

LINKS = (
	("lead", "Lead"),
	("solar_consumer", "Solar Consumer"),
	("site_survey", "Site Survey"),
	("solar_design_estimate", "Solar Design Estimate"),
	("subsidy_eligibility_check", "Subsidy Eligibility Check"),
	("solar_proposal", "Solar Proposal"),
	("solar_package", "Solar Package"),
	("stage_template", "Installation Stage Template"),
	("discom", "DISCOM"),
	("discom_section", "DISCOM Section"),
	("subsidy_scheme", "Subsidy Scheme"),
	("sales_order", "Sales Order"),
	("quotation", "Quotation"),
)


#: The Design Estimate's system tables, copied onto the job's System tab under the same names.
ESTIMATE_TABLES = (
	"panels", "inverters", "batteries", "bos_items",
	"kseb_expenses", "mounting_expenses", "installation_expenses",
)


class SolarInstallation(Document):
	def autoname(self):
		set_name(self, "installation_series_prefix", ".YYYY.-.#####", fallback="SOL-INST")

	def validate(self):
		self.pull_lead_context()
		self.copy_estimate_design()
		assert_same_company(self, LINKS)
		self.resolve_template()
		self.execution_start_date = self.execution_start_date or self.order_date
		self.pull_consumer_defaults()
		self.apply_package_defaults()
		entered_tasks = self.flags.portal_task_rows
		if not self.stages or (entered_tasks is not None and self.is_new()):
			stages.build_stages(self)
		if entered_tasks:
			stages.apply_entered_tasks(self, entered_tasks)
		self.release_dangling_links()
		self.validate_capacity()
		self.resolve_statutory()
		serials.validate_register(self)
		self.roll_counts()
		stages.recompute(self)

	def resolve_template(self):
		if self.stage_template:
			return
		self.stage_template = stages.resolve_template(
			self.subsidy_scheme,
			self.system_type,
			frappe.db.get_value("Solar Consumer", self.solar_consumer, "consumer_category"),
			self.company,
		)

	def pull_lead_context(self):
		"""Fill the job from its lead: the records it is built from, then the Details tab.

		A job opened by the Sales Order handoff names its consumer and estimate but not the
		lead, so the lead is read back from them. Only blanks are filled - a reference or a
		value somebody chose on the installation stays as chosen. Submitted jobs are left
		alone: their links are fixed, and the backfill patch filled the ones that predate
		the lead.
		"""
		if self.docstatus != 0:
			return
		if not self.lead:
			self.lead = installation_lead.lead_of(
				self.solar_consumer, self.solar_design_estimate, self.solar_proposal
			)
		if not self.lead:
			return  # the mandatory check names the missing lead

		context = installation_lead.lead_context(self.lead, self.solar_consumer)
		if not (self.solar_consumer or context.get("solar_consumer")):
			frappe.throw(
				_("Lead {0} has no Solar Consumer yet. Create the Solar Consumer from the lead first.").format(
					self.lead
				),
				title=_("No Solar Consumer"),
			)
		if self.solar_consumer and installation_lead.consumer_contradicts_lead(self.lead, self.solar_consumer):
			frappe.throw(
				_("Solar Consumer {0} did not come from lead {1}.").format(self.solar_consumer, self.lead),
				title=_("Consumer and Lead Disagree"),
			)

		for field, value in context.items():
			if value not in (None, "") and not self.get(field):
				self.set(field, value)
		# Frappe fetches linked values before `validate` runs, so links set just now - and
		# every link on a job the handoff submits in the same call - fetch here instead.
		self.refresh_fetched(("lead", "solar_consumer", "site_survey", "subsidy_eligibility_check",
			"solar_proposal", "solar_design_estimate", "quotation"))

	def copy_estimate_design(self):
		"""Snapshot the estimate's system tables, and the summary that follows from them.

		Copied while the job is a draft - again whenever another estimate is linked - and
		fixed from submission on, so the job keeps the design it was opened with. The rows
		are read-only here; the design is changed on the estimate.
		"""
		# Rows a person entered on the portal's create page, keyed by table. Those tables keep
		# the estimate's computed rows (they carry a source) and take the rest as entered.
		entered = self.flags.portal_design_rows or {}
		if self.docstatus != 0 or not (self.solar_design_estimate or entered):
			return
		if not entered and not (self.is_new() or self.has_value_changed("solar_design_estimate")) and any(
			self.get(table) for table in ESTIMATE_TABLES
		):
			return

		estimate = (
			frappe.get_doc("Solar Design Estimate", self.solar_design_estimate) if self.solar_design_estimate else None
		)
		for table in ESTIMATE_TABLES:
			rows = [row.as_dict(no_default_fields=True) for row in estimate.get(table)] if estimate else []
			if table in entered:
				rows = [row for row in rows if row.get("source")] + entered[table]
			self.set(table, rows)
		if entered:
			self.work_out_entered_rows(entered)

		# The summary reads the design, not the package's defaults: the estimate is what was sold.
		if self.panels:
			panel = self.panels[0]
			self.module_make = panel.panel_make or self.module_make
			self.module_wattage = panel.panel_capacity_wp or self.module_wattage
			self.module_count = sum(int(row.nos or 0) for row in self.panels) or self.module_count
		if self.inverters:
			inverter = self.inverters[0]
			self.inverter_make = inverter.inverter_make or self.inverter_make
			self.inverter_capacity_kw = inverter.inverter_capacity_kw or self.inverter_capacity_kw

	def work_out_entered_rows(self, entered):
		"""Counts, capacities and amounts for rows typed on the portal, as the estimate works them out.

		Panels are counted to reach the job's capacity, inverters to carry the panels, each
		priced at rate times count; an installation line is priced per kW on the roof type.
		"""
		if "panels" in entered:
			for row in self.panels:
				if row.panel_make and not row.panel_type:
					is_dcr = frappe.db.get_value("Component Make", row.panel_make, "is_dcr")
					row.panel_type = "DCR" if is_dcr else "Non-DCR"
				row.nos = unit_count(flt(self.capacity_kw) * 1000, row.panel_capacity_wp)
				row.total_capacity_kwp = flt(cint(row.nos) * flt(row.panel_capacity_wp) / 1000, 3)
				row.amount = flt(flt(row.rate) * flt(row.nos), 2)
		panel_kwp = flt(sum(flt(row.total_capacity_kwp) for row in self.panels), 3)
		if "inverters" in entered:
			for row in self.inverters:
				row.nos = unit_count(panel_kwp, row.inverter_capacity_kw)
				row.total_capacity_kw = flt(cint(row.nos) * flt(row.inverter_capacity_kw), 3)
				row.amount = flt(flt(row.rate) * flt(row.nos), 2)
		if "installation_expenses" in entered:
			rate = flt(frappe.db.get_value("Roof Type", self.roof_type, "installation_rate_per_kw")) if self.roof_type else 0
			for row in self.installation_expenses:
				if not row.get("source"):
					row.amount = flt((panel_kwp or flt(self.capacity_kw)) * rate, 2)

	def refresh_fetched(self, links):
		for link in links:
			name = self.get(link)
			fetched = self.meta.get_fields_to_fetch(link)
			if not name or not fetched:
				continue
			sources = [df.fetch_from.split(".")[-1] for df in fetched]
			values = frappe.db.get_value(self.meta.get_field(link).options, name, sources, as_dict=True) or {}
			for df in fetched:
				self.set(df.fieldname, values.get(df.fetch_from.split(".")[-1]))

	def pull_consumer_defaults(self):
		"""The consumer record already knows who the party is; carry it across.

		Everything downstream - the billing plan, the O&M contract, the renewal
		opportunity - needs a party, and leaving it blank here strands all three.
		"""
		if self.customer or not self.solar_consumer:
			return
		self.customer = frappe.db.get_value("Solar Consumer", self.solar_consumer, "customer")

	def apply_package_defaults(self):
		"""Carry the package's bill of materials onto the installation.

		The package master is where the client records the actual makes - Rayzon modules,
		Solinteg inverters - and those makes drive serial validation, the DCR declaration
		and every warranty term downstream. Site-specific overrides are respected; only
		blanks are filled.
		"""
		if not self.solar_package or not frappe.db.exists("Solar Package", self.solar_package):
			# A job whose package was later deleted must still open and save; the link
			# validation says what is missing, this must not crash before it gets the chance.
			return
		package = frappe.get_cached_doc("Solar Package", self.solar_package)
		# A package offers several module and inverter options; the job is built with one
		# of each, and which one is the package's own decision, not this form's.
		module = default_module(package)
		inverter = default_inverter(package)
		mapping = {
			"module_make": module.module_make if module else None,
			"module_wattage": module.module_wattage if module else None,
			"module_count": module.module_count if module else None,
			"inverter_make": inverter.inverter_make if inverter else None,
			"inverter_capacity_kw": inverter.inverter_capacity_kw if inverter else None,
			"system_type": package.system_type,
			"connection_type": package.connection_type,
		}
		for fieldname, value in mapping.items():
			if value and not self.get(fieldname):
				self.set(fieldname, value)
		if self.is_new() and not self.is_dcr_compliant:
			self.is_dcr_compliant = package.is_dcr_compliant

	def validate_capacity(self):
		"""Capacity must match the design estimate unless a manager overrode it."""
		if not self.solar_design_estimate:
			return
		designed = flt(
			frappe.db.get_value("Solar Design Estimate", self.solar_design_estimate, "final_capacity_kw"), 3
		)
		if not designed or flt(self.capacity_kw, 3) == designed:
			return
		if not set(frappe.get_roles()).intersection(stages.MANAGER_ROLES):
			frappe.throw(
				_("Capacity {0} kW does not match design estimate {1} at {2} kW. Only an operations manager may override this.").format(
					self.capacity_kw, self.solar_design_estimate, designed
				),
				title=_("Capacity Mismatch"),
			)
		self.flags.capacity_overridden = designed

	def resolve_statutory(self):
		"""Fees follow the capacity. A change of capacity changes what the customer owes."""
		if not (self.discom and self.capacity_kw):
			return
		try:
			fees = statutory.get_statutory_fees(
				self.discom,
				self.connection_type or "Single Phase",
				self.capacity_kw,
				self.net_meter_mode or "Purchased by Customer",
				company=self.company,
			)
		except frappe.ValidationError:
			return
		self.kseb_application_fee = fees["application_fee_gross"]
		self.kseb_registration_fee = fees["registration_fee_gross"]
		self.kseb_registration_refundable = fees["registration_refundable"]
		self.net_meter_charge = fees["net_meter_charge"]
		self.statutory_total = fees["statutory_total"]

	def roll_counts(self):
		if self.is_new():
			return
		self.open_snag_count = frappe.db.count(
			"Installation Snag",
			{"solar_installation": self.name, "status": ["in", ["Open", "In Progress"]], "docstatus": ["<", 2]},
		)
		self.critical_snag_count = frappe.db.count(
			"Installation Snag",
			{
				"solar_installation": self.name,
				"severity": "Critical",
				"status": ["in", ["Open", "In Progress"]],
				"docstatus": ["<", 2],
			},
		)
		self.stale_document_count = len([r for r in self.generated_documents if r.is_stale])
		mandatory = [r for r in self.documents if r.is_mandatory]
		self.document_pack_complete = 1 if mandatory and all(r.attachment for r in mandatory) else 0

	def on_submit(self):
		if self.flags.capacity_overridden:
			self.add_comment(
				"Comment",
				_("Capacity overridden from {0} kW (design estimate) to {1} kW by {2}.").format(
					self.flags.capacity_overridden, self.capacity_kw, frappe.session.user
				),
			)
		# Nothing starts on submit. Tasks are independent: a task begins when somebody opens
		# the document that carries it out, and the job is In Progress from the order.
		stages.recompute(self)

	def before_update_after_submit(self):
		"""Execution happens after submit, so the guards must run here too.

		Serial capture, document generation and stage transitions all edit a submitted
		installation. Running only `validate` would leave the serial uniqueness guard - a
		compliance control, not a nicety - unenforced for the whole life of the job.

		This is the BEFORE hook deliberately: `on_update_after_submit` runs after the row
		has already been written, so anything computed there is silently discarded.
		"""
		serials.validate_register(self)
		self.release_dangling_links()
		self.roll_counts()
		stages.recompute(self)

	def release_dangling_links(self):
		"""A task document deleted behind the engine's back must not make the job unsaveable."""
		if self.is_new():
			return
		from a3_sola.api import tasks

		tasks.release_dangling_links(self)

	def on_cancel(self):
		self.status = "Cancelled"


# ------------------------------------------------------------------ form actions
@frappe.whitelist()
def verify_document(installation, row_name):
	"""Stamp a checklist row as verified. Evidence must be checked, not just attached."""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("write")
	for row in doc.documents:
		if row.name == row_name:
			if not row.attachment:
				frappe.throw(_("Attach {0} before verifying it.").format(row.document_name))
			row.is_verified = 1
			row.verified_by = frappe.session.user
			row.verified_on = frappe.utils.now_datetime()
			break
	else:
		frappe.throw(_("Checklist row not found."))
	doc.flags.ignore_validate_update_after_submit = True
	doc.save(ignore_permissions=True)
	return True


@frappe.whitelist()
def get_task_grid_html(installation):
	"""The task board rendered on the form: one chip per task, coloured by status, with
	the assignee, the due date and the document that carries it out."""
	doc = frappe.get_doc("Solar Installation", installation)
	doc.check_permission("read")
	colours = {
		"Pending": ("#e9ecef", "#495057"),
		"In Progress": ("#cfe2ff", "#084298"),
		"Blocked": ("#f8d7da", "#842029"),
		"Completed": ("#d1e7dd", "#0f5132"),
		"Skipped": ("#f1f3f5", "#868e96"),
	}
	esc = frappe.utils.escape_html
	cells = []
	for row in doc.stages:
		bg, fg = colours.get(row.status, ("#e9ecef", "#495057"))
		if row.is_sla_breached:
			bg, fg = "#f8d7da", "#842029"
		bits = [row.status]
		if row.assigned_to:
			bits.append(esc(frappe.utils.get_fullname(row.assigned_to)))
		if row.due_date and row.status not in ("Completed", "Skipped"):
			bits.append(_("due {0}").format(frappe.utils.formatdate(row.due_date, "dd MMM")))
		elif row.planned_start_date and row.status not in ("Completed", "Skipped"):
			bits.append(_("plan {0} – {1}").format(
				frappe.utils.formatdate(row.planned_start_date, "dd MMM"),
				frappe.utils.formatdate(row.planned_date, "dd MMM"),
			))
		link = ""
		if row.task_document and frappe.db.exists(row.task_doctype, row.task_document):
			link = (
				f'<a href="/app/{frappe.scrub(row.task_doctype).replace("_", "-")}/{esc(row.task_document)}" '
				f'style="color:{fg};text-decoration:underline">{esc(row.task_document)}</a>'
			)
		title = row.skip_reason or row.blocked_reason or f"{row.activity_scope or ''} · {row.status} - SLA {row.sla_days or 0}d"
		cells.append(
			f'<div title="{esc(title)}" style="display:inline-block;width:230px;margin:3px;padding:6px 9px;'
			f'border-radius:6px;font-size:11px;background:{bg};color:{fg};vertical-align:top;'
			f'{"opacity:.6;" if row.status == "Skipped" else ""}">'
			f"<b>{esc(row.stage_code)}</b> · {esc(row.stage_name)}<br>"
			f'<span style="font-size:10px">{" · ".join(bits)}</span>'
			f'{"<br>" + link if link else ""}</div>'
		)
	return "<div style='line-height:1.4'>" + "".join(cells) + "</div>"


@frappe.whitelist()
def get_stage_chain_html(installation):
	"""Kept for anything still calling the old name; renders the task grid."""
	return get_task_grid_html(installation)
