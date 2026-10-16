/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The project page's task board: a card opens a small menu - the task where it is carried
 * out, its documents, and skipping it (or putting a skipped one back). Documents come from
 * the job's register (api/portal_tasks.py): each with its file, an upload while it is
 * missing, and a print for the ones the system writes. Skip asks for the reason the desk
 * asks for, and posts the same tasks.skip_task; the page then reloads with the board as
 * it now stands. The server decides what is allowed - a mandatory task is a manager's to
 * skip - and its message is shown as it is.
 */
(function () {
	"use strict";

	var board = document.querySelector(".a3s-proj__board[data-installation]");
	if (!board) return;
	var installation = board.dataset.installation;
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}

	/* Pull the human-readable text out of Frappe's _server_messages envelope. */
	function serverMessage(body) {
		try {
			var msgs = JSON.parse((body && body._server_messages) || "[]");
			if (msgs.length) return String(JSON.parse(msgs[0]).message || "").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (body && body.exception) ? String(body.exception).split(":").slice(1).join(":").trim() : "";
	}

	function call(method, args, formData) {
		var opts = { method: "POST", credentials: "same-origin", headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json" } };
		if (formData) {
			opts.body = formData;
		} else {
			opts.headers["Content-Type"] = "application/json";
			opts.body = JSON.stringify(args || {});
		}
		return fetch("/api/method/" + method, opts).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
				return body.message;
			});
		});
	}

	/* ---------------------------------------------------------------- menu */
	var menu = null;

	function closeMenu() {
		if (!menu) return;
		menu.el.remove();
		menu.button.setAttribute("aria-expanded", "false");
		menu = null;
	}

	function openMenu(button) {
		closeMenu();
		var card = button.closest(".a3s-proj__task");
		var task = {
			code: button.dataset.code, name: button.dataset.name, status: button.dataset.status, url: button.dataset.url,
			assignees: (button.dataset.assignees || "").split(",").filter(Boolean),
			assigneeNames: button.dataset.assigneeNames || "", canComplete: button.dataset.canComplete === "1",
		};
		var el = document.createElement("div");
		el.className = "a3s-taskmenu";
		el.setAttribute("role", "menu");
		var items = [];
		if (task.url) items.push('<a role="menuitem" href="' + esc(task.url) + '">Open task</a>');
		else items.push('<span role="menuitem" aria-disabled="true" class="is-disabled">Open task <small>(skipped)</small></span>');
		items.push('<button type="button" role="menuitem" data-act="documents">Documents</button>');
		if (task.canComplete) items.push('<button type="button" role="menuitem" data-act="complete">Complete task</button>');
		if (task.status === "Skipped") items.push('<button type="button" role="menuitem" data-act="unskip">Undo skip</button>');
		else if (task.status !== "Completed") items.push('<button type="button" role="menuitem" data-act="skip">Skip task</button>');
		el.innerHTML = items.join("");
		/* On the page, not in the card: the board clips what overflows it. */
		document.body.appendChild(el);
		var rect = card.getBoundingClientRect();
		var width = el.offsetWidth;
		el.style.top = Math.min(rect.bottom + 4, window.innerHeight - el.offsetHeight - 8) + "px";
		el.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)) + "px";
		button.setAttribute("aria-expanded", "true");
		menu = { el: el, button: button };
		el.addEventListener("click", function (event) {
			var act = event.target.closest("[data-act]");
			if (!act) return;
			closeMenu();
			if (act.dataset.act === "documents") showDocuments(task);
			else if (act.dataset.act === "complete") askComplete(task);
			else if (act.dataset.act === "skip") askSkip(task);
			else if (act.dataset.act === "unskip") askUnskip(task);
		});
		var first = el.querySelector("a, button");
		if (first) first.focus();
	}

	board.addEventListener("click", function (event) {
		var button = event.target.closest(".a3s-proj__task-open");
		if (!button) return;
		event.preventDefault();
		if (menu && menu.button === button) closeMenu();
		else openMenu(button);
	});
	document.addEventListener("click", function (event) {
		if (menu && !menu.el.contains(event.target) && event.target.closest(".a3s-proj__task-open") !== menu.button) closeMenu();
	});
	document.addEventListener("keydown", function (event) { if (event.key === "Escape") closeMenu(); });
	window.addEventListener("scroll", closeMenu, true);
	window.addEventListener("resize", closeMenu);

	/* --------------------------------------------------------------- modal */
	function modal(title, sub) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML =
			'<div class="a3s-modal__panel a3s-taskpanel" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
			'<h3 class="a3s-modal__title">' + esc(title) + "</h3>" +
			(sub ? '<p class="a3s-taskpanel__sub">' + esc(sub) + "</p>" : "") +
			'<div class="a3s-taskpanel__body"></div>' +
			'<p class="a3s-form__status" data-status role="status" aria-live="polite"></p>' +
			"</div>";
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
		document.body.appendChild(back);
		var status = back.querySelector("[data-status]");
		return {
			el: back,
			body: back.querySelector(".a3s-taskpanel__body"),
			close: close,
			status: function (text, kind) {
				status.textContent = text || "";
				status.classList.toggle("is-error", kind === "error");
				status.classList.toggle("is-success", kind === "success");
			},
		};
	}

	/* ----------------------------------------------------------- documents */
	function showDocuments(task) {
		var m = modal(task.name, "Documents for this task");
		m.body.innerHTML = '<p class="a3s-taskpanel__empty">Loading…</p>';
		call("a3_sola.api.portal_tasks.task_documents", { installation: installation, task_code: task.code })
			.then(function (data) { renderDocuments(m, task, data); })
			.catch(function (e) { m.body.innerHTML = ""; m.status(e.message, "error"); });
	}

	function renderDocuments(m, task, data) {
		var rows = data.documents || [];
		var html = "";
		if (!rows.length) html += '<p class="a3s-taskpanel__empty">This task lists no documents.</p>';
		/* What the system prints goes out signed and sealed while the box is ticked. */
		if (rows.some(function (d) { return (d.prints || []).some(function (p) { return p.signable; }); })) {
			html += '<label class="a3s-check a3s-taskdocs__sign"><input type="checkbox" checked data-print-signed>' +
				"<span>Print with sign &amp; seal</span></label>";
		}
		html += '<ul class="a3s-taskdocs">';
		var targets = [];
		rows.forEach(function (d) {
			/* A row of several papers - the customer's KYC, the PM Surya Ghar registration - is a
			   checklist: its name and count across the top, then each paper on a line of its own,
			   Uploaded with Open, or Missing with Upload. */
			var parts = {};
			(d.files || []).forEach(function (f) { if (f.label) (parts[f.label] = parts[f.label] || []).push(f); });
			var labels = Object.keys(parts);
			if (d.files && !d.note && labels.length + (d.missing || []).length >= 2) {
				var total = labels.length + d.missing.length;
				html += '<li class="a3s-taskdocs__row a3s-taskdocs__row--group"><div class="a3s-taskdocs__info">' +
					'<p class="a3s-taskdocs__name">' + esc(d.name) + (d.mandatory ? ' <span class="a3s-req" title="Required">*</span>' : "") + "</p>" +
					'<p class="a3s-taskdocs__meta"><span class="a3s-taskdocs__state is-' + (d.missing.length ? (labels.length ? "partly" : "missing") : "uploaded") + '">' +
					labels.length + " of " + total + " uploaded</span></p></div>" +
					'<ul class="a3s-taskdocs__parts">' +
					labels.map(function (label) {
						return '<li class="a3s-taskdocs__part"><span class="a3s-taskdocs__part-name">' + esc(label) + "</span>" +
							'<span class="a3s-taskdocs__state is-uploaded">Uploaded</span>' +
							parts[label].map(function (f, i) {
								return '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(f.url) + '" target="_blank" rel="noopener">Open' + (i ? " " + (i + 1) : "") + "</a>";
							}).join("") + "</li>";
					}).join("") +
					d.missing.map(function (mm) {
						targets.push(mm.upload);
						return '<li class="a3s-taskdocs__part"><span class="a3s-taskdocs__part-name">' + esc(mm.label) + "</span>" +
							'<span class="a3s-taskdocs__state is-missing">Missing</span>' +
							(data.can_upload ? '<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-upload-to="' + (targets.length - 1) + '">Upload</button>' : "") +
							"</li>";
					}).join("") + "</ul></li>";
				return;
			}
			/* Several files to a row - the loan's pack - and an upload for each missing one. */
			if (d.files) {
				var done = d.files.length && !(d.missing || []).length;
				var st = d.note && !d.files.length ? "Missing" : (done ? (d.kind === "Generated" ? "Generated" : "Uploaded") : (d.files.length ? "Partly" : "Missing"));
				html += '<li class="a3s-taskdocs__row"><div class="a3s-taskdocs__info">' +
					'<p class="a3s-taskdocs__name">' + esc(d.name) + (d.mandatory ? ' <span class="a3s-req" title="Required">*</span>' : "") + "</p>" +
					'<p class="a3s-taskdocs__meta">' + (d.note ? esc(d.note) : '<span class="a3s-taskdocs__state is-' + st.toLowerCase() + '">' + st + "</span>") + "</p></div>" +
					'<div class="a3s-taskdocs__actions">' +
					d.files.map(function (f) {
						return '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(f.url) + '" target="_blank" rel="noopener">Open' + (f.label ? " " + esc(f.label) : "") + "</a>";
					}).join("") +
					(d.prints || []).map(function (p) {
						return '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(p.url) + '&signed=1" data-print-base="' +
							esc(p.url) + '" target="_blank" rel="noopener">' + esc(p.label) + "</a>";
					}).join("") +
					(d.missing || []).map(function (mm) {
						targets.push(mm.upload);
						return '<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-upload-to="' + (targets.length - 1) + '">Upload ' + esc(mm.label) + "</button>";
					}).join("") +
					"</div></li>";
				return;
			}
			var state = d.file_url ? (d.kind === "Generated" ? "Generated" : "Uploaded") : "Missing";
			html += '<li class="a3s-taskdocs__row">' +
				'<div class="a3s-taskdocs__info">' +
				'<p class="a3s-taskdocs__name">' + esc(d.name) + (d.mandatory ? ' <span class="a3s-req" title="Required">*</span>' : "") + "</p>" +
				'<p class="a3s-taskdocs__meta"><span class="a3s-taskdocs__state is-' + state.toLowerCase() + '">' + state + "</span>" +
				(d.file_name ? " " + esc(d.file_name) : "") + "</p>" +
				"</div>" +
				'<div class="a3s-taskdocs__actions">' +
				(d.file_url ? '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(d.file_url) + '" target="_blank" rel="noopener">Open</a>' : "") +
				(d.prints || []).map(function (p) {
					if (!p.signable) return '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(p.url) + '">' + esc(p.label) + "</a>";
					return '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(p.url) + '&signed=1" data-print-base="' +
						esc(p.url) + '" target="_blank" rel="noopener">' + esc(p.label) + "</a>";
				}).join("") +
				(!d.file_url && data.can_upload ? '<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-upload="' + esc(d.row) + '">Upload</button>' : "") +
				"</div></li>";
		});
		html += "</ul>";
		/* What has been claimed back for this task, and where each claim stands. */
		if ((data.claims || []).length) {
			html += '<p class="a3s-taskdocs__heading">Reimbursements</p><ul class="a3s-taskdocs">';
			data.claims.forEach(function (c) {
				html += '<li class="a3s-taskdocs__row"><div class="a3s-taskdocs__info">' +
					'<p class="a3s-taskdocs__name">' + esc(c.description) + " · " + esc(c.amount) + "</p>" +
					'<p class="a3s-taskdocs__meta"><span class="a3s-taskdocs__state is-' + esc(c.status.toLowerCase().replace(/ /g, "-")) + '">' +
					esc(c.status) + "</span> " + esc(c.who) + "</p></div>" +
					'<div class="a3s-taskdocs__actions"><a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(c.route) + '">Open</a></div></li>';
			});
			html += "</ul>";
		}
		if (data.can_upload && !data.fixed) {
			html += '<form class="a3s-form a3s-taskdocs__add">' +
				'<label for="a3s-taskdoc-name">Add another document</label>' +
				'<div class="a3s-taskdocs__addrow"><input type="text" id="a3s-taskdoc-name" placeholder="What is it? e.g. Sanction letter">' +
				'<button type="button" class="a3s-btn a3s-btn--secondary a3s-btn--sm" data-upload-new>Choose file</button></div>' +
				'<p class="a3s-field__hint">Up to ' + esc(data.max_file_mb) + " MB.</p></form>";
		}
		html += '<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--ghost" data-close>Close</button></div>';
		html += '<input type="file" hidden data-file>';
		m.body.innerHTML = html;

		var signed = m.body.querySelector("[data-print-signed]");
		if (signed) {
			signed.addEventListener("change", function () {
				Array.prototype.forEach.call(m.body.querySelectorAll("[data-print-base]"), function (link) {
					link.href = link.dataset.printBase + "&signed=" + (signed.checked ? "1" : "0");
				});
			});
		}
		var picker = m.body.querySelector("[data-file]");
		var pending = null;
		m.body.addEventListener("click", function (event) {
			var one = event.target.closest("[data-upload]");
			var extra = event.target.closest("[data-upload-new]");
			var to = event.target.closest("[data-upload-to]");
			if (one) { pending = { row: one.dataset.upload }; picker.click(); }
			if (to) { pending = { target: targets[Number(to.dataset.uploadTo)] }; picker.click(); }
			if (extra) {
				var name = m.body.querySelector("#a3s-taskdoc-name").value.trim();
				if (!name) { m.status("Say what the document is first.", "error"); return; }
				pending = { document_name: name };
				picker.click();
			}
		});
		picker.addEventListener("change", function () {
			if (!picker.files.length || !pending) return;
			var reload = function () {
				return call("a3_sola.api.portal_tasks.task_documents", { installation: installation, task_code: task.code })
					.then(function (fresh) { renderDocuments(m, task, fresh); m.status("Uploaded.", "success"); });
			};
			if (pending.target) {
				var t = pending.target, up = new FormData();
				up.append("file", picker.files[0]);
				var method;
				if (t.kind === "consumer") {
					/* Kept on the consumer, filed as what it is (its KYC rows follow). */
					method = "a3_sola.api.portal_attachments.upload";
					up.append("doctype", "Solar Consumer"); up.append("name", t.consumer); up.append("document_type", t.document_type);
				} else {
					method = "a3_sola.api.portal_tasks.upload";
					up.append("installation", installation); up.append("task_code", t.task_code); up.append("document_name", t.document_name);
				}
				m.status("Uploading…");
				call(method, null, up).then(reload).catch(function (e) { m.status(e.message, "error"); });
				pending = null; picker.value = "";
				return;
			}
			var form = new FormData();
			form.append("installation", installation);
			form.append("task_code", task.code);
			if (pending.row) form.append("row", pending.row);
			if (pending.document_name) form.append("document_name", pending.document_name);
			form.append("file", picker.files[0]);
			m.status("Uploading…");
			call("a3_sola.api.portal_tasks.upload", null, form).then(function (data) {
				renderDocuments(m, task, data);
				m.status("Uploaded.", "success");
			}).catch(function (e) { m.status(e.message, "error"); });
		});
	}

	/* ------------------------------------------------------------ complete */
	function askComplete(task) {
		var m = modal("Complete " + task.name, "Marked Completed straight away - nothing more to fill in on the task.");
		m.body.innerHTML =
			'<form class="a3s-form a3s-modal__form">' +
			(task.assigneeNames ? '<p class="a3s-field__hint" style="margin:0 0 0.75rem">Assigned to: <b>' + esc(task.assigneeNames) + "</b></p>" : "") +
			'<div class="a3s-field"><label for="a3s-done-remarks">Remark <span class="a3s-req">*</span></label>' +
			'<textarea id="a3s-done-remarks" name="remarks" rows="3" required placeholder="How was it done?"></textarea></div>' +
			'<label style="display:flex;gap:0.5rem;align-items:flex-start;margin-top:0.75rem"><input type="checkbox" name="confirmed" required>' +
			"<span>I confirm this task is done.</span></label>" +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary">Complete task</button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
		var form = m.body.querySelector("form");
		form.elements.remarks.focus();
		form.addEventListener("submit", function (event) {
			event.preventDefault();
			var remarks = form.elements.remarks.value.trim();
			if (!remarks) { m.status("Add a remark: how was the task done?", "error"); return; }
			if (!form.elements.confirmed.checked) { m.status("Tick the confirmation that the task is done.", "error"); return; }
			m.status("Completing…");
			call("a3_sola.api.tasks.complete_from_board", { installation: installation, task_code: task.code, remarks: remarks, confirmed: 1 })
				.then(function () { window.location.reload(); })
				.catch(function (e) { m.status(e.message, "error"); });
		});
	}

	/* ---------------------------------------------------------------- skip */
	function askSkip(task) {
		var m = modal("Skip " + task.name, "The task will show as Skipped. It can be put back later.");
		m.body.innerHTML =
			'<form class="a3s-form a3s-modal__form">' +
			'<div class="a3s-field"><label for="a3s-skip-reason">Reason <span class="a3s-req">*</span></label>' +
			'<textarea id="a3s-skip-reason" name="reason" rows="3" required></textarea></div>' +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary">Skip task</button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
		var form = m.body.querySelector("form");
		form.elements.reason.focus();
		form.addEventListener("submit", function (event) {
			event.preventDefault();
			var reason = form.elements.reason.value.trim();
			if (!reason) { m.status("Say why the task is not needed.", "error"); return; }
			m.status("Skipping…");
			call("a3_sola.api.tasks.skip_task", { installation: installation, task_code: task.code, reason: reason })
				.then(function () { window.location.reload(); })
				.catch(function (e) { m.status(e.message, "error"); });
		});
	}

	function askUnskip(task) {
		var m = modal("Put back " + task.name, "The task returns to Pending.");
		m.body.innerHTML =
			'<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--primary" data-go>Undo skip</button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div>';
		m.body.querySelector("[data-go]").addEventListener("click", function () {
			m.status("Putting it back…");
			call("a3_sola.api.tasks.unskip_task", { installation: installation, task_code: task.code })
				.then(function () { window.location.reload(); })
				.catch(function (e) { m.status(e.message, "error"); });
		});
	}
})();
