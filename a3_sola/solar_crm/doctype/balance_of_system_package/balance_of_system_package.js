// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// The Component Make type each item's make is drawn from; mirrors MAKE_TYPE in the controller.
const BOS_MAKE_TYPE = {
	DCDB: "DCDB",
	ACDB: "ACDB",
	"DC Cable": "Cable",
	"AC Cable": "Cable",
	Earthing: "Earthing",
	"Lightning Protection": "Lightning Protection",
	"Solar Energy Meter": "Energy Meter",
};

frappe.ui.form.on("Balance of System Package", {
	setup(frm) {
		frm.set_query("inverter_type", () => ({
			filters: { component_type: "Inverter", is_active: 1, company: frm.doc.company },
		}));
		frm.set_query("make", "items", (doc, cdt, cdn) => ({
			filters: {
				component_type: BOS_MAKE_TYPE[locals[cdt][cdn].item] || "",
				is_active: 1,
				company: frm.doc.company,
			},
		}));
	},
});
