/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The share buttons of a document's page (templates/includes/portal_share.html): the
 * device's share sheet for the PDF itself, and the WhatsApp and email links, whose click
 * also downloads the PDF to drop into the chat or the email - a link carries no file.
 */
(function () {
	"use strict";

	/* A page may carry more than one set (a purchase list and its pending items): each is
	   wired once, however many times the script is included. */
	if (window.a3sShareWired) return;
	window.a3sShareWired = true;
	Array.prototype.forEach.call(document.querySelectorAll("[data-share]"), wire);

	function wire(share) {
	/* ---- share the PDF itself, through the device's share sheet ---------- */
	var shareButton = share.querySelector("[data-share-file]");
	if (shareButton && navigator.canShare && window.File
			&& navigator.canShare({ files: [new File([""], "x.pdf", { type: "application/pdf" })] })) {
		shareButton.hidden = false;
		shareButton.addEventListener("click", function () {
			shareButton.disabled = true;
			shareButton.classList.add("is-busy");
			fetch(share.dataset.pdf, { credentials: "same-origin" })
				.then(function (r) {
					if (!r.ok) throw new Error("The PDF could not be made.");
					return r.blob();
				})
				.then(function (blob) {
					var file = new File([blob], share.dataset.file || "proposal.pdf", { type: "application/pdf" });
					return navigator.share({ files: [file], title: share.dataset.title, text: share.dataset.text });
				})
				.catch(function (e) {
					// Closing the share sheet is not an error worth saying.
					if (e && e.name !== "AbortError") window.alert(e.message || "Sharing did not work.");
				})
				.then(function () {
					shareButton.disabled = false;
					shareButton.classList.remove("is-busy");
				});
		});
	}

	/* ---- WhatsApp and email: the chat opens by the link, and the PDF downloads to go in it */
	var hint = share.querySelector("[data-share-hint]");
	var hintTimer = null;
	{
		Array.prototype.forEach.call(share.querySelectorAll("[data-share-download]"), function (link) {
			link.addEventListener("click", function () {
				// Not prevented: the link still opens WhatsApp or the mail app, as a click does.
				var save = document.createElement("a");
				save.href = share.dataset.download;
				save.download = share.dataset.file || "";
				document.body.appendChild(save);
				save.click();
				save.remove();
				if (hint) {
					hint.textContent = "Downloading " + (share.dataset.file || "the proposal PDF") + " \u2013 " + link.dataset.shareDownload + ".";
					hint.hidden = false;
					window.clearTimeout(hintTimer);
					hintTimer = window.setTimeout(function () { hint.hidden = true; }, 12000);
				}
			});
		});
	}

	/* ---- email: sent by the site, the PDF attached ---------------------- */
	var emailButton = share.querySelector("[data-share-email]");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function serverMessage(data) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (msgs.length) return String(JSON.parse(msgs[0]).message || "").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return "";
	}

	function field(label, control, id) {
		var wrap = document.createElement("div");
		wrap.className = "a3s-field";
		var l = document.createElement("label");
		l.htmlFor = id;
		l.textContent = label;
		control.id = id;
		wrap.appendChild(l);
		wrap.appendChild(control);
		return wrap;
	}

	if (emailButton) {
		emailButton.addEventListener("click", function () {
			var d = emailButton.dataset;
			var back = document.createElement("div");
			back.className = "a3s-modal";
			var panel = document.createElement("div");
			panel.className = "a3s-modal__panel a3s-share-mail";
			panel.setAttribute("role", "dialog");
			panel.setAttribute("aria-modal", "true");
			panel.setAttribute("aria-label", "Email the PDF");
			var title = document.createElement("h3");
			title.className = "a3s-modal__title";
			title.textContent = "Email " + d.name;
			var note = document.createElement("p");
			note.className = "a3s-field__hint";
			note.textContent = "Sent from the company mailbox with " + (share.dataset.file || "the PDF") + " attached, and kept on this record's timeline.";
			var form = document.createElement("form");
			form.className = "a3s-form a3s-modal__form";
			var to = document.createElement("input");
			to.type = "text"; to.value = d.to || ""; to.placeholder = "customer@example.com"; to.required = true;
			var subject = document.createElement("input");
			subject.type = "text"; subject.value = d.subject || ""; subject.required = true;
			var body = document.createElement("textarea");
			body.rows = 12; body.value = d.text || "";
			form.appendChild(field("To", to, "share-mail-to"));
			form.appendChild(field("Subject", subject, "share-mail-subject"));
			form.appendChild(field("Message", body, "share-mail-body"));
			var tip = document.createElement("p");
			tip.className = "a3s-field__hint";
			tip.textContent = "Text between *stars* is sent in bold, as on WhatsApp.";
			form.appendChild(tip);
			var status = document.createElement("p");
			status.className = "a3s-form__status";
			status.setAttribute("role", "status");
			var actions = document.createElement("div");
			actions.className = "a3s-form__actions";
			var send = document.createElement("button");
			send.type = "submit"; send.className = "a3s-btn a3s-btn--primary"; send.textContent = "Send email";
			var cancel = document.createElement("button");
			cancel.type = "button"; cancel.className = "a3s-btn a3s-btn--ghost"; cancel.textContent = "Cancel";
			actions.appendChild(send); actions.appendChild(cancel);
			form.appendChild(status); form.appendChild(actions);
			panel.appendChild(title); panel.appendChild(note); panel.appendChild(form);
			back.appendChild(panel);

			var sending = false;
			function close() { if (sending) return; back.remove(); document.removeEventListener("keydown", onKey); }
			function onKey(e) { if (e.key === "Escape") close(); }
			document.addEventListener("keydown", onKey);
			back.addEventListener("click", function (e) { if (e.target === back) close(); });
			cancel.addEventListener("click", close);
			form.addEventListener("submit", function (e) {
				e.preventDefault();
				sending = true;
				send.disabled = cancel.disabled = true;
				send.classList.add("is-busy");
				send.textContent = "Sending\u2026";
				status.textContent = "";
				status.classList.remove("is-error");
				fetch("/api/method/a3_sola.api.portal_share.send_email", {
					method: "POST",
					credentials: "same-origin",
					headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
					body: JSON.stringify({ doctype: d.doctype, name: d.name, recipients: to.value, subject: subject.value, message: body.value, part: d.part || "" })
				}).then(function (r) {
					return r.json().catch(function () { return {}; }).then(function (data) { return { ok: r.ok, data: data }; });
				}).then(function (res) {
					if (!res.ok) throw new Error(serverMessage(res.data) || "The email could not be sent.");
					status.classList.add("is-success");
					status.textContent = "Sent to " + ((res.data.message || {}).sent_to || to.value) + ". Refreshing\u2026";
					// The record's timeline - and a proposal's dispatch - now show it.
					window.setTimeout(function () { window.location.reload(); }, 1200);
				}).catch(function (err) {
					sending = false;
					send.disabled = cancel.disabled = false;
					send.classList.remove("is-busy");
					send.textContent = "Send email";
					status.classList.add("is-error");
					status.textContent = err.message || "The email could not be sent.";
				});
			});
			document.body.appendChild(back);
			to.focus();
		});
	}

	/* ---- download: which print format, each with its own buttons ---------- */
	var formatsButton = share.querySelector("[data-share-formats]");
	var formatsNode = share.querySelector("[data-share-formats-list]");
	if (formatsButton && formatsNode) {
		var formats = [];
		try { formats = JSON.parse(formatsNode.textContent) || []; } catch (e) { formats = []; }
		formatsButton.addEventListener("click", function () {
			var back = document.createElement("div");
			back.className = "a3s-modal";
			var panel = document.createElement("div");
			panel.className = "a3s-modal__panel a3s-share-formats";
			panel.setAttribute("role", "dialog");
			panel.setAttribute("aria-modal", "true");
			panel.setAttribute("aria-label", "Download PDF");
			var head = document.createElement("div");
			head.className = "a3s-share-formats__head";
			var title = document.createElement("h3");
			title.className = "a3s-modal__title";
			title.textContent = "Download PDF";
			var x = document.createElement("button");
			x.type = "button"; x.className = "a3s-share-formats__x"; x.textContent = "\u00d7"; x.setAttribute("aria-label", "Close");
			head.appendChild(title); head.appendChild(x);
			var note = document.createElement("p");
			note.className = "a3s-field__hint";
			note.textContent = "Choose the print format.";
			var list = document.createElement("ul");
			list.className = "a3s-share-formats__list";
			formats.forEach(function (f) {
				var li = document.createElement("li");
				var name = document.createElement("span");
				name.className = "a3s-share-formats__name";
				name.textContent = f.name;
				if (f["default"]) {
					var tag = document.createElement("small");
					tag.className = "a3s-share-formats__tag";
					tag.textContent = "Default";
					name.appendChild(tag);
				}
				var actions = document.createElement("span");
				actions.className = "a3s-share-formats__actions";
				var view = document.createElement("a");
				view.className = "a3s-btn a3s-btn--ghost a3s-btn--sm";
				view.href = f.view; view.target = "_blank"; view.rel = "noopener"; view.textContent = "View";
				var dl = document.createElement("a");
				dl.className = "a3s-btn a3s-btn--primary a3s-btn--sm";
				dl.href = f.download; dl.textContent = "Download";
				dl.setAttribute("aria-label", "Download " + f.name);
				actions.appendChild(view); actions.appendChild(dl);
				li.appendChild(name); li.appendChild(actions);
				list.appendChild(li);
			});
			panel.appendChild(head); panel.appendChild(note); panel.appendChild(list);
			back.appendChild(panel);
			function onKey(e) { if (e.key === "Escape") shut(); }
			function shut() { back.remove(); document.removeEventListener("keydown", onKey); formatsButton.focus(); }
			document.addEventListener("keydown", onKey);
			back.addEventListener("click", function (e) { if (e.target === back) shut(); });
			x.addEventListener("click", shut);
			document.body.appendChild(back);
			var first = list.querySelector("a.a3s-btn--primary");
			if (first) first.focus();
		});
	}
	}
})();
