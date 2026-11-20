/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Administration > Task Assignees (www/a3solaportal/task-assignees, api/task_defaults): each
 * task's default position, person, when it starts and its SLA days. A changed row is marked; Save posts the rows
 * and reloads. Find filters the rows by name or code.
 */
(function () {
	"use strict";

	var body = document.querySelector("[data-taskdef-rows]");
	if (!body) return;
	var save = document.querySelector("[data-taskdef-save]");
	var status = document.querySelector("[data-taskdef-status]");
	var find = document.querySelector("[data-taskdef-find]");
	var count = document.querySelector("[data-taskdef-count]");
	var total = document.querySelector("[data-taskdef-total]");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var rows = Array.prototype.slice.call(body.querySelectorAll("tr[data-row]"));

	function valuesOf(tr) {
		var v = { name: tr.dataset.row };
		Array.prototype.forEach.call(tr.querySelectorAll("[data-field]"), function (el) { v[el.dataset.field] = el.value; });
		v.sla_days = String(parseInt(v.sla_days, 10) || 0);
		return v;
	}
	var saved = {};
	rows.forEach(function (tr) { saved[tr.dataset.row] = JSON.stringify(valuesOf(tr)); });

	function setStatus(text, tone) {
		status.textContent = text || "";
		status.dataset.tone = tone || "";
		status.hidden = !text;
	}
	function changedRows() {
		return rows.filter(function (tr) { return JSON.stringify(valuesOf(tr)) !== saved[tr.dataset.row]; });
	}
	function refresh() {
		var changed = changedRows();
		rows.forEach(function (tr) { tr.classList.toggle("is-changed", changed.indexOf(tr) !== -1); });
		save.disabled = !changed.length;
		var sum = rows.reduce(function (s, tr) { return s + (parseInt(valuesOf(tr).sla_days, 10) || 0); }, 0);
		if (total) total.textContent = sum + " days";
		var shown = rows.filter(function (tr) { return !tr.hidden; }).length;
		if (count) count.textContent = (shown === rows.length ? rows.length + " tasks" : shown + " of " + rows.length + " tasks") +
			(changed.length ? " · " + changed.length + " changed" : "");
	}

	body.addEventListener("change", function (e) {
		if (e.target.dataset.field === "start_trigger") {
			var after = e.target.closest("td").querySelector(".a3s-taskdef__after");
			after.hidden = e.target.value !== "After another task";
			if (!after.hidden) after.querySelector("select").focus();
		}
		setStatus("");
		refresh();
	});
	body.addEventListener("input", function (e) { if (e.target.dataset.field === "sla_days") refresh(); });
	if (find) find.addEventListener("input", function () {
		var q = find.value.trim().toLowerCase();
		rows.forEach(function (tr) { tr.hidden = !!q && tr.dataset.find.indexOf(q) === -1; });
		refresh();
	});
	window.addEventListener("beforeunload", function (e) {
		if (changedRows().length) { e.preventDefault(); e.returnValue = ""; }
	});

	save.addEventListener("click", function () {
		var changed = changedRows();
		var bad = changed.filter(function (tr) {
			var n = parseInt(tr.querySelector('[data-field="sla_days"]').value, 10);
			return isNaN(n) || n < 0 || n > 365;
		});
		if (bad.length) {
			setStatus("SLA days must be a whole number from 0 to 365.", "error");
			bad[0].querySelector('[data-field="sla_days"]').focus();
			return;
		}
		var orphan = changed.filter(function (tr) {
			return tr.querySelector('[data-field="start_trigger"]').value === "After another task" &&
				!tr.querySelector('[data-field="start_after_task"]').value;
		});
		if (orphan.length) {
			setStatus("Choose the task it starts after.", "error");
			orphan[0].querySelector('[data-field="start_after_task"]').focus();
			return;
		}
		save.disabled = true;
		setStatus("Saving…");
		var form = new FormData();
		form.append("rows", JSON.stringify(changed.map(valuesOf)));
		fetch("/api/method/a3_sola.api.task_defaults.save", { method: "POST", credentials: "same-origin", body: form,
			headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } })
			.then(function (r) {
				return r.json().catch(function () { return {}; }).then(function (data) {
					if (!r.ok) {
						var msg = "";
						try { msg = JSON.parse(JSON.parse(data._server_messages || "[]")[0] || "{}").message || ""; } catch (err) { /* none */ }
						throw new Error(r.status === 403 ? "Only an administrator can change task assignees." : (msg || "That did not save. Try again."));
					}
					return data.message || {};
				});
			})
			.then(function (res) {
				rows.forEach(function (tr) { saved[tr.dataset.row] = JSON.stringify(valuesOf(tr)); });
				setStatus("Saved " + (res.changed || 0) + " task" + (res.changed === 1 ? "" : "s") + ". New projects take them from now on.", "ok");
				refresh();
			})
			.catch(function (err) { setStatus(err.message, "error"); refresh(); });
	});

	refresh();
})();
