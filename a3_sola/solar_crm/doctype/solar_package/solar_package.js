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

// Each specification row is an Item of its own category: the dropdown offers only that item
// group's items, and choosing one writes its description into the row's specification.
const ITEM_ROWS = [
	["modules", "module_item", "module_specification", () => "Modules"],
	["inverters", "inverter_item", "inverter_specification", () => "Inverters"],
	["batteries", "battery_item", "specification", () => "Batteries"],
	["system_items", "item", "specification", (row) => system_item_group(row.system_type)],
	["optional_add_ons", "item_code", "item", () => "Optional Add-ons"],
];

function system_item_group(system_type) {
	return { "Solar Energy Meter": "Meters", "Mounting Structure": "Mounting Structures", Battery: "Batteries" }[system_type]
		|| "Cables and BOS";
}

function fill_from_item(frm, cdt, cdn, item_field, text_field) {
	const item = locals[cdt][cdn][item_field];
	if (!item) return;
	frappe.db.get_value("Item", item, ["item_name", "description"]).then(({ message }) => {
		const text = $("<div>").html((message && message.description) || "").text().trim() || (message && message.item_name);
		if (text) frappe.model.set_value(cdt, cdn, text_field, text);
	});
}

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
	payment_terms(frm) {
		show_payment_terms(frm);
	},
	financed_payment_terms(frm) {
		show_payment_terms(frm);
	},
	setup(frm) {
		["payment_terms", "financed_payment_terms"].forEach((field) =>
			frm.set_query(field, () => ({ filters: { company: frm.doc.company, is_active: 1 } }))
		);
		// Each expense table offers only the Items of its own group (seeded by install.py).
		[
			["kseb_expenses", "particulars", "KSEB Expenses"],
			["mounting_expenses", "item", "Mounting Structure Expenses"],
			["installation_expenses", "item", "Installation Expenses"],
		].forEach(([table, field, group]) => {
			frm.set_query(field, table, () => ({ filters: { item_group: group, disabled: 0 } }));
		});
		ITEM_ROWS.forEach(([table, field, , group]) => {
			frm.set_query(field, table, (doc, cdt, cdn) => ({
				filters: { item_group: ["descendants of (inclusive)", group(locals[cdt][cdn])], disabled: 0 },
			}));
		});
		frm.set_query("roof_type", () => ({ filters: { company: frm.doc.company } }));
		// The row's own make and phase narrow the models, so every kit of them is offered
		// (Hoymiles Single Phase: HM-1000 1 kW to 6 kW), smallest first, by inverter_model.search.
		frm.set_query("inverter_model", "inverters", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			const filters = { is_active: 1 };
			if (row.inverter_make) filters.inverter_make = row.inverter_make;
			if (row.inverter_phase) filters.inverter_phase = row.inverter_phase;
			return { query: "a3_sola.solar_crm.doctype.inverter_model.inverter_model.search", filters };
		});
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

	before_save(frm) {
		// Opened from an estimate's Create Package: remember it is this save that answers it.
		const pending = frappe.a3s_package_for_estimate;
		if (pending && pending.package === frm.doc.name) pending.saving = true;
	},

	after_save(frm) {
		const pending = frappe.a3s_package_for_estimate;
		if (!(pending && pending.saving)) return;
		delete frappe.a3s_package_for_estimate;
		frappe.set_route("Form", "Solar Design Estimate", pending.estimate).then(() => {
			frappe.model.set_value("Solar Design Estimate", pending.estimate, "solar_package", frm.doc.name);
		});
	},

	refresh(frm) {
		// The payment terms' milestones, shown under the two choices.
		show_payment_terms(frm);
		refresh_price_choices(frm);
		if (frm.doc.__islocal) return;
		// The package is a finished good: its name and code are its Item, and its BOM is made
		// by hand from that Item.
		if (!frm.doc.item) {
			frm.add_custom_button(__("Create Item"), () => {
				frappe.call({
					method: "a3_sola.solar_crm.doctype.solar_package.solar_package.create_item_and_bom",
					args: { solar_package: frm.doc.name },
					freeze: true,
					callback: () => frm.reload_doc(),
				});
			});
		} else {
			// The BOM is the package: its Item the finished good, its quoted panel, inverter,
			// batteries and balance of system the raw materials (api/package_items).
			const bom_call = (method, done) => {
				if (frm.is_dirty()) {
					frappe.msgprint(__("Save the package first."));
					return;
				}
				frappe.call({ method: `a3_sola.api.package_items.${method}`, args: { solar_package: frm.doc.name },
					freeze: true, freeze_message: __("Making the BOM…") })
					.then(({ message }) => { done(message); frm.reload_doc(); });
			};
			if (!frm.doc.bom) {
				frm.add_custom_button(__("Create BOM"), () => bom_call("create_bom", (r) =>
					frappe.show_alert({ message: __("BOM {0} created with {1} raw materials.", [r.bom, r.lines]), indicator: "green" })));
			} else {
				frm.add_custom_button(__("Update BOM"), () => bom_call("update_bom", (r) => {
					if (r.unchanged) {
						frappe.show_alert({ message: __("BOM {0} already matches the package.", [r.bom]), indicator: "blue" });
					} else if (r.previous) {
						frappe.msgprint({ title: __("BOM Updated"), indicator: "green", message:
							__("{0} replaces {1}, which is now inactive:", [r.bom, r.previous]) +
							"<ul>" + r.changes.map((c) => `<li>${frappe.utils.escape_html(c)}</li>`).join("") + "</ul>" });
					} else {
						frappe.show_alert({ message: __("BOM {0} created.", [r.bom]), indicator: "green" });
					}
				}));
				frm.add_custom_button(__("View BOM"), () => frappe.set_route("Form", "BOM", frm.doc.bom));
			}
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
	module_item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "module_item", "module_specification"),
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

	item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "item", "specification"),
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

	inverter_item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "inverter_item", "inverter_specification"),
	inverter_specification: (frm) => refresh_price_choices(frm),
	inverters_remove: (frm) => refresh_price_choices(frm),
});

