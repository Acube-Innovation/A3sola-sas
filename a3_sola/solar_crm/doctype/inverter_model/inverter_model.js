// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Inverter Model", {
	setup(frm) {
		frm.set_query("inverter_make", () => ({ filters: { component_type: "Inverter" } }));
	},
});
