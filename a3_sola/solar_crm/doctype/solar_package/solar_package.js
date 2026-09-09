// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// The five price selections are chosen from this package's own option tables, so their
// dropdowns are rebuilt from those tables rather than being a fixed list on the doctype.
// A blank first entry is deliberate: a half-filled row must be able to say so.
const PRICE_SOURCES = [
	["module", "modules", (row) => row.module_specification],
	["inverter", "inverters", (row) => row.inverter_specification],
	["dcdb", "system_items", (row) => (row.system_type === "DCDB" ? row.specification : null)],
	["acdb", "system_items", (row) => (row.system_type === "ACDB" ? row.specification : null)],
	[
		"energy_meter",
		"system_items",
		(row) => (row.system_type === "Solar Energy Meter" ? row.specification : null),
	],
];

function refresh_price_choices(frm) {
	const grid = frm.fields_dict.prices && frm.fields_dict.prices.grid;
	if (!grid) return;
	PRICE_SOURCES.forEach(([fieldname, table, pick]) => {
		const seen = [];
		(frm.doc[table] || []).forEach((row) => {
			const value = pick(row);
			if (value && !seen.includes(value)) seen.push(value);
		});
		grid.update_docfield_property(fieldname, "options", [""].concat(seen).join("\n"));
	});
	grid.refresh();
}

frappe.ui.form.on("Solar Package", {
	refresh(frm) {
		refresh_price_choices(frm);
		if (frm.doc.__islocal) return;
		if (!frm.doc.item || !frm.doc.bom) {
			frm.add_custom_button(__("Create Item and BOM"), () => {
				frappe.call({
					method: "a3_sola.solar_crm.doctype.solar_package.solar_package.create_item_and_bom",
					args: { solar_package: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
				});
			});
		}
	},
});

// The default is a choice between rows, not a flag on each. Ticking one has to clear the
// others here, or the user meets a validation error for doing the obvious thing.
function keep_one_default(frm, table, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.is_default) return;
	(frm.doc[table] || []).forEach((other) => {
		if (other.name !== cdn && other.is_default) {
			frappe.model.set_value(other.doctype, other.name, "is_default", 0);
		}
	});
}

// The first option of its kind is the default; there is nothing else it could be.
function default_the_first(frm, table, cdt, cdn) {
	if ((frm.doc[table] || []).length === 1) {
		frappe.model.set_value(cdt, cdn, "is_default", 1);
	}
}

frappe.ui.form.on("Solar Package Module", {
	is_default: (frm, cdt, cdn) => keep_one_default(frm, "modules", cdt, cdn),
	modules_add: (frm, cdt, cdn) => default_the_first(frm, "modules", cdt, cdn),
	module_specification: (frm) => refresh_price_choices(frm),
	modules_remove: (frm) => refresh_price_choices(frm),
});

// Balance of system differs: the default is per type, so ticking a DCDB clears only the
// other DCDB rows. An ACDB alongside it is not a competing option.
frappe.ui.form.on("Solar Package System Item", {
	is_default(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.is_default || !row.system_type) return;
		(frm.doc.system_items || []).forEach((other) => {
			if (other.name !== cdn && other.system_type === row.system_type && other.is_default) {
				frappe.model.set_value(other.doctype, other.name, "is_default", 0);
			}
		});
	},

	system_type(frm, cdt, cdn) {
		// A row that has just been given its type is the only one of that type until
		// another arrives, so it is the one quoted.
		const row = locals[cdt][cdn];
		refresh_price_choices(frm);
		if (!row.system_type || row.is_default) return;
		const others = (frm.doc.system_items || []).filter(
			(other) => other.name !== cdn && other.system_type === row.system_type
		);
		if (!others.length) frappe.model.set_value(cdt, cdn, "is_default", 1);
	},

	specification: (frm) => refresh_price_choices(frm),
	system_items_remove: (frm) => refresh_price_choices(frm),
});

frappe.ui.form.on("Solar Package Price", {
	// A new price row starts on the configuration the package is offered by default, which
	// is the row somebody is most likely to be pricing first.
	prices_add(frm, cdt, cdn) {
		const of_type = (type) =>
			(frm.doc.system_items || []).filter((r) => r.system_type === type);
		const chosen = (rows, field) => {
			const row = rows.find((r) => r.is_default) || rows[0];
			return row ? row[field] : null;
		};
		const defaults = {
			module: chosen(frm.doc.modules || [], "module_specification"),
			inverter: chosen(frm.doc.inverters || [], "inverter_specification"),
			dcdb: chosen(of_type("DCDB"), "specification"),
			acdb: chosen(of_type("ACDB"), "specification"),
			energy_meter: chosen(of_type("Solar Energy Meter"), "specification"),
		};
		Object.entries(defaults).forEach(([field, value]) => {
			if (value) frappe.model.set_value(cdt, cdn, field, value);
		});
	},
});

frappe.ui.form.on("Solar Package Inverter", {
	is_default: (frm, cdt, cdn) => keep_one_default(frm, "inverters", cdt, cdn),
	inverters_add: (frm, cdt, cdn) => default_the_first(frm, "inverters", cdt, cdn),

	inverter_specification: (frm) => refresh_price_choices(frm),
	inverters_remove: (frm) => refresh_price_choices(frm),
});
