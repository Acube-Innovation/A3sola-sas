# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""When a customer is warned, restricted or switched off - held as data.

Everything about the timing of that sequence lives in a record, not in code. A client who
decides 7 days of grace is too harsh edits a row; they do not commission a change.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class SubscriptionPolicy(Document):
	def validate(self):
		self._order_stages()
		self._thresholds_make_sense()
		self._stages_do_not_contradict()

	def on_update(self):
		self._only_one_default()
		_forget_cached_policies()

	def after_insert(self):
		_forget_cached_policies()

	def on_trash(self):
		_forget_cached_policies()

	# ------------------------------------------------------------------ checks
	def _order_stages(self):
		"""Renumber by the order the rows are in, so `sequence` is never a lie."""
		for index, row in enumerate(self.stages, start=1):
			row.sequence = index

	def _thresholds_make_sense(self):
		if cint(self.suspension_after_days) <= cint(self.grace_period_days):
			frappe.throw(
				_("Suspension at day {0} would land on or before grace at day {1}. A "
				  "customer must reach grace, and be warned there, before anything is "
				  "switched off.").format(
					cint(self.suspension_after_days), cint(self.grace_period_days)
				),
				title=_("Thresholds Out of Order"),
			)
		if self.cancellation_after_days and cint(self.cancellation_after_days) <= cint(
			self.suspension_after_days
		):
			frappe.throw(
				_("Cancellation at day {0} would land on or before suspension at day "
				  "{1}.").format(
					cint(self.cancellation_after_days), cint(self.suspension_after_days)
				),
				title=_("Thresholds Out of Order"),
			)

	def _stages_do_not_contradict(self):
		"""Two rules, both learned from policies that looked fine and behaved badly."""
		seen_codes = set()
		last_offset = None
		for row in self.stages:
			code = (row.stage_code or "").strip().upper()
			if not code:
				frappe.throw(_("Row {0}: every stage needs a code.").format(row.idx))
			if code in seen_codes:
				frappe.throw(
					_("Row {0}: stage code {1} is used twice. A stage is identified by "
					  "its code in every event this policy writes.").format(row.idx, code),
					title=_("Duplicate Stage"),
				)
			seen_codes.add(code)
			row.stage_code = code

			# Day-driven stages must run forwards. A stage at day 5 sitting after one at
			# day 12 never fires, and nothing about the record says so.
			if row.trigger_type in ("Days After Due Date", "Days After Failure"):
				offset = cint(row.day_offset)
				if last_offset is not None and offset < last_offset:
					frappe.throw(
						_("Row {0}: day {1} comes before row {2}'s day {3}. Day-driven "
						  "stages have to run forwards or the earlier one never "
						  "fires.").format(row.idx, offset, row.idx - 1, last_offset),
						title=_("Stages Out of Order"),
					)
				last_offset = offset

			if row.notify_tenant and not row.notification_template:
				# Not fatal: the engine falls back to a plain message. But a policy that
				# says it notifies and has nothing to send is worth saying out loud.
				frappe.msgprint(
					_("Stage {0} notifies the tenant but names no template. A plain "
					  "message will be sent instead.").format(code),
					indicator="orange",
					alert=True,
				)

	def _only_one_default(self):
		if not self.is_default:
			return
		others = frappe.get_all(
			"Subscription Policy",
			filters={"is_default": 1, "name": ["!=", self.name]},
			pluck="name",
		)
		for other in others:
			frappe.db.set_value("Subscription Policy", other, "is_default", 0,
			                    update_modified=False)
		if others:
			frappe.msgprint(
				_("{0} is now the default policy; {1} is not.").format(
					self.name, ", ".join(others)
				),
				alert=True,
			)

	# ------------------------------------------------------------------ lookup
	def stage_for(self, days_overdue, dunning_exhausted=False):
		"""The stage that applies at `days_overdue`, or None.

		The latest day-driven stage whose offset has been reached. Reading it that way
		rather than "the next one" means a subscription that goes 20 days unpaid lands on
		the day-15 stage rather than walking through every stage it skipped.
		"""
		reached = None
		for row in sorted(self.stages, key=lambda r: cint(r.sequence)):
			if row.trigger_type == "Dunning Exhausted":
				if dunning_exhausted:
					reached = row
				continue
			if row.trigger_type in ("Days After Due Date", "Days After Failure"):
				if cint(days_overdue) >= cint(row.day_offset):
					reached = row
		return reached


def _forget_cached_policies():
	"""Drop the request-scoped policy list.

	`policy.resolve` caches the active policies for the life of the request, because the
	nightly engine otherwise reads the table once per subscription. That cache has to be
	dropped the moment a policy changes, or a policy created and then resolved in the same
	request - which is what a test does, and what a desk user does when they add one and
	immediately run the engine - resolves against the list as it was beforehand.
	"""
	if hasattr(frappe.local, "_a3s_active_policies"):
		delattr(frappe.local, "_a3s_active_policies")
