/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The proposal page (proposals/new and proposals/<name>/edit), in the desk form's two
 * tabs. Choosing the lead fills its consumer, survey, customer and site details and its
 * design estimates, from api/portal_proposal.lead_details. The estimates can be
 * reordered (the first is the base), removed and added back; Design Comparison shows
 * them compared. Save posts the fields and the estimates in order to save_proposal; the
 * proposal's own validate works out the rest.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-pp-form");
	if (!form) return;

	var API = "/api/method/a3_sola.api.portal_proposal.";
	var name = form.dataset.name || "";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var state = JSON.parse(document.getElementById("a3s-pp-state").textContent || "{}");
	var status = document.getElementById("a3s-pp-status");
	var submit = document.getElementById("a3s-pp-submit");
	var CUSTOMER = ["salutation", "customer_name", "mobile_no", "email_id", "location", "district"];
	var touched = {};

	function field(f) { return document.getElementById("fld-" + f); }
	function node(tag, cls, text) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text !== undefined) n.textContent = text;
		return n;
	}
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

	/* ------------------------------------------------------------ tabs */
	var tabs = Array.prototype.slice.call(form.querySelectorAll("[data-tab]"));
	function showTab(key) {
		tabs.forEach(function (t) {
			var on = t.dataset.tab === key;
			t.setAttribute("aria-selected", on ? "true" : "false");
			t.tabIndex = on ? 0 : -1;
			document.getElementById("panel-" + t.dataset.tab).hidden = !on;
		});
		if (key === "comparison") renderComparison();
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

	/* ------------------------------------------------------------ search boxes */
	Array.prototype.forEach.call(form.querySelectorAll("[data-combo]"), window.a3sCombo.wire);
	function setField(f, value) {
		var el = field(f);
		if (!el || el.value === (value || "")) return;
		el.value = value || "";
		el.dispatchEvent(new Event("a3s:sync"));
	}

	/* A lead lists only its consumers; a consumer only its surveys. */
	var lead = field("lead"), consumer = field("solar_consumer"), survey = field("site_survey");
	/* An issued proposal belongs to its lead and consumer: shown, not changed. */
	if (form.dataset.issued) {
		[lead, consumer].forEach(function (el) {
			el.disabled = true;
			var box = document.getElementById(el.id + "-search");
			if (box) { box.disabled = true; box.title = "Fixed once the proposal is issued"; }
		});
	}
	function narrow() {
		Array.prototype.forEach.call(consumer.options, function (o) {
			var off = !!(o.value && lead.value && o.dataset.lead && o.dataset.lead !== lead.value);
			o.hidden = off; o.disabled = off;
		});
		Array.prototype.forEach.call(survey.options, function (o) {
			var off = !!(o.value && consumer.value && o.dataset.consumer !== consumer.value);
			o.hidden = off; o.disabled = off;
		});
	}

	/* ------------------------------------------------------------ filling from the lead */
	CUSTOMER.forEach(function (f) {
		var el = field(f);
		if (el) el.addEventListener("input", function () { touched[f] = true; });
		if (el) el.addEventListener("change", function () { touched[f] = true; });
	});
	var request = 0;
	function fill(fromConsumer) {
		narrow();
		var mine = ++request;
		if (!lead.value) {
			apply({ values: {}, site: state.site, rows: [], available: [], existing: null }, false);
			return;
		}
		say("Filling in from the lead…");
		call("lead_details", { lead: lead.value, solar_consumer: fromConsumer ? consumer.value : "", proposal: name })
			.then(function (data) { if (mine === request) { apply(data, fromConsumer); say(""); } })
			.catch(function (e) { if (mine === request) say(e.message, "error"); });
	}
	function apply(data, fromConsumer) {
		var values = data.values || {};
		if (!fromConsumer) setField("solar_consumer", values.solar_consumer);
		setField("site_survey", values.site_survey);
		narrow();
		CUSTOMER.forEach(function (f) { if (!touched[f] && f in values) setField(f, values[f]); });
		state.site = (data.site || state.site || []).map(function (s) {
			return Object.keys(values).length ? s : { fieldname: s.fieldname, label: s.label, value: "" };
		});
		state.rows = (data.rows || []).slice();
		state.available = (data.available || []).slice();
		state.existing = data.existing || null;
		paint();
	}
	lead.addEventListener("change", function () { fill(false); });
	consumer.addEventListener("change", function () { if (lead.value) fill(true); else narrow(); });

	/* ------------------------------------------------------------ painting */
	function paintSite() {
		var dl = document.getElementById("a3s-pp-site");
		dl.innerHTML = "";
		(state.site || []).forEach(function (s) {
			var row = node("div");
			row.appendChild(node("dt", "", s.label));
			var v = s.value;
			var dd = node("dd");
			if (s.fieldname === "google_location_url" && v) {
				var a = node("a", "", "Open map"); a.href = v; a.target = "_blank"; a.rel = "noopener";
				dd.appendChild(a);
			} else {
				dd.textContent = v || "—";
			}
			row.appendChild(dd);
			dl.appendChild(row);
		});
	}
	function rowButton(label, title, onClick, disabled) {
		var b = node("button", "a3s-btn a3s-btn--ghost a3s-btn--sm", label);
		b.type = "button"; b.title = title; b.setAttribute("aria-label", title);
		b.disabled = !!disabled;
		b.addEventListener("click", onClick);
		return b;
	}
	function move(i, by) {
		var r = state.rows.splice(i, 1)[0];
		state.rows.splice(i + by, 0, r);
		paint();
	}
	function paintRows() {
		var body = document.getElementById("a3s-pp-rows");
		body.innerHTML = "";
		state.rows.forEach(function (r, i) {
			var tr = node("tr");
			if (i === 0) tr.className = "is-base";
			tr.appendChild(node("td", "", String(i + 1)));
			var td = node("td");
			var a = node("a", "", r.name); a.href = r.route;
			td.appendChild(a);
			if (r.draft) td.appendChild(node("span", "a3s-pp__draft", "Draft"));
			tr.appendChild(td);
			var base = node("td");
			if (i === 0) base.appendChild(node("span", "a3s-pp__base", "Base"));
			tr.appendChild(base);
			tr.appendChild(node("td", "", r.date));
			tr.appendChild(node("td", "", r.package || "—"));
			tr.appendChild(node("td", "a3s-num", String(r.capacity_kw)));
			tr.appendChild(node("td", "a3s-num", r.total_label));
			var act = node("td", "a3s-lf__row-actions");
			act.appendChild(rowButton("↑", "Move up" + (i === 1 ? " (make it the base)" : ""), function () { move(i, -1); }, i === 0));
			act.appendChild(rowButton("↓", "Move down", function () { move(i, 1); }, i === state.rows.length - 1));
			var rm = rowButton("Remove", "Remove " + r.name, function () { state.rows.splice(i, 1); paint(); });
			rm.classList.add("a3s-lf__remove");
			act.appendChild(rm);
			tr.appendChild(act);
			body.appendChild(tr);
		});
		document.getElementById("a3s-pp-empty").hidden = !!state.rows.length;
		body.closest(".a3s-tablewrap").hidden = !state.rows.length;
		document.getElementById("a3s-pp-count").textContent = String(state.rows.length);

		/* What can be added back: the lead's estimates not in the table. */
		var listed = state.rows.map(function (r) { return r.name; });
		var spare = (state.available || []).filter(function (r) { return listed.indexOf(r.name) === -1; });
		var add = document.getElementById("a3s-pp-add");
		var pick = document.getElementById("a3s-pp-add-select");
		pick.innerHTML = "";
		spare.forEach(function (r) {
			var o = node("option", "", r.name + (r.package ? " · " + r.package : "") + " · " + r.total_label);
			o.value = r.name;
			pick.appendChild(o);
		});
		add.hidden = !spare.length;
	}
	document.getElementById("a3s-pp-add-btn").addEventListener("click", function () {
		var pick = document.getElementById("a3s-pp-add-select");
		var r = (state.available || []).filter(function (x) { return x.name === pick.value; })[0];
		if (r) { state.rows.push(r); paint(); }
	});
	function paintExisting() {
		var box = document.getElementById("a3s-pp-existing");
		box.innerHTML = "";
		box.hidden = !state.existing;
		if (!state.existing) return;
		box.appendChild(document.createTextNode("This lead already has proposal "));
		var a = node("a", "", state.existing.name); a.href = state.existing.route;
		box.appendChild(a);
		box.appendChild(document.createTextNode(". A lead has one proposal: open it to add a version rather than making a second."));
	}

	/* The comparison follows the table, fetched when its tab is shown or the rows change. */
	var compared = null, compareTimer = null;
	function renderComparison() {
		var names = state.rows.map(function (r) { return r.name; });
		var key = names.join("|");
		var box = document.getElementById("a3s-pp-comparison");
		if (key === compared) return;
		compared = key;
		if (!names.length) {
			box.innerHTML = "";
			box.appendChild(node("p", "a3s-field__hint", "Add design estimates on the Proposal Details tab to compare them here."));
			return;
		}
		box.classList.add("is-loading");
		fetch("/api/method/a3_sola.api.proposal_comparison.get_design_comparison?estimates=" + encodeURIComponent(JSON.stringify(names)), {
			credentials: "same-origin", headers: { "Accept": "application/json" }
		}).then(function (r) { return r.json(); })
		  .then(function (data) { if (compared === key) box.innerHTML = (data && data.message) || ""; })
		  .catch(function () { compared = null; })
		  .then(function () { box.classList.remove("is-loading"); });
	}

	function paint() {
		paintSite();
		paintRows();
		paintExisting();
		clearTimeout(compareTimer);
		if (!document.getElementById("panel-comparison").hidden) compareTimer = setTimeout(renderComparison, 250);
	}

	/* ------------------------------------------------------------ save */
	form.addEventListener("submit", function (e) {
		e.preventDefault();
		if (!lead.value) { say("Choose the lead this proposal is for.", "error"); showTab("details"); return; }
		var values = {};
		["lead", "solar_consumer", "site_survey", "proposal_date", "remarks"].concat(CUSTOMER).forEach(function (f) {
			var el = field(f);
			if (el) values[f] = el.value;
		});
		submit.disabled = true;
		say(name ? "Saving…" : "Creating the proposal…");
		call("save_proposal", { values: values, estimates: state.rows.map(function (r) { return r.name; }), name: name }, true)
			.then(function (res) {
				say(name ? "Saved. Opening the proposal…" : "Created. Opening the proposal…", "success");
				window.location.assign(res.route);
			})
			.catch(function (err) {
				submit.disabled = false;
				say(err.message, "error");
			});
	});

	narrow();
	paint();
})();
