/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The sales order page (sales-orders/new and sales-orders/<name>), as the quotation page is.
 * Choosing the lead lists its quotations (api/sales_order_option.quotations), each said
 * orderable or why not; one must be chosen. Choosing it shows it in the three tabs
 * (quotation_view) - order details, bill of materials, terms. Save raises the order from it
 * with the dates asked, or saves a draft (save_order); Submit saves and then submits it.
 */
(function () {
	"use strict";

	var root = document.getElementById("a3s-sf");
	if (!root) return;

	var API = "/api/method/a3_sola.api.";
	var state = JSON.parse(document.getElementById("a3s-sf-state").textContent || "{}");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var lead = document.getElementById("fld-sf-lead");
	var box = document.getElementById("a3s-sf-quotes");
	var status = document.getElementById("a3s-sf-status");
	var save = document.getElementById("a3s-sf-save");
	var submit = document.getElementById("a3s-sf-submit");
	var dates = {
		transaction_date: document.getElementById("fld-sf-transaction_date"),
		delivery_date: document.getElementById("fld-sf-delivery_date")
	};
	var chosen = state.quotation || "";
	var cards = {};

	function say(text, kind) {
		status.textContent = text || "";
		status.classList.toggle("is-error", kind === "error");
		status.classList.toggle("is-success", kind === "success");
	}
	function serverMessage(data) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			var last = msgs.length ? JSON.parse(msgs[msgs.length - 1]) : null;
			if (last && last.message) return String(last.message).replace(/<br\s*\/?>/g, " ").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception) ? String(data.exception).split(":").slice(1).join(":").trim() : "";
	}
	function call(method, args, post) {
		var opts = { credentials: "same-origin", headers: { "Accept": "application/json" } };
		var url = API + method;
		if (post) {
			opts.method = "POST";
			opts.headers["Content-Type"] = "application/json";
			opts.headers["X-Frappe-CSRF-Token"] = csrf;
			opts.body = JSON.stringify(args);
		} else {
			url += "?" + Object.keys(args).map(function (k) { return k + "=" + encodeURIComponent(args[k] || ""); }).join("&");
		}
		return fetch(url, opts).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (data) {
				if (!r.ok) throw new Error(serverMessage(data) || "That did not work. Try again.");
				return data.message;
			});
		});
	}
	function node(tag, cls, text) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text !== undefined) n.textContent = text;
		return n;
	}

	/* ------------------------------------------------------------ tabs */
	var tabs = Array.prototype.slice.call(root.querySelectorAll("[data-tab]"));
	function showTab(key) {
		tabs.forEach(function (t) {
			var on = t.dataset.tab === key;
			t.setAttribute("aria-selected", on ? "true" : "false");
			t.tabIndex = on ? 0 : -1;
			document.getElementById("panel-so-" + t.dataset.tab).hidden = !on;
		});
	}
	tabs.forEach(function (t, i) {
		t.addEventListener("click", function () { showTab(t.dataset.tab); });
		t.addEventListener("keydown", function (e) {
			if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
			var next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
			next.focus();
			showTab(next.dataset.tab);
		});
	});

	/* ------------------------------------------------------------ the quotations */
	Array.prototype.forEach.call(root.querySelectorAll("[data-combo]"), window.a3sCombo.wire);
	/* A quotation may be chosen when it is submitted and not ordered yet - or is this order's own. */
	function choosable(c) { return c.orderable || (state.name && c.quotation === state.quotation); }
	function title(c) { return c.quotation + (c.package ? " · " + c.package : ""); }
	function sub(c) {
		var parts = [];
		if (c.capacity_kwp) parts.push(c.capacity_kwp + " kWp " + c.connection_type + " " + c.system_type);
		if (c.option) parts.push(c.option);
		parts.push(c.date + " · " + c.status);
		return parts.join(" · ");
	}
	/* A card per quotation: a click opens its details (preview below); its radio - or Choose
	   there - picks it. One that cannot be ordered says why and cannot be picked. */
	function card(c) {
		var ok = choosable(c);
		var el = node("div", "a3s-qf__opt" + (ok ? "" : " is-off"));
		el.tabIndex = 0;
		el.setAttribute("role", "button");
		el.setAttribute("aria-label", title(c) + " - view details");
		var radio = node("input");
		radio.type = "radio"; radio.name = "sf-quote"; radio.id = "sf-q-" + c.quotation; radio.value = c.quotation;
		radio.disabled = !state.editable || !ok;
		radio.checked = c.quotation === chosen;
		radio.setAttribute("aria-label", "Choose " + title(c));
		radio.addEventListener("change", function () { choose(c.quotation); });
		radio.addEventListener("click", function (e) { e.stopPropagation(); });
		el.appendChild(radio);
		var text = node("span", "a3s-qf__opt-text");
		text.appendChild(node("b", "", title(c)));
		text.appendChild(node("small", "", sub(c)));
		if (!ok) text.appendChild(node("small", "a3s-sf__why", c.reason));
		el.appendChild(text);
		var right = node("span", "a3s-qf__opt-right");
		right.appendChild(node("span", "a3s-qf__price", c.total_text));
		right.appendChild(node("small", "a3s-qf__opt-more", "View details"));
		el.appendChild(right);
		el.addEventListener("click", function () { preview(c); });
		el.addEventListener("keydown", function (e) {
			if (e.target === el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); preview(c); }
		});
		return el;
	}

	/* The quotation in a pop-up: who and what, its value and main components. */
	function preview(c) {
		var back = node("div", "a3s-modal");
		var panel = node("div", "a3s-modal__panel a3s-qf-preview");
		panel.setAttribute("role", "dialog");
		panel.setAttribute("aria-modal", "true");
		panel.setAttribute("aria-label", title(c));
		var head = node("div", "a3s-qf-preview__head");
		var titles = node("div");
		titles.appendChild(node("h3", "a3s-qf-preview__title", title(c)));
		titles.appendChild(node("p", "a3s-qf-preview__sub", sub(c)));
		head.appendChild(titles);
		head.appendChild(node("strong", "a3s-qf-preview__price", c.total_text));
		var close = node("button", "a3s-qf-preview__x", "×");
		close.type = "button";
		close.setAttribute("aria-label", "Close");
		head.appendChild(close);
		var body = node("div", "a3s-qf-preview__body");
		body.appendChild(node("p", "a3s-field__hint", "Loading the quotation…"));
		var foot = node("div", "a3s-form__actions a3s-qf-preview__foot");
		if (!choosable(c)) foot.appendChild(node("p", "a3s-form__status is-error", c.reason));
		if (state.editable && choosable(c)) {
			var isChosen = c.quotation === chosen;
			var pick = node("button", "a3s-btn a3s-btn--primary", isChosen ? "Chosen" : "Choose this quotation");
			pick.type = "button";
			pick.disabled = isChosen;
			pick.addEventListener("click", function () { choose(c.quotation, true); shut(); });
			foot.appendChild(pick);
		}
		var open = node("a", "a3s-btn a3s-btn--ghost", "Open quotation");
		open.href = c.route;
		foot.appendChild(open);
		var done = node("button", "a3s-btn a3s-btn--ghost", "Close");
		done.type = "button";
		foot.appendChild(done);
		panel.appendChild(head); panel.appendChild(body); panel.appendChild(foot);
		back.appendChild(panel);

		function onKey(e) { if (e.key === "Escape") shut(); }
		function shut() { back.remove(); document.removeEventListener("keydown", onKey); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back) shut(); });
		close.addEventListener("click", shut);
		done.addEventListener("click", shut);
		document.body.appendChild(back);
		close.focus();

		call("sales_order_option.quotation_view", { quotation: c.quotation, order: state.name })
			.then(function (v) { body.innerHTML = (v || {}).preview || ""; })
			.catch(function (e) { body.innerHTML = ""; body.appendChild(node("p", "a3s-form__status is-error", e.message)); });
	}

	function paint(list) {
		box.innerHTML = "";
		cards = {};
		list.forEach(function (c) { cards[c.quotation] = c; box.appendChild(card(c)); });
		if (!list.length && lead.value) {
			var none = node("p", "a3s-field__hint", "This lead has no quotation yet. ");
			var make = node("a", "", "Make one first.");
			make.href = "/a3solaportal/quotations/new?source_dt=Lead&source=" + encodeURIComponent(lead.value);
			none.appendChild(make);
			box.appendChild(none);
		}
	}
	function loadQuotes() {
		if (!lead.value && !state.name) { box.innerHTML = ""; return Promise.resolve([]); }
		say("Loading the lead's quotations…");
		return call("sales_order_option.quotations", { lead: lead.value, order: state.name }).then(function (list) {
			say("");
			paint(list || []);
			return list || [];
		}).catch(function (e) { say(e.message, "error"); return []; });
	}
	function choose(quotation, check) {
		chosen = quotation;
		if (check) {
			var radio = document.getElementById("sf-q-" + quotation);
			if (radio) radio.checked = true;
		}
		if (save) save.disabled = false;
		paintTabs();
	}
	function paintTabs() {
		var blank = "<p class=\"a3s-field__hint\">Choose a quotation above to see it here.</p>";
		Array.prototype.forEach.call(root.querySelectorAll("[data-html]"), function (el) {
			if (!chosen) el.innerHTML = blank;
			el.classList.toggle("is-loading", !!chosen);
		});
		if (!chosen) return;
		call("sales_order_option.quotation_view", { quotation: chosen, order: state.name })
			.then(function (v) {
				Array.prototype.forEach.call(root.querySelectorAll("[data-html]"), function (el) {
					el.innerHTML = (v || {})[el.dataset.html] || "";
					el.classList.remove("is-loading");
				});
			})
			.catch(function (e) { say(e.message, "error"); });
	}
	lead.addEventListener("change", function () {
		chosen = "";
		if (save) save.disabled = true;
		paintTabs();
		loadQuotes();
	});

	/* ------------------------------------------------------------ dates */
	/* Deliveries are on working days (the order's validate says so too): said here as it is typed. */
	if (dates.delivery_date) dates.delivery_date.addEventListener("change", function () {
		var v = dates.delivery_date.value;
		var day = v ? new Date(v + "T00:00:00").getDay() : -1;
		say(day === 0 || day === 6 ? "That is a " + (day === 0 ? "Sunday" : "Saturday") + ": deliveries are on working days." : "",
			day === 0 || day === 6 ? "error" : "");
	});
	function values() {
		var out = {};
		Object.keys(dates).forEach(function (k) { if (dates[k]) out[k] = dates[k].value; });
		return out;
	}

	/* ------------------------------------------------------------ save and submit */
	function saveOrder() {
		if (!chosen) { say("Choose a quotation first: an order is raised from one.", "error"); return Promise.reject(null); }
		if (dates.delivery_date && !dates.delivery_date.value) {
			say("Choose the delivery date.", "error");
			showTab("details");
			dates.delivery_date.focus();
			return Promise.reject(null);
		}
		return call("sales_order_option.save_order", { quotation: chosen, values: values(), name: state.name }, true);
	}
	if (save) save.addEventListener("click", function () {
		save.disabled = true;
		say(state.name ? "Saving…" : "Raising the sales order…");
		saveOrder()
			.then(function (res) { say("Saved. Opening it…", "success"); window.location.assign(res.route); })
			.catch(function (e) { save.disabled = false; if (e) say(e.message, "error"); });
	});
	if (submit) submit.addEventListener("click", function () {
		submit.disabled = true;
		say("Submitting…");
		saveOrder()
			.then(function () { return call("portal_crud.submit_record", { slug: "sales-orders", name: state.name }, true); })
			.then(function () { window.location.reload(); })
			.catch(function (e) { submit.disabled = false; if (e) say(e.message, "error"); });
	});

	/* ------------------------------------------------------------ start */
	if (!state.editable) {
		var search = document.getElementById("fld-sf-lead-search");
		if (search) { search.disabled = true; search.title = "A submitted order keeps its quotation"; }
	}
	if (state.lead) {
		lead.value = state.lead;
		lead.dispatchEvent(new Event("a3s:sync"));
	}
	loadQuotes().then(function () {
		var c = cards[chosen];
		if (chosen && c && choosable(c)) { choose(chosen, true); return; }
		/* Opened from a quotation that cannot be ordered: say why, and choose nothing. */
		if (chosen && c) say(c.quotation + ": " + c.reason + ".", "error");
		chosen = "";
		if (save) save.disabled = true;
	});
})();
