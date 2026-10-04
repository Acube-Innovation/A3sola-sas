/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The lead-first create form (projects/new). Only the lead is shown at first. Choosing
 * one asks the server what an installation for that lead would open with - the same
 * steps its save runs - and reveals the rest of the form filled with it. Choosing another
 * lead fills it again, except for the fields the person has changed by hand. Saving
 * posts the editable fields to create_from_lead and opens the new project.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-lead-first-form");
	if (!form) return;

	var slug = form.dataset.slug;
	var lead = document.getElementById("fld-lead");
	var body = document.getElementById("a3s-lf-body");
	var leadStatus = document.getElementById("a3s-lf-lead-status");
	var submit = form.querySelector("[data-submit]");
	var status = form.querySelector("[data-status]");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var submitLabel = submit.textContent;
	var touched = {};
	/* The records a lead decides. Another lead replaces them even if they were changed. */
	var LEAD_LINKS = ["solar_consumer", "site_survey", "subsidy_eligibility_check", "solar_design_estimate", "solar_proposal"];
	var request = 0;

	/* Every filled control: the form's tabs, and the lead's companions beside it. */
	function controls() {
		return Array.prototype.slice.call(form.querySelectorAll("[data-field]")).filter(function (el) {
			return el !== lead;
		});
	}

	function say(el, text, kind) {
		el.textContent = text || "";
		el.classList.toggle("is-error", kind === "error");
		el.classList.toggle("is-success", kind === "success");
	}

	function serverMessage(data) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (!msgs.length) return (data && data.exception) ? String(data.exception).split(":").slice(1).join(":").trim() : "";
			var first = JSON.parse(msgs[0]);
			return (first && first.message) ? String(first.message).replace(/<[^>]*>/g, "") : "";
		} catch (e) {
			return "";
		}
	}

	function post(method, payload) {
		return fetch("/api/method/" + method, {
			method: "POST",
			credentials: "same-origin",
			headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
			body: JSON.stringify(payload)
		}).then(function (r) {
			return r.json().catch(function () { return {}; })
				.then(function (data) { return { ok: r.ok, code: r.status, data: data }; });
		});
	}

	/* ------------------------------------------------------------ display */
	function plain(value, type) {
		if (value === null || value === undefined || value === "") return "";
		var n = Number(value);
		if (type === "Currency" && !isNaN(n)) return n ? n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "";
		if ((type === "Float" || type === "Percent") && !isNaN(n)) return n ? String(Math.round(n * 1000) / 1000) + (type === "Percent" ? "%" : "") : "";
		if (type === "Int" && !isNaN(n)) return n ? String(n) : "";
		if (type === "Check") return Number(value) ? "Yes" : "No";
		if (type === "Date") return String(value).slice(0, 10);
		return String(value);
	}

	/* A Link select may not list the value the lead points at - add it, named. */
	function ensureOption(select, value, label) {
		if (!value || select.tagName !== "SELECT") return;
		for (var i = 0; i < select.options.length; i++) if (select.options[i].value === value) return;
		var o = document.createElement("option");
		o.value = value;
		o.textContent = label && label !== value ? label + " · " + value : value;
		select.appendChild(o);
	}

	function fill(preview, onlyUntouched) {
		var values = preview.values || {};
		var titles = preview.titles || {};
		controls().forEach(function (el) {
			var field = el.dataset.field;
			if (!(field in values)) return;
			if (onlyUntouched && touched[field] && LEAD_LINKS.indexOf(field) < 0) return;
			var value = values[field];
			if (el.type === "checkbox") {
				el.checked = !!Number(value);
			} else if (el.readOnly) {
				el.value = el.dataset.type === "Link" ? (titles[field] || value || "") : plain(value, el.dataset.type);
			} else {
				if (el.type === "number" && (value === 0 || value === "0") && el.step !== "1") value = "";
				if (el.type === "datetime-local" && value) value = String(value).slice(0, 16).replace(" ", "T");
				if (el.type === "date" && value) value = String(value).slice(0, 10);
				ensureOption(el, value, titles[field]);
				el.value = value === null || value === undefined ? "" : value;
			}
		});

		Array.prototype.forEach.call(body.querySelectorAll("[data-table]"), function (wrap) {
			var rows = (preview.tables || {})[wrap.dataset.table] || [];
			if (wrap.hasAttribute("data-editable")) {
				/* Rows changed by hand stay when another lead is chosen; the rest follow it. */
				if (onlyUntouched && edited[wrap.dataset.table]) return;
				tableRows[wrap.dataset.table] = rows.map(function (r) { return Object.assign({}, r); });
				edited[wrap.dataset.table] = false;
				paintRows(wrap.dataset.table);
				return;
			}
			var cols = Array.prototype.map.call(wrap.querySelectorAll("th[data-col]"), function (th) {
				return { field: th.dataset.col, type: th.dataset.type };
			});
			var tbody = wrap.querySelector("tbody");
			tbody.innerHTML = "";
			rows.forEach(function (row, i) {
				var tr = document.createElement("tr");
				var td = document.createElement("td");
				td.textContent = String(i + 1);
				tr.appendChild(td);
				cols.forEach(function (c) {
					var cell = document.createElement("td");
					cell.textContent = plain(row[c.field], c.type);
					tr.appendChild(cell);
				});
				tbody.appendChild(tr);
			});
			wrap.dataset.empty = rows.length ? "" : "1";
		});
		applyVisibility();
	}

	/* ------------------------------------------------------------ editable tables
	   The System tables a row can be added to, as on the estimate: each row is added or
	   changed in a popup, rows the estimate works out itself (they carry a source) are
	   shown but not changed, and counts and amounts are shown as the save will work them
	   out. Only tables changed here are sent; the rest are taken from the estimate. */
	var editor = (function () {
		try { return JSON.parse(document.getElementById("a3s-lf-rows").textContent || "{}"); }
		catch (e) { return {}; }
	})();
	var tableRows = {};
	var edited = {};

	function unitCount(required, size) {
		required = Number(required) || 0; size = Number(size) || 0;
		if (!required || !size) return 0;
		return Math.ceil(Math.round((required / size) * 1e6) / 1e6);
	}

	function isoDay(d) {
		return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2);
	}

	/* The tasks laid end to end from the start date, each taking its SLA days, as
	   stages.plan_dates does on save; a skipped task takes no time and has no dates. */
	function planTasks() {
		var start = valueOf("execution_start_date") || valueOf("order_date");
		var cursor = start ? new Date(start + "T00:00:00") : new Date();
		(tableRows.stages || []).forEach(function (r) {
			if (r.status === "Skipped") { r.planned_start_date = r.planned_date = ""; return; }
			r.planned_start_date = isoDay(cursor);
			cursor.setDate(cursor.getDate() + (parseInt(r.sla_days, 10) || 0));
			r.planned_date = isoDay(cursor);
		});
	}

	function workOut(key) {
		if (key === "stages") { planTasks(); return; }
		if (!edited[key]) return;
		var capacity = Number((document.getElementById("fld-capacity_kw") || {}).value) || 0;
		var panelKwp = (tableRows.panels || []).reduce(function (sum, r) { return sum + (Number(r.total_capacity_kwp) || 0); }, 0);
		(tableRows[key] || []).forEach(function (r) {
			if (key === "panels") {
				r.nos = unitCount(capacity * 1000, r.panel_capacity_wp);
				r.total_capacity_kwp = Math.round(r.nos * (Number(r.panel_capacity_wp) || 0)) / 1000;
				r.amount = Math.round((Number(r.rate) || 0) * r.nos * 100) / 100;
			} else if (key === "inverters") {
				r.nos = unitCount(panelKwp, r.inverter_capacity_kw);
				r.total_capacity_kw = Math.round(r.nos * (Number(r.inverter_capacity_kw) || 0) * 1000) / 1000;
				r.amount = Math.round((Number(r.rate) || 0) * r.nos * 100) / 100;
			}
		});
	}

	function fieldSpec(key, fieldname) {
		var t = (editor.tables || {})[key];
		return t ? t.fields.filter(function (f) { return f.fieldname === fieldname; })[0] : null;
	}

	/* A dropdown's value is a record id; the table shows the name the dropdown shows. */
	function cellText(key, fieldname, value, type) {
		var f = fieldSpec(key, fieldname);
		if (f && f.choices && value) {
			var hit = ((editor.choices || {})[f.choices] || []).filter(function (o) { return o.value === value; })[0];
			if (hit) return hit.label;
		}
		return plain(value, type);
	}

	function button(text, cls, onClick) {
		var b = document.createElement("button");
		b.type = "button";
		b.className = "a3s-btn a3s-btn--ghost a3s-btn--sm " + (cls || "");
		b.textContent = text;
		b.addEventListener("click", onClick);
		return b;
	}

	function paintRows(key) {
		var wrap = body.querySelector('[data-table="' + key + '"]');
		if (!wrap) return;
		workOut(key);
		if (key === "panels") workOut("inverters");
		var cols = Array.prototype.map.call(wrap.querySelectorAll("th[data-col]"), function (th) {
			return { field: th.dataset.col, type: th.dataset.type };
		});
		var tbody = wrap.querySelector("tbody");
		var rows = tableRows[key] || [];
		tbody.innerHTML = "";
		rows.forEach(function (row, i) {
			var tr = document.createElement("tr");
			var td = document.createElement("td");
			td.textContent = String(i + 1);
			tr.appendChild(td);
			cols.forEach(function (c) {
				var cell = document.createElement("td");
				cell.textContent = cellText(key, c.field, row[c.field], c.type);
				tr.appendChild(cell);
			});
			var actions = document.createElement("td");
			actions.className = "a3s-lf__row-actions";
			if (row.__template) {
				actions.appendChild(button("Edit", "", function () { openRow(key, i); }));
			} else if (row.source) {
				var note = document.createElement("span");
				note.className = "a3s-lf__auto";
				note.textContent = "From estimate";
				note.title = "Worked out by the estimate; it cannot be changed here.";
				actions.appendChild(note);
			} else {
				actions.appendChild(button("Edit", "", function () { openRow(key, i); }));
				actions.appendChild(button("Remove", "a3s-lf__remove", function () {
					rows.splice(i, 1);
					edited[key] = true;
					paintRows(key);
					if (key === "panels") paintRows("inverters");
				}));
			}
			tr.appendChild(actions);
			tbody.appendChild(tr);
		});
		wrap.querySelector(".a3s-tablewrap").hidden = !rows.length;
		wrap.querySelector("[data-empty-note]").hidden = !!rows.length;
		wrap.dataset.empty = "";
	}

	/* -------------------------------------------- the popup */
	var modal = document.getElementById("a3s-lf-modal");
	var rowForm = document.getElementById("a3s-lf-row-form");
	var rowFields = document.getElementById("a3s-lf-row-fields");
	var rowStatus = document.getElementById("a3s-lf-row-status");
	var rowSubmit = document.getElementById("a3s-lf-row-submit");
	var editing = null;

	function fillSelect(select, f, values) {
		var by = f.filter_by ? values[f.filter_by] : "";
		var keep = values[f.fieldname] || "";
		select.innerHTML = "";
		var blank = document.createElement("option");
		blank.value = ""; blank.textContent = "\u2014";
		select.appendChild(blank);
		((editor.choices || {})[f.choices] || []).filter(function (o) {
			return !o.filter || !by || o.filter === by;
		}).forEach(function (o) {
			var opt = document.createElement("option");
			opt.value = o.value; opt.textContent = o.label;
			if (o.value === keep) opt.selected = true;
			select.appendChild(opt);
		});
		/* A value the list no longer offers is kept, so opening a row never changes it. */
		if (keep && select.value !== keep) {
			var extra = document.createElement("option");
			extra.value = keep; extra.textContent = keep; extra.selected = true;
			select.appendChild(extra);
		}
	}

	function rowValues() {
		var out = {};
		Array.prototype.forEach.call(rowForm.elements, function (el) {
			if (el.name) out[el.name] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value;
		});
		return out;
	}

	function openRow(key, index) {
		var t = (editor.tables || {})[key];
		if (!t) return;
		var row = index === null ? null : tableRows[key][index];
		editing = { key: key, index: index };
		document.getElementById("a3s-lf-modal-title").textContent = (row ? "Change " : "Add ") + t.label.toLowerCase();
		rowSubmit.textContent = row ? "Save changes" : "Add";
		say(rowStatus, "");

		var values = {};
		t.fields.forEach(function (f) {
			var v = row ? row[f.fieldname] : f.default;
			values[f.fieldname] = v === null || v === undefined ? "" : String(v);
		});
		rowFields.innerHTML = "";
		t.fields.forEach(function (f) {
			var id = "a3s-lf-row-" + f.fieldname;
			var input;
			if (f.input === "select") {
				input = document.createElement("select");
				input.name = f.fieldname;
				fillSelect(input, f, values);
			} else if (f.input === "check") {
				input = document.createElement("input");
				input.type = "checkbox";
				input.name = f.fieldname;
				input.checked = !!Number(values[f.fieldname]);
			} else if (f.input === "textarea") {
				input = document.createElement("textarea");
				input.rows = 2;
				input.name = f.fieldname;
				input.value = values[f.fieldname];
			} else {
				input = document.createElement("input");
				input.type = f.input === "number" ? "number" : f.input === "date" ? "date" : "text";
				if (f.input === "number") input.step = "any";
				input.name = f.fieldname;
				input.value = values[f.fieldname];
			}
			input.id = id;
			/* On a task the template gave the job, the template's own fields are not changed. */
			if (row && row.__template && f.locked_on_template) input.disabled = true;
			var label = document.createElement("label");
			label.setAttribute("for", id);
			label.textContent = f.label;
			if (f.reqd) {
				var req = document.createElement("span");
				req.className = "a3s-req"; req.textContent = " *";
				label.appendChild(req);
			}
			var wrap = document.createElement("div");
			wrap.className = "a3s-field" + (f.input === "textarea" ? " a3s-de-fields__wide" : "");
			wrap.appendChild(label);
			wrap.appendChild(input);
			rowFields.appendChild(wrap);
		});
		/* A make list follows the variant, type or item chosen beside it. */
		t.fields.forEach(function (f) {
			if (!f.filter_by) return;
			var source = rowForm.elements[f.filter_by];
			if (source) source.addEventListener("change", function () { fillSelect(rowForm.elements[f.fieldname], f, rowValues()); });
		});
		modal.hidden = false;
		var first = rowFields.querySelector("input, select, textarea");
		if (first) first.focus();
	}

	function closeRow() {
		modal.hidden = true;
		editing = null;
	}

	rowForm.addEventListener("submit", function (event) {
		event.preventDefault();
		if (!editing) return;
		var t = editor.tables[editing.key];
		var values = rowValues();
		var row0 = editing.index === null ? null : tableRows[editing.key][editing.index];
		var missing = t.fields.filter(function (f) {
			return f.reqd && !(row0 && row0.__template && f.locked_on_template) && !String(values[f.fieldname] || "").trim();
		});
		if (missing.length) {
			say(rowStatus, "Fill in " + missing.map(function (f) { return f.label; }).join(", ") + ".", "error");
			rowForm.elements[missing[0].fieldname].focus();
			return;
		}
		var rows = tableRows[editing.key] = tableRows[editing.key] || [];
		if (editing.index === null) rows.push(values);
		else Object.assign(rows[editing.index], values);
		edited[editing.key] = true;
		var key = editing.key;
		closeRow();
		paintRows(key);
		if (key === "panels") paintRows("inverters");
		applyVisibility();
	});
	Array.prototype.forEach.call(modal.querySelectorAll("[data-modal-close]"), function (b) { b.addEventListener("click", closeRow); });
	modal.addEventListener("click", function (event) { if (event.target === modal) closeRow(); });
	document.addEventListener("keydown", function (event) { if (event.key === "Escape" && !modal.hidden) closeRow(); });
	Array.prototype.forEach.call(body.querySelectorAll("[data-add-row]"), function (b) {
		b.addEventListener("click", function () { openRow(b.dataset.addRow, null); });
	});
	/* Panels are counted to reach the capacity, so a new capacity recounts them. */
	var capacityInput = document.getElementById("fld-capacity_kw");
	if (capacityInput) capacityInput.addEventListener("change", function () { paintRows("panels"); paintRows("inverters"); });

	/* -------------------------------------------- tasks from the stage template
	   Another template - or a change to what decides which of its tasks apply - asks the
	   server for the template's tasks again. A changed start date only moves the plan.
	   Changes made to tasks here are carried across: the job's own fields on a template
	   task by its code, and tasks added by hand after them. */
	var TASK_INPUTS = ["stage_template", "is_financed", "subsidy_scheme", "capacity_kw", "net_meter_mode"];
	var taskTicket = 0;

	function reloadTasks() {
		var template = valueOf("stage_template");
		var ticket = ++taskTicket;
		if (!template) { tableRows.stages = []; paintRows("stages"); applyVisibility(); return; }
		post("a3_sola.api.installation_lead.get_template_tasks", {
			stage_template: template, execution_start_date: valueOf("execution_start_date"),
			order_date: valueOf("order_date"), is_financed: valueOf("is_financed") ? 1 : 0,
			subsidy_scheme: valueOf("subsidy_scheme"), capacity_kw: valueOf("capacity_kw"),
			net_meter_mode: valueOf("net_meter_mode")
		}).then(function (res) {
			if (ticket !== taskTicket || !res.ok || !res.data) return;
			var fresh = res.data.message || [];
			if (edited.stages) {
				var jobFields = editor.tables.stages.fields.filter(function (f) { return !f.locked_on_template; })
					.map(function (f) { return f.fieldname; });
				var before = {};
				(tableRows.stages || []).forEach(function (r) { if (r.__template) before[r.stage_code] = r; });
				fresh.forEach(function (r) {
					var old = before[r.stage_code];
					if (old) jobFields.forEach(function (f) { if (old[f] !== undefined) r[f] = old[f]; });
				});
				fresh = fresh.concat((tableRows.stages || []).filter(function (r) { return !r.__template; }));
			}
			tableRows.stages = fresh;
			paintRows("stages");
			applyVisibility();
		});
	}

	TASK_INPUTS.forEach(function (name) {
		var el = document.getElementById("fld-" + name);
		if (el) el.addEventListener("change", reloadTasks);
	});
	["execution_start_date", "order_date"].forEach(function (name) {
		var el = document.getElementById("fld-" + name);
		if (el) el.addEventListener("change", function () { paintRows("stages"); });
	});

	/* As on the desk: an empty read-only field is not shown, a field or section behind a
	   condition shows only when it holds, and a section with nothing left in it goes. */
	function valueOf(field) {
		var el = form.querySelector('[data-field="' + field + '"]');
		if (!el) return "";
		if (el.type === "checkbox") return el.checked ? "1" : "";
		return el.value;
	}

	function holds(rule) {
		if (!rule) return true;
		var at = rule.indexOf("=");
		if (at < 0) { var v = valueOf(rule); return !!v && v !== "0"; }
		return valueOf(rule.slice(0, at)) === rule.slice(at + 1);
	}

	function applyVisibility() {
		Array.prototype.forEach.call(form.querySelectorAll("#a3s-lf-body .a3s-field, [data-companion]"), function (wrap) {
			var el = wrap.querySelector("[data-field]");
			var show = holds(wrap.dataset.showWhen);
			if (show && wrap.hasAttribute("data-readonly") && el) {
				show = el.type === "checkbox" ? el.checked : String(el.value || "").trim() !== "";
			}
			wrap.hidden = !show;
		});
		Array.prototype.forEach.call(body.querySelectorAll("[data-table]"), function (wrap) {
			wrap.hidden = wrap.dataset.empty === "1";
		});
		Array.prototype.forEach.call(body.querySelectorAll(".a3s-lf__section"), function (sec) {
			var any = sec.querySelector(".a3s-field:not([hidden]), [data-table]:not([hidden])");
			sec.hidden = !holds(sec.dataset.showWhen) || !any;
		});
		Array.prototype.forEach.call(body.querySelectorAll(".a3s-lf__card"), function (card) {
			card.hidden = !card.querySelector(".a3s-lf__section:not([hidden])");
		});
		Array.prototype.forEach.call(body.querySelectorAll("[data-panel]"), function (panel) {
			panel.dataset.empty = panel.querySelector(".a3s-lf__card:not([hidden])") ? "" : "1";
		});
		showTab(activeTab);
	}

	/* ------------------------------------------------------------ tabs */
	var tabs = Array.prototype.slice.call(body.querySelectorAll("[data-tab]"));
	var activeTab = tabs.length ? tabs[0].dataset.tab : "";

	function showTab(key) {
		var panels = Array.prototype.slice.call(body.querySelectorAll("[data-panel]"));
		var usable = function (k) {
			var p = body.querySelector('[data-panel="' + k + '"]');
			return p && p.dataset.empty !== "1";
		};
		/* The tab in use may have emptied (another lead): fall back to the first with content. */
		if (!usable(key)) {
			var first = tabs.filter(function (t) { return usable(t.dataset.tab); })[0];
			key = first ? first.dataset.tab : key;
		}
		activeTab = key;
		tabs.forEach(function (t) {
			var on = t.dataset.tab === key;
			t.hidden = !usable(t.dataset.tab);
			t.setAttribute("aria-selected", on ? "true" : "false");
			t.setAttribute("tabindex", on ? "0" : "-1");
		});
		panels.forEach(function (p) { p.hidden = p.dataset.panel !== key || p.dataset.empty === "1"; });

		var visible = tabs.filter(function (t) { return !t.hidden; });
		var at = visible.map(function (t) { return t.dataset.tab; }).indexOf(key);
		var last = at === visible.length - 1;
		prev.hidden = at <= 0;
		next.hidden = last;
		submit.hidden = !last;
	}

	/* The tab before or after the one in view, among those shown, scrolled to its top. */
	function step(by) {
		var visible = tabs.filter(function (t) { return !t.hidden; });
		var at = visible.map(function (t) { return t.dataset.tab; }).indexOf(activeTab);
		var target = visible[at + by];
		if (!target) return;
		showTab(target.dataset.tab);
		var bar = body.querySelector(".a3s-lf__tabs");
		var top = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--a3s-topbar-h")) || 64;
		window.scrollTo({ top: Math.max(bar.getBoundingClientRect().top + window.pageYOffset - top - 16, 0), behavior: "smooth" });
	}

	var prev = form.querySelector("[data-prev]");
	var next = form.querySelector("[data-next]");
	prev.addEventListener("click", function () { step(-1); });
	next.addEventListener("click", function () { step(1); });

	tabs.forEach(function (t, i) {
		t.addEventListener("click", function () { showTab(t.dataset.tab); });
		t.addEventListener("keydown", function (e) {
			if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
			var visible = tabs.filter(function (x) { return !x.hidden; });
			var at = visible.indexOf(t) + (e.key === "ArrowRight" ? 1 : -1);
			var next = visible[(at + visible.length) % visible.length];
			if (next) { showTab(next.dataset.tab); next.focus(); }
		});
	});

	/* ------------------------------------------------------------ the lead */
	function loadLead() {
		var name = (lead.value || "").trim();
		var ticket = ++request;
		if (!name) {
			body.hidden = true;
			Array.prototype.forEach.call(form.querySelectorAll("[data-companion]"), function (w) { w.hidden = true; });
			say(leadStatus, "");
			return;
		}
		say(leadStatus, "Reading the lead…");
		post("a3_sola.api.installation_lead.get_installation_preview", { lead: name }).then(function (res) {
			if (ticket !== request) return;
			if (!res.ok || !res.data || !res.data.message) {
				body.hidden = true;
				Array.prototype.forEach.call(form.querySelectorAll("[data-companion]"), function (w) { w.hidden = true; });
				say(leadStatus, serverMessage(res.data) || "Could not read that lead.", "error");
				return;
			}
			var preview = res.data.message;
			fill(preview, !body.hidden);
			body.hidden = false;
			say(leadStatus, preview.warning || "", preview.warning ? "error" : "");
		}).catch(function () {
			if (ticket !== request) return;
			say(leadStatus, "Could not reach the server. Check your connection and try again.", "error");
		});
	}

	lead.addEventListener("change", loadLead);
	body.addEventListener("input", function (e) { if (e.target.dataset.field) touched[e.target.dataset.field] = true; });
	body.addEventListener("change", function (e) {
		if (e.target.dataset.field) touched[e.target.dataset.field] = true;
		applyVisibility();
	});
	if (lead.value) loadLead();

	/* ------------------------------------------------------------ save */
	function collect() {
		var out = { slug: slug, lead: lead.value, tables: {} };
		/* Only the tables changed here, without the estimate's own rows: the server keeps those. */
		Object.keys(edited).forEach(function (key) {
			if (!edited[key]) return;
			var fields = editor.tables[key].fields.map(function (f) { return f.fieldname; });
			out.tables[key] = (tableRows[key] || []).filter(function (r) { return !r.source; }).map(function (r) {
				var row = {};
				fields.forEach(function (f) { row[f] = r[f] === undefined || r[f] === null ? "" : r[f]; });
				if (r.__template) row.__template = 1;
				return row;
			});
		});
		Array.prototype.forEach.call(form.elements, function (el) {
			if (!el.name || el === lead) return;
			var wrap = el.closest(".a3s-field");
			/* A field behind an unmet condition is not being asked, so it posts nothing. */
			if (wrap && wrap.hidden) return;
			out[el.name] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value;
		});
		return out;
	}

	/* The error names a field by its label; open the tab that field is on so it can be fixed. */
	function revealFieldIn(message) {
		var labels = Array.prototype.slice.call(body.querySelectorAll(".a3s-field label"));
		for (var i = 0; i < labels.length; i++) {
			var text = labels[i].textContent.replace("*", "").trim();
			if (text && message.indexOf(text) >= 0) {
				var panel = labels[i].closest("[data-panel]");
				if (panel) showTab(panel.dataset.panel);
				return;
			}
		}
	}

	function busy(on) {
		submit.disabled = on;
		submit.textContent = on ? "Creating…" : submitLabel;
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		if (submit.hidden) { step(1); return; }
		if (!lead.value) { say(leadStatus, "Choose the lead first.", "error"); lead.focus(); return; }
		busy(true);
		say(status, "Creating…");
		post("a3_sola.api.portal_crud.create_from_lead", collect()).then(function (res) {
			if (res.ok && res.data && res.data.message) {
				say(status, "Created " + res.data.message.name + ". Opening it…", "success");
				window.location.assign(res.data.message.route);
				return;
			}
			busy(false);
			if (res.code === 403) { say(status, "You do not have permission to create a project.", "error"); return; }
			var message = serverMessage(res.data) || "Could not create the project. Check the fields and try again.";
			say(status, message, "error");
			revealFieldIn(message);
		}).catch(function () {
			busy(false);
			say(status, "Could not reach the server. Check your connection and try again.", "error");
		});
	});
})();
