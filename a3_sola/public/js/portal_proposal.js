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

	/* ---- the version actions: Generate in Next steps, the rest in the history */
	var panels = Array.prototype.slice.call(document.querySelectorAll("[data-proposal-actions]"));
	if (!panels.length) return;

	var name = panels[0].dataset.name;
	var status = panels[0].querySelector("[data-proposal-status]");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var ENDPOINT = "a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.";

	function setStatus(text, kind) {
		if (!status) return;
		status.textContent = text || "";
		status.classList.toggle("is-error", kind === "error");
		status.classList.toggle("is-success", kind === "success");
	}

	function busy(on) {
		panels.forEach(function (panel) {
			panel.querySelectorAll("button").forEach(function (b) { b.disabled = on; });
		});
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

	/* Text into HTML, for labels built from record names. */
	function esc(text) {
		return String(text == null ? "" : text).replace(/[&<>"]/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
		});
	}

	/* What Create quotation and Revise choose from (portal_proposal_next.html). */
	var choices = (function () {
		var node = document.getElementById("a3s-proposal-choices");
		try { return node ? JSON.parse(node.textContent) : {}; } catch (e) { return {}; }
	})();
	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

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
				var route = result.data && result.data.message && result.data.message.route;
				setStatus(route ? "Done. Opening it…" : "Saved. Refreshing…", "success");
				if (route) window.location.assign(route);
				else window.location.reload();
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
					f.options.map(function (o) {
						var value = typeof o === "object" ? o.value : o;
						var label = typeof o === "object" ? o.label : o;
						return '<option value="' + esc(value) + '"' + (String(value) === String(f.value) ? " selected" : "") + ">" +
							esc(label) + "</option>";
					}).join("") +
					"</select>";
			} else if (f.type === "textarea") {
				control = '<textarea id="' + id + '" name="' + f.name + '" rows="3"></textarea>';
			} else {
				control = '<input type="text" id="' + id + '" name="' + f.name + '" value="' + (f.value || "") + '">';
			}
			wrap.innerHTML = '<label for="' + id + '">' + esc(f.label) + "</label>" + control +
				(f.hint ? '<p class="a3s-field__hint">' + esc(f.hint) + "</p>" : "");
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
			var fields = [];
			if ((choices.estimates || []).length) {
				fields.push({
					name: "solar_design_estimate", label: "Design estimate this version quotes", type: "select",
					options: choices.estimates, value: choices.base,
					hint: "A changed design saved as a new estimate keeps the earlier versions' designs as they were sent."
				});
			}
			fields.push({ name: "notes", label: "Why this revision", type: "textarea" });
			ask("Revise proposal", fields, "Open version", function (v) { post("add_version", v, "Opening a new version…"); });
		},
		quotation: function () {
			var versions = choices.versions || [];
			if (!versions.length) {
				post("create_quotation", {}, "Building the quotation…");
				return;
			}
			var accepted = versions.filter(function (v) { return v.outcome === "Accepted"; })[0];
			var options = versions.map(function (v) {
				return {
					value: v.version_no,
					label: "Version " + v.version_no + " \u00b7 " + v.raised + " \u00b7 " + money.format(v.cost) +
						(v.estimate ? " \u00b7 " + v.estimate : "") + (v.outcome === "Accepted" ? " \u00b7 Accepted" : "") +
						(v.changed_after ? " \u00b7 estimate changed since" : "")
				};
			});
			ask("Create quotation", [{
				name: "version_no", label: "Which version did the client accept?", type: "select",
				options: options, value: (accepted || versions[0]).version_no,
				hint: "The chosen version is recorded as Accepted and quoted from its own design estimate. " +
					"\"Estimate changed since\" means that estimate was edited after the version was raised."
			}], "Create quotation", function (v) { post("create_quotation", v, "Building the quotation…"); });
		}
	};

	panels.forEach(function (panel) {
		panel.addEventListener("click", function (event) {
			var button = event.target.closest("[data-act]");
			if (!button) return;
			var action = ACTIONS[button.dataset.act];
			if (!action) return;
			// Say how it went where it was asked.
			status = panel.querySelector("[data-proposal-status]") || status;
			action();
		});
	});
})();
