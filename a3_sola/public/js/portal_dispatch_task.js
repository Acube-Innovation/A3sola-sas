/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The Material Dispatch page (www/a3solaportal/projects/task.html, api/dispatch_task): from
 * the company godown to the customer's site - what goes (the procurement tasks' godown
 * lists), the dispatch date, vehicle and driver, the module and inverter serial numbers and
 * the signed delivery slip - then Mark dispatched. Every step redraws from the server's state.
 */
(function () {
	"use strict";

	var root = document.querySelector("[data-dispatch]");
	if (!root) return;
	var API = "/api/method/a3_sola.api.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var installation = root.dataset.installation;
	var body = root.querySelector("[data-dispatch-body]");
	var status = root.querySelector("[data-dispatch-status]");
	var picker = root.querySelector("[data-dispatch-file]");
	var state = JSON.parse(root.querySelector("[data-dispatch-data]").textContent);

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

	function call(method, args, form) {
		form = form || new FormData();
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

	function input(name, text, value, type, extra) {
		return '<div class="a3s-field"><label for="a3s-d-' + name + '">' + text + "</label>" +
			'<input type="' + (type || "text") + '" id="a3s-d-' + name + '" name="' + name + '" value="' + esc(value) + '"' +
			(state.can_edit ? "" : " disabled") + (extra || "") + "></div>";
	}

	function lists(s) {
		if (!s.lists.length) return '<p class="a3s-field__hint">No procurement task on this job yet.</p>';
		return s.lists.map(function (l) {
			var head = "<b>" + esc(l.title) + "</b> &middot; " + esc(l.method);
			if (!l.godown) {
				return '<p class="a3s-field__hint">' + head + " &mdash; shipped by the vendor straight to the customer; not in this dispatch.</p>";
			}
			return '<p style="margin:0.5rem 0 0.35rem">' + head + "</p>" +
				'<div class="a3s-tablewrap"><table class="a3s-table"><thead><tr><th>#</th><th>Material</th><th>Qty</th><th>Unit</th></tr></thead><tbody>' +
				(l.rows.length ? l.rows.map(function (r, i) {
					return "<tr><td>" + (i + 1) + "</td><td>" + esc(r.material) + "</td><td>" + esc(r.qty) + "</td><td>" + esc(r.uom || "") + "</td></tr>";
				}).join("") : '<tr><td colspan="4">Nothing listed on the task yet.</td></tr>') + "</tbody></table></div>";
		}).join("");
	}

	function slip(s) {
		var d = s.slip, st = d.file_url ? "Uploaded" : "Missing";
		return '<ul class="a3s-taskdocs"><li class="a3s-taskdocs__row"><div class="a3s-taskdocs__info">' +
			'<p class="a3s-taskdocs__name">Signed delivery slip or photograph</p>' +
			'<p class="a3s-taskdocs__meta"><span class="a3s-taskdocs__state is-' + st.toLowerCase() + '">' + st + "</span></p></div>" +
			'<div class="a3s-taskdocs__actions">' +
			(d.file_url ? '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(d.file_url) + '" target="_blank" rel="noopener">Open</a>' : "") +
			(s.can_edit ? '<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-act="upload">' + (d.file_url ? "Replace" : "Upload") + "</button>" : "") +
			"</div></li></ul>";
	}

	function paint() {
		var s = state, t = s.task, d = s.dispatch;
		var tone = { Completed: "uploaded", "In Progress": "partly", Pending: "missing", Skipped: "partly" }[t.status] || "partly";
		var html = '<div class="a3s-paytask__head"><h3 class="a3s-edit__card-title">' + esc(t.name) + "</h3>" +
			'<span class="a3s-taskdocs__state is-' + tone + '">' + esc(t.status) + "</span></div>";
		if (t.status === "Skipped") {
			html += '<p class="a3s-field__hint">Not needed on this job' + (t.reason ? ": " + esc(t.reason) : "") + ".</p>";
		}
		if (t.status === "Completed") html += '<p class="a3s-field__hint">Dispatched on ' + esc(t.completed_on) + ".</p>";

		html += label("Route") + '<div class="a3s-dispatch__route">' +
			"<div><h4>Ship from</h4>" + s.ship_from.map(esc).join("<br>") + "</div>" +
			"<div><h4>Ship to</h4>" + s.ship_to.map(esc).join("<br>").replace(/\n/g, "<br>") +
			(s.map ? '<br><a href="' + esc(s.map) + '" target="_blank" rel="noopener">Open in Google Maps</a>' : "") + "</div></div>";

		html += label("What goes") + lists(s);

		html += label("Dispatch") + '<div class="a3s-paytask__fields">' +
			input("dispatch_date", 'Dispatched on <span class="a3s-req">*</span>', d.dispatch_date, "date") +
			input("dispatch_vehicle", "Vehicle", d.dispatch_vehicle, "text", ' placeholder="e.g. KL-07-AB-1234"') +
			input("dispatch_driver", "Driver", d.dispatch_driver) +
			input("dispatch_driver_mobile", "Driver mobile", d.dispatch_driver_mobile, "tel") + "</div>" +
			'<div class="a3s-field" style="margin-top:0.85rem"><label for="a3s-d-notes">Notes</label>' +
			'<textarea id="a3s-d-notes" name="dispatch_notes" rows="2"' + (s.can_edit ? "" : " disabled") + ">" + esc(d.dispatch_notes) + "</textarea></div>";

		var mods = s.serials.Module || [], invs = s.serials.Inverter || [];
		html += label("Serial numbers") + '<div class="a3s-paytask__fields">' +
			'<div class="a3s-field"><label for="a3s-d-mod">Module serials (' + mods.length + (s.expected_modules ? " of " + s.expected_modules : "") + ")</label>" +
			'<textarea id="a3s-d-mod" name="module_serials" rows="6" placeholder="One per line"' + (s.can_edit ? "" : " disabled") + ">" + esc(mods.join("\n")) + "</textarea></div>" +
			'<div class="a3s-field"><label for="a3s-d-inv">Inverter serials (' + invs.length + ")</label>" +
			'<textarea id="a3s-d-inv" name="inverter_serials" rows="6" placeholder="One per line"' + (s.can_edit ? "" : " disabled") + ">" + esc(invs.join("\n")) + "</textarea></div></div>";

		html += label("Delivery slip") + slip(s);

		if (s.can_edit) {
			html += '<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--secondary" data-act="save">Save</button>' +
				(s.can_complete ? '<button type="button" class="a3s-btn a3s-btn--primary" data-act="done">Mark dispatched</button>' : "") + "</div>";
		}
		body.innerHTML = html;
	}

	function values() {
		var out = {};
		Array.prototype.forEach.call(body.querySelectorAll("input[name], textarea[name]"), function (el) { out[el.name] = el.value; });
		return out;
	}

	body.addEventListener("click", function (e) {
		var act = e.target.closest("[data-act]");
		if (!act) return;
		if (act.dataset.act === "upload") picker.click();
		if (act.dataset.act === "save" || act.dataset.act === "done") {
			var done = act.dataset.act === "done";
			setStatus(done ? "Marking dispatched…" : "Saving…");
			call(done ? "dispatch_task.mark_dispatched" : "dispatch_task.save", Object.assign({ installation: installation }, values()))
				.then(function (s) { state = s; paint(); setStatus(done ? "Dispatched. The task is complete." : "Saved.", "ok"); })
				.catch(function (err) { setStatus(err.message, "error"); });
		}
	});

	picker.addEventListener("change", function () {
		if (!picker.files.length) return;
		var form = new FormData();
		form.append("file", picker.files[0]);
		var args = { installation: installation, task_code: state.task.code };
		if (state.slip.row && !state.slip.file_url) args.row = state.slip.row;
		else args.document_name = state.slip.name;
		var typed = values();
		setStatus("Uploading…");
		call("portal_tasks.upload", args, form)
			.then(function () { return call("dispatch_task.save", Object.assign({ installation: installation }, typed)); })
			.then(function (s) { state = s; paint(); setStatus("Uploaded.", "ok"); })
			.catch(function (err) { setStatus(err.message, "error"); });
		picker.value = "";
	});

	paint();
})();
