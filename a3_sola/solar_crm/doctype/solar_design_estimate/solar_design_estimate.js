// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// The Component Make type each balance-of-system item's make is drawn from; mirrors
// MAKE_TYPE in balance_of_system_package.py.
const BOS_MAKE_TYPE = {
	DCDB: "DCDB",
	ACDB: "ACDB",
	"DC Cable": "Cable",
	"AC Cable": "Cable",
	Earthing: "Earthing",
	"Lightning Protection": "Lightning Protection",
	"Solar Energy Meter": "Energy Meter",
};

frappe.ui.form.on("Solar Design Estimate", {
	refresh(frm) {
		frm.add_custom_button(__("Compare Packages"), () => compare_packages(frm), __("Options"));
		if (frm.doc.docstatus === 0 && !frm.doc.solar_package) {
			frm.add_custom_button(__("Create Package"), () => create_package(frm), __("Options"));
		}

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

	setup(frm) {
		// Each expense table offers only the Items of its own group (seeded by install.py).
		[
			["kseb_expenses", "particulars", "KSEB Expenses"],
			["mounting_expenses", "item", "Mounting Structure Expenses"],
			["installation_expenses", "item", "Installation Expenses"],
		].forEach(([table, field, group]) => {
			frm.set_query(field, table, () => ({ filters: { item_group: group, disabled: 0 } }));
		});
		frm.set_query("panel_variant", "panels", () => ({
			filters: { component_type: "Module", is_active: 1, company: frm.doc.company },
		}));
		// Variant first: only makes of the chosen variant are offered.
		frm.set_query("panel_make", "panels", (doc, cdt, cdn) => ({
			filters: {
				component_type: "Module",
				is_active: 1,
				company: frm.doc.company,
				technology: locals[cdt][cdn].panel_variant || "",
			},
		}));
		frm.set_query("inverter_type", "inverters", () => ({
			filters: { component_type: "Inverter", is_active: 1, company: frm.doc.company },
		}));
		frm.set_query("inverter_make", "inverters", (doc, cdt, cdn) => ({
			filters: {
				component_type: "Inverter",
				is_active: 1,
				company: frm.doc.company,
				technology: locals[cdt][cdn].inverter_type || "",
			},
		}));
		frm.set_query("make", "bos_items", (doc, cdt, cdn) => ({
			filters: {
				component_type: BOS_MAKE_TYPE[locals[cdt][cdn].item] || "",
				is_active: 1,
				company: frm.doc.company,
			},
		}));
		frm.set_query("battery_variant", "batteries", () => ({
			filters: { component_type: "Battery", is_active: 1, company: frm.doc.company },
		}));
		frm.set_query("battery_make", "batteries", (doc, cdt, cdn) => ({
			filters: {
				component_type: "Battery",
				is_active: 1,
				company: frm.doc.company,
				technology: locals[cdt][cdn].battery_variant || "",
			},
		}));
	},

	override_capacity_kw(frm) {
		// The server settles the final size on save; until then panels follow the override.
		(frm.doc.panels || []).forEach((row) => set_panel_count(frm, row));
	},

	solar_consumer(frm) {
		frm.set_query("site_survey", () => ({
			filters: { solar_consumer: frm.doc.solar_consumer, docstatus: 1 },
		}));
	},
});

frappe.ui.form.on("Design Estimate Panel", {
	panel_capacity_wp(frm, cdt, cdn) {
		set_panel_count(frm, locals[cdt][cdn]);
	},

	panel_variant(frm, cdt, cdn) {
		// A make chosen under another variant no longer applies.
		const row = locals[cdt][cdn];
		if (row.panel_make) frappe.model.set_value(cdt, cdn, "panel_make", null);
	},

	panel_make(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.panel_make) return;
		frappe.db.get_value("Component Make", row.panel_make, "is_dcr").then((r) => {
			frappe.model.set_value(cdt, cdn, "panel_type", r.message.is_dcr ? "DCR" : "Non-DCR");
		});
	},

	panels_add(frm, cdt, cdn) {
		set_panel_count(frm, locals[cdt][cdn]);
	},

	panels_remove(frm) {
		set_inverter_counts(frm);
	},
});

