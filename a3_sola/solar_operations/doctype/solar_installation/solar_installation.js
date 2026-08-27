// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

const API = "a3_sola.api.stages";
const DOCS = "a3_sola.api.documents";

frappe.ui.form.on("Solar Installation", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		render_stage_chain(frm);
		stage_buttons(frm);
		document_buttons(frm);
		serial_buttons(frm);
		banners(frm);
	},
});

function current_stage_row(frm) {
	return (frm.doc.stages || []).find((r) => ["In Progress", "Blocked"].includes(r.status));
}

function open_stages(frm) {
	return (frm.doc.stages || [])
		.filter((r) => !["Completed", "Skipped"].includes(r.status))
		.map((r) => r.stage_code);
}

function render_stage_chain(frm) {
	frappe.call({
		method: "a3_sola.solar_operations.doctype.solar_installation.solar_installation.get_stage_chain_html",
		args: { installation: frm.doc.name },
		callback(r) {
			if (r.message) frm.get_field("stage_chain").$wrapper.html(r.message);
		},
	});
}

function stage_buttons(frm) {
	const current = current_stage_row(frm);
	const group = __("Stage");

	if (current && current.status === "In Progress") {
		frm.add_custom_button(__("Advance Stage"), () => {
			frappe.prompt(
				[
					{ fieldname: "actual_date", label: __("Completed On"), fieldtype: "Date",
					  default: frappe.datetime.get_today(), reqd: 1 },
					{ fieldname: "external_reference", label: __("External Ref / Approval No"), fieldtype: "Data" },
					{ fieldname: "remarks", label: __("Remarks"), fieldtype: "Small Text" },
				],
				(values) => call(frm, `${API}.advance_stage`, { stage_code: current.stage_code, ...values }),
				__("Complete: {0}", [current.stage_name]),
				__("Advance")
			);
		}, group);

		frm.add_custom_button(__("Block Stage"), () => {
			frappe.prompt(
				[{ fieldname: "blocked_reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 }],
				(values) => call(frm, `${API}.block_stage`, { stage_code: current.stage_code, ...values }),
				__("Block: {0}", [current.stage_name]),
				__("Block")
			);
		}, group);
	}

	if (current && current.status === "Blocked") {
		frm.add_custom_button(__("Unblock"), () => {
			frappe.prompt(
				[{ fieldname: "remarks", label: __("Resolution"), fieldtype: "Small Text", reqd: 1 }],
				(values) => call(frm, `${API}.unblock_stage`, { stage_code: current.stage_code, ...values }),
				__("Unblock: {0}", [current.stage_name]),
				__("Unblock")
			);
		}, group);
	}

	const manager = frappe.user_roles.some((r) =>
		["Solar Operations Manager", "System Manager"].includes(r)
	);
	if (!manager) return;

	frm.add_custom_button(__("Skip Stage"), () => {
		frappe.prompt(
			[
				{ fieldname: "stage_code", label: __("Stage"), fieldtype: "Select",
				  options: open_stages(frm).join("\n"), reqd: 1 },
				{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
			],
			(values) => call(frm, `${API}.skip_stage`, values),
			__("Skip Stage"),
			__("Skip")
		);
	}, group);

	frm.add_custom_button(__("Revert Stage"), () => {
		frappe.prompt(
			[
				{ fieldname: "stage_code", label: __("Revert To"), fieldtype: "Select",
				  options: (frm.doc.stages || []).map((r) => r.stage_code).join("\n"), reqd: 1 },
				{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text", reqd: 1 },
			],
			(values) => call(frm, `${API}.revert_stage`, values),
			__("Revert Stage"),
			__("Revert")
		);
	}, group);
}

function document_buttons(frm) {
	const group = __("Documents");
	const current = current_stage_row(frm);

	frm.add_custom_button(__("Generate Document Pack"), () => {
		frappe.call({
			method: `${DOCS}.generate_document_pack`,
			args: { installation: frm.doc.name, stage_code: current ? current.stage_code : null },
			freeze: true,
			freeze_message: __("Generating documents..."),
			callback(r) {
				show_pack_result(r.message || []);
				frm.reload_doc();
			},
		});
	}, group);

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
}

function show_pack_result(results) {
	const rows = results
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
					<tbody>${rows}</tbody></table>`,
			},
		],
	}).show();
}

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
		frm.dashboard.add_indicator(__("SLA breached · {0}", [frm.doc.blocking_party || ""]), "red");
	}
	if (frm.doc.critical_snag_count > 0) {
		frm.dashboard.add_comment(
			__("{0} critical snag(s) open. PCR is blocked until they are resolved.", [
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

frappe.ui.form.on("Installation Document", {
	verify(frm, cdt, cdn) {
		frappe.call({
			method: "a3_sola.solar_operations.doctype.solar_installation.solar_installation.verify_document",
			args: { installation: frm.doc.name, row_name: cdn },
			callback: () => frm.reload_doc(),
		});
	},
});
