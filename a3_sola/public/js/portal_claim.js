/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Claim reimbursement, from inside a task: its create form and its document's page carry
 * a button (data-claim, with data-installation, data-task, data-task-name). Paid for the
 * task from one's own pocket, it is claimed back here - amount, date, what for, remarks,
 * the receipt - and goes to an operations manager to approve, then to Accounts to pay
 * (api/reimbursements.raise_claim).
 */
(function () {
	"use strict";

	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

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
		return "";
	}

	function open(button) {
		var today = new Date().toISOString().slice(0, 10);
		var taskName = button.dataset.taskName || "";
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML =
			'<div class="a3s-modal__panel a3s-taskpanel" role="dialog" aria-modal="true" aria-label="Claim Reimbursement">' +
			'<h3 class="a3s-modal__title">Claim Reimbursement</h3>' +
			'<p class="a3s-taskpanel__sub">' + esc(taskName) + " · goes to an operations manager to approve, then to Accounts to pay.</p>" +
			'<form class="a3s-form a3s-modal__form">' +
			'<div class="a3s-field"><label for="a3s-claim-amount">Amount (Rs.) <span class="a3s-req">*</span></label>' +
			'<input type="number" id="a3s-claim-amount" name="amount" min="1" step="any" required></div>' +
			'<div class="a3s-field"><label for="a3s-claim-date">Paid on <span class="a3s-req">*</span></label>' +
			'<input type="date" id="a3s-claim-date" name="expense_date" value="' + today + '" max="' + today + '" required></div>' +
			'<div class="a3s-field"><label for="a3s-claim-what">What it was for</label>' +
			'<input type="text" id="a3s-claim-what" name="description" placeholder="' + esc(taskName) + '"></div>' +
			'<div class="a3s-field"><label for="a3s-claim-remarks">Remarks</label><textarea id="a3s-claim-remarks" name="remarks" rows="2"></textarea></div>' +
			'<div class="a3s-field"><label for="a3s-claim-receipt">Receipt (optional)</label><input type="file" id="a3s-claim-receipt" name="receipt"></div>' +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary">Send for approval</button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button>' +
			'<p class="a3s-form__status" data-status role="status" aria-live="polite"></p></div></form></div>';
		document.body.appendChild(back);
		var form = back.querySelector("form");
		var status = back.querySelector("[data-status]");
		function say(text, error) { status.textContent = text || ""; status.classList.toggle("is-error", !!error); }
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
		form.elements.amount.focus();

		form.addEventListener("submit", function (event) {
			event.preventDefault();
			if (!(Number(form.elements.amount.value) > 0)) { say("Enter the amount paid.", true); return; }
			var data = new FormData();
			data.append("installation", button.dataset.installation);
			data.append("task_code", button.dataset.task);
			data.append("amount", form.elements.amount.value);
			data.append("expense_date", form.elements.expense_date.value);
			data.append("description", form.elements.description.value.trim());
			data.append("remarks", form.elements.remarks.value.trim());
			if (form.elements.receipt.files.length) data.append("file", form.elements.receipt.files[0]);
			say("Sending…");
			fetch("/api/method/a3_sola.api.reimbursements.raise_claim", {
				method: "POST", credentials: "same-origin", body: data,
				headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json" },
			}).then(function (r) {
				return r.json().catch(function () { return {}; }).then(function (body) {
					if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
					var claim = body.message;
					form.innerHTML = '<p class="a3s-taskpanel__empty">Sent for approval as <a href="' + esc(claim.route) + '">' + esc(claim.name) + "</a>.</p>" +
						'<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--ghost" data-close>Close</button></div>';
					/* The task's button now opens the claim it raised. */
					button.outerHTML = '<a class="a3s-btn a3s-btn--secondary" href="' + esc(claim.route) + '"><svg class="a3s-ic" aria-hidden="true">' +
						'<use href="#ic-wallet"></use></svg><span>View Reimbursement · ' + esc(claim.status) + "</span></a>";
				});
			}).catch(function (e) { say(e.message, true); });
		});
	}

	document.addEventListener("click", function (event) {
		var button = event.target.closest("[data-claim]");
		if (!button) return;
		event.preventDefault();
		open(button);
	});
})();
