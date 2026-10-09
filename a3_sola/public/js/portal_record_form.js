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

	/* Choosing the lead (or, for a survey, the consumer) fills in what that record already
	   knows. Only fields still as the page left them, or as this last filled them, are
	   written: anything typed stays. The server fills the same fields again on save, so
	   nothing depends on this having run. */
	var PREFILL_FROM = { "Solar Consumer": ["lead"], "Site Survey": ["lead", "solar_consumer"] };
	var doctype = form.dataset.doctype || "";
	var triggers = PREFILL_FROM[doctype] || [];
	if (triggers.length) {
		var initial = {}, filled = {};
		var read = function (el) { return el.type === "checkbox" ? (el.checked ? "1" : "") : el.value; };
		Array.prototype.forEach.call(form.elements, function (el) { if (el.name) initial[el.name] = read(el); });
		var untouched = function (el) {
			var v = read(el);
			return v === "" || v === initial[el.name] || (el.name in filled && v === filled[el.name]);
		};
		var put = function (el, value) {
			value = value === null || value === undefined ? "" : String(value);
			if (el.tagName === "SELECT") {
				if (el.dataset.dependsOn) { el.dataset.pending = value; }
				if (!Array.prototype.some.call(el.options, function (o) { return o.value === value; })) return false;
			}
			if (el.type === "checkbox") el.checked = !!value && value !== "0";
			else el.value = value;
			return true;
		};
		var apply = function (values, from) {
			var changed = [];
			Object.keys(values).forEach(function (name) {
				if (name === from) return;
				var el = form.elements[name];
				if (!el || !el.name || el.type === "file" || el.type === "hidden") return;
				/* The other of lead and consumer follows the one chosen. */
				var follows = triggers.indexOf(name) !== -1;
				if (!follows && !untouched(el)) return;
				if (read(el) === String(values[name])) return;
				if (put(el, values[name])) { filled[name] = read(el); if (!follows) changed.push(el); }
			});
			/* Parents first, so a dependent list (DISCOM, then its section) loads before it is set. */
			changed.forEach(function (el) { el.dispatchEvent(new Event("change", { bubbles: true })); });
			if (changed.length || Object.keys(values).length) setStatus("Filled in from the " + (from === "lead" ? "lead" : "consumer") + ". Check and change anything that differs.", "success");
		};
		triggers.forEach(function (name) {
			var el = form.elements[name];
			if (!el) return;
			el.addEventListener("change", function () {
				if (!el.value) return;
				var args = { doctype: doctype };
				args[name] = el.value;
				fetch("/api/method/a3_sola.api.record_links.prefill", {
					method: "POST", credentials: "same-origin",
					headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
					body: JSON.stringify(args)
				}).then(function (r) { return r.json(); })
				  .then(function (body) { if (body && body.message) apply(body.message, name); })
				  .catch(function () { /* the server fills them on save */ });
			});
		});
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
				setStatus("Created. Opening it…", "success");
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
