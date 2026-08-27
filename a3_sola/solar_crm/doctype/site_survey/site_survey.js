// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Site Survey", {
	refresh(frm) {
		const colour = { Cleared: "green", "Cleared with Conditions": "orange", Blocked: "red" };
		if (frm.doc.ehs_overall_status) {
			frm.dashboard.add_indicator(
				__("EHS: {0}", [frm.doc.ehs_overall_status]),
				colour[frm.doc.ehs_overall_status]
			);
		}
		if (frm.doc.ehs_overall_status === "Blocked") {
			frm.dashboard.add_comment(
				__("This survey fails a lender go/no-go criterion and cannot be submitted: {0}", [
					frm.doc.ehs_conditions || "",
				]),
				"red",
				true
			);
		}
	},

	asbestos_present(frm) {
		if (frm.doc.asbestos_present) {
			frappe.msgprint({
				title: __("Go / No-Go Failure"),
				indicator: "red",
				message: __(
					"Roofing containing broken or dilapidated asbestos is a lender go/no-go criterion. This survey cannot be submitted and the job is not financeable."
				),
			});
		}
	},
});
