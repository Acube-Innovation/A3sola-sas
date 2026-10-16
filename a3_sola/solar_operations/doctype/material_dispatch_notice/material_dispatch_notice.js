// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const MDN = "a3_sola.solar_operations.doctype.material_dispatch_notice.material_dispatch_notice";

frappe.ui.form.on("Material Dispatch Notice", {
	setup(frm) {
		// Any active contractor of the company: one contractor may do both structure and electrical work.
		frm.set_query("solar_contractor", () => ({ filters: { company: frm.doc.company, is_active: 1 } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open Installation"), () =>
			frappe.set_route("Form", "Solar Installation", frm.doc.solar_installation));
		// The data for the completion report, on the letterhead or on plain paper.
		const report = (letterhead) => window.open("/api/method/a3_sola.api.completion_print.pdf?installation=" +
			encodeURIComponent(frm.doc.solar_installation) + "&notice=" + encodeURIComponent(frm.doc.name) +
			"&letterhead=" + (letterhead ? 1 : 0));
		frm.add_custom_button(__("On Letterhead"), () => report(true), __("Completion Report"));
		frm.add_custom_button(__("Without Letterhead"), () => report(false), __("Completion Report"));
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
