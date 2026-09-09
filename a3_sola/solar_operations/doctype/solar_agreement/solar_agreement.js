// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar Agreement", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.docstatus === 0 && frm.doc.stamp_paper_status !== "Purchased") {
			frm.add_custom_button(__("Record Stamp Paper"), () => record_stamp_paper(frm))
				.addClass("btn-primary");
		}

		if (frm.doc.docstatus === 0 && frm.doc.stamp_paper_status === "Purchased") {
			frm.add_custom_button(
				frm.doc.agreement_text ? __("Regenerate Text") : __("Generate Text"),
				() => generate(frm)
			).addClass(frm.doc.agreement_text ? "" : "btn-primary");
		}

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Stamp Paper Data Sheet"), () => data_sheet(frm), __("Generate"));
		}

		if (frm.doc.docstatus === 1 && !frm.doc.is_terminated) {
			frm.add_custom_button(__("Terminate"), () => terminate(frm));
		}

		if (frm.doc.is_terminated) {
			frm.dashboard.set_headline_alert(
				__("Terminated by {0} on {1}: {2}", [
					frm.doc.terminated_by,
					frappe.datetime.str_to_user(frm.doc.terminated_on),
					frm.doc.termination_reason,
				]),
				"red"
			);
		}

		if (frm.doc.agreement_text && frm.doc.is_edited) {
			frm.dashboard.set_headline_alert(
				__("This text was edited after it was generated. Regenerating will discard those edits."),
				"orange"
			);
		}

		if (frm.doc.docstatus === 0 && frm.doc.stamp_paper_status !== "Purchased") {
			frm.dashboard.set_headline_alert(
				__("The agreement is written on stamp paper. Record the purchase before generating the text."),
				"blue"
			);
		}
	},
});

function record_stamp_paper(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Record Stamp Paper"),
		fields: [
			{
				fieldname: "purchased_on",
				fieldtype: "Date",
				label: __("Purchased On"),
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{ fieldname: "serial_no", fieldtype: "Data", label: __("Stamp Paper Serial No") },
			{ fieldname: "cb", fieldtype: "Column Break" },
			{
				fieldname: "value",
				fieldtype: "Currency",
				label: __("Value"),
				default: frm.doc.stamp_paper_value,
			},
			{ fieldname: "vendor", fieldtype: "Data", label: __("Vendor / Treasury") },
		],
		primary_action_label: __("Record"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.solar_operations.doctype.solar_agreement.solar_agreement.record_stamp_paper",
				args: { agreement: frm.doc.name, ...values },
				freeze: true,
				freeze_message: __("Recording the stamp paper…"),
				callback: () => {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function generate(frm) {
	const run = (force) =>
		frappe.call({
			method: "a3_sola.api.agreement.generate",
			args: { agreement: frm.doc.name, force: force ? 1 : 0 },
			freeze: true,
			freeze_message: __("Generating the agreement…"),
			callback: () => frm.reload_doc(),
		});

	if (frm.doc.is_edited) {
		frappe.confirm(
			__("This text was edited after it was generated. Regenerating discards those edits. Continue?"),
			() => run(true)
		);
		return;
	}
	run(false);
}


function data_sheet(frm) {
	frappe.call({
		method: "a3_sola.solar_operations.doctype.solar_agreement.solar_agreement.generate_stamp_paper_data",
		args: { agreement: frm.doc.name },
		freeze: true,
		freeze_message: __("Preparing the data sheet…"),
		callback: (r) => {
			frm.reload_doc();
			if (r.message && r.message.file_url) window.open(r.message.file_url);
		},
	});
}

function terminate(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Terminate Agreement"),
		fields: [
			{
				fieldname: "terminated_by",
				fieldtype: "Select",
				label: __("Terminated By"),
				options: ["Consumer", "DISCOM"],
				reqd: 1,
			},
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
		],
		primary_action_label: __("Terminate"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.solar_operations.doctype.solar_agreement.solar_agreement.terminate",
				args: { agreement: frm.doc.name, ...values },
				freeze: true,
				callback: () => {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}
