// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

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

// An inverter option may be built on one of the package's other panels (Built with Panel):
// its dropdown is the package's own panels, rebuilt as they change. Blank is the default panel.
function refresh_panel_choices(frm) {
	const grid = frm.fields_dict.inverters && frm.fields_dict.inverters.grid;
	if (!grid) return;
	const panels = [...new Set((frm.doc.modules || []).map((r) => r.module_specification).filter(Boolean))];
	grid.update_docfield_property("panel_specification", "options", [""].concat(panels).join("\n"));
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
		refresh_panel_choices(frm);
		setup_bom_tables(frm);
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
	module_specification: (frm) => refresh_panel_choices(frm),
	modules_remove: (frm) => refresh_panel_choices(frm),
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
		if (!row.system_type || row.is_default) return;
		const others = (frm.doc.system_items || []).filter(
			(other) => other.name !== cdn && other.system_type === row.system_type
		);
		if (!others.length) frappe.model.set_value(cdt, cdn, "is_default", 1);
	},

	item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "item", "specification"),
});

frappe.ui.form.on("Solar Package Inverter", {
	is_default: (frm, cdt, cdn) => keep_one_default(frm, "inverters", cdt, cdn),
	inverters_add: (frm, cdt, cdn) => default_the_first(frm, "inverters", cdt, cdn),

	inverter_item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "inverter_item", "inverter_specification"),
});

// The Material BOM (Inverter tab), the Structure BOMs (Mounting tab) and the Expenses (Cost tab)
// come from Excel as often as they are typed (api/package_bom_tables): the sheet is read on the
// server, which finds or makes each Item, and its rows replace the table here, to be saved with
// the package.
const BOM_TABLES_API = "a3_sola.api.package_bom_tables";
const BOM_TABLES = ["material_bom", "structure_boms", "expenses"];

function setup_bom_tables(frm) {
	BOM_TABLES.forEach((table) => {
		const grid = frm.fields_dict[table] && frm.fields_dict[table].grid;
		if (!grid) return;
		grid.add_custom_button(__("Download Excel"), () =>
			open_url_post(`/api/method/${BOM_TABLES_API}.download_sheet`, {
				table,
				rows: JSON.stringify(frm.doc[table] || []),
				package: frm.doc.__islocal ? "" : frm.doc.name,
			}));
		grid.add_custom_button(__("Upload Excel"), () => {
			const had = (frm.doc[table] || []).length;
			if (had) {
				frappe.confirm(__("The sheet's rows replace the {0} rows of the {1}. Go on?", [had, __(grid.df.label)]),
					() => upload_bom_table(frm, table));
			} else {
				upload_bom_table(frm, table);
			}
		});
	});
	show_roof_names(frm);
}

function upload_bom_table(frm, table) {
	new frappe.ui.FileUploader({
		as_dataurl: true,
		allow_multiple: false,
		restrictions: { allowed_file_types: [".xlsx", ".csv"] },
		on_success(file) {
			frappe.call({
				method: `${BOM_TABLES_API}.read_sheet`,
				args: {
					content: file.dataurl,
					filename: file.name,
					table,
					company: frm.doc.company,
					inverters: (frm.doc.inverters || []).map((r) => ({
						inverter_item: r.inverter_item,
						inverter_specification: r.inverter_specification,
					})),
				},
				freeze: true,
				freeze_message: __("Reading the sheet…"),
			}).then(({ message }) => {
				frm.clear_table(table);
				message.rows.forEach((row) => frm.add_child(table, row));
				frm.refresh_field(table);
				if (table === "expenses") total_expenses(frm);
				frm.dirty();
				let text = __("{0} rows read from the sheet. Save the package to keep them.", [message.rows.length]);
				if (message.created.length) {
					text += "<br><br>" + __("New Items made:") + "<ul>" +
						message.created.map((i) => `<li>${frappe.utils.escape_html(i)}</li>`).join("") + "</ul>";
				}
				frappe.msgprint({ title: __(frm.fields_dict[table].df.label), indicator: "green", message: text });
			});
		},
	});
}

// A Structure BOM row keeps its roof types by name (SOL-ROOF-001); the grid shows what they say.
function show_roof_names(frm) {
	frappe.db.get_list("Roof Type", { fields: ["name", "roof_type"], limit: 500 }).then((roofs) => {
		const says = Object.fromEntries(roofs.map((r) => [r.name, r.roof_type || r.name]));
		const df = frappe.meta.docfield_map["Solar Package Structure BOM"] &&
			frappe.meta.docfield_map["Solar Package Structure BOM"].roof_types;
		if (!df) return;
		df.formatter = (value) => (value || "").split(",").map((v) => v.trim()).filter(Boolean)
			.map((v) => frappe.utils.escape_html(says[v] || v)).join(", ");
		frm.refresh_field("structure_boms");
	});
}

