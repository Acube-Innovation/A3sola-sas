# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""The electricity connection, not the person.

One Customer may hold several connections, so this is a separate document linked to
Customer rather than fields on Customer.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from a3_sola.api.naming import set_name
from a3_sola.api import kyc, record_links
from a3_sola.api.permissions import assert_same_company

IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PIN_PATTERN = re.compile(r"^[1-9][0-9]{5}$")

#: The parts of an address, each held twice on the consumer: `site_<part>` and `permanent_<part>`.
ADDRESS_PREFIXES = ("site", "permanent")
ADDRESS_PARTS = ("address_line1", "address_line2", "city", "district", "state", "pincode")

LINKS = (
	("customer", "Customer"),
	("discom", "DISCOM"),
	("discom_section", "DISCOM Section"),
	("roof_type", "Roof Type"),
)


class SolarConsumer(Document):
	def autoname(self):
		set_name(self, "consumer_series_prefix", ".YYYY.-.#####", fallback="SOL-CON")

	def validate(self):
		self.ensure_lead()
		record_links.fill_consumer(self)
		self.set_addresses()
		kyc.stamp(self)
		assert_same_company(self, LINKS)
		self.validate_consumer_number_unique()
		self.compute_annual_consumption()
		self.compose_gps()
		self.fill_discom_id()
		self.validate_bank_details()

	def on_update(self):
		record_links.consumer_saved(self)

	def ensure_lead(self):
		"""Every customer hangs off a lead - its installation is opened from it - but the lead
		is not asked for. A customer entered without one is given one: an open lead of the
		same company with the same mobile or email, else a new lead from the customer's own
		details."""
		if self.lead:
			return
		self.lead = open_lead_of(self) or make_lead_for(self)

	def set_addresses(self):
		"""The installation site is typed on the consumer, part by part. The permanent
		address is the same place unless the consumer says it is not - it is what the
		agreement recites as where the consumer resides. Neither is required: a customer is
		saved without them, and they are filled in when known.

		Each is also kept whole (`installation_site_address`, `permanent_address`), one part
		to a line, which is what documents print.
		"""
		if self.installation_address and not self.site_address_line1:
			# Given an Address record instead (the desk, the starter data): its parts.
			for part, value in address_parts(self.installation_address).items():
				if value and not self.get(f"site_{part}"):
					self.set(f"site_{part}", value)
		for prefix in ADDRESS_PREFIXES:
			if prefix == "permanent" and self.permanent_address_same != "No":
				continue
			self.validate_address_parts(prefix)
		self.installation_site_address = self.compose_address("site")
		if self.permanent_address_same != "No":
			self.permanent_address_same = "Yes"
			for part in ADDRESS_PARTS:
				self.set(f"permanent_{part}", self.get(f"site_{part}"))
		self.permanent_address = self.compose_address("permanent")

	def validate_address_parts(self, prefix):
		label = _("Installation site") if prefix == "site" else _("Permanent address")
		pincode = (self.get(f"{prefix}_pincode") or "").strip()
		if pincode:
			if not PIN_PATTERN.match(pincode):
				frappe.throw(_("{0}: PIN code {1} is not valid. Expected six digits.").format(label, frappe.bold(pincode)))
			self.set(f"{prefix}_pincode", pincode)
		district, state = self.get(f"{prefix}_district"), self.get(f"{prefix}_state")
		if district:
			district_state = frappe.db.get_value("Indian District", district, "state")
			if not state:
				self.set(f"{prefix}_state", district_state)
			elif district_state and district_state != state:
				frappe.throw(_("{0}: district {1} is not in {2}.").format(label, frappe.bold(district), frappe.bold(state)))

	def compose_address(self, prefix):
		"""The address one part to a line: house, street, place, then district, state and PIN.
		None while only the state (Kerala, its default) is there: that is no address yet."""
		if not any(self.get(f"{prefix}_{part}") for part in ADDRESS_PARTS if part != "state"):
			return None
		district = self.get(f"{prefix}_district")
		district_name = frappe.db.get_value("Indian District", district, "district_name") if district else None
		last = ", ".join(p for p in (district_name, self.get(f"{prefix}_state")) if p)
		pincode = self.get(f"{prefix}_pincode")
		if pincode:
			last = f"{last} - {pincode}" if last else pincode
		lines = [self.get(f"{prefix}_address_line1"), self.get(f"{prefix}_address_line2"), self.get(f"{prefix}_city"), last]
		return ",\n".join(str(p).strip() for p in lines if p and str(p).strip()) or None

	def validate_consumer_number_unique(self):
		"""A consumer number is unique per DISCOM. Point at the existing record, don't just refuse."""
		if not (self.consumer_number and self.discom):
			return
		existing = frappe.db.get_value(
			"Solar Consumer",
			{"consumer_number": self.consumer_number, "discom": self.discom, "name": ["!=", self.name]},
			["name", "consumer_name"],
			as_dict=True,
		)
		if existing:
			frappe.throw(
				_("Consumer number {0} on {1} already exists as {2} ({3}).").format(
					frappe.bold(self.consumer_number),
					self.discom,
					frappe.utils.get_link_to_form("Solar Consumer", existing.name),
					existing.consumer_name,
				),
				title=_("Duplicate Consumer Number"),
			)

	def compute_annual_consumption(self):
		cycles = 12 if self.billing_frequency == "Monthly" else 6
		self.annual_consumption_units = flt(self.avg_consumption_units) * cycles

	def compose_gps(self):
		if self.latitude and self.longitude:
			self.gps_coordinates = f"{flt(self.latitude, 6)}, {flt(self.longitude, 6)}"
		else:
			self.gps_coordinates = None

	def fill_discom_id(self):
		"""The DISCOM ID is the section office's code - "Chalakudy - 5661" is 5661. Taken from
		the section while blank, and moved with it when the section changes; one typed in
		by hand that is not the old section's code stays."""
		code = frappe.db.get_value("DISCOM Section", self.discom_section, "section_code") if self.discom_section else None
		if not code:
			return
		before = self.get_doc_before_save()
		old = (
			frappe.db.get_value("DISCOM Section", before.discom_section, "section_code")
			if before and before.discom_section else None
		)
		if not self.discom_id or self.discom_id == old:
			self.discom_id = code

	def validate_bank_details(self):
		"""The DBT and the 80% registration refund both land in this account.

		A wrong IFSC is a failed transfer discovered weeks later, and a name mismatch is
		the single most common reason a DBT bounces — so warn, loudly, but do not block:
		the account is often supplied after the survey.
		"""
		# The account is usually in the consumer's own name; a different holder is typed over it.
		if not (self.bank_account_holder_name or "").strip():
			self.bank_account_holder_name = self.consumer_name
		if self.bank_ifsc_code:
			self.bank_ifsc_code = self.bank_ifsc_code.strip().upper()
			if not IFSC_PATTERN.match(self.bank_ifsc_code):
				frappe.throw(
					_("IFSC code {0} is not valid. Expected four letters, a zero, then six alphanumerics.").format(
						frappe.bold(self.bank_ifsc_code)
					)
				)
		if (
			self.bank_account_holder_name
			and self.consumer_name
			and self.bank_account_holder_name.strip().lower() != self.consumer_name.strip().lower()
		):
			frappe.msgprint(
				_("Bank account holder {0} differs from the customer name {1}. A mismatch is the most common cause of a failed Direct Benefit Transfer — confirm it is intended.").format(
					frappe.bold(self.bank_account_holder_name), frappe.bold(self.consumer_name)
				),
				title=_("Check Bank Details"),
				indicator="orange",
			)

	def set_status(self, status):
		"""Status advances through the sales journey and is never set by hand."""
		order = ["New", "Surveyed", "Designed", "Proposed", "Quoted", "Converted"]
		if status == "Dropped" or self.status == "Dropped":
			pass
		elif self.status in order and status in order and order.index(status) < order.index(self.status):
			# never walk the status backwards on a re-submit
			return
		self.db_set("status", status, update_modified=False)


