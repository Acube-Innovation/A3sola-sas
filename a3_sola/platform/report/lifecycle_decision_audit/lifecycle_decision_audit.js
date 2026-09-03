// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.query_reports["Lifecycle Decision Audit"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Date",
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
		},
		{ fieldname: "to_date", label: __("To"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{
			fieldname: "platform_subscription",
			label: __("Subscription"),
			fieldtype: "Link",
			options: "Platform Subscription",
		},
		{ fieldname: "tenant", label: __("Tenant"), fieldtype: "Link", options: "Tenant" },
		{
			fieldname: "event_type",
			label: __("Event"),
			fieldtype: "Select",
			options: [
				"", "Activated", "Renewed", "Entered Past Due", "Entered Grace",
				"Suspension Warned", "Suspended", "Restored", "Plan Upgraded",
				"Plan Downgraded", "Seats Added", "Seats Removed",
				"Cancellation Requested", "Cancelled", "Reactivated",
				"Policy Evaluated", "Manual Override",
			].join("\n"),
		},
		{
			fieldname: "exclude_dry_run",
			label: __("Hide dry-run decisions"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
