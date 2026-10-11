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

	/* The search box over each long link field: portal_combo.js. */
	var wireCombo = window.a3sCombo.wire;
	Array.prototype.forEach.call(form.querySelectorAll("[data-combo]"), wireCombo);

	/* A lead narrows the consumers to its own, and the consumers narrow the surveys to
	   theirs; with one left, it is chosen. A choice that no longer fits is cleared. */
	var leadField = document.getElementById("fld-lead");
	var consumerField = document.getElementById("fld-solar_consumer");
	var surveyField = document.getElementById("fld-site_survey");

	function setField(select, value) {
		if (select.value === value) return;
		select.value = value;
		select.dispatchEvent(new Event("a3s:sync"));
		select.dispatchEvent(new Event("change", { bubbles: true }));
	}
	function keepOnly(select, fits) {
		var left = [];
		Array.prototype.forEach.call(select.options, function (o) {
			if (!o.value) return;
			var off = !fits(o);
			o.hidden = off;
			o.disabled = off;
			if (!off) left.push(o.value);
		});
		if (select.value && left.indexOf(select.value) === -1) setField(select, "");
		return left;
	}
	function narrow() {
		var lead = leadField ? leadField.value : "";
		var consumers = null;
		if (consumerField) {
			var mine = keepOnly(consumerField, function (o) { return !lead || o.dataset.lead === lead; });
			if (lead && !consumerField.value && mine.length === 1) setField(consumerField, mine[0]);
			consumers = consumerField.value ? [consumerField.value] : (lead ? mine : null);
		}
		if (surveyField) {
			var surveys = keepOnly(surveyField, function (o) { return !consumers || consumers.indexOf(o.dataset.consumer) !== -1; });
			if (consumers && !surveyField.value && surveys.length === 1) setField(surveyField, surveys[0]);
		}
	}
	if (leadField) leadField.addEventListener("change", narrow);
	if (consumerField) consumerField.addEventListener("change", narrow);
	narrow();

	/* A survey chosen first brings its consumer, and the consumer its lead. */
	function optionOf(select, value) {
		return Array.prototype.filter.call(select.options, function (o) { return o.value === value; })[0];
	}
	if (surveyField && consumerField) {
		surveyField.addEventListener("change", function () {
			var picked = surveyField.value && optionOf(surveyField, surveyField.value);
			if (picked && picked.dataset.consumer && !consumerField.value) setField(consumerField, picked.dataset.consumer);
		});
	}
	if (consumerField && leadField) {
		consumerField.addEventListener("change", function () {
			var picked = consumerField.value && optionOf(consumerField, consumerField.value);
			if (picked && picked.dataset.lead && !leadField.value) setField(leadField, picked.dataset.lead);
		});
	}

	/* Package Details: the package list follows the connection type - a package is listed
	   when it has an inverter of that phase - and an Off-Grid system cannot take subsidy. A
	   choice the rules no longer allow is cleared, and the page says why. */
	var phaseField = document.getElementById("fld-connection_type");
	var packageField = document.getElementById("fld-solar_package");
	var systemField = document.getElementById("fld-system_type");
	var subsidyField = document.getElementById("fld-subsidy_option");
	/* With subsidy, only DCR-compliant packages: the subsidy needs DCR panels. */
	function packageFits(o, phase, subsidy) {
		var phases = o.dataset.phases ? o.dataset.phases.split("|") : [];
		if (phase && phases.length && phases.indexOf(phase) === -1) return "phase";
		if (subsidy === "With Subsidy" && o.dataset.dcr === "0") return "dcr";
		return "";
	}
	function droppedNote(o, why, phase) {
		return "\u201c" + o.textContent + "\u201d " + (why === "dcr"
			? "is not DCR compliant, and subsidy needs DCR panels, so it was cleared. Choose a DCR package."
			: "has no " + phase + " inverter, so it was cleared. Choose a " + phase + " package.");
	}
	function packageRules() {
		if (packageField) {
			var dropped = null, why = "";
			var phase = phaseField ? phaseField.value : "";
			keepOnly(packageField, function (o) {
				var off = packageFits(o, phase, subsidyField ? subsidyField.value : "");
				if (off && o.value === packageField.value) { dropped = o; why = off; }
				return !off;
			});
			if (dropped) setStatus(droppedNote(dropped, why, phase));
		}
		if (subsidyField) {
			/* Subsidy is only for the subsidy tariff (LT-I, domestic), and never Off-Grid. A
			   tariff not chosen yet does not rule it out. */
			var tariff = document.getElementById("fld-tariff_code");
			var needed = subsidyField.dataset.subsidyTariff;
			var wrongTariff = !!(needed && tariff && tariff.value && tariff.value !== needed);
			var offGrid = !!systemField && systemField.value === "Off-Grid";
			var blocked = wrongTariff || offGrid;
			Array.prototype.forEach.call(subsidyField.options, function (o) {
				if (o.value === "With Subsidy") { o.disabled = blocked; o.hidden = blocked; }
			});
			if (blocked && subsidyField.value === "With Subsidy") {
				subsidyField.value = "Without Subsidy";
				subsidyField.dispatchEvent(new Event("change", { bubbles: true }));
				var picked = tariff && tariff.selectedOptions[0];
				setStatus(wrongTariff
					? "Subsidy is only for " + needed + " customers; this one is " + (picked ? picked.textContent : tariff.value) + ", so Subsidy was set to Without Subsidy."
					: "An Off-Grid system cannot take subsidy, so Subsidy was set to Without Subsidy.");
			} else if (!blocked && /^(Subsidy is only for|An Off-Grid system cannot take subsidy)/.test(status.textContent)) {
				setStatus("");  // subsidy is allowed again: the reason it was not no longer applies
			}
		}
	}
	/* Subsidy again, with no scheme chosen: the default scheme (PM Surya Ghar) comes back. */
	var schemeField = document.getElementById("fld-subsidy_scheme");
	if (subsidyField && schemeField && schemeField.dataset.default) {
		subsidyField.addEventListener("change", function () {
			if (subsidyField.value === "With Subsidy" && !schemeField.value) setField(schemeField, schemeField.dataset.default);
		});
	}
	if (phaseField) phaseField.addEventListener("change", packageRules);
	if (subsidyField) subsidyField.addEventListener("change", packageRules);
	if (systemField) systemField.addEventListener("change", packageRules);
	var tariffSelect = document.getElementById("fld-tariff_code");
	if (tariffSelect) tariffSelect.addEventListener("change", packageRules);
	packageRules();

	/* The Electricity Tariff is the chosen consumer's KSEB code, unless one was chosen here. */
	var tariffField = document.getElementById("fld-tariff_code");
	if (tariffField && consumerField) {
		var tariffFilled = tariffField.value;  // what the page or this last put there
		consumerField.addEventListener("change", function () {
			if (tariffField.value && tariffField.value !== tariffFilled) return;  // chosen by hand
			var picked = consumerField.value && optionOf(consumerField, consumerField.value);
			var code = picked && picked.dataset.tariff;
			if (code && optionOf(tariffField, code)) {
				setField(tariffField, code);
				tariffFilled = code;
			}
		});
	}

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
		var system = field("system_type");
		var subsidy = field("subsidy_option");
		if (system && subsidy) {
			var offGrid = system.value === "Off-Grid";
			Array.prototype.forEach.call(subsidy.options, function (o) {
				if (o.value === "With Subsidy") { o.disabled = offGrid; o.hidden = offGrid; }
			});
			if (offGrid && subsidy.value === "With Subsidy") subsidy.value = "Without Subsidy";
		}
		if (pkg) {
			var phaseValue = phase ? phase.value : "";
			var why = "";
			Array.prototype.forEach.call(pkg.options, function (o) {
				if (!o.value) return;
				var off = packageFits(o, phaseValue, subsidy ? subsidy.value : "");
				o.hidden = !!off;
				o.disabled = !!off;
				if (off && o.value === pkg.value) why = off;
			});
			var dropped = pkg.selectedOptions[0];
			if (dropped && dropped.disabled) {
				pkg.value = "";
				setStatus(droppedNote(dropped, why, phaseValue));
			}
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
