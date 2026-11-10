// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// Each specification row is an Item of its own category: the dropdown offers only that item
// group's items, and choosing one writes its description into the row's specification.
const ITEM_ROWS = [
	["modules", "module_item", "module_specification", () => "Modules"],
	["inverters", "inverter_item", "inverter_specification", () => "Inverters"],
	["batteries", "battery_item", "specification", () => "Batteries"],
	["system_items", "item", "specification", (row) => system_item_group(row.system_type)],
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

// The Pricing Options dropdowns follow the package's panels as they change.
function refresh_panel_choices(frm) {
	refresh_pricing_choices(frm);
}

// A Pricing Option names the package's own panels, inverters and batteries, as solar_package.py
// names them (panel_name, inverter_name, battery_name): each dropdown is rebuilt from those rows.
const one_line = (text) => (text || "").split(/\s+/).filter(Boolean).join(" ");
const battery_name = (row) => one_line(row.specification) || [
	flt(row.battery_voltage) ? `${flt(row.battery_voltage)} V` : "",
	flt(row.battery_capacity_ah) ? `${flt(row.battery_capacity_ah)} Ah` : "",
].filter(Boolean).join(" x ");

function refresh_pricing_choices(frm) {
	const grid = frm.fields_dict.pricing_options && frm.fields_dict.pricing_options.grid;
	if (!grid) return;
	const names = (rows, name) => [...new Set((rows || []).map(name).filter(Boolean))];
	grid.update_docfield_property("panel", "options",
		[""].concat(names(frm.doc.modules, (r) => one_line(r.module_specification))).join("\n"));
	grid.update_docfield_property("inverter", "options",
		[""].concat(names(frm.doc.inverters, (r) => one_line(r.inverter_specification))).join("\n"));
	grid.update_docfield_property("battery", "options", [""].concat(names(frm.doc.batteries, battery_name)).join("\n"));
	grid.refresh();
}

// The Package Cost is the default pricing option's (solar_package.py does it again on save).
function package_cost_from_pricing(frm) {
	const rows = frm.doc.pricing_options || [];
	const row = rows.find((r) => r.is_default) || rows[0];
	frm.set_value("package_cost", row ? flt(row.cost) : 0);
}

frappe.ui.form.on("Solar Package Pricing Option", {
	is_default(frm, cdt, cdn) {
		keep_one_default(frm, "pricing_options", cdt, cdn);
		package_cost_from_pricing(frm);
	},
	pricing_options_add: (frm, cdt, cdn) => default_the_first(frm, "pricing_options", cdt, cdn),
	cost: (frm) => package_cost_from_pricing(frm),
	pricing_options_remove: (frm) => package_cost_from_pricing(frm),
});

frappe.ui.form.on("Solar Package", {
	// Batteries count towards the Total Package Cost on an Off-Grid or Hybrid package only.
	system_type: (frm) => total_the_package(frm),
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
		// An add-on's Item Group is one of the add-on groups (package_items.add_on_groups); its Item
		// is of that group, or of any of them till one is chosen.
		const add_on_groups = () => (frm.doc.__onload && frm.doc.__onload.add_on_groups) || [];
		frm.set_query("item_group", "optional_add_ons", () => ({ filters: { name: ["in", add_on_groups()] } }));
		frm.set_query("item_code", "optional_add_ons", (doc, cdt, cdn) => ({
			filters: { item_group: locals[cdt][cdn].item_group || ["in", add_on_groups()], disabled: 0 },
		}));
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
		show_panel_items(frm);
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

// The Solar Panels grid's first column: the panel's Item in bold, its specification under it.
function show_panel_items(frm) {
	const formatter = (value, df, options, row) => {
		const spec = row && row.module_specification;
		return [
			value && `<b>${frappe.utils.escape_html(frappe.utils.get_link_title("Item", value) || value)}</b>`,
			spec && frappe.utils.escape_html(spec),
		].filter(Boolean).join("<br>");
	};
	// Each grid row formats from its own copy of the fields, made when it is first drawn (and
	// copied from these for the rows still to come), so the base and every copy take it.
	const map = frappe.meta.docfield_map["Solar Package Module"];
	if (map && map.module_item) map.module_item.formatter = formatter;
	Object.values(frappe.meta.docfield_copy["Solar Package Module"] || {}).forEach((fields) => {
		if (fields.module_item) fields.module_item.formatter = formatter;
	});
	// A grid row is one line high; these grow to the two lines, every column with them.
	frappe.dom.set_style(
		`[data-route^="Form/Solar Package/"] .frappe-control[data-fieldname="modules"] .grid-body .data-row > .grid-static-col,
		[data-route^="Form/Solar Package/"] .frappe-control[data-fieldname="modules"] .grid-body .data-row > .row-index,
		[data-route^="Form/Solar Package/"] .frappe-control[data-fieldname="modules"] .grid-body .data-row > .row-check { height: auto; min-height: 38px; }`,
		"a3s-package-panel-rows"
	);
	frm.refresh_field("modules");
}

// A panel option's Total Panel Rate is its Rate per Panel for every panel (solar_package.py
// total_the_panels does it again on save).
function total_the_panel(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.rate) * cint(row.module_count));
	total_the_package(frm);
}

// The Total Package Cost as the rows change: what the default build adds up to, as
// solar_package.py package_build_up works it out again on save. The KSEB, Mounting and
// Installation rows are worked out on save, so until then their amounts are the last saved.
function total_the_package(frm) {
	if (frm.doctype !== "Solar Package") return;
	const doc = frm.doc;
	// A kit's parts (api/package_kits) are not options; an option's amount takes them in.
	const options = (rows) => (rows || []).filter((r) => !r.bundle_part);
	const first_default = (rows) => options(rows).find((r) => r.is_default) || options(rows)[0];
	const sum = (rows, amount) => (rows || []).reduce((total, r) => total + amount(r), 0);
	const kit = (rows, head) => (head ? (rows || []).filter((r) => r === head || (head.bundle_key && r.bundle_part && r.bundle_key === head.bundle_key)) : []);
	const panel = first_default(doc.modules);
	const inverter = first_default(doc.inverters);
	const system = {};
	(doc.system_items || []).forEach((r) => {
		if (r.system_type && (r.is_default || !(r.system_type in system))) system[r.system_type] = r;
	});
	const batteries = ["Off-Grid", "Hybrid"].includes(doc.system_type) ? doc.batteries : [];
	const total =
		sum(kit(doc.modules, panel), (r) => flt(r.rate) * cint(r.module_count)) +
		sum(kit(doc.inverters, inverter), (r) => flt(r.unit_rate) * (cint(r.inverter_count) || 1)) +
		sum((batteries || []).filter((r) => !r.is_option), (r) => flt(r.rate) * cint(r.nos)) +
		sum(Object.values(system), (r) => flt(r.cost)) +
		sum(doc.kseb_expenses, (r) => flt(r.amount)) +
		sum(doc.mounting_expenses, (r) => flt(r.amount)) +
		sum(doc.installation_expenses, (r) => flt(r.amount));
	frm.set_value("total_package_cost", flt(total, 2));
}

frappe.ui.form.on("Solar Package Module", {
	is_default(frm, cdt, cdn) {
		keep_one_default(frm, "modules", cdt, cdn);
		total_the_package(frm);
	},
	modules_add: (frm, cdt, cdn) => default_the_first(frm, "modules", cdt, cdn),
	module_item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "module_item", "module_specification"),
	module_specification(frm, cdt, cdn) {
		refresh_panel_choices(frm);
		// The first column shows it under the Item.
		const row = frm.fields_dict.modules.grid.get_row(cdn);
		if (row) row.refresh();
	},
	rate: total_the_panel,
	module_count: total_the_panel,
	// Rate per Panel is its Wattage x Wattage Rate, as on save.
	module_wattage: (frm, cdt, cdn) => rate_from_wattage(cdt, cdn),
	wattage_rate: (frm, cdt, cdn) => rate_from_wattage(cdt, cdn),
	modules_remove(frm) {
		refresh_panel_choices(frm);
		total_the_package(frm);
	},
});

