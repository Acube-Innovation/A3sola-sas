// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar Proposal", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;

		frm.add_custom_button(__("Generate Proposal"), () => {
			frappe.call({
				method: "a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.generate_proposal",
				args: { solar_proposal: frm.doc.name },
				freeze: true,
				freeze_message: __("Rendering the proposal..."),
				callback: () => frm.reload_doc(),
			});
		});

		if (frm.doc.proposal_pdf) {
			// The client sends from their own WhatsApp number, so this puts the message one
			// tap away rather than pretending to send on their behalf.
			frm.add_custom_button(__("Send on WhatsApp"), () => {
				frappe.call({
					method: "a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.get_whatsapp_link",
					args: { solar_proposal: frm.doc.name },
					callback(r) {
						if (r.message) window.open(r.message, "_blank");
					},
				});
			}, __("Send"));

			frm.add_custom_button(__("Copy Message"), () => {
				frappe.utils.copy_to_clipboard(frm.doc.greeting_message || "");
				frappe.show_alert({ message: __("Message copied"), indicator: "green" });
			}, __("Send"));

			frm.add_custom_button(__("Mark Sent"), () => {
				frappe.prompt(
					[{ fieldname: "sent_via", label: __("Sent Via"), fieldtype: "Select", options: "WhatsApp\nEmail\nPrinted", default: "WhatsApp", reqd: 1 }],
					(values) => {
						frappe.call({
							method: "a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.mark_sent",
							args: { solar_proposal: frm.doc.name, ...values },
							callback: () => frm.reload_doc(),
						});
					},
					__("Mark Sent")
				);
			}, __("Send"));
		}

		if (frm.doc.status === "Superseded" && frm.doc.superseded_by) {
			frm.dashboard.add_comment(
				__("Superseded by {0}", [frappe.utils.get_form_link("Solar Proposal", frm.doc.superseded_by, true)]),
				"orange",
				true
			);
		}
	},
});
