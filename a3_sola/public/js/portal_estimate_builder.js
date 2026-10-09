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
		$("de-pdf-link").href = state.pdf_route;
		$("de-save-as").hidden = !state.can_save_as;
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
			// Choosing a table shows its saved rows; Add (or Edit on a row) opens the popup.
			button.addEventListener("click", function () {
				active = s.key;
				setStatus("", null, pageStatus);
				paint();
			});
			nav.appendChild(el("li", {}, [button]));
		});
	}

	/* ------------------------------------------------- middle: saved box */
	/* Amounts stay on one line: "₹ 1,95,000.00" broken after the sign reads as two numbers. */
	var MONEY = { rate: true, amount: true, system_cost: true };

	function paintSaved() {
		var s = section();
		$("de-saved-title").textContent = s.label;
		$("de-saved-total").textContent = money.format(lineAmount(s.key));
		$("de-add").hidden = !state.editable;
		var body = $("de-saved");
		body.innerHTML = "";
		body.appendChild(s.rows.length
			? (s.compact ? compactTable(s) : savedTable(s))
			: el("p", { class: "a3s-de-empty", text: state.editable ? "Nothing saved yet. Use Add to enter the first one." : "Nothing saved." }));
	}

	/* A row action as an icon; its name is the tooltip and what a screen reader says. */
	function iconButton(name, label, onClick, danger) {
		var button = el("button", { type: "button", class: "a3s-icon-btn" + (danger ? " a3s-icon-btn--danger" : ""),
			title: label, "aria-label": label }, [icon(name)]);
		button.addEventListener("click", onClick);
		return button;
	}

	/* Panels, inverters and batteries read as the Inverter Options do: the item in bold with
	   its detail under it, then the figures. The Option tick leads the row, labelled, so it
	   is not taken for an options tick: an Option is shown, not priced. */
	function compactTable(s) {
		var head = el("tr", {}, ["Item", "Qty \u00d7 Rate", "Amount", ""].map(function (t, i) {
			return el("th", { scope: "col", class: i && i < 3 ? "a3s-de-money" : null, text: t });
		}));
		var rows = s.rows.map(function (row) {
			var isOption = s.has_option && Number(row.values.is_option) === 1;
			var optionLabel = null;
			if (s.has_option) {
				var tick = el("input", {
					type: "checkbox", "aria-label": "Option - shown, not added to the commercials",
					checked: isOption ? "checked" : null,
					disabled: state.editable && !row.computed ? null : "disabled"
				});
				tick.addEventListener("change", function () { setOption(s, row, tick); });
				optionLabel = el("label", { class: "a3s-de-option__name", title: "Option: shown to the customer, not added to the commercials" }, [
					tick, el("span", { class: "a3s-de-option-tag", text: "Option" })
				]);
			}
			var item = el("td", {}, [
				optionLabel,
				el("strong", { class: "a3s-de-item__title" + (s.has_option ? "" : " is-first"), text: row.title || "" }),
				row.sub ? el("small", { class: "a3s-de-sub", text: row.sub }) : null,
				isOption ? el("small", { class: "a3s-de-unpriced", text: "Not priced" }) : null
			]);
			var actions = el("td", { class: "a3s-de-saved__actions" });
			if (row.computed) {
				actions.appendChild(el("span", { class: "a3s-badge", title: "Worked out by the estimate on every save", text: "Auto" }));
			} else if (state.editable) {
				actions.appendChild(iconButton("edit", "Edit", function () { openModal(row); }));
				actions.appendChild(iconButton("trash", "Remove", function () { removeRow(row); }, true));
			}
			var count = row.display[s.count_field || "nos"];
			var qty = count ? count + " \u00d7 " + (row.display.rate || "\u2014") : (row.display.rate || "");
			return el("tr", { class: isOption ? "is-off" : "" }, [
				item,
				el("td", { class: "a3s-de-money", text: qty }),
				el("td", { class: "a3s-de-money a3s-de-amount", text: row.display.amount || "" }),
				actions
			]);
		});
		return el("div", { class: "a3s-de-table a3s-de-table--compact" }, [el("table", {}, [el("thead", {}, [head]), el("tbody", {}, rows)])]);
	}

	/* One table of saved rows, with Edit and Remove on each row typed here. */
	function savedTable(s) {
		var head = el("tr", {}, s.columns.map(function (c) { return el("th", { scope: "col", text: c.label }); }).concat([el("th", { "aria-label": "Actions" })]));
		var rows = s.rows.map(function (row) {
			var cells = s.columns.map(function (c) {
				return el("td", { class: MONEY[c.fieldname] ? "a3s-de-money" : null, text: row.display[c.fieldname] || "" });
			});
			var actions = el("td", { class: "a3s-de-saved__actions" });
			if (row.computed) {
				actions.appendChild(el("span", { class: "a3s-badge", title: "Worked out by the estimate on every save", text: "Auto" }));
			} else if (state.editable) {
				actions.appendChild(iconButton("edit", "Edit", function () { openModal(row); }));
				actions.appendChild(iconButton("trash", "Remove", function () { removeRow(row); }, true));
			}
			cells.push(actions);
			return el("tr", {}, cells);
		});
		return el("div", { class: "a3s-de-table" }, [el("table", {}, [el("thead", {}, [head]), el("tbody", {}, rows)])]);
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
			var parts = [label, input];
			if (f.hint) parts.push(el("p", { class: "a3s-field__hint", text: f.hint }));
			holder.appendChild(el("div", { class: "a3s-field" + (f.input === "textarea" ? " a3s-de-fields__wide" : "") }, parts));
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

	/* WhatsApp opens with the customer's number and the estimate's summary, ready to send.
	   The window is opened at once, inside the click, so the browser does not block it. */
	$("de-whatsapp").addEventListener("click", function () {
		var win = window.open("", "_blank");
		setStatus("Opening WhatsApp…", null, pageStatus);
		call("whatsapp_link", { name: state.name })
			.then(function (link) {
				if (win) win.location.href = link; else window.location.href = link;
				setStatus("WhatsApp opened with the estimate summary. Download the PDF to send it in the chat.", "success", pageStatus);
			})
			.catch(function (error) {
				if (win) win.close();
				setStatus(error.message, "error", pageStatus);
			});
	});

	/* Save As: a copy of this estimate, with the next number, opened on its details step. */
	$("de-save-as").addEventListener("click", function () {
		var button = $("de-save-as");
		button.disabled = true;
		setStatus("Making a copy…", null, pageStatus);
		call("save_as", { name: state.name })
			.then(function (copy) {
				setStatus("Copied to " + copy.name + ". Opening it…", "success", pageStatus);
				window.location.assign(copy.route);
			})
			.catch(function (error) {
				button.disabled = false;
				setStatus(error.message, "error", pageStatus);
			});
	});

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
		/* A warning from the save (sizing with Options) is shown instead of the plain "Saved". */
		if (next.warnings && next.warnings.length) setStatus(next.warnings.join(" "), "error", pageStatus);
		else setStatus(message, "success", pageStatus);
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

	function setOption(s, row, tick) {
		setStatus("Saving…", null, pageStatus);
		call("save_row", { name: state.name, section: s.key, values: { is_option: tick.checked ? 1 : 0 }, row: row.name })
			.then(function (next) { apply(next, tick.checked ? "Marked as an option: not added to the commercials." : "Priced: this row is in the commercials, and the other rows of the table are now Options."); })
			.catch(function (error) { tick.checked = !tick.checked; fail(error); });
	}

	function removeRow(row) {
		setStatus("Removing…", null, pageStatus);
		call("remove_row", { name: state.name, section: active, row: row.name })
			.then(function (next) { apply(next, "Removed."); })
			.catch(fail);
	}

	paint();
})();
