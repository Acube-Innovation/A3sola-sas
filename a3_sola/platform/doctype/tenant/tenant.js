// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// Everything an operator does to a live tenant. Terminate is deliberately awkward: it sits
// under a separate group, needs the tenant code typed out, and says in the dialog what it
// will and will not do — because the row above and the row below in the list are other
// people's businesses.

frappe.ui.form.on("Tenant", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		const operator = frappe.user.has_role([
			"Platform Provisioning Operator",
			"Platform Tenant Manager",
			"Platform Admin",
			"System Manager",
		]);
		const manager = frappe.user.has_role([
			"Platform Tenant Manager",
			"Platform Admin",
			"System Manager",
		]);
		if (!operator) return;

		frm.add_custom_button(__("Re-run Isolation Test"), () => rerun_isolation(frm));
		frm.add_custom_button(__("Recalculate Usage"), () => simple(frm, "recalculate_usage"), __("Actions"));
		frm.add_custom_button(__("Resend Welcome"), () => simple(frm, "resend_welcome"), __("Actions"));
		if (manager) {
			frm.add_custom_button(__("Apply Module Entitlements"), () => simple(frm, "apply_entitlements"), __("Actions"));
			frm.add_custom_button(__("Export Tenant Data"), () => export_data(frm), __("Actions"));
			frm.add_custom_button(__("Terminate Tenant"), () => terminate(frm), __("Danger"));
		}
		if (frm.doc.provisioning_job) {
			frm.add_custom_button(
				__("Provisioning Job"),
				() => frappe.set_route("Form", "Provisioning Job", frm.doc.provisioning_job),
				__("Actions")
			);
		}

		headline(frm);
		show_dashboard(frm);
	},
});

function headline(frm) {
	if (frm.doc.status === "Provisioned with Errors") {
		frm.dashboard.set_headline_alert(
			__("This tenant is half-built and has not been handed to the customer. {0}", [
				frappe.utils.escape_html(frm.doc.status_reason || ""),
			]),
			"red"
		);
	} else if (!frm.doc.isolation_test_passed) {
		frm.dashboard.set_headline_alert(
			__("Isolation has not been verified for this tenant."),
			"orange"
		);
	} else if (frm.doc.status === "Active") {
		frm.dashboard.set_headline_alert(
			__("{0} of {1} seats in use.", [frm.doc.active_users || 0, frm.doc.user_quota || 0]),
			"green"
		);
	}
}

function show_dashboard(frm) {
	frappe.call({
		method: "a3_sola.api.tenant_admin.tenant_dashboard",
		args: { tenant: frm.doc.name },
		callback(r) {
			const d = r.message || {};
			if (!d.usage) return;
			const rows = [
				[__("Seats"), `${d.usage.used} used, ${d.usage.pending} invited, ${d.usage.available} free of ${d.usage.quota}`],
				[__("Setup checklist"), `${d.onboarding_percent}% complete`],
			];
			if (d.subscription) {
				rows.push([
					__("Subscription"),
					`${d.subscription.status} · ${d.subscription.billing_cycle} · next ${frappe.datetime.str_to_user(d.subscription.next_billing_date)} · ${d.subscription.collection_route}`,
				]);
			}
			frm.dashboard.add_section(
				`<table class="table table-bordered" style="font-size:12px;margin:0;">
					${rows.map((row) => `<tr><td style="width:180px;">${row[0]}</td><td>${frappe.utils.escape_html(row[1])}</td></tr>`).join("")}
				</table>`,
				__("At a glance")
			);
		},
	});
}

function rerun_isolation(frm) {
	frappe.call({
		method: "a3_sola.api.isolation.rerun",
		args: { tenant: frm.doc.name },
		freeze: true,
		freeze_message: __("Running every check as the tenant's own administrator…"),
		callback(r) {
			frappe.msgprint({
				title: __("Isolation Test"),
				message: (r.message || {}).remarks || __("Done."),
				indicator: "blue",
			});
			frm.reload_doc();
		},
	});
}

function simple(frm, method) {
	frappe.call({
		method: `a3_sola.api.tenant_admin.${method}`,
		args: { tenant: frm.doc.name },
		freeze: true,
		callback() {
			frappe.show_alert({ message: __("Done."), indicator: "green" });
			frm.reload_doc();
		},
	});
}

function export_data(frm) {
	frappe.call({
		method: "a3_sola.api.tenant_admin.export_tenant_data",
		args: { tenant: frm.doc.name },
		freeze: true,
		freeze_message: __("Collecting everything belonging to this tenant…"),
		callback(r) {
			const out = r.message || {};
			frappe.msgprint({
				title: __("Export ready"),
				message: `<p>${__("{0} doctypes exported.", [out.doctypes || 0])}</p>
					<p><a href="${frappe.utils.escape_html(out.file_url || "#")}" target="_blank">${__("Download")}</a></p>`,
				indicator: "green",
			});
		},
	});
}

function terminate(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Terminate {0}", [frm.doc.tenant_name]),
		fields: [
			{
				fieldtype: "HTML",
				options: `<div class="alert alert-warning" style="font-size:13px;">
					<p><b>${__("What this does")}</b>: exports the tenant's data, disables every one of their users, and marks the tenant Terminated.</p>
					<p><b>${__("What it does not do")}</b>: it does not delete the company, and it does not delete any data. Erasure is a separate, deliberate operation that needs a documented request from the customer.</p>
				</div>`,
			},
			{
				fieldname: "confirmation",
				fieldtype: "Data",
				label: __("Type the tenant code to confirm"),
				description: frm.doc.tenant_code,
				reqd: 1,
			},
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Why is this tenant being terminated?"),
				reqd: 1,
			},
		],
		primary_action_label: __("Terminate"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.api.tenant_admin.terminate_tenant",
				args: { tenant: frm.doc.name, ...values },
				freeze: true,
				callback(r) {
					const out = r.message || {};
					dialog.hide();
					frappe.msgprint({
						title: __("Terminated"),
						message: __(
							"{0} users disabled. The company {1} and all its data were kept. Export: {2}",
							[out.users_disabled, out.company_retained, out.export]
						),
						indicator: "orange",
					});
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}
