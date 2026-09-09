// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
//
// The sales order is the job's first task. What it needs from the customer lives on the
// Solar Consumer; the order fetches it and shows what is still missing.

frappe.ui.form.on("Sales Order", {
	refresh(frm) {
		if (!frm.doc.solar_consumer) return;
		render_kyc(frm);
		frm.add_custom_button(__("Fetch KYC"), () => render_kyc(frm, true), __("Solar"));
		frm.add_custom_button(__("Open Consumer KYC"), () =>
			frappe.set_route("Form", "Solar Consumer", frm.doc.solar_consumer), __("Solar"));
	},
	solar_consumer(frm) {
		if (frm.doc.solar_consumer) render_kyc(frm);
	},
});

function render_kyc(frm, announce) {
	frappe.call({
		method: "a3_sola.api.kyc.get_kyc_status",
		args: { solar_consumer: frm.doc.solar_consumer, sales_order: frm.doc.name },
		callback(r) {
			const status = r.message || { rows: [], missing: [], complete: false };
			const rows = status.rows
				.map(
					(d) => `<tr><td>${frappe.utils.escape_html(d.kyc_type)}</td>
						<td>${d.attachment ? `<a href="${d.attachment}" target="_blank">${__("Open")}</a>` : "—"}</td>
						<td>${frappe.utils.escape_html(d.document_no || "")}</td>
						<td>${d.is_verified ? "✓" : ""}</td></tr>`
				)
				.join("");
			const missing = status.missing.length
				? `<p class="text-danger" style="margin:6px 0 0">${__("Missing")}: ${status.missing.map(frappe.utils.escape_html).join(", ")}</p>`
				: `<p class="text-success" style="margin:6px 0 0">${__("KYC complete")}</p>`;
			const table = rows
				? `<table class="table table-bordered" style="font-size:12px;margin:0">
					<thead><tr><th>${__("Document")}</th><th>${__("File")}</th><th>${__("Number")}</th><th>${__("Verified")}</th></tr></thead>
					<tbody>${rows}</tbody></table>`
				: `<p class="text-muted" style="margin:0">${__("No KYC documents on the consumer yet.")}</p>`;
			if (frm.fields_dict.kyc_html) frm.fields_dict.kyc_html.$wrapper.html(table + missing);
			if (announce) frappe.show_alert({ message: status.complete ? __("KYC complete") : __("KYC incomplete"), indicator: status.complete ? "green" : "orange" });
		},
	});
}
