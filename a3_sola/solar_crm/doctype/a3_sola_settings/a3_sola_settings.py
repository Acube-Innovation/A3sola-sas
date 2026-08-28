# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

SETTINGS_DOCTYPE = "A3 Sola Settings"


class A3SolaSettings(Document):
	def validate(self):
		self.validate_payment_gateway()
		self.validate_compliance_windows()
		self.validate_payment_accounts()
		self.validate_tenancy_strategy()
		self.validate_isolation_gate()
		self.record_sensitive_changes()

	def validate_tenancy_strategy(self):
		"""The strategy is architecture, not a toggle.

		Every existing tenant snapshotted the strategy it was built under. Flipping this
		afterwards would leave the setting saying one thing while every workspace on the
		instance was built the other way - and the next provisioning run would use a code
		path nothing else on the site matches. Migrating between models is a project; see
		docs/TENANCY_MODEL.md.
		"""
		if self.is_new() or not self.has_value_changed("tenancy_strategy"):
			return
		if not frappe.db.exists("DocType", "Tenant"):
			return
		count = frappe.db.count("Tenant")
		if count:
			frappe.throw(
				_("{0} tenant(s) already exist, every one of them built under the current "
				  "strategy. Changing the tenancy model now is a migration, not a setting - "
				  "see docs/TENANCY_MODEL.md.").format(count),
				title=_("Strategy Is Locked"),
			)

	def validate_isolation_gate(self):
		"""Switching off the isolation test needs a reason somebody put their name to.

		It is the last line of defence against one tenant reading another's ledger. There
		are legitimate reasons to skip it - a load test, a throwaway site - and none of
		them are "it was slow", so the justification is mandatory and it is kept.
		"""
		if self.run_isolation_test_on_provision:
			return
		if not (self.isolation_test_waiver_reason or "").strip():
			frappe.throw(
				_("Isolation verification is the last thing standing between a new tenant "
				  "and another customer's data. If you are switching it off, record why."),
				title=_("Justification Required"),
			)

	def record_sensitive_changes(self):
		"""Credential and compliance changes go into the permanent trail.

		This runs in validate rather than on_update so the entry is written inside the
		same transaction as the change: if the save is rolled back, so is the record of
		it, and the two never disagree.
		"""
		from a3_sola.api import audit

		audit.record_settings_change(self)

	def validate_payment_gateway(self):
		"""Live mode without credentials fails at the worst possible moment.

		Mock mode deliberately needs nothing: its whole purpose is to let somebody try the
		flow before any account exists.
		"""
		if self.gateway_mode != "Live":
			return
		missing = [
			label
			for label, value in (
				("Key ID", self.razorpay_key_id),
				("Key Secret", self.get_password("razorpay_key_secret", raise_exception=False)),
				("Webhook Secret", self.get_password("razorpay_webhook_secret", raise_exception=False)),
			)
			if not value
		]
		if missing:
			frappe.throw(
				frappe._("Live mode needs {0}. Switching to Live without them would fail on "
				         "the first real customer.").format(", ".join(missing)),
				title=frappe._("Gateway Not Configured"),
			)

	def validate_compliance_windows(self):
		"""24 hours is the regulatory minimum for a pre-debit notice, not a preference."""
		from frappe.utils import cint

		if self.pre_debit_notice_hours and cint(self.pre_debit_notice_hours) < 24:
			frappe.throw(
				frappe._("The pre-debit notice must be at least 24 hours. The RBI e-mandate "
				         "framework requires notifying the customer before every automatic "
				         "debit, and debiting without that notice is a compliance breach."),
				title=frappe._("Below the Regulatory Minimum"),
			)

	def validate_payment_accounts(self):
		"""An account belonging to another company would post one tenant's money elsewhere."""
		for row in self.payment_account_mapping or []:
			for fieldname in (
				"bank_or_clearing_account", "gateway_fee_expense_account",
				"gst_output_igst_account", "gst_output_cgst_account",
				"gst_output_sgst_account", "subscription_revenue_account",
				"unearned_revenue_account", "refund_account",
			):
				account = row.get(fieldname)
				if not account:
					continue
				owner = frappe.db.get_value("Account", account, "company")
				if owner and owner != row.company:
					frappe.throw(
						frappe._("Account {0} belongs to {1}, but the row is for {2}.").format(
							account, owner, row.company
						),
						title=frappe._("Cross-Company Account"),
					)

	pass


