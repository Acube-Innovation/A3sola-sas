// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Solar OM Contract", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) {
			return;
		}

		if (frm.doc.renewed_to) {
			frm.dashboard.set_headline(
				__("Renewed as {0}.", [
					`<a href="/app/solar-om-contract/${frm.doc.renewed_to}">${frm.doc.renewed_to}</a>`,
				])
			);
		} else if (["Active", "Expiring Soon", "Expired"].includes(frm.doc.status)) {
			frm.add_custom_button(__("Renew Contract"), () => renew(frm));
		}

		if (frm.doc.performance_obligation_status === "Breached") {
			frm.dashboard.add_indicator(__("Performance obligation breached"), "red");
		}

		render_performance_chart(frm);
	},
});

function render_performance_chart(frm) {
	// Expected against actual, by month, with the performance ratio over the top. The
	// question this answers is "is it getting worse", which a table of readings does not.
	frappe.call({
		method: "a3_sola.api.sla.performance_series",
		args: { om_contract: frm.doc.name },
	}).then((response) => {
		const series = response.message;
		if (!series || !series.labels.length) {
			return;
		}
		frm.dashboard.render_graph({
			title: __("Generation against design expectation"),
			data: {
				labels: series.labels,
				datasets: [
					{ name: __("Expected kWh"), values: series.expected, chartType: "bar" },
					{ name: __("Actual kWh"), values: series.actual, chartType: "bar" },
				],
				yMarkers: [
					{
						label: __("Contractual floor"),
						value: frm.doc.contractual_performance_ratio_percent,
						options: { labelPos: "left" },
					},
				],
			},
			type: "axis-mixed",
			colors: ["#b8c2cc", "#29cd42"],
		});
	});
}

function renew(frm) {
	// The free scheme-mandated term is ending; what follows is a paid AMC, so the value
	// is the one thing the renewal cannot infer.
	const dialog = new frappe.ui.Dialog({
		title: __("Renew Contract"),
		fields: [
			{
				fieldname: "years",
				fieldtype: "Int",
				label: __("Term (years)"),
				default: frm.doc.duration_years || 1,
				reqd: 1,
			},
			{
				fieldname: "contract_value",
				fieldtype: "Currency",
				label: __("Annual Contract Value"),
				description: __("Coverage and service levels carry across unchanged."),
			},
		],
		primary_action_label: __("Renew"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.api.om.renew_contract",
				args: {
					contract: frm.doc.name,
					years: values.years,
					contract_value: values.contract_value,
				},
				freeze: true,
			}).then((response) => {
				dialog.hide();
				if (response.message) {
					frappe.set_route("Form", "Solar OM Contract", response.message);
				}
			});
		},
	});
	dialog.show();
}
