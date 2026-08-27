// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
//
// The outreach cadence on Lead. Logging a contact attempt is the single most-used action
// in the app, so it is two taps on a phone.

frappe.ui.form.on("Lead", {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		if (!frm.doc.solar_consumer && frm.doc.discom) {
			frm.add_custom_button(__("Create Solar Consumer"), () => {
				frappe.call({
					method: "a3_sola.overrides.lead.create_solar_consumer",
					args: { lead: frm.doc.name },
					freeze: true,
					callback(r) {
						if (r.message) frappe.set_route("Form", "Solar Consumer", r.message);
					},
				});
			}, __("Solar"));
		}

		frm.add_custom_button(__("Log Outreach"), () => log_outreach(frm), __("Solar"));

		if (frm.doc.followup_status === "FOLLOW UP DUE") {
			frm.dashboard.add_indicator(__("Follow up due"), "red");
		}
		if (frm.doc.consecutive_non_connects >= 3) {
			frm.dashboard.add_comment(
				__("{0} consecutive non-connects. Consider the breakup message.", [
					frm.doc.consecutive_non_connects,
				]),
				"orange",
				true
			);
		}
	},
});

function log_outreach(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Log Outreach"),
		fields: [
			{ fieldname: "channel", label: __("Channel"), fieldtype: "Select", reqd: 1, default: "Call",
			  options: "Call\nWhatsApp\nEmail\nSMS\nSite Visit\nWalk-in" },
			{ fieldname: "call_status", label: __("Call Status"), fieldtype: "Select",
			  options: "\nNot Answered\nBusy\nSwitched Off\nConnected\nNot Applicable",
			  depends_on: "eval:doc.channel=='Call'" },
			{ fieldname: "outreach_step", label: __("Cadence Step"), fieldtype: "Select",
			  default: frm.doc.outreach_stage || "Step 1: First Contact",
			  options: [
				"Step 1: First Contact", "Step 2: 24hr Nudge", "Step 3: Value/ROI",
				"Step 4: Breakup/Close", "Completed: Proposal Sent", "Ad-hoc",
			  ].join("\n") },
			{ fieldname: "outcome", label: __("Outcome"), fieldtype: "Small Text" },
			{ fieldname: "next_action", label: __("Next Action"), fieldtype: "Small Text" },
		],
		primary_action_label: __("Log"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.api.outreach.log_outreach",
				args: { lead: frm.doc.name, ...values },
				freeze: true,
				callback(r) {
					d.hide();
					frm.reload_doc();
					if (r.message && r.message.next_followup_date) {
						frappe.show_alert({
							message: __("Next follow-up: {0}", [frappe.datetime.str_to_user(r.message.next_followup_date)]),
							indicator: "green",
						});
					}
				},
			});
		},
	});
	d.show();
}
