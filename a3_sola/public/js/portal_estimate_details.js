/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Step one of the design estimate builder. Next saves the details - creating the estimate
 * the first time - and moves on to step two. The server validates; this only collects.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-de-details");
	if (!form) return;

	var next = document.getElementById("a3s-de-next");
	var status = document.getElementById("a3s-de-status");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function setStatus(text, kind) {
		status.textContent = text || "";
		status.classList.toggle("is-error", kind === "error");
	}

	function serverMessage(data) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			var last = msgs.length ? JSON.parse(msgs[msgs.length - 1]) : null;
			if (last && last.message) return String(last.message).replace(/<br\s*\/?>/g, " ").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception) ? String(data.exception).split(":").slice(1).join(":").trim() : "";
	}

	/* A field that only applies to one answer - the subsidy scheme - shows with that answer. */
	var conditional = form.querySelectorAll("[data-show-when]");
	function applyConditions() {
		Array.prototype.forEach.call(conditional, function (wrap) {
			var parts = wrap.dataset.showWhen.split("=");
			var source = document.getElementById("fld-" + parts[0]);
			wrap.hidden = !(source && source.value === parts.slice(1).join("="));
		});
	}
	Array.prototype.forEach.call(conditional, function (wrap) {
		var source = document.getElementById("fld-" + wrap.dataset.showWhen.split("=")[0]);
		if (source) source.addEventListener("change", applyConditions);
	});
	applyConditions();

	/* Lead, consumer and the other link fields can run to hundreds of records, so each gets a
	   search box over its select: typing narrows the list, clicking or arrowing down opens it
	   whole. The select stays the field - hidden, still named, still firing change - so the
	   profile and the save read it as before. */
	var comboCount = 0;
	function wireCombo(wrap) {
		var select = wrap.querySelector("select");
		if (!select) return;
		var listId = "a3s-combo-list-" + (++comboCount);
		var input = document.createElement("input");
		input.type = "search";
		input.autocomplete = "off";
		input.placeholder = "Search or pick";
		input.setAttribute("role", "combobox");
		input.setAttribute("aria-expanded", "false");
		input.setAttribute("aria-controls", listId);
		input.setAttribute("aria-autocomplete", "list");
		input.setAttribute("aria-label", select.getAttribute("aria-label") || "");
		var list = document.createElement("div");
		list.className = "a3s-combo__list";
		list.id = listId;
		list.setAttribute("role", "listbox");
		list.hidden = true;
		/* The label points at the visible box. The select keeps its id, which the profile and
		   the conditions look it up by, and is hidden by class: the save skips [hidden]. */
		input.id = select.id + "-search";
		var label = wrap.querySelector('label[for="' + select.id + '"]');
		if (label) label.htmlFor = input.id;
		select.classList.add("a3s-combo__native");
		select.tabIndex = -1;
		select.parentNode.insertBefore(input, select);
		select.parentNode.insertBefore(list, select.nextSibling);

		var shown = [];
		var active = -1;
		function choices() {
			return Array.prototype.filter.call(select.options, function (o) { return o.value; });
		}
		function labelOf(value) {
			var o = choices().filter(function (c) { return c.value === value; })[0];
			return o ? o.textContent : "";
		}
		function close() {
			list.hidden = true;
			input.setAttribute("aria-expanded", "false");
			active = -1;
		}
		function highlight(i) {
			active = i;
			Array.prototype.forEach.call(list.children, function (opt, j) {
				opt.classList.toggle("is-active", j === i);
				if (j === i) { opt.scrollIntoView({ block: "nearest" }); input.setAttribute("aria-activedescendant", opt.id); }
			});
			if (i < 0) input.removeAttribute("aria-activedescendant");
		}
		function render(query) {
			var words = (query || "").toLowerCase().split(/\s+/).filter(Boolean);
			shown = choices().filter(function (o) {
				var text = (o.textContent + " " + o.value).toLowerCase();
				return words.every(function (w) { return text.indexOf(w) !== -1; });
			});
			list.innerHTML = "";
			if (!shown.length) {
				list.appendChild(node("p", "a3s-combo__none", "No match."));
			}
			shown.forEach(function (o, i) {
				var opt = node("button", "a3s-combo__opt");
				opt.type = "button";
				opt.tabIndex = -1;
				opt.id = listId + "-" + i;
				opt.setAttribute("role", "option");
				opt.setAttribute("aria-selected", o.value === select.value ? "true" : "false");
				opt.appendChild(document.createTextNode(o.textContent));
				if (o.value !== o.textContent) opt.appendChild(node("small", "", o.value));
				/* mousedown, not click: it lands before the input's blur closes the list. */
				opt.addEventListener("mousedown", function (e) { e.preventDefault(); choose(o.value); });
				list.appendChild(opt);
			});
			list.hidden = false;
			input.setAttribute("aria-expanded", "true");
			highlight(-1);
		}
		function choose(value) {
			var changed = select.value !== value;
			select.value = value;
			input.value = labelOf(value);
			close();
			if (changed) select.dispatchEvent(new Event("change", { bubbles: true }));
		}

		input.value = labelOf(select.value);
		input.addEventListener("focus", function () { input.select(); });
		input.addEventListener("click", function () { if (list.hidden) render(""); });
		input.addEventListener("input", function () { render(input.value); });
		input.addEventListener("keydown", function (e) {
			if (e.key === "ArrowDown" || e.key === "ArrowUp") {
				e.preventDefault();
				if (list.hidden) { render(""); }
				if (!shown.length) return;
				var step = e.key === "ArrowDown" ? 1 : -1;
				highlight((active + step + shown.length) % shown.length);
			} else if (e.key === "Enter" && !list.hidden) {
				e.preventDefault();  /* never submit the form from the search box */
				var pick = active >= 0 ? shown[active] : (shown.length === 1 ? shown[0] : null);
				if (pick) choose(pick.value);
			} else if (e.key === "Escape" && !list.hidden) {
				e.preventDefault();
				input.value = labelOf(select.value);
				close();
			}
		});
		/* Leaving the box keeps the chosen record; leaving it emptied clears the field. */
		input.addEventListener("blur", function () {
			if (!input.value.trim()) { if (select.value) choose(""); else close(); return; }
			input.value = labelOf(select.value);
			close();
		});
	}
	Array.prototype.forEach.call(form.querySelectorAll("[data-combo]"), wireCombo);

	/* The "?" beside the tariff: what the chosen KSEB code covers, kept in step with the
	   field while it is open. Closes on a click elsewhere or Escape. */
	Array.prototype.forEach.call(form.querySelectorAll("[data-help]"), function (btn) {
		var fieldname = btn.dataset.help;
		var pop = document.getElementById("help-" + fieldname);
		var select = document.getElementById("fld-" + fieldname);
		var info = {};
		try { info = JSON.parse(document.getElementById("help-data-" + fieldname).textContent) || {}; } catch (e) { /* none */ }
		function fill() {
			pop.innerHTML = "";
			var c = select && info[select.value];
			if (!c) {
				pop.appendChild(node("p", "a3s-help__empty", "Choose a tariff code to see who it applies to."));
				return;
			}
			pop.appendChild(node("p", "a3s-help__code", c.code));
			pop.appendChild(node("p", "a3s-help__name", c.name));
			var dl = node("dl", "a3s-help__rows");
			[["Supply", c.group], ["Voltage level", c.voltage], ["Usage & applicability", c.usage]].forEach(function (r) {
				if (!r[1]) return;
				var row = node("div");
				row.appendChild(node("dt", "", r[0]));
				row.appendChild(node("dd", "", r[1]));
				dl.appendChild(row);
			});
			pop.appendChild(dl);
		}
		function toggle(open) {
			if (open) fill();
			pop.hidden = !open;
			btn.setAttribute("aria-expanded", open ? "true" : "false");
		}
		btn.addEventListener("click", function (e) { e.stopPropagation(); toggle(pop.hidden); });
		pop.addEventListener("click", function (e) { e.stopPropagation(); });
		document.addEventListener("click", function () { if (!pop.hidden) toggle(false); });
		document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !pop.hidden) { toggle(false); btn.focus(); } });
		if (select) select.addEventListener("change", function () { if (!pop.hidden) fill(); });
	});

	/* The consumer's details beside the Consumer fields, refreshed as the lead or consumer
	   changes. The server reads them with the person's own permissions. */
	var profile = document.getElementById("a3s-de-profile");
	function node(tag, cls, text) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text !== undefined) n.textContent = text;
		return n;
	}
	function paintProfile(p) {
		profile.innerHTML = "";
		if (!p) {
			profile.appendChild(node("p", "a3s-de-profile__empty", "Choose a lead or a solar consumer to see their details here."));
			return;
		}
		profile.appendChild(node("p", "a3s-de-profile__source", p.source + " \u00b7 " + p.name));
		profile.appendChild(node("p", "a3s-de-profile__name", p.title));
		var dl = node("dl", "a3s-de-profile__rows");
		(p.rows || []).forEach(function (r) {
			var row = node("div");
			row.appendChild(node("dt", "", r.label));
			row.appendChild(node("dd", "", r.value));
			dl.appendChild(row);
		});
		profile.appendChild(dl);
	}
	function refreshProfile() {
		var lead = document.getElementById("fld-lead");
		var consumer = document.getElementById("fld-solar_consumer");
		var query = "lead=" + encodeURIComponent(lead ? lead.value : "") +
			"&solar_consumer=" + encodeURIComponent(consumer ? consumer.value : "");
		profile.classList.add("is-loading");
		fetch("/api/method/a3_sola.api.portal_estimate.profile?" + query, {
			credentials: "same-origin", headers: { "Accept": "application/json" }
		}).then(function (r) { return r.json(); })
		  .then(function (data) { paintProfile(data && data.message); })
		  .catch(function () { /* keep what was shown */ })
		  .then(function () { profile.classList.remove("is-loading"); });
	}
	if (profile) {
		["fld-lead", "fld-solar_consumer"].forEach(function (id) {
			var el = document.getElementById(id);
			if (el) el.addEventListener("change", refreshProfile);
		});
	}

	/* Package & Sizing options: one row per combination, one of them recommended. A row's
	   subsidy scheme only shows when that row is with subsidy. */
	var optionsBody = form.querySelector("[data-options]");
	var template = document.getElementById("a3s-de-option-template");

	function optionRows() {
		return optionsBody ? Array.prototype.slice.call(optionsBody.querySelectorAll("tr[data-option]")) : [];
	}

	/* A row lists only the packages for its connection type, and an Off-Grid row cannot take
	   subsidy. A choice the row no longer allows is cleared rather than left to fail the save. */
	function applyRowRules(tr) {
		function field(name) { return tr.querySelector('[data-field="' + name + '"]'); }
		var phase = field("connection_type");
		var pkg = field("solar_package");
		if (phase && pkg) {
			Array.prototype.forEach.call(pkg.options, function (o) {
				var phases = o.dataset.phases ? o.dataset.phases.split("|") : [];
				var off = !!(phase.value && phases.length && phases.indexOf(phase.value) === -1);
				o.hidden = off;
				o.disabled = off;
			});
			var dropped = pkg.selectedOptions[0];
			if (dropped && dropped.disabled) {
				pkg.value = "";
				setStatus("“" + dropped.textContent + "” has no " + phase.value + " inverter, so it was cleared. Choose a " + phase.value + " package, or pick one later on the Inverter tab.");
			}
		}
		var system = field("system_type");
		var subsidy = field("subsidy_option");
		if (system && subsidy) {
			var offGrid = system.value === "Off-Grid";
			Array.prototype.forEach.call(subsidy.options, function (o) {
				if (o.value === "With Subsidy") { o.disabled = offGrid; o.hidden = offGrid; }
			});
			if (offGrid && subsidy.value === "With Subsidy") subsidy.value = "Without Subsidy";
		}
	}

	function applyRowConditions(tr) {
		applyRowRules(tr);
		Array.prototype.forEach.call(tr.querySelectorAll("[data-row-show-when]"), function (wrap) {
			var parts = wrap.dataset.rowShowWhen.split("=");
			var source = tr.querySelector('[data-field="' + parts[0] + '"]');
			var on = !!source && source.value === parts.slice(1).join("=");
			wrap.hidden = !on;
			if (!on) Array.prototype.forEach.call(wrap.querySelectorAll("[data-field]"), function (el) { el.value = ""; });
		});
	}

	function wireRow(tr) {
		applyRowConditions(tr);
		tr.addEventListener("change", function () { applyRowConditions(tr); });
		tr.querySelector("[data-remove-option]").addEventListener("click", function () {
			if (optionRows().length === 1) {
				setStatus("Keep at least one option.", "error");
				return;
			}
			var wasRecommended = tr.querySelector("[data-recommended]").checked;
			tr.remove();
			if (wasRecommended) optionRows()[0].querySelector("[data-recommended]").checked = true;
			renumber();
			setStatus("");
		});
	}

	/* Options are numbered in order, and renumbered when one is added or removed. */
	function renumber() {
		optionRows().forEach(function (tr, i) {
			var n = tr.querySelector("[data-option-number]");
			if (n) n.textContent = String(i + 1);
		});
	}

	optionRows().forEach(wireRow);
	renumber();

	var addOption = form.querySelector("[data-add-option]");
	if (addOption && template) {
		addOption.addEventListener("click", function () {
			/* A new option starts as a copy of the last one: usually only one thing changes. */
			var rows = optionRows();
			var last = rows[rows.length - 1];
			var tr = template.content.querySelector("tr").cloneNode(true);
			Array.prototype.forEach.call(tr.querySelectorAll("[data-field]"), function (el) {
				var from = last && last.querySelector('[data-field="' + el.dataset.field + '"]');
				el.value = from ? from.value : "";
			});
			tr.querySelector("[data-recommended]").checked = false;
			optionsBody.appendChild(tr);
			wireRow(tr);
			renumber();
			var first = tr.querySelector("[data-field]");
			if (first) first.focus();
		});
	}

	function collectOptions() {
		return optionRows().map(function (tr) {
			var row = { is_recommended: tr.querySelector("[data-recommended]").checked ? 1 : 0 };
			Array.prototype.forEach.call(tr.querySelectorAll("[data-field]"), function (el) {
				if (!el.closest("[hidden]")) row[el.dataset.field] = el.value;
			});
			return row;
		});
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		var values = {};
		Array.prototype.forEach.call(form.elements, function (el) {
			if (el.name && el.name !== "recommended_option" && !el.closest("[hidden]")) values[el.name] = el.value;
		});
		next.disabled = true;
		setStatus("Saving…");
		fetch("/api/method/a3_sola.api.portal_estimate.save_details", {
			method: "POST",
			credentials: "same-origin",
			headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
			body: JSON.stringify({ values: values, name: form.dataset.name || null, sizing_options: optionRows().length ? collectOptions() : null })
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (data) { return { ok: r.ok, data: data }; });
		}).then(function (res) {
			if (res.ok && res.data.message) {
				window.location.assign(res.data.message.route);
				return;
			}
			next.disabled = false;
			setStatus(serverMessage(res.data) || "Could not save. Check the fields and try again.", "error");
		}).catch(function () {
			next.disabled = false;
			setStatus("Could not reach the server. Check your connection and try again.", "error");
		});
	});
})();
