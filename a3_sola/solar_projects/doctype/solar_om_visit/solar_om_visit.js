// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar OM Visit", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Capture Reading"), () => capture(frm));
		}
	},
});

function capture(frm) {
	// Taken on the roof, not remembered a week later.
	const dialog = new frappe.ui.Dialog({
		title: __("Capture Reading"),
		fields: [
			{
				fieldname: "inverter_lifetime_kwh",
				fieldtype: "Float",
				label: __("Inverter Lifetime Generation (kWh)"),
				default: frm.doc.inverter_lifetime_generation,
			},
			{
				fieldname: "import_reading",
				fieldtype: "Float",
				label: __("Net Meter Import"),
				default: frm.doc.import_reading,
			},
			{
				fieldname: "export_reading",
				fieldtype: "Float",
				label: __("Net Meter Export"),
				default: frm.doc.export_reading,
			},
		],
		primary_action_label: __("Record"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.api.sla.capture_reading",
				args: { om_visit: frm.doc.name, ...values },
				freeze: true,
			}).then((response) => {
				dialog.hide();
				if (response.message) {
					frappe.set_route("Form", "Generation Reading", response.message);
				}
			});
		},
	});
	dialog.show();
}
