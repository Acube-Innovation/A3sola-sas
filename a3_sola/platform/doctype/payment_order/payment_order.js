// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// Recovery actions for an order that has gone wrong. The ordering here is deliberate:
// "Fetch Status" is offered first and framed as the thing to try, because it settles a
// disagreement with the gateway's own record. "Mark Paid by Hand" is grouped away under
// Actions and refuses to run while a gateway order exists, so it cannot become the
// reflex.

frappe.ui.form.on("Payment Order", {
	refresh(frm) {
		if (frm.doc.docstatus === 2) return;
		const operator = frappe.user.has_role([
			"Platform Billing Manager",
			"Platform Admin",
			"System Manager",
		]);
		if (!operator) return;

		if (frm.doc.gateway_order_id || frm.doc.gateway_payment_link_id) {
			frm.add_custom_button(__("Fetch Status from Gateway"), () => fetch_status(frm));
		}
		if (frm.doc.status !== "Paid" && frm.doc.platform_subscription) {
			frm.add_custom_button(__("Reissue Payment Link"), () => reissue(frm), __("Actions"));
		}
		if (frm.doc.status !== "Paid" && !frm.doc.gateway_order_id) {
			frm.add_custom_button(__("Mark Paid by Hand"), () => mark_paid(frm), __("Actions"));
		}
		a3_sola.audit.add_button(frm, __("Actions"));

		if (frm.doc.status === "Failed" && frm.doc.last_error_description) {
			frm.dashboard.set_headline_alert(
				__("Last failure: {0}", [frappe.utils.escape_html(frm.doc.last_error_description)]),
				"orange"
			);
		}
	},
});

function fetch_status(frm) {
	frappe.call({
		method: "a3_sola.api.admin_actions.refetch_payment_status",
		args: { payment_order: frm.doc.name },
		freeze: true,
		freeze_message: __("Asking the gateway…"),
		callback(r) {
			const out = r.message || {};
			if (out.discrepancy) {
				frappe.msgprint({
					title: __("Needs a human"),
					message: out.discrepancy,
					indicator: "red",
				});
			} else if (out.changed) {
				frappe.show_alert({ message: __("Payment found and applied."), indicator: "green" });
			} else {
				frappe.show_alert(
					__("The gateway agrees with us: {0}.", [out.gateway_status || __("no change")])
				);
			}
			frm.reload_doc();
		},
	});
}

function reissue(frm) {
	frappe.prompt(
		[
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Why is a new link needed?"),
				description: __("Kept on the record. The customer never sees it."),
			},
		],
		(values) => {
			frappe.call({
				method: "a3_sola.api.admin_actions.reissue_payment_link",
				args: { payment_order: frm.doc.name, reason: values.reason },
				freeze: true,
				callback(r) {
					frappe.msgprint({
						title: __("New link ready"),
						message: `<a href="${frappe.utils.escape_html(
							(r.message || {}).url || "#"
						)}" target="_blank">${__("Open the payment link")}</a>`,
						indicator: "green",
					});
					frm.reload_doc();
				},
			});
		},
		__("Reissue Payment Link"),
		__("Create Link")
	);
}

function mark_paid(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Mark Paid by Hand"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="alert alert-warning" style="font-size:13px;">${__(
					"You are asserting that money arrived which no gateway has confirmed. This is recorded permanently against your name. Use it only for transfers made outside the gateway."
				)}</div>`,
			},
			{
				fieldname: "external_reference",
				fieldtype: "Data",
				label: __("Bank reference, UTR or cheque number"),
				reqd: 1,
			},
			{ fieldname: "received_on", fieldtype: "Date", label: __("Received on") },
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Why are you recording this by hand?"),
				reqd: 1,
				description: __("A sentence. This is what an auditor will read."),
			},
		],
		primary_action_label: __("Record the Payment"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.api.admin_actions.mark_paid_manually",
				args: { payment_order: frm.doc.name, ...values },
				freeze: true,
				callback() {
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}
