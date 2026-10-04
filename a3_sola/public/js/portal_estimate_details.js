/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Step one of the design estimate builder. Next saves the details - creating the estimate
 * the first time - and moves on to step two. The server validates; this only collects.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-de-details");
	if (!form) return;

	var next = document.getElementById("a3s-de-next");
	var status = document.getElementById("a3s-de-status");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function setStatus(text, kind) {
		status.textContent = text || "";
		status.classList.toggle("is-error", kind === "error");
	}

	function serverMessage(data) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			var last = msgs.length ? JSON.parse(msgs[msgs.length - 1]) : null;
			if (last && last.message) return String(last.message).replace(/<br\s*\/?>/g, " ").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception) ? String(data.exception).split(":").slice(1).join(":").trim() : "";
	}

	/* A field that only applies to one answer - the subsidy scheme - shows with that answer. */
	var conditional = form.querySelectorAll("[data-show-when]");
	function applyConditions() {
		Array.prototype.forEach.call(conditional, function (wrap) {
			var parts = wrap.dataset.showWhen.split("=");
			var source = document.getElementById("fld-" + parts[0]);
			wrap.hidden = !(source && source.value === parts.slice(1).join("="));
		});
	}
	Array.prototype.forEach.call(conditional, function (wrap) {
		var source = document.getElementById("fld-" + wrap.dataset.showWhen.split("=")[0]);
		if (source) source.addEventListener("change", applyConditions);
	});
	applyConditions();

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		var values = {};
		Array.prototype.forEach.call(form.elements, function (el) {
			if (el.name && !el.closest("[hidden]")) values[el.name] = el.value;
		});
		next.disabled = true;
		setStatus("Saving…");
		fetch("/api/method/a3_sola.api.portal_estimate.save_details", {
			method: "POST",
			credentials: "same-origin",
			headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
			body: JSON.stringify({ values: values, name: form.dataset.name || null })
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (data) { return { ok: r.ok, data: data }; });
		}).then(function (res) {
			if (res.ok && res.data.message) {
				window.location.assign(res.data.message.route);
				return;
			}
			next.disabled = false;
			setStatus(serverMessage(res.data) || "Could not save. Check the fields and try again.", "error");
		}).catch(function () {
			next.disabled = false;
			setStatus("Could not reach the server. Check your connection and try again.", "error");
		});
	});
})();
