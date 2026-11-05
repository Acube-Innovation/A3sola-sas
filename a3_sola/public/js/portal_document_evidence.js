/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The customer's documents on the subsidy eligibility check (api/document_evidence): each
 * document read by OCR on the lead or the customer, and each detail with the document it
 * came from. Where two documents spell a detail two ways it is a warning, and the check is
 * saved or submitted only once someone confirms, in a pop-up, that the details are correct.
 */
(function () {
	"use strict";

	var card = document.querySelector("[data-evidence]");
	if (!card) return;
	var API = "/api/method/a3_sola.api.document_evidence.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var name = card.dataset.name;
	var body = card.querySelector("[data-evidence-body]");
	var state = null;
	var passing = false;

	function esc(v) {
		return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}

	function message(data, fallback) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (msgs.length) return String(JSON.parse(msgs[0]).message || "").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return fallback;
	}

	function call(method, params, post) {
		var url = API + method, opts = { credentials: "same-origin", headers: { Accept: "application/json", "X-Frappe-CSRF-Token": csrf } };
		if (post) { opts.method = "POST"; opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(params); }
		else url += "?" + new URLSearchParams(params).toString();
		return fetch(url, opts).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (data) {
				if (!r.ok) throw new Error(message(data, "That did not go through. Try again."));
				return data.message || {};
			});
		});
	}

	function source(v) {
		return '<span class="a3s-evidence__from">from <b>' + esc(v.document) + "</b>" +
			(v.as ? " (as " + esc(v.as) + ")" : "") + "</span>";
	}

	function pending() { return state && state.conflicts.length && !state.confirmed; }

	function render() {
		var s = state, html = "";
		if (!s.documents.length) {
			html = '<p class="a3s-attach__status">No documents read yet. Upload the KSEB bill, the Aadhaar card and the passbook or cancelled cheque on the lead or the customer, and what they say shows here.</p>';
			body.innerHTML = html;
			return;
		}
		if (s.conflicts.length && !s.confirmed) {
			html += '<div class="a3s-attach__status a3s-evidence__alert" data-tone="warn"><span><b>The documents differ on ' +
				esc(s.conflicts.map(function (c) { return c.label; }).join(", ")) + ".</b> The customer may not be eligible for the subsidy until the documents agree. Check them against the documents and confirm before this check is saved or submitted; send the customer the PDF to show what to correct.</span>" +
				(s.can_confirm ? '<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-evidence-confirm>Review and confirm</button>' : "") + "</div>";
		} else if (s.conflicts.length) {
			html += '<p class="a3s-attach__status" data-tone="ok">Where the documents differ, ' + esc(s.confirmed_by) + " checked them and confirmed the details correct on " + esc(s.confirmed_on) + ".</p>";
		} else {
			html += '<p class="a3s-attach__status" data-tone="ok">The documents agree on every detail read from them.</p>';
		}
		if (s.load && !s.load.ok) {
			html += '<p class="a3s-attach__status" data-tone="warn"><b>The proposed system (' + esc(s.load.capacity_kw) + " kW, " + esc(s.load.capacity_from) +
				") is larger than the connected load (" + esc(s.load.load_w) + " W, from the " + esc(s.load.load_from) + ").</b> A rooftop system has to be no larger than the connected load: enhance the load with KSEB or make the system smaller, or commissioning may be delayed.</p>";
		}
		if (s.record_differs && s.record_differs.length) {
			html += '<p class="a3s-attach__status" data-tone="warn"><b>The customer&rsquo;s record differs from the documents on ' + esc(s.record_differs.join(", ")) +
				".</b> The subsidy application is made from the record: correct it on the customer (Read the document again there).</p>";
		}
		html += '<div class="a3s-evidence__table" role="table" aria-label="Details and the documents they came from">' +
			'<div class="a3s-evidence__row a3s-evidence__row--head" role="row"><span role="columnheader">Detail</span><span role="columnheader">What the documents say</span></div>';
		s.details.forEach(function (d) {
			html += '<div class="a3s-evidence__row' + (d.conflict || d.record_differs ? " is-conflict" : "") + '" role="row"><span class="a3s-evidence__label" role="cell">' + esc(d.label) +
				(d.conflict ? ' <span class="a3s-evidence__pill">Differs</span>' : d.record_differs ? ' <span class="a3s-evidence__pill">Record differs</span>' : "") + '</span><span class="a3s-evidence__values" role="cell">';
			d.values.forEach(function (v) {
				html += '<span class="a3s-evidence__value"><span>' + esc(v.value) + "</span> " + source(v) + "</span>";
			});
			if (d.record_differs) html += '<span class="a3s-evidence__record">On the customer&rsquo;s record: <b>' + esc(d.record) + "</b></span>";
			html += "</span></div>";
		});
		html += "</div>";
		html += '<h4 class="a3s-edit__subtitle a3s-evidence__docs-title">Documents</h4><ul class="a3s-evidence__docs">';
		s.documents.forEach(function (doc) {
			html += '<li><span class="a3s-attach__tag">' + esc(doc.document) + '</span> <a href="' + esc(doc.file_url) + '" target="_blank" rel="noopener">' +
				esc(doc.file_name) + '</a> <span class="a3s-attach__meta">' + esc(doc.doctype === "Lead" ? "Lead" : "Customer") + " " + esc(doc.record) + " · " +
				(Object.keys(doc.fields).length ? "read " + esc(doc.read_on) : "not read yet - open it there and choose Read") + "</span></li>";
		});
		html += "</ul>";
		body.innerHTML = html;
		var btn = body.querySelector("[data-evidence-confirm]");
		if (btn) btn.addEventListener("click", function () { confirmModal(); });
	}

	/* The details that differ, each with what every document says: confirmed correct, or not. */
	function confirmModal() {
		return new Promise(function (resolve) {
			var modal = document.createElement("div");
			modal.className = "a3s-modal";
			modal.setAttribute("role", "dialog");
			modal.setAttribute("aria-modal", "true");
			modal.setAttribute("aria-labelledby", "a3s-evidence-title");
			var list = state.conflicts.map(function (c) {
				return "<li><b>" + esc(c.label) + "</b><ul>" + c.values.map(function (v) {
					return "<li>" + esc(v.value) + " " + source(v) + "</li>";
				}).join("") + "</ul></li>";
			}).join("");
			modal.innerHTML = '<div class="a3s-modal__panel a3s-modal__panel--mismatch a3s-evidence__modal">' +
				'<p class="a3s-modal__title" id="a3s-evidence-title">&#9888; Documents differ</p>' +
				"<p>The customer&rsquo;s documents do not spell these details the same way:</p>" +
				'<ul class="a3s-evidence__conflicts">' + list + "</ul>" +
				'<p class="a3s-field__hint">Open the documents and check them. Confirm only if the details on this check are correct for the customer &mdash; the subsidy is paid into the account named here. Your confirmation is recorded on the check.</p>' +
				'<label class="a3s-check" style="margin:0.75rem 0"><input type="checkbox" data-ev-ok> <span>I have checked the documents: these details are correct</span></label>' +
				'<p class="a3s-form__status is-error" data-ev-status hidden></p>' +
				'<div class="a3s-form__actions" style="margin-top:0.75rem"><button type="button" class="a3s-btn a3s-btn--primary" data-ev-go disabled>Confirm</button>' +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-ev-cancel>Cancel</button></div></div>';
			document.body.appendChild(modal);
			var ok = modal.querySelector("[data-ev-ok]"), go = modal.querySelector("[data-ev-go]"), status = modal.querySelector("[data-ev-status]");
			function close(answer) { modal.remove(); document.removeEventListener("keydown", onKey); resolve(answer); }
			function onKey(e) { if (e.key === "Escape") close(false); }
			ok.addEventListener("change", function () { go.disabled = !ok.checked; });
			go.addEventListener("click", function () {
				go.disabled = true; go.classList.add("is-busy");
				call("confirm", { name: name, signature: state.signature }, true).then(function (s) {
					state = s; render(); close(true);
				}).catch(function (e) {
					status.textContent = e.message; status.hidden = false; go.classList.remove("is-busy");
					/* The documents changed meanwhile: shown again, to be checked again. */
					load();
				});
			});
			modal.querySelector("[data-ev-cancel]").addEventListener("click", function () { close(false); });
			modal.addEventListener("click", function (e) { if (e.target === modal) close(false); });
			document.addEventListener("keydown", onKey);
			ok.focus();
		});
	}

	/* Save and Submit wait for the confirmation while the documents differ. */
	function gate(e, resume) {
		if (passing || !pending()) return;
		e.preventDefault();
		e.stopImmediatePropagation();
		confirmModal().then(function (yes) {
			if (!yes) return;
			passing = true;
			try { resume(); } finally { passing = false; }
		});
	}
	document.addEventListener("click", function (e) {
		var btn = e.target.closest && e.target.closest("#a3s-submit-record");
		if (btn) gate(e, function () { btn.click(); });
	}, true);
	document.addEventListener("submit", function (e) {
		var form = e.target;
		if (form && form.id === "a3s-record-edit-form") {
			var by = e.submitter;
			gate(e, function () { form.requestSubmit(by || undefined); });
		}
	}, true);

	function load() {
		return call("get", { name: name }).then(function (s) { state = s; render(); })
			.catch(function (e) { body.innerHTML = '<p class="a3s-attach__status" data-tone="error">' + esc(e.message) + "</p>"; });
	}
	load();
})();
