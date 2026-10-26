/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Step two of the design estimate builder: a tab per option chosen on step one, then
 * Compare. In a tab - left: the System & Options tables; middle: the chosen table's rows,
 * a row added or changed in a popup; right: what each table costs, the tax and the total.
 *
 * A change is worked out on the server at once - counts, expense rows and prices are its to
 * work out - and held, with the tab's other changes, until the tab's Save. The recommended
 * option saves this estimate; any other option is saved as an estimate of its own for the
 * same lead. Additional structure, cable and discount rows are records of their own and are
 * kept as they are made, on a saved option only.
 */
(function () {
	"use strict";

	var dataEl = document.getElementById("a3s-de-data");
	if (!dataEl) return;

	var page = JSON.parse(dataEl.textContent);  // {tabs, option, root, details_route, state}
	var COMPARE = "__compare__";
	var LINKED = { additional_structure: true, additional_cable: true, special_discount: true };
	var option = page.option;      // the tab on show: an option row's name, or COMPARE
	var state = page.state;        // that tab as last worked out
	var cache = {};                // option -> state, so a tab comes back as it was left
	var pending = {};              // option -> its unsaved changes, in order
	var comparison = null;         // the last Compare, or null when it is out of date
	cache[option] = state;
	var active = (state.sections[0] || {}).key;
	var editing = null; // the row being changed, or null when adding
	var busy = false;

	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

	var $ = function (id) { return document.getElementById(id); };
	var form = $("de-form");
	var submit = $("de-submit");
	var cancel = $("de-cancel");
	var status = $("de-status");
	var pageStatus = $("de-page-status");
	var tabStatus = $("de-tab-status");
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

	function tab(key) {
		return page.tabs.find(function (t) { return t.key === key; }) || null;
	}

	function changes(key) {
		return pending[key] || [];
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
				if (!r.ok || !data.message) throw new Error(serverMessage(data) || "Could not work that out. Try again.");
				return data.message;
			});
		});
	}

	/* ------------------------------------------------------------ tabs */
	function tabStatusText(t) {
		if (!t.estimate) return "Not saved";
		if (t.estimate === page.root) return "This estimate";
		return "Saved as " + t.estimate;
	}

	function paintTabs() {
		var bar = $("de-tabs");
		bar.innerHTML = "";
		page.tabs.forEach(function (t) {
			var dirty = changes(t.key).length > 0;
			var button = el("button", {
				type: "button", role: "tab", class: "a3s-de-tab" + (t.estimate ? "" : " is-unsaved"),
				"aria-selected": t.key === option ? "true" : "false", disabled: busy ? "disabled" : null
			}, [
				el("span", { class: "a3s-de-tab__top" }, [
					el("strong", { text: "Option " + t.number }),
					t.recommended ? el("span", { class: "a3s-de-tab__chip", text: "Recommended" }) : null,
					dirty ? el("span", { class: "a3s-de-tab__dot", title: "Unsaved changes", "aria-label": "Unsaved changes" }) : null
				]),
				el("span", { class: "a3s-de-tab__package", text: t.package + (t.capacity ? " · " + t.capacity : "") }),
				t.parts.length ? el("span", { class: "a3s-de-tab__parts", text: t.parts.join(" · ") }) : null,
				el("span", { class: "a3s-de-tab__state", text: tabStatusText(t) + (dirty ? " · unsaved changes" : "") })
			]);
			button.addEventListener("click", function () { selectTab(t.key); });
			var holder = el("div", { class: "a3s-de-tabwrap" }, [button]);
			/* The cross takes the option off the estimate, after asking. */
			if (page.can_remove && t.key) {
				var cross = el("button", { type: "button", class: "a3s-de-tab__x", title: "Remove Option " + t.number,
					"aria-label": "Remove Option " + t.number, disabled: busy ? "disabled" : null, text: "\u00d7" });
				cross.addEventListener("click", function (event) { event.stopPropagation(); removeOption(t); });
				holder.appendChild(cross);
			}
			bar.appendChild(holder);
		});
		if (page.tabs.length > 1) {
			var compare = el("button", {
				type: "button", role: "tab", class: "a3s-de-tab a3s-de-tab--compare",
				"aria-selected": option === COMPARE ? "true" : "false", disabled: busy ? "disabled" : null
			}, [icon("stack"), el("strong", { text: "Compare" }), el("span", { class: "a3s-de-tab__state", text: page.tabs.length + " options side by side" })]);
			compare.addEventListener("click", function () { selectTab(COMPARE); });
			bar.appendChild(compare);
		}
		/* Save all: every option saved in turn. */
		if (page.tabs.some(function (t) { return t.docstatus !== 1; })) {
			var saveAll = el("button", { type: "button", class: "a3s-square-btn a3s-de-saveall-btn", title: "Save all options",
				"aria-label": "Save all options", disabled: busy ? "disabled" : null }, [icon("save")]);
			saveAll.addEventListener("click", saveAllOptions);
			bar.appendChild(saveAll);
		}
	}

	/* ---------------------------------------------- remove an option */
	/* With `work`, the dialog stays open on OK while it runs: the button spins, nothing else
	   can be pressed, and a failure closes it and rejects with the error. */
	function confirmDialog(title, text, ok, work, working) {
		var box = $("de-confirm"), okButton = $("de-confirm-ok"), cancel = $("de-confirm-cancel");
		$("de-confirm-title").textContent = title;
		$("de-confirm-text").textContent = text;
		okButton.textContent = ok;
		okButton.disabled = cancel.disabled = false;
		okButton.classList.remove("is-busy");
		okButton.removeAttribute("aria-busy");
		box.hidden = false;
		cancel.focus();
		return new Promise(function (resolve, reject) {
			var running = false;
			function close() {
				box.hidden = true;
				okButton.onclick = cancel.onclick = box.onclick = document.onkeydown = null;
				okButton.disabled = cancel.disabled = false;
				okButton.classList.remove("is-busy");
				okButton.removeAttribute("aria-busy");
			}
			function done(answer) {
				if (running) return;
				close();
				resolve(answer);
			}
			okButton.onclick = function () {
				if (!work) return done(true);
				if (running) return;
				running = true;
				okButton.disabled = cancel.disabled = true;
				okButton.classList.add("is-busy");
				okButton.setAttribute("aria-busy", "true");
				okButton.textContent = working || ok;
				Promise.resolve().then(work).then(function () {
					// Left open: the work ends by moving the page on.
					resolve(true);
				}, function (error) {
					running = false;
					close();
					reject(error);
				});
			};
			cancel.onclick = function () { done(false); };
			box.onclick = function (event) { if (event.target === box) done(false); };
			document.onkeydown = function (event) { if (event.key === "Escape") done(false); };
		});
	}

	function removeOption(t) {
		if (busy) return;
		var notes = [];
		if (t.recommended) notes.push("It is the recommended option, so the next option becomes the recommended one and this estimate is rebuilt on it.");
		if (t.estimate && t.estimate !== page.root) notes.push("It is saved as " + t.estimate + ", which is kept as an estimate of its own.");
		if (changes(t.key).length) notes.push("Its unsaved changes are lost.");
		confirmDialog("Remove Option " + t.number + "?",
			t.package + (t.parts.length ? " (" + t.parts.join(" \u00b7 ") + ")" : "") + " is taken off this estimate's options. " + notes.join(" "),
			"Remove option",
			function () {
				begin("Removing Option " + t.number + "\u2026", tabStatus);
				pending[t.key] = [];
				return call("remove_option", { name: page.root, option: t.key })
					.then(function (result) {
						// Unsaved changes in the other tabs go with the reload; it was asked.
						pending = {};
						window.location.assign(result.route);
					});
			},
			"Removing\u2026")
			.catch(function (error) { fail(error, tabStatus); });
	}

	/* --------------------------------------------------- save all options */
	function saveAllOptions() {
		if (busy) return;
		var tabs = page.tabs.slice();
		var box = $("de-saveall"), list = $("de-saveall-list"), close = $("de-saveall-close");
		var saved = 0, failed = 0;
		list.innerHTML = "";
		close.disabled = true;
		$("de-saveall-title").textContent = "Saving all options";
		setStatus("", null, $("de-saveall-status"));
		box.hidden = false;
		busy = true;
		paintTabs();

		function progress(done) {
			var pct = Math.round(done * 100 / tabs.length);
			$("de-saveall-bar").style.width = pct + "%";
			$("de-saveall-progress").setAttribute("aria-valuenow", String(pct));
			$("de-saveall-count").textContent = done + " of " + tabs.length + " options";
		}
		function label(t) { return "Option " + t.number + " \u00b7 " + t.package; }

		progress(0);
		var chain = Promise.resolve();
		tabs.forEach(function (t, i) {
			chain = chain.then(function () {
				var line = el("li", { class: "is-working" }, [el("span", { text: label(t) }), el("small", { text: "Saving\u2026" })]);
				list.appendChild(line);
				if (t.docstatus === 1) {
					line.className = "is-skipped";
					line.lastChild.textContent = "Submitted as " + t.estimate + ": not changed";
					progress(i + 1);
					return;
				}
				return call("save_tab", { name: page.root, option: t.key, ops: changes(t.key) })
					.then(function (payload) {
						pending[t.key] = [];
						cache[t.key] = payload.state;
						page.tabs = payload.tabs;
						page.details_route = payload.details_route;
						page.can_remove = payload.can_remove;
						saved += 1;
						line.className = "is-done";
						line.lastChild.textContent = "Saved as " + payload.state.name + (payload.state.name === page.root ? " (this estimate)" : "");
					})
					.catch(function (error) {
						failed += 1;
						line.className = "is-failed";
						line.lastChild.textContent = "Not saved: " + error.message;
					})
					.then(function () { progress(i + 1); });
			});
		});
		chain.then(function () {
			busy = false;
			comparison = null;
			$("de-saveall-title").textContent = failed ? "Saved, with problems" : "All options saved";
			setStatus(failed ? saved + " saved, " + failed + " not saved: see above." : "All " + saved + " options are saved.",
				failed ? "error" : "success", $("de-saveall-status"));
			close.disabled = false;
			close.focus();
		});
	}

	$("de-saveall-close").addEventListener("click", function () {
		$("de-saveall").hidden = true;
		// The tab on show stays, now with the estimate it was saved as.
		if (option !== COMPARE && cache[option]) {
			state = cache[option];
			keepActive();
		}
		paint();
		if (option === COMPARE) loadCompare();
	});

	function selectTab(key) {
		if (busy || key === option) return;
		option = key;
		setStatus("", null, tabStatus);
		setStatus("", null, pageStatus);
		if (key === COMPARE) {
			paint();
			loadCompare();
			return;
		}
		if (cache[key]) {
			state = cache[key];
			keepActive();
			paint();
			return;
		}
		work(key, changes(key), "");
	}

	function keepActive() {
		if (!state.sections.some(function (s) { return s.key === active; })) active = (state.sections[0] || {}).key;
	}

	/* ------------------------------------------------------------ header */
	function paintHeader() {
		/* The title is the estimate on show: a saved option's own ID, else this estimate's. */
		var shown = option !== COMPARE && state.saved && state.name ? state.name : page.root;
		$("de-title").textContent = shown + (state.title && state.title !== shown ? " · " + state.title : "");
		$("de-details-link").href = page.details_route || "#";
		$("de-details-link").hidden = !page.details_route;
		var comparing = option === COMPARE;
		$("de-tabhead").hidden = comparing;
		$("a3s-de-builder").hidden = comparing;
		$("de-compare").hidden = !comparing;
		if (comparing) return;

		var t = tab(option) || { number: 1, package: "", estimate: state.name, recommended: true };
		var dirty = changes(option).length > 0;
		$("de-tab-name").textContent = "Option " + t.number + (t.recommended ? " (recommended)" : "") + " · " + tabStatusText(t);
		var summary = $("de-summary");
		summary.innerHTML = "";
		state.summary.forEach(function (item) {
			summary.appendChild(el("div", {}, [el("dt", { text: item.label }), el("dd", { text: item.value || "—" })]));
		});

		/* The PDF and WhatsApp send what is saved, so they wait for the changes to be saved. */
		$("de-pdf-link").href = state.pdf_route || "#";
		$("de-pdf-link").hidden = !state.saved || dirty;
		$("de-whatsapp").hidden = !state.saved || dirty;
		$("de-discard").hidden = !dirty || busy;
		var save = $("de-save");
		var canSave = state.editable && (dirty || !state.saved);
		save.hidden = !state.editable && state.saved;
		save.disabled = busy || !canSave;
		$("de-save-label").textContent = !state.saved
			? "Save as new estimate"
			: (dirty ? "Save changes" : "Saved");
		save.title = !state.saved
			? "Saves this option as an estimate of its own for the same lead"
			: (dirty ? "Saves the changes made in this tab to " + state.name : "Nothing to save in this tab");
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
			// Choosing a table shows its rows; Add (or Edit on a row) opens the popup.
			button.addEventListener("click", function () {
				active = s.key;
				setStatus("", null, pageStatus);
				paint();
			});
			nav.appendChild(el("li", {}, [button]));
		});
		if (!state.saved) {
			nav.appendChild(el("li", { class: "a3s-de-nav__note", text: "Additional structure, cable and discount can be added once this option is saved." }));
		}
	}

	/* ------------------------------------------------- middle: rows box */
	/* Amounts stay on one line: "₹ 1,95,000.00" broken after the sign reads as two numbers. */
	var MONEY = { rate: true, amount: true, system_cost: true };

	function paintSaved() {
		var s = section();
		$("de-saved-title").textContent = s.label;
		/* Optional add-ons are offered beside the system: their own sum, not a commercials line. */
		var unpriced = s.unpriced_total !== null && s.unpriced_total !== undefined;
		$("de-saved-total").textContent = money.format(unpriced ? s.unpriced_total : lineAmount(s.key));
		$("de-saved-total").title = unpriced ? "Optional: not added to the total" : "";
		$("de-add").hidden = !state.editable;
		$("de-add").disabled = busy;
		var body = $("de-saved");
		body.innerHTML = "";
		body.appendChild(s.rows.length
			? (s.compact ? compactTable(s) : savedTable(s))
			: el("p", { class: "a3s-de-empty", text: state.editable ? "Nothing here yet. Use Add to enter the first one." : "Nothing here." }));
	}

	/* A row action as an icon; its name is the tooltip and what a screen reader says. */
	function iconButton(name, label, onClick, danger) {
		var button = el("button", { type: "button", class: "a3s-icon-btn" + (danger ? " a3s-icon-btn--danger" : ""),
			title: label, "aria-label": label, disabled: busy ? "disabled" : null }, [icon(name)]);
		button.addEventListener("click", onClick);
		return button;
	}

	function rowActions(row) {
		var actions = el("td", { class: "a3s-de-saved__actions" });
		if (row.computed) {
			actions.appendChild(el("span", { class: "a3s-badge", title: "Worked out by the estimate on every change", text: "Auto" }));
		} else if (state.editable) {
			actions.appendChild(iconButton("edit", "Edit", function () { openModal(row); }));
			actions.appendChild(iconButton("trash", "Remove", function () { removeRow(row); }, true));
		}
		return actions;
	}

	/* Panels, inverters and batteries read as the Inverter Options do: the item in bold with
	   its detail under it, then the figures. The Option tick leads the row, labelled, so it
	   is not taken for an options tick: an Option is shown, not priced. */
	function compactTable(s) {
		var head = el("tr", {}, ["Item", "Qty × Rate", "Amount", ""].map(function (t, i) {
			return el("th", { scope: "col", class: i && i < 3 ? "a3s-de-money" : null, text: t });
		}));
		var rows = s.rows.map(function (row) {
			var isOption = s.has_option && Number(row.values.is_option) === 1;
			var optionLabel = null;
			if (s.has_option) {
				var tick = el("input", {
					type: "checkbox", "aria-label": "Option - shown, not added to the commercials",
					checked: isOption ? "checked" : null,
					disabled: state.editable && !row.computed && !busy ? null : "disabled"
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
			var count = row.display[s.count_field || "nos"];
			var qty = count ? count + " × " + (row.display.rate || "—") : (row.display.rate || "");
			if (row.included) qty = count ? count + " nos" : "";
			return el("tr", { class: isOption ? "is-off" : "" }, [
				item,
				el("td", { class: "a3s-de-money", text: qty }),
				row.included && !isOption
					? el("td", { class: "a3s-de-money" }, [el("span", { class: "a3s-de-included", text: "In package" })])
					: el("td", { class: "a3s-de-money a3s-de-amount", text: isOption ? "" : (row.display.amount || "") }),
				rowActions(row)
			]);
		});
		return el("div", { class: "a3s-de-table a3s-de-table--compact" }, [el("table", {}, [el("thead", {}, [head]), el("tbody", {}, rows)])]);
	}

	/* One table of rows, with Edit and Remove on each row typed here. */
	function savedTable(s) {
		var head = el("tr", {}, s.columns.map(function (c) { return el("th", { scope: "col", text: c.label }); }).concat([el("th", { "aria-label": "Actions" })]));
		var rows = s.rows.map(function (row) {
			var cells = s.columns.map(function (c) {
				if (row.included && MONEY[c.fieldname]) {
					return el("td", { class: "a3s-de-money" }, c.fieldname === "amount" ? [el("span", { class: "a3s-de-included", text: "In package" })] : []);
				}
				return el("td", { class: MONEY[c.fieldname] ? "a3s-de-money" : null, text: row.display[c.fieldname] || "" });
			});
			cells.push(rowActions(row));
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
		submit.textContent = editing ? "Apply changes" : "Add";

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
		/* With a package, its price covers its own items: a line shows only when something is
		   charged on it, or when it is the table being worked on. */
		var hasPackage = c.lines.some(function (l) { return l.key === "package"; });
		c.lines.filter(function (line) {
			return !hasPackage || line.key === "package" || line.key === active || Number(line.amount);
		}).forEach(function (line) {
			var isPackage = line.key === "package";
			lines.appendChild(el("li", { class: (line.key === active ? "is-active" : "") + (isPackage ? " is-package" : "") }, [
				el("span", {}, [
					isPackage ? el("small", { class: "a3s-de-com__kicker", text: "Package price" }) : null,
					document.createTextNode(line.label)
				]),
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

		var proposal = $("de-proposal");
		proposal.innerHTML = "";
		var action = state.proposal_action;
		if (action && !changes(option).length) {
			proposal.appendChild(el("a", { class: "a3s-btn a3s-btn--primary a3s-btn--block a3s-de-com__proposal", href: action.href }, [
				icon("doc"), el("span", { text: action.label })
			]));
			proposal.appendChild(el("p", { class: "a3s-edit__hint", text: action.hint }));
		} else if (!state.saved) {
			proposal.appendChild(el("p", { class: "a3s-edit__hint", text: "Save this option to add it to a proposal." }));
		}
	}

	/* ------------------------------------------------------------- compare */
	function paintCompare() {
		var body = $("de-compare-body");
		body.innerHTML = "";
		if (!comparison) return;
		var cols = comparison;
		var lowest = null;
		cols.forEach(function (c) { if (!c.error && (lowest === null || c.total < lowest)) lowest = c.total; });

		var head = el("tr", {}, [el("th", { scope: "col", text: "" })].concat(cols.map(function (c) {
			var open = el("button", { type: "button", class: "a3s-textlink", text: "Option " + c.number });
			open.addEventListener("click", function () { selectTab(c.key); });
			return el("th", { scope: "col", class: "a3s-de-money" }, [
				open,
				c.recommended ? el("small", { class: "a3s-de-sub", text: "Recommended" }) : null,
				el("small", { class: "a3s-de-sub", text: (c.estimate ? (c.estimate === page.root ? "This estimate" : c.estimate) : "Not saved") + (c.unsaved ? " · unsaved changes" : "") })
			]);
		})));

		var rows = [];
		function row(label, values, cls) {
			rows.push(el("tr", { class: cls || "" }, [el("th", { scope: "row", text: label })].concat(values.map(function (v, i) {
				return el("td", { class: "a3s-de-money" + (cols[i].error ? " is-error" : ""), text: v });
			}))));
		}
		function pick(fn) { return cols.map(function (c) { return c.error ? "" : fn(c); }); }

		row("Package", cols.map(function (c) { return c.package; }));
		row("Proposed size", pick(function (c) { return c.size; }));
		row("Panels", pick(function (c) { return c.panel_kwp; }));
		row("Inverters", pick(function (c) { return c.inverter_kw; }));
		row("Package price", pick(function (c) { return c.package_cost; }));
		row("Solar panel", pick(function (c) { return c.panel; }));
		row("Inverter", pick(function (c) { return c.inverter; }));
		if (cols.some(function (c) { return c.battery; })) row("Battery", pick(function (c) { return c.battery || "—"; }));
		var keys = [];
		/* Lines in the order of the option with the most of them, so a battery sits where it does there. */
		cols.slice().sort(function (a, b) { return (b.lines || []).length - (a.lines || []).length; }).forEach(function (c) {
			(c.lines || []).forEach(function (l) { if (!keys.some(function (k) { return k.key === l.key; })) keys.push({ key: l.key, label: l.label }); });
		});
		keys.forEach(function (k) {
			row(k.label, pick(function (c) {
				var line = (c.lines || []).find(function (l) { return l.key === k.key; });
				return money.format(line ? line.amount : 0);
			}), "is-line");
		});
		row("Subtotal", pick(function (c) { return money.format(c.subtotal); }), "is-sum");
		row("GST", pick(function (c) { return money.format(c.gst_amount); }));
		rows.push(el("tr", { class: "is-grand" }, [el("th", { scope: "row", text: "Total" })].concat(cols.map(function (c) {
			return el("td", { class: "a3s-de-money" + (!c.error && c.total === lowest && cols.length > 1 ? " is-best" : "") },
				c.error ? [el("small", { class: "a3s-de-compare__error", text: c.error })] : [document.createTextNode(money.format(c.total))]);
		}))));
		body.appendChild(el("table", { class: "a3s-de-compare__table" }, [el("thead", {}, [head]), el("tbody", {}, rows)]));
	}

	function loadCompare() {
		comparison = null;
		paintCompare();
		setStatus("Working out every option…", null, $("de-compare-status"));
		busy = true;
		paintTabs();
		call("compare", { name: page.root, pending: pending })
			.then(function (result) {
				comparison = result;
				setStatus(Object.keys(pending).some(function (k) { return pending[k].length; })
					? "Unsaved changes are included. Save them in their tabs to keep them." : "", null, $("de-compare-status"));
			})
			.catch(function (error) { setStatus(error.message, "error", $("de-compare-status")); })
			.then(function () { busy = false; paintTabs(); paintCompare(); });
	}

	function paint() {
		paintTabs();
		paintHeader();
		if (option === COMPARE) return;
		paintNav();
		paintSaved();
		paintCommercials();
	}

	/* ------------------------------------------------------------- popup */
	function openModal(row) {
		if (!state.editable || busy) return;
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
		setStatus("Opening WhatsApp…", null, tabStatus);
		call("whatsapp_link", { name: state.name })
			.then(function (link) {
				if (win) win.location.href = link; else window.location.href = link;
				setStatus("WhatsApp opened with the estimate summary. Download the PDF to send it in the chat.", "success", tabStatus);
			})
			.catch(function (error) {
				if (win) win.close();
				setStatus(error.message, "error", tabStatus);
			});
	});

	$("de-add").addEventListener("click", function () { openModal(null); });
	$("de-close").addEventListener("click", closeModal);
	cancel.addEventListener("click", closeModal);
	modal.addEventListener("click", function (event) { if (event.target === modal) closeModal(); });
	document.addEventListener("keydown", function (event) { if (event.key === "Escape" && !modal.hidden) closeModal(); });

	/* ------------------------------------------------- changes and saving */
	function apply(payload, key, message, target) {
		page.tabs = payload.tabs;
		page.details_route = payload.details_route;
		cache[key] = payload.state;
		comparison = null;
		if (key === option) {
			state = payload.state;
			keepActive();
		}
		closeModal();
		paint();
		/* A warning from the change (sizing with Options) is shown instead of the plain message. */
		if (payload.state.warnings && payload.state.warnings.length) setStatus(payload.state.warnings.join(" "), "error", target || pageStatus);
		else setStatus(message, "success", target || pageStatus);
	}

	function begin(text, target) {
		busy = true;
		setStatus(text, null, target || pageStatus);
		paint();
	}

	function end() {
		busy = false;
		submit.disabled = false;
		paint();
	}

	function fail(error, target) {
		end();
		setStatus(error.message, "error", modal.hidden ? (target || pageStatus) : status);
	}

	/* Work a tab out with these changes; they become its unsaved changes if it works. */
	function work(key, ops, message) {
		begin("Working it out…", key === option ? pageStatus : tabStatus);
		return call("tab_state", { name: page.root, option: key, ops: ops })
			.then(function (payload) {
				pending[key] = ops;
				busy = false;
				apply(payload, key, message);
			})
			.catch(fail);
	}

	function change(item, message) {
		var key = option;
		return work(key, changes(key).concat([item]), message);
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		submit.disabled = true;
		setStatus("Working it out…");
		var values = currentValues();
		var row = editing ? editing.name : null;
		if (LINKED[active]) {
			linkedChange("save_linked_row", { section: active, values: values, row: row }, "Saved.");
			return;
		}
		change({ section: active, values: values, row: row }, "Changed. Save the tab to keep it.");
	});

	/* A failed change repaints the tab as it was, so the tick goes back by itself. */
	function setOption(s, row, tick) {
		change({ section: s.key, values: { is_option: tick.checked ? 1 : 0 }, row: row.name },
			tick.checked ? "Marked as an option: not added to the commercials. Save the tab to keep it."
				: "Priced: this row is in the commercials, and the other rows of the table are now Options. Save the tab to keep it.");
	}

	function removeRow(row) {
		if (LINKED[active]) {
			linkedChange("remove_linked_row", { section: active, row: row.name }, "Removed.");
			return;
		}
		change({ section: active, row: row.name, action: "remove" }, "Removed. Save the tab to keep it.");
	}

	/* Additional structure, cable and discount are records of their own: kept at once. */
	function linkedChange(method, args, message) {
		var key = option;
		begin("Saving…");
		call(method, Object.assign({ name: page.root, option: key, ops: changes(key) }, args))
			.then(function (payload) { busy = false; apply(payload, key, message); })
			.catch(fail);
	}

	$("de-save").addEventListener("click", function () {
		var key = option;
		var wasSaved = state.saved;
		begin(wasSaved ? "Saving…" : "Saving as a new estimate…", tabStatus);
		call("save_tab", { name: page.root, option: key, ops: changes(key) })
			.then(function (payload) {
				pending[key] = [];
				busy = false;
				apply(payload, key, wasSaved ? "Saved." : "Saved as " + payload.state.name + ", for the same lead.", tabStatus);
			})
			.catch(function (error) { fail(error, tabStatus); });
	});

	$("de-discard").addEventListener("click", function () {
		if (!window.confirm("Discard the changes made in this tab?")) return;
		work(option, [], "Changes discarded.");
	});

	/* Unsaved changes are only in this page: leaving it asks first. */
	window.addEventListener("beforeunload", function (event) {
		if (Object.keys(pending).some(function (k) { return pending[k].length; })) {
			event.preventDefault();
			event.returnValue = "";
		}
	});

	paint();
})();
