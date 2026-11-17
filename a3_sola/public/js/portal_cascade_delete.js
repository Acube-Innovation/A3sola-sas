// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
//
// Delete a lead or a customer with everything made for them (api/cascade_delete).
// The button first asks what would go and shows it; the delete needs the record's
// name typed in, since it cannot be undone from here.
(function () {
	"use strict";
	var btn = document.querySelector("[data-cascade-delete]");
	if (!btn) return;
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : (window.csrf_token || "");
	var API = "a3_sola.api.cascade_delete.";

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}

	function serverMessage(body) {
		try {
			var msgs = JSON.parse((body && body._server_messages) || "[]");
			if (msgs.length) return String(JSON.parse(msgs[msgs.length - 1]).message || "").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (body && body.exception) ? String(body.exception).split(":").slice(1).join(":").trim() : "";
	}

	function call(method, args) {
		return fetch("/api/method/" + API + method, {
			method: "POST", credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json", "Content-Type": "application/json" },
			body: JSON.stringify(args || {}),
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
				return body.message;
			});
		}, function () { throw new Error("Could not reach the server. Check your connection and try again."); });
	}

	function modal(title) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML = '<div class="a3s-modal__panel a3s-modal__panel--mismatch a3s-cascade" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
			'<h3 class="a3s-modal__title">' + esc(title) + '</h3><div data-body></div>' +
			'<p class="a3s-form__status" data-status role="status" aria-live="polite" hidden></p></div>';
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
		document.body.appendChild(back);
		var status = back.querySelector("[data-status]");
		return {
			body: back.querySelector("[data-body]"), close: close,
			status: function (text, tone) {
				status.textContent = text || ""; status.hidden = !text;
				status.classList.toggle("is-error", tone === "error");
			},
		};
	}

	function list(counts) {
		return '<ul class="a3s-cascade__list">' + counts.map(function (c) {
			return "<li><span>" + esc(c.label) + "</span><b>" + esc(c.count) + "</b></li>";
		}).join("") + "</ul>";
	}

	function open() {
		var args = { doctype: btn.dataset.doctype, name: btn.dataset.name };
		var kind = btn.dataset.kind || "record";
		var m = modal("Delete " + kind);
		m.body.innerHTML = '<p class="a3s-cascade__text">Checking what goes with it…</p>';
		call("preview", args).then(function (p) {
			if (p.blockers.length) {
				m.body.innerHTML = '<p class="a3s-cascade__text"><b>' + esc(p.title) + "</b> cannot be deleted: these documents are in the accounts. Cancel them in ERPNext first, then delete.</p>" +
					'<ul class="a3s-cascade__list">' + p.blockers.map(function (b) {
						return "<li><span>" + esc(b.doctype) + " " + esc(b.name) + "</span><b>" + esc(b.reason) + "</b></li>";
					}).join("") + "</ul>" +
					'<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--ghost" data-close>Close</button></div>';
				return;
			}
			var kept = [];
			if (p.kept.contacts) kept.push(p.kept.contacts + (p.kept.contacts === 1 ? " contact" : " contacts"));
			if (p.kept.addresses) kept.push(p.kept.addresses + (p.kept.addresses === 1 ? " address" : " addresses"));
			m.body.innerHTML = '<p class="a3s-cascade__text"><b>' + esc(p.title) + "</b> (" + esc(p.name) + ") and the " + esc(p.total) +
				" records made for them will be deleted, with their attachments:</p>" + list(p.counts) +
				(kept.length ? '<p class="a3s-cascade__text">' + esc(kept.join(" and ")) + " also used by someone else will stay, without this " + esc(kind) + ".</p>" : "") +
				'<div class="a3s-field"><label for="a3s-cascade-confirm">Type ' + esc(p.name) + ' to confirm <span class="a3s-req">*</span></label>' +
				'<input id="a3s-cascade-confirm" type="text" autocomplete="off" spellcheck="false"></div>' +
				'<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-cascade__ok" data-ok disabled>' +
				'<svg class="a3s-ic" aria-hidden="true"><use href="#ic-trash"></use></svg><span>Delete ' + esc(p.total) + " records</span></button>" +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div>';
			var input = m.body.querySelector("input");
			var ok = m.body.querySelector("[data-ok]");
			input.focus();
			input.addEventListener("input", function () { ok.disabled = input.value.trim() !== p.name; });
			ok.addEventListener("click", function () {
				ok.disabled = true; ok.classList.add("is-busy"); ok.querySelector("span").textContent = "Deleting…"; m.status("");
				call("delete", { doctype: args.doctype, name: args.name, confirm: input.value.trim() }).then(function (r) {
					window.location.href = r.redirect;
				}).catch(function (err) {
					m.status(err.message, "error");
					ok.classList.remove("is-busy"); ok.querySelector("span").textContent = "Delete " + p.total + " records";
					ok.disabled = input.value.trim() !== p.name;
				});
			});
		}).catch(function (err) {
			m.body.innerHTML = '<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--ghost" data-close>Close</button></div>';
			m.status(err.message, "error");
		});
	}

	btn.addEventListener("click", open);
})();
