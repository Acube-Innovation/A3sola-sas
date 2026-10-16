// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
//
// The consumer as an ERPNext Customer: made by hand here, or by the first quotation saved.
// The installation site and the permanent address: each district is offered for its state.

frappe.ui.form.on("Solar Consumer", {
	setup(frm) {
		["site", "permanent"].forEach((prefix) => {
			frm.set_query(`${prefix}_district`, () => {
				const state = frm.doc[`${prefix}_state`];
				return state ? { filters: { state } } : {};
			});
		});
	},
	site_state(frm) {
		clear_district(frm, "site");
	},
	permanent_state(frm) {
		clear_district(frm, "permanent");
	},
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.customer) {
			frm.add_custom_button(__("ERPNext Customer"), () => frappe.set_route("Form", "Customer", frm.doc.customer), __("View"));
			return;
		}
		frm.add_custom_button(__("Create ERPNext Customer"), () => {
			frappe.call({
				method: "a3_sola.solar_crm.doctype.solar_consumer.solar_consumer.make_customer",
				args: { solar_consumer: frm.doc.name },
				freeze: true,
				freeze_message: __("Creating the customer…"),
				callback(r) {
					if (!r.message) return;
					frappe.show_alert({ message: __("Customer {0} linked.", [r.message.customer_name || r.message.customer]), indicator: "green" });
					frm.reload_doc();
				},
			});
		});
	},
});

function clear_district(frm, prefix) {
	const district = frm.doc[`${prefix}_district`];
	const state = frm.doc[`${prefix}_state`];
	if (!district || !state) return;
	frappe.db.get_value("Indian District", district, "state").then((r) => {
		if (r.message && r.message.state !== state) frm.set_value(`${prefix}_district`, null);
	});
}
