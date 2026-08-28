// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// One "Audit Trail" button, shared by every record that has one. Kept here rather than
// copied into each doctype script so the dialog stays identical wherever it is opened -
// an auditor should not have to learn two layouts for the same information.

frappe.provide("a3_sola.audit");

a3_sola.audit.show_trail = function (frm) {
	frappe.call({
		method: "a3_sola.api.admin_actions.audit_trail",
		args: { reference_doctype: frm.doctype, reference_name: frm.doc.name },
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint({
					title: __("Audit Trail"),
					message: __("Nothing has been recorded against this record yet."),
				});
				return;
			}
			const body = rows
				.map(
					(row) => `<tr>
						<td style="white-space:nowrap;">${frappe.datetime.str_to_user(row.occurred_on)}</td>
						<td>${frappe.utils.escape_html(row.entry_type || "")}</td>
						<td>${frappe.utils.escape_html(row.subject || "")}</td>
						<td>${frappe.utils.escape_html(row.actor || "")}</td>
						<td>${frappe.utils.escape_html(row.reason || "")}</td>
					</tr>`
				)
				.join("");
			frappe.msgprint({
				title: __("Audit Trail"),
				wide: true,
				message: `<div style="overflow-x:auto;"><table class="table table-bordered" style="font-size:12px;">
					<thead><tr>
						<th>${__("When")}</th><th>${__("Event")}</th><th>${__("Summary")}</th>
						<th>${__("By")}</th><th>${__("Reason")}</th>
					</tr></thead>
					<tbody>${body}</tbody>
				</table></div>`,
			});
		},
	});
};

a3_sola.audit.add_button = function (frm, group) {
	frm.add_custom_button(__("Audit Trail"), () => a3_sola.audit.show_trail(frm), group);
};
