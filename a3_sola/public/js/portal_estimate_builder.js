/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Step two of the design estimate builder. Left: the System & Options tables. Middle: the
 * chosen table's saved rows; a row is added or changed in a popup. Right: what each table
 * costs, the tax and the total. Every add, change or removal saves the estimate and
 * repaints from what the server returns - counts, expense rows and prices are its to work out.
 */
(function () {
	"use strict";

	var dataEl = document.getElementById("a3s-de-data");
	if (!dataEl) return;

	var state = JSON.parse(dataEl.textContent);
	var active = (state.sections[0] || {}).key;
	var editing = null; // the row being changed, or null when adding

	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

	var $ = function (id) { return document.getElementById(id); };
	var form = $("de-form");
	var submit = $("de-submit");
	var cancel = $("de-cancel");
	var status = $("de-status");
	var pageStatus = $("de-page-status");
	var modal = $("de-modal");

	function el(tag, attrs, children) {
		var node = document.createElement(tag);
		Object.keys(attrs || {}).forEach(function (key) {
			if (key === "text") node.textContent = attrs[key];
			else if (key === "class") node.className = attrs[key];
			else if (attrs[key] !== null && attrs[key] !== undefined && attrs[key] !== false) node.setAttribute(key, attrs[key]);
		});
		(children || []).forEach(function (child) { if (child) node.appendChild(child); });
		return node;
	}

	function icon(name) {
		var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
		svg.setAttribute("class", "a3s-ic");
		svg.setAttribute("aria-hidden", "true");
		var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
		use.setAttribute("href", "#ic-" + name);
		svg.appendChild(use);
		return svg;
	}

	function section() {
		return state.sections.find(function (s) { return s.key === active; }) || state.sections[0];
	}

	function lineAmount(key) {
		var line = state.commercials.lines.find(function (l) { return l.key === key; });
		return line ? line.amount : 0;
	}

	function setStatus(text, kind, target) {
		target = target || status;
		target.textContent = text || "";
		target.classList.toggle("is-error", kind === "error");
		target.classList.toggle("is-success", kind === "success");
	}

	function serverMessage(data) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			var last = msgs.length ? JSON.parse(msgs[msgs.length - 1]) : null;
			if (last && last.message) return String(last.message).replace(/<br\s*\/?>/g, " ").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception) ? String(data.exception).split(":").slice(1).join(":").trim() : "";
	}

	function call(method, args) {
		return fetch("/api/method/a3_sola.api.portal_estimate." + method, {
			method: "POST",
			credentials: "same-origin",
			headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
			body: JSON.stringify(args)
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (data) {
				if (!r.ok || !data.message) throw new Error(serverMessage(data) || "Could not save. Try again.");
				return data.message;
			});
		});
	}

	/* ------------------------------------------------------------ header */
	function paintHeader() {
		$("de-title").textContent = state.name + (state.title && state.title !== state.name ? " · " + state.title : "");
		var summary = $("de-summary");
		summary.innerHTML = "";
		state.summary.forEach(function (item) {
			summary.appendChild(el("div", {}, [el("dt", { text: item.label }), el("dd", { text: item.value || "—" })]));
		});
		$("de-details-link").href = state.details_route;
		$("de-details-link").hidden = !state.editable;
		$("de-view-link").href = state.view_route;
	}

	/* --------------------------------------------------------- left: nav */
	function paintNav() {
		var nav = $("de-nav");
		nav.innerHTML = "";
		state.sections.forEach(function (s) {
			var button = el("button", {
				type: "button", role: "tab", "aria-selected": s.key === active ? "true" : "false",
				class: "a3s-de-nav__item"
			}, [
				icon(s.icon),
				el("span", { class: "a3s-de-nav__label", text: s.label }),
				el("span", { class: "a3s-de-nav__n", text: String(s.rows.length) })
			]);
			// Choosing a table shows its saved rows and opens the popup to add one.
			button.addEventListener("click", function () {
				active = s.key;
				setStatus("", null, pageStatus);
				paint();
				openModal(null);
			});
			nav.appendChild(el("li", {}, [button]));
		});
	}

	/* ------------------------------------------------- middle: saved box */
	function paintSaved() {
		var s = section();
		$("de-saved-title").textContent = s.label;
		$("de-saved-total").textContent = money.format(lineAmount(s.key));
		$("de-add").hidden = !state.editable;
		var body = $("de-saved");
		body.innerHTML = "";
		if (!s.rows.length) {
			body.appendChild(el("p", { class: "a3s-de-empty", text: state.editable ? "Nothing saved yet. Use Add to enter the first one." : "Nothing saved." }));
			return;
		}
		var head = el("tr", {}, s.columns.map(function (c) { return el("th", { scope: "col", text: c.label }); }).concat([el("th", { "aria-label": "Actions" })]));
		var rows = s.rows.map(function (row) {
			var cells = s.columns.map(function (c) { return el("td", { text: row.display[c.fieldname] || "" }); });
			var actions = el("td", { class: "a3s-de-saved__actions" });
			if (row.computed) {
				actions.appendChild(el("span", { class: "a3s-badge", title: "Worked out by the estimate on every save", text: "Auto" }));
			} else if (state.editable) {
				var edit = el("button", { type: "button", class: "a3s-btn a3s-btn--ghost a3s-btn--sm", text: "Edit" });
				edit.addEventListener("click", function () { openModal(row); });
				var remove = el("button", { type: "button", class: "a3s-btn a3s-btn--ghost a3s-btn--sm", text: "Remove" });
				remove.addEventListener("click", function () { removeRow(row); });
				actions.appendChild(edit);
				actions.appendChild(remove);
			}
			cells.push(actions);
			return el("tr", {}, cells);
		});
		body.appendChild(el("div", { class: "a3s-de-table" }, [el("table", {}, [el("thead", {}, [head]), el("tbody", {}, rows)])]));
	}

	/* ------------------------------------------------------ middle: form */
	function options(field, values) {
		var list = state.choices[field.choices] || [];
		if (field.filter_by) {
			var by = values[field.filter_by];
			list = list.filter(function (o) { return !o.filter || !by || o.filter === by; });
		}
		return list;
	}

	function fillSelect(select, field, values) {
		var keep = values[field.fieldname] || "";
		select.innerHTML = "";
		select.appendChild(el("option", { value: "", text: "—" }));
		options(field, values).forEach(function (o) {
			select.appendChild(el("option", { value: o.value, text: o.label, selected: o.value === keep ? "selected" : null }));
		});
		if (keep && select.value !== keep) select.value = "";
	}

	function currentValues() {
		var out = {};
		Array.prototype.forEach.call(form.elements, function (input) { if (input.name) out[input.name] = input.value; });
		return out;
	}

	function paintForm() {
		var s = section();
		$("de-form-title").textContent = (editing ? "Change " : "Add ") + s.label.toLowerCase();
		submit.textContent = editing ? "Save changes" : "Add";

		var values = {};
		s.fields.forEach(function (f) {
			var v = editing ? editing.values[f.fieldname] : f.default;
			values[f.fieldname] = v === null || v === undefined ? "" : String(v);
		});

		var holder = $("de-fields");
		holder.innerHTML = "";
		s.fields.forEach(function (f) {
			var id = "de-fld-" + f.fieldname;
			var input;
			if (f.input === "select") {
				input = el("select", { id: id, name: f.fieldname });
				fillSelect(input, f, values);
			} else if (f.input === "textarea") {
				input = el("textarea", { id: id, name: f.fieldname, rows: "2" });
				input.value = values[f.fieldname];
			} else {
				input = el("input", { id: id, name: f.fieldname, type: f.input === "number" ? "number" : "text", step: f.input === "number" ? "any" : null });
				input.value = values[f.fieldname];
			}
			var label = el("label", { for: id, text: f.label });
			if (f.reqd) label.appendChild(el("span", { class: "a3s-req", text: " *" }));
			holder.appendChild(el("div", { class: "a3s-field" + (f.input === "textarea" ? " a3s-de-fields__wide" : "") }, [label, input]));
		});

		/* A make list follows the variant, type or item chosen beside it. */
		s.fields.forEach(function (f) {
			if (!f.filter_by) return;
			var source = $("de-fld-" + f.filter_by);
			if (source) source.addEventListener("change", function () { fillSelect($("de-fld-" + f.fieldname), f, currentValues()); });
		});
	}

	/* -------------------------------------------------- right: commercials */
	function paintCommercials() {
		var c = state.commercials;
		var lines = $("de-com-lines");
		lines.innerHTML = "";
		c.lines.forEach(function (line) {
			lines.appendChild(el("li", { class: line.key === active ? "is-active" : "" }, [
				el("span", { text: line.label }),
				el("strong", { text: money.format(line.amount) })
			]));
		});
		var totals = $("de-com-totals");
		totals.innerHTML = "";
		var gstLabel = "GST" + (c.gst_percent ? " (" + c.gst_percent + "%)" : "");
		[
			["Subtotal", c.subtotal, ""],
			[gstLabel, c.gst_amount, ""],
			["Total", c.total, "is-grand"]
		].forEach(function (t) {
			totals.appendChild(el("div", { class: t[2] }, [el("dt", { text: t[0] }), el("dd", { text: money.format(t[1]) })]));
		});
		if (!c.gst_percent) {
			totals.appendChild(el("p", { class: "a3s-field__hint", text: "No GST rate set. Enter Estimate GST % in A3 Sola Settings." }));
		} else {
			totals.appendChild(el("p", { class: "a3s-field__hint", text: "GST on " + money.format(c.taxable) + "; KSEB fees are already gross." }));
		}
	}

	function paint() {
		paintHeader();
		paintNav();
		paintSaved();
		paintCommercials();
	}

	/* ------------------------------------------------------------- popup */
	function openModal(row) {
		if (!state.editable) return;
		editing = row || null;
		submit.disabled = false;
		setStatus("");
		paintForm();
		modal.hidden = false;
		var first = form.querySelector("input, select, textarea");
		if (first) first.focus();
	}

	function closeModal() {
		modal.hidden = true;
		editing = null;
	}

	$("de-add").addEventListener("click", function () { openModal(null); });
	$("de-close").addEventListener("click", closeModal);
	cancel.addEventListener("click", closeModal);
	modal.addEventListener("click", function (event) { if (event.target === modal) closeModal(); });
	document.addEventListener("keydown", function (event) { if (event.key === "Escape" && !modal.hidden) closeModal(); });

	/* ------------------------------------------------------------ saving */
	function apply(next, message) {
		state = next;
		closeModal();
		paint();
		setStatus(message, "success", pageStatus);
	}

	function fail(error) {
		submit.disabled = false;
		setStatus(error.message, "error", modal.hidden ? pageStatus : status);
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		submit.disabled = true;
		setStatus("Saving…");
		call("save_row", { name: state.name, section: active, values: currentValues(), row: editing ? editing.name : null })
			.then(function (next) { submit.disabled = false; apply(next, "Saved."); })
			.catch(fail);
	});

	function removeRow(row) {
		setStatus("Removing…", null, pageStatus);
		call("remove_row", { name: state.name, section: active, row: row.name })
			.then(function (next) { apply(next, "Removed."); })
			.catch(fail);
	}

	paint();
})();
