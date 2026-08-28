// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Subscription Invoice", {
	refresh(frm) {
		if (!frm.is_new()) a3_sola.audit.add_button(frm);

		if (frm.doc.docstatus === 1 && frm.doc.payment_status !== "Paid") {
			frm.dashboard.set_headline_alert(
				__("Outstanding: {0}", [
					format_currency(
						frm.doc.grand_total - (frm.doc.paid_amount || 0),
						frm.doc.currency
					),
				]),
				"orange"
			);
		}
		if (frm.doc.posting_status === "Not Posted" && frm.doc.docstatus === 1) {
			frm.dashboard.add_comment(
				__(
					"Nothing has reached the ledger for this invoice. Payment postings are switched off in A3 Sola Settings."
				),
				"blue",
				true
			);
		}
	},
});
