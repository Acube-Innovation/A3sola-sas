// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Platform Subscription", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		if (!frappe.user.has_role(["Platform Billing Manager", "Platform Admin", "System Manager"]))
			return;

		frm.add_custom_button(
			__("Request New Mandate"),
			() => {
				frappe.prompt(
					[
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Why does the mandate need replacing?"),
							description: __(
								"The current mandate is cancelled and collection moves to assisted renewal until the customer authorises a new one."
							),
						},
					],
					(values) => {
						frappe.call({
							method: "a3_sola.api.admin_actions.reregister_mandate",
							args: { platform_subscription: frm.doc.name, reason: values.reason },
							freeze: true,
							callback() {
								frm.reload_doc();
							},
						});
					},
					__("Request a New Mandate"),
					__("Request")
				);
			},
			__("Mandate")
		);

		if (frm.doc.payment_mandate) {
			frm.add_custom_button(
				__("Cancel Mandate"),
				() => {
					frappe.prompt(
						[
							{
								fieldname: "reason",
								fieldtype: "Small Text",
								label: __("What did the customer say?"),
								reqd: 1,
							},
						],
						(values) => {
							frappe.call({
								method: "a3_sola.api.admin_actions.cancel_mandate_as_operator",
								args: { platform_subscription: frm.doc.name, reason: values.reason },
								freeze: true,
								callback() {
									frm.reload_doc();
								},
							});
						},
						__("Cancel on the customer's behalf"),
						__("Cancel Mandate")
					);
				},
				__("Mandate")
			);
		}

		a3_sola.audit.add_button(frm);

		if (frm.doc.route_reason) {
			frm.dashboard.set_headline_alert(
				frappe.utils.escape_html(frm.doc.route_reason),
				frm.doc.collection_route === "Auto Debit" ? "green" : "blue"
			);
		}
	},
});
