// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const METHOD = "a3_sola.solar_crm.doctype.solar_proposal.solar_proposal";

function call(frm, method, args, message) {
	return frappe.call({
		method: `${METHOD}.${method}`,
		args: { solar_proposal: frm.doc.name, ...args },
		freeze: true,
		freeze_message: message,
		callback: () => frm.reload_doc(),
	});
}

frappe.ui.form.on("Solar Proposal", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;

		frm.add_custom_button(__("Generate Proposal"), () =>
			call(frm, "generate_proposal", {}, __("Rendering the proposal..."))
		);

		if (frm.doc.proposal_pdf) {
			// The client sends from their own WhatsApp number, so this puts the message one
			// tap away rather than pretending to send on their behalf.
			frm.add_custom_button(__("Send on WhatsApp"), () => {
				frappe.call({
					method: `${METHOD}.get_whatsapp_link`,
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
					[{
						fieldname: "sent_via", label: __("Sent Via"), fieldtype: "Select",
						options: "WhatsApp\nEmail\nPrinted\nHand Delivered", default: "WhatsApp", reqd: 1,
					}],
					(values) => call(frm, "record_dispatch", values, __("Recording dispatch...")),
					__("Mark Sent")
				);
			}, __("Send"));
		}

		// ---- what the customer said, and where that leads ----------------------
		if (frm.doc.current_version) {
			frm.add_custom_button(__("Record Response"), () => {
				frappe.prompt(
					[
						{
							fieldname: "outcome", label: __("Outcome"), fieldtype: "Select", reqd: 1,
							options: "Accepted\nRevision Requested\nRejected\nLost", default: "Accepted",
						},
						{ fieldname: "client_comments", label: __("Comments from Client"), fieldtype: "Small Text" },
						{
							fieldname: "lost_reason", label: __("Lost Reason"), fieldtype: "Small Text",
							depends_on: "eval:['Rejected','Lost'].includes(doc.outcome)",
						},
					],
					(values) => call(frm, "record_response", values, __("Recording the response...")),
					__("Response from Client"),
					__("Record")
				);
			}, __("Client"));

			frm.add_custom_button(__("Revise"), () => {
				frappe.prompt(
					[
						{
							fieldname: "solar_design_estimate", label: __("Design Estimate"), fieldtype: "Link",
							options: "Solar Design Estimate", default: frm.doc.solar_design_estimate,
							description: __("Quote a different estimate on this version, or leave it as it is."),
						},
						{ fieldname: "notes", label: __("Why this revision"), fieldtype: "Small Text" },
					],
					(values) => call(frm, "add_version", values, __("Opening a new version...")),
					__("Revise Proposal"),
					__("Open Version")
				);
			}, __("Client"));
		}

		if (frm.doc.status === "Accepted") {
			frm.add_custom_button(__("Create Quotation"), () => {
				frappe.call({
					method: `${METHOD}.create_quotation`,
					args: { solar_proposal: frm.doc.name },
					freeze: true,
					freeze_message: __("Building the quotation..."),
					callback(r) {
						if (!r.message) return;
						if (r.message.existing) {
							frappe.show_alert({ message: __("This proposal already has a quotation."), indicator: "orange" });
						}
						frappe.set_route("Form", "Quotation", r.message.name);
					},
				});
			}).addClass("btn-primary");
		}

		// ---- banners -----------------------------------------------------------
		const latest = (frm.doc.versions || []).slice(-1)[0];
		if (latest && latest.outcome && latest.outcome !== "Awaiting Response") {
			const tone = { Accepted: "green", "Revision Requested": "orange", Rejected: "red", Lost: "red" }[latest.outcome];
			frm.dashboard.add_comment(
				__("Version {0}: {1}{2}", [
					latest.version_no,
					latest.outcome,
					latest.client_comments ? ` — ${latest.client_comments}` : "",
				]),
				tone,
				true
			);
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
