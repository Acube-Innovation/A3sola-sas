/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The proposal's version-history actions. Each one posts to the same whitelisted endpoint
 * the desk calls, so the history is written in one place regardless of where somebody is
 * working, and the page reloads to show what the server actually recorded rather than
 * guessing at it.
 */
(function () {
	"use strict";

	var panel = document.getElementById("a3s-proposal-actions");
	if (!panel) return;

	var name = panel.dataset.name;
	var status = document.getElementById("a3s-proposal-status");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var ENDPOINT = "a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.";

	function setStatus(text, kind) {
		status.textContent = text || "";
		status.classList.toggle("is-error", kind === "error");
		status.classList.toggle("is-success", kind === "success");
	}

	function busy(on) {
		panel.querySelectorAll("button").forEach(function (b) { b.disabled = on; });
	}

	/* Frappe returns a thrown message inside _server_messages as a JSON array. */
	function serverMessage(data) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (!msgs.length) return "";
			var first = JSON.parse(msgs[0]);
			return (first && first.message) ? String(first.message).replace(/<[^>]*>/g, "") : "";
		} catch (e) {
			return "";
		}
	}

	function post(method, args, working) {
		busy(true);
		setStatus(working);
		return fetch("/api/method/" + ENDPOINT + method, {
			method: "POST",
			credentials: "same-origin",
			headers: {
				"Content-Type": "application/json",
				"Accept": "application/json",
				"X-Frappe-CSRF-Token": csrf
			},
			body: JSON.stringify(Object.assign({ solar_proposal: name }, args || {}))
		}).then(function (response) {
			return response.json().catch(function () { return {}; })
				.then(function (data) { return { ok: response.ok, code: response.status, data: data }; });
		}).then(function (result) {
			if (result.ok) {
				setStatus("Saved. Refreshing…", "success");
				window.location.reload();
				return;
			}
			busy(false);
			if (result.code === 403) {
				setStatus("You do not have permission to do that.", "error");
				return;
			}
			setStatus(serverMessage(result.data) || "That did not go through. Try again.", "error");
		}).catch(function () {
			busy(false);
			setStatus("Could not reach the server. Check your connection and try again.", "error");
		});
	}

	/* ---- a small dialog, so an action can ask for what it needs ---------- */
	function ask(title, fields, submitLabel, onSubmit) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML =
			'<div class="a3s-modal__panel" role="dialog" aria-modal="true" aria-label="' + title + '">' +
			'<h3 class="a3s-modal__title">' + title + "</h3>" +
			'<form class="a3s-form a3s-modal__form"></form>' +
			"</div>";
		var form = back.querySelector("form");

		fields.forEach(function (f) {
			var wrap = document.createElement("div");
			wrap.className = "a3s-field";
			var id = "mf-" + f.name;
			var control;
			if (f.type === "select") {
				control = '<select id="' + id + '" name="' + f.name + '">' +
					f.options.map(function (o) { return '<option value="' + o + '">' + o + "</option>"; }).join("") +
					"</select>";
			} else if (f.type === "textarea") {
				control = '<textarea id="' + id + '" name="' + f.name + '" rows="3"></textarea>';
			} else {
				control = '<input type="text" id="' + id + '" name="' + f.name + '" value="' + (f.value || "") + '">';
			}
			wrap.innerHTML = '<label for="' + id + '">' + f.label + "</label>" + control;
			form.appendChild(wrap);
		});

		var actions = document.createElement("div");
		actions.className = "a3s-form__actions";
		actions.innerHTML =
			'<button type="submit" class="a3s-btn a3s-btn--primary">' + submitLabel + "</button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button>';
		form.appendChild(actions);

		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.hasAttribute("data-close")) close(); });
		form.addEventListener("submit", function (e) {
			e.preventDefault();
			var values = {};
			fields.forEach(function (f) { values[f.name] = (form.elements[f.name].value || "").trim(); });
			close();
			onSubmit(values);
		});

		document.body.appendChild(back);
		var first = form.querySelector("input, select, textarea");
		if (first) first.focus();
	}

	var ACTIONS = {
		generate: function () {
			post("generate_proposal", {}, "Rendering the proposal…");
		},
		dispatch: function () {
			ask("Record dispatch", [
				{ name: "sent_via", label: "Sent via", type: "select", options: ["WhatsApp", "Email", "Printed", "Hand Delivered"] }
			], "Record", function (v) { post("record_dispatch", v, "Recording dispatch…"); });
		},
		response: function () {
			ask("Response from client", [
				{ name: "outcome", label: "Outcome", type: "select", options: ["Accepted", "Revision Requested", "Rejected", "Lost"] },
				{ name: "client_comments", label: "Comments from client", type: "textarea" },
				{ name: "lost_reason", label: "Lost reason (if rejected or lost)", type: "textarea" }
			], "Record", function (v) { post("record_response", v, "Recording the response…"); });
		},
		revise: function () {
			ask("Revise proposal", [
				{ name: "notes", label: "Why this revision", type: "textarea" }
			], "Open version", function (v) { post("add_version", v, "Opening a new version…"); });
		},
		quotation: function () {
			post("create_quotation", {}, "Building the quotation…");
		}
	};

	panel.addEventListener("click", function (event) {
		var button = event.target.closest("[data-act]");
		if (!button) return;
		var action = ACTIONS[button.dataset.act];
		if (action) action();
	});
})();
