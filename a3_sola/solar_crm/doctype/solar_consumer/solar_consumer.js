// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
//
// The consumer as an ERPNext Customer: made by hand here, or by the first quotation saved.

frappe.ui.form.on("Solar Consumer", {
	refresh(frm) {
		if (frm.is_new()) return;
		if (frm.doc.customer) {
			frm.add_custom_button(__("Customer"), () => frappe.set_route("Form", "Customer", frm.doc.customer), __("View"));
			return;
		}
		frm.add_custom_button(__("Create Customer"), () => {
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
