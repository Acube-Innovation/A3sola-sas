// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const REFERENCE_FIELDS = ["lead", "solar_consumer", "company", "subsidy_scheme", "design_estimate"];
const SNAPSHOT_FIELDS = [
	"consumer_name", "mobile_no", "email_id", "consumer_category", "connection_type",
	"discom", "discom_section", "consumer_number", "roof_type", "capacity_kw", "avg_bill_amount",
];

// Fill the form from whichever reference was picked. Links already set by the user are
// kept; the snapshot is always refreshed because it is read-only and mirrors the source.
function fill_from_reference(frm) {
	if (!frm.doc.lead && !frm.doc.solar_consumer) {
		SNAPSHOT_FIELDS.forEach((f) => frm.set_value(f, null));
		return;
	}
	frappe.call({
		method: "a3_sola.solar_crm.doctype.subsidy_eligibility_check.subsidy_eligibility_check.get_reference_details",
		args: { lead: frm.doc.lead, solar_consumer: frm.doc.solar_consumer, design_estimate: frm.doc.design_estimate },
		callback: ({ message }) => {
			if (!message) return;
			REFERENCE_FIELDS.forEach((f) => {
				if (!frm.doc[f] && message[f]) frm.set_value(f, message[f]);
			});
			SNAPSHOT_FIELDS.forEach((f) => frm.set_value(f, message[f] ?? null));
		},
	});
}

frappe.ui.form.on("Subsidy Eligibility Check", {
	setup(frm) {
		frm.set_query("solar_consumer", () => {
			const filters = {};
			if (frm.doc.company) filters.company = frm.doc.company;
			if (frm.doc.lead) filters.lead = frm.doc.lead;
			return { filters };
		});
		frm.set_query("lead", () => (frm.doc.company ? { filters: { company: frm.doc.company } } : {}));
		frm.set_query("design_estimate", () => ({
			filters: frm.doc.solar_consumer ? { solar_consumer: frm.doc.solar_consumer, docstatus: ["<", 2] } : { docstatus: ["<", 2] },
		}));
	},

	lead(frm) {
		fill_from_reference(frm);
	},

	solar_consumer(frm) {
		fill_from_reference(frm);
	},

	design_estimate(frm) {
		if (frm.doc.lead || frm.doc.solar_consumer) fill_from_reference(frm);
	},

	refresh(frm) {
		if (frm.is_new() && (frm.doc.lead || frm.doc.solar_consumer) && !frm.doc.consumer_name) {
			// Opened from a Lead's or Consumer's connections panel with the link pre-set.
			fill_from_reference(frm);
		}

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
