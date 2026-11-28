/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Administration > Event Packages (www/a3solaportal/event-packages, api/event_package_rules):
 * the company's rules - a 2-month bill range and the visitor's answers, and the package they
 * get - checked top to bottom. Rows are added, removed and moved here; Save posts them all in
 * their order. "Check a visitor" shows what the event would quote for a set of answers.
 */
(function () {
	"use strict";

	var dataEl = document.getElementById("a3s-evpkg-data");
	var body = document.querySelector("[data-evpkg-rows]");
	if (!dataEl || !body) return;
	var data = JSON.parse(dataEl.textContent || "{}");
	var save = document.querySelector("[data-evpkg-save]");
	var status = document.querySelector("[data-evpkg-status]");
	var count = document.querySelector("[data-evpkg-count]");
	var addBtn = document.querySelector("[data-evpkg-add]");
	var companySel = document.querySelector("[data-evpkg-company]");
	var tryForm = document.querySelector("[data-evpkg-try]");
	var result = document.querySelector("[data-evpkg-result]");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
	var API = "/api/method/a3_sola.api.event_package_rules.";
	var savedState = "";

	function el(tag, attrs, kids) {
		var n = document.createElement(tag);
		Object.keys(attrs || {}).forEach(function (k) {
			var v = attrs[k];
			if (v === null || v === undefined || v === false) return;
			if (k === "text") n.textContent = v;
			else if (k === "class") n.className = v;
			else n.setAttribute(k, v === true ? "" : v);
		});
		(kids || []).forEach(function (c) { if (c) n.appendChild(c); });
		return n;
	}
	function setStatus(text, tone) {
		status.textContent = text || "";
		status.dataset.tone = tone || "";
		status.hidden = !text;
	}
	function errorOf(r, body, fallback) {
		var msg = "";
		try { msg = JSON.parse(JSON.parse(body._server_messages || "[]")[0] || "{}").message || ""; } catch (e) { /* none */ }
		if (r.status === 403 && !msg) msg = "You do not have permission to do that.";
		return new Error(msg || fallback || "That did not go through. Try again.");
	}
	function post(method, fields) {
		var form = new FormData();
		Object.keys(fields).forEach(function (k) { form.append(k, fields[k]); });
		return fetch(API + method, { method: "POST", credentials: "same-origin", body: form,
			headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } })
			.catch(function () { throw new Error("Could not reach the server. Check your connection and try again."); })
			.then(function (r) {
				return r.json().catch(function () { return {}; }).then(function (b) {
					if (!r.ok) throw errorOf(r, b);
					return b.message || {};
				});
			});
	}

	/* ---------------------------------------------------------------- the table */
	function selectOf(field, options, value, label) {
		var s = el("select", { "data-field": field, "aria-label": label });
		options.forEach(function (o) {
			var opt = el("option", { value: o.value, text: o.label });
			if (o.value === value) opt.selected = true;
			s.appendChild(opt);
		});
		return el("div", { class: "a3s-field" }, [s]);
	}
	function rowOf(rule) {
		var tr = el("tr");
		var no = el("span", { class: "a3s-evpkg__no" });
		var up = el("button", { type: "button", "data-move": "-1", "aria-label": "Move up", text: "▲" });
		var down = el("button", { type: "button", "data-move": "1", "aria-label": "Move down", text: "▼" });
		tr.appendChild(el("td", { "data-label": "#" }, [no, el("span", { class: "a3s-evpkg__move" }, [up, down])]));
		["bill_from", "bill_to"].forEach(function (f) {
			var input = el("input", { type: "number", min: "0", step: "1", inputmode: "numeric", "data-field": f,
				placeholder: f === "bill_to" ? "No limit" : "0", "aria-label": f === "bill_to" ? "Bill to" : "Bill from" });
			var v = rule[f];
			input.value = v === null || v === undefined || (f === "bill_to" && !v) ? "" : String(Math.round(v));
			tr.appendChild(el("td", { class: "a3s-evpkg__money", "data-label": f === "bill_to" ? "Bill to (₹)" : "Bill from (₹)" },
				[el("div", { class: "a3s-field" }, [input])]));
		});
		data.questions.forEach(function (q) {
			var opts = data.choices[q.field].map(function (o) { return { value: o, label: o }; });
			tr.appendChild(el("td", { class: "a3s-evpkg__ans", "data-label": q.label },
				[selectOf(q.field, opts, rule[q.field] || "Any", q.label)]));
		});
		var pkgOpts = [{ value: "", label: "Choose the package…" }].concat(data.packages);
		tr.appendChild(el("td", { class: "a3s-evpkg__pkg", "data-label": "Package" },
			[selectOf("package", pkgOpts, rule.package || "", "Package")]));
		var active = el("input", { type: "checkbox", "data-field": "is_active", "aria-label": "Active" });
		active.checked = rule.is_active === undefined ? true : !!rule.is_active;
		tr.appendChild(el("td", { "data-label": "Active" }, [el("label", { class: "a3s-check" }, [active])]));
		var del = el("button", { type: "button", class: "a3s-evpkg__del", "data-remove": "1", "aria-label": "Remove this rule" });
		del.innerHTML = '<svg class="a3s-ic" aria-hidden="true"><use href="#ic-trash"></use></svg>';
		tr.appendChild(el("td", {}, [del]));
		tr.dataset.saved = JSON.stringify(valuesOf(tr));
		if (!rule.name) tr.dataset.saved = "";
		return tr;
	}
	function rows() { return Array.prototype.slice.call(body.querySelectorAll("tr[data-saved]")); }
	function valuesOf(tr) {
		var v = {};
		Array.prototype.forEach.call(tr.querySelectorAll("[data-field]"), function (f) {
			v[f.dataset.field] = f.type === "checkbox" ? (f.checked ? 1 : 0) : f.value.trim();
		});
		return v;
	}
	function state() { return JSON.stringify(rows().map(valuesOf)); }
	function render() {
		body.innerHTML = "";
		if (!data.rules.length) body.appendChild(emptyRow());
		data.rules.forEach(function (r) { body.appendChild(rowOf(r)); });
		savedState = state();
		refresh();
	}
	function emptyRow() {
		return el("tr", { "data-empty": "1" }, [el("td", { colspan: String(6 + data.questions.length), class: "a3s-evpkg__empty",
			text: "No rules yet. Every visitor's package is chosen automatically. Add a rule to choose it yourself." })]);
	}
	function refresh() {
		var list = rows();
		var empty = body.querySelector("[data-empty]");
		if (list.length && empty) empty.remove();
		if (!list.length && !empty) body.appendChild(emptyRow());
		var changed = 0;
		list.forEach(function (tr, i) {
			tr.querySelector(".a3s-evpkg__no").textContent = String(i + 1);
			tr.querySelector('[data-move="-1"]').disabled = i === 0;
			tr.querySelector('[data-move="1"]').disabled = i === list.length - 1;
			var isChanged = JSON.stringify(valuesOf(tr)) !== tr.dataset.saved;
			tr.classList.toggle("is-changed", isChanged);
			tr.classList.toggle("is-off", !tr.querySelector('[data-field="is_active"]').checked);
			if (isChanged) changed++;
		});
		var dirty = state() !== savedState;
		save.disabled = !dirty;
		var active = list.filter(function (tr) { return tr.querySelector('[data-field="is_active"]').checked; }).length;
		count.textContent = list.length + (list.length === 1 ? " rule" : " rules") +
			(active !== list.length ? " · " + active + " active" : "") + (dirty ? " · unsaved changes" : "");
	}

	body.addEventListener("input", function () { setStatus(""); refresh(); });
	body.addEventListener("change", function () { setStatus(""); refresh(); });
	body.addEventListener("click", function (e) {
		var tr = e.target.closest("tr[data-saved]");
		if (!tr) return;
		var move = e.target.closest("[data-move]");
		if (move && !move.disabled) {
			if (move.dataset.move === "-1" && tr.previousElementSibling) body.insertBefore(tr, tr.previousElementSibling);
			else if (move.dataset.move === "1" && tr.nextElementSibling) body.insertBefore(tr.nextElementSibling, tr);
			refresh();
			move.focus();
		} else if (e.target.closest("[data-remove]")) {
			tr.remove();
			refresh();
		}
	});
	addBtn.addEventListener("click", function () {
		var last = rows().slice(-1)[0];
		var seed = { is_active: 1 };
		if (last) {
			var v = valuesOf(last);
			// The next range starts where the last one ended, with the same answers.
			seed = Object.assign({}, v, { bill_from: v.bill_to ? Number(v.bill_to) + 1 : null, bill_to: null, package: "" });
		}
		var tr = rowOf(seed);
		body.appendChild(tr);
		refresh();
		tr.querySelector('[data-field="bill_from"]').focus();
	});

	save.addEventListener("click", function () {
		var list = rows();
		for (var i = 0; i < list.length; i++) {
			var v = valuesOf(list[i]);
			if (!v.package) { setStatus("Rule " + (i + 1) + ": choose the package.", "error"); list[i].querySelector('[data-field="package"]').focus(); return; }
			if (v.bill_to && Number(v.bill_to) < Number(v.bill_from || 0)) {
				setStatus("Rule " + (i + 1) + ": Bill to is below Bill from.", "error");
				list[i].querySelector('[data-field="bill_to"]').focus();
				return;
			}
		}
		save.disabled = true;
		setStatus("Saving…");
		post("save", { company: data.company, rows: JSON.stringify(list.map(valuesOf)) })
			.then(function (res) {
				data = res.data;
				render();
				setStatus("Saved. Event visitors get these packages from now on.", "ok");
			})
			.catch(function (err) { setStatus(err.message, "error"); refresh(); });
	});

	if (companySel) companySel.addEventListener("change", function () {
		if (state() !== savedState && !window.confirm("Leave your unsaved changes for " + data.company + "?")) {
			companySel.value = data.company;
			return;
		}
		setStatus("Loading…");
		fetch(API + "load?company=" + encodeURIComponent(companySel.value), { credentials: "same-origin", headers: { Accept: "application/json" } })
			.then(function (r) { return r.json().then(function (b) { if (!r.ok) throw errorOf(r, b); return b.message; }); })
			.then(function (d) { data = d; render(); setStatus(""); if (result) result.hidden = true; })
			.catch(function (err) { companySel.value = data.company; setStatus(err.message, "error"); });
	});
	window.addEventListener("beforeunload", function (e) {
		if (state() !== savedState) { e.preventDefault(); e.returnValue = ""; }
	});

	/* ---------------------------------------------------------------- check a visitor */
	if (tryForm) tryForm.addEventListener("submit", function (e) {
		e.preventDefault();
		var fields = {};
		Array.prototype.forEach.call(tryForm.elements, function (f) { if (f.name) fields[f.name] = f.value; });
		result.hidden = false;
		result.innerHTML = "";
		result.appendChild(el("p", { class: "a3s-attach__status", text: "Checking…" }));
		post("check", { company: data.company, data: JSON.stringify(fields) })
			.then(function (res) { showResult(res); })
			.catch(function (err) {
				result.innerHTML = "";
				result.appendChild(el("p", { class: "a3s-attach__status", "data-tone": "error", text: err.message }));
			});
	});
	function showResult(res) {
		var est = res.estimate || {};
		result.innerHTML = "";
		var how = res.rule_no ? "Rule " + res.rule_no + " matched." :
			est.custom ? "No rule matched, and no package covers this bill: the event shows a custom estimate for our engineer to design." :
			"No rule matched: the package was chosen automatically.";
		result.appendChild(el("p", { class: "a3s-attach__status", "data-tone": res.rule_no ? "ok" : "warn",
			text: how + " A 2-month bill of " + money.format(res.two_month_bill) + "." }));
		var items = [
			["Package", est.package_name || (est.custom ? "Custom " + est.kw_min + "–" + est.kw_max + " kW" : "—")],
			["Size", est.kw ? est.kw + " kW" : "—"],
			["Connection", est.connection_type || "—"],
			["Price", est.price ? money.format(est.price) : "—"],
			["Subsidy", est.subsidy ? money.format(est.subsidy) : "—"],
			["After subsidy", est.net ? money.format(est.net) : "—"],
		];
		result.appendChild(el("dl", {}, items.map(function (it) {
			return el("div", {}, [el("dt", { text: it[0] }), el("dd", { text: it[1] })]);
		})));
	}

	render();
})();