def open_lead_of(doc):
	"""A lead of the customer's company with its mobile or email that no customer has yet."""
	for field in ("mobile_no", "email_id"):
		value = (doc.get(field) or "").strip()
		if not value:
			continue
		name = frappe.db.get_value(
			"Lead", {field: value, "company": doc.company, "solar_consumer": ["is", "not set"]}, "name"
		)
		if name:
			return name
	return None


#: The lead's field for each customer field it is made from.
LEAD_FROM_CUSTOMER = {
	"lead_name": "consumer_name", "company": "company", "mobile_no": "mobile_no", "email_id": "email_id",
	"consumer_category": "consumer_category", "discom": "discom", "discom_section": "discom_section",
	"consumer_number": "consumer_number", "connection_type": "connection_type", "roof_type": "roof_type",
	"city": "site_city", "state": "site_state", "district": "site_district",
}


def make_lead_for(doc):
	"""A new lead made from a customer entered without one, so the job has its enquiry."""
	meta = frappe.get_meta("Lead")
	values = {
		lead_field: doc.get(field) for lead_field, field in LEAD_FROM_CUSTOMER.items()
		if doc.get(field) and (lead_field == "lead_name" or meta.get_field(lead_field))
	}
	# ERPNext refuses a second lead with an email another lead already has.
	if values.get("email_id") and frappe.db.exists("Lead", {"email_id": values["email_id"]}):
		values.pop("email_id")
	lead = frappe.get_doc({"doctype": "Lead", **values})
	lead.flags.ignore_permissions = True
	lead.insert()
	return lead.name


