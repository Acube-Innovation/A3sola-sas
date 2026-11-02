/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The Supplier Invoice page (www/a3solaportal/projects/task.html, api/supplier_bill): the
 * supplier's tax invoice uploaded and read - supplier, bill no. and date, its lines, taxes and
 * total - checked and corrected here, then entered as a submitted Purchase Invoice on the job.
 * The job's bills are listed; All supplier bills entered completes the task.
 */
(function () {
	"use strict";

	var root = document.querySelector("[data-supbill]");
	if (!root) return;
	var API = "/api/method/a3_sola.api.supplier_bill.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var installation = root.dataset.installation;
	var body = root.querySelector("[data-supbill-body]");
	var status = root.querySelector("[data-supbill-status]");
	var picker = root.querySelector("[data-supbill-file]");
	var state = JSON.parse(root.querySelector("[data-supbill-data]").textContent);
	/* The bill being checked: what `read` returned, as edited here, and its file. */
	var draft = null, file = null, busy = false;
	/* Several bills uploaded together: each read into its own entry, `current` the one open in
	   the check view. An entry keeps its own draft (edits, templates, payment) and calculation. */
	var queue = [], current = -1;
	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

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

	function num(v) { var n = parseFloat(String(v == null ? "" : v).replace(/,/g, "")); return isNaN(n) ? 0 : n; }
	function round2(n) { return Math.round(n * 100) / 100; }
	function label(text) { return '<p class="a3s-paytask__label">' + text + "</p>"; }

	/* ------------------------------------------------------------- the job's bills */

	function billRow(b) {
		var paid = b.docstatus === 1 && b.outstanding <= 0;
		var pays = (b.payments || []).map(function (p) {
			return '<a href="' + esc(p.url) + '">' + esc(p.name) + "</a> &middot; " + esc(p.mode_of_payment || "") +
				(p.paid_into ? " &rarr; " + esc(p.paid_into) : "") +
				(p.reference_no ? " &middot; " + esc(p.reference_no) : "") + (p.reference_date ? " &middot; " + esc(p.reference_date) : "") +
				(p.proof_url ? ' &middot; <a href="' + esc(p.proof_url) + '" target="_blank" rel="noopener">Proof</a>' : "") +
				(p.claim ? '<br><small>Reimbursement <a href="' + esc(p.claim.url) + '">' + esc(p.claim.name) + "</a> to " +
					esc(p.claim.who) + " &middot; " + esc(p.claim.status) + "</small>" : "");
		}).join("<br>");
		var action = b.docstatus === 1 && !paid && state.can_pay
			? '<button type="button" class="a3s-btn a3s-btn--ghost a3s-supbill__pay" data-mark-paid="' + esc(b.name) + '">Mark as paid</button>' : "";
		return "<tr><td>" + esc(b.bill_no || "") + "</td><td>" + esc(b.bill_date || "") + '</td><td class="num">' + money.format(b.total) +
			'</td><td><a href="' + esc(b.url) + '">' + esc(b.name) + "</a>" + (b.docstatus === 1 ? "" : " (draft)") + "</td>" +
			'<td><span class="a3s-supbill__pill ' + (paid ? "is-paid" : "is-unpaid") + '">' + esc(paid ? "Paid" : (b.status || "Unpaid")) + "</span>" +
			(!paid && b.outstanding ? '<small class="a3s-field__hint" style="display:block">Due ' + money.format(b.outstanding) + "</small>" : "") + "</td>" +
			"<td>" + ((pays && action ? pays + "<br>" + action : pays || action) || "&mdash;") + "</td></tr>";
	}

	/* A supplier's card once it has a bill on the project: invoices come in by the one upload. */
	function cards() {
		return (state.suppliers || []).filter(function (c) { return c.bills.length; });
	}

	var CARD_STATE = { none: "No invoice yet", unpaid: "Unpaid", part: "Part paid", paid: "Paid" };

	/* Each supplier on its own card: its bills, what it is owed, its own upload, its own payment. */
	function billsList() {
		var list = cards();
		var html = list.length ? "" : '<p class="a3s-field__hint">No supplier bill on this project yet. Upload the invoices below: a supplier not in ERPNext is created from its invoice.</p>';
		html += list.map(function (c, i) {
			var mine = state.bills.filter(function (b) { return c.bills.indexOf(b.name) !== -1; });
			return '<div class="a3s-supbill__card" data-card="' + i + '"><div class="a3s-supbill__cardhead"><div><b>' + esc(c.name) + "</b>" +
				(c.gstin ? ' <span class="a3s-field__hint">GSTIN ' + esc(c.gstin) + "</span>" : "") + "</div>" +
				'<span class="a3s-supbill__cardtools"><button type="button" class="a3s-textlink" data-edit-supplier="' + esc(c.supplier) + '">Edit details</button>' +
				'<span class="a3s-supbill__pill ' + (c.state === "paid" ? "is-paid" : c.state === "none" ? "is-none" : "is-unpaid") + '">' + CARD_STATE[c.state] + "</span></span></div>" +
				(mine.length ? '<div class="a3s-tablewrap"><table class="a3s-table"><thead><tr><th>Bill no.</th><th>Date</th><th class="num">Total</th>' +
					"<th>Purchase Invoice</th><th>Status</th><th>Payment</th></tr></thead><tbody>" + mine.map(billRow).join("") + "</tbody></table></div>" : "") +
				'<div class="a3s-supbill__cardfoot">' +
				(mine.length ? '<span class="a3s-field__hint">Billed ' + money.format(c.total) + " &middot; paid " + money.format(c.paid) +
					' &middot; <b class="' + (c.due > 0 ? "is-due" : "is-paidtext") + '">due ' + money.format(c.due) + "</b></span>" : "") +
				(state.can_pay && c.unpaid.length > 1 ? '<button type="button" class="a3s-btn a3s-btn--primary a3s-supbill__pay" data-pay-supplier="' + i + '">Pay ' +
					esc(c.name) + " " + money.format(c.due) + "</button>" : "") +

				"</div></div>";
		}).join("");
		return html;
	}

	/* ------------------------------------------------------------- paid or unpaid */
	function choices() { return state.payment_choices || { modes: [], accounts: [], default_mode: null }; }

	function accountOf(mode) {
		var m = choices().modes.filter(function (x) { return x.name === mode; })[0];
		return m ? m.account : null;
	}

	/* The payment's fields - on the bill being entered (`prefix` "pay") and in the Mark as paid pop-up. */
	function paymentFields(p, prefix) {
		var ch = choices();
		return '<div class="a3s-paytask__fields">' +
			'<div class="a3s-field"><label for="' + prefix + '-mode">Mode of payment</label><select id="' + prefix + '-mode" data-pay="mode">' +
			options(ch.modes.map(function (m) { return m.name; }), p.mode) + "</select></div>" +
			'<div class="a3s-field"><label for="' + prefix + '-account">Paid from</label><select id="' + prefix + '-account" data-pay="account">' +
			options(ch.accounts, p.account) +
			(ch.reimbursement ? '<option value="Reimbursement"' + (p.account === "Reimbursement" ? " selected" : "") +
				">Reimbursement (paid by an employee)</option>" : "") + "</select></div>" +
			/* Paid by an employee: who, and how much is claimed back - the bill's due amount unless less. */
			'<div class="a3s-field" data-reimb' + (p.account === "Reimbursement" ? "" : " hidden") + '><label for="' + prefix + '-claimant">Employee</label>' +
			'<select id="' + prefix + '-claimant" data-pay="claimant">' + (ch.claimants || []).map(function (c) {
				return '<option value="' + esc(c.user) + '"' + (c.user === (p.claimant || ch.me) ? " selected" : "") + ">" + esc(c.name) +
					(c.user === ch.me ? " (you)" : "") + "</option>";
			}).join("") + "</select></div>" +
			'<div class="a3s-field" data-reimb' + (p.account === "Reimbursement" ? "" : " hidden") + '><label for="' + prefix + '-amount">Reimbursement amount</label>' +
			'<input id="' + prefix + '-amount" data-pay="amount" inputmode="decimal" value="' + esc(p.amount || "") + '"></div>' +
			'<div class="a3s-field"><label for="' + prefix + '-on">Paid on</label><input type="date" id="' + prefix + '-on" data-pay="paid_on" value="' + esc(p.paid_on) + '"></div>' +
			'<div class="a3s-field"><label for="' + prefix + '-ref">Transaction / UTR no.</label><input id="' + prefix + '-ref" data-pay="reference_no" value="' + esc(p.reference_no || "") + '" placeholder="UTR, cheque or transaction no."></div>' +
			'<div class="a3s-field"><label for="' + prefix + '-proof">Payment proof</label><input type="file" id="' + prefix + '-proof" data-pay-proof accept="application/pdf,image/*"></div>' +
			'</div><p class="a3s-field__hint">Enter the transaction number or attach the proof &mdash; one of them is needed to mark it paid.</p>';
	}

	/* "Paid from" a reimbursement shows who paid it and how much is claimed back. */
	function toggleReimb(scope, due) {
		var acc = scope.querySelector('[data-pay="account"]');
		var on = acc && acc.value === "Reimbursement";
		Array.prototype.forEach.call(scope.querySelectorAll("[data-reimb]"), function (n) { n.hidden = !on; });
		var amt = scope.querySelector('[data-pay="amount"]');
		if (on && amt && !amt.value && due) amt.value = due;
	}

	function newPayment() {
		var mode = choices().default_mode;
		return { status: "Unpaid", mode: mode, account: accountOf(mode), paid_on: new Date().toISOString().slice(0, 10), reference_no: "" };
	}

	/* Read a payment's fields back from where they are drawn. */
	function readPayment(scope, p) {
		Array.prototype.forEach.call(scope.querySelectorAll("[data-pay]"), function (el) { p[el.dataset.pay] = el.value; });
		var f = scope.querySelector("[data-pay-proof]");
		return { payment: p, proof: f && f.files[0] ? f.files[0] : null };
	}

	function payMissing(p, proof) { return p.status === "Paid" && !(p.reference_no || "").trim() && !proof; }

	/* Which of the supplier's accounts the payment goes into: a choice when it has several. */
	function payToField(supplier) {
		var c = (state.suppliers || []).filter(function (x) { return x.supplier === supplier; })[0];
		var accts = (c && c.bank_accounts) || [];
		if (!accts.length) return "";
		function text(a) { return a.bank_name + " \u00b7 A/c " + a.account_no + (a.ifsc ? " \u00b7 " + a.ifsc : "") + (a.is_default ? " (default)" : ""); }
		if (accts.length === 1) return '<p class="a3s-field__hint">Pay to: <b>' + esc(text(accts[0])) + '</b><input type="hidden" data-pay-to value="' + esc(accts[0].name) + '"></p>';
		return '<div class="a3s-field"><label>Pay to (the supplier\u2019s account)</label><select data-pay-to>' + accts.map(function (a) {
			return '<option value="' + esc(a.name) + '"' + (a.is_default ? " selected" : "") + ">" + esc(text(a)) + "</option>";
		}).join("") + "</select></div>";
	}

	/* Pay one bill (`invoice`), or every unpaid bill of one supplier (`card`) in one payment. */
	function markPaid(invoice, card) {
		var bill = card ? { bill_no: card.unpaid.length + " bills", supplier_name: card.name, outstanding: card.due }
			: state.bills.filter(function (b) { return b.name === invoice; })[0];
		var p = newPayment(); p.status = "Paid";
		var modal = document.createElement("div");
		modal.className = "a3s-modal";
		modal.setAttribute("role", "dialog");
		modal.setAttribute("aria-modal", "true");
		modal.innerHTML = '<div class="a3s-modal__panel a3s-supbill__paypanel"><p class="a3s-modal__title">Mark as paid</p>' +
			"<p><b>" + esc(bill.bill_no || bill.name) + "</b> from " + esc(bill.supplier_name || bill.supplier) + " &middot; " +
			money.format(bill.outstanding || bill.total) + " due</p>" + payToField(card ? card.supplier : (bill.supplier || "")) + paymentFields(p, "mp") +
			'<p class="a3s-attach__status" data-mp-status hidden></p>' +
			'<div class="a3s-form__actions" style="margin-top:0.75rem"><button type="button" class="a3s-btn a3s-btn--primary" data-mp-save>Save payment</button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-mp-cancel>Cancel</button></div></div>';
		document.body.appendChild(modal);
		if (card) {  /* a reimbursement is entered bill by bill */
			var r = modal.querySelector('[data-pay="account"] option[value="Reimbursement"]'); if (r) r.remove();
		}
		var note = modal.querySelector("[data-mp-status]");
		function close() { modal.remove(); }
		modal.querySelector("[data-mp-cancel]").addEventListener("click", close);
		modal.addEventListener("click", function (e) { if (e.target === modal) close(); });
		var due = bill.outstanding || bill.total;
		modal.querySelector('[data-pay="mode"]').addEventListener("change", function (e) {
			var sel = modal.querySelector('[data-pay="account"]'), acc = accountOf(e.target.value);
			if (acc && sel.value !== "Reimbursement") sel.value = acc;
		});
		modal.querySelector('[data-pay="account"]').addEventListener("change", function () { toggleReimb(modal, due); });
		modal.querySelector("[data-mp-save]").addEventListener("click", function () {
			var got = readPayment(modal, p);
			var to = modal.querySelector("[data-pay-to]");
			if (to) got.payment.party_bank_account = to.value;
			if (payMissing(got.payment, got.proof)) {
				note.hidden = false; note.dataset.tone = "error";
				note.textContent = "Enter the transaction number or attach the payment proof to mark it paid.";
				return;
			}
			var form = new FormData();
			if (got.proof) form.append("proof", got.proof, got.proof.name);
			note.hidden = false; note.dataset.tone = ""; note.textContent = "Saving the payment\u2026";
			(card ? call("pay_supplier", { installation: installation, supplier: card.supplier, payment: JSON.stringify(got.payment) }, form)
				: call("mark_paid", { installation: installation, invoice: invoice, payment: JSON.stringify(got.payment) }, form)).then(function (s) {
				close(); state = s; paint();
				if (card) { setStatus(card.name + "'s " + card.unpaid.length + " bills are paid in one Payment Entry.", "ok"); return; }
				var now = state.bills.filter(function (b) { return b.name === invoice; })[0] || {};
				setStatus(invoice + (now.outstanding > 0 ? " is part paid, " + money.format(now.outstanding) + " still due" : " is paid") +
					": its Payment Entry is made in ERPNext" + (got.payment.account === "Reimbursement" ? ", and the reimbursement claim raised." : "."), "ok");
			}).catch(function (e) { note.dataset.tone = "error"; note.textContent = e.message; });
		});
	}

	/* ------------------------------------------------------------- the bill being checked */
	function rows() { return draft.bill.lines.concat(draft.bill.charges); }

	/* ERPNext's calculation of the bill as it stands here (supplier_bill.preview): each line's
	   taxes at its item tax template's rates, the invoice's taxes, totals and rounding. */
	var calc = null, previewing = null, previewTimer = null;

	function payload() {
		var b = draft.bill;
		return {
			supplier: draft.supplier.new ? null : draft.supplier.name,
			supplier_name: draft.supplier.supplier_name, supplier_gstin: draft.supplier.gstin,
			bill_no: b.bill_no, bill_date: b.bill_date, tax_template: draft.tax_template, lines: rows(),
			consignee: b.consignee || "", name_confirmed: draft.name_confirmed ? 1 : 0,
			payment: draft.payment || { status: "Unpaid" },
			bill: { cgst: num(b.cgst), sgst: num(b.sgst), igst: num(b.igst), round_off: num(b.round_off), total: num(b.total) }
		};
	}

	function recalc() {
		clearTimeout(previewTimer);
		previewTimer = setTimeout(function () {
			var ask = previewing = call("preview", { installation: installation, data: JSON.stringify(payload()) });
			ask.then(function (c) {
				if (ask !== previewing || !draft) return;  /* a later change asked again */
				calc = c; paintCalc();
			}).catch(function (e) { setStatus(e.message, "error"); });
		}, 300);
	}

	function taxText(t) { return esc(t.label) + " " + t.rate + "% " + money.format(t.amount); }

	/* Each line's working, under it: taxable, its taxes, its total. */
	function lineCalc(i) {
		var l = calc && calc.lines[i];
		if (!l) return "";
		return "Taxable " + money.format(l.net_amount) + (l.taxes.length ? " &middot; " + l.taxes.map(taxText).join(" &middot; ") : "") +
			" &middot; <b>Line total " + money.format(l.total) + "</b>";
	}

	function calcHtml() {
		if (!calc) return '<p class="a3s-field__hint">Working it out&hellip;</p>';
		var bill = calc.bill || {};
		var billTax = { CGST: bill.cgst, SGST: bill.sgst, IGST: bill.igst };
		function row(text, ours, theirs, strong) {
			var off = theirs != null && Math.abs(ours - theirs) > 0.009;
			return "<tr" + (strong ? ' class="is-total"' : "") + "><th>" + text + '</th><td class="num">' + money.format(ours) +
				'</td><td class="num' + (off ? " is-off" : "") + '">' + (theirs != null ? money.format(theirs) : "&mdash;") + "</td></tr>";
		}
		return '<div class="a3s-tablewrap"><table class="a3s-table a3s-supbill__calc"><thead><tr><th>ERPNext calculation</th>' +
			'<th class="num">Invoice</th><th class="num">Bill says</th></tr></thead><tbody>' +
			row("Net total", calc.net_total, null) +
			calc.taxes.map(function (t) {
				var key = (t.label || "").toUpperCase().replace(/[^A-Z]/g, "");
				return row(esc(t.account) + " (" + t.rate + "% on net; each line at its own rate)", t.amount,
					billTax[key] != null ? billTax[key] : null);
			}).join("") +
			row("Total taxes", calc.total_taxes, null) +
			row("Grand total", calc.grand_total, null) +
			row("Rounding adjustment", calc.rounding_adjustment, bill.round_off != null ? bill.round_off : null) +
			row("Rounded total", calc.rounded_total, bill.total || null, true) +
			"</tbody></table></div>" +
			(calc.warnings.length ? '<p class="a3s-attach__status" data-tone="warn">' + esc(calc.warnings.join(" ")) + "</p>" : "");
	}

	function paintCalc() {
		var box = body.querySelector("[data-calc]");
		if (box) box.innerHTML = calcHtml();
		Array.prototype.forEach.call(body.querySelectorAll("[data-linecalc]"), function (n) {
			n.innerHTML = lineCalc(+n.dataset.linecalc);
		});
	}

	function options(list, value, blank) {
		return (blank ? '<option value="">' + blank + "</option>" : "") + list.map(function (n) {
			return '<option value="' + esc(n) + '"' + (n === value ? " selected" : "") + ">" + esc(n) + "</option>";
		}).join("");
	}

	function field(name, text, value, type) {
		return '<div class="a3s-field"><label for="sb-' + name + '">' + text + "</label>" +
			'<input type="' + (type || "text") + '" id="sb-' + name + '" data-head="' + name + '" value="' + esc(value) + '"></div>';
	}

	function checkView() {
		var b = draft.bill, s = draft.supplier, ch = draft.choices || { templates: [], item_templates: [] };
		var html = label("The bill") + '<div class="a3s-paytask__fields">' +
			field("supplier_name", "Supplier", s.supplier_name || "") +
			field("supplier_gstin", "Supplier GSTIN", s.gstin || "") +
			field("bill_no", "Bill no.", b.bill_no || "") +
			field("bill_date", "Bill date", b.bill_date || "", "date") + "</div>" +
			'<p class="a3s-field__hint">' + (s.new
				? "Not a supplier yet: <b>" + esc(s.supplier_name || "the supplier") + "</b> is added as one, with this GSTIN, when the bill is entered."
				: "Supplier on file: <b>" + esc(s.name) + "</b>" + (s.gstin_on_file ? " (GSTIN " + esc(s.gstin_on_file) + ")" : "") + ". " +
					'<button type="button" class="a3s-textlink" data-edit-supplier="' + esc(s.name) + '">Edit supplier details</button>') + "</p>";
		/* A supplier not in ERPNext: created from its invoice, as read, before the bill is entered. */
		if (s.new) html += newSupplierCard(draft);
		/* A supplier on file, an account on the invoice it does not hold: offered, never in the way. */
		var nb = draft.new_bank_account;
		if (nb && !draft.new_bank_dismissed && !s.new) {
			html += '<div class="a3s-attach__status a3s-supbill__newbank" data-tone="warn">This invoice gives a bank account <b>' + esc(s.supplier_name || s.name) +
				"</b> doesn't have on file: <b>" + esc(nb.bank_name) + "</b> &middot; A/c " + esc(nb.account_no) + (nb.ifsc ? " &middot; IFSC " + esc(nb.ifsc) : "") + "." +
				'<div class="a3s-form__actions" style="margin-top:0.5rem"><button type="button" class="a3s-btn a3s-btn--ghost" data-add-bank>Add to ' + esc(s.supplier_name || s.name) + "</button>" +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-skip-bank>Not now</button></div></div>';
		}
		/* Uploaded on another supplier's card: never entered under the wrong supplier. */
		var wrong = entry() && entry().wrongCard;
		if (wrong) {
			html += '<div class="a3s-attach__status a3s-supbill__mismatch" data-tone="error"><b>Wrong supplier:</b> this invoice is from <b>' + esc(wrong.actual) +
				"</b>, not <b>" + esc(wrong.card) + "</b>." +
				'<div class="a3s-form__actions" style="margin-top:0.5rem"><button type="button" class="a3s-btn a3s-btn--ghost" data-wrong-keep>Enter under ' + esc(wrong.actual) + "</button>" +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-discard>Discard</button></div></div>';
		}
		/* Entered already: said first, and nothing to create. */
		var dup = draft.already_entered;
		if (dup) {
			html += '<p class="a3s-attach__status a3s-supbill__mismatch" data-tone="error"><b>Already entered:</b> bill ' + esc(b.bill_no) +
				" is " + '<a href="' + esc(dup.url) + '">' + esc(dup.invoice) + "</a> (" + esc(dup.status) + ")" +
				(dup.project ? ' on project <a href="' + esc(dup.project_url) + '">' + esc(dup.project) + "</a>" + (dup.customer ? " (" + esc(dup.customer) + ")" : "") : "") +
				". One bill is entered once &mdash; to enter it again, cancel " + esc(dup.invoice) + " first.</p>";
		}
		var nc = draft.name_check;
		if (nc && !nc.matches) {
			html += '<p class="a3s-attach__status a3s-supbill__mismatch" data-tone="error"><b>Name mismatch:</b> the bill is for <b>' + esc(nc.bill_name) +
				"</b>, but this project is <b>" + esc(nc.customer) + "</b>&rsquo;s. You will be asked to confirm before it is entered.</p>";
		} else if (nc && nc.bill_name) {
			html += '<p class="a3s-field__hint">Bill made out for <b>' + esc(nc.bill_name) + "</b> &mdash; this project&rsquo;s customer.</p>";
		}
		html += label("Taxes") + '<div class="a3s-paytask__fields"><div class="a3s-field"><label for="sb-tax-template">Purchase Taxes and Charges Template</label>' +
			'<select id="sb-tax-template" data-tax-template>' + options(ch.templates, draft.tax_template, "No tax") + "</select></div></div>" +
			'<p class="a3s-field__hint">In-state: CGST + SGST; out-state: IGST. Each line pays at its own Item Tax Template&rsquo;s rate (GST 5% is 2.5% + 2.5%).</p>';
		html += label("Lines (" + rows().length + ")") + '<div class="a3s-tablewrap"><table class="a3s-table a3s-supbill__lines"><thead><tr>' +
			'<th>#</th><th>Description</th><th>HSN</th><th>Item Tax Template</th><th class="num">Qty</th><th>Unit</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead><tbody>' +
			(rows().length ? "" : '<tr><td colspan="8" class="a3s-field__hint">No lines were read from this bill. Add them below.</td></tr>') +
			rows().map(function (r, i) {
				return '<tr data-row="' + i + '"><td class="a3s-supbill__no">' + (i + 1) +
					'<button type="button" class="a3s-supbill__rowx" data-remove-row title="Remove this line" aria-label="Remove line ' + (i + 1) + '">&times;</button></td><td><input data-f="description" value="' + esc(r.description) + '">' +
					(r.serials && r.serials.length ? "<small>Serials: " + esc(r.serials.join(", ")) + "</small>" : "") +
					(r.item_code ? "<small>Item: " + esc(r.item_code) + "</small>" : "") + "</td>" +
					'<td><input data-f="hsn" value="' + esc(r.hsn || "") + '"></td>' +
					'<td><select data-f="item_tax_template">' + options(ch.item_templates, r.item_tax_template, "No tax") + "</select>" +
					(r.gst_rate !== "" && r.gst_rate != null ? "<small>Bill: " + esc(r.gst_rate) + "%</small>" : "") + "</td>" +
					'<td class="num"><input data-f="qty" value="' + esc(r.qty) + '" inputmode="decimal"></td>' +
					'<td><input data-f="uom" value="' + esc(r.uom || "") + '"></td>' +
					'<td class="num"><input data-f="rate" value="' + esc(r.rate) + '" inputmode="decimal"></td>' +
					'<td class="num" data-amount>' + money.format(num(r.amount)) + "</td></tr>" +
					/* The line's working, the width of the table under it. */
					'<tr class="a3s-supbill__calcrow"><td></td><td colspan="7" data-linecalc="' + i + '">' + lineCalc(i) + "</td></tr>";
			}).join("") + "</tbody></table></div>" +
			'<div class="a3s-supbill__more"><button type="button" class="a3s-supbill__textbtn" data-add-line>+ Add line</button></div>';
		html += label("Calculation") + '<div data-calc>' + calcHtml() + "</div>";
		var pay = draft.payment = draft.payment || newPayment();
		html += label("Payment") + '<div class="a3s-supbill__paychoice" role="group" aria-label="Payment">' +
			["Unpaid", "Paid"].map(function (st) {
				return '<button type="button" class="a3s-btn ' + (pay.status === st ? "a3s-btn--primary" : "a3s-btn--ghost") +
					'" data-pay-status="' + st + '" aria-pressed="' + (pay.status === st) + '">' + st + "</button>";
			}).join("") + "</div>" +
			(pay.status === "Paid" ? '<div data-paybox style="margin-top:0.75rem">' + paymentFields(pay, "pay") + "</div>"
				: '<p class="a3s-field__hint">Entered unpaid: mark it paid from the bills list once it is paid.</p>');
		html += '<div class="a3s-form__actions" style="margin-top:1rem">' +
			'<button type="button" class="a3s-btn a3s-btn--primary" data-create' + (draft.already_entered || (entry() && entry().wrongCard) || draft.supplier.new ? " disabled" : "") + ">Create Purchase Invoice</button>" +
			(draft.supplier.new ? '<span class="a3s-field__hint">Create the supplier first.</span>' : "") +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-discard>Discard</button></div>';
		return html;
	}

	function paint() {
		var html = '<div class="a3s-paytask__head"><h3 class="a3s-edit__card-title">' + esc(state.task.name) + "</h3>" +
			'<span class="a3s-status-pill">' + esc(state.status || "") + "</span></div>" +
			'<p class="a3s-field__hint">' + esc(state.consumer_name || state.installation) + " &middot; the supplier's tax invoice for the project's material, entered as a Purchase Invoice.</p>";
		html += label("Suppliers and their bills") + billsList() + statementCard();
		if (state.can_edit) {
			/* Another supplier's invoice can be added at any time, while a bill is being checked too. */
			if (draft) html += '<div class="a3s-supbill__more"><button type="button" class="a3s-btn a3s-btn--secondary" data-pick><svg class="a3s-ic" aria-hidden="true"><use href="#ic-upload"></use></svg><span>Upload Invoice</span></button></div>';
			if (queue.length) html += queueStrip();
			if (draft) html += checkView();
			else html += label("Add a bill") + '<div class="a3s-supbill__drop" data-drop><span><b>Upload the supplier\'s invoices</b><br>' +
				'<span class="a3s-field__hint">A PDF as the supplier sent it, or a clear photo - one bill or several, from different suppliers. Each is read for you to check.</span></span>' +
				'<button type="button" class="a3s-btn a3s-btn--primary" data-pick>Choose the invoices</button></div>';
			if (!draft && state.bills.some(function (b) { return b.docstatus === 1; })) {
				html += '<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--primary" data-done>All supplier bills entered</button>' +
					'<span class="a3s-field__hint">Completes the task. A project billed by two suppliers has a bill from each.</span></div>';
			}
		}
		body.innerHTML = html;
	}

	/* ------------------------------------------------------------- several bills */
	function entry() { return queue[current]; }

	/* What an entry needs: entered, ready to enter as it is, or a look first. */
	function entryState(q) {
		if (q.error) return { key: "error", text: "Couldn't read" };
		if (!q.data) return { key: "reading", text: "Reading\u2026" };
		if (q.entered) return { key: "entered", text: "Entered as " + q.entered };
		if (q.data.already_entered) return { key: "dup", text: "Already entered" };
		if (q.wrongCard) return { key: "wrong", text: "Not " + q.wrongCard.card + "'s" };
		if (q.data.supplier && q.data.supplier["new"]) return { key: "new", text: "New supplier" };
		var c = q.calc || q.data.calculation || {};
		if ((q.data.warnings || []).length || (c.warnings || []).length || (q.data.name_check && !q.data.name_check.matches)) return { key: "check", text: "Check" };
		return { key: "ready", text: "Ready" };
	}

	function queueStrip() {
		var ready = queue.filter(function (q) { return entryState(q).key === "ready"; }).length;
		return label("Invoices uploaded (" + queue.length + ") \u2014 click one to check it") + '<div class="a3s-supbill__queue">' + queue.map(function (q, i) {
			var st = entryState(q), b = q.data && q.data.bill || {};
			var total = q.calc ? q.calc.rounded_total : (q.data && q.data.calculation ? q.data.calculation.rounded_total : null);
			return '<button type="button" class="a3s-supbill__chip is-' + st.key + (i === current ? " is-open" : "") + '" data-open-bill="' + i + '">' +
				"<b>" + esc((q.data && q.data.supplier && (q.data.supplier.supplier_name || q.data.supplier.name)) || q.file.name) + "</b>" +
				"<span>" + esc(b.bill_no || q.file.name) + (total ? " &middot; " + money.format(total) : "") + "</span>" +
				'<span class="a3s-supbill__chipstate">' + esc(st.text) + "</span></button>";
		}).join("") + "</div>" +
			(ready > 1 ? '<div class="a3s-form__actions" style="margin-top:0.5rem"><button type="button" class="a3s-btn a3s-btn--ghost" data-create-all>' +
				"Create all " + ready + " ready bills (unpaid)</button>" +
				'<span class="a3s-field__hint">Bills marked Check open one by one.</span></div>' : "");
	}

	/* Keep the open bill's edits on its entry, then open another. */
	function openEntry(i) {
		var q = entry();
		if (q && draft) {
			if (draft.payment && draft.payment.status === "Paid" && body.querySelector("[data-paybox]")) readPayment(body.querySelector("[data-paybox]"), draft.payment);
			q.data = draft; q.calc = calc;
		}
		current = i;
		q = entry();
		draft = q && q.data && !q.entered ? q.data : null;
		file = q ? q.file : null;
		calc = q ? (q.calc || (q.data && q.data.calculation) || null) : null;
		paint();
		if (q && q.data) sayRead(q);
	}

	function sayRead(q) {
		var data = q.data, n = data.bill.lines.length + data.bill.charges.length;
		if (data.supplier && data.supplier["new"]) setStatus("Read " + n + " lines. " + (data.supplier.supplier_name || "The supplier") +
			" is not in ERPNext yet: check its details and create the supplier first.", "warn");
		else if (data.already_entered) setStatus("This bill is already entered as " + data.already_entered.invoice + ": nothing to create.", "error");
		else if (data.warnings && data.warnings.length) setStatus("Read " + n + " lines. " + data.warnings.join(" "), "warn");
		else setStatus("Read " + n + " lines; the lines and taxes add up to the bill's total. Check them, then create the Purchase Invoice.", "ok");
	}

	function summary() {
		var counts = {};
		queue.forEach(function (q) { var k = entryState(q).key; counts[k] = (counts[k] || 0) + 1; });
		var parts = [];
		if (counts.ready) parts.push(counts.ready + " ready");
		if (counts.check) parts.push(counts.check + " to check");
		if (counts["new"]) parts.push(counts["new"] + " from a new supplier");
		if (counts.wrong) parts.push(counts.wrong + " on the wrong supplier");
		if (counts.dup) parts.push(counts.dup + " already entered");
		if (counts.error) parts.push(counts.error + " could not be read");
		if (counts.entered) parts.push(counts.entered + " entered");
		return queue.length + " bill" + (queue.length === 1 ? "" : "s") + " read: " + parts.join(", ") + ".";
	}

	/* Each file read in turn; the first that is not entered yet opens. */
	function readBills(files, card) {
		files = Array.prototype.slice.call(files || []);
		if (!files.length || busy) return;
		busy = true;
		var start = queue.length;
		files.forEach(function (f) { queue.push({ file: f, data: null }); });
		paint();
		files.reduce(function (chain, f, k) {
			return chain.then(function () {
				var q = queue[start + k];
				setStatus("Reading " + f.name + " (" + (k + 1) + " of " + files.length + ")\u2026");
				var form = new FormData();
				form.append("file", f, f.name);
				return call("read", { installation: installation }, form).then(function (data) {
					q.data = data; q.calc = data.calculation || null;
					/* Uploaded on a supplier's card: the bill must be that supplier's, by GSTIN. */
					if (card) {
						var sup = data.supplier || {}, gst = (sup.gstin || "").toUpperCase();
						var same = sup.name ? sup.name === card.supplier : (gst && card.gstin && gst === card.gstin.toUpperCase());
						if (!same) q.wrongCard = { card: card.name, actual: sup.supplier_name || sup.name || "another supplier" };
						else if (!sup.name) { sup.name = card.supplier; sup["new"] = false; }
					}
				}).catch(function (e) { q.error = e.message; });
			});
		}, Promise.resolve()).then(function () {
			busy = false; picker.value = "";
			/* A bill already open stays open: the new ones wait in the row above it. */
			if (draft && current >= 0 && current < start) { paint(); setStatus(summary() + " Click a bill above to check it.", "ok"); return; }
			var open = queue.findIndex(function (q, i) { return i >= start && q.data && !q.entered; });
			if (open === -1) open = start;
			if (queue.length === 1 && queue[0].data) { openEntry(0); return; }
			openEntry(open);
			setStatus(summary(), "ok");
		});
	}

	/* ------------------------------------------------------------- the material statement */
	function statementCard() {
		var st = state.statement;
		if (!st || !st.bills) return "";
		var url = "/api/method/a3_sola.api.supplier_bill.statement_pdf?installation=" + encodeURIComponent(installation);
		return label("Project material statement") + '<dl class="a3s-supbill__stmt">' +
			"<div><dt>Bills</dt><dd>" + st.bills + " from " + st.suppliers + " supplier" + (st.suppliers === 1 ? "" : "s") + "</dd></div>" +
			"<div><dt>Taxable</dt><dd>" + money.format(st.taxable) + "</dd></div>" +
			"<div><dt>GST</dt><dd>" + money.format(st.tax) + "</dd></div>" +
			"<div><dt>Total</dt><dd>" + money.format(st.total) + "</dd></div>" +
			'<div><dt>Paid</dt><dd class="is-paid">' + money.format(st.paid) + "</dd></div>" +
			'<div><dt>Due</dt><dd class="is-due">' + money.format(st.due) + "</dd></div></dl>" +
			'<div class="a3s-form__actions" style="margin-top:0.5rem"><a class="a3s-btn a3s-btn--ghost" href="' + url + '" target="_blank" rel="noopener">View statement</a>' +
			'<a class="a3s-btn a3s-btn--ghost" href="' + url + '&download=1">Download</a>' +
			'<span class="a3s-field__hint">Every supplier bill on this project in one PDF: their lines, GST by rate, the total, paid and due.</span></div>';
	}

	/* The pop-up a bill for another customer needs: entered on this job only once confirmed. */
	function confirmMismatch(nc) {
		return new Promise(function (resolve) {
			var modal = document.createElement("div");
			modal.className = "a3s-modal";
			modal.setAttribute("role", "dialog");
			modal.setAttribute("aria-modal", "true");
			modal.innerHTML = '<div class="a3s-modal__panel a3s-supbill__mismatchpanel"><p class="a3s-modal__title">&#9888; Name mismatch</p>' +
				"<p>The supplier&rsquo;s bill is made out for <b>" + esc(nc.bill_name) + "</b>, but this project is <b>" + esc(nc.customer) + "</b>&rsquo;s.</p>" +
				'<p class="a3s-field__hint">Enter it on this project only if the material really is for ' + esc(nc.customer) +
				" &mdash; the bill shipped to another name, say. The invoice records that you confirmed it.</p>" +
				'<label class="a3s-check" style="margin:0.75rem 0"><input type="checkbox" data-mm-ok> <span>I confirm this bill is for ' + esc(nc.customer) + "&rsquo;s project</span></label>" +
				'<div class="a3s-form__actions" style="margin-top:0.75rem"><button type="button" class="a3s-btn a3s-btn--primary" data-mm-go disabled>Enter on this project</button>' +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-mm-cancel>Cancel</button></div></div>';
			document.body.appendChild(modal);
			var ok = modal.querySelector("[data-mm-ok]"), go = modal.querySelector("[data-mm-go]");
			function close(answer) { modal.remove(); document.removeEventListener("keydown", onKey); resolve(answer); }
			function onKey(e) { if (e.key === "Escape") close(false); }
			ok.addEventListener("change", function () { go.disabled = !ok.checked; });
			go.addEventListener("click", function () { close(true); });
			modal.querySelector("[data-mm-cancel]").addEventListener("click", function () { close(false); });
			modal.addEventListener("click", function (e) { if (e.target === modal) close(false); });
			document.addEventListener("keydown", onKey);
			ok.focus();
		});
	}

	/* A line typed in, for one the bill's reading missed: taxed as the line before it. */
	function addLine() {
		var all = rows(), last = all[all.length - 1], ch = draft.choices || { item_templates: [] };
		draft.bill.lines.push({ description: "", hsn: "", qty: 1, uom: "Nos", rate: 0, discount: 0, amount: 0, gst_rate: "",
			serials: [], item_tax_template: last ? last.item_tax_template : (ch.item_templates[0] || "") });
		paint(); recalc();
		var input = body.querySelector('[data-row="' + (draft.bill.lines.length - 1) + '"] [data-f="description"]');
		if (input) input.focus();
	}

	function removeLine(i) {
		var lines = draft.bill.lines;
		if (i < lines.length) lines.splice(i, 1); else draft.bill.charges.splice(i - lines.length, 1);
		paint(); recalc();
	}

	function create() {
		if (busy) return;
		if (!rows().some(function (r) { return num(r.qty) && (r.description || "").trim(); })) {
			setStatus("Add at least one line, with its description and quantity.", "error");
			return;
		}
		var nc = draft.name_check;
		if (nc && !nc.matches && !draft.name_confirmed) {
			confirmMismatch(nc).then(function (yes) {
				if (!yes) { setStatus("Not entered: the bill's name does not match this project's customer.", "error"); return; }
				draft.name_confirmed = true;
				create();
			});
			return;
		}
		var proof = null;
		if (draft.payment && draft.payment.status === "Paid") {
			var got = readPayment(body.querySelector("[data-paybox]"), draft.payment);
			proof = got.proof;
			if (payMissing(draft.payment, proof)) {
				setStatus("Enter the transaction number or attach the payment proof to enter it as paid.", "error");
				return;
			}
		}
		var b = draft.bill;
		if (calc && b.total && Math.abs(calc.rounded_total - num(b.total)) > 1 && !window.confirm("ERPNext works it out to " +
			money.format(calc.rounded_total) + ", not the bill's " + money.format(num(b.total)) + ". Enter it anyway?")) return;
		busy = true;
		setStatus("Entering the bill\u2026");
		var form = new FormData();
		if (file) form.append("file", file, file.name);
		if (proof) form.append("proof", proof, proof.name);
		call("create", { installation: installation, data: JSON.stringify(payload()) }, form).then(function (res) {
			state = res.state;
			if (entry()) { entry().entered = res.name; entry().data = draft; }
			draft = null; file = null; calc = null;
			var next = queue.findIndex(function (q) { return q.data && !q.entered && !q.data.already_entered && !q.error; });
			if (next !== -1) { current = -1; openEntry(next); } else paint();
			setStatus("Entered as Purchase Invoice " + res.name + " for " + money.format(res.rounded_total || res.grand_total) + ", submitted, with the bill attached" +
				(res.payment_entry ? ", and paid (" + res.payment_entry + ")." : "; unpaid."), "ok");
		}).catch(function (e) { setStatus(e.message, "error"); })
		  .then(function () { busy = false; });
	}

	var SUPPLIER_FIELDS = [
		["supplier_name", "Supplier name"], ["gstin", "GSTIN"], ["pan", "PAN"], ["gst_category", "GST category"],
		["supplier_group", "Supplier group"], ["address_line1", "Address line 1"], ["address_line2", "Address line 2"],
		["city", "City / town"], ["state", "State"], ["pincode", "PIN code"], ["phone", "Phone"], ["email", "E-mail"]
	];
	var BANK_FIELDS = [["account_holder", "Account holder"], ["bank_name", "Bank name"], ["account_no", "Account no."],
		["branch", "Branch"], ["ifsc", "IFSC"], ["swift", "SWIFT code"]];

	function newSupplierCard(d) {
		var det = d.supplier.details = d.supplier.details || {};
		/* What the invoice gave, marked so - before the page's own defaults fill the rest. */
		var read = d._read = d._read || Object.keys(det).filter(function (k) { return det[k]; });
		if (!det.supplier_group) det.supplier_group = d.default_supplier_group || (d.supplier_groups || [])[0] || "";
		function input(f) {
			var k = f[0], v = det[k] || "", mark = read.indexOf(k) !== -1 ? ' <span class="a3s-supbill__fromread">from the invoice</span>' : "";
			var ctl = k === "gst_category" ? '<select data-sup="' + k + '">' + options(d.gst_categories || [], v) + "</select>"
				: k === "supplier_group" ? '<select data-sup="' + k + '">' + options(d.supplier_groups || [], v) + "</select>"
				: '<input data-sup="' + k + '" value="' + esc(v) + '">';
			return '<div class="a3s-field"><label>' + f[1] + mark + "</label>" + ctl + "</div>";
		}
		return '<div class="a3s-supbill__newsup"><p class="a3s-modal__title">New supplier &mdash; not in ERPNext yet</p>' +
			'<p class="a3s-field__hint">Read from the invoice: check the details, then create the supplier. Its bills are entered and paid on their own.</p>' +
			'<div class="a3s-paytask__fields">' + SUPPLIER_FIELDS.map(input).join("") + "</div>" +
			label("Bank details") + '<div class="a3s-paytask__fields">' + BANK_FIELDS.map(input).join("") + "</div>" +
			'<div class="a3s-form__actions" style="margin-top:0.75rem"><button type="button" class="a3s-btn a3s-btn--primary" data-make-supplier>Create supplier in ERPNext</button></div></div>';
	}

	function makeSupplier() {
		if (busy || !draft) return;
		var det = draft.supplier.details || {};
		Array.prototype.forEach.call(body.querySelectorAll("[data-sup]"), function (el) { det[el.dataset.sup] = el.value.trim(); });
		if (!det.supplier_name) { setStatus("Enter the supplier's name.", "error"); return; }
		busy = true;
		setStatus("Creating " + det.supplier_name + " in ERPNext\u2026");
		call("create_supplier", { installation: installation, details: JSON.stringify(det) }).then(function (made) {
			var gst = (made.gstin || "").toUpperCase();
			/* This bill, and every other read bill of the same new supplier, now has it. */
			queue.concat(entry() ? [] : [{ data: draft }]).forEach(function (q) {
				var sup = q.data && q.data.supplier;
				if (!sup || !sup["new"]) return;
				var same = gst ? (sup.gstin || "").toUpperCase() === gst : (sup.supplier_name || "").trim().toUpperCase() === det.supplier_name.toUpperCase();
				if (same || q.data === draft) { sup.name = made.supplier; sup["new"] = false; sup.supplier_name = made.name; sup.gstin = made.gstin || sup.gstin; sup.gstin_on_file = made.gstin; }
			});
			draft.supplier.name = made.supplier; draft.supplier["new"] = false; draft.supplier.gstin_on_file = made.gstin;
			paint();
			setStatus((made.existed ? made.name + " was already in ERPNext; the bill is under it." : made.name + " is created in ERPNext, with its address" +
				(det.account_no ? ", contact and bank account." : " and contact.")) + " Now check the bill and create the Purchase Invoice.", "ok");
		}).catch(function (e) { setStatus(e.message, "error"); }).then(function () { busy = false; });
	}

	/* A supplier's details - its GSTIN, address, contact, bank account and IFSC - changed in a pop-up. */
	function editSupplier(supplier) {
		setStatus("Opening " + supplier + "\u2026");
		fetch(API + "supplier_profile?" + new URLSearchParams({ installation: installation, supplier: supplier }), {
			credentials: "same-origin", headers: { Accept: "application/json" }
		}).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(message(d, "Could not open the supplier.")); return d.message; }); })
		  .then(function (prof) {
			setStatus("");
			var d = prof.details;
			function input(f) {
				var k = f[0], v = d[k] || "";
				var ctl = k === "gst_category" ? '<select data-ed="' + k + '">' + options(prof.gst_categories, v) + "</select>"
					: k === "supplier_group" ? '<select data-ed="' + k + '">' + options(prof.supplier_groups, v) + "</select>"
					: '<input data-ed="' + k + '" value="' + esc(v) + '"' + (prof.can_edit ? "" : " disabled") + ">";
				return '<div class="a3s-field"><label>' + f[1] + "</label>" + ctl + "</div>";
			}
			var modal = document.createElement("div");
			modal.className = "a3s-modal";
			modal.setAttribute("role", "dialog");
			modal.setAttribute("aria-modal", "true");
			modal.innerHTML = '<div class="a3s-modal__panel a3s-supbill__edpanel"><p class="a3s-modal__title">Supplier details</p>' +
				'<p class="a3s-field__hint">' + esc(prof.supplier) + " &middot; saved to the supplier in ERPNext, its address, contact and bank account.</p>" +
				'<div class="a3s-paytask__fields">' + SUPPLIER_FIELDS.map(input).join("") + "</div>" +
				label("Bank accounts") + '<div data-ed-banks></div>' +
				(prof.can_edit ? '<button type="button" class="a3s-btn a3s-btn--ghost" data-ed-addbank>+ Add bank account</button>' : "") +
				'<p class="a3s-attach__status" data-ed-status hidden></p>' +
				'<div class="a3s-form__actions" style="margin-top:0.75rem">' + (prof.can_edit ? '<button type="button" class="a3s-btn a3s-btn--primary" data-ed-save>Save supplier</button>' : "") +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-ed-cancel>' + (prof.can_edit ? "Cancel" : "Close") + "</button></div></div>";
			document.body.appendChild(modal);
			/* The supplier's accounts, each its own group: Default, Remove, and + Add bank account. */
			var banks = (d.bank_accounts || []).map(function (b) { return Object.assign({}, b); });
			if (!banks.length) banks.push({ is_default: 1 });
			var BANK_EDIT = BANK_FIELDS.filter(function (f) { return f[0] !== "branch"; });
			function readBanks() {
				Array.prototype.forEach.call(modal.querySelectorAll("[data-bank]"), function (g) {
					var b = banks[+g.dataset.bank];
					Array.prototype.forEach.call(g.querySelectorAll("[data-bk]"), function (el) { b[el.dataset.bk] = el.value.trim(); });
				});
			}
			function drawBanks() {
				modal.querySelector("[data-ed-banks]").innerHTML = banks.map(function (b, i) {
					if (b.remove) return "";
					return '<div class="a3s-supbill__bank" data-bank="' + i + '"><div class="a3s-paytask__fields">' + BANK_EDIT.map(function (f) {
						return '<div class="a3s-field"><label>' + f[1] + '</label><input data-bk="' + f[0] + '" value="' + esc(b[f[0]] || "") + '"' + (prof.can_edit ? "" : " disabled") + "></div>";
					}).join("") + "</div>" + '<div class="a3s-supbill__banktools"><label class="a3s-check"><input type="radio" name="ed-default" data-bank-default="' + i + '"' +
						(b.is_default ? " checked" : "") + (prof.can_edit ? "" : " disabled") + "> <span>Default account</span></label>" +
						(prof.can_edit ? '<button type="button" class="a3s-textlink" data-bank-remove="' + i + '">Remove</button>' : "") + "</div></div>";
				}).join("") || '<p class="a3s-field__hint">No bank account.</p>';
			}
			drawBanks();
			modal.addEventListener("click", function (e) {
				if (e.target.closest("[data-ed-addbank]")) { readBanks(); banks.push({ is_default: banks.every(function (b) { return b.remove; }) ? 1 : 0 }); drawBanks(); }
				var rm = e.target.closest("[data-bank-remove]");
				if (rm) {
					readBanks();
					var b = banks[+rm.dataset.bankRemove];
					if (b.name && !window.confirm("Remove " + (b.bank_name || "this account") + " " + (b.account_no || "") + " from the supplier? Past payments keep it.")) return;
					if (b.name) b.remove = 1; else banks.splice(+rm.dataset.bankRemove, 1);
					drawBanks();
				}
				var df = e.target.closest("[data-bank-default]");
				if (df) { readBanks(); banks.forEach(function (b, i) { b.is_default = i === +df.dataset.bankDefault ? 1 : 0; }); }
			});
			var note = modal.querySelector("[data-ed-status]");
			function close() { modal.remove(); }
			modal.querySelector("[data-ed-cancel]").addEventListener("click", close);
			modal.addEventListener("click", function (e) { if (e.target === modal) close(); });
			var save = modal.querySelector("[data-ed-save]");
			if (save) save.addEventListener("click", function () {
				var out = {};
				Array.prototype.forEach.call(modal.querySelectorAll("[data-ed]"), function (el) { out[el.dataset.ed] = el.value.trim(); });
				readBanks();
				out.bank_accounts = banks.filter(function (b) { return b.remove || b.account_no || b.bank_name; });
				var bad = out.bank_accounts.filter(function (b) { return !b.remove && !(b.account_no && b.bank_name); });
				if (bad.length) { note.hidden = false; note.dataset.tone = "error"; note.textContent = "Each bank account needs its bank name and account no."; return; }
				note.hidden = false; note.dataset.tone = ""; note.textContent = "Saving\u2026";
				save.disabled = true;
				call("update_supplier", { installation: installation, supplier: prof.supplier, details: JSON.stringify(out) }).then(function (after) {
					close();
					/* The open bill shows the supplier as it now is. */
					queue.forEach(function (q) {
						var sp = q.data && q.data.supplier;
						if (sp && sp.name === after.supplier) { sp.gstin_on_file = after.details.gstin; sp.supplier_name = after.details.supplier_name; }
					});
					if (draft && draft.supplier.name === after.supplier) { draft.supplier.gstin_on_file = after.details.gstin; }
					return refreshState().then(function () {
						paint();
						setStatus(after.details.supplier_name + "'s details are saved in ERPNext.", "ok");
					});
				}).catch(function (e) { save.disabled = false; note.dataset.tone = "error"; note.textContent = e.message; });
			});
		}).catch(function (e) { setStatus(e.message, "error"); });
	}

	function refreshState() {
		return fetch(API + "state?" + new URLSearchParams({ installation: installation }), { credentials: "same-origin", headers: { Accept: "application/json" } })
			.then(function (r) { return r.json(); }).then(function (d) { if (d && d.message) state = d.message; }).catch(function () { /* keep */ });
	}

	/* Every ready bill entered in turn, unpaid; the first that fails stops it, and opens. */
	function createAll() {
		if (busy) return;
		openEntry(current);  /* keep the open bill's edits */
		var ready = queue.map(function (q, i) { return i; }).filter(function (i) { return entryState(queue[i]).key === "ready"; });
		busy = true;
		var done = 0;
		ready.reduce(function (chain, i) {
			return chain.then(function () {
				var q = queue[i], keep = draft;
				draft = q.data;
				draft.payment = { status: "Unpaid" };
				var data = payload();
				draft = keep;
				setStatus("Entering " + (done + 1) + " of " + ready.length + "\u2026");
				var form = new FormData();
				form.append("file", q.file, q.file.name);
				return call("create", { installation: installation, data: JSON.stringify(data) }, form).then(function (res) {
					q.entered = res.name; state = res.state; done++;
				}).catch(function (e) { q.failed = e.message; throw { at: i, message: e.message }; });
			});
		}, Promise.resolve()).then(function () {
			busy = false;
			var next = queue.findIndex(function (q) { return q.data && !q.entered && !q.data.already_entered && !q.error; });
			current = -1; draft = null;
			if (next !== -1) openEntry(next); else paint();
			setStatus(done + " bills entered, unpaid. " + summary(), "ok");
		}).catch(function (err) {
			busy = false; current = -1; draft = null;
			openEntry(err.at);
			setStatus(done + " entered; stopped at this bill: " + err.message, "error");
		});
	}

	body.addEventListener("click", function (e) {
		var st = e.target.closest("[data-pay-status]"), mp = e.target.closest("[data-mark-paid]");
		if (st && draft) {
			if (draft.payment && draft.payment.status === "Paid") readPayment(body.querySelector("[data-paybox]") || body, draft.payment);
			draft.payment.status = st.dataset.payStatus; paint(); return;
		}
		if (mp) { markPaid(mp.dataset.markPaid); return; }
		var ps = e.target.closest("[data-pay-supplier]");
		if (ps) { markPaid(null, cards()[+ps.dataset.paySupplier]); return; }
		if (e.target.closest("[data-make-supplier]")) { makeSupplier(); return; }
		if (e.target.closest("[data-skip-bank]") && draft) { draft.new_bank_dismissed = true; paint(); return; }
		if (e.target.closest("[data-add-bank]") && draft && !busy) {
			var nb = draft.new_bank_account;
			if (!window.confirm("Add " + nb.bank_name + " A/c " + nb.account_no + (nb.ifsc ? " (IFSC " + nb.ifsc + ")" : "") + " to " +
				(draft.supplier.supplier_name || draft.supplier.name) + "? It stays the same supplier, with one more account.")) return;
			busy = true;
			call("add_bank_account", { installation: installation, supplier: draft.supplier.name, details: JSON.stringify(nb) }).then(function () {
				draft.new_bank_account = null;
				return refreshState().then(function () { paint(); setStatus(nb.bank_name + " A/c " + nb.account_no + " is added to " + (draft.supplier.supplier_name || draft.supplier.name) + ".", "ok"); });
			}).catch(function (err) { setStatus(err.message, "error"); }).then(function () { busy = false; });
			return;
		}
		var es = e.target.closest("[data-edit-supplier]");
		if (es) { editSupplier(es.dataset.editSupplier); return; }
		if (e.target.closest("[data-wrong-keep]") && entry()) { delete entry().wrongCard; paint(); return; }
		if (e.target.closest("[data-pick]")) picker.click();
		else if (e.target.closest("[data-create]")) create();
		else if (e.target.closest("[data-add-line]")) addLine();
		else if (e.target.closest("[data-remove-row]")) removeLine(+e.target.closest("[data-row]").dataset.row);
		else if (e.target.closest("[data-discard]")) {
			if (current >= 0) queue.splice(current, 1);
			current = -1; draft = null; file = null; calc = null; setStatus("");
			var left = queue.findIndex(function (q) { return q.data && !q.entered; });
			if (left !== -1) openEntry(left); else { queue = queue.filter(function (q) { return q.entered; }); paint(); }
		}
		else if (e.target.closest("[data-open-bill]")) openEntry(+e.target.closest("[data-open-bill]").dataset.openBill);
		else if (e.target.closest("[data-create-all]")) createAll();
		else if (e.target.closest("[data-done]")) {
			if (busy) return;
			busy = true;
			call("mark_done", { installation: installation }).then(function (s) {
				state = s; paint(); setStatus("Supplier Invoice is done.", "ok");
			}).catch(function (err) { setStatus(err.message, "error"); }).then(function () { busy = false; });
		}
	});

	/* Edits keep the draft: a line's amount follows its qty and rate, and every change is
	   worked out again by ERPNext. */
	function edited(e) {
		if (!draft) return;
		var el = e.target;
		if (el.dataset.sup) { (draft.supplier.details = draft.supplier.details || {})[el.dataset.sup] = el.value; return; }
		if (status.dataset.tone === "ok") setStatus("");  /* what was read no longer says it all */
		if (el.hasAttribute("data-tax-template")) {
			draft.tax_template = el.value; recalc(); return;
		}
		if (el.dataset.head) {
			if (["supplier_name", "supplier_gstin"].indexOf(el.dataset.head) !== -1) {
				draft.supplier[el.dataset.head === "supplier_name" ? "supplier_name" : "gstin"] = el.value;
			} else draft.bill[el.dataset.head] = el.value;
			return;
		}
		if (el.dataset.f) {
			var tr = el.closest("[data-row]"), r = rows()[+tr.dataset.row];
			r[el.dataset.f] = el.value;
			if (el.dataset.f === "qty" || el.dataset.f === "rate") {
				r.amount = round2(num(r.qty) * num(r.rate) * (1 - num(r.discount) / 100));
				tr.querySelector("[data-amount]").textContent = money.format(r.amount);
			}
			if (["qty", "rate", "item_tax_template", "description"].indexOf(el.dataset.f) !== -1) recalc();
		}
	}
	body.addEventListener("input", edited);
	body.addEventListener("change", function (e) {
		if (e.target.dataset.pay === "mode" && draft) {
			var acc = accountOf(e.target.value), sel = body.querySelector('[data-paybox] [data-pay="account"]');
			if (acc && sel && sel.value !== "Reimbursement") sel.value = acc;
			return;
		}
		if (e.target.dataset.pay === "account" && draft) {
			toggleReimb(body.querySelector("[data-paybox]"), calc ? calc.rounded_total : "");
			return;
		}
		if (e.target.dataset.pay) return;
		if (e.target.tagName === "SELECT") edited(e);
	});

	picker.addEventListener("change", function () { readBills(picker.files); });
	body.addEventListener("dragover", function (e) { if (e.target.closest("[data-drop]")) e.preventDefault(); });
	body.addEventListener("drop", function (e) {
		if (!e.target.closest("[data-drop]")) return;
		e.preventDefault();
		readBills(e.dataTransfer && e.dataTransfer.files);
	});

	paint();
})();