// Depends on Roof Type and Panel Capacity: the company's roof types, and the capacities the
// packages are made in with room for one that none is yet.
function choose_structure_depends_on(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const split = (value) => (value || "").split(",").map((v) => v.trim()).filter(Boolean);
	// Not .map(flt): map's index and array would go in as flt's precision and number format.
	const to_kw = (value) => flt(value);
	const roofs_chosen = split(row.roof_types);
	const kw_chosen = split(row.panel_capacities).map(to_kw);
	Promise.all([
		frappe.db.get_list("Roof Type", { filters: { company: frm.doc.company }, fields: ["name", "roof_type"], limit: 500 }),
		frappe.xcall(`${BOM_TABLES_API}.capacities`),
	]).then(([roofs, capacities]) => {
		const kws = [...new Set(capacities.concat(kw_chosen))].sort((a, b) => a - b);
		const dialog = new frappe.ui.Dialog({
			title: __("Depends on Roof Type and Capacity"),
			fields: [
				{
					fieldname: "roof_types",
					fieldtype: "MultiCheck",
					columns: 2,
					label: __("Roof types"),
					description: __("None ticked: every roof type."),
					options: roofs.map((r) => ({
						label: r.roof_type || r.name, value: r.name, checked: roofs_chosen.includes(r.name),
					})),
				},
				{
					fieldname: "capacities",
					fieldtype: "MultiCheck",
					columns: 4,
					label: __("Panel capacity (kW)"),
					description: __("None ticked: every capacity."),
					options: kws.map((kw) => ({
						label: `${kw} kW`, value: String(kw), checked: kw_chosen.includes(kw),
					})),
				},
				{
					fieldname: "other_capacities",
					fieldtype: "Data",
					label: __("Other capacities (kW)"),
					description: __("Separated by commas, e.g. 6, 7.5"),
				},
			],
			primary_action_label: __("Set"),
			primary_action(values) {
				const others = split(values.other_capacities).map(to_kw);
				if (others.some((kw) => !(kw > 0))) {
					frappe.msgprint(__("Other capacities are numbers of kW, such as 6 or 7.5."));
					return;
				}
				const chosen = [...new Set((values.capacities || []).map(to_kw).concat(others))].sort((a, b) => a - b);
				frappe.model.set_value(cdt, cdn, {
					roof_types: (values.roof_types || []).join(", "),
					panel_capacities: chosen.join(", "),
				});
				dialog.hide();
			},
		});
		dialog.show();
	});
}

// Depends on Inverter is chosen from the package's own inverter options, by their Items.
function choose_inverters(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const offered = [...new Set((frm.doc.inverters || []).map((r) => r.inverter_item).filter(Boolean))];
	if (!offered.length) {
		frappe.msgprint(__("Give the package's inverter options their Items first."));
		return;
	}
	const chosen = (row.inverters || "").split("\n").map((s) => s.trim()).filter(Boolean);
	const quoted = (frm.doc.inverters || []).find((r) => r.is_default);
	const dialog = new frappe.ui.Dialog({
		title: __("Depends on Inverter"),
		fields: [{
			fieldname: "inverters",
			fieldtype: "MultiCheck",
			columns: 1,
			label: __("Needed with"),
			description: __("None ticked: needed with every inverter."),
			options: offered.map((item) => ({
				label: item + (quoted && quoted.inverter_item === item ? ` (${__("default")})` : ""),
				value: item,
				checked: chosen.includes(item),
			})),
		}],
		primary_action_label: __("Set"),
		primary_action({ inverters }) {
			frappe.model.set_value(cdt, cdn, "inverters", (inverters || []).join("\n"));
			dialog.hide();
		},
	});
	dialog.show();
}

// Both tables' rows: the UOM follows the Item chosen (it stays the user's to change after), and
// the amount is the quantity at the rate.
const BOM_ROW_EVENTS = {
	item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item) return;
		frappe.db.get_value("Item", row.item, "stock_uom").then(({ message }) => {
			if (message && message.stock_uom) frappe.model.set_value(cdt, cdn, "uom", message.stock_uom);
		});
	},
	qty: (frm, cdt, cdn) => bom_row_amount(cdt, cdn),
	rate: (frm, cdt, cdn) => bom_row_amount(cdt, cdn),
};

function bom_row_amount(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
}

frappe.ui.form.on("Solar Package Material BOM", {
	...BOM_ROW_EVENTS,
	choose_inverters: (frm, cdt, cdn) => choose_inverters(frm, cdt, cdn),
});

frappe.ui.form.on("Solar Package Structure BOM", {
	...BOM_ROW_EVENTS,
	choose_depends_on: (frm, cdt, cdn) => choose_structure_depends_on(frm, cdt, cdn),
});

// The Expenses' total, as the rows change (the server totals it again on save).
function total_expenses(frm) {
	frm.set_value("total_expenses", (frm.doc.expenses || []).reduce((sum, r) => sum + flt(r.amount), 0));
}

frappe.ui.form.on("Solar Package Expense", {
	...BOM_ROW_EVENTS,
	amount: (frm) => total_expenses(frm),
	expenses_remove: (frm) => total_expenses(frm),
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