def address_parts(address):
	"""An ERPNext Address as the consumer's address parts, {part: value}. Its county, else
	its city, is taken as the district when the state has a district of that name."""
	row = frappe.db.get_value(
		"Address", address, ["address_line1", "address_line2", "city", "county", "state", "pincode"], as_dict=True
	)
	if not row:
		return {}
	state = row.state if row.state and frappe.db.exists("Indian State", row.state) else None
	district = None
	for place in (row.county, row.city):
		name = place and state and f"{place}, {state}"
		if name and frappe.db.exists("Indian District", name):
			district = name
			break
	return {"address_line1": row.address_line1, "address_line2": row.address_line2, "city": row.city,
		"district": district, "state": state, "pincode": (row.pincode or "").replace(" ", "") or None}


# ------------------------------------------------------------------ the ERPNext Customer
#: The Customer Group a consumer's category lands in.
CUSTOMER_GROUP = {"Residential": "Individual", "Group Housing": "Individual", "Commercial": "Commercial",
	"Industrial": "Commercial", "Government": "Government"}


def ensure_customer(consumer):
	"""The consumer's ERPNext Customer, made the first time it is needed, and linked.

	A consumer becomes a customer when they are quoted - a quotation is raised to a Customer,
	not a Lead. A Customer already made from the consumer's lead is linked rather than
	duplicated; otherwise one is made in the consumer's name, with their mobile and email
	(ERPNext makes the primary contact from them), their category's group, and the
	installation address linked to it. Returns the Customer's name.
	"""
	doc = frappe.get_doc("Solar Consumer", consumer) if isinstance(consumer, str) else consumer
	if doc.customer and frappe.db.exists("Customer", doc.customer):
		return doc.customer
	name = frappe.db.get_value("Customer", {"lead_name": doc.lead}, "name") if doc.lead else None
	if not name:
		individual = (doc.consumer_category or "Residential") in ("Residential", "Group Housing")
		group = CUSTOMER_GROUP.get(doc.consumer_category or "Residential", "Individual")
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": doc.consumer_name,
			"customer_type": "Individual" if individual else "Company",
			"customer_group": group if frappe.db.exists("Customer Group", group)
				else frappe.db.get_single_value("Selling Settings", "customer_group") or "All Customer Groups",
			"territory": "India" if frappe.db.exists("Territory", "India")
				else frappe.db.get_single_value("Selling Settings", "territory") or "All Territories",
			"gst_category": "Unregistered",
			"lead_name": doc.lead or None,
			"mobile_no": doc.mobile_no or None,
			"email_id": doc.email_id or None,
		})
		customer.flags.ignore_permissions = True
		customer.insert()
		name = customer.name
	# The installation address is the customer's address too.
	if doc.installation_address and not frappe.db.exists("Dynamic Link", {"parenttype": "Address",
			"parent": doc.installation_address, "link_doctype": "Customer", "link_name": name}):
		address = frappe.get_doc("Address", doc.installation_address)
		address.append("links", {"link_doctype": "Customer", "link_name": name})
		address.flags.ignore_permissions = True
		address.save()
	doc.db_set("customer", name)
	return name


@frappe.whitelist()
def make_customer(solar_consumer):
	"""Convert the consumer to an ERPNext Customer (or link the one already made from its
	lead), from the consumer's desk form or portal page."""
	doc = frappe.get_doc("Solar Consumer", solar_consumer)
	doc.check_permission("write")
	frappe.has_permission("Customer", "create", throw=True)
	customer = ensure_customer(doc)
	return {"customer": customer, "customer_name": frappe.db.get_value("Customer", customer, "customer_name"),
		"route": "/app/customer/" + frappe.utils.quote(customer)}
