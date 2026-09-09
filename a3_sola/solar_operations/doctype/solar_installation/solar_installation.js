// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const TASKS = "a3_sola.api.tasks";
const DOCS = "a3_sola.api.documents";
const MANAGER_ROLES = ["Solar Operations Manager", "System Manager"];

frappe.ui.form.on("Solar Installation", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		render_task_grid(frm);
		task_button(frm);
		task_actions(frm);
		document_buttons(frm);
		serial_buttons(frm);
		banners(frm);
	},
});

function is_manager() {
	return frappe.user_roles.some((r) => MANAGER_ROLES.includes(r));
}

function rows(frm, statuses) {
	return (frm.doc.stages || []).filter((r) => !statuses || statuses.includes(r.status));
}

function task_label(r) {
	const who = r.assigned_to ? ` · ${r.assigned_to}` : "";
	return `${r.stage_code} · ${r.stage_name} — ${r.status}${who}`;
}

function task_options(frm, statuses) {
	return rows(frm, statuses).map((r) => ({ label: task_label(r), value: r.stage_code }));
}

function render_task_grid(frm) {
	frappe.call({
		method: "a3_sola.solar_operations.doctype.solar_installation.solar_installation.get_task_grid_html",
		args: { installation: frm.doc.name },
		callback(r) {
			if (r.message) frm.get_field("stage_chain").$wrapper.html(r.message);
		},
	});
}

// ------------------------------------------------------------------ the Task button
// Pick a task; land in the document that carries it out - the existing one if there is
// one, a new one prefilled otherwise. This is how a task is worked, in any order.
function task_button(frm) {
	frm.add_custom_button(__("Task"), () => {
		const open = task_options(frm, ["Pending", "In Progress", "Blocked"]);
		const done = task_options(frm, ["Completed", "Skipped"]);
		const d = new frappe.ui.Dialog({
			title: __("Which task?"),
			fields: [
				{
					fieldname: "task_code",
					fieldtype: "Autocomplete",
					label: __("Task"),
					reqd: 1,
					options: [...open, ...done],
					description: __("Open tasks first, then completed and skipped ones."),
				},
			],
			primary_action_label: __("Open"),
			primary_action(values) {
				d.hide();
				open_task(frm, values.task_code);
			},
		});
		d.show();
	}).addClass("btn-primary");
}

function open_task(frm, task_code) {
	frappe.call({
		method: `${TASKS}.open_task`,
		args: { installation: frm.doc.name, task_code },
		freeze: true,
		callback(r) {
			const target = r.message || {};
			if (target.name) {
				frappe.set_route("Form", target.doctype, target.name);
			} else if (target.route_options) {
				frappe.new_doc(target.doctype, target.route_options);
			} else {
				frappe.msgprint(__("There is nothing to open for {0}: this job has no {1}.", [
					task_code,
					__(target.doctype),
				]));
			}
		},
	});
}

