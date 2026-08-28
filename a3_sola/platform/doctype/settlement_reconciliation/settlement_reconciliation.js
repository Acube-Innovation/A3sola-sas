// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Settlement Reconciliation", {
	refresh(frm) {
		if (!frappe.user.has_role(["Platform Billing Manager", "Platform Admin", "System Manager"]))
			return;

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Match Again"), () => {
				frappe.call({
					method: "a3_sola.api.admin_actions.run_reconciliation_for_range",
					args: {
						from_date: frm.doc.settlement_date,
						to_date: frm.doc.settlement_date,
						gateway: frm.doc.gateway,
					},
					freeze: true,
					freeze_message: __("Matching…"),
					callback(r) {
						const out = r.message || {};
						frappe.show_alert({
							message: __("{0} matched, {1} still unmatched.", [
								out.matched || 0,
								out.unmatched || 0,
							]),
							indicator: out.unmatched ? "orange" : "green",
						});
						frm.reload_doc();
					},
				});
			});
		}

		if (frm.doc.unmatched_count) {
			frm.dashboard.set_headline_alert(
				__(
					"{0} line(s) match no payment we hold. Money has moved that this system cannot account for - each one needs explaining before this can be submitted.",
					[frm.doc.unmatched_count]
				),
				"red"
			);
		}
	},
});
