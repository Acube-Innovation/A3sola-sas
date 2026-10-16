/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The Serials to Electrical Contractor page (www/a3solaportal/projects/task.html,
 * api/serials_task): the job's electrical contractor, the module and inverter serials, the
 * Data for Completion Report on the letterhead or plain paper, and its sending - by email,
 * which completes the task, or by WhatsApp, then Mark complete. Every step redraws from the
 * server's state.
 */
(function () {
	"use strict";

	var root = document.querySelector("[data-serials]");
	if (!root) return;
	var API = "/api/method/a3_sola.api.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var installation = root.dataset.installation;
	var body = root.querySelector("[data-serials-body]");
	var status = root.querySelector("[data-serials-status]");
	var state = JSON.parse(root.querySelector("[data-serials-data]").textContent);

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}

	function message(data, fallback) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (msgs.length) return JSON.parse(msgs[0]).message.replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception ? String(data.exception).split(":").slice(1).join(":").trim() : "") || fallback;
	}

	function call(method, args) {
		var form = new FormData();
		Object.keys(args || {}).forEach(function (k) { form.append(k, args[k]); });
		return fetch(API + method, { method: "POST", credentials: "same-origin", body: form,
			headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } })
			.then(function (r) {
				return r.json().catch(function () { return {}; }).then(function (data) {
					if (!r.ok) throw new Error(message(data, "Something went wrong (" + r.status + ")."));
					return data.message || {};
				});
			});
	}

	function setStatus(text, tone) {
		status.textContent = text || "";
		status.dataset.tone = tone || "";
		status.hidden = !text;
	}

	function label(text) { return '<p class="a3s-paytask__label">' + text + "</p>"; }

	function contractor(s) {
		var c = s.contractor;
		if (!c) {
			return '<div class="a3s-serials__box"><span class="a3s-field__hint">No electrical contractor on this job yet. ' +
				'Set it on the project (<a href="' + esc(s.project_route) + '">open the project</a>), then come back to send.</span></div>';
		}
		return '<div class="a3s-serials__box"><b>' + esc(c.contractor_name) + "</b>" +
			(c.contact_person ? "<br>Contact: " + esc(c.contact_person) : "") +
			(c.mobile_no ? '<br>Phone: <a href="tel:' + esc(c.mobile_no) + '">' + esc(c.mobile_no) + "</a>" : "") +
			(c.email_id ? "<br>Email: " + esc(c.email_id) : '<br><span class="a3s-field__hint">No email address on the contractor.</span>') +
			"</div>";
	}

	function serials(s) {
		var mods = s.serials.Module || [], invs = s.serials.Inverter || [], off = s.can_edit ? "" : " disabled";
		return '<div class="a3s-paytask__fields">' +
			'<div class="a3s-field"><label for="a3s-s-mod">Module serials (' + mods.length + (s.expected_modules ? " of " + s.expected_modules : "") + ")</label>" +
			'<textarea id="a3s-s-mod" name="module_serials" rows="7" placeholder="One per line"' + off + ">" + esc(mods.join("\n")) + "</textarea></div>" +
			'<div class="a3s-field"><label for="a3s-s-inv">Inverter serials (' + invs.length + ")</label>" +
			'<textarea id="a3s-s-inv" name="inverter_serials" rows="7" placeholder="One per line"' + off + ">" + esc(invs.join("\n")) + "</textarea></div></div>" +
			(s.can_edit ? '<div class="a3s-form__actions" style="margin-top:0.75rem"><button type="button" class="a3s-btn a3s-btn--secondary" data-act="save">Save serials</button></div>' : "");
	}

	function prints(s) {
		if (!s.ready) return '<p class="a3s-field__hint">Enter the serials first: the sheet lists every module and inverter serial.</p>';
		return '<div class="a3s-serials__box a3s-serials__prints">' + s.prints.map(function (p) {
			return "<div><span>" + esc(p.label) + "</span>" +
				'<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(p.view) + '" target="_blank" rel="noopener">View</a> ' +
				'<a class="a3s-btn a3s-btn--ghost a3s-btn--sm" href="' + esc(p.download) + '">Download</a></div>';
		}).join("") + "</div>";
	}

	function send(s) {
		var t = s.task;
		if (t.status === "Completed") {
			return '<p class="a3s-field__hint">Sent' + (t.sent_to ? " to " + esc(t.sent_to) : "") + " &middot; completed on " + esc(t.completed_on) + ".</p>";
		}
		if (!s.can_complete) return "";
		if (!s.ready) return '<p class="a3s-field__hint">Nothing to send yet.</p>';
		var e = s.email;
		return '<div class="a3s-paytask__fields">' +
			'<div class="a3s-field"><label for="a3s-s-to">To <span class="a3s-req">*</span></label>' +
			'<input type="email" id="a3s-s-to" name="recipients" value="' + esc(e.to) + '" placeholder="contractor@example.com"></div>' +
			'<div class="a3s-field"><label for="a3s-s-subject">Subject</label>' +
			'<input type="text" id="a3s-s-subject" name="subject" value="' + esc(e.subject) + '"></div></div>' +
			'<div class="a3s-field" style="margin-top:0.85rem"><label for="a3s-s-msg">Message</label>' +
			'<textarea id="a3s-s-msg" name="message" rows="3">' + esc(e.message) + "</textarea></div>" +
			'<label style="display:flex;gap:0.5rem;align-items:center;margin-top:0.6rem"><input type="checkbox" name="letterhead" checked> Attach on the Renewcore letterhead</label>' +
			'<div class="a3s-serials__send">' +
			'<button type="button" class="a3s-btn a3s-btn--primary" data-act="email">Send by email</button>' +
			(s.whatsapp ? '<a class="a3s-btn a3s-btn--secondary" href="' + esc(s.whatsapp) + '" target="_blank" rel="noopener">Send on WhatsApp</a>' : "") +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-act="done">Mark complete</button></div>' +
			'<p class="a3s-field__hint" style="margin-top:0.5rem">Sending by email completes the task. After sending on WhatsApp, press Mark complete.</p>';
	}

	function paint() {
		var s = state, t = s.task;
		var tone = { Completed: "uploaded", "In Progress": "partly", Pending: "missing", Skipped: "partly" }[t.status] || "partly";
		var html = '<div class="a3s-paytask__head"><h3 class="a3s-edit__card-title">' + esc(t.name) + "</h3>" +
			'<span class="a3s-taskdocs__state is-' + tone + '">' + esc(t.status) + "</span></div>";
		if (t.status === "Skipped") {
			html += '<p class="a3s-field__hint">Not needed on this job' + (t.reason ? ": " + esc(t.reason) : "") + ".</p>";
		}
		html += label("Electrical contractor") + contractor(s);
		html += label("Serial numbers") + serials(s);
		html += label("Data for completion report") + prints(s);
		html += label("Send to the contractor") + send(s);
		body.innerHTML = html;
	}

	function values() {
		var out = {};
		Array.prototype.forEach.call(body.querySelectorAll("input[name], textarea[name]"), function (el) {
			out[el.name] = el.type === "checkbox" ? (el.checked ? 1 : 0) : el.value;
		});
		return out;
	}

	function run(method, args, busy, done) {
		setStatus(busy);
		return call(method, Object.assign({ installation: installation }, args))
			.then(function (s) { state = s; paint(); setStatus(done, "ok"); })
			.catch(function (err) { setStatus(err.message, "error"); });
	}

	body.addEventListener("click", function (e) {
		var act = e.target.closest("[data-act]");
		if (!act) return;
		var v = values();
		if (act.dataset.act === "save") {
			run("serials_task.save", { module_serials: v.module_serials || "", inverter_serials: v.inverter_serials || "" },
				"Saving…", "Saved.");
		} else if (act.dataset.act === "email") {
			run("serials_task.send_email", { recipients: v.recipients || "", subject: v.subject || "", message: v.message || "",
				letterhead: v.letterhead }, "Sending…", "Sent. The task is complete.");
		} else if (act.dataset.act === "done") {
			if (!window.confirm("Mark the task complete? Do this once the data has reached the contractor.")) return;
			run("serials_task.mark_complete", {}, "Completing…", "The task is complete.");
		}
	});

	paint();
})();
