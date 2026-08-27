// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar Package", {
	refresh(frm) {
		if (frm.doc.__islocal) return;
		if (!frm.doc.item || !frm.doc.bom) {
			frm.add_custom_button(__("Create Item and BOM"), () => {
				frappe.call({
					method: "a3_sola.solar_crm.doctype.solar_package.solar_package.create_item_and_bom",
					args: { solar_package: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
				});
			});
		}
	},
});
