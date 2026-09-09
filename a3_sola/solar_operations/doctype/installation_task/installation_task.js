// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const CTL = "a3_sola.solar_operations.doctype.installation_task.installation_task";

frappe.ui.form.on("Installation Task", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Open Installation"), () =>
			frappe.set_route("Form", "Solar Installation", frm.doc.solar_installation)
		);

		if (frm.doc.docstatus === 0) {
			if (frm.doc.status === "Pending") {
				frm.add_custom_button(__("Start"), () => call(frm, `${CTL}.start`, {}));
			}
			frm.add_custom_button(__("Mark Completed"), () => {
				frappe.prompt(
					[{ fieldname: "completed_on", label: __("Completed On"), fieldtype: "Date",
					   default: frappe.datetime.get_today(), reqd: 1 }],
					(values) => call(frm, `${CTL}.complete`, values),
					__("Complete {0}", [frm.doc.task_name || frm.doc.task_code]),
					__("Complete")
				);
			}).addClass("btn-primary");
			frm.add_custom_button(__("Skip"), () => {
				frappe.prompt(
					[{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 }],
					(values) => call(frm, `${CTL}.skip`, values),
					__("Skip {0}", [frm.doc.task_name || frm.doc.task_code]),
					__("Skip")
				);
			});
		}

		frm.add_custom_button(__("Attach Evidence"), () => {
			frappe.prompt(
				[
					{ fieldname: "document_name", label: __("Document"), fieldtype: "Data", reqd: 1 },
					{ fieldname: "file_url", label: __("File"), fieldtype: "Attach", reqd: 1 },
					{ fieldname: "document_date", label: __("Date"), fieldtype: "Date",
					  default: frappe.datetime.get_today() },
					{ fieldname: "reference_no", label: __("Reference No"), fieldtype: "Data" },
				],
				(values) => call(frm, `${CTL}.attach_evidence`, values),
				__("Attach Evidence"),
				__("Attach")
			);
		}, __("Documents"));

		frappe.call({
			method: `${CTL}.document_choices`,
			args: { task: frm.doc.name },
			callback(r) {
				(r.message || []).forEach((choice) => {
					frm.add_custom_button(__("Generate {0}", [choice.name]), () =>
						call(frm, `${CTL}.generate`, { template_code: choice.code }), __("Documents"));
				});
			},
		});

		if (["ADV", "BAL"].includes(frm.doc.task_code) && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Pull Bank Tranche"), () =>
				call(frm, `${CTL}.pull_loan_tranche`, {}), __("Payment"));
		}

		if (frm.doc.docstatus === 0 && frm.doc.status !== "Completed") {
			frm.dashboard.set_headline_alert(
				__("Set the status to Completed and submit; the installation's task row completes on submit."),
				"blue"
			);
		}
	},

	task_code(frm) {
		if (frm.doc.task_code === "OTHER") frm.set_df_property("task_name", "read_only", 0);
	},
});

function call(frm, method, args) {
	frappe.call({
		method,
		args: { task: frm.doc.name, ...args },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}
