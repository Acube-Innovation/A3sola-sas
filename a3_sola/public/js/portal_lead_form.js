/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The create-a-lead form. Posts to the whitelisted create_lead endpoint and does no
 * validation of its own beyond a courtesy check - the server validates again and is the
 * only thing that decides whether the record is written.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-lead-form");
	if (!form) return;

	var submit = document.getElementById("a3s-lead-submit");
	var status = document.getElementById("a3s-lead-status");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function setStatus(text, kind) {
		status.textContent = text || "";
		status.classList.toggle("is-error", kind === "error");
		status.classList.toggle("is-success", kind === "success");
	}

	function markInvalid(id, invalid) {
		var field = document.getElementById("f-" + id);
		if (field) field.classList.toggle("a3s-field--error", invalid);
	}

	function busy(on) {
		submit.disabled = on;
		submit.textContent = on ? "Creating…" : "Create lead";
	}

	function value(name) {
		var el = form.elements[name];
		return el ? el.value.trim() : "";
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		markInvalid("lead_name", false);
		markInvalid("company_name", false);

		/* Same rule the server enforces, checked here only to spare a round trip. */
		if (!value("lead_name") && !value("company_name")) {
			markInvalid("lead_name", true);
			markInvalid("company_name", true);
			setStatus("Enter a lead name or a company name.", "error");
			(form.elements.lead_name || {}).focus && form.elements.lead_name.focus();
			return;
		}

		busy(true);
		setStatus("Creating…");

		var payload = {
			lead_name: value("lead_name"),
			company_name: value("company_name"),
			email_id: value("email_id"),
			mobile_no: value("mobile_no"),
			status: value("status"),
			source: value("source")
		};

		fetch("/api/method/a3_sola.api.leads.create_lead", {
			method: "POST",
			credentials: "same-origin",
			headers: {
				"Content-Type": "application/json",
				"Accept": "application/json",
				"X-Frappe-CSRF-Token": csrf
			},
			body: JSON.stringify(payload)
		}).then(function (response) {
			return response.json().catch(function () { return {}; })
				.then(function (data) { return { ok: response.ok, code: response.status, data: data }; });
		}).then(function (result) {
			if (result.ok && result.data && result.data.message) {
				setStatus("Lead created. Taking you to the list…", "success");
				window.location.assign(result.data.message.route || "/a3solaportal/leads");
				return;
			}
			busy(false);
			if (result.code === 403) {
				setStatus("You do not have permission to create a lead.", "error");
				return;
			}
			/* Frappe returns the thrown message in _server_messages as a JSON array. */
			setStatus(serverMessage(result.data) || "Could not create the lead. Check the fields and try again.", "error");
		}).catch(function () {
			busy(false);
			setStatus("Could not reach the server. Check your connection and try again.", "error");
		});
	});

	/* Pull the human-readable text out of Frappe's _server_messages envelope. */
	function serverMessage(data) {
		try {
			var msgs = JSON.parse(data._server_messages || "[]");
			if (!msgs.length) return "";
			var first = JSON.parse(msgs[0]);
			return (first && first.message) ? String(first.message).replace(/<[^>]*>/g, "") : "";
		} catch (e) {
			return "";
		}
	}
})();
