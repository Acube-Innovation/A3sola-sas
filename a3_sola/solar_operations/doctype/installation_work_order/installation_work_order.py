# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Site execution."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from a3_sola.api import stages
from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company

LINKS = (("solar_installation", "Solar Installation"), ("solar_consumer", "Solar Consumer"))


class InstallationWorkOrder(Document):
	def autoname(self):
		set_name(self, "work_order_series_prefix", ".YYYY.-.#####", fallback="SOL-WO")

	def validate(self):
		assert_same_company(self, LINKS)
		self.validate_dates()
		self.check_crew_conflicts()

	def validate_dates(self):
		if self.planned_end_date and getdate(self.planned_end_date) < getdate(self.planned_start_date):
			frappe.throw(_("Planned end cannot be before planned start."))

	def check_crew_conflicts(self):
		"""A technician on two jobs at once is a job that will not happen."""
		if not (self.planned_start_date and self.planned_end_date):
			return
		for row in self.crew:
			if not row.technician:
				continue
			conflict = frappe.db.sql(
				"""
				select wo.name
				from `tabInstallation Work Order` wo
				join `tabWork Order Crew` crew on crew.parent = wo.name
				where crew.technician = %(technician)s
				  and wo.name != %(name)s
				  and wo.docstatus < 2
				  and wo.status not in ('Cancelled', 'Completed')
				  and wo.planned_start_date <= %(end)s
				  and wo.planned_end_date >= %(start)s
				limit 1
				""",
				{
					"technician": row.technician,
					"name": self.name or "new",
					"start": self.planned_start_date,
					"end": self.planned_end_date,
				},
			)
			if conflict:
				frappe.throw(
					_("{0} is already scheduled on {1} over these dates.").format(
						frappe.bold(row.technician),
						frappe.utils.get_link_to_form("Installation Work Order", conflict[0][0]),
					),
					title=_("Crew Conflict"),
				)

	def before_submit(self):
		if not (self.safety_briefing_done and self.ppe_verified):
			frappe.throw(
				_("The safety briefing and PPE verification must both be recorded before this work order can be submitted."),
				title=_("Safety Checks Required"),
			)

	def on_submit(self):
		self.roll_labour_hours()
		self.prompt_install_advance()

	def roll_labour_hours(self):
		"""Rolled onto the installation for Phase 3 costing to consume."""
		total = frappe.db.sql(
			"""
			select sum(crew.actual_hours)
			from `tabInstallation Work Order` wo
			join `tabWork Order Crew` crew on crew.parent = wo.name
			where wo.solar_installation = %s and wo.docstatus = 1
			""",
			(self.solar_installation,),
		)[0][0]
		frappe.db.set_value(
			"Solar Installation", self.solar_installation, "total_labour_hours", flt(total), update_modified=False
		)

	def prompt_install_advance(self):
		if self.work_order_type != "Testing" or self.status != "Completed":
			return
		outstanding = frappe.db.count(
			"Installation Work Order",
			{"solar_installation": self.solar_installation, "docstatus": 0},
		)
		if outstanding:
			return
		frappe.msgprint(
			_("All work orders for this installation are complete. Advance the INST stage when the completion log and photographs are attached."),
			indicator="blue",
		)


@frappe.whitelist()
def get_technician_schedule(from_date, to_date, company):
	"""Crew utilisation, for the calendar and the dashboard chart."""
	return frappe.db.sql(
		"""
		select crew.technician, wo.name as work_order, wo.work_order_type,
		       wo.planned_start_date, wo.planned_end_date, wo.status,
		       crew.planned_hours, crew.actual_hours, wo.solar_installation
		from `tabInstallation Work Order` wo
		join `tabWork Order Crew` crew on crew.parent = wo.name
		where wo.company = %(company)s
		  and wo.docstatus < 2
		  and wo.planned_start_date <= %(to_date)s
		  and wo.planned_end_date >= %(from_date)s
		order by crew.technician, wo.planned_start_date
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)
