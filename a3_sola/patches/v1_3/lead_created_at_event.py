"""Created at Event on the leads an event's QR registration made, so the leads list shows the
event as who created them rather than the event's lead owner.

A lead the event made has the event's own outreach line - "Scanned the QR code at <event>."
or "Registered at <event> by QR code." - written as the lead was created (within minutes).
A lead someone made before the visitor registered has it only later, and is left as it is.
An event renamed since is found by the lead's own event."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import get_datetime

from a3_sola.setup.custom_fields import CUSTOM_FIELDS

FIELD = "a3s_created_at_event"
WITHIN_SECONDS = 300


def execute():
	create_custom_fields({"Lead": [f for f in CUSTOM_FIELDS["Lead"] if f["fieldname"] == FIELD]}, update=True)
	frappe.clear_cache(doctype="Lead")
	events = frappe.get_all("Solar Event", fields=["name", "event_name"])
	for lead in frappe.get_all("Lead", filters={"a3s_event": ["is", "set"], FIELD: ["is", "not set"]},
			fields=["name", "creation", "a3s_event"]):
		rows = frappe.get_all("Outreach Log", filters={"parent": lead.name, "parenttype": "Lead"},
			fields=["contact_datetime", "outcome"], order_by="contact_datetime asc", limit_page_length=3)
		for row in rows:
			if not row.contact_datetime or abs((get_datetime(row.contact_datetime) - get_datetime(lead.creation)).total_seconds()) > WITHIN_SECONDS:
				continue
			text = row.outcome or ""
			if not (text.startswith("Scanned the QR code at ") or (text.startswith("Registered at ") and " by QR code" in text)):
				continue
			# The event named in the line, else (renamed since) the one the lead registered at.
			event = next((e.name for e in events if e.event_name and e.event_name in text), None) or lead.a3s_event
			if event:
				frappe.db.set_value("Lead", lead.name, FIELD, event, update_modified=False)
				break
