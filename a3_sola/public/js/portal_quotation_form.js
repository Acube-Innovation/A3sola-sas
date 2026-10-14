/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The quotation page (quotations/new and quotations/<name>). Choosing the lead lists its
 * proposals and their options (api/quotation_option.options); choosing an option shows it
 * in the three tabs (option_view) - details, bill of materials and price, terms - which are
 * read, not typed. Save raises the quotation for that option, or points a draft at it
 * (save_quotation); Submit submits a saved draft.
 */
(function () {
	"use strict";

	var root = document.getElementById("a3s-qf");
	if (!root) return;

	var API = "/api/method/a3_sola.api.";
	var state = JSON.parse(document.getElementById("a3s-qf-state").textContent || "{}");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var lead = document.getElementById("fld-qf-lead");
	var box = document.getElementById("a3s-qf-options");
	var status = document.getElementById("a3s-qf-status");
	var save = document.getElementById("a3s-qf-save");
	var submit = document.getElementById("a3s-qf-submit");
	var chosen = { estimate: state.estimate || "", proposal: state.proposal || "" };

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
			document.getElementById("panel-q-" + t.dataset.tab).hidden = !on;
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

	/* ------------------------------------------------------------ the options */
	Array.prototype.forEach.call(root.querySelectorAll("[data-combo]"), window.a3sCombo.wire);
	/* A card per option: hover lifts it, a click opens its details to tell it from the
	   others (preview below), and its radio - or Choose there - picks it. */
	function optionCard(o, proposal) {
		var id = "qf-opt-" + o.estimate;
		var card = node("div", "a3s-qf__opt");
		card.tabIndex = 0;
		card.setAttribute("role", "button");
		card.setAttribute("aria-label", optionTitle(o) + " - view details");
		var radio = node("input");
		radio.type = "radio"; radio.name = "qf-option"; radio.id = id; radio.value = o.estimate;
		radio.disabled = !state.editable;
		radio.checked = o.estimate === chosen.estimate;
		radio.setAttribute("aria-label", "Choose " + optionTitle(o));
		radio.addEventListener("change", function () { choose(o.estimate, proposal); });
		radio.addEventListener("click", function (e) { e.stopPropagation(); });
		card.appendChild(radio);
		var text = node("span", "a3s-qf__opt-text");
		text.appendChild(node("b", "", optionTitle(o)));
		text.appendChild(node("small", "", optionSub(o)));
		card.appendChild(text);
		var right = node("span", "a3s-qf__opt-right");
		right.appendChild(node("span", "a3s-qf__price", o.price_text));
		right.appendChild(node("small", "a3s-qf__opt-more", "View details"));
		card.appendChild(right);
		card.addEventListener("click", function () { preview(o, proposal); });
		card.addEventListener("keydown", function (e) {
			if (e.target === card && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); preview(o, proposal); }
		});
		return card;
	}
	function optionTitle(o) {
		return (o.number ? "Option " + o.number : "Estimate") + " \u00b7 " + (o.package || o.estimate);
	}
	function optionSub(o) {
		return o.capacity_kwp + " kWp " + o.connection_type + " " + o.system_type + " \u00b7 " + o.estimate + (o.submitted ? "" : " \u00b7 draft");
	}

	/* The option in a pop-up: its facts and main components (panels, inverter, battery). */
	function preview(o, proposal) {
		var back = node("div", "a3s-modal");
		var panel = node("div", "a3s-modal__panel a3s-qf-preview");
		panel.setAttribute("role", "dialog");
		panel.setAttribute("aria-modal", "true");
		panel.setAttribute("aria-label", optionTitle(o));
		var head = node("div", "a3s-qf-preview__head");
		var titles = node("div");
		titles.appendChild(node("h3", "a3s-qf-preview__title", optionTitle(o)));
		titles.appendChild(node("p", "a3s-qf-preview__sub", optionSub(o) + (proposal ? " \u00b7 Proposal " + proposal : "")));
		head.appendChild(titles);
		head.appendChild(node("strong", "a3s-qf-preview__price", o.price_text));
		var close = node("button", "a3s-qf-preview__x", "\u00d7");
		close.type = "button";
		close.setAttribute("aria-label", "Close");
		head.appendChild(close);
		var body = node("div", "a3s-qf-preview__body");
		body.appendChild(node("p", "a3s-field__hint", "Loading the option\u2026"));
		var foot = node("div", "a3s-form__actions a3s-qf-preview__foot");
		var isChosen = o.estimate === chosen.estimate;
		if (state.editable) {
			var pick = node("button", "a3s-btn a3s-btn--primary", isChosen ? "Chosen" : "Choose this option");
			pick.type = "button";
			pick.disabled = isChosen;
			pick.addEventListener("click", function () { choose(o.estimate, proposal, true); shut(); });
			foot.appendChild(pick);
		}
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

		call("quotation_option.option_view", { estimate: o.estimate, proposal: proposal })
			.then(function (v) {
				body.innerHTML = "";
				[["preview", "Details"]].forEach(function (part) {
					if (!(v || {})[part[0]]) return;
					var section = node("section", "a3s-qf-preview__part");
					section.appendChild(node("h4", "a3s-qf-preview__label", part[1]));
					var html = node("div");
					html.innerHTML = v[part[0]];
					section.appendChild(html);
					body.appendChild(section);
				});
			})
			.catch(function (e) { body.innerHTML = ""; body.appendChild(node("p", "a3s-form__status is-error", e.message)); });
	}
	function paintOptions(data) {
		box.innerHTML = "";
		(data.proposals || []).forEach(function (p) {
			var group = node("div", "a3s-qf__group");
			group.appendChild(node("p", "a3s-qf__group-title", "Proposal " + p.name + (p.version > 1 ? " · version " + p.version : "") + " · " + p.date + " · " + p.status));
			p.options.forEach(function (o) { group.appendChild(optionCard(o, p.name)); });
			box.appendChild(group);
		});
		if ((data.loose || []).length) {
			var group = node("div", "a3s-qf__group");
			group.appendChild(node("p", "a3s-qf__group-title", "Estimates not in a proposal"));
			data.loose.forEach(function (o) { group.appendChild(optionCard(o, "")); });
			box.appendChild(group);
		}
		if (!box.children.length) box.appendChild(node("p", "a3s-field__hint", lead.value ? "This lead has no proposal yet. Make one first." : ""));
	}
	function loadOptions() {
		if (!lead.value) { box.innerHTML = ""; return Promise.resolve(); }
		say("Loading the lead's proposals…");
		return call("quotation_option.options", { lead: lead.value }).then(function (data) {
			say("");
			paintOptions(data || {});
			// Opened from a proposal: its Option 1, the base, unless one is chosen already.
			if (!chosen.estimate && chosen.proposal) {
				var p = (data.proposals || []).filter(function (x) { return x.name === chosen.proposal; })[0];
				if (p && p.options.length) choose(p.options[0].estimate, p.name, true);
			}
		}).catch(function (e) { say(e.message, "error"); });
	}
	function choose(estimate, proposal, check) {
		chosen = { estimate: estimate, proposal: proposal };
		if (check) {
			var radio = document.getElementById("qf-opt-" + estimate);
			if (radio) radio.checked = true;
		}
		if (save) save.disabled = false;
		paintTabs();
	}
	function paintTabs() {
		if (!chosen.estimate) return;
		Array.prototype.forEach.call(root.querySelectorAll("[data-html]"), function (el) { el.classList.add("is-loading"); });
		call("quotation_option.option_view", { estimate: chosen.estimate, proposal: chosen.proposal, quotation: state.name })
			.then(function (v) {
				Array.prototype.forEach.call(root.querySelectorAll("[data-html]"), function (el) {
					el.innerHTML = (v || {})[el.dataset.html] || "";
					el.classList.remove("is-loading");
				});
			})
			.catch(function (e) { say(e.message, "error"); });
	}
	lead.addEventListener("change", function () { chosen = { estimate: "", proposal: "" }; if (save) save.disabled = true; loadOptions(); });

	/* ------------------------------------------------------------ save and submit */
	if (save) save.addEventListener("click", function () {
		if (!chosen.estimate) { say("Choose an option first.", "error"); return; }
		save.disabled = true;
		say(state.name ? "Saving…" : "Raising the quotation…");
		call("quotation_option.save_quotation", { estimate: chosen.estimate, proposal: chosen.proposal, name: state.name }, true)
			.then(function (res) { say("Saved. Opening it…", "success"); window.location.assign(res.route); })
			.catch(function (e) { save.disabled = false; say(e.message, "error"); });
	});
	if (submit) submit.addEventListener("click", function () {
		submit.disabled = true;
		say("Submitting…");
		call("cost_estimate.submit", { name: state.name }, true)
			.then(function () { window.location.reload(); })
			.catch(function (e) { submit.disabled = false; say(e.message, "error"); });
	});

	/* ------------------------------------------------------------ start */
	if (!state.editable) {
		var search = document.getElementById("fld-qf-lead-search");
		if (search) { search.disabled = true; search.title = "A submitted quotation keeps its option"; }
	}
	if (state.lead) {
		lead.value = state.lead;
		lead.dispatchEvent(new Event("a3s:sync"));
	}
	loadOptions().then(function () { if (state.estimate) choose(state.estimate, state.proposal, true); });
	if (save && state.name) save.disabled = false;
})();
