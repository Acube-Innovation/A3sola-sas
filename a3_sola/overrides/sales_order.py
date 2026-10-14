# Copyright (c) 2026, Acube Innovations and contributors
# For license information, please see license.txt
"""Sales Order: the handoff into Solar Operations."""

import frappe



#: Days from today an order's delivery date starts at, on the portal's create form.
DELIVERY_LEAD_DAYS = 7


def working_day(date):
	"""`date`, or the Monday after it when it falls on a Saturday or Sunday."""
	from frappe.utils import add_days, getdate

	date = getdate(date)
	return add_days(date, 7 - date.weekday()) if date.weekday() >= 5 else date


def default_delivery_date():
	"""A week from today, on a working day: what a new order's delivery date starts at."""
	from frappe.utils import add_days, today

	return str(working_day(add_days(today(), DELIVERY_LEAD_DAYS)))


def validate_delivery_dates(doc, method=None):
	"""No delivery on a weekend: the order's date and each item's, where set or changed."""
	from frappe import _
	from frappe.utils import format_date, getdate

	before = doc.get_doc_before_save()
	was = {r.name: r.delivery_date for r in (before.items if before else [])}
	checks = []
	if doc.delivery_date and (not before or str(before.delivery_date) != str(doc.delivery_date)):
		checks.append((_("Delivery Date"), doc.delivery_date))
	for row in doc.get("items") or []:
		if row.delivery_date and str(was.get(row.name)) != str(row.delivery_date):
			checks.append((_("Row {0} delivery date").format(row.idx), row.delivery_date))
	for label, date in checks:
		if getdate(date).weekday() >= 5:
			frappe.throw(
				_("{0} {1} is a {2}. Deliveries are on working days: choose {3} or another weekday.").format(
					label, format_date(date), getdate(date).strftime("%A"), format_date(working_day(date))),
				title=_("Weekend Delivery Date"),
			)


def no_gst_on_solar_orders(doc, method=None):
	"""A solar order carries no GST rows: its price is the package MRP, GST included, and
	the GST is worked out on each milestone invoice by the Solar GST Valuation Rule (goods
	and installation at their own rates) - which one package line cannot show."""
	if not _is_solar_order(doc) or not (doc.get("taxes") or doc.get("taxes_and_charges")):
		return
	doc.taxes_and_charges = None
	doc.set("taxes", [])
	doc.calculate_taxes_and_totals()


def _is_solar_order(doc):
	"""An order raised from a solar quotation, or for a solar package item."""
	for item in doc.get("items") or []:
		if item.get("prevdoc_docname") and frappe.db.get_value("Quotation", item.prevdoc_docname, "solar_package"):
			return True
		if item.item_code and frappe.db.get_value("Item", item.item_code, "item_group") == "Solar Packages":
			return True
	return False


def on_submit(doc, method=None):
	"""Advance the consumer.

	The project (the Solar Installation) is not opened here: the person opens it from the
	order's Next steps on the portal, which runs `handoff.create_solar_installation`.
	"""
	consumer = _solar_consumer_for(doc)
	if not consumer:
		return

	frappe.get_doc("Solar Consumer", consumer).set_status("Converted")
	if not doc.get("solar_consumer"):
		doc.db_set("solar_consumer", consumer, update_modified=False)


def _solar_consumer_for(doc):
	if doc.get("solar_consumer"):
		return doc.solar_consumer
	for item in doc.items:
		if item.prevdoc_docname:
			consumer = frappe.db.get_value("Quotation", item.prevdoc_docname, "solar_consumer")
			if consumer:
				return consumer
	return None
