// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// "Provisioned with Errors" has to be a workable state rather than a dead end, because it
// is the state that happens while a customer is waiting. Roll Back disappears once the
// point of no return has been passed, and the button says why rather than just vanishing.

frappe.ui.form.on("Provisioning Job", {
	refresh(frm) {
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
		if (!operator || frm.doc.docstatus === 2) return;

		if (frm.doc.status !== "Completed") {
			frm.add_custom_button(__("Resume"), () => {
				frappe.call({
					method: "resume",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Continuing from the first step that is not complete…"),
					callback: () => frm.reload_doc(),
				});
			}).addClass("btn-primary");
		}

		const failed = (frm.doc.steps || []).filter((row) => row.status === "Failed");
		failed.forEach((row) => {
			frm.add_custom_button(
				__("Retry {0}", [row.step_name]),
				() => {
					frappe.call({
						method: "retry_step",
						doc: frm.doc,
						args: { step_code: row.step_code },
						freeze: true,
						callback: () => frm.reload_doc(),
					});
				},
				__("Retry a Step")
			);
		});

		(frm.doc.steps || [])
			.filter((row) => ["Failed", "Pending"].includes(row.status))
			.forEach((row) => {
				frm.add_custom_button(
					__("Skip {0}", [row.step_name]),
					() => skip(frm, row),
					__("Skip a Step")
				);
			});

		if (manager) {
			if (!frm.doc.point_of_no_return_passed) {
				frm.add_custom_button(__("Roll Back"), () => {
					frappe.confirm(
						__("This undoes every reversible step and leaves the system as it was. Continue?"),
						() =>
							frappe.call({
								method: "roll_back",
								doc: frm.doc,
								freeze: true,
								callback: () => frm.reload_doc(),
							})
					);
				}, __("Danger"));
			} else {
				frm.add_custom_button(__("Why can't I roll back?"), () => {
					frappe.msgprint({
						title: __("Past the point of no return"),
						message: __(
							"A user account exists for this tenant. Rolling back now would mean deleting auth state and possibly a company with data, which this product never does automatically. Work through docs/PROVISIONING_RUNBOOK.md instead."
						),
						indicator: "orange",
					});
				}, __("Danger"));
			}
		}

		if (frm.doc.requires_manual_intervention) {
			frm.add_custom_button(__("Mark Resolved"), () => resolve(frm));
			frm.dashboard.set_headline_alert(
				__("Waiting for a human at {0}. {1}", [
					frm.doc.current_step || "?",
					frappe.utils.escape_html(frm.doc.failure_summary || ""),
				]),
				"red"
			);
		}
	},
});

function skip(frm, row) {
	frappe.prompt(
		[
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Why is {0} being skipped?", [row.step_name]),
				reqd: 1,
				description: __("Kept on the record. Mandatory steps cannot be skipped at all."),
			},
		],
		(values) => {
			frappe.call({
				method: "skip_step",
				doc: frm.doc,
				args: { step_code: row.step_code, reason: values.reason },
				freeze: true,
				callback: () => frm.reload_doc(),
			});
		},
		__("Skip a step"),
		__("Skip")
	);
}

function resolve(frm) {
	frappe.prompt(
		[
			{
				fieldname: "notes",
				fieldtype: "Text",
				label: __("What did you do?"),
				reqd: 1,
				description: __("The next person to open this job needs to know."),
			},
		],
		(values) => {
			frappe.call({
				method: "mark_resolved",
				doc: frm.doc,
				args: { notes: values.notes },
				freeze: true,
				callback: () => frm.reload_doc(),
			});
		},
		__("Mark resolved"),
		__("Resolve")
	);
}
