// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
//
// The outreach cadence on Lead. Logging a contact attempt is the single most-used action
// in the app, so it is two taps on a phone.

frappe.ui.form.on("Lead", {
	refresh(frm) {
		if (frm.doc.__islocal) return;

		if (!frm.doc.solar_consumer && frm.doc.discom) {
			frm.add_custom_button(__("Create Customer"), () => consumer_address_dialog(frm), __("Solar"));
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

// The customer's installation site, and the permanent address when it is somewhere else -
// neither required, filled in when known. The site starts where the lead is.
function consumer_address_dialog(frm) {
	const different = 'eval:doc.permanent_address_same=="No"';
	const parts = (prefix, when) => {
		const shown = when ? { depends_on: when } : {};
		return [
			{ fieldname: `${prefix}_address_line1`, fieldtype: "Data", label: __("House Name / Building No."), ...shown },
			{ fieldname: `${prefix}_address_line2`, fieldtype: "Data", label: __("Street / Area"), ...shown },
			{ fieldname: `${prefix}_city`, fieldtype: "Data", label: __("City / Town / Village"), ...shown },
			{ fieldtype: "Column Break" },
			{ fieldname: `${prefix}_state`, fieldtype: "Link", options: "Indian State", label: __("State"), default: "Kerala", ...shown,
				onchange: () => dialog.set_value(`${prefix}_district`, null) },
			{ fieldname: `${prefix}_district`, fieldtype: "Link", options: "Indian District", label: __("District"), ...shown,
				get_query: () => ({ filters: dialog.get_value(`${prefix}_state`) ? { state: dialog.get_value(`${prefix}_state`) } : {} }) },
			{ fieldname: `${prefix}_pincode`, fieldtype: "Data", label: __("PIN Code"), ...shown },
		];
	};
	const dialog = new frappe.ui.Dialog({
		title: __("Customer Address"),
		size: "large",
		fields: [
			{ fieldtype: "Section Break", label: __("Installation Site Address") },
			...parts("site"),
			{ fieldtype: "Section Break", label: __("Permanent Address") },
			{ fieldname: "permanent_address_same", fieldtype: "Select", label: __("Permanent Address Same as Installation Site?"),
				options: "Yes\nNo", default: "Yes", reqd: 1 },
			{ fieldtype: "Section Break", depends_on: different },
			...parts("permanent", different),
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.overrides.lead.create_solar_consumer",
				args: { lead: frm.doc.name, address: values },
				freeze: true,
				callback(r) {
					dialog.hide();
					if (r.message) frappe.set_route("Form", "Solar Consumer", r.message);
				},
			});
		},
	});
	dialog.set_values({ site_city: frm.doc.city, site_state: frm.doc.state || "Kerala" }).then(() => {
		if (frm.doc.district) dialog.set_value("site_district", frm.doc.district);
	});
	dialog.show();
}
