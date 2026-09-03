// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.query_reports["Platform Audit"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
		},
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "tenant", label: __("Tenant"), fieldtype: "Link", options: "Tenant" },
		{ fieldname: "actor", label: __("Actor contains"), fieldtype: "Data" },
		{
			fieldname: "source",
			label: __("Source"),
			fieldtype: "Select",
			options: [
				"",
				"Payments and Settings",
				"Subscription Lifecycle",
				"Access Suspensions",
				"Entitlement Changes",
			].join("\n"),
		},
		{
			fieldname: "exclude_dry_run",
			label: __("Hide dry-run decisions"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
