# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Site execution.

One order carries every kind of work it covers - structure one week, modules and wiring the
next - and is done by the company's own employees or by a contractor. An installation order
proves itself with photographs that say where they were taken; the bank's completion pack
and the portal both want the coordinates, and a photograph without them is a picture of a
roof somewhere.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime, today

from a3_sola.api.naming import set_name
from a3_sola.api.permissions import assert_same_company
from a3_sola.api.settings import get_int

LINKS = (
	("solar_installation", "Solar Installation"),
	("solar_consumer", "Solar Consumer"),
	("solar_contractor", "Solar Contractor"),
)


class InstallationWorkOrder(Document):
	def autoname(self):
		set_name(self, "work_order_series_prefix", ".YYYY.-.#####", fallback="SOL-WO")

	def validate(self):
		assert_same_company(self, LINKS)
		self.derive_primary_type()
		self.sync_crew_parties()
		self.stamp_task_header()
		self.stamp_photos()
		self.validate_dates()
		self.check_crew_conflicts()

	def derive_primary_type(self):
		"""The old single type, kept for costing and the demo, now follows the first row."""
		if self.work_types:
			self.work_order_type = self.work_types[0].work_type
		elif not self.work_order_type:
			frappe.throw(_("Add at least one work type to the order."), title=_("No Work Type"))
		# Snag work is never an installation task, whatever the form defaulted the kind to.
		if self.work_order_type == "Rectification":
			self.work_order_kind = "Rectification"

	def sync_crew_parties(self):
		"""A crew row is an employee or a contractor; the two columns say the same thing twice.

		`technician` is kept filled for employee rows so labour costing and the O&M visit,
		which reuse this child table, keep reading the column they always read.
		"""
		for row in self.crew:
			if row.party and not row.party_type:
				row.party_type = "Employee"
			if row.party_type == "Employee":
				if row.party and not row.technician:
					row.technician = row.party
				elif row.technician and not row.party:
					row.party = row.technician
				row.party_name = frappe.db.get_value("Employee", row.party, "employee_name") if row.party else None
			elif row.party_type == "Solar Contractor" and row.party:
				row.technician = None
				company, name = frappe.db.get_value("Solar Contractor", row.party, ["company", "contractor_name"])
				if company != self.company:
					frappe.throw(
						_("Contractor {0} belongs to {1}, not {2}.").format(name, company, self.company),
						title=_("Cross-Company Link"),
					)
				row.party_name = name

	def stamp_task_header(self):
		if not self.assigned_by:
			self.assigned_by = frappe.session.user
		if not self.assigned_on:
			self.assigned_on = today()

	def stamp_photos(self):
		count = 0
		for row in self.photos:
			if row.latitude and row.longitude:
				count += 1
				row.map_link = f"https://maps.google.com/?q={flt(row.latitude, 6)},{flt(row.longitude, 6)}"
				if row.geo_source in (None, "", "None"):
					row.geo_source = "Manual"
			else:
				row.map_link = None
			if not row.captured_by:
				row.captured_by = frappe.session.user
			if not row.captured_on:
				row.captured_on = now_datetime()
		self.geo_photo_count = count

	def gate_geo_photos(self):
		"""An installation order proves itself with located photographs, or not at all."""
		if self.work_order_kind != "Installation":
			return
		minimum = get_int("min_geotagged_photos")
		if minimum and cint(self.geo_photo_count) < minimum:
			frappe.throw(
				_("An installation work order needs at least {0} geo-tagged photographs before it is "
				  "submitted; this one has {1}. Capture the location on each photo row.").format(
					minimum, cint(self.geo_photo_count)
				),
				title=_("Photographs Without Location"),
			)

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
		self.gate_geo_photos()
		if not (self.safety_briefing_done and self.ppe_verified):
			frappe.throw(
				_("The safety briefing and PPE verification must both be recorded before this work order can be submitted."),
				title=_("Safety Checks Required"),
			)

	def on_submit(self):
		self.roll_labour_hours()

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