frappe.ui.form.on("Design Estimate Inverter", {
	inverter_type(frm, cdt, cdn) {
		// A make chosen under another type no longer applies.
		if (locals[cdt][cdn].inverter_make) frappe.model.set_value(cdt, cdn, "inverter_make", null);
	},

	inverter_capacity_kw(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		set_inverter_count(frm, row);
		if (!row.inverter_phase) {
			// Same default as the controller; the limit itself is checked on save.
			const three = frm.doc.connection_type === "Three Phase" && flt(row.inverter_capacity_kw) > 5;
			frappe.model.set_value(cdt, cdn, "inverter_phase", three ? "Three Phase" : "Single Phase");
		}
	},
});

// Mirrors compute_panels() in the controller: proposed size / panel Wp, rounded up.
function set_panel_count(frm, row) {
	const kw = flt(frm.doc.override_capacity_kw) || flt(frm.doc.final_capacity_kw);
	const wp = flt(row.panel_capacity_wp);
	const nos = kw && wp ? Math.ceil(flt((kw * 1000) / wp, 6)) : 0;
	frappe.model.set_value(row.doctype, row.name, "nos", nos);
	frappe.model.set_value(row.doctype, row.name, "total_capacity_kwp", flt((nos * wp) / 1000, 3));
	set_inverter_counts(frm);
}

frappe.ui.form.on("Design Estimate Battery", {
	battery_variant(frm, cdt, cdn) {
		// A make chosen under another variant no longer applies.
		if (locals[cdt][cdn].battery_make) frappe.model.set_value(cdt, cdn, "battery_make", null);
	},
	battery_voltage: set_battery_energy,
	battery_capacity_ah: set_battery_energy,
	nos: set_battery_energy,
	batteries_add(frm, cdt, cdn) {
		if (frm.doc.connection_type) frappe.model.set_value(cdt, cdn, "battery_phase", frm.doc.connection_type);
	},
});

// Mirrors compute_batteries() in the controller.
function set_battery_energy(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const kwh = (flt(row.battery_voltage) * flt(row.battery_capacity_ah) * cint(row.nos)) / 1000;
	frappe.model.set_value(cdt, cdn, "total_energy_kwh", flt(kwh, 3));
}

// Mirrors compute_inverters() in the controller: total panel kWp / inverter kW, rounded up.
function set_inverter_count(frm, row) {
	const panel_kwp = (frm.doc.panels || []).reduce((sum, p) => sum + flt(p.total_capacity_kwp), 0);
	const kw = flt(row.inverter_capacity_kw);
	const nos = panel_kwp && kw ? Math.ceil(flt(panel_kwp / kw, 6)) : 0;
	frappe.model.set_value(row.doctype, row.name, "nos", nos);
	frappe.model.set_value(row.doctype, row.name, "total_capacity_kw", flt(nos * kw, 3));
}

function set_inverter_counts(frm) {
	(frm.doc.inverters || []).forEach((row) => set_inverter_count(frm, row));
}

// Opens a new Solar Package filled from the System & Options tab. Saving it comes back
// here with the package selected (see after_save in solar_package.js).
function create_package(frm) {
	frappe.call({
		method: "a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate.package_values_from_estimate",
		args: { doc: frm.doc },
		freeze: true,
		callback(r) {
			const values = r.message || {};
			frappe.model.with_doctype("Solar Package", () => {
				const pkg = frappe.model.get_new_doc("Solar Package");
				Object.entries(values).forEach(([field, value]) => {
					if (!Array.isArray(value)) {
						pkg[field] = value;
						return;
					}
					value.forEach((row) => Object.assign(frappe.model.add_child(pkg, field), row));
				});
				frappe.a3s_package_for_estimate = { estimate: frm.doc.name, package: pkg.name };
				frappe.set_route("Form", "Solar Package", pkg.name);
			});
		},
	});
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
