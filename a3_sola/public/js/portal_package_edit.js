/* One Solar Package, edited whole: its details and every table, laid out as the desk form lays
   them out - its tabs, sections and columns - and its Item and BOM (a3_sola.api.portal_packages).
   The page keeps the package as the server sent it, changes it here, and posts it whole on Save;
   the server's rules decide the rest and its answer is painted back - computed KSEB rows,
   totals and the like. */
(function () {
	"use strict";

	var API = "a3_sola.api.portal_packages.";
	/* The Materials, Structure and Expenses tabs' tables, which come from Excel as often as they are
	   typed (solar_package.js). */
	var SHEETS = "a3_sola.api.package_bom_tables.";
	var SHEET_TABLES = { material_bom: 1, structure_boms: 1, expenses: 1 };
	/* The desk's Balance and Mounting tabs are not offered here; their rows stay as they are. */
	var HIDDEN_TABS = { tab_system: 1, tab_mounting: 1 };
	/* The BOM tab as a full BOM (package_bom_tree): rows copied there from the other tabs, and each
	   bundle's or BOM's items under it - worked out on save, never typed. */
	var TREE_FIELDS = { row_kind: 1, bom_no: 1, source_row: 1 };
	var SOURCE_TABS = { "Solar Panel": "tab_modules", "Inverter": "tab_inverter", "KSEB": "tab_kseb",
		"Installation": "tab_installation", "Optional Add-ons": "tab_add_ons" };
	var ASSEMBLY_TABLES = { modules: 1, inverters: 1, kseb_expenses: 1, installation_expenses: 1, optional_add_ons: 1,
		material_bom: 1, structure_boms: 1, expenses: 1 };
	function isComponent(r) { return r.row_kind === "Component"; }
	function isOwn(r) { return !r.source_row && !isComponent(r); }
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var pkg = JSON.parse(document.getElementById("a3s-package-data").textContent);
	var form = document.querySelector("[data-pkg-form]");
	var tabsEl = document.querySelector("[data-pkg-tabs]");
	var panels = document.querySelector("[data-pkg-panels]");
	var headActs = document.querySelector("[data-head-actions]");
	var statusEl = form.querySelector("[data-status]");
	var active = "package";
	var dirty = false;

	/* Choices picked from the package's own rows (solar_package.js): an inverter option's Built
	   with Panel is one of the package's panels. */
	/* A Pricing Option names the package's own panels, inverters and batteries, as the server
	   names them (solar_package panel_name, inverter_name, battery_name). */
	function oneLine(t) { return String(t || "").split(/\s+/).filter(Boolean).join(" "); }
	function batteryName(r) {
		return oneLine(r.specification) || [Number(r.battery_voltage) ? Number(r.battery_voltage) + " V" : "",
			Number(r.battery_capacity_ah) ? Number(r.battery_capacity_ah) + " Ah" : ""].filter(Boolean).join(" x ");
	}
	var ROW_SOURCES = {
		"inverters.panel_specification": ["modules", function (r) { return r.module_specification; }],
		"pricing_options.panel": ["modules", function (r) { return oneLine(r.module_specification); }],
		"pricing_options.inverter": ["inverters", function (r) { return oneLine(r.inverter_specification); }],
		"pricing_options.battery": ["batteries", batteryName]
	};
	/* The Item field of each table (the expense tables' own, besides the spec rows'). */
	var ITEM_FIELD = { kseb_expenses: "particulars", mounting_expenses: "item", installation_expenses: "item", components: "item" };
	Object.keys(pkg.item_text).forEach(function (t) { ITEM_FIELD[t] = pkg.item_text[t][0]; });
	var ONE_DEFAULT = { modules: 1, inverters: 1, pricing_options: 1 };
	/* A row's amount is its rate times its count, as the server works it out on save. */
	var ROW_AMOUNT = { modules: ["rate", "module_count"], batteries: ["rate", "nos"], inverters: ["unit_rate", "inverter_count"],
		kseb_expenses: ["rate", "qty"], installation_expenses: ["rate", "qty"], optional_add_ons: ["rate", "qty"] };
	/* A grid's first column that shows the row's Item in bold with its text under it. */
	var STACKED = { modules: ["module_item", "module_specification"] };
	/* A row form laid out line by line - a line of one field is full width, of three, three
	   across - with its Item chosen as an Item, a Bundle or a BOM first. Any field not placed
	   follows, two across. */
	var ROW_LAYOUTS = {
		modules: [["module_item"], ["module_specification"], ["module_make", "module_wattage", "wattage_rate", "is_default"],
			["rate", "module_count", "amount"], ["module_alternate_makes"]],
		inverters: [["inverter_item"], ["inverter_specification"], ["item_group", "inverter_phase", "inverter_topology"],
			["inverter_make", "inverter_model", "panel_specification"], ["inverter_capacity_kw", "with_optimizer", "is_default"],
			["inverter_count", "unit_rate", "amount"]],
		kseb_expenses: [["particulars"], ["rate", "qty", "amount"]],
		installation_expenses: [["item"], ["specification"], ["rate", "qty", "amount"]],
		optional_add_ons: [["item_group", "item_code"], ["item"], ["rate", "qty", "amount"]],
		material_bom: sheetRowLayout, structure_boms: sheetRowLayout, expenses: sheetRowLayout
	};
	/* A Materials, Structure or Expenses row: an Item by its Category first; a Bundle or a BOM by
	   name alone, the line's full width. */
	function sheetRowLayout(kind) {
		return [kind === "Item" ? ["category", "item"] : ["item"], ["description"], ["uom", "qty", "rate", "amount"]];
	}
	/* The tables whose Item Group is chosen first: its Items are offered, none till then. */
	var GROUP_FIRST = { optional_add_ons: 1 };
	/* Not asked in a package's row form: an estimate's alone; an add-on's Type (a new one is Other). */
	var NOT_ASKED = { "installation_expenses.in_package": 1, "optional_add_ons.add_on_type": 1 };
	/* The tables whose Item is chosen as an Item, a Bundle or a BOM first; the others offer their
	   own group's Items. */
	var KIND_TABLES = { modules: 1, inverters: 1, installation_expenses: 1, material_bom: 1, structure_boms: 1, expenses: 1 };
	/* A Bundle or BOM chosen is replaced by its items (package_kits): each row says what it came
	   from. On the panel and inverter tabs a kit is one option - its first row - and its other
	   rows are its parts, counted in the option and never options themselves. */
	var KITS = "a3_sola.api.package_kits.";
	var KIT_FIELD = { bundle_type: 1, bundle_ref: 1, bundle_qty: 1, bundle_key: 1, bundle_part: 1 };
	var OPTION_KITS = { modules: 1, inverters: 1 };
	function isPart(r) { return !!Number(r && r.bundle_part); }
	/* The rows a table counts: a kit's parts and a bundle's listed items are not. */
	function counted(f) {
		return ((pkg.tables[f] && pkg.tables[f].rows) || []).filter(function (r) { return !isComponent(r) && !(OPTION_KITS[f] && isPart(r)); });
	}
	function kitOf(rows, head) {
		return rows.filter(function (r) { return r === head || (head.bundle_key && isPart(r) && r.bundle_key === head.bundle_key); });
	}
	/* A kit part's form: its item, its text, its count and rate. */
	var PART_LAYOUTS = { modules: [["module_item"], ["module_specification"], ["rate", "module_count", "amount"]],
		inverters: [["inverter_item"], ["inverter_specification"], ["inverter_count", "unit_rate", "amount"]] };
	/* Shown, not typed, in a laid-out row form: worked out from the fields beside it. */
	var WORKED_OUT = { "kseb_expenses.amount": "Rate x Quantity.", "installation_expenses.amount": "Rate x Quantity.",
		"modules.rate": "Wattage x Wattage Rate." };
	/* A row the system fills in (a KSEB fee; the installation line, where its roof type has a rate):
	   these follow it and are not typed. */
	var FROM_SOURCE = { "kseb_expenses.rate": "Set by KSEB fees.", "kseb_expenses.qty": "Set by KSEB fees.",
		"installation_expenses.rate": "Set by roof type.", "installation_expenses.qty": "Set by roof type." };
	function roofRate() {
		var roof = (pkg.choices["Roof Type"] || []).find(function (r) { return r.value === pkg.values.roof_type; });
		return roof ? Number(roof.installation_rate) || 0 : 0;
	}
	function setBySystem(table, row) {
		if (!row.source) return false;
		return table === "installation_expenses" ? roofRate() > 0 : true;
	}
	/* A table's own group's Items - exactly its group, where the group is exact (the expenses). */
	function groupOptions(table) {
		var group = pkg.category[table], exact = (pkg.exact_group || []).indexOf(table) !== -1;
		return (pkg.choices.items[group] || []).filter(function (o) { return !o.kind && (!exact || o.group === group); });
	}
	/* Written in a small box, the line's full width: a few words, not a paragraph. */
	var SMALL_TEXT = { "modules.module_specification": 1, "inverters.inverter_specification": 1, "installation_expenses.specification": 1,
		"optional_add_ons.item": 1, "material_bom.description": 1, "structure_boms.description": 1, "expenses.description": 1 };
	var KINDS = ["Item", "Bundle", "BOM"];
	/* An Item row's choices: its category group's own Items (the panels: the Modules groups). A
	   Bundle or BOM row's: every Product Bundle, every Item with a BOM. */
	function kindOptions(table, kind, row) {
		/* A row with an Item Group (the inverters') offers that group's Items only. */
		var group = row && row.item_group;
		var exact = (pkg.exact_group || []).indexOf(table) !== -1;
		if (kind === "Item") return (pkg.choices.items[pkg.category[table]] || []).filter(function (o) {
			return !o.kind && (!group || o.group === group) && (!exact || o.group === pkg.category[table]);
		});
		return allItems().filter(function (o) { return o.kind === kind; })
			.map(function (o) { return { value: o.value, label: o.label.replace(/^(Bundle|BOM): /, ""), text: o.text }; });
	}
	/* The Items a row form offers: by kind, by its chosen group, or its table's group's. A
	   Materials, Structure or Expenses row's: any Item of its Category (the groups under it too),
	   none till one is chosen; or any Bundle, any BOM. */
	function itemOptions(table, kind, row) {
		if (SHEET_TABLES[table]) {
			if (kind !== "Item") return kindOptions(table, kind, row);
			var category = (pkg.choices["Item Group"] || []).find(function (g) { return g.value === row.category; });
			return category ? pkg.choices.Item.filter(function (o) { return !o.kind && category.under.indexOf(o.group) !== -1; }) : [];
		}
		if (KIND_TABLES[table]) return kindOptions(table, kind, row);
		if (!GROUP_FIRST[table]) return groupOptions(table);
		return row.item_group ? (pkg.choices.items[pkg.category[table]] || []).filter(function (o) { return o.group === row.item_group; }) : [];
	}
	/* One of a few choices, as a row of buttons. */
	function pills(name, label, choices, current) {
		return '<div class="a3s-pkg__kinds" role="radiogroup" aria-label="' + esc(label) + '">' + choices.map(function (k) {
			return '<label class="a3s-pkg__kind"><input type="radio" name="' + esc(name) + '" value="' + esc(k) + '"' + (k === current ? " checked" : "") + "><span>" + esc(k) + "</span></label>";
		}).join("") + "</div>";
	}
	function kindOf(value) {
		var hit = value && (pkg.choices.Item.find(function (o) { return o.value === value; }) || allItems().find(function (o) { return o.value === value; }));
		return (hit && hit.kind) || "Item";
	}

	/* ------------------------------------------------------------------ helpers */
	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}
	function serverMessage(body) {
		try {
			var msgs = JSON.parse((body && body._server_messages) || "[]");
			var texts = msgs.map(function (m) { return String(JSON.parse(m).message || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim(); }).filter(Boolean);
			if (texts.length) return texts.join(" ");
		} catch (e) { /* fall through */ }
		return (body && body.exception) ? String(body.exception).split("\n").pop().replace(/^[\w.]+(Error|Exception):\s*/, "").trim() : "";
	}
	function call(method, args) { return callPath(API + method, args); }
	function callPath(path, args) {
		return fetch("/api/method/" + path, {
			method: "POST", credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json", "Content-Type": "application/json" },
			body: JSON.stringify(args || {})
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
				return body.message;
			});
		});
	}
	function setStatus(el, text, tone) {
		el.textContent = text || "";
		el.dataset.tone = tone || "";
		el.hidden = !text;
	}
	function icon(name) { return '<svg class="a3s-ic" aria-hidden="true"><use href="#ic-' + name + '"></use></svg>'; }
	function isNum(type) { return type === "Float" || type === "Int" || type === "Currency" || type === "Percent"; }
	function money(n) { return "₹" + (Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 }); }
	function systemGroup(type) {
		return { "Solar Energy Meter": "Meters", "Mounting Structure": "Mounting Structures", Battery: "Batteries" }[type] || "Cables and BOS";
	}
	function company() { return pkg.values.company || ""; }
	function hasBatteries() { return ["Off-Grid", "Hybrid"].indexOf(pkg.values.system_type) !== -1; }
	function touch() { dirty = true; paintHead(); }
	/* A list one per line (Depends On, as an Item may hold a comma), or by commas. */
	function split(value, byLine) {
		return String(value || "").split(byLine ? "\n" : /[,\n]/).map(function (s) { return s.trim(); }).filter(Boolean);
	}
	/* The Expenses' total, as the rows change (the server totals it again on save). */
	function totalExpenses() {
		if (!pkg.tables.expenses) return;
		pkg.values.total_expenses = pkg.tables.expenses.rows.reduce(function (sum, r) { return sum + (isComponent(r) ? 0 : Number(r.amount) || 0); }, 0);
	}
	/* What a Pricing Options row's cost is made of, as the rows stand (solar_package.pricing_build_up,
	   again on save): its panel's and inverter's options (a kit's parts in them) and its battery,
	   the Installation rows, the Materials, Structure and Expenses rows that go with that panel and
	   inverter, and its margin. Not KSEB. */
	function pricingBuildUp(r) {
		function rows(f) { return (pkg.tables[f] && pkg.tables[f].rows) || []; }
		function n(x) { return Number(x) || 0; }
		function sum(list, amount) { return list.reduce(function (total, x) { return total + amount(x); }, 0); }
		var panel = rows("modules").find(function (x) { return !isPart(x) && oneLine(x.module_specification) && oneLine(x.module_specification) === oneLine(r.panel); });
		var inverter = rows("inverters").find(function (x) { return !isPart(x) && oneLine(x.inverter_specification) && oneLine(x.inverter_specification) === oneLine(r.inverter); });
		var battery = r.battery && hasBatteries() ? rows("batteries").find(function (x) { return batteryName(x) === oneLine(r.battery); }) : null;
		var panels = panel ? kitOf(rows("modules"), panel) : [], inverters = inverter ? kitOf(rows("inverters"), inverter) : [];
		/* The Items it uses, which a Materials, Structure or Expenses row may depend on. */
		var used = {};
		function use(list, f) { list.forEach(function (x) { if (x && x[f]) used[x[f]] = 1; }); }
		use(panels, "module_item");
		use(inverters, "inverter_item");
		use(battery ? [battery] : [], "battery_item");
		use(rows("system_items").filter(function (x) { return x.is_default; }), "item");
		use(rows("kseb_expenses"), "particulars");
		use(rows("mounting_expenses"), "item");
		use(rows("installation_expenses"), "item");
		function applying(f) {
			return sum(rows(f).filter(function (x) {
				var deps = split(x.depends_on, true);
				return x.item && isOwn(x) && (!deps.length || deps.some(function (d) { return used[d]; }));
			}), function (x) { return n(x.qty) * n(x.rate); });
		}
		var parts = [["Panel", sum(panels, function (x) { return n(x.rate) * n(x.module_count); })],
			["Inverter", sum(inverters, function (x) { return n(x.unit_rate) * (n(x.inverter_count) || 1); })]];
		if (hasBatteries()) parts.push(["Battery", battery ? n(battery.rate) * n(battery.nos) : 0]);
		return parts.concat([["Installation", sum(rows("installation_expenses"), function (x) { return n(x.amount); })],
			["Materials", applying("material_bom")], ["Structure", applying("structure_boms")], ["Expenses", applying("expenses")],
			["Margin", n(r.margin)]]);
	}
	function pricingCost(r) {
		return Math.round(pricingBuildUp(r).reduce(function (total, p) { return total + p[1]; }, 0) * 100) / 100;
	}
	function breakdownRows(r) {
		return '<p class="a3s-pkg__breakdownhead">How the cost is made up</p><dl class="a3s-pkg__breakdownlist">' +
			pricingBuildUp(r).map(function (p) { return "<div><dt>" + esc(p[0]) + "</dt><dd>" + money(p[1]) + "</dd></div>"; }).join("") +
			'<div class="a3s-pkg__breakdowntotal"><dt>Package Cost</dt><dd>' + money(pricingCost(r)) + "</dd></div></dl>";
	}
	/* The Package Cost is the default pricing option's, as the rows change (again on save). */
	function packageCostFromPricing() {
		var rows = (pkg.tables.pricing_options && pkg.tables.pricing_options.rows) || [];
		var row = rows.find(function (r) { return r.is_default; }) || rows[0];
		pkg.values.package_cost = row ? Number(row.cost) || 0 : 0;
		var shown = panels.querySelector('[data-ro="package_cost"]');
		if (shown) shown.textContent = money(pkg.values.package_cost);
	}
	/* The Total Package Cost as the rows change: the default panel's Total Panel Rate, the default
	   inverter's rate x nos, the batteries, the default Balance of System rows and the KSEB,
	   Mounting and Installation amounts (solar_package.package_build_up, again on save). */
	function totalPackageCost() {
		function rows(f) { return (pkg.tables[f] && pkg.tables[f].rows) || []; }
		function first(f) { var r = rows(f).filter(function (x) { return !isPart(x); }); return r.find(function (x) { return x.is_default; }) || r[0]; }
		function n(x) { return Number(x) || 0; }
		/* An option's amount, a kit's parts in it. */
		function option(f, head, rate, count, atLeastOne) {
			return head ? kitOf(rows(f), head).reduce(function (sum, r) { return sum + n(r[rate]) * (n(r[count]) || (atLeastOne ? 1 : 0)); }, 0) : 0;
		}
		var panel = first("modules"), inverter = first("inverters"), system = {};
		rows("system_items").forEach(function (r) { if (r.system_type && (r.is_default || !(r.system_type in system))) system[r.system_type] = r; });
		var total = option("modules", panel, "rate", "module_count") + option("inverters", inverter, "unit_rate", "inverter_count", true);
		if (hasBatteries()) rows("batteries").forEach(function (r) { if (!r.is_option) total += n(r.rate) * n(r.nos); });
		Object.keys(system).forEach(function (k) { total += n(system[k].cost); });
		["kseb_expenses", "mounting_expenses", "installation_expenses"].forEach(function (f) { rows(f).forEach(function (r) { total += n(r.amount); }); });
		pkg.values.total_package_cost = Math.round(total * 100) / 100;
		var shown = panels.querySelector('[data-ro="total_package_cost"]');
		if (shown) shown.textContent = money(pkg.values.total_package_cost);
	}

	/* ------------------------------------------------------------------ choices */
	function allItems() {
		var seen = {}, out = [];
		Object.keys(pkg.choices.items).forEach(function (g) {
			pkg.choices.items[g].forEach(function (i) { if (!seen[i.value]) { seen[i.value] = 1; out.push(i); } });
		});
		return out;
	}
	/* What a Link field offers, narrowed as the desk form's queries narrow it. */
	function linkOptions(table, col, row) {
		var c = pkg.choices, f = col.fieldname, doctype = col.options;
		if (f === "item_group" && table && pkg.category[table]) return (c.item_groups || {})[pkg.category[table]] || [];
		if (table && ITEM_FIELD[table] === f) {
			if (table === "components") return allItems();
			var group = table === "system_items" ? systemGroup(row.system_type) : pkg.category[table];
			return c.items[group] || [];
		}
		if (f === "inverter_model") {
			return c["Inverter Model"].filter(function (m) {
				return (!row.inverter_make || m.make === row.inverter_make) && (!row.inverter_phase || m.phase === row.inverter_phase);
			});
		}
		if (f === "battery_variant") {
			return c["Component Technology"].filter(function (t) { return t.type === "Battery" && (!t.company || t.company === company()); });
		}
		if (f === "battery_make") {
			return c["Component Make"].filter(function (m) {
				return m.type === "Battery" && m.active && (!m.company || m.company === company()) && (!row.battery_variant || m.technology === row.battery_variant);
			});
		}
		var list = c[doctype] || [];
		if (doctype === "Component Make") return list.filter(function (m) { return m.active; });
		if (doctype === "Roof Type" || doctype === "Billing Milestone Template") {
			return list.filter(function (x) { return !x.company || x.company === company(); });
		}
		return list;
	}
	function labelOf(doctype, value, table, field) {
		if (!value) return "";
		var list = (table && ITEM_FIELD[table] === field) ? allItems() : doctype === "Item" ? pkg.choices.Item.concat(allItems()) :
			(pkg.choices[doctype] || []);
		var hit = list.find(function (o) { return o.value === value; });
		return hit ? hit.label : value;
	}
	function rowOptions(src) {
		var seen = [];
		(pkg.tables[src[0]].rows || []).forEach(function (r) {
			if (isPart(r)) return;
			var v = src[1](r);
			if (v && seen.indexOf(v) === -1) seen.push(v);
		});
		return seen.map(function (v) { return { value: v, label: v }; });
	}

	/* ------------------------------------------------------------------ inputs */
	function input(col, value, opts) {
		opts = opts || {};
		var id = (opts.prefix || "f-") + col.fieldname, name = ' name="' + esc(col.fieldname) + '" id="' + id + '"';
		var req = col.reqd ? ' <span class="a3s-req">*</span>' : "";
		var label = '<label for="' + id + '">' + esc(col.label) + req + "</label>";
		var described = col.description;
		/* The tabs' Item fields take a Product Bundle or an Item with a BOM as well (package_bom_tree). */
		if (opts.table && ASSEMBLY_TABLES[opts.table] && (ITEM_FIELD[opts.table] === col.fieldname || (SHEET_TABLES[opts.table] && col.fieldname === "item"))) {
			described = "An Item, a Bundle or a BOM: bundles and BOMs are listed first. A bundle's items go into the package's own BOM when it is made.";
		}
		if (opts.hint !== undefined) described = opts.hint;
		var hint = described ? '<p class="a3s-field__hint">' + esc(described) + "</p>" : "";
		if (col.read_only) {
			var shown = col.type === "Link" ? labelOf(col.options, value, opts.table, col.fieldname) :
				col.type === "Currency" ? (value != null && value !== "" ? money(value) : "") : col.type === "Check" ? (value ? "Yes" : "No") : value;
			return '<div class="a3s-field"><span class="a3s-pkg__rolabel">' + esc(col.label) + '</span><p class="a3s-pkg__ro" data-ro="' + esc(col.fieldname) + '">' +
				(shown === "" || shown == null ? '<span class="a3s-table__muted">Not set</span>' : esc(shown)) + "</p>" + hint + "</div>";
		}
		if (col.type === "Check") {
			return '<label class="a3s-check"><input type="checkbox"' + name + (value ? " checked" : "") + "><span>" + esc(col.label) + "</span></label>";
		}
		if (opts.small) {
			return '<div class="a3s-field a3s-field--wide">' + label + '<textarea rows="2"' + (col.type === "Data" ? ' maxlength="140"' : "") + name + ">" + esc(value) + "</textarea>" + hint + "</div>";
		}
		if (col.type === "Small Text" || col.type === "Text") {
			return '<div class="a3s-field a3s-field--wide">' + label + '<textarea rows="3"' + name + ">" + esc(value) + "</textarea>" + hint + "</div>";
		}
		if (col.type === "Select" || col.type === "Link") {
			var options = opts.options ? opts.options : ROW_SOURCES[opts.table + "." + col.fieldname] ? rowOptions(ROW_SOURCES[opts.table + "." + col.fieldname]) :
				col.type === "Link" ? linkOptions(opts.table, col, opts.row || pkg.values) :
				(col.options || []).filter(function (o) { return o !== ""; }).map(function (o) { return { value: o, label: o }; });
			var found = !value || options.some(function (o) { return o.value === value; });
			var html = '<option value="">' + (col.type === "Link" ? "Choose…" : "—") + "</option>" +
				(found ? "" : '<option value="' + esc(value) + '" selected>' + esc(labelOf(col.options, value, opts.table, col.fieldname)) + " (not offered)</option>") +
				options.map(function (o) { return '<option value="' + esc(o.value) + '"' + (o.value === value ? " selected" : "") + ">" + esc(o.label) + "</option>"; }).join("");
			var combo = options.length > 12 || opts.comboLimit;
			var comboAttrs = combo ? " data-combo" + (opts.comboLimit ? ' data-combo-limit="' + opts.comboLimit + '" data-combo-open' : "") : "";
			return '<div class="a3s-field' + (combo ? " a3s-combo a3s-combo--field" : "") + '"' + comboAttrs + ">" + label + "<select" + name + ">" + html + "</select>" + hint + "</div>";
		}
		var type = isNum(col.type) ? ' type="number" step="' + (col.type === "Int" ? "1" : "any") + '" inputmode="decimal"' : "";
		return '<div class="a3s-field">' + label + "<input" + type + name + ' value="' + esc(value == null ? "" : value) + '">' + hint + "</div>";
	}
	function readValue(el, col) {
		if (col.type === "Check") return el.checked ? 1 : 0;
		if (isNum(col.type)) return el.value === "" ? (col.type === "Int" ? 0 : 0) : Number(el.value);
		return el.value;
	}

	/* ------------------------------------------------------------------ tabs and panels */
	function visibleTabs() {
		return pkg.tabs.filter(function (t) { return !HIDDEN_TABS[t.key] && (t.key !== "batteries" || hasBatteries()); });
	}
	function paintTabs() {
		tabsEl.innerHTML = visibleTabs().map(function (t) {
			var n = t.tables.reduce(function (sum, f) { return sum + counted(f).length; }, 0);
			return '<button type="button" role="tab" data-tab="' + t.key + '" aria-selected="' + (t.key === active) + '"><span>' + esc(t.label) + "</span>" +
				(t.tables.length ? '<span class="a3s-ce-tabs__n">' + n + "</span>" : "") + "</button>";
		}).join("");
	}
	function paint() {
		if (!visibleTabs().some(function (t) { return t.key === active; })) active = "package";
		paintTabs();
		var tab = pkg.tabs.find(function (t) { return t.key === active; });
		panels.innerHTML = tab.sections.map(function (s) { return sectionHtml(tab, s); }).join("");
		paintTerms();
		if (window.a3sCombo) window.a3sCombo.wireAll(panels);
	}
	/* A section of the desk form: its title, then its columns side by side, each column's fields,
	   tables and HTML in the desk's order. A section of fields only reads across, so its rows
	   line up. A section that opens with a table of its own name needs no title of its own. */
	function sectionHtml(tab, s) {
		var first = s.columns[0][0];
		var titled = s.label && !(first.table && pkg.tables[first.table].label === s.label);
		var fieldsOnly = s.columns.every(function (c) { return c.every(function (e) { return e.field; }); });
		var body = s.columns.length > 1 && fieldsOnly ? acrossHtml(tab, s.columns)
			: s.columns.length > 1
			? '<div class="a3s-pkg__cols">' + s.columns.map(function (c) { return '<div class="a3s-pkg__stack">' + entriesHtml(tab, c, false) + "</div>"; }).join("") + "</div>"
			: entriesHtml(tab, s.columns[0], true);
		return '<section class="a3s-pkg__section">' + (titled ? '<h3 class="a3s-pkg__sectiontitle">' + esc(s.label) + "</h3>" : "") + body + "</section>";
	}
	/* The desk's columns row by row: each column's first field makes the first row, its second
	   the second, and so on - the Package tab's System Type, Connection Type, Specification Code
	   and Package Name across the top. A shorter column leaves its place in a row empty. */
	function acrossHtml(tab, columns) {
		var n = Math.min(columns.length, 4), depth = Math.max.apply(null, columns.map(function (c) { return c.length; })), cells = [];
		for (var i = 0; i < depth; i++) {
			columns.forEach(function (c) {
				cells.push(c[i] ? fieldHtml(tab, c[i].field) : '<div class="a3s-pkg__gap" aria-hidden="true"></div>');
			});
		}
		return '<div class="a3s-form__grid a3s-pkg__across' + (n > 2 ? " a3s-form__grid--" + n : "") + '">' + cells.join("") + "</div>";
	}
	function fieldHtml(tab, fieldname) {
		var col = tab.fields.find(function (c) { return c.fieldname === fieldname; });
		if (col.fieldname === "item" || col.fieldname === "bom") col = Object.assign({}, col, { read_only: 1 });
		return input(col, pkg.values[col.fieldname]);
	}
	/* A column's entries; in a one-column section its fields sit two to a row, as the rest of
	   the portal's forms have them. */
	function entriesHtml(tab, entries, grid) {
		var html = "", fields = [];
		function flush() {
			if (fields.length) html += '<div class="' + (grid ? "a3s-form__grid" : "a3s-pkg__stack") + '">' + fields.join("") + "</div>";
			fields = [];
		}
		entries.forEach(function (e) {
			if (e.field) {
				/* Each Payment Terms' milestones under it, in its own column. */
				fields.push(fieldHtml(tab, e.field) + (TERMS[e.field] ? '<div class="a3s-pkg__terms" data-terms-for="' + e.field + '"></div>' : ""));
				return;
			}
			flush();
			if (e.table) {
				html += tableHtml(e.table);
				if (e.table === "batteries" && !hasBatteries()) html += '<p class="a3s-field__hint">Batteries are for Off-Grid and Hybrid systems.</p>';
			}
		});
		flush();
		return html;
	}
	/* The grid's columns are the desk grid's: every column in its list view. */
	function listColumns(spec) {
		var cols = spec.columns.filter(function (c) { return c.in_list; });
		return cols.length ? cols : spec.columns.slice(0, 6);
	}
	function cell(spec, col, row) {
		var v = row[col.fieldname], stack = STACKED[spec.fieldname];
		if (stack && col.fieldname === stack[0]) {
			var name = v ? labelOf(col.options, v, spec.fieldname, col.fieldname) : "", text = row[stack[1]] || "";
			if (!name && !text) return '<span class="a3s-table__muted">—</span>';
			return (name ? '<strong class="a3s-pkg__cellname">' + esc(name) + "</strong>" : "") + (name && text ? "<br>" : "") +
				(text ? '<span class="a3s-pkg__celltext">' + esc(text) + "</span>" : "");
		}
		if (col.fieldname === "depends_on" && SHEET_TABLES[spec.fieldname]) return dependsCell(split(v, true).map(function (i) { return labelOf("Item", i); }));
		if (col.type === "Check") return v ? '<span class="a3s-pkg__tick" aria-label="Yes">' + icon("check") + "</span>" : "";
		if (v === "" || v == null) return '<span class="a3s-table__muted">—</span>';
		if (col.type === "Link") return esc(labelOf(col.options, v, spec.fieldname, col.fieldname));
		if (col.type === "Currency") return money(v);
		if (isNum(col.type)) return esc(Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 }));
		return esc(v);
	}
	/* Depending on nothing, a row is always taken (package_bom_tables.applies). */
	function dependsCell(names) {
		return names.length ? esc(names.join(", ")) : '<span class="a3s-table__muted">Always</span>';
	}
	/* A BOM-tab row's Item cell in the full BOM: a bundle or BOM marked as such, its items set in
	   under it, a copied row saying which tab it comes from. */
	function treeCell(f, row, html) {
		var twig = '<span class="a3s-pkg__twig" aria-hidden="true">\u2514</span>';
		/* A kit's part, under its option; a row from a bundle or BOM, which one. */
		if (OPTION_KITS[f] && isPart(row)) return twig + html;
		var kit = row.bundle_ref ? ' <span class="a3s-badge a3s-badge--open">' + esc((row.bundle_type || "Bundle") + " \u00b7 " + row.bundle_ref) + "</span>" : "";
		if (!SHEET_TABLES[f]) return html + kit;
		if (isComponent(row)) return twig + html;
		var tags = kit;
		if (row.row_kind) tags += ' <span class="a3s-badge a3s-badge--open">' + esc(row.row_kind === "BOM" && row.bom_no ? "BOM · " + row.bom_no : row.row_kind) + "</span>";
		if (row.source_row) tags += ' <span class="a3s-badge">From ' + esc(row.source_row) + "</span>";
		return html + tags;
	}
	function rowClass(f, row) {
		if (OPTION_KITS[f]) return isPart(row) ? " a3s-pkg__child" : row.bundle_key ? " a3s-pkg__parent" : "";
		if (!SHEET_TABLES[f]) return "";
		return isComponent(row) ? " a3s-pkg__child" : row.row_kind ? " a3s-pkg__parent" : "";
	}
	/* Copied and component rows are worked out on save: a copied row is changed on its own tab. */
	function rowActions(f, row, i) {
		if (SHEET_TABLES[f] && isComponent(row)) return "";
		if (SHEET_TABLES[f] && row.source_row) {
			var tab = SOURCE_TABS[String(row.source_row).replace(/ row \d+$/, "")];
			return tab ? '<button type="button" class="a3s-btn a3s-btn--ghost a3s-btn--sm" data-goto-tab="' + tab + '">Edit on its tab</button>' : "";
		}
		return '<div class="a3s-users__actions">' +
			'<button type="button" class="a3s-icon-btn a3s-icon-btn--framed" data-edit-row title="Edit" aria-label="Edit row ' + (i + 1) + '">' + icon("edit") + "</button>" +
			'<button type="button" class="a3s-icon-btn a3s-icon-btn--danger" data-remove-row title="Remove" aria-label="Remove row ' + (i + 1) + '">' + icon("trash") + "</button>" +
			"</div>";
	}
	function tableHtml(f) {
		var spec = pkg.tables[f], cols = listColumns(spec), rows = spec.rows || [];
		/* Each pricing row's cost, from the other tabs as they stand. */
		if (f === "pricing_options") rows.forEach(function (r) { r.cost = pricingCost(r); });
		var sheet = SHEET_TABLES[f] ?
			'<button type="button" class="a3s-btn a3s-btn--ghost a3s-btn--sm" data-sheet="download">' + icon("download") + "<span>Download Excel</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost a3s-btn--sm" data-sheet="upload">' + icon("upload") + "<span>Upload Excel</span></button>" : "";
		return '<section class="a3s-pkg__table" data-table="' + f + '">' +
			'<div class="a3s-pkg__tablehead"><h3 class="a3s-pkg__tabletitle">' + esc(spec.label) + ' <span class="a3s-pkg__count">' + counted(f).length + "</span></h3>" +
			'<div class="a3s-pkg__tableacts">' + sheet +
			'<button type="button" class="a3s-btn a3s-btn--secondary a3s-btn--sm" data-add-row><span>+ Add row</span></button></div></div>' +
			(rows.length ? '<div class="a3s-tablewrap"><table class="a3s-table a3s-pkg__rows"><thead><tr>' +
				cols.map(function (c) { return "<th" + (isNum(c.type) ? ' class="a3s-table__num"' : "") + ">" + esc(c.label) + "</th>"; }).join("") +
				'<th><span class="a3s-sr-only">Actions</span></th></tr></thead><tbody>' +
				rows.map(function (row, i) {
					return '<tr data-row="' + i + '" class="' + rowClass(f, row) + '">' + cols.map(function (c, k) {
						var html = cell(spec, c, row);
						return '<td data-label="' + esc(c.label) + '"' + (isNum(c.type) ? ' class="a3s-table__num"' : "") + ">" + (k === 0 ? treeCell(f, row, html) : html) + "</td>";
					}).join("") + "<td>" + rowActions(f, row, i) + "</td></tr>";
				}).join("") + "</tbody></table></div>" :
				'<p class="a3s-pkg__none">No rows yet.</p>') +
			(SHEET_TABLES[f] ? '<p class="a3s-field__hint">Only the rows added here: nothing is copied in from the other tabs on save.</p>' : "") +
			(f === "pricing_options" ? '<p class="a3s-field__hint">The package is saved with one row at least.</p>' : "") +
			"</section>";
	}
	/* The Payment Terms fields, each with its milestones under it; what a blank one says. */
	var TERMS = { payment_terms: "Choose the payment terms to see their milestones.",
		financed_payment_terms: "None chosen: a financed job takes the terms beside." };
	function paintTerms() {
		Array.prototype.forEach.call(panels.querySelectorAll("[data-terms-for]"), function (el) {
			var n = pkg.values[el.dataset.termsFor];
			if (!n) { el.innerHTML = '<p class="a3s-field__hint">' + esc(TERMS[el.dataset.termsFor]) + "</p>"; return; }
			var t = pkg.choices["Billing Milestone Template"].find(function (x) { return x.value === n; }) || { label: n, milestones: [] };
			el.innerHTML = '<div class="a3s-pkg__term"><p class="a3s-pkg__termname">' + esc(t.label) + "</p>" +
				'<table class="a3s-table a3s-pkg__termtable"><thead><tr><th>Milestone</th><th>When</th><th class="a3s-table__num">%</th></tr></thead><tbody>' +
				t.milestones.map(function (m) {
					return '<tr><td data-label="Milestone">' + esc(m.name) + (m.advance ? ' <span class="a3s-badge a3s-badge--quotation">Advance</span>' : "") + "</td>" +
						'<td data-label="When">' + esc(m.when) + '</td><td data-label="%" class="a3s-table__num">' + esc(m.percent) + "%</td></tr>";
				}).join("") + "</tbody></table></div>";
		});
	}

	/* The package's own fields: kept as they change. */
	panels.addEventListener("change", function (e) {
		var el = e.target;
		if (!el.name || el.closest("[data-table]")) return;
		var tab = pkg.tabs.find(function (t) { return t.key === active; });
		var col = tab && tab.fields.find(function (c) { return c.fieldname === el.name; });
		if (!col) return;
		pkg.values[col.fieldname] = readValue(el, col);
		touch();
		if (col.fieldname === "system_type") { paintTabs(); totalPackageCost(); }
		if (col.fieldname === "payment_terms" || col.fieldname === "financed_payment_terms") paintTerms();
		if (col.fieldname === "company") paint();
	});
	tabsEl.addEventListener("click", function (e) {
		var b = e.target.closest("[data-tab]");
		if (!b) return;
		active = b.dataset.tab;
		paint();
	});

	/* ------------------------------------------------------------------ rows */
	function modal(title, sub) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML = '<div class="a3s-modal__panel a3s-users__panel a3s-pkg__modal" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
			'<div class="a3s-users__modalhead"><h3 class="a3s-modal__title">' + esc(title) + "</h3>" +
			'<button type="button" class="a3s-icon-btn" data-close aria-label="Close">&times;</button></div>' +
			(sub ? '<p class="a3s-users__sub">' + sub + "</p>" : "") +
			'<div data-body></div><p class="a3s-attach__status" data-mstatus role="status" aria-live="polite" hidden></p></div>';
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
		document.body.appendChild(back);
		return { el: back, body: back.querySelector("[data-body]"), close: close,
			status: function (t, tone) { setStatus(back.querySelector("[data-mstatus]"), t, tone); } };
	}
	function rowForm(table, index) {
		var spec = pkg.tables[table], rows = spec.rows, adding = index == null;
		var draft = adding ? {} : Object.assign({}, rows[index]);
		if (adding) {
			spec.columns.forEach(function (c) { if (c.default != null && c.default !== "") draft[c.fieldname] = isNum(c.type) || c.type === "Check" ? Number(c.default) : c.default; });
		}
		var m = modal((adding ? "Add " : "Edit ") + spec.label.toLowerCase() + " row", adding ? "" : "Row " + (index + 1));
		var part = OPTION_KITS[table] && isPart(draft);
		var layout = part ? PART_LAYOUTS[table] : ROW_LAYOUTS[table];
		var itemField = ITEM_FIELD[table] || (SHEET_TABLES[table] ? "item" : null);
		var kind = layout ? kindOf(draft[itemField]) : null;
		/* A row saved before it had an Item Group is in its Item's. */
		if (GROUP_FIRST[table] && !draft.item_group && draft[itemField]) {
			draft.item_group = (allItems().find(function (o) { return o.value === draft[itemField]; }) || {}).group;
		}
		/* What a row form's Item says under it. */
		function itemHint() {
			if (SHEET_TABLES[table]) {
				if (kind === "Item" && !draft.category) return "Choose the category first.";
				return kind !== "Item" ? "Replaced by its items." : "Choosing fills the description.";
			}
			if (part) return "Part of the kit above.";
			if (kind !== "Item" && KIND_TABLES[table]) return "Replaced by its items.";
			if (GROUP_FIRST[table]) return draft.item_group ? "Choosing fills the description." : "Choose the group first.";
			return pkg.item_text[table] ? "Choosing fills the specification." : "From " + pkg.category[table] + " items.";
		}
		function shown(c) {
			return !PICKED[table + "." + c.fieldname] && !TREE_FIELDS[c.fieldname] && !KIT_FIELD[c.fieldname] &&
				!(layout && NOT_ASKED[table + "." + c.fieldname]);
		}
		function field(c) {
			var opts = { table: table, row: draft, prefix: "r-" };
			if (layout && c.fieldname === itemField) {
				opts.options = itemOptions(table, kind, draft);
				opts.comboLimit = 10;
				opts.hint = itemHint();
				/* A kit's part is the item the bundle or BOM has. */
				if (part) c = Object.assign({}, c, { read_only: 1 });
			}
			if (layout && SHEET_TABLES[table] && c.fieldname === "category") opts.comboLimit = 10;
			var key = table + "." + c.fieldname;
			if (key === "pricing_options.cost") opts.hint = "Worked out, as below.";
			/* A kit's part keeps its own rate (its selling price). */
			if (layout && ((WORKED_OUT[key] && !part) || (FROM_SOURCE[key] && setBySystem(table, draft)))) {
				opts.hint = WORKED_OUT[key] || FROM_SOURCE[key];
				c = Object.assign({}, c, { read_only: 1 });
			}
			if (SMALL_TEXT[table + "." + c.fieldname]) opts.small = true;
			return input(c, draft[c.fieldname], opts);
		}
		/* Line by line, as ROW_LAYOUTS says; else every field, two across. */
		function fieldsHtml() {
			if (!layout) return '<div class="a3s-form__grid">' + spec.columns.filter(shown).map(field).join("") + pickerHtml(table, draft) + "</div>";
			var placed = {};
			/* A layout that follows the kind places every field it asks for. */
			var byKind = typeof layout === "function";
			var lines = (byKind ? layout(kind) : layout).map(function (line) {
				var cols = line.map(function (f) { placed[f] = 1; return spec.columns.find(function (c) { return c.fieldname === f; }); })
					.filter(function (c) { return c && shown(c); });
				return cols.length ? '<div class="a3s-pkg__line a3s-pkg__line--' + line.length + '">' + cols.map(field).join("") + "</div>" : "";
			}).join("");
			var rest = byKind ? [] : spec.columns.filter(function (c) { return shown(c) && !placed[c.fieldname]; });
			var kinds = KIND_TABLES[table] && !part ? pills("a3s-row-kind", spec.label + " row is", KINDS, kind) : "";
			return kinds + '<div class="a3s-pkg__lines">' + lines + "</div>" +
				(rest.length ? '<div class="a3s-form__grid">' + rest.map(field).join("") + "</div>" : "") + pickerHtml(table, draft);
		}
		function paintForm() {
			m.body.innerHTML = '<form class="a3s-modal__form" novalidate>' + fieldsHtml() +
				'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary"><span>' + (adding ? "Add row" : "Done") + "</span></button>" +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
			if (window.a3sCombo) window.a3sCombo.wireAll(m.body);
		}
		/* The Item's search box, ready to type in: its first ten choices open under it. Where the
		   group comes first, its dropdown until one is chosen. */
		function focusItem() {
			var box = layout && (GROUP_FIRST[table] && !draft.item_group ? m.body.querySelector("#r-item_group") :
				SHEET_TABLES[table] && kind === "Item" && !draft.category ? m.body.querySelector("#r-category-search") :
				m.body.querySelector("#r-" + itemField + "-search"));
			if (box) box.focus();
		}
		paintForm();
		if (adding) focusItem();
		/* A choice that narrows another (make and phase the model, variant the make, type the
		   item) repaints the form; an Item fills the row's specification text. */
		var REPAINT = { inverter_make: 1, inverter_phase: 1, battery_variant: 1, system_type: 1 };
		m.body.addEventListener("change", function (e) {
			var el = e.target;
			/* Item, Bundle or BOM: the Item's choices follow; one of the other kind is let go. */
			if (el.name === "a3s-row-kind") {
				kind = el.value;
				readPickers(table, draft, m.body);
				if (draft[itemField] && !itemOptions(table, kind, draft).some(function (o) { return o.value === draft[itemField]; })) draft[itemField] = "";
				paintForm();
				focusItem();
				return;
			}
			/* Depends on, ticked: the package's Items to choose from. */
			if (el.name === "pick-depends") {
				var list = m.body.querySelector("[data-depends]");
				if (list) list.hidden = !el.checked;
				return;
			}
			var col = spec.columns.find(function (c) { return c.fieldname === el.name; });
			if (!col) return;
			draft[col.fieldname] = readValue(el, col);
			/* The Item Group (a Category) narrows the Items: one of another group is let go. */
			if (layout && (col.fieldname === "item_group" || (SHEET_TABLES[table] && col.fieldname === "category"))) {
				if (draft[itemField] && kind === "Item" && !itemOptions(table, kind, draft).some(function (o) { return o.value === draft[itemField]; })) draft[itemField] = "";
				readPickers(table, draft, m.body);
				paintForm();
				if ((GROUP_FIRST[table] || SHEET_TABLES[table]) && draft[col.fieldname]) focusItem();
				return;
			}
			/* An Item chosen sets its group, where it is one of the category's. */
			if (layout && col.fieldname === itemField && draft[col.fieldname]) {
				var chosen = allItems().find(function (o) { return o.value === draft[col.fieldname]; });
				var groups = ((pkg.choices.item_groups || {})[pkg.category[table]] || []).map(function (g) { return g.value; });
				var groupBox = m.body.querySelector('[name="item_group"]');
				if (chosen && groupBox && groups.indexOf(chosen.group) !== -1) { draft.item_group = chosen.group; groupBox.value = chosen.group; }
			}
			var fill = pkg.item_text[table];
			if (fill && col.fieldname === fill[0] && draft[fill[0]]) {
				var item = allItems().find(function (i) { return i.value === draft[fill[0]]; });
				if (item && item.text) { draft[fill[1]] = item.text; var t = m.body.querySelector('[name="' + fill[1] + '"]'); if (t) t.value = item.text; }
			}
			if (SHEET_TABLES[table]) {
				/* The UOM and Category follow the Item chosen (the UOM stays the user's to change
				   after), and the amount is the quantity at the rate. */
				if (col.fieldname === "item") {
					var chosen = pkg.choices.Item.find(function (i) { return i.value === draft.item; });
					if (chosen) { draft.uom = chosen.uom || draft.uom; draft.category = chosen.group; }
					readPickers(table, draft, m.body);
					paintForm();
					/* Its description, from the Item. */
					if (draft.item) {
						var asked = draft.item;
						call("item_description", { item: asked }).then(function (text) {
							if (draft.item !== asked || !text) return;
							draft.description = text;
							var box = m.body.querySelector('[name="description"]');
							if (box) box.value = text;
						}).catch(function () { /* left to fill by hand */ });
					}
					return;
				}
				if (col.fieldname === "qty" || col.fieldname === "rate") {
					draft.amount = (Number(draft.qty) || 0) * (Number(draft.rate) || 0);
					var ro = m.body.querySelector('[data-ro="amount"]');
					if (ro) ro.textContent = money(draft.amount);
				}
			}
			/* A panel's Rate per Panel is its Wattage x Wattage Rate (solar_package.total_the_panels). */
			if (table === "modules" && !part && (col.fieldname === "module_wattage" || col.fieldname === "wattage_rate")) {
				if (Number(draft.wattage_rate)) draft.rate = (Number(draft.module_wattage) || 0) * Number(draft.wattage_rate);
				draft.amount = (Number(draft.rate) || 0) * (Number(draft.module_count) || 0);
				var rateBox = m.body.querySelector('[data-ro="rate"]'), totalBox = m.body.querySelector('[data-ro="amount"]');
				if (rateBox) rateBox.textContent = money(draft.rate);
				if (totalBox) totalBox.textContent = money(draft.amount);
			}
			/* A pricing row's cost follows its panel, inverter, battery and margin. */
			if (table === "pricing_options") {
				draft.cost = pricingCost(draft);
				var costBox = m.body.querySelector('[data-ro="cost"]'), parts = m.body.querySelector("[data-breakdown]");
				if (costBox) costBox.textContent = money(draft.cost);
				if (parts) parts.innerHTML = breakdownRows(draft);
			}
			var by = ROW_AMOUNT[table];
			if (by && by.indexOf(col.fieldname) !== -1) {
				draft.amount = (Number(draft[by[0]]) || 0) * (Number(draft[by[1]]) || 0);
				var shown = m.body.querySelector('[data-ro="amount"]');
				if (shown) shown.textContent = money(draft.amount);
			}
			if (REPAINT[col.fieldname]) { readPickers(table, draft, m.body); paintForm(); }
		});
		m.body.addEventListener("submit", function (e) {
			e.preventDefault();
			spec.columns.forEach(function (c) {
				var el = m.body.querySelector('[name="' + c.fieldname + '"]');
				if (el && !c.read_only) draft[c.fieldname] = readValue(el, c);
			});
			var wrong = readPickers(table, draft, m.body);
			if (wrong) { m.status(wrong, "error"); return; }
			if (SHEET_TABLES[table]) draft.amount = (Number(draft.qty) || 0) * (Number(draft.rate) || 0);
			if (table === "pricing_options") draft.cost = pricingCost(draft);
			if (table === "modules" && !part && Number(draft.wattage_rate)) draft.rate = (Number(draft.module_wattage) || 0) * Number(draft.wattage_rate);
			if (ROW_AMOUNT[table]) draft.amount = (Number(draft[ROW_AMOUNT[table][0]]) || 0) * (Number(draft[ROW_AMOUNT[table][1]]) || 0);
			var missing = spec.columns.filter(function (c) { return c.reqd && !c.read_only && (draft[c.fieldname] === "" || draft[c.fieldname] == null); });
			if (missing.length) { m.status("Fill " + missing.map(function (c) { return c.label; }).join(", ") + ".", "error"); return; }
			/* A Bundle or BOM: replaced by its items, each priced at its selling price. */
			if (KIND_TABLES[table] && !part && kind !== "Item") {
				Object.keys(KIT_FIELD).forEach(function (f) { delete draft[f]; });
				m.status("Opening it into its items…");
				callPath(KITS + "expand_row", { table: table, row: JSON.stringify(draft) }).then(place)
					.catch(function (err) { m.status(err.message, "error"); });
				return;
			}
			place([draft]);
		});
		/* The row - or the rows a bundle opened into - in its place; a kit it replaces goes whole. */
		function place(list) {
			var old = adding ? null : rows[index];
			if (old && OPTION_KITS[table] && !isPart(old) && old.bundle_key && list[0].bundle_key !== old.bundle_key) {
				kitOf(rows, old).forEach(function (r) { if (r !== old) rows.splice(rows.indexOf(r), 1); });
			}
			if (adding) Array.prototype.push.apply(rows, list);
			else rows.splice.apply(rows, [rows.indexOf(old), 1].concat(list));
			keepDefaults(table, list[0], adding);
			if (table === "expenses") totalExpenses();
			if (table === "pricing_options") packageCostFromPricing();
			totalPackageCost();
			m.close();
			touch();
			paint();
			if (list.length > 1) setStatus(statusEl, "Replaced by its " + list.length + " items, each at its selling price. Save the package to keep them.", "ok");
		}
	}

	/* ------------------------------------------------------------------ "depends on" picker */
	/* The desk's Select Items dialog, here inside the row's form: a Materials, Structure or
	   Expenses row, Depends on ticked, is taken only where one of the package's Items ticked
	   under it is used (package_bom_tables.applies); unticked, always. */
	var PICKED = { "material_bom.depends_on": 1, "structure_boms.depends_on": 1, "expenses.depends_on": 1 };
	/* The package's own Items, as its other tabs name them now: what a row may depend on. */
	var OWN_ITEMS = [["modules", "module_item", "Solar Panel"], ["inverters", "inverter_item", "Inverter"],
		["batteries", "battery_item", "Battery"], ["system_items", "item", "Balance"], ["kseb_expenses", "particulars", "KSEB"],
		["mounting_expenses", "item", "Mounting"], ["installation_expenses", "item", "Installation"]];
	function ownItems() {
		var seen = {}, out = [];
		OWN_ITEMS.forEach(function (t) {
			((pkg.tables[t[0]] && pkg.tables[t[0]].rows) || []).forEach(function (r) {
				var item = r[t[1]];
				if (item && !seen[item]) { seen[item] = 1; out.push({ value: item, label: labelOf("Item", item), note: t[2] }); }
			});
		});
		return out;
	}
	function checks(name, options) {
		return '<div class="a3s-pkg__checks">' + options.map(function (o) {
			return '<label class="a3s-check"><input type="checkbox" name="' + name + '" value="' + esc(o.value) + '"' + (o.checked ? " checked" : "") + "><span>" + esc(o.label) +
				(o.note ? ' <span class="a3s-pkg__checknote">' + esc(o.note) + "</span>" : "") + "</span></label>";
		}).join("") + "</div>";
	}
	function pickerHtml(table, draft) {
		if (table === "pricing_options") return '<div class="a3s-pkg__breakdown" data-breakdown>' + breakdownRows(draft) + "</div>";
		if (!SHEET_TABLES[table]) return "";
		var chosen = split(draft.depends_on, true), own = ownItems();
		var options = own.concat(chosen.filter(function (c) { return !own.some(function (o) { return o.value === c; }); })
			.map(function (c) { return { value: c, label: labelOf("Item", c), note: "No longer on the package" }; }))
			.map(function (o) { return Object.assign({ checked: chosen.indexOf(o.value) !== -1 }, o); });
		return '<fieldset class="a3s-pkg__picker a3s-pkg__depends">' +
			'<label class="a3s-check"><input type="checkbox" name="pick-depends"' + (chosen.length ? " checked" : "") + "><span>Depends on</span></label>" +
			'<div data-depends' + (chosen.length ? "" : " hidden") + ">" +
			(options.length ? '<p class="a3s-field__hint">Taken only with a ticked item.</p>' + checks("pick-depends_on", options) :
				'<p class="a3s-field__hint">Give the package\'s other tabs their items first.</p>') +
			"</div></fieldset>";
	}
	/* The ticks into the row's Depends On, as the server keeps it; what is wrong, if anything. */
	function readPickers(table, draft, body) {
		var box = SHEET_TABLES[table] && body.querySelector('[name="pick-depends"]');
		if (!box) return "";
		var ticked = Array.prototype.filter.call(body.querySelectorAll('[name="pick-depends_on"]'), function (el) { return el.checked; })
			.map(function (el) { return el.value; });
		if (box.checked && !ticked.length) return "Tick what the row depends on, or untick Depends on.";
		draft.depends_on = box.checked ? ticked.join("\n") : "";
		return "";
	}
	/* One default among the panels and the inverters, one per type among the rest: ticking
	   one clears the others, and the first of its kind is the default (solar_package.js). */
	function keepDefaults(table, row, added) {
		var rows = pkg.tables[table].rows;
		if (ONE_DEFAULT[table]) {
			if (added && rows.filter(function (r) { return !isPart(r); }).length === 1) row.is_default = 1;
			if (row.is_default) rows.forEach(function (r) { if (r !== row) r.is_default = 0; });
		}
		if (table === "system_items" && row.system_type) {
			var same = rows.filter(function (r) { return r !== row && r.system_type === row.system_type; });
			if (!same.length) row.is_default = 1;
			if (row.is_default) same.forEach(function (r) { r.is_default = 0; });
		}
	}
	panels.addEventListener("click", function (e) {
		var go = e.target.closest("[data-goto-tab]");
		if (go) { active = go.dataset.gotoTab; paint(); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
		var section = e.target.closest("[data-table]");
		if (!section) return;
		var table = section.dataset.table;
		if (e.target.closest("[data-add-row]")) return rowForm(table, null);
		var sheet = e.target.closest("[data-sheet]");
		if (sheet) return sheet.dataset.sheet === "download" ? downloadSheet(table) : uploadSheet(table);
		var tr = e.target.closest("tr[data-row]");
		if (!tr) return;
		var i = Number(tr.dataset.row);
		if (e.target.closest("[data-edit-row]")) return rowForm(table, i);
		if (e.target.closest("[data-remove-row]")) {
			/* A bundle's or a BOM's items go with it; a kit's option with its parts. */
			var rows = pkg.tables[table].rows, n = 1;
			while (i + n < rows.length && isComponent(rows[i + n])) n++;
			var gone = OPTION_KITS[table] && !isPart(rows[i]) && rows[i].bundle_key ? kitOf(rows, rows[i]) : rows.slice(i, i + n);
			gone.forEach(function (r) { rows.splice(rows.indexOf(r), 1); });
			if (table === "expenses") totalExpenses();
			if (table === "pricing_options") packageCostFromPricing();
			totalPackageCost();
			touch();
			paint();
		}
	});

	/* ------------------------------------------------------------------ Excel */
	/* Download Excel: the table as it stands here, saved or not, in the columns Upload Excel
	   reads; headings alone for an empty table, as a template (package_bom_tables.download_sheet). */
	function downloadSheet(table) {
		/* The rows typed or uploaded here: the copied rows and the items listed under a bundle or
		   BOM are worked out on save, and would come back as rows of their own. */
		var own = pkg.tables[table].rows.filter(isOwn);
		var body = new URLSearchParams({ table: table, rows: JSON.stringify(own), package: pkg.name || "" });
		fetch("/api/method/" + SHEETS + "download_sheet", {
			method: "POST", credentials: "same-origin", headers: { "X-Frappe-CSRF-Token": csrf }, body: body
		}).then(function (r) {
			if (!r.ok) {
				return r.json().catch(function () { return {}; }).then(function (b) { throw new Error(serverMessage(b) || "The sheet could not be made. Try again."); });
			}
			var named = /filename="?([^";]+)"?/.exec(r.headers.get("Content-Disposition") || "");
			return r.blob().then(function (blob) { return { blob: blob, name: named ? decodeURIComponent(named[1]) : table + ".xlsx" }; });
		}).then(function (file) {
			var a = document.createElement("a");
			a.href = URL.createObjectURL(file.blob);
			a.download = file.name;
			document.body.appendChild(a);
			a.click();
			a.remove();
			setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
		}).catch(function (err) { setStatus(statusEl, err.message, "error"); });
	}
	/* Upload Excel: the sheet is read on the server, which finds or makes each Item, and its rows
	   replace the table here, to be saved with the package (package_bom_tables.read_sheet). */
	function uploadSheet(table) {
		var spec = pkg.tables[table];
		var own = spec.rows.filter(isOwn).length;
		if (own && !window.confirm("The sheet's rows replace the " + own + " rows typed into the " + spec.label + ". Go on?")) return;
		var picker = document.createElement("input");
		picker.type = "file";
		picker.accept = ".xlsx,.csv";
		picker.addEventListener("change", function () {
			var file = picker.files[0];
			if (!file) return;
			var reader = new FileReader();
			reader.onload = function () {
				setStatus(statusEl, "Reading the sheet…");
				callPath(SHEETS + "read_sheet", {
					content: reader.result, filename: file.name, table: table, company: company(),
					items: JSON.stringify(ownItems().map(function (o) { return o.value; }))
				}).then(function (res) {
					/* Items the sheet made are choices from now on. */
					res.rows.forEach(function (r) {
						if (!pkg.choices.Item.some(function (i) { return i.value === r.item; })) pkg.choices.Item.push({ value: r.item, label: r.item, group: r.category, uom: r.uom });
					});
					spec.rows = res.rows;
					if (table === "expenses") totalExpenses();
					touch();
					paint();
					setStatus(statusEl, res.rows.length + " rows read from the sheet. Save the package to keep them." +
						(res.created.length ? " New Items made: " + res.created.join(", ") + "." : ""), "ok");
				}).catch(function (err) { setStatus(statusEl, err.message, "error"); });
			};
			reader.readAsDataURL(file);
		});
		picker.click();
	}

	/* ------------------------------------------------------------------ save */
	function load(data, message) {
		pkg = data;
		dirty = false;
		document.querySelector("[data-package-title]").textContent = pkg.title;
		document.querySelector("[data-package-sub]").textContent = pkg.name ? pkg.name + " · " + (pkg.values.specification_code || "") : "";
		if (pkg.name && window.history.replaceState) window.history.replaceState(null, "", "/a3solaportal/packages/edit?name=" + encodeURIComponent(pkg.name));
		paint();
		paintHead();
		if (message) setStatus(statusEl, message, "ok");
	}
	form.addEventListener("submit", function (e) {
		e.preventDefault();
		/* A package is saved with a Pricing Options row at least (Solar Package.require_pricing_options). */
		if (pkg.tables.pricing_options && !pkg.tables.pricing_options.rows.length) {
			active = "tab_pricing";
			paint();
			setStatus(statusEl, "Add a Pricing Options row before saving: a panel, an inverter and the cost the package is offered at.", "error");
			return;
		}
		var btn = form.querySelector("[data-save]");
		btn.disabled = true;
		setStatus(statusEl, "Saving…");
		var tables = {};
		Object.keys(pkg.tables).forEach(function (f) { tables[f] = pkg.tables[f].rows; });
		call("save_package", { data: { name: pkg.name, modified: pkg.modified, values: pkg.values, tables: tables } }).then(function (saved) {
			btn.disabled = false;
			load(saved, "Saved. Prices, KSEB and the other worked-out rows are updated.");
		}).catch(function (err) {
			btn.disabled = false;
			setStatus(statusEl, err.message, "error");
		});
	});
	window.addEventListener("beforeunload", function (e) { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

	/* ------------------------------------------------------------------ Item and BOM */
	function paintHead() {
		if (!pkg.name) { headActs.innerHTML = ""; return; }
		var v = pkg.values, html = "";
		if (!v.item) html += '<button type="button" class="a3s-btn a3s-btn--secondary" data-do="create_item">' + icon("box") + "<span>Create Item</span></button>";
		else if (!v.bom) html += '<button type="button" class="a3s-btn a3s-btn--secondary" data-do="create_bom">' + icon("stack") + "<span>Create BOM</span></button>";
		else html += '<button type="button" class="a3s-btn a3s-btn--secondary" data-do="update_bom">' + icon("stack") + "<span>Update BOM</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-do="view_bom">' + icon("eye") + "<span>View BOM</span></button>";
		html += '<a class="a3s-btn a3s-btn--ghost" href="/a3solaportal/packages/edit?copy=' + encodeURIComponent(pkg.name) + '">' + icon("stack") + "<span>Duplicate</span></a>";
		headActs.innerHTML = html;
	}
	headActs.addEventListener("click", function (e) {
		var b = e.target.closest("[data-do]");
		if (!b) return;
		var what = b.dataset.do;
		if (what === "view_bom") return viewBom();
		if (dirty) { setStatus(statusEl, "Save the package first: the Item and BOM are made from it as saved.", "error"); return; }
		b.disabled = true;
		setStatus(statusEl, what === "create_item" ? "Making the Item…" : "Making the BOM…");
		call(what, { name: pkg.name }).then(function (r) {
			var res = r.result || {}, msg;
			if (what === "create_item") msg = "Item " + (res.item || pkg.values.item || "") + " created" + (res.bom ? " with BOM " + res.bom : "") + ". Now create its BOM.";
			else if (what === "create_bom") msg = "BOM " + res.bom + " created with " + res.lines + " raw materials.";
			else if (res.unchanged) msg = "BOM " + res.bom + " already matches the package.";
			else if (res.previous) msg = res.bom + " replaces " + res.previous + ", which is now inactive: " + res.changes.join("; ") + ".";
			else msg = "BOM " + res.bom + " created.";
			load(r.package, msg);
		}).catch(function (err) { b.disabled = false; setStatus(statusEl, err.message, "error"); });
	});
	function viewBom() {
		var m = modal("BOM", "Loading…");
		call("bom", { name: pkg.name }).then(function (b) {
			m.el.querySelector(".a3s-users__sub").innerHTML = esc(b.name) + " &middot; " + esc(b.item_name || b.item) +
				(b.is_default ? ' <span class="a3s-badge a3s-badge--converted">Default</span>' : "") + (b.is_active ? "" : ' <span class="a3s-badge a3s-badge--lost-quotation">Inactive</span>');
			m.body.innerHTML = '<div class="a3s-tablewrap"><table class="a3s-table"><thead><tr><th>Raw material</th><th class="a3s-table__num">Qty</th><th>UOM</th><th class="a3s-table__num">Rate</th><th class="a3s-table__num">Amount</th></tr></thead><tbody>' +
				b.rows.map(function (r) {
					return '<tr><td data-label="Raw material">' + esc(r.item_name || r.item_code) + (r.item_name && r.item_name !== r.item_code ? '<span class="a3s-table__meta">' + esc(r.item_code) + "</span>" : "") + "</td>" +
						'<td data-label="Qty" class="a3s-table__num">' + esc(r.qty) + '</td><td data-label="UOM">' + esc(r.uom) + "</td>" +
						'<td data-label="Rate" class="a3s-table__num">' + money(r.rate) + '</td><td data-label="Amount" class="a3s-table__num">' + money(r.amount) + "</td></tr>";
				}).join("") + '</tbody></table></div><p class="a3s-pkg__total">Total ' + money(b.total) + "</p>";
		}).catch(function (err) { m.status(err.message, "error"); });
	}

	paint();
	paintHead();
})();
