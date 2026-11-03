/* One Solar Package, edited whole: its details and every table, in the desk form's tabs, and
   its Item and BOM (a3_sola.api.portal_packages). The page keeps the package as the server
   sent it, changes it here, and posts it whole on Save; the server's rules decide the rest
   and its answer is painted back - computed KSEB rows, totals and the like. */
(function () {
	"use strict";

	var API = "a3_sola.api.portal_packages.";
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
	var LIST_COLUMNS = 6;

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
	function call(method, args) {
		return fetch("/api/method/" + API + method, {
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
		var list = (table && ITEM_FIELD[table] === field) ? allItems() : (pkg.choices[doctype] || []);
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
				col.type === "Currency" ? (value ? money(value) : "") : col.type === "Check" ? (value ? "Yes" : "No") : value;
			return '<div class="a3s-field"><span class="a3s-pkg__rolabel">' + esc(col.label) + '</span><p class="a3s-pkg__ro">' +
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
		var html = "";
		if (tab.fields.length) {
			html += '<div class="a3s-form__grid a3s-pkg__fields">' + tab.fields.map(function (col) {
				if (col.fieldname === "item" || col.fieldname === "bom") col = Object.assign({}, col, { read_only: 1 });
				return input(col, pkg.values[col.fieldname]);
			}).join("") + "</div>";
		}
		if (tab.key === "cost") html += '<div class="a3s-pkg__terms" data-terms></div>';
		tab.tables.forEach(function (f) { html += tableHtml(f); });
		if (tab.key === "batteries" && !hasBatteries()) html += '<p class="a3s-field__hint">Batteries are for Off-Grid and Hybrid systems.</p>';
		panels.innerHTML = html;
		if (tab.key === "cost") paintTerms();
		if (window.a3sCombo) window.a3sCombo.wireAll(panels);
	}
	function listColumns(spec) {
		var cols = spec.columns.filter(function (c) { return c.in_list; });
		if (!cols.length) cols = spec.columns.slice();
		return cols.slice(0, LIST_COLUMNS);
	}
	function cell(spec, col, row) {
		var v = row[col.fieldname];
		if (col.type === "Check") return v ? '<span class="a3s-pkg__tick" aria-label="Yes">' + icon("check") + "</span>" : "";
		if (v === "" || v == null) return '<span class="a3s-table__muted">—</span>';
		if (col.type === "Link") return esc(labelOf(col.options, v, spec.fieldname, col.fieldname));
		if (col.type === "Currency") return money(v);
		if (isNum(col.type)) return esc(Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 }));
		return esc(v);
	}
	function tableHtml(f) {
		var spec = pkg.tables[f], cols = listColumns(spec), rows = spec.rows || [];
		return '<section class="a3s-pkg__table" data-table="' + f + '">' +
			'<div class="a3s-pkg__tablehead"><h3 class="a3s-pkg__tabletitle">' + esc(spec.label) + ' <span class="a3s-pkg__count">' + rows.length + "</span></h3>" +
			'<button type="button" class="a3s-btn a3s-btn--secondary a3s-btn--sm" data-add-row><span>+ Add row</span></button></div>' +
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
				spec.columns.map(function (c) { return input(c, draft[c.fieldname], { table: table, row: draft, prefix: "r-" }); }).join("") +
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
			if (REPAINT[col.fieldname]) paintForm();
		});
		m.body.addEventListener("submit", function (e) {
			e.preventDefault();
			spec.columns.forEach(function (c) {
				var el = m.body.querySelector('[name="' + c.fieldname + '"]');
				if (el && !c.read_only) draft[c.fieldname] = readValue(el, c);
			});
			var missing = spec.columns.filter(function (c) { return c.reqd && !c.read_only && (draft[c.fieldname] === "" || draft[c.fieldname] == null); });
			if (missing.length) { m.status("Fill " + missing.map(function (c) { return c.label; }).join(", ") + ".", "error"); return; }
			if (adding) rows.push(draft); else rows[index] = draft;
			keepDefaults(table, draft, adding);
			m.close();
			touch();
			paint();
		});
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
		var tr = e.target.closest("tr[data-row]");
		if (!tr) return;
		var i = Number(tr.dataset.row);
		if (e.target.closest("[data-edit-row]")) return rowForm(table, i);
		if (e.target.closest("[data-remove-row]")) {
			pkg.tables[table].rows.splice(i, 1);
			touch();
			paint();
		}
	});

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
