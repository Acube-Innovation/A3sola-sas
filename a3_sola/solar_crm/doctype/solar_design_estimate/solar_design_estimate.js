// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar Design Estimate", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Add Option from Package"), () => add_option(frm), __("Options"));
		}
		frm.add_custom_button(__("Compare Packages"), () => compare_packages(frm), __("Options"));

		// The regulatory position is data, so surface whatever it currently says.
		if (frm.doc.regulation_message) {
			frm.dashboard.add_comment(
				frm.doc.regulation_message,
				frm.doc.connection_type_compliant ? "yellow" : "red",
				true
			);
		}
		if (frm.doc.binding_constraint) {
			frm.dashboard.add_indicator(
				__("Bound by {0}", [frm.doc.binding_constraint]),
				"blue"
			);
		}
	},

	solar_consumer(frm) {
		frm.set_query("site_survey", () => ({
			filters: { solar_consumer: frm.doc.solar_consumer, docstatus: 1 },
		}));
	},
});

function add_option(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Add Priced Option"),
		fields: [
			{
				fieldname: "solar_package",
				label: __("Solar Package"),
				fieldtype: "Link",
				options: "Solar Package",
				reqd: 1,
				get_query: () => ({ filters: { is_active: 1, company: frm.doc.company } }),
			},
			{
				fieldname: "inverter_option",
				label: __("Inverter Option"),
				fieldtype: "Select",
				options: "1\n2",
				default: "1",
				description: __("Packages carry two inverter options side by side, as the client quotes them."),
			},
			{ fieldname: "option_name", label: __("Option Name"), fieldtype: "Data" },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate.add_option_from_package",
				args: { design_estimate: frm.doc.name, ...values },
				freeze: true,
				callback: () => {
					d.hide();
					frm.reload_doc();
				},
			});
		},
	});
	d.show();
}

function compare_packages(frm) {
	frappe.call({
		method: "a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate.compare_packages",
		args: { design_estimate: frm.doc.name },
		freeze: true,
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint(__("No active packages within 2 kW of the recommendation."));
				return;
			}
			const fmt = (v) => format_currency(v, "INR");
			const body = `
				<table class="table table-bordered" style="font-size:12px">
					<thead><tr>
						<th>${__("Package")}</th><th class="text-right">${__("kW")}</th>
						<th class="text-right">${__("Cost")}</th><th class="text-right">${__("Subsidy")}</th>
						<th class="text-right">${__("Net")}</th><th class="text-right">${__("Annual Savings")}</th>
						<th class="text-right">${__("Payback")}</th><th>${__("DCR")}</th>
					</tr></thead>
					<tbody>${rows
						.map(
							(x) => `<tr>
						<td>${frappe.utils.escape_html(x.specification_code || x.package)}</td>
						<td class="text-right">${x.capacity_kw}</td>
						<td class="text-right">${fmt(x.cost)}</td>
						<td class="text-right">${fmt(x.subsidy)}</td>
						<td class="text-right">${fmt(x.net_cost)}</td>
						<td class="text-right">${fmt(x.annual_savings)}</td>
						<td class="text-right">${x.payback_years}</td>
						<td>${x.is_dcr_compliant ? "✓" : ""}</td>
					</tr>`
						)
						.join("")}</tbody>
				</table>`;
			new frappe.ui.Dialog({ title: __("Package Comparison"), size: "extra-large", fields: [{ fieldtype: "HTML", options: body }] }).show();
		},
	});
}