// ------------------------------------------------------------------ the other actions
function task_actions(frm) {
	const group = __("Task Actions");

	frm.add_custom_button(__("Assign"), () => {
		frappe.prompt(
			[
				{ fieldname: "task_code", label: __("Task"), fieldtype: "Select",
				  options: task_options(frm, ["Pending", "In Progress", "Blocked"]), reqd: 1 },
				{ fieldname: "user", label: __("Assign To"), fieldtype: "Link", options: "User", reqd: 1 },
				{ fieldname: "due_date", label: __("Due"), fieldtype: "Date" },
			],
			(values) => call(frm, `${TASKS}.assign_task`, values),
			__("Assign Task"),
			__("Assign")
		);
	}, group);

	frm.add_custom_button(__("Block"), () => {
		frappe.prompt(
			[
				{ fieldname: "task_code", label: __("Task"), fieldtype: "Select",
				  options: task_options(frm, ["Pending", "In Progress"]), reqd: 1 },
				{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
			],
			(values) => call(frm, `${TASKS}.block_task`, values),
			__("Block Task"),
			__("Block")
		);
	}, group);

	if (rows(frm, ["Blocked"]).length) {
		frm.add_custom_button(__("Unblock"), () => {
			frappe.prompt(
				[
					{ fieldname: "task_code", label: __("Task"), fieldtype: "Select",
					  options: task_options(frm, ["Blocked"]), reqd: 1 },
					{ fieldname: "remarks", label: __("Resolution"), fieldtype: "Small Text", reqd: 1 },
				],
				(values) => call(frm, `${TASKS}.unblock_task`, values),
				__("Unblock Task"),
				__("Unblock")
			);
		}, group);
	}

	frm.add_custom_button(__("Mark Done Without Document"), () => {
		frappe.prompt(
			[
				{ fieldname: "task_code", label: __("Task"), fieldtype: "Select",
				  options: task_options(frm, ["Pending", "In Progress", "Blocked"]), reqd: 1 },
				{ fieldname: "actual_date", label: __("Completed On"), fieldtype: "Date",
				  default: frappe.datetime.get_today(), reqd: 1 },
				{ fieldname: "external_reference", label: __("Reference"), fieldtype: "Data" },
				{ fieldname: "cost", label: __("Cost"), fieldtype: "Currency" },
				{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
			],
			(values) => call(frm, `${TASKS}.complete_task`, values),
			__("Complete Task"),
			__("Complete")
		);
	}, group);

	frm.add_custom_button(__("Skip"), () => {
		frappe.prompt(
			[
				{ fieldname: "task_code", label: __("Task"), fieldtype: "Select",
				  options: task_options(frm, ["Pending", "In Progress", "Blocked"]), reqd: 1 },
				{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
			],
			(values) => call(frm, `${TASKS}.skip_task`, values),
			__("Skip Task"),
			__("Skip")
		);
	}, group);

	if (rows(frm, ["Skipped"]).length) {
		frm.add_custom_button(__("Unskip"), () => {
			frappe.prompt(
				[
					{ fieldname: "task_code", label: __("Task"), fieldtype: "Select",
					  options: task_options(frm, ["Skipped"]), reqd: 1 },
					{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
				],
				(values) => call(frm, `${TASKS}.unskip_task`, values),
				__("Put Task Back"),
				__("Unskip")
			);
		}, group);
	}

	if (is_manager() && rows(frm, ["Completed", "Skipped"]).length) {
		frm.add_custom_button(__("Reopen"), () => {
			frappe.prompt(
				[
					{ fieldname: "task_code", label: __("Task"), fieldtype: "Select",
					  options: task_options(frm, ["Completed", "Skipped"]), reqd: 1 },
					{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
				],
				(values) => call(frm, `${TASKS}.reopen_task`, values),
				__("Reopen Task"),
				__("Reopen")
			);
		}, group);
	}
}

// ------------------------------------------------------------------ documents
function document_buttons(frm) {
	const group = __("Documents");

	frm.add_custom_button(__("Generate All Documents"), () => {
		frappe.call({
			method: `${DOCS}.generate_document_pack`,
			args: { installation: frm.doc.name },
			freeze: true,
			freeze_message: __("Generating the full pack..."),
			callback(r) {
				show_pack_result(r.message || []);
				frm.reload_doc();
			},
		});
	}, group);

	if (frm.doc.stale_document_count > 0) {
		frm.add_custom_button(__("Regenerate Stale"), () => {
			frappe.confirm(
				__("Some of these documents may already have been issued. Regenerating replaces the file — the issued copy stays with whoever received it. Continue?"),
				() => {
					const stale = (frm.doc.generated_documents || []).filter((r) => r.is_stale);
					frappe.call({
						method: `${DOCS}.generate_document_pack`,
						args: { installation: frm.doc.name },
						freeze: true,
						callback: () => frm.reload_doc(),
					});
					frappe.show_alert({ message: __("Regenerating {0} documents", [stale.length]), indicator: "blue" });
				}
			);
		}, group);
	}

	// The register's Verified box is a QC stamp. The button behind it makes that a recorded act.
	frm.fields_dict.documents.grid.add_custom_button(__("Verify Selected"), () => {
		const selected = frm.fields_dict.documents.grid.get_selected_children();
		if (!selected.length) {
			frappe.msgprint(__("Select the register rows to verify."));
			return;
		}
		Promise.all(
			selected.map((row) =>
				frappe.call({
					method: "a3_sola.solar_operations.doctype.solar_installation.solar_installation.verify_document",
					args: { installation: frm.doc.name, row_name: row.name },
				})
			)
		).then(() => frm.reload_doc());
	});
}

function show_pack_result(results) {
	const lines = results
		.map(
			(r) =>
				`<tr><td>${frappe.utils.escape_html(r.template)}</td>
				 <td>${r.status === "generated" ? "✓" : "✗"}</td>
				 <td>${frappe.utils.escape_html(r.error || "")}</td></tr>`
		)
		.join("");
	new frappe.ui.Dialog({
		title: __("Document Pack"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<table class="table table-bordered" style="font-size:12px">
					<thead><tr><th>${__("Document")}</th><th>${__("Status")}</th><th>${__("Error")}</th></tr></thead>
					<tbody>${lines}</tbody></table>`,
			},
		],
	}).show();
}

// ------------------------------------------------------------------ serials
function serial_buttons(frm) {
	const group = __("Serials");
	frm.add_custom_button(__("Pull from Delivery Notes"), () => {
		frappe.call({
			method: "a3_sola.api.serials.pull_serials_from_delivery_note",
			args: { installation: frm.doc.name },
			freeze: true,
			callback(r) {
				frappe.show_alert({
					message: __("{0} serials imported", [(r.message || {}).added || 0]),
					indicator: "green",
				});
				frm.reload_doc();
			},
		});
	}, group);

	frm.add_custom_button(__("Export Manifest"), () => {
		window.open(
			`/api/method/a3_sola.api.serials.export_serial_manifest?installation=${encodeURIComponent(frm.doc.name)}`
		);
	}, group);
}

// ------------------------------------------------------------------ banners
function banners(frm) {
	if (frm.doc.stale_document_count > 0) {
		frm.dashboard.add_comment(
			__("{0} generated document(s) no longer match this record. Regenerate before issuing them.", [
				frm.doc.stale_document_count,
			]),
			"orange",
			true
		);
	}
	if (frm.doc.is_sla_breached) {
		frm.dashboard.add_indicator(__("Overdue task · {0}", [frm.doc.blocking_party || ""]), "red");
	}
	if (frm.doc.form2_due_on && !rows(frm).some((r) => r.stage_code === "KFORMS" && ["Completed", "Skipped"].includes(r.status))) {
		frm.dashboard.add_indicator(
			__("Form 2 due {0}", [frappe.datetime.str_to_user(frm.doc.form2_due_on)]),
			frappe.datetime.get_diff(frm.doc.form2_due_on, frappe.datetime.get_today()) < 7 ? "red" : "blue"
		);
	}
	if (frm.doc.critical_snag_count > 0) {
		frm.dashboard.add_comment(
			__("{0} critical snag(s) open. The subsidy claim is blocked until they are resolved.", [
				frm.doc.critical_snag_count,
			]),
			"red",
			true
		);
	}
	if (frm.doc.modules_expected && !frm.doc.serial_capture_complete) {
		frm.dashboard.add_indicator(
			__("Serials {0}/{1}", [frm.doc.modules_captured || 0, frm.doc.modules_expected]),
			"orange"
		);
	}
}

function call(frm, method, args) {
	frappe.call({
		method,
		args: { installation: frm.doc.name, ...args },
		freeze: true,
		callback: () => frm.reload_doc(),
	});
}
