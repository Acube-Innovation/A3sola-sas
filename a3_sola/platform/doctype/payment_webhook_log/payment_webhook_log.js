// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// Reprocessing is offered only for events that passed signature verification. An event
// that failed verification is not trustworthy data - replaying it would be replaying
// whatever an attacker sent.

frappe.ui.form.on("Payment Webhook Log", {
	refresh(frm) {
		if (!frappe.user.has_role(["Platform Billing Manager", "Platform Admin", "System Manager"]))
			return;

		if (frm.doc.signature_verified) {
			frm.add_custom_button(__("Reprocess"), () => {
				frappe.prompt(
					[{ fieldname: "reason", fieldtype: "Small Text", label: __("Why?") }],
					(values) => {
						frappe.call({
							method: "a3_sola.api.admin_actions.reprocess_webhook",
							args: { log_name: frm.doc.name, reason: values.reason },
							freeze: true,
							callback(r) {
								frappe.show_alert({
									message: __("Now: {0}", [(r.message || {}).status || "?"]),
									indicator: "green",
								});
								frm.reload_doc();
							},
						});
					},
					__("Reprocess this event"),
					__("Reprocess")
				);
			});
		} else {
			frm.dashboard.set_headline_alert(
				__(
					"This event did not pass signature verification, so its contents cannot be trusted and it will not be reprocessed."
				),
				"red"
			);
		}

		if (frm.doc.related_doctype && frm.doc.related_name) {
			frm.add_custom_button(
				__("Open {0}", [__(frm.doc.related_doctype)]),
				() => frappe.set_route("Form", frm.doc.related_doctype, frm.doc.related_name),
				__("Actions")
			);
		}
	},
});
