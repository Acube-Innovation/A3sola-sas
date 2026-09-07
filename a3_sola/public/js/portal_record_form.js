/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The generic create form for a portal collection. It gathers every named control, posts
 * them with the collection slug to create_record, and does no validation of its own - the
 * server validates against the doctype and is the only thing that decides.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-record-form");
	if (!form) return;

	var slug = form.dataset.slug;
	var sourceDt = form.dataset.sourceDt || "";
	var source = form.dataset.source || "";
	var submit = document.getElementById("a3s-record-submit");
	var status = document.getElementById("a3s-record-status");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var submitLabel = submit.textContent;

	function setStatus(text, kind) {
		status.textContent = text || "";
		status.classList.toggle("is-error", kind === "error");
		status.classList.toggle("is-success", kind === "success");
	}

	function busy(on) {
		submit.disabled = on;
		submit.textContent = on ? "Creating…" : submitLabel;
	}

	function collect() {
		var out = { slug: slug };
		/* Created from another record: the server re-reads it and applies the rest of the
		   mapping itself, so only the pointer travels - never the mapped values. */
		if (sourceDt && source) { out.source_dt = sourceDt; out.source = source; }
		Array.prototype.forEach.call(form.elements, function (el) {
			if (!el.name) return;
			if (el.type === "checkbox") out[el.name] = el.checked ? "1" : "0";
			else out[el.name] = el.value;
		});
		return out;
	}

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

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		busy(true);
		setStatus("Creating…");

		fetch("/api/method/a3_sola.api.portal_crud.create_record", {
			method: "POST",
			credentials: "same-origin",
			headers: {
				"Content-Type": "application/json",
				"Accept": "application/json",
				"X-Frappe-CSRF-Token": csrf
			},
			body: JSON.stringify(collect())
		}).then(function (response) {
			return response.json().catch(function () { return {}; })
				.then(function (data) { return { ok: response.ok, code: response.status, data: data }; });
		}).then(function (result) {
			if (result.ok && result.data && result.data.message) {
				setStatus("Created. Taking you to the list…", "success");
				window.location.assign(result.data.message.route || ("/a3solaportal/" + slug));
				return;
			}
			busy(false);
			if (result.code === 403) {
				setStatus("You do not have permission to create this record.", "error");
				return;
			}
			setStatus(serverMessage(result.data) || "Could not create the record. Check the fields and try again.", "error");
		}).catch(function () {
			busy(false);
			setStatus("Could not reach the server. Check your connection and try again.", "error");
		});
	});
})();