function rate_from_wattage(cdt, cdn) {
	const row = locals[cdt][cdn];
	if (flt(row.wattage_rate) && !row.bundle_part) frappe.model.set_value(cdt, cdn, "rate", flt(row.module_wattage) * flt(row.wattage_rate));
}

// Balance of system differs: the default is per type, so ticking a DCDB clears only the
// other DCDB rows. An ACDB alongside it is not a competing option.
frappe.ui.form.on("Solar Package System Item", {
	is_default(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.is_default && row.system_type) {
			(frm.doc.system_items || []).forEach((other) => {
				if (other.name !== cdn && other.system_type === row.system_type && other.is_default) {
					frappe.model.set_value(other.doctype, other.name, "is_default", 0);
				}
			});
		}
		total_the_package(frm);
	},
	cost: (frm) => total_the_package(frm),
	system_items_remove: (frm) => total_the_package(frm),

	system_type(frm, cdt, cdn) {
		// A row that has just been given its type is the only one of that type until
		// another arrives, so it is the one quoted.
		const row = locals[cdt][cdn];
		if (row.system_type && !row.is_default) {
			const others = (frm.doc.system_items || []).filter(
				(other) => other.name !== cdn && other.system_type === row.system_type
			);
			if (!others.length) frappe.model.set_value(cdt, cdn, "is_default", 1);
		}
		total_the_package(frm);
	},

	item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "item", "specification"),
});

