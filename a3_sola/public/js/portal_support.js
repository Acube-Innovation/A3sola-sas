/* Support: platform staff find anyone in any company and log in as them; the sessions held,
   with Revoke for an open one (a3_sola.api.impersonation). */
(function () {
	"use strict";

	var API = "a3_sola.api.impersonation.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var boot = JSON.parse(document.getElementById("a3s-support-data").textContent);
	var pageStatus = document.querySelector("[data-page-status]");
	var results = document.querySelector("[data-results]");
	var resultRows = document.querySelector("[data-result-rows]");
	var sessionRows = document.querySelector("[data-session-rows]");
	var sessionEmpty = document.querySelector("[data-session-empty]");
	var found = [];

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
		return (body && body.exception) ? String(body.exception).split(":").slice(1).join(":").trim() : "";
	}
	function call(method, args) {
		var url = "/api/method/" + API + method;
		var opts = { method: "POST", credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json", "Content-Type": "application/json" },
			body: JSON.stringify(args || {}) };
		return fetch(url, opts).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
				return body.message;
			});
		});
	}
	function setStatus(el, text, tone) { el.textContent = text || ""; el.dataset.tone = tone || ""; el.hidden = !text; }
	function modal(title, sub) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML = '<div class="a3s-modal__panel" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
			'<h3 class="a3s-modal__title">' + esc(title) + "</h3>" + (sub ? '<p class="a3s-users__sub">' + sub + "</p>" : "") +
			'<div data-body></div><p class="a3s-attach__status" data-status role="status" aria-live="polite" hidden></p></div>';
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
		document.body.appendChild(back);
		var status = back.querySelector("[data-status]");
		return { body: back.querySelector("[data-body]"), close: close, status: function (t, tone) { setStatus(status, t, tone); } };
	}

	/* ------------------------------------------------------------ people */
	function renderResults() {
		results.hidden = false;
		resultRows.innerHTML = found.length ? found.map(function (u, i) {
			return "<tr><td><span class=\"a3s-table__link\">" + esc(u.full_name) + '</span><span class="a3s-table__meta">' + esc(u.name) + "</span></td>" +
				'<td><span class="a3s-support__companies">' + u.companies.map(function (c) {
					return '<span class="a3s-badge a3s-badge--' + esc((c.type || "").toLowerCase()) + '">' + esc(c.company_name) + " &middot; " + esc(c.type) + "</span>";
				}).join("") + "</span></td>" +
				'<td>' + (u.open ? '<span class="a3s-table__muted">Session open</span>' :
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-login-as="' + i + '"><span>Log in as</span></button>') + "</td></tr>";
		}).join("") : '<tr><td colspan="3" class="a3s-table__muted">No match.</td></tr>';
	}
	document.querySelector("[data-search]").addEventListener("submit", function (e) {
		e.preventDefault();
		setStatus(pageStatus, "Searching…");
		call("search", { query: e.target.q.value.trim() }).then(function (rows) {
			found = rows || []; setStatus(pageStatus, ""); renderResults();
		}).catch(function (err) { setStatus(pageStatus, err.message, "error"); });
	});
	resultRows.addEventListener("click", function (e) {
		var b = e.target.closest("[data-login-as]");
		if (b) loginAs(found[+b.dataset.loginAs]);
	});

	function loginAs(u) {
		var m = modal("Log in as", esc(u.full_name) + " &middot; " + esc(u.name));
		var active = (u.companies.filter(function (c) { return c.is_active; })[0] || u.companies[0] || {}).company;
		var opts = [15, 30, 60, 120].filter(function (n) { return n <= (boot.minutes || 120); });
		m.body.innerHTML = '<form class="a3s-modal__form" novalidate>' +
			(u.companies.length > 1 ? '<div class="a3s-field"><label for="sp-co">Company</label><select id="sp-co" name="company">' +
				u.companies.map(function (c) { return '<option value="' + esc(c.company) + '"' + (c.company === active ? " selected" : "") + ">" + esc(c.company_name) + " (" + esc(c.type) + ")</option>"; }).join("") +
				'</select><p class="a3s-field__hint" data-move hidden>Their account moves to this company for the session, on every device they are signed in on. They are told.</p></div>' : "") +
			'<div class="a3s-field"><label for="sp-reason">Why <span class="a3s-req">*</span></label>' +
			'<textarea id="sp-reason" name="reason" rows="3" required placeholder="For example: ticket 482, the proposal will not print"></textarea>' +
			'<p class="a3s-field__hint">At least 15 characters. Kept in the audit trail and shown to them.</p></div>' +
			'<div class="a3s-field"><label for="sp-min">For</label><select id="sp-min" name="minutes">' +
			opts.map(function (n) { return '<option value="' + n + '"' + (n === 30 ? " selected" : "") + ">" + n + " minutes</option>"; }).join("") + "</select></div>" +
			'<label class="a3s-check"><input type="checkbox" name="notify" checked><span>Tell them by e-mail</span></label>' +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary"><span>Log in as ' + esc(u.full_name) + "</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
		var form = m.body.querySelector("form");
		if (form.company) form.company.addEventListener("change", function () {
			m.body.querySelector("[data-move]").hidden = form.company.value === active;
		});
		form.reason.focus();
		form.addEventListener("submit", function (e) {
			e.preventDefault();
			if (form.reason.value.trim().length < 15) { m.status("Say why, in at least 15 characters.", "error"); return; }
			var btn = form.querySelector('[type="submit"]');
			btn.disabled = true; m.status("Opening…");
			call("start", { user: u.name, reason: form.reason.value.trim(), minutes: form.minutes.value,
				company: form.company ? form.company.value : null, notify_user: form.notify.checked ? 1 : 0 })
				.then(function (r) { window.location.assign((r && r.redirect) || "/a3solaportal/dashboard"); })
				.catch(function (err) { m.status(err.message, "error"); btn.disabled = false; });
		});
	}

	/* ------------------------------------------------------------ sessions */
	function renderSessions(list) {
		sessionEmpty.hidden = list.length > 0;
		sessionRows.innerHTML = list.map(function (s) {
			var open = s.status === "Open";
			return "<tr><td>" + esc(s.operator_name) + '<span class="a3s-table__meta">' + esc(s.level) + "</span></td>" +
				"<td>" + esc(s.target_name) + '<span class="a3s-table__meta">' + esc(s.target) + "</span></td>" +
				"<td>" + esc(s.company_name) + "</td><td>" + esc(s.started_on) + '<span class="a3s-table__meta">' + (open ? "until " + esc(s.expires_on) : esc(s.end_reason || "")) + "</span></td>" +
				'<td class="a3s-table__status"><span class="a3s-badge ' + (open ? "a3s-badge--open" : "") + '">' + esc(s.status) + "</span></td>" +
				'<td class="a3s-table__muted">' + esc(s.reason) + "</td>" +
				"<td>" + (open ? '<button type="button" class="a3s-btn a3s-btn--ghost" data-revoke="' + esc(s.name) + '"><span>End now</span></button>' : "") + "</td></tr>";
		}).join("");
	}
	sessionRows.addEventListener("click", function (e) {
		var b = e.target.closest("[data-revoke]");
		if (!b) return;
		b.disabled = true;
		call("revoke", { name: b.dataset.revoke }).then(function () {
			return call("sessions", { limit: 50 });
		}).then(function (rows) { renderSessions(rows || []); setStatus(pageStatus, "Session ended.", "ok"); })
			.catch(function (err) { setStatus(pageStatus, err.message, "error"); b.disabled = false; });
	});
	renderSessions(boot.sessions || []);
})();
