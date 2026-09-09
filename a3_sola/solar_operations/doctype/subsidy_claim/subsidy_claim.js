// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const CLAIM = "a3_sola.solar_operations.doctype.subsidy_claim.subsidy_claim";

frappe.ui.form.on("Subsidy Claim", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus !== 1) return;
		const open = (frm.doc.corrections || []).filter((r) => !r.resubmitted_on);
		if (open.some((r) => !r.correction_done)) {
			frm.add_custom_button(__("Record Correction"), () => {
				const todo = open.filter((r) => !r.correction_done);
				frappe.prompt(
					[
						{ fieldname: "row_name", fieldtype: "Select", label: __("Correction"), reqd: 1,
						  options: todo.map((r) => ({ label: `${r.raised_on}: ${(r.reason || "").slice(0, 60)}`, value: r.name })) },
						{ fieldname: "corrected_on", fieldtype: "Date", label: __("Corrected On"), default: frappe.datetime.get_today(), reqd: 1 },
						{ fieldname: "attachment", fieldtype: "Attach", label: __("Proof") },
						{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
					],
					(v) => frappe.call({ method: `${CLAIM}.record_correction`, args: { subsidy_claim: frm.doc.name, ...v }, freeze: true, callback: () => frm.reload_doc() }),
					__("Record a Correction"), __("Record")
				);
			});
		}
		if (open.length && open.every((r) => r.correction_done)) {
			frm.add_custom_button(__("Mark Resubmitted"), () =>
				frappe.call({ method: `${CLAIM}.mark_resubmitted`, args: { subsidy_claim: frm.doc.name }, freeze: true, callback: () => frm.reload_doc() })
			).addClass("btn-primary");
		}
	},
});
