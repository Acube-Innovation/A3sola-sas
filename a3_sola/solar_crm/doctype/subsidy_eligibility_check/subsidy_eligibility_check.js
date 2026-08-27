// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Subsidy Eligibility Check", {
	refresh(frm) {
		const colour = { Eligible: "green", "Eligible with Conditions": "orange", "Not Eligible": "red" };
		if (frm.doc.overall_result) {
			frm.dashboard.add_indicator(__(frm.doc.overall_result), colour[frm.doc.overall_result]);
		}

		const failing = (frm.doc.rule_results || []).filter((r) => r.result === "Fail");
		if (failing.length && frappe.user_roles.some((r) => ["Solar CRM Manager", "Solar Sales Manager", "System Manager"].includes(r))) {
			frm.add_custom_button(__("Waive Rule"), () => {
				frappe.prompt(
					[
						{
							fieldname: "rule_code",
							label: __("Rule"),
							fieldtype: "Select",
							options: failing.map((r) => r.rule_code).join("\n"),
							reqd: 1,
						},
						{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
					],
					(values) => {
						frappe.call({
							method: "a3_sola.solar_crm.doctype.subsidy_eligibility_check.subsidy_eligibility_check.waive_rule",
							args: { eligibility_check: frm.doc.name, ...values },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
					},
					__("Waive Eligibility Rule"),
					__("Waive")
				);
			});
		}
	},
});
