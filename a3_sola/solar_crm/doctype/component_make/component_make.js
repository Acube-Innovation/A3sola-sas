// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Component Make", {
	setup(frm) {
		frm.set_query("technology", () => ({
			filters: { component_type: frm.doc.component_type, is_active: 1 },
		}));
	},

	component_type(frm) {
		// A technology belongs to one component type; a changed type invalidates it.
		frm.set_value("technology", null);
	},
});
