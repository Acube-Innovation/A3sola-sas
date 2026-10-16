/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The KYC Documents card (templates/includes/portal_kyc.html): each paper the customer is
 * asked for, uploaded or pending, and how many are in. A pending one is uploaded from here
 * onto the record, as that document type (a3_sola.api.portal_attachments.upload); the card
 * then reads the summary again (a3_sola.api.kyc.summary) and asks the Attachments card to
 * reload. A file added or removed in the Attachments card updates this one the same way.
 */
(function () {
	"use strict";

	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function message(data, fallback) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (msgs.length) return JSON.parse(msgs[0]).message.replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception ? String(data.exception).split(":").slice(1).join(":").trim() : "") || fallback;
	}

	function call(method, body, isGet) {
		var opts = { credentials: "same-origin", headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } };
		var url = "/api/method/" + method;
		if (isGet) url += "?" + new URLSearchParams(body).toString();
		else { opts.method = "POST"; opts.body = body; }
		return fetch(url, opts).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (data) {
				if (!r.ok) throw new Error(message(data, "Something went wrong (" + r.status + ")."));
				return data.message || {};
			});
		});
	}

	function el(tag, cls, text) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text != null) n.textContent = text;
		return n;
	}

	Array.prototype.forEach.call(document.querySelectorAll("[data-kyc]"), function (card) {
		var doctype = card.dataset.doctype, name = card.dataset.name;
		var list = card.querySelector("[data-kyc-list]");
		var count = card.querySelector("[data-kyc-count]");
		var summary = card.querySelector("[data-kyc-summary]");
		var input = card.querySelector("[data-kyc-input]");
		var status = card.querySelector("[data-kyc-status]");
		var pendingType = null;

		function setStatus(text, tone) {
			status.textContent = text || "";
			status.dataset.tone = tone || "";
			status.hidden = !text;
		}

		function paint(data) {
			count.textContent = data.uploaded + " of " + data.total + " uploaded";
			summary.textContent = data.pending
				? data.pending + " pending. A document uploaded on the lead or the customer counts for both."
				: "All KYC documents are in.";
			list.textContent = "";
			(data.items || []).forEach(function (item) {
				var li = el("li", "a3s-taskdocs__row");
				var info = el("div", "a3s-taskdocs__info");
				info.appendChild(el("p", "a3s-taskdocs__name", item.label));
				var metaLine = el("p", "a3s-taskdocs__meta");
				metaLine.appendChild(el("span", "a3s-taskdocs__state " + (item.uploaded ? "is-uploaded" : "is-missing"),
					item.uploaded ? "Uploaded" : "Pending"));
				info.appendChild(metaLine);
				li.appendChild(info);
				var actions = el("div", "a3s-taskdocs__actions");
				item.files.forEach(function (f) {
					var a = el("a", "a3s-btn a3s-btn--secondary a3s-btn--sm", "Open" + (item.types.length > 1 ? " " + f.type : ""));
					a.href = f.url; a.target = "_blank"; a.rel = "noopener";
					actions.appendChild(a);
				});
				if (!item.uploaded && data.can_upload) {
					var up = el("button", "a3s-btn a3s-btn--primary a3s-btn--sm", "Upload");
					up.type = "button";
					up.addEventListener("click", function () { pendingType = item.types[0]; input.click(); });
					actions.appendChild(up);
				}
				li.appendChild(actions);
				list.appendChild(li);
			});
		}

		function reload() {
			return call("a3_sola.api.kyc.summary", { doctype: doctype, name: name }, true).then(paint)
				.catch(function (e) { setStatus(e.message, "error"); });
		}

		input.addEventListener("change", function () {
			if (!input.files.length || !pendingType) return;
			var body = new FormData();
			body.append("doctype", doctype); body.append("name", name); body.append("document_type", pendingType);
			body.append("file", input.files[0], input.files[0].name);
			setStatus("Uploading " + pendingType + "…");
			var kind = pendingType;
			call("a3_sola.api.portal_attachments.upload", body).then(function () {
				setStatus(kind + " uploaded.", "ok");
				document.dispatchEvent(new CustomEvent("a3s:attachments-reload", { detail: { doctype: doctype, name: name } }));
				return reload();
			}).catch(function (e) { setStatus(e.message, "error"); });
			pendingType = null; input.value = "";
		});

		/* The Attachments card changed: a file added, retyped or removed there. */
		document.addEventListener("a3s:attachments-changed", function (e) {
			if (e.detail && e.detail.doctype === doctype && e.detail.name === name) reload();
		});

		try { paint(JSON.parse(card.querySelector("[data-kyc-data]").textContent)); } catch (e) { reload(); }
	});
})();
