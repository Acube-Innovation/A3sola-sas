// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
//
// "Delete with all records" on the Lead and Solar Consumer forms: the same server call as
// the portal's Delete (api/cascade_delete) - shows what goes, asks for the name, deletes.

frappe.provide("a3_sola");

a3_sola.CASCADE_DELETE_ROLES = ["System Manager", "Solar CRM Manager", "Solar Sales Manager"];

a3_sola.add_cascade_delete = function (frm, kind) {
	if (frm.is_new() || !a3_sola.CASCADE_DELETE_ROLES.some((r) => frappe.user.has_role(r))) return;
	frm.add_custom_button(__("Delete with all records"), () => a3_sola.cascade_delete(frm, kind), __("Solar"));
};

a3_sola.cascade_delete = function (frm, kind) {
	const args = { doctype: frm.doctype, name: frm.doc.name };
	frappe.call({
		method: "a3_sola.api.cascade_delete.preview",
		args,
		freeze: true,
		freeze_message: __("Checking what goes with it…"),
	}).then((r) => {
		const p = r.message;
		const rows = (items) => items.map((i) => `<li>${frappe.utils.escape_html(i)}</li>`).join("");
		if (p.blockers.length) {
			frappe.msgprint({
				title: __("Cannot delete {0}", [kind]),
				indicator: "red",
				message: __("These documents are in the accounts. Cancel them first, then delete.") +
					`<ul>${rows(p.blockers.map((b) => `${b.doctype} ${b.name}: ${b.reason}`))}</ul>`,
			});
			return;
		}
		const d = new frappe.ui.Dialog({
			title: __("Delete {0}", [kind]),
			fields: [
				{ fieldtype: "HTML", options:
					`<p>${__("{0} and the {1} records made for them will be deleted, with their attachments:",
						[`<b>${frappe.utils.escape_html(p.title)}</b>`, p.total])}</p>` +
					`<ul>${rows(p.counts.map((c) => `${c.label}: ${c.count}`))}</ul>` },
			],
			primary_action_label: __("Delete {0} records", [p.total]),
			primary_action() {
				frappe.call({
					method: "a3_sola.api.cascade_delete.delete",
					args,
					freeze: true,
					freeze_message: __("Deleting…"),
				}).then(() => {
					d.hide();
					frappe.show_alert({ message: __("Deleted {0} records.", [p.total]), indicator: "green" });
					frappe.set_route("List", frm.doctype);
				});
			},
		});
		d.get_primary_btn().removeClass("btn-primary").addClass("btn-danger");
		d.show();
	});
};