frappe.ui.form.on("Design Estimate Battery", {
	battery_item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "battery_item", "specification"),
});

frappe.ui.form.on("Solar Package Add-on", {
	item_code: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "item_code", "item"),
});

function show_payment_terms(frm) {
	const field = frm.get_field("payment_terms_preview");
	if (!field) return;
	const names = [frm.doc.payment_terms, frm.doc.financed_payment_terms].filter((n, i, all) => n && all.indexOf(n) === i);
	if (!names.length) {
		field.$wrapper.html(`<p class="text-muted small">${__("Choose the payment terms to see their milestones.")}</p>`);
		return;
	}
	Promise.all(names.map((name) => frappe.db.get_doc("Billing Milestone Template", name))).then((docs) => {
		field.$wrapper.html(docs.map((doc) => `
			<p class="small" style="margin:8px 0 4px"><b>${frappe.utils.escape_html(doc.template_name || doc.name)}</b></p>
			<table class="table table-bordered table-condensed small" style="margin-bottom:8px">
				<thead><tr><th>${__("Milestone")}</th><th>${__("When")}</th><th class="text-right">%</th></tr></thead>
				<tbody>${(doc.milestones || []).map((m) => `<tr><td>${frappe.utils.escape_html(m.milestone_name)}${m.is_advance ? ` <span class="indicator-pill orange">${__("Advance")}</span>` : ""}</td>
					<td>${frappe.utils.escape_html(m.trigger_type)}${m.trigger_stage_code ? " · " + frappe.utils.escape_html(m.trigger_stage_code) : ""}</td>
					<td class="text-right">${flt(m.percentage)}%</td></tr>`).join("")}</tbody>
			</table>`).join(""));
	});
}
