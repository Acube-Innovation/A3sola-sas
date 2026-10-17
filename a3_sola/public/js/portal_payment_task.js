/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * A payment task's page (www/a3solaportal/projects/task.html, api/payment_tasks): has the
 * payment been received - Yes files the receipt and sends the task to Accounts; Accounts then
 * confirms it, completing the task, or sends it back with a reason. Every step redraws the
 * page from the state the server returns.
 */
(function () {
	"use strict";

	var card = document.querySelector("[data-paytask]");
	if (!card) return;
	var API = "/api/method/a3_sola.api.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var installation = card.dataset.installation, task = card.dataset.task;
	var body = card.querySelector("[data-paytask-body]");
	var status = card.querySelector("[data-paytask-status]");
	var picker = card.querySelector("[data-paytask-file]");
	var answer = "";
	/* What is typed before Send: kept across redraws (an upload redraws the page). */
	var draft = null;

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

	function call(method, args, formData) {
		var form = formData || new FormData();
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

	function receipt(s) {
		var d = s.document;
		var state = d.file_url ? "Uploaded" : "Missing";
		return '<ul class="a3s-taskdocs"><li class="a3s-taskdocs__row"><div class="a3s-taskdocs__info">' +
			'<p class="a3s-taskdocs__name">' + esc(d.name) + ' <span class="a3s-req" title="Required">*</span></p>' +
			'<p class="a3s-taskdocs__meta"><span class="a3s-taskdocs__state is-' + state.toLowerCase() + '">' + state + "</span></p></div>" +
			'<div class="a3s-taskdocs__actions">' +
			(d.file_url ? '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(d.file_url) + '" target="_blank" rel="noopener">Open</a>' : "") +
			(!d.file_url && s.can_mark ? '<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-act="upload">Upload</button>' : "") +
			"</div></li></ul>";
	}

	function money(n) {
		return "₹ " + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 });
	}

	/* The amount against what this phase asks now - its share plus anything unpaid before. */
	function verdict(s, amount) {
		var due = s.due;
		if (!due || !(Number(amount) > 0)) return "";
		var got = Number(amount);
		if (got + 0.5 >= due.collect) {
			return '<span class="a3s-taskdocs__state is-uploaded">Clears this phase' + (due.arrears ? " and the arrears" : "") + "</span>";
		}
		return '<span class="a3s-taskdocs__state is-missing">' + money(due.collect - got) + " still outstanding of " + esc(due.collect_text) + "</span>";
	}

	/* The job's payment schedule: every phase of the terms, this one marked, what each has had and
	   what is left, and - for a phase still open - what to collect now. */
	function dueLine(s) {
		var due = s.due;
		if (!due) return "";
		var rows = due.schedule.map(function (p) {
			var done = Number(p.remaining) < 0.5;
			return "<tr" + (p.current ? ' style="font-weight:700;background:var(--color-accent-soft)"' : "") + ">" +
				"<td>" + esc(p.task) + '<br><span class="a3s-field__hint">' + esc(p.name) + "</span></td>" +
				"<td>" + esc(p.when) + (p.when_status ? ' <span class="a3s-field__hint">· ' + esc(p.when_status) + "</span>" : "") + "</td>" +
				"<td>" + esc(p.percent) + "%</td><td>" + esc(p.amount_text) + "</td>" +
				"<td>" + esc(p.received_text || "-") + (p.assumed ? '<br><span class="a3s-field__hint">confirmed in full</span>' : "") + "</td>" +
				"<td>" + (done ? '<span class="a3s-taskdocs__state is-uploaded">Paid</span>' : esc(p.remaining_text)) + "</td></tr>";
		}).join("");
		var line = s.task.status === "Completed"
			? "Received for this phase <b>" + esc((s.payment && s.payment.amount_text) || current(due).received_text || due.amount_text) + "</b>"
			: "This phase <b>" + esc(due.amount_text) + "</b>" +
				(due.arrears ? ' + previous unpaid <b style="color:var(--color-accent-hover)">' + esc(due.arrears_text) + "</b>" : "") +
				(due.credit ? ' - paid ahead <b>' + esc(due.credit_text) + "</b>" : "") +
				" = collect <b>" + esc(due.collect_text) + "</b>";
		return '<div class="a3s-tablewrap"><table class="a3s-table"><thead><tr><th>Phase</th><th>When</th><th>%</th><th>Amount</th><th>Received</th><th>Remaining</th></tr></thead><tbody>' +
			rows + "</tbody></table></div>" +
			'<p style="margin:0.6rem 0 0">' + line + "</p>" +
			'<p class="a3s-field__hint" style="margin:0.25rem 0 0">Contract ' + esc(due.base_text) + " (" + esc(due.terms) + ") · received so far <b>" +
			esc(due.received_total_text) + "</b> · remaining <b>" + esc(due.remaining_total_text) + "</b></p>";
	}

	function current(due) {
		return due.schedule.filter(function (p) { return p.current; })[0] || {};
	}

	/* What was received, as tiles: amount, bank, received by. */
	function details(s) {
		var p = s.payment || {};
		if (!p.amount_text && !p.bank && !p.company) return "";
		var tile = function (label, value) { return value ? "<div><dt>" + label + "</dt><dd>" + esc(value) + "</dd></div>" : ""; };
		return '<dl class="a3s-paytask__summary">' + tile("Amount received", p.amount_text) + tile("Bank", p.bank) +
			tile("Received by", p.company) + tile("Account", p.account) +
			(s.due && s.task.status !== "Completed" ? tile("To collect" + (s.due.arrears ? " (incl. arrears)" : ""), s.due.collect_text) : "") + "</dl>" +
			(s.due && p.amount && s.task.status !== "Completed" ? '<p style="margin:0.6rem 0 0">' + verdict(s, p.amount) + "</p>" : "");
	}

	function form(s) {
		if (!draft) draft = { amount: s.payment.amount || "", bank: s.payment.bank || "", company: s.payment.company || "",
			payment_date: new Date().toISOString().slice(0, 10), mode: "Bank Transfer", reference: "" };
		return '<p class="a3s-paytask__label">Payment details</p><div class="a3s-paytask__fields">' +
			'<div class="a3s-field"><label for="a3s-pay-amount">Amount received (₹) <span class="a3s-req">*</span></label>' +
			'<input type="number" min="0" step="any" id="a3s-pay-amount" data-draft="amount" placeholder="0" value="' + esc(draft.amount) + '"></div>' +
			'<div class="a3s-field"><label for="a3s-pay-bank">Bank <span class="a3s-req">*</span></label>' +
			'<input type="text" id="a3s-pay-bank" data-draft="bank" placeholder="e.g. HDFC Aluva" value="' + esc(draft.bank) + '"></div>' +
			'<div class="a3s-field"><label for="a3s-pay-company">Received by <span class="a3s-req">*</span></label>' +
			'<select id="a3s-pay-company" data-draft="company"><option value="">Choose the company…</option>' +
			(s.company_options || []).map(function (c) {
				return '<option value="' + esc(c) + '"' + (c === draft.company ? " selected" : "") + ">" + esc(c) + "</option>";
			}).join("") + "</select></div>" +
			'<div class="a3s-field"><label for="a3s-pay-date">Payment date <span class="a3s-req">*</span></label>' +
			'<input type="date" id="a3s-pay-date" data-draft="payment_date" value="' + esc(draft.payment_date) + '"></div>' +
			'<div class="a3s-field"><label for="a3s-pay-mode">Mode</label><select id="a3s-pay-mode" data-draft="mode"><option value=""></option>' +
			(s.modes || []).map(function (m) {
				return '<option value="' + esc(m) + '"' + (m === draft.mode ? " selected" : "") + ">" + esc(m) + "</option>";
			}).join("") + "</select></div>" +
			'<div class="a3s-field"><label for="a3s-pay-ref">Reference (UTR / cheque no.)</label>' +
			'<input type="text" id="a3s-pay-ref" data-draft="reference" value="' + esc(draft.reference) + '"></div></div>' +
			'<p style="margin:0.6rem 0 0" data-verdict>' + verdict(s, draft.amount) + "</p>";
	}

	/* The phase's payments on the job's schedule - a phase can be paid in parts. */
	function payments(s) {
		if (!(s.payments || []).length) return "";
		var tone = { Confirmed: "uploaded", "Awaiting Confirmation": "pending-approval", "Sent Back": "rejected" };
		return '<p class="a3s-paytask__label">Payments' + (s.payment_status ? " &middot; " + esc(s.payment_status) +
			(s.payment_status !== "Paid" ? ", " + esc(s.pending_text) + " pending" : "") : "") + "</p>" +
			'<ul class="a3s-paysched__payments">' + s.payments.map(function (p) {
				return '<li class="a3s-paysched__payment"><div class="a3s-paysched__pay-main"><strong>' + esc(p.amount_text) + "</strong>" +
					'<span class="a3s-taskdocs__state is-' + (tone[p.status] || "missing") + '">' + esc(p.status) + "</span>" +
					'<p class="a3s-paysched__pay-meta">' + [p.date, p.mode, p.reference, p.bank, p.firm].filter(Boolean).map(esc).join(" &middot; ") + "</p>" +
					(p.status === "Sent Back" && p.remarks ? '<p class="a3s-paysched__pay-meta is-warn">' + esc(p.remarks) + "</p>" : "") + "</div>" +
					(p.receipt ? '<a class="a3s-icon-btn a3s-icon-btn--framed" href="' + esc(p.receipt) + '" target="_blank" rel="noopener" title="Open the receipt" aria-label="Open the receipt">' +
						'<svg class="a3s-ic" aria-hidden="true"><use href="#ic-eye"></use></svg></a>' : "") + "</li>";
			}).join("") + "</ul>";
	}

	function head(s) {
		var t = s.task, slug = t.status.toLowerCase().replace(/ /g, "-");
		var tone = { completed: "uploaded", "awaiting-accounts": "partly", pending: "missing", "in-progress": "partly" }[slug] || slug;
		return '<div class="a3s-paytask__head"><h3 class="a3s-edit__card-title">' + esc(t.name) + "</h3>" +
			'<span class="a3s-taskdocs__state is-' + esc(tone) + '">' + esc(t.status) + "</span></div>";
	}

	function paint(s) {
		var t = s.task, html = head(s);
		if (s.due) html += '<p class="a3s-paytask__label">Payment schedule</p>' + dueLine(s);
		html += payments(s);
		if (t.status === "Completed") {
			html += '<p class="a3s-field__hint">Payment confirmed by Accounts' + (s.confirmed_by ? " (" + esc(s.confirmed_by) + ")" : "") +
				(s.confirmed_on ? " on " + esc(s.confirmed_on) : "") + ".</p>" + details(s) +
				'<p class="a3s-paytask__label">Receipt or bank advice</p>' + receipt(s);
		} else if (t.status === "Awaiting Accounts") {
			html += '<p class="a3s-field__hint">Marked received by ' + esc(s.received_by) + " on " + esc(s.received_on) +
				". Waiting for Accounts to confirm the payment.</p>" + details(s) +
				'<p class="a3s-paytask__label">Receipt or bank advice</p>' + receipt(s);
			if (s.can_confirm) {
				html += '<div class="a3s-form__actions">' +
					'<button type="button" class="a3s-btn a3s-btn--primary" data-act="confirm">Confirm payment received</button>' +
					'<button type="button" class="a3s-btn a3s-btn--secondary" data-act="back">Not received &ndash; send back</button></div>' +
					'<div class="a3s-field" data-back hidden><label for="a3s-pay-reason">Why is it not confirmed? <span class="a3s-req">*</span></label>' +
					'<textarea id="a3s-pay-reason" rows="2"></textarea>' +
					'<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--primary" data-act="send-back">Send back</button></div></div>';
			}
		} else if (t.status === "Skipped") {
			html += '<p class="a3s-field__hint">This task is not needed on this job.</p>';
		} else {
			if (s.remarks) html += '<p class="a3s-field__hint">' + esc(s.remarks) + "</p>";
			if (s.can_mark) {
				html += '<p class="a3s-paytask__label">Has the payment been received? <span class="a3s-req">*</span></p>' +
					'<div class="a3s-paytask__choice" role="group" aria-label="Has the payment been received?">' +
					'<button type="button" class="a3s-btn a3s-btn--secondary" data-answer="yes" aria-pressed="' + (answer === "yes") + '">Yes, received</button>' +
					'<button type="button" class="a3s-btn a3s-btn--secondary" data-answer="no" aria-pressed="' + (answer === "no") + '">Not yet</button></div>';
				if (answer === "yes") {
					html += form(s) + '<p class="a3s-paytask__label">Receipt or bank advice</p>' + receipt(s) +
						'<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--primary" data-act="send"' +
						(s.document.file_url ? "" : " disabled") + ">Send to Accounts</button>" +
						(s.document.file_url ? "" : '<span class="a3s-field__hint">Upload the receipt or bank advice first.</span>') + "</div>";
				} else if (answer === "no") {
					html += '<p class="a3s-field__hint" style="margin-top:0.75rem">Nothing to do yet. Come back and choose <b>Yes, received</b> when the payment comes in.</p>';
				}
			} else {
				html += '<p class="a3s-field__hint">Waiting for the payment.</p>' + receipt(s);
			}
		}
		body.innerHTML = html;
	}

	var current = JSON.parse(card.querySelector("[data-paytask-data]").textContent);
	function redraw(s) { current = s; paint(s); }

	body.addEventListener("click", function (e) {
		var pick = e.target.closest("[data-answer]");
		if (pick) { answer = pick.dataset.answer; paint(current); }
	});
	body.addEventListener("input", function (e) {
		if (e.target.dataset && e.target.dataset.draft && draft) draft[e.target.dataset.draft] = e.target.value;
		var v = body.querySelector("[data-verdict]");
		if (v && e.target.dataset.draft === "amount") v.innerHTML = verdict(current, draft.amount);
	});
	body.addEventListener("click", function (e) {
		var act = e.target.closest("[data-act]");
		if (!act) return;
		var what = act.dataset.act;
		if (what === "upload") picker.click();
		if (what === "send") {
			if (!(Number(draft.amount) > 0) || !draft.bank.trim() || !draft.company) {
				setStatus("Enter the amount received, the bank and who received it.", "error");
				return;
			}
			setStatus("Sending to Accounts…");
			call("payment_tasks.mark_received", { installation: installation, task_code: task,
				amount: draft.amount, bank: draft.bank, company: draft.company, payment_date: draft.payment_date,
				mode: draft.mode, reference: draft.reference })
				.then(function (s) { answer = ""; draft = null; redraw(s); setStatus("Sent to Accounts to confirm.", "ok"); })
				.catch(function (err) { setStatus(err.message, "error"); });
		}
		if (what === "confirm") {
			setStatus("Confirming…");
			call("payment_tasks.confirm", { installation: installation, task_code: task })
				.then(function (s) {
					redraw(s);
					setStatus(s.task.status === "Completed" ? "Payment confirmed. The task is complete."
						: "Payment confirmed. " + (s.pending_text || "Some") + " is still pending on this phase.", "ok");
				})
				.catch(function (err) { setStatus(err.message, "error"); });
		}
		if (what === "back") body.querySelector("[data-back]").hidden = false;
		if (what === "send-back") {
			var reason = body.querySelector("#a3s-pay-reason").value.trim();
			if (!reason) { setStatus("Say why the payment is not confirmed.", "error"); return; }
			call("payment_tasks.send_back", { installation: installation, task_code: task, reason: reason })
				.then(function (s) { answer = ""; draft = null; redraw(s); setStatus("Sent back.", "ok"); })
				.catch(function (err) { setStatus(err.message, "error"); });
		}
	});

	picker.addEventListener("change", function () {
		if (!picker.files.length) return;
		var form = new FormData();
		form.append("file", picker.files[0]);
		var args = { installation: installation, task_code: task };
		if (current.document.row) args.row = current.document.row;
		else args.document_name = current.document.name;
		setStatus("Uploading…");
		call("portal_tasks.upload", args, form)
			.then(function () { return call("payment_tasks.state", { installation: installation, task_code: task }); })
			.then(function (s) { redraw(s); setStatus("Uploaded.", "ok"); })
			.catch(function (err) { setStatus(err.message, "error"); });
		picker.value = "";
	});

	paint(current);
})();
