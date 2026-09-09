// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const MDN = "a3_sola.solar_operations.doctype.material_dispatch_notice.material_dispatch_notice";

frappe.ui.form.on("Material Dispatch Notice", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open Installation"), () =>
			frappe.set_route("Form", "Solar Installation", frm.doc.solar_installation));
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Pull Serials"), () => call(frm, `${MDN}.pull_serials`));
		frm.add_custom_button(__("Generate Data Sheet"), () => call(frm, `${MDN}.generate`));
		frm.add_custom_button(__("Send to Contractor"), () => {
			frappe.confirm(
				__("Email the data sheet to {0}? Sending completes the task and submits this notice.", [frm.doc.contractor_email || "—"]),
				() => call(frm, `${MDN}.send`)
			);
		}).addClass("btn-primary");
	},
});

function call(frm, method) {
	frappe.call({ method, args: { notice: frm.doc.name }, freeze: true, callback: () => frm.reload_doc() });
}
