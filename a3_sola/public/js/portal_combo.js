/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The portal's search-select, shared by the forms that pick a lead, consumer or survey
 * (the design estimate details, the proposal). `a3sCombo.wire(wrap)` puts a search box
 * over the <select> inside `wrap`. Setting the select from a script and dispatching
 * "a3s:sync" on it updates the box - as does setting its value or rebuilding its options.
 * `a3sCombo.wireAll(root)` wires every [data-combo] field under root.
 *
 * Optional, on the wrap: data-combo-limit="10" shows only the first ten matches (the rest are
 * found by typing), and data-combo-open opens the list as soon as the box is focused.
 */
(function () {
	"use strict";

	function node(tag, cls, text) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text !== undefined) n.textContent = text;
		return n;
	}

	/* Lead, consumer and the other link fields can run to hundreds of records, so each gets a
	   search box over its select: typing narrows the list, clicking or arrowing down opens it
	   whole. The select stays the field - hidden, still named, still firing change - so the
	   profile and the save read it as before. */
	var comboCount = 0;
	function wireCombo(wrap) {
		var select = wrap.querySelector("select");
		if (!select || wrap.dataset.comboWired) return;
		wrap.dataset.comboWired = "1";
		/* data-combo-add names what can be added from the list ("section"): its last entry
		   offers it, and choosing that fires "a3s:combo-add" on the select with what was typed. */
		var adds = wrap.dataset.comboAdd || "";
		var limit = parseInt(wrap.dataset.comboLimit, 10) || 0;
		var openOnFocus = wrap.hasAttribute("data-combo-open");
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
		/* Options switched off by a filter (the lead narrowing the consumers) are not offered. */
		function choices() {
			return Array.prototype.filter.call(select.options, function (o) { return o.value && !o.disabled; });
		}
		/* The box shows what was chosen; an option named after something else (a survey,
		   after its consumer) also shows its id, since one consumer can have several. */
		function labelOf(value) {
			var o = choices().filter(function (c) { return c.value === value; })[0];
			if (!o) return "";
			return o.dataset.showId ? o.textContent + " \u00b7 " + o.value : o.textContent;
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
			var more = 0;
			if (limit && shown.length > limit) { more = shown.length - limit; shown = shown.slice(0, limit); }
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
			if (more) list.appendChild(node("p", "a3s-combo__more", more + " more: keep typing to find them."));
			if (adds) {
				var add = node("button", "a3s-combo__opt a3s-combo__add");
				add.type = "button";
				add.tabIndex = -1;
				add.textContent = "+ Add a new " + adds + (query && query.trim() ? " “" + query.trim() + "”" : "");
				add.addEventListener("mousedown", function (e) {
					e.preventDefault();
					var typed = (query || "").trim();
					close();
					input.value = labelOf(select.value);
					select.dispatchEvent(new CustomEvent("a3s:combo-add", { bubbles: true, detail: { query: typed } }));
				});
				list.appendChild(add);
			}
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
		/* Set from the script rather than picked here: show what the field now holds. */
		function sync() { if (document.activeElement !== input) input.value = labelOf(select.value); input.disabled = select.disabled; }
		select.addEventListener("a3s:sync", sync);
		select.addEventListener("change", sync);
		/* Other scripts set the select's value directly (a bill read, a lead's details) or
		   rebuild its options (a list that follows its parent): the box follows both. */
		var native = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
		Object.defineProperty(select, "value", {
			configurable: true,
			get: function () { return native.get.call(select); },
			set: function (v) { native.set.call(select, v); sync(); }
		});
		if (window.MutationObserver) {
			new MutationObserver(sync).observe(select, { childList: true, attributes: true, attributeFilter: ["disabled"] });
		}
		input.addEventListener("focus", function () { input.select(); if (openOnFocus && list.hidden) render(""); });
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

	/* Every [data-combo] field under `root` not wired yet: the portal's create and edit forms. */
	function wireAll(root) {
		Array.prototype.forEach.call((root || document).querySelectorAll("[data-combo]"), wireCombo);
	}

	window.a3sCombo = { wire: wireCombo, wireAll: wireAll };
})();
