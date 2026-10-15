/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Assign people, inside a task: its page's Assigned to strip (portal_task_people.html)
 * opens a checklist of the office - tick any number; the first ticked leads - and saves it
 * as the task's people on the project (api/task_assignees.set_task_assignees).
 */
(function () {
	"use strict";

	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}
	function serverMessage(body) {
		try {
			var msgs = JSON.parse((body && body._server_messages) || "[]");
			if (msgs.length) return String(JSON.parse(msgs[0]).message || "").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return "";
	}
	function call(method, args) {
		return fetch("/api/method/" + method, {
			method: "POST", credentials: "same-origin",
			headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
			body: JSON.stringify(args || {}),
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
				return body.message;
			});
		});
	}

	function open(strip) {
		var installation = strip.dataset.installation;
		var chosen = (strip.dataset.assignees || "").split(",").filter(Boolean);
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML =
			'<div class="a3s-modal__panel a3s-taskpanel" role="dialog" aria-modal="true" aria-label="Assign people">' +
			'<h3 class="a3s-modal__title">Assign ' + esc(strip.dataset.taskName) + "</h3>" +
			'<p class="a3s-taskpanel__sub">Tick everyone working on this task. The first ticked leads.</p>' +
			'<div class="a3s-taskpanel__body"><p class="a3s-taskpanel__empty">Loading…</p></div>' +
			'<p class="a3s-form__status" data-status role="status" aria-live="polite"></p></div>';
		document.body.appendChild(back);
		var body = back.querySelector(".a3s-taskpanel__body");
		var status = back.querySelector("[data-status]");
		function say(text, error) { status.textContent = text || ""; status.classList.toggle("is-error", !!error); }
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });

		call("a3_sola.api.task_assignees.candidates", { installation: installation }).then(function (people) {
			/* The current people first, in their order, then everyone else by name. */
			people.sort(function (a, b) {
				var ia = chosen.indexOf(a.name), ib = chosen.indexOf(b.name);
				if (ia !== -1 || ib !== -1) return (ia === -1 ? 1e6 : ia) - (ib === -1 ? 1e6 : ib);
				return (a.full_name || a.name).localeCompare(b.full_name || b.name);
			});
			body.innerHTML =
				'<form class="a3s-form a3s-modal__form">' +
				'<input type="text" class="a3s-assign__search" placeholder="Search people" aria-label="Search people">' +
				'<div class="a3s-assign__list">' +
				people.map(function (p) {
					return '<label class="a3s-check a3s-assign__person" data-search="' + esc(((p.full_name || "") + " " + p.name).toLowerCase()) + '">' +
						'<input type="checkbox" value="' + esc(p.name) + '"' + (chosen.indexOf(p.name) !== -1 ? " checked" : "") + ">" +
						"<span>" + esc(p.full_name || p.name) + " <small>" + esc(p.name) + "</small></span></label>";
				}).join("") +
				"</div>" +
				'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary">Save</button>' +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
			var form = body.querySelector("form");
			var search = form.querySelector(".a3s-assign__search");
			search.focus();
			search.addEventListener("input", function () {
				var q = search.value.trim().toLowerCase();
				Array.prototype.forEach.call(form.querySelectorAll(".a3s-assign__person"), function (row) {
					row.hidden = q && row.dataset.search.indexOf(q) === -1;
				});
			});
			/* Keep the order people were ticked in: the first stays the lead. */
			form.addEventListener("change", function (event) {
				var box = event.target;
				if (box.type !== "checkbox") return;
				var at = chosen.indexOf(box.value);
				if (box.checked && at === -1) chosen.push(box.value);
				if (!box.checked && at !== -1) chosen.splice(at, 1);
			});
			form.addEventListener("submit", function (event) {
				event.preventDefault();
				say("Saving…");
				call("a3_sola.api.task_assignees.set_task_assignees", { installation: installation, task_code: strip.dataset.task, users: chosen })
					.then(function () { window.location.reload(); })
					.catch(function (e) { say(e.message, true); });
			});
		}).catch(function (e) { body.innerHTML = ""; say(e.message, true); });
	}

	document.addEventListener("click", function (event) {
		var button = event.target.closest("[data-assign-people]");
		if (!button) return;
		event.preventDefault();
		open(button.closest(".a3s-taskpeople"));
	});
})();
