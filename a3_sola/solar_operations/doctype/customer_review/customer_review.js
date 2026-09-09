// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const REVIEW = "a3_sola.solar_operations.doctype.customer_review.customer_review";

frappe.ui.form.on("Customer Review", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open Installation"), () =>
			frappe.set_route("Form", "Solar Installation", frm.doc.solar_installation));

		if (frm.doc.google_review_status !== "Posted") {
			frm.add_custom_button(__("Send Review Link (WhatsApp)"), () => request(frm, "WhatsApp"), __("Google Review"));
			frm.add_custom_button(__("Send Review Link (Email)"), () => request(frm, "Email"), __("Google Review"));
			frm.add_custom_button(__("Open Google Review Page"), () => request(frm, "In Person"), __("Google Review"));
			frm.add_custom_button(__("Mark Posted"), () => posted(frm), __("Google Review"));
			if (frm.doc.google_review_status !== "Declined") {
				frm.add_custom_button(__("Customer Declined"), () => {
					frappe.prompt({ fieldname: "reason", fieldtype: "Small Text", label: __("Why"), reqd: 1 },
						(v) => call(frm, `${REVIEW}.mark_declined`, v), __("Customer Declined"), __("Record"));
				}, __("Google Review"));
			}
		}
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Complete Review"), () =>
				frappe.confirm(__("Complete this review? It will be submitted."), () => call(frm, `${REVIEW}.complete`))
			).addClass("btn-primary");
		}
	},
});

function call(frm, method, extra = {}, then) {
	frappe.call({ method, args: { review: frm.doc.name, ...extra }, freeze: true, callback: (r) => { frm.reload_doc(); if (then) then(r.message); } });
}

function request(frm, via) {
	call(frm, `${REVIEW}.request_review`, { via }, (r) => {
		if (r && r.link) window.open(r.link, "_blank");
	});
}

function posted(frm) {
	frappe.prompt(
		[
			{ fieldname: "link", fieldtype: "Data", label: __("Review Link") },
			{ fieldname: "screenshot", fieldtype: "Attach", label: __("Screenshot") },
			{ fieldname: "posted_on", fieldtype: "Date", label: __("Posted On"), default: frappe.datetime.get_today() },
		],
		(v) => call(frm, `${REVIEW}.mark_posted`, v), __("Google Review Posted"), __("Record")
	);
}
