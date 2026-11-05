/* One Solar Package, edited whole: its details and every table, laid out as the desk form lays
   them out - its tabs, sections and columns - and its Item and BOM (a3_sola.api.portal_packages).
   The page keeps the package as the server sent it, changes it here, and posts it whole on Save;
   the server's rules decide the rest and its answer is painted back - computed KSEB rows,
   totals and the like. */
(function () {
	"use strict";

	var API = "a3_sola.api.portal_packages.";
	/* The BOM tab's tables, which come from Excel as often as they are typed (solar_package.js). */
	var SHEETS = "a3_sola.api.package_bom_tables.";
	var SHEET_TABLES = { material_bom: 1, structure_boms: 1, expenses: 1 };
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
	var ROW_SOURCES = {
		"inverters.panel_specification": ["modules", function (r) { return r.module_specification; }]
	};
	/* The Item field of each table (the expense tables' own, besides the spec rows'). */
	var ITEM_FIELD = { kseb_expenses: "particulars", mounting_expenses: "item", installation_expenses: "item", components: "item" };
	Object.keys(pkg.item_text).forEach(function (t) { ITEM_FIELD[t] = pkg.item_text[t][0]; });
	var ONE_DEFAULT = { modules: 1, inverters: 1 };

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
	/* "Depends on" lists: the inverters one per line, roof types and capacities by commas. */
	function split(value, byLine) {
		return String(value || "").split(byLine ? "\n" : /[,\n]/).map(function (s) { return s.trim(); }).filter(Boolean);
	}
	/* The Expenses' total, as the rows change (the server totals it again on save). */
	function totalExpenses() {
		if (!pkg.tables.expenses) return;
		pkg.values.total_expenses = pkg.tables.expenses.rows.reduce(function (sum, r) { return sum + (Number(r.amount) || 0); }, 0);
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
		var hint = col.description ? '<p class="a3s-field__hint">' + esc(col.description) + "</p>" : "";
		if (col.read_only) {
			var shown = col.type === "Link" ? labelOf(col.options, value, opts.table, col.fieldname) :
				col.type === "Currency" ? (value != null && value !== "" ? money(value) : "") : col.type === "Check" ? (value ? "Yes" : "No") : value;
			return '<div class="a3s-field"><span class="a3s-pkg__rolabel">' + esc(col.label) + '</span><p class="a3s-pkg__ro" data-ro="' + esc(col.fieldname) + '">' +
				(shown === "" || shown == null ? '<span class="a3s-table__muted">Not set</span>' : esc(shown)) + "</p>" + hint + "</div>";
		}
		if (col.type === "Check") {
			return '<label class="a3s-check"><input type="checkbox"' + name + (value ? " checked" : "") + "><span>" + esc(col.label) + "</span></label>";
		}
		if (col.type === "Small Text" || col.type === "Text") {
			return '<div class="a3s-field a3s-field--wide">' + label + '<textarea rows="3"' + name + ">" + esc(value) + "</textarea>" + hint + "</div>";
		}
		if (col.type === "Select" || col.type === "Link") {
			var options = ROW_SOURCES[opts.table + "." + col.fieldname] ? rowOptions(ROW_SOURCES[opts.table + "." + col.fieldname]) :
				col.type === "Link" ? linkOptions(opts.table, col, opts.row || pkg.values) :
				(col.options || []).filter(function (o) { return o !== ""; }).map(function (o) { return { value: o, label: o }; });
			var found = !value || options.some(function (o) { return o.value === value; });
			var html = '<option value="">' + (col.type === "Link" ? "Choose…" : "—") + "</option>" +
				(found ? "" : '<option value="' + esc(value) + '" selected>' + esc(labelOf(col.options, value, opts.table, col.fieldname)) + " (not offered)</option>") +
				options.map(function (o) { return '<option value="' + esc(o.value) + '"' + (o.value === value ? " selected" : "") + ">" + esc(o.label) + "</option>"; }).join("");
			var combo = options.length > 12;
			return '<div class="a3s-field' + (combo ? " a3s-combo a3s-combo--field" : "") + '"' + (combo ? " data-combo" : "") + ">" + label + "<select" + name + ">" + html + "</select>" + hint + "</div>";
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
		return pkg.tabs.filter(function (t) { return t.key !== "batteries" || hasBatteries(); });
	}
	function paintTabs() {
		tabsEl.innerHTML = visibleTabs().map(function (t) {
			var n = t.tables.reduce(function (sum, f) { return sum + (pkg.tables[f].rows || []).length; }, 0);
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
	   tables and HTML in the desk's order. A section that opens with a table of its own name
	   needs no title of its own. */
	function sectionHtml(tab, s) {
		var first = s.columns[0][0];
		var titled = s.label && !(first.table && pkg.tables[first.table].label === s.label);
		var body = s.columns.length > 1
			? '<div class="a3s-pkg__cols">' + s.columns.map(function (c) { return '<div class="a3s-pkg__stack">' + entriesHtml(tab, c, false) + "</div>"; }).join("") + "</div>"
			: entriesHtml(tab, s.columns[0], true);
		return '<section class="a3s-pkg__section">' + (titled ? '<h3 class="a3s-pkg__sectiontitle">' + esc(s.label) + "</h3>" : "") + body + "</section>";
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
				var col = tab.fields.find(function (c) { return c.fieldname === e.field; });
				if (col.fieldname === "item" || col.fieldname === "bom") col = Object.assign({}, col, { read_only: 1 });
				fields.push(input(col, pkg.values[col.fieldname]));
				return;
			}
			flush();
			if (e.table) {
				html += tableHtml(e.table);
				if (e.table === "batteries" && !hasBatteries()) html += '<p class="a3s-field__hint">Batteries are for Off-Grid and Hybrid systems.</p>';
			} else if (e.html === "payment_terms_preview") {
				html += '<div class="a3s-pkg__terms" data-terms></div>';
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
		var v = row[col.fieldname];
		if (col.fieldname === "inverters" && spec.fieldname === "material_bom") return dependsCell(split(v, true).map(function (i) { return labelOf("Item", i); }));
		if (col.fieldname === "roof_types") return dependsCell(split(v).map(function (r) { return labelOf("Roof Type", r); }));
		if (col.fieldname === "panel_capacities") return dependsCell(split(v).map(function (kw) { return kw + " kW"; }));
		if (col.type === "Check") return v ? '<span class="a3s-pkg__tick" aria-label="Yes">' + icon("check") + "</span>" : "";
		if (v === "" || v == null) return '<span class="a3s-table__muted">—</span>';
		if (col.type === "Link") return esc(labelOf(col.options, v, spec.fieldname, col.fieldname));
		if (col.type === "Currency") return money(v);
		if (isNum(col.type)) return esc(Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 }));
		return esc(v);
	}
	/* Saying nothing means every one (package_bom_tables.applies). */
	function dependsCell(names) {
		return names.length ? esc(names.join(", ")) : '<span class="a3s-table__muted">All</span>';
	}
	function tableHtml(f) {
		var spec = pkg.tables[f], cols = listColumns(spec), rows = spec.rows || [];
		var sheet = SHEET_TABLES[f] ?
			'<button type="button" class="a3s-btn a3s-btn--ghost a3s-btn--sm" data-sheet="download">' + icon("download") + "<span>Download Excel</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost a3s-btn--sm" data-sheet="upload">' + icon("upload") + "<span>Upload Excel</span></button>" : "";
		return '<section class="a3s-pkg__table" data-table="' + f + '">' +
			'<div class="a3s-pkg__tablehead"><h3 class="a3s-pkg__tabletitle">' + esc(spec.label) + ' <span class="a3s-pkg__count">' + rows.length + "</span></h3>" +
			'<div class="a3s-pkg__tableacts">' + sheet +
			'<button type="button" class="a3s-btn a3s-btn--secondary a3s-btn--sm" data-add-row><span>+ Add row</span></button></div></div>' +
			(rows.length ? '<div class="a3s-tablewrap"><table class="a3s-table a3s-pkg__rows"><thead><tr>' +
				cols.map(function (c) { return "<th" + (isNum(c.type) ? ' class="a3s-table__num"' : "") + ">" + esc(c.label) + "</th>"; }).join("") +
				'<th><span class="a3s-sr-only">Actions</span></th></tr></thead><tbody>' +
				rows.map(function (row, i) {
					return '<tr data-row="' + i + '">' + cols.map(function (c) {
						return '<td data-label="' + esc(c.label) + '"' + (isNum(c.type) ? ' class="a3s-table__num"' : "") + ">" + cell(spec, c, row) + "</td>";
					}).join("") + '<td><div class="a3s-users__actions">' +
						'<button type="button" class="a3s-icon-btn a3s-icon-btn--framed" data-edit-row title="Edit" aria-label="Edit row ' + (i + 1) + '">' + icon("edit") + "</button>" +
						'<button type="button" class="a3s-icon-btn a3s-icon-btn--danger" data-remove-row title="Remove" aria-label="Remove row ' + (i + 1) + '">' + icon("trash") + "</button>" +
						"</div></td></tr>";
				}).join("") + "</tbody></table></div>" :
				'<p class="a3s-pkg__none">No rows yet.</p>') +
			"</section>";
	}
	function paintTerms() {
		var el = panels.querySelector("[data-terms]");
		if (!el) return;
		var names = [pkg.values.payment_terms, pkg.values.financed_payment_terms].filter(function (n, i, all) { return n && all.indexOf(n) === i; });
		if (!names.length) { el.innerHTML = '<p class="a3s-field__hint">Choose the payment terms to see their milestones.</p>'; return; }
		el.innerHTML = names.map(function (n) {
			var t = pkg.choices["Billing Milestone Template"].find(function (x) { return x.value === n; }) || { label: n, milestones: [] };
			return '<div class="a3s-pkg__term"><p class="a3s-pkg__termname">' + esc(t.label) + "</p>" +
				'<table class="a3s-table a3s-pkg__termtable"><thead><tr><th>Milestone</th><th>When</th><th class="a3s-table__num">%</th></tr></thead><tbody>' +
				t.milestones.map(function (m) {
					return '<tr><td data-label="Milestone">' + esc(m.name) + (m.advance ? ' <span class="a3s-badge a3s-badge--quotation">Advance</span>' : "") + "</td>" +
						'<td data-label="When">' + esc(m.when) + '</td><td data-label="%" class="a3s-table__num">' + esc(m.percent) + "%</td></tr>";
				}).join("") + "</tbody></table></div>";
		}).join("");
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
		if (col.fieldname === "system_type") paintTabs();
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
		function paintForm() {
			m.body.innerHTML = '<form class="a3s-modal__form" novalidate><div class="a3s-form__grid">' +
				spec.columns.filter(function (c) { return !PICKED[table + "." + c.fieldname]; })
					.map(function (c) { return input(c, draft[c.fieldname], { table: table, row: draft, prefix: "r-" }); }).join("") +
				pickerHtml(table, draft) +
				'</div><div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary"><span>' + (adding ? "Add row" : "Done") + "</span></button>" +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
			if (window.a3sCombo) window.a3sCombo.wireAll(m.body);
		}
		paintForm();
		/* A choice that narrows another (make and phase the model, variant the make, type the
		   item) repaints the form; an Item fills the row's specification text. */
		var REPAINT = { inverter_make: 1, inverter_phase: 1, battery_variant: 1, system_type: 1 };
		m.body.addEventListener("change", function (e) {
			var el = e.target, col = spec.columns.find(function (c) { return c.fieldname === el.name; });
			if (!col) return;
			draft[col.fieldname] = readValue(el, col);
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
					return;
				}
				if (col.fieldname === "qty" || col.fieldname === "rate") {
					draft.amount = (Number(draft.qty) || 0) * (Number(draft.rate) || 0);
					var ro = m.body.querySelector('[data-ro="amount"]');
					if (ro) ro.textContent = money(draft.amount);
				}
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
			var missing = spec.columns.filter(function (c) { return c.reqd && !c.read_only && (draft[c.fieldname] === "" || draft[c.fieldname] == null); });
			if (missing.length) { m.status("Fill " + missing.map(function (c) { return c.label; }).join(", ") + ".", "error"); return; }
			if (adding) rows.push(draft); else rows[index] = draft;
			keepDefaults(table, draft, adding);
			if (table === "expenses") totalExpenses();
			m.close();
			touch();
			paint();
		});
	}

	/* ------------------------------------------------------------------ "depends on" pickers */
	/* The desk's Select Inverters and Select Roof / kW dialogs, here inside the row's form: a
	   Material BOM row is needed with the inverter options ticked, a Structure BOM row with the
	   roof types and system capacities ticked; nothing ticked is every one. */
	var PICKED = { "material_bom.inverters": 1, "structure_boms.roof_types": 1, "structure_boms.panel_capacities": 1 };
	function checks(name, options) {
		return '<div class="a3s-pkg__checks">' + options.map(function (o) {
			return '<label class="a3s-check"><input type="checkbox" name="' + name + '" value="' + esc(o.value) + '"' + (o.checked ? " checked" : "") + "><span>" + esc(o.label) + "</span></label>";
		}).join("") + "</div>";
	}
	function pickerHtml(table, draft) {
		if (table === "material_bom") {
			var inverters = pkg.tables.inverters.rows, chosen = split(draft.inverters, true);
			var quoted = inverters.find(function (r) { return r.is_default; });
			var offered = inverters.map(function (r) { return r.inverter_item; }).filter(function (v, i, all) { return v && all.indexOf(v) === i; });
			var options = offered.concat(chosen.filter(function (c) { return offered.indexOf(c) === -1; })).map(function (item) {
				return { value: item, checked: chosen.indexOf(item) !== -1, label: labelOf("Item", item) +
					(offered.indexOf(item) === -1 ? " (no longer an option)" : quoted && quoted.inverter_item === item ? " (default)" : "") };
			});
			return '<fieldset class="a3s-pkg__picker"><legend>Depends on Inverter</legend>' +
				(options.length ? '<p class="a3s-field__hint">None ticked: needed with every inverter.</p>' + checks("pick-inverters", options) :
					'<p class="a3s-field__hint">Give the package\'s inverter options their Items first; until then the row is needed with every inverter.</p>') +
				"</fieldset>";
		}
		if (table === "structure_boms") {
			var roofs = split(draft.roof_types), kws = split(draft.panel_capacities).map(Number);
			var all = pkg.choices.capacities.map(Number).concat(kws).filter(function (v, i, a) { return v > 0 && a.indexOf(v) === i; }).sort(function (a, b) { return a - b; });
			return '<fieldset class="a3s-pkg__picker"><legend>Depends on Roof Type</legend><p class="a3s-field__hint">None ticked: every roof type.</p>' +
				checks("pick-roof_types", linkOptions(null, { fieldname: "roof_type", options: "Roof Type" }, pkg.values).map(function (r) {
					return { value: r.value, label: r.label, checked: roofs.indexOf(r.value) !== -1 };
				})) + "</fieldset>" +
				'<fieldset class="a3s-pkg__picker"><legend>Panel Capacity (kW)</legend><p class="a3s-field__hint">The system\'s capacity. None ticked: every capacity.</p>' +
				checks("pick-panel_capacities", all.map(function (kw) { return { value: String(kw), label: kw + " kW", checked: kws.indexOf(kw) !== -1 }; })) +
				'<div class="a3s-field a3s-pkg__other"><label for="r-other-kw">Other capacities (kW)</label><input id="r-other-kw" name="pick-other_kw" inputmode="decimal" placeholder="Separated by commas, e.g. 6, 7.5"></div>' +
				"</fieldset>";
		}
		return "";
	}
	/* The ticks into the row's fields, as the server keeps them; what is wrong, if anything. */
	function readPickers(table, draft, body) {
		if (table !== "material_bom" && table !== "structure_boms") return "";
		function ticked(name) {
			return Array.prototype.filter.call(body.querySelectorAll('[name="' + name + '"]'), function (el) { return el.checked; }).map(function (el) { return el.value; });
		}
		if (table === "material_bom") {
			if (body.querySelector('[name="pick-inverters"]')) draft.inverters = ticked("pick-inverters").join("\n");
			return "";
		}
		draft.roof_types = ticked("pick-roof_types").join(", ");
		var other = body.querySelector('[name="pick-other_kw"]');
		var others = split(other && other.value);
		if (others.some(function (kw) { return !(Number(kw) > 0); })) return "Other capacities are numbers of kW, such as 6 or 7.5.";
		draft.panel_capacities = ticked("pick-panel_capacities").concat(others).map(Number)
			.filter(function (v, i, a) { return a.indexOf(v) === i; }).sort(function (a, b) { return a - b; }).join(", ");
		return "";
	}
	/* One default among the panels and the inverters, one per type among the rest: ticking
	   one clears the others, and the first of its kind is the default (solar_package.js). */
	function keepDefaults(table, row, added) {
		var rows = pkg.tables[table].rows;
		if (ONE_DEFAULT[table]) {
			if (added && rows.length === 1) row.is_default = 1;
			if (row.is_default) rows.forEach(function (r) { if (r !== row) r.is_default = 0; });
		}
		if (table === "system_items" && row.system_type) {
			var same = rows.filter(function (r) { return r !== row && r.system_type === row.system_type; });
			if (!same.length) row.is_default = 1;
			if (row.is_default) same.forEach(function (r) { r.is_default = 0; });
		}
	}
	panels.addEventListener("click", function (e) {
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
			pkg.tables[table].rows.splice(i, 1);
			if (table === "expenses") totalExpenses();
			touch();
			paint();
		}
	});

	/* ------------------------------------------------------------------ Excel */
	/* Download Excel: the table as it stands here, saved or not, in the columns Upload Excel
	   reads; headings alone for an empty table, as a template (package_bom_tables.download_sheet). */
	function downloadSheet(table) {
		var body = new URLSearchParams({ table: table, rows: JSON.stringify(pkg.tables[table].rows), package: pkg.name || "" });
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
		if (spec.rows.length && !window.confirm("The sheet's rows replace the " + spec.rows.length + " rows of the " + spec.label + ". Go on?")) return;
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
					inverters: pkg.tables.inverters.rows.map(function (r) { return { inverter_item: r.inverter_item, inverter_specification: r.inverter_specification }; })
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
