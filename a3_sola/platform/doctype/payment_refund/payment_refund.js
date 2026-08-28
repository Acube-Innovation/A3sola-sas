// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Payment Refund", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && frm.doc.status === "Pending Approval") {
			if (
				frappe.user.has_role([
					"Platform Billing Manager",
					"Platform Admin",
					"System Manager",
				])
			) {
				frm.add_custom_button(__("Approve"), () => {
					frappe.confirm(
						__(
							"Approving records your name against this refund permanently. Continue?"
						),
						() => frm.call("approve").then(() => frm.reload_doc())
					);
				}).addClass("btn-primary");
			} else {
				frm.dashboard.set_headline_alert(
					__(
						"This refund is above the approval threshold and needs a billing manager before it can be submitted."
					),
					"orange"
				);
			}
		}

		if (frm.doc.status === "Failed" && frm.doc.failure_reason) {
			frm.dashboard.set_headline_alert(
				__("The gateway refused this refund: {0}", [
					frappe.utils.escape_html(frm.doc.failure_reason),
				]),
				"red"
			);
		}

		if (!frm.is_new()) a3_sola.audit.add_button(frm);
	},
});
