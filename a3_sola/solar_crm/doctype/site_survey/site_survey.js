// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// Each cable total is its legs added up until it is typed over (site_survey.py CABLE_TOTALS).
const CABLE_TOTALS = {
	total_dc_length_m: ["panel_to_dcdb_m", "dcdb_to_inverter_m"],
	total_ac_length_m: ["inverter_to_acdb_m", "acdb_to_meter_m"],
};
const leg_sum = (frm, legs) => flt(legs.reduce((acc, leg) => acc + flt(frm.doc[leg]), 0), 2);

function remember_cable_sums(frm) {
	frm._cable_sums = {};
	for (const [total, legs] of Object.entries(CABLE_TOTALS)) frm._cable_sums[total] = leg_sum(frm, legs);
}

function follow_cable_total(frm, total) {
	const was = (frm._cable_sums || {})[total];
	const now = leg_sum(frm, CABLE_TOTALS[total]);
	if (!flt(frm.doc[total]) || flt(frm.doc[total], 2) === was) frm.set_value(total, now);
	frm._cable_sums[total] = now;
}

const cable_events = {};
for (const [total, legs] of Object.entries(CABLE_TOTALS)) {
	for (const leg of legs) cable_events[leg] = (frm) => follow_cable_total(frm, total);
}
frappe.ui.form.on("Site Survey", cable_events);

frappe.ui.form.on("Site Survey", {
	onload(frm) {
		remember_cable_sums(frm);
	},

	refresh(frm) {
		remember_cable_sums(frm);
		if (!frm.is_new()) {
			// The survey as the team's paper Site Survey Report.
			frm.add_custom_button(__("Site Survey Report"), () =>
				window.open("/api/method/a3_sola.api.survey_print.pdf?survey=" + encodeURIComponent(frm.doc.name))
			);
		}
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
