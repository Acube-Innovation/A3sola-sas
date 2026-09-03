# Copyright (c) 2026, A3 Sola and contributors
# For license information, please see license.txt

"""Connections-panel extensions for the ERPNext doctypes the solar chain
passes through.  Wired up in hooks.override_doctype_dashboards; each one
receives ERPNext's own dashboard data and adds to it rather than
replacing it."""

from frappe import _


def _extend(data, fieldname, groups, non_standard=None):
	"""Merge groups into an existing dashboard definition."""
	data = data or {}
	data.setdefault("fieldname", fieldname)
	data.setdefault("non_standard_fieldnames", {})
	data.setdefault("transactions", [])
	for dt, fn in (non_standard or {}).items():
		data["non_standard_fieldnames"].setdefault(dt, fn)
	already = {i for t in data["transactions"] for i in t.get("items") or []}
	for label, items in groups:
		fresh = [i for i in items if i not in already]
		if not fresh:
			continue
		existing = [t for t in data["transactions"] if t.get("label") == label]
		if existing:
			existing[0]["items"].extend(fresh)
		else:
			data["transactions"].append({"label": label, "items": fresh})
		already.update(fresh)
	return data


def get_lead_dashboard_data(data=None):
	return _extend(
		data,
		"lead",
		[
			(_("Solar pipeline"), ["Solar Consumer", "Solar Proposal"]),
		],
		non_standard={"Solar Consumer": "lead", "Solar Proposal": "lead"},
	)


def get_project_dashboard_data(data=None):
	return _extend(
		data,
		"project",
		[
			(_("Solar delivery"), ["Solar Installation", "Solar Billing Plan", "Statutory Fee Recovery"]),
			(_("Solar service"), ["Solar OM Contract", "Solar OM Visit", "Service Ticket", "Solar Warranty Claim", "Generation Reading"]),
		],
		non_standard={"Solar Installation": "project", "Solar Billing Plan": "project", "Statutory Fee Recovery": "project", "Solar OM Contract": "project", "Solar OM Visit": "project", "Service Ticket": "project", "Solar Warranty Claim": "project", "Generation Reading": "project"},
	)


def get_quotation_dashboard_data(data=None):
	return _extend(
		data,
		"quotation",
		[
			(_("Solar"), ["Solar Installation", "Loan Application"]),
		],
		non_standard={"Solar Installation": "quotation", "Loan Application": "quotation"},
	)


def get_sales_invoice_dashboard_data(data=None):
	return _extend(
		data,
		"sales_invoice",
		[
			(_("Solar"), ["Solar OM Visit", "Subscription Invoice"]),
		],
		non_standard={"Solar OM Visit": "sales_invoice", "Subscription Invoice": "sales_invoice"},
	)


def get_sales_order_dashboard_data(data=None):
	return _extend(
		data,
		"sales_order",
		[
			(_("Solar"), ["Solar Installation", "Project", "Solar Billing Plan"]),
		],
		non_standard={"Solar Installation": "sales_order", "Project": "sales_order", "Solar Billing Plan": "sales_order"},
	)