frappe.ui.form.on("Solar Package Inverter", {
	is_default(frm, cdt, cdn) {
		keep_one_default(frm, "inverters", cdt, cdn);
		total_the_package(frm);
	},
	inverters_add: (frm, cdt, cdn) => default_the_first(frm, "inverters", cdt, cdn),

	inverter_item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "inverter_item", "inverter_specification"),
	inverter_specification: (frm) => refresh_pricing_choices(frm),
	unit_rate: (frm) => total_the_package(frm),
	inverter_count: (frm) => total_the_package(frm),
	inverters_remove(frm) {
		total_the_package(frm);
		refresh_pricing_choices(frm);
	},
});

// The batteries and the KSEB, Mounting and Installation rows are the estimate's doctypes too:
// these handlers act on a package only (total_the_package checks).
frappe.ui.form.on("Design Estimate Battery", {
	rate: battery_amount,
	nos: battery_amount,
	is_option: (frm) => total_the_package(frm),
	batteries_remove(frm) {
		total_the_package(frm);
		if (frm.doctype === "Solar Package") refresh_pricing_choices(frm);
	},
	specification: (frm) => frm.doctype === "Solar Package" && refresh_pricing_choices(frm),
	battery_voltage: (frm) => frm.doctype === "Solar Package" && refresh_pricing_choices(frm),
	battery_capacity_ah: (frm) => frm.doctype === "Solar Package" && refresh_pricing_choices(frm),
});

function battery_amount(frm, cdt, cdn) {
	if (frm.doctype !== "Solar Package") return;
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.rate) * cint(row.nos));
	total_the_package(frm);
}

[
	["Design Estimate KSEB Expense", "kseb_expenses"],
	["Design Estimate Mounting Expense", "mounting_expenses"],
	["Design Estimate Installation Expense", "installation_expenses"],
].forEach(([doctype, table]) => {
	frappe.ui.form.on(doctype, {
		amount: (frm) => total_the_package(frm),
		[`${table}_remove`]: (frm) => total_the_package(frm),
	});
});

// A KSEB row's Amount is its Rate x Quantity (api/expenses.price_by_rate); an Amount typed in the
// grid sets the Rate to match, so the save keeps it.
frappe.ui.form.on("Design Estimate KSEB Expense", {
	rate: (frm, cdt, cdn) => amount_from_rate(frm, cdt, cdn),
	qty: (frm, cdt, cdn) => amount_from_rate(frm, cdt, cdn),
	amount(frm, cdt, cdn) {
		if (frm.doctype !== "Solar Package") return;
		const row = locals[cdt][cdn];
		const qty = row.qty == null || row.qty === "" ? 1 : flt(row.qty);
		if (!row.source && qty && flt(row.rate) * qty !== flt(row.amount)) frappe.model.set_value(cdt, cdn, "rate", flt(row.amount) / qty);
	},
});

// An installation row's Amount is its Rate x Quantity; the line a roof type prices is set on save.
frappe.ui.form.on("Design Estimate Installation Expense", {
	rate: (frm, cdt, cdn) => amount_from_rate(frm, cdt, cdn),
	qty: (frm, cdt, cdn) => amount_from_rate(frm, cdt, cdn),
});

function amount_from_rate(frm, cdt, cdn) {
	if (frm.doctype !== "Solar Package") return;
	const row = locals[cdt][cdn];
	const amount = flt(row.rate) * (row.qty == null || row.qty === "" ? 1 : flt(row.qty));
	if (flt(row.amount) !== amount) frappe.model.set_value(cdt, cdn, "amount", amount);
}