def repair_orphan_company_rows():
	"""Drop account-mapping rows for companies that no longer exist.

	Kept as a named entry point because the runbook references it, but the general sweep
	below covers it too.
	"""
	removed = 0
	for child_doctype, fieldname in (
		("Solar Company Account Mapping", "solar_account_mapping"),
		("Platform Payment Account Mapping", "payment_account_mapping"),
	):
		if not frappe.db.table_exists(child_doctype):
			continue
		rows = frappe.get_all(
			child_doctype,
			filters={"parenttype": "A3 Sola Settings", "parentfield": fieldname},
			fields=["name", "company"],
		)
		for row in rows:
			if row.company and not frappe.db.exists("Company", row.company):
				frappe.db.delete(child_doctype, {"name": row.name})
				removed += 1
	if removed:
		frappe.db.commit()
	return removed


def repair_dangling_links():
	"""Null every settings Link that points at a record which no longer exists.

	This singleton holds around forty Link fields - a default DISCOM, a default stage
	template, a source warehouse, a milestone template and so on - and it is saved by the
	installer, by provisioning, and by anyone changing an unrelated setting on a different
	tab. Frappe validates **every** link on **every** save, so one deleted master makes the
	whole of settings unsaveable, and with it seeding, provisioning and every feature that
	writes a setting.

	A dangling link is not a state worth defending: the record it named is gone, and no
	behaviour depends on remembering a name that resolves to nothing. So it is cleared, and
	the seeding that runs immediately afterwards fills it back in with something real.

	It has to be a direct update rather than a `validate` hook, because Frappe checks links
	*before* it runs `validate` - a controller method clearing them would never get the
	chance. Called from the installer, so `bench migrate` heals an affected site.
	"""
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	cleared = {}

	values = frappe.db.get_singles_dict(SETTINGS_DOCTYPE) or {}
	for field in meta.get_link_fields():
		value = values.get(field.fieldname)
		if not value or not field.options:
			continue
		if not frappe.db.exists("DocType", field.options):
			continue
		if frappe.db.exists(field.options, value):
			continue
		frappe.db.set_single_value(SETTINGS_DOCTYPE, field.fieldname, None)
		cleared[field.fieldname] = value

	# Child rows too - a table of message templates is as capable of holding a dead link
	# as the parent is, and it blocks the same save.
	for table_field in meta.get_table_fields():
		child_meta = frappe.get_meta(table_field.options)
		if not frappe.db.table_exists(table_field.options):
			continue
		link_fields = [f for f in child_meta.get_link_fields() if f.options]
		if not link_fields:
			continue
		for row in frappe.get_all(
			table_field.options,
			filters={"parenttype": SETTINGS_DOCTYPE, "parentfield": table_field.fieldname},
			fields=["name"] + [f.fieldname for f in link_fields],
		):
			for field in link_fields:
				value = row.get(field.fieldname)
				if not value or not frappe.db.exists("DocType", field.options):
					continue
				if frappe.db.exists(field.options, value):
					continue
				# A child row whose only purpose is the dead link goes entirely; one with
				# other content keeps its place with the link cleared.
				frappe.db.delete(table_field.options, {"name": row.name})
				cleared[f"{table_field.fieldname}.{field.fieldname}"] = value
				break

	if cleared:
		frappe.db.commit()
		frappe.clear_cache(doctype=SETTINGS_DOCTYPE)
	return cleared
