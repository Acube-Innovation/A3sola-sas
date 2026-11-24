/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The project page's task board: a card opens its actions under itself - the task where it
 * is carried out, its documents, completing it, and skipping it (or putting a skipped one
 * back). Documents come from the job's register (api/portal_tasks.py): each with its file,
 * an upload while it is missing, and a print for the ones the system writes. Skip asks for the reason the desk
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

	/* -------------------------------------------------------- task actions */
	/* A card opens its actions in its list, under itself, pushing the cards below down - four
	   buttons in a row: open the task, its documents, complete it, skip it (or undo the skip).
	   A second click closes them; one card's are open at a time. What a task cannot do now is
	   shown greyed, with the reason in its tooltip. */
	var menu = null;

	function closeMenu() {
		if (!menu) return;
		menu.el.remove();
		menu.card.classList.remove("is-open");
		menu.button.setAttribute("aria-expanded", "false");
		menu = null;
	}

	function action(act, icon, label, opts) {
		opts = opts || {};
		var inner = '<span class="a3s-taskacts__icon"><svg class="a3s-ic" aria-hidden="true"><use href="#ic-' + icon + '"></use></svg></span>' +
			'<span class="a3s-taskacts__label">' + esc(label) + "</span>";
		var title = opts.title ? ' title="' + esc(opts.title) + '"' : "";
		if (opts.disabled) return '<span class="a3s-taskacts__btn is-disabled" aria-disabled="true"' + title + ">" + inner + "</span>";
		if (opts.href) return '<a class="a3s-taskacts__btn" href="' + esc(opts.href) + '"' + title + ">" + inner + "</a>";
		return '<button type="button" class="a3s-taskacts__btn" data-act="' + act + '"' + title + ">" + inner + "</button>";
	}

	function openMenu(button) {
		closeMenu();
		var card = button.closest(".a3s-proj__task");
		var task = {
			code: button.dataset.code, name: button.dataset.name, status: button.dataset.status, url: button.dataset.url,
			assignees: (button.dataset.assignees || "").split(",").filter(Boolean),
			assigneeNames: button.dataset.assigneeNames || "", canComplete: button.dataset.canComplete === "1",
			locked: button.dataset.locked === "1", lockReason: button.dataset.lockReason || "",
		};
		var items = [
			/* Held for 50% payment (api/stages.check_half_paid): it opens once half is in, or on exemption. */
			task.locked ? action("open", "open", "Open task", { disabled: true, title: "Waits for 50% payment" + (task.lockReason ? ": " + task.lockReason : "") })
				: task.url ? action("open", "open", "Open task", { href: task.url })
				: action("open", "open", "Open task", { disabled: true, title: "This task is skipped" }),
			action("documents", "doc", "Documents"),
			task.canComplete ? action("complete", "check", "Complete")
				: action("complete", "check", "Complete", { disabled: true,
					title: task.status === "Completed" ? "Already completed" : "Completed in its own page, or not yours to complete" }),
			task.status === "Skipped" ? action("unskip", "undo", "Undo skip")
				: task.status === "Completed" ? action("skip", "skip", "Skip", { disabled: true, title: "A completed task is not skipped" })
				: action("skip", "skip", "Skip"),
		];
		var el = document.createElement("li");
		el.className = "a3s-taskacts";
		el.id = "a3s-taskacts-" + task.code;
		el.setAttribute("role", "group");
		el.setAttribute("aria-label", task.name + ": actions");
		el.innerHTML = items.join("");
		card.after(el);
		card.classList.add("is-open");
		button.setAttribute("aria-expanded", "true");
		button.setAttribute("aria-controls", el.id);
		menu = { el: el, button: button, card: card };
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
		if (first) first.focus({ preventScroll: true });
	}

	board.addEventListener("click", function (event) {
		var button = event.target.closest(".a3s-proj__task-open");
		if (!button) return;
		event.preventDefault();
		if (menu && menu.button === button) closeMenu();
		else openMenu(button);
	});
	document.addEventListener("keydown", function (event) {
		if (event.key === "Escape" && menu) {
			var button = menu.button;
			closeMenu();
			button.focus();
		}
	});

	/* --------------------------------------------------------------- modal */
	function modal(title, sub) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML =
			'<div class="a3s-modal__panel a3s-taskpanel" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
			/* The title, and room beside it for the panel's own actions (the documents' Share). */
			'<div class="a3s-taskpanel__head"><div class="a3s-taskpanel__titles">' +
			'<h3 class="a3s-modal__title">' + esc(title) + "</h3>" +
			(sub ? '<p class="a3s-taskpanel__sub">' + esc(sub) + "</p>" : "") +
			'</div><div class="a3s-taskpanel__headacts" data-head-acts></div></div>' +
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
			head: back.querySelector("[data-head-acts]"),
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

	/* The documents' actions as icons - view, download, upload - each named in its tooltip
	   and for a screen reader (the portal's sprite, templates/includes/portal_icons.html). */
	function svgIcon(name) {
		return '<svg class="a3s-ic" aria-hidden="true"><use href="#ic-' + name + '"></use></svg>';
	}
	function iconLink(name, label, href, attrs) {
		return '<a class="a3s-icon-btn a3s-icon-btn--framed" href="' + esc(href) + '" title="' + esc(label) +
			'" aria-label="' + esc(label) + '"' + (attrs || "") + ">" + svgIcon(name) + "</a>";
	}
	function uploadButton(label, attrs) {
		return '<button type="button" class="a3s-icon-btn a3s-icon-btn--primary" title="' + esc(label) +
			'" aria-label="' + esc(label) + '" ' + attrs + ">" + svgIcon("upload") + "</button>";
	}
	/* A print opens to view, or downloads - its label says which. */
	function printLink(p, signable) {
		var name = /^view/i.test(p.label) ? "eye" : "download";
		if (!signable) return iconLink(name, p.label, p.url, name === "eye" ? ' target="_blank" rel="noopener"' : "");
		return iconLink(name, p.label, p.url + "&signed=1", ' data-print-base="' + esc(p.url) + '" target="_blank" rel="noopener"');
	}

	/* What the panel's Share (at the top) can send: each row marks its shareable document,
	   unseen - a row has no share button of its own. A paper the system prints goes as the
	   sign & seal box says. */
	function shareButton(url, label, signable) {
		return '<span hidden data-share-url="' + esc(url) + '" data-share-name="' + esc(label) + '"' +
			(signable ? " data-share-signable" : "") + "></span>";
	}

	/* Share several of the task's documents at once, from the Share at the top of its panel:
	   every document it can share is listed, all ticked; untick what is not wanted and send
	   them by WhatsApp, e-mail, the phone's share sheet, or copy the links - one message, a
	   link for each (api/task_share.share_links). Papers the system prints go as the sign &
	   seal box says. */
	function shareables(m) {
		var signed = m.body.querySelector("[data-print-signed]");
		var seen = {}, out = [];
		Array.prototype.forEach.call(m.body.querySelectorAll("[data-share-url]"), function (b) {
			var url = b.dataset.shareUrl;
			if (b.hasAttribute("data-share-signable")) url += "&signed=" + (!signed || signed.checked ? "1" : "0");
			if (seen[url]) return;
			seen[url] = true;
			out.push({ url: url, name: b.dataset.shareName });
		});
		return out;
	}
	function shareMany(m, task) {
		var docs = shareables(m);
		var s = modal("Share documents", task.name);
		var canShare = !!(navigator.share);
		s.body.innerHTML =
			'<p class="a3s-taskpanel__sub">Untick any document you do not want to send. Anyone with the links can open them for 30 days, without signing in.</p>' +
			'<div class="a3s-taskpick__bar"><label class="a3s-check"><input type="checkbox" checked data-pick-all><span>Select all</span></label>' +
			'<span class="a3s-taskpick__count" data-pick-count></span></div>' +
			'<ul class="a3s-taskdocs a3s-taskpick">' + docs.map(function (d, i) {
				return '<li class="a3s-taskdocs__row"><label class="a3s-check"><input type="checkbox" checked data-pick="' + i + '">' +
					"<span>" + esc(d.name) + "</span></label></li>";
			}).join("") + "</ul>" +
			'<div class="a3s-taskshare">' +
			'<button type="button" class="a3s-btn a3s-taskshare__wa" data-send="whatsapp">' + svgIcon("whatsapp") + "<span>WhatsApp</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--secondary" data-send="mail">' + svgIcon("mail") + "<span>E-mail</span></button>" +
			(canShare ? '<button type="button" class="a3s-btn a3s-btn--secondary" data-send="device">' + svgIcon("share") + "<span>Share files</span></button>" : "") +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-send="copy">' + svgIcon("doc") + "<span>Copy links</span></button>" +
			"</div>" +
			'<textarea class="a3s-taskshare__link" rows="4" readonly hidden aria-label="Share links" data-links></textarea>' +
			'<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--ghost" data-close>Close</button></div>';

		var picks = s.body.querySelectorAll("[data-pick]");
		var all = s.body.querySelector("[data-pick-all]");
		var count = s.body.querySelector("[data-pick-count]");
		var sends = s.body.querySelectorAll("[data-send]");
		function chosen() {
			return Array.prototype.filter.call(picks, function (p) { return p.checked; })
				.map(function (p) { return docs[Number(p.dataset.pick)].url; });
		}
		function refresh() {
			var n = chosen().length;
			count.textContent = n + " of " + docs.length + " selected";
			all.checked = n === docs.length;
			all.indeterminate = n > 0 && n < docs.length;
			Array.prototype.forEach.call(sends, function (b) { b.disabled = !n; });
		}
		refresh();
		s.body.addEventListener("change", function (e) {
			if (e.target === all) Array.prototype.forEach.call(picks, function (p) { p.checked = all.checked; });
			refresh();
		});

		/* One set of links per selection: asked for once, reused by each way of sending. */
		var made = {};
		function links(urls) {
			var key = urls.join("\n");
			if (!made[key]) made[key] = call("a3_sola.api.task_share.share_links",
				{ installation: installation, task_code: task.code, urls: JSON.stringify(urls) });
			return made[key];
		}
		var ready = null;
		s.body.addEventListener("click", function (e) {
			var b = e.target.closest("[data-send]");
			if (!b) return;
			var urls = chosen();
			if (!urls.length) { s.status("Choose at least one document.", "error"); return; }
			var how = b.dataset.send;
			s.status("Making the links…");
			if (how === "whatsapp") {
				/* Opened now, while the click still counts, so no pop-up blocker stops it. */
				var win = window.open("", "_blank");
				links(urls).then(function (r) {
					var href = "https://api.whatsapp.com/send?text=" + encodeURIComponent(r.message);
					if (win) win.location = href; else window.open(href, "_blank");
					s.status("");
				}).catch(function (err) { if (win) win.close(); s.status(err.message, "error"); });
				return;
			}
			if (how === "mail") {
				links(urls).then(function (r) {
					window.location.href = "mailto:?subject=" + encodeURIComponent(r.subject) + "&body=" + encodeURIComponent(r.message);
					s.status("");
				}).catch(function (err) { s.status(err.message, "error"); });
				return;
			}
			if (how === "copy") {
				links(urls).then(function (r) {
					var box = s.body.querySelector("[data-links]");
					box.value = r.message;
					box.hidden = false;
					return (navigator.clipboard ? navigator.clipboard.writeText(r.message) : Promise.reject()).catch(function () {
						box.select(); document.execCommand("copy");
					}).then(function () { s.status("Links copied.", "success"); });
				}).catch(function (err) { s.status(err.message, "error"); });
				return;
			}
			/* The files themselves where the device can take them, else the links. Fetching
			   them can outlast the click; if the device then refuses, a second press shares them. */
			var key = urls.join("\n");
			function send(p) {
				var data = p.files ? { files: p.files, title: p.r.subject, text: p.r.subject }
					: { title: p.r.subject, text: p.r.message };
				return navigator.share(data).then(function () { s.status(""); }).catch(function (err) {
					if (err && err.name === "NotAllowedError") { s.status("Files ready. Press Share files again.", "success"); return; }
					if (err && err.name !== "AbortError") s.status("Could not share: " + err.message, "error"); else s.status("");
				});
			}
			if (ready && ready.key === key) { send(ready); return; }
			links(urls).then(function (r) {
				return Promise.all(r.documents.map(function (d) {
					return fetch(d.link).then(function (res) { return res.blob(); }).then(function (blob) {
						return new File([blob], d.file_name, { type: blob.type || "application/pdf" });
					});
				})).then(function (files) {
					var p = { key: key, r: r, files: navigator.canShare && navigator.canShare({ files: files }) ? files : null };
					ready = p;
					return send(p);
				});
			}).catch(function (err) { s.status("Could not share: " + err.message, "error"); });
		});
	}

	/* The print a row shares: the one to view, else the first - not its download twin. */
	function sharePrint(d) {
		var prints = d.prints || [];
		return prints.find(function (p) { return !/download=1/.test(p.url); }) || prints[0] || null;
	}

	/* The tasks done on the national portal - registration, accepting the customer for the
	   loan, the installation update, the subsidy request - open it from their documents. */
	var SURYA_GHAR_PORTAL = "https://pmsuryaghar.gov.in/#/";
	var SURYA_GHAR_TASKS = ["NPA", "ACPT", "PORTUPD", "SUBREQ"];

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
								return iconLink("eye", "Open " + label + (i ? " " + (i + 1) : ""), f.url, ' target="_blank" rel="noopener"') +
									shareButton(f.url, label);
							}).join("") + "</li>";
					}).join("") +
					d.missing.map(function (mm) {
						targets.push(mm.upload);
						return '<li class="a3s-taskdocs__part"><span class="a3s-taskdocs__part-name">' + esc(mm.label) + "</span>" +
							'<span class="a3s-taskdocs__state is-missing">Missing</span>' +
							(data.can_upload ? uploadButton("Upload " + mm.label, 'data-upload-to="' + (targets.length - 1) + '"') : "") +
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
						return iconLink("eye", "Open" + (f.label ? " " + f.label : ""), f.url, ' target="_blank" rel="noopener"');
					}).join("") +
					(d.prints || []).map(function (p) { return printLink(p, true); }).join("") +
					((d.prints || []).length ? shareButton(d.prints[0].url, d.name, true) :
						d.files.map(function (f) { return shareButton(f.url, f.label || d.name); }).join("")) +
					(d.missing || []).map(function (mm) {
						targets.push(mm.upload);
						return uploadButton("Upload " + mm.label, 'data-upload-to="' + (targets.length - 1) + '"');
					}).join("") +
					"</div></li>";
				return;
			}
			/* A paper the system prints is there to view and download before anyone uploads it -
			   Generated, not Missing; the signed copy, once uploaded, shows as Uploaded. */
			var state = d.file_url ? (d.kind === "Generated" ? "Generated" : "Uploaded") : ((d.prints || []).length ? "Generated" : "Missing");
			html += '<li class="a3s-taskdocs__row">' +
				'<div class="a3s-taskdocs__info">' +
				'<p class="a3s-taskdocs__name">' + esc(d.name) + (d.mandatory ? ' <span class="a3s-req" title="Required">*</span>' : "") + "</p>" +
				'<p class="a3s-taskdocs__meta"><span class="a3s-taskdocs__state is-' + state.toLowerCase() + '">' + state + "</span>" +
				(d.file_name ? " " + esc(d.file_name) : "") + "</p>" +
				"</div>" +
				'<div class="a3s-taskdocs__actions">' +
				/* A paper printed live has its own View: no second eye for the same PDF. */
				(d.file_url && !(d.prints || []).some(function (p) { return d.file_url.indexOf(p.url) === 0; })
					? iconLink("eye", "Open " + (d.file_name || d.name), d.file_url, ' target="_blank" rel="noopener"') : "") +
				(d.prints || []).map(function (p) { return printLink(p, p.signable); }).join("") +
				(sharePrint(d) ? shareButton(sharePrint(d).url, d.name, sharePrint(d).signable) :
					(d.file_url ? shareButton(d.file_url, d.file_name || d.name) : "")) +
				(!d.file_url && data.can_upload ? uploadButton("Upload " + d.name, 'data-upload="' + esc(d.row) + '"') : "") +
				(d.removable && data.can_upload ? '<button type="button" class="a3s-icon-btn a3s-icon-btn--framed a3s-icon-btn--danger" title="Remove ' +
					esc(d.file_name || d.name) + '" aria-label="Remove ' + esc(d.file_name || d.name) + '" data-remove="' + esc(d.row) +
					'" data-remove-name="' + esc(d.name) + '">' + svgIcon("trash") + "</button>" : "") +
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
					'<div class="a3s-taskdocs__actions">' + iconLink("eye", "Open " + c.description, c.route) + "</div></li>";
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
		/* At the top: the PM Surya Ghar portal, for a task done on it, and Share - every
		   document the panel can share, all ticked to start. */
		m.head.innerHTML = (SURYA_GHAR_TASKS.indexOf(task.code) !== -1
			? '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + SURYA_GHAR_PORTAL + '" target="_blank" rel="noopener"' +
				' title="Open the PM Surya Ghar portal in a new tab">' + svgIcon("globe") + "<span>PM Surya Ghar portal</span></a>"
			: "") +
			(m.body.querySelector("[data-share-url]")
				? '<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-share-many>' + svgIcon("share") + "<span>Share</span></button>"
				: "");
		var many = m.head.querySelector("[data-share-many]");
		if (many) many.addEventListener("click", function () { shareMany(m, task); });

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
			var drop = event.target.closest("[data-remove]");
			if (drop) {
				if (!window.confirm("Remove the uploaded " + drop.dataset.removeName + "?")) return;
				m.status("Removing…");
				call("a3_sola.api.portal_tasks.remove", { installation: installation, task_code: task.code, row: drop.dataset.remove })
					.then(function (fresh) { renderDocuments(m, task, fresh); m.status("Removed.", "success"); })
					.catch(function (e) { m.status(e.message, "error"); });
				return;
			}
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

	/* --------------------------------------------------------- 50% exemption */
	/* An Operations Manager lets the held work go ahead before half is paid, saying why. */
	var exemptButton = document.querySelector("[data-exempt-half]");
	if (exemptButton) exemptButton.addEventListener("click", function () {
		var m = modal("Exempt from the 50% payment rule",
			"Structure and material procurement and the balance request start now, before half the project value is in.");
		m.body.innerHTML =
			'<form class="a3s-form a3s-modal__form">' +
			'<div class="a3s-field"><label for="a3s-exempt-reason">Reason <span class="a3s-req">*</span></label>' +
			'<textarea id="a3s-exempt-reason" name="reason" rows="3" required></textarea></div>' +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary">Exempt project</button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
		var form = m.body.querySelector("form");
		form.elements.reason.focus();
		form.addEventListener("submit", function (event) {
			event.preventDefault();
			var reason = form.elements.reason.value.trim();
			if (!reason) { m.status("Say why this project may go ahead before 50% is paid.", "error"); return; }
			m.status("Exempting…");
			call("a3_sola.api.stages.exempt_half_payment", { installation: installation, reason: reason })
				.then(function () { window.location.reload(); })
				.catch(function (e) { m.status(e.message, "error"); });
		});
	});

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

	/* ------------------------------------------------------ payment schedule */
	/* The job's payment schedule (api/billing.schedule): a payment is recorded with its
	   receipt (payment_tasks.mark_received) and waits for Accounts, who confirm or send it
	   back - each counts on the schedule only once confirmed. */
	var paysched = document.querySelector(".a3s-paysched");
	if (paysched) {
		var payData = {};
		try { payData = JSON.parse(paysched.querySelector("[data-payschedule]").textContent || "{}"); } catch (e) { /* none */ }
		paysched.addEventListener("click", function (event) {
			var record = event.target.closest("[data-pay-record]");
			var ok = event.target.closest("[data-pay-confirm]");
			var back = event.target.closest("[data-pay-sendback]");
			if (record) recordPayment();
			if (ok) confirmPayment(ok.dataset.phase, ok.dataset.payConfirm);
			if (back) sendBackPayment(back.dataset.phase, back.dataset.paySendback, back.dataset.amount);
		});
	}

	function options(list, selected) {
		return list.map(function (o) {
			var value = typeof o === "string" ? o : o.code, label = typeof o === "string" ? o : o.name + " (pending " + o.pending_text + ")";
			return '<option value="' + esc(value) + '"' + (value === selected ? " selected" : "") + ">" + esc(label) + "</option>";
		}).join("");
	}

	function recordPayment() {
		var phases = payData.phases || [];
		var m = modal("Record payment", "It counts on the schedule once Accounts confirm it.");
		var today = new Date(); today = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0");
		m.body.innerHTML =
			'<form class="a3s-form a3s-modal__form">' +
			'<div class="a3s-field"><label for="a3s-pay-phase">For <span class="a3s-req">*</span></label>' +
			'<select id="a3s-pay-phase" name="phase" required>' + options(phases) + "</select></div>" +
			'<div class="a3s-field"><label for="a3s-pay-amount">Amount (₹) <span class="a3s-req">*</span></label>' +
			'<input id="a3s-pay-amount" name="amount" type="number" min="1" step="0.01" required></div>' +
			'<div class="a3s-field"><label for="a3s-pay-date">Payment date <span class="a3s-req">*</span></label>' +
			'<input id="a3s-pay-date" name="payment_date" type="date" max="' + today + '" value="' + today + '" required></div>' +
			'<div class="a3s-field"><label for="a3s-pay-mode">Mode</label><select id="a3s-pay-mode" name="mode"><option value=""></option>' +
			options(payData.modes || [], "Bank Transfer") + "</select></div>" +
			'<div class="a3s-field"><label for="a3s-pay-ref">Reference (UTR / cheque no.)</label><input id="a3s-pay-ref" name="reference" type="text"></div>' +
			'<div class="a3s-field"><label for="a3s-pay-bank">Bank <span class="a3s-req">*</span></label><input id="a3s-pay-bank" name="bank" type="text" required></div>' +
			'<div class="a3s-field"><label for="a3s-pay-firm">Received by <span class="a3s-req">*</span></label>' +
			'<select id="a3s-pay-firm" name="company" required>' + options(payData.firms || [], (payData.firms || [])[0]) + "</select></div>" +
			'<div class="a3s-field"><label for="a3s-pay-file">Receipt or bank advice <span class="a3s-req">*</span></label>' +
			'<input id="a3s-pay-file" name="file" type="file" accept="image/*,application/pdf"></div>' +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary">Record payment</button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
		var form = m.body.querySelector("form");
		/* The phase's pending amount, offered as the amount. */
		function prefill() {
			var phase = phases.filter(function (p) { return p.code === form.elements.phase.value; })[0];
			if (phase) form.elements.amount.value = Number(phase.pending).toFixed(2);
		}
		form.elements.phase.addEventListener("change", prefill);
		prefill();
		form.addEventListener("submit", function (event) {
			event.preventDefault();
			var data = new FormData();
			data.append("installation", installation);
			data.append("task_code", form.elements.phase.value);
			["amount", "payment_date", "mode", "reference", "bank", "company"].forEach(function (k) { data.append(k, form.elements[k].value); });
			if (form.elements.file.files.length) data.append("file", form.elements.file.files[0]);
			m.status("Recording…");
			call("a3_sola.api.payment_tasks.mark_received", null, data)
				.then(function () { window.location.reload(); })
				.catch(function (e) { m.status(e.message, "error"); });
		});
	}

	function confirmPayment(phase, row) {
		if (!window.confirm("Confirm this payment has been received?")) return;
		call("a3_sola.api.payment_tasks.confirm", { installation: installation, task_code: phase, payment: row })
			.then(function () { window.location.reload(); })
			.catch(function (e) { window.alert(e.message); });
	}

	function sendBackPayment(phase, row, amount) {
		var m = modal("Send back " + amount, "It will not count, and goes back to whoever recorded it.");
		m.body.innerHTML =
			'<form class="a3s-form a3s-modal__form">' +
			'<div class="a3s-field"><label for="a3s-pay-reason">Why is it not confirmed? <span class="a3s-req">*</span></label>' +
			'<textarea id="a3s-pay-reason" name="reason" rows="3" required></textarea></div>' +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary">Send back</button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
		var form = m.body.querySelector("form");
		form.elements.reason.focus();
		form.addEventListener("submit", function (event) {
			event.preventDefault();
			var reason = form.elements.reason.value.trim();
			if (!reason) { m.status("Say why the payment is not confirmed.", "error"); return; }
			call("a3_sola.api.payment_tasks.send_back", { installation: installation, task_code: phase, payment: row, reason: reason })
				.then(function () { window.location.reload(); })
				.catch(function (e) { m.status(e.message, "error"); });
		});
	}
})();