// The Material BOM, Structure BOMs and Expenses (each a tab of its own) come from Excel as often as they are
// typed (api/package_bom_tables): the sheet is read on the server, which finds or makes each
// Item, and its rows replace the table here, to be saved with the package.
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
		// A Category narrows the Items offered (the groups under it too).
		frm.set_query("item", table, (doc, cdt, cdn) => {
			const category = locals[cdt][cdn].category;
			return { filters: category ? { item_group: ["descendants of (inclusive)", category], disabled: 0 } : { disabled: 0 } };
		});
	});
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
					items: JSON.stringify(own_items(frm).map((o) => o.item)),
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

// The package's own Items, as its other tabs name them: what a Materials, Structure or Expenses
// row may depend on (api/package_bom_tables.OWN_ITEMS).
const OWN_ITEMS = [
	["modules", "module_item", "Solar Panel"], ["inverters", "inverter_item", "Inverter"], ["batteries", "battery_item", "Battery"],
	["system_items", "item", "Balance"], ["kseb_expenses", "particulars", "KSEB"], ["mounting_expenses", "item", "Mounting"],
	["installation_expenses", "item", "Installation"],
];

function own_items(frm) {
	const seen = new Set();
	const out = [];
	OWN_ITEMS.forEach(([table, field, tab]) => (frm.doc[table] || []).forEach((r) => {
		if (r[field] && !seen.has(r[field])) {
			seen.add(r[field]);
			out.push({ item: r[field], tab });
		}
	}));
	return out;
}

// Depends On: the row is taken only where one of the Items ticked is used; none ticked, always.
function choose_depends_on(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const offered = own_items(frm);
	const chosen = (row.depends_on || "").split("\n").map((s) => s.trim()).filter(Boolean);
	const gone = chosen.filter((item) => !offered.some((o) => o.item === item)).map((item) => ({ item, tab: __("No longer on the package") }));
	if (!offered.length && !gone.length) {
		frappe.msgprint(__("Give the package's other tabs their Items first."));
		return;
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Depends On"),
		fields: [{
			fieldname: "items",
			fieldtype: "MultiCheck",
			columns: 1,
			label: __("Taken only with"),
			description: __("None ticked: always taken."),
			options: offered.concat(gone).map(({ item, tab }) => ({
				label: `${item} (${tab})`, value: item, checked: chosen.includes(item),
			})),
		}],
		primary_action_label: __("Set"),
		primary_action({ items }) {
			frappe.model.set_value(cdt, cdn, "depends_on", (items || []).join("\n"));
			dialog.hide();
		},
	});
	dialog.show();
}

// The three tables' rows: the UOM and description follow the Item chosen (they stay the user's to
// change after), and the amount is the quantity at the rate.
const BOM_ROW_EVENTS = {
	item(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item) return;
		frappe.db.get_value("Item", row.item, "stock_uom").then(({ message }) => {
			if (message && message.stock_uom) frappe.model.set_value(cdt, cdn, "uom", message.stock_uom);
		});
		fill_from_item(frm, cdt, cdn, "item", "description");
	},
	choose_depends_on: (frm, cdt, cdn) => choose_depends_on(frm, cdt, cdn),
	qty: (frm, cdt, cdn) => bom_row_amount(cdt, cdn),
	rate: (frm, cdt, cdn) => bom_row_amount(cdt, cdn),
};

function bom_row_amount(cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
}

frappe.ui.form.on("Solar Package Material BOM", BOM_ROW_EVENTS);

frappe.ui.form.on("Solar Package Structure BOM", BOM_ROW_EVENTS);

// The Expenses' total, as the rows change (the server totals it again on save).
function total_expenses(frm) {
	// A bundle's or a BOM's items are its parts, already in its own amount (package_bom_tree).
	frm.set_value("total_expenses", (frm.doc.expenses || []).reduce((sum, r) => sum + (r.row_kind === "Component" ? 0 : flt(r.amount)), 0));
}

frappe.ui.form.on("Solar Package Expense", {
	...BOM_ROW_EVENTS,
	amount: (frm) => total_expenses(frm),
	expenses_remove: (frm) => total_expenses(frm),
});

frappe.ui.form.on("Design Estimate Battery", {
	battery_item: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "battery_item", "specification"),
});

// An add-on's Amount is its Rate x Quantity, as on save.
frappe.ui.form.on("Solar Package Add-on", {
	item_code: (frm, cdt, cdn) => fill_from_item(frm, cdt, cdn, "item_code", "item"),
	rate: (frm, cdt, cdn) => amount_from_rate(frm, cdt, cdn),
	qty: (frm, cdt, cdn) => amount_from_rate(frm, cdt, cdn),
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
