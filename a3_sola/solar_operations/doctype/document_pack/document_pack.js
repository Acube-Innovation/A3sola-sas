// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const PACK = "a3_sola.solar_operations.doctype.document_pack.document_pack";

frappe.ui.form.on("Document Pack", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open Installation"), () =>
			frappe.set_route("Form", "Solar Installation", frm.doc.solar_installation));
		if (frm.doc.merged_pdf) {
			frm.add_custom_button(__("Open Merged PDF"), () => window.open(frm.doc.merged_pdf));
		}
		if (frm.doc.docstatus !== 0) return;

		frm.add_custom_button(__("Generate All"), () => call(frm, `${PACK}.generate_pack`), __("Documents"));
		frm.add_custom_button(__("Attach Upload"), () => attach_upload(frm), __("Documents"));
		frm.add_custom_button(__("Merge PDF"), () => call(frm, `${PACK}.merge_pdf`), __("Documents"));
		frm.add_custom_button(__("Send by Email"), () => send(frm), __("Documents"));

		const type = frm.doc.pack_type;
		if (type === "KSEB Submission") {
			frm.add_custom_button(__("Mark Submitted to AE"), () => mark_sent(frm));
			frm.add_custom_button(__("Record Acknowledgement"), () => acknowledge(frm));
		} else if (type === "Bank Completion Pack") {
			frm.add_custom_button(__("Mark Sent to Bank"), () => mark_sent(frm, true));
		} else {
			frm.add_custom_button(__("Mark Handed Over"), () => mark_sent(frm, true));
		}
		frm.add_custom_button(__("Complete"), () =>
			frappe.confirm(__("Complete this pack? It will be submitted."), () => call(frm, `${PACK}.complete`))
		).addClass("btn-primary");
		frm.add_custom_button(__("Skip"), () => {
			frappe.prompt(
				{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
				(v) => call(frm, `${PACK}.skip`, v), __("Skip this pack"), __("Skip")
			);
		});
		if (frm.doc.generation_notes) {
			frm.dashboard.set_headline_alert(__("Some items did not generate: see Generation Notes."), "orange");
		}
	},
});

function call(frm, method, extra = {}) {
	frappe.call({ method, args: { pack: frm.doc.name, ...extra }, freeze: true, callback: () => frm.reload_doc() });
}

function attach_upload(frm) {
	frappe.prompt(
		[
			{ fieldname: "document_name", fieldtype: "Data", label: __("Document"), reqd: 1 },
			{ fieldname: "file_url", fieldtype: "Attach", label: __("File"), reqd: 1 },
			{ fieldname: "document_date", fieldtype: "Date", label: __("Date"), default: frappe.datetime.get_today() },
			{ fieldname: "reference_no", fieldtype: "Data", label: __("Reference No") },
		],
		(v) => call(frm, `${PACK}.attach_upload`, v), __("Attach a Document"), __("Attach")
	);
}

function send(frm) {
	frappe.prompt(
		[
			{ fieldname: "recipients", fieldtype: "Data", label: __("To (email)"), reqd: 1 },
			{ fieldname: "message", fieldtype: "Small Text", label: __("Message") },
		],
		(v) => call(frm, `${PACK}.send`, v), __("Send the merged PDF"), __("Send")
	);
}

function mark_sent(frm, with_reference) {
	const fields = [{ fieldname: "on", fieldtype: "Date", label: __("On"), default: frappe.datetime.get_today(), reqd: 1 }];
	if (with_reference) {
		fields.push({ fieldname: "via", fieldtype: "Select", label: __("Via"), options: ["By Hand", "Email", "Bank Portal", "Courier", "WhatsApp"] });
		fields.push({ fieldname: "reference", fieldtype: "Data", label: frm.doc.pack_type === "Bank Completion Pack" ? __("Bank Reference") : __("Handed To") });
	}
	frappe.prompt(fields, (v) => call(frm, `${PACK}.mark_sent`, v), __("Record Delivery"), __("Record"));
}

function acknowledge(frm) {
	frappe.prompt(
		[
			{ fieldname: "acknowledgement_no", fieldtype: "Data", label: __("Acknowledgement No") },
			{ fieldname: "on", fieldtype: "Date", label: __("Acknowledged On"), default: frappe.datetime.get_today(), reqd: 1 },
			{ fieldname: "ae_name", fieldtype: "Data", label: __("Assistant Engineer") },
			{ fieldname: "file_url", fieldtype: "Attach", label: __("Acknowledged Copy") },
		],
		(v) => call(frm, `${PACK}.mark_acknowledged`, v), __("Record the AE's Acknowledgement"), __("Record")
	);
}
