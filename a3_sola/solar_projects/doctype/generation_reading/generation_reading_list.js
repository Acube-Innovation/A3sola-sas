// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.listview_settings["Generation Reading"] = {
	onload(listview) {
		// Most clients export from an inverter portal rather than key readings in.
		listview.page.add_inner_button(__("Import from Portal Export"), () => import_readings());
	},

	get_indicator(doc) {
		if (!doc.performance_ratio_percent) {
			return [__("Recorded"), "gray", "performance_ratio_percent,=,0"];
		}
		if (doc.performance_ratio_percent < 75) {
			return [__("Below floor"), "red", "performance_ratio_percent,<,75"];
		}
		if (doc.performance_ratio_percent < 80) {
			return [__("Underperforming"), "orange", "performance_ratio_percent,<,80"];
		}
		return [__("Healthy"), "green", "performance_ratio_percent,>=,80"];
	},
};

function import_readings() {
	const dialog = new frappe.ui.Dialog({
		title: __("Import Generation Readings"),
		fields: [
			{
				fieldname: "solar_installation",
				fieldtype: "Link",
				options: "Solar Installation",
				label: __("Installation"),
				reqd: 1,
			},
			{
				fieldname: "reading_source",
				fieldtype: "Select",
				label: __("Source"),
				options: "Inverter Portal\nNet Meter\nInverter Display\nCustomer Reported",
				default: "Inverter Portal",
			},
			{
				fieldname: "csv_text",
				fieldtype: "Code",
				label: __("Paste the CSV"),
				reqd: 1,
				description: __(
					"A header row naming reading_date, plus at least one of inverter_lifetime_kwh, import_reading or export_reading. Dates already recorded are skipped."
				),
			},
		],
		primary_action_label: __("Import"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.api.sla.import_readings",
				args: values,
				freeze: true,
				freeze_message: __("Reading the export…"),
			}).then((response) => {
				const result = response.message || {};
				dialog.hide();
				frappe.msgprint({
					title: __("Import complete"),
					message: __("{0} recorded, {1} already on file, {2} could not be read.", [
						(result.created || []).length,
						(result.skipped || []).length,
						(result.failed || []).length,
					]),
					indicator: (result.failed || []).length ? "orange" : "green",
				});
				cur_list.refresh();
			});
		},
	});
	dialog.show();
}
