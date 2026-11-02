/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The Enter Serial Numbers page (www/a3solaportal/projects/task.html, api/serial_entry): the
 * job's serial register - modules, inverters, optimisers, the rest - one serial a line. The
 * supplier bill's serials come in by themselves the first time and on Fetch; a photo or PDF of
 * the labels is read with OCR and its serials ticked in; anything is typed or corrected, then
 * Saved. Mark done completes the task once every module and the inverter have a serial.
 */
(function () {
	"use strict";

	var root = document.querySelector("[data-serent]");
	if (!root) return;
	var API = "/api/method/a3_sola.api.serial_entry.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var installation = root.dataset.installation;
	var body = root.querySelector("[data-serent-body]");
	var status = root.querySelector("[data-serent-status]");
	var picker = root.querySelector("[data-serent-file]");
	var state = JSON.parse(root.querySelector("[data-serent-data]").textContent);
	var FIELDS = { Module: "module_serials", Inverter: "inverter_serials", Optimiser: "optimiser_serials", Other: "other_serials" };
	var LABELS = { Module: "Modules", Inverter: "Inverters", Optimiser: "Optimisers", Other: "Other (meter, boxes, ...)" };
	/* What the last photo read: its serials, to tick into `kind`. */
	var read = null, busy = false, dirty = false;

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

	/* The boxes as they stand: {type: [serials]}. */
	function typed() {
		var out = {};
		state.types.forEach(function (t) {
			var box = body.querySelector('[data-kind="' + t + '"]');
			out[t] = (box ? box.value : (state.register[t] || []).join("\n")).split(/[\n,]+/)
				.map(function (s) { return s.trim(); }).filter(Boolean);
		});
		return out;
	}

	/* Serials entered twice across the boxes. */
	function duplicates(lists) {
		var seen = {}, dup = [];
		Object.keys(lists).forEach(function (t) {
			lists[t].forEach(function (s) {
				var k = s.toUpperCase();
				if (seen[k] && dup.indexOf(s) === -1) dup.push(s);
				seen[k] = true;
			});
		});
		return dup;
	}

	function countText(t, n) {
		if (t === "Module" && state.expected_modules) {
			var ok = n >= state.expected_modules;
			return '<span class="a3s-serent__count ' + (ok ? "is-ok" : "is-short") + '">' + n + " of " + state.expected_modules + (ok ? " ✓" : "") + "</span>";
		}
		if (t === "Inverter") return '<span class="a3s-serent__count ' + (n ? "is-ok" : "is-short") + '">' + n + "</span>";
		return '<span class="a3s-serent__count">' + n + "</span>";
	}

	function billsTable() {
		if (!state.bills.length) {
			return '<p class="a3s-field__hint">The supplier invoice lists no serial numbers' +
				" &mdash; read them off the labels below, or type them.</p>";
		}
		var fresh = state.bills.filter(function (b) { return !b.in_register; }).length;
		return '<div class="a3s-tablewrap"><table class="a3s-table"><thead><tr><th>Serial no.</th><th>Type</th><th>Item</th><th>Bill</th><th></th></tr></thead><tbody>' +
			state.bills.map(function (b) {
				return "<tr><td>" + esc(b.serial_no) + "</td><td>" + esc(b.component_type) + "</td><td>" + esc(b.item_name) +
					"</td><td>" + esc(b.bill_no || b.invoice) + "</td><td" + (b.in_register ? ">In the register" : ' class="new">Not yet') + "</td></tr>";
			}).join("") + "</tbody></table></div>" +
			(state.can_edit && fresh ? '<div class="a3s-form__actions" style="margin-top:0.6rem"><button type="button" class="a3s-btn a3s-btn--ghost" data-fetch>' +
				"Fetch " + fresh + " from supplier invoice</button></div>" : "");
	}

	function boxes() {
		var lists = state.register;  /* drawn from the server's register, not the boxes it replaces */
		return '<div class="a3s-serent__boxes">' + state.types.map(function (t) {
			return '<div class="a3s-field"><label for="se-' + t + '">' + LABELS[t] + countText(t, (lists[t] || []).length) + "</label>" +
				'<textarea id="se-' + t + '" data-kind="' + t + '" spellcheck="false"' + (state.can_edit ? "" : " disabled") +
				' placeholder="One serial number a line">' + esc((state.register[t] || []).join("\n")) + "</textarea></div>";
		}).join("") + "</div><p class=\"a3s-serent__dup\" data-dups hidden></p>";
	}

	function readPanel() {
		if (!state.can_edit) return "";
		var html = label("Read serial numbers from a photo") + '<div class="a3s-serent__read">' +
			'<span>Add to</span><select data-read-kind>' + state.types.map(function (t) {
				return '<option value="' + t + '">' + LABELS[t] + "</option>";
			}).join("") + "</select>" +
			'<button type="button" class="a3s-btn a3s-btn--primary" data-pick>Upload photo or PDF</button>' +
			'<span class="a3s-field__hint">The labels, a sticker sheet or the packing list: the serial numbers on it are read for you to tick.</span></div>';
		if (read) {
			html += '<p style="margin:0.75rem 0 0"><b>' + read.serials.length + " serial numbers read</b> from " + esc(read.name) +
				(read.serials.length ? " &mdash; tick the ones to add to <b>" + esc(LABELS[read.kind]) + "</b>." : ".") + "</p>" +
				'<div class="a3s-serent__picks">' + read.serials.map(function (s, i) {
					return '<label><input type="checkbox" data-pick-serial="' + i + '"' + (s.have ? " disabled" : " checked") + "> " + esc(s.serial_no) +
						(s.have ? ' <span class="a3s-field__hint">(already entered)</span>' : "") + "</label>";
				}).join("") + "</div>" +
				(read.serials.length ? '<button type="button" class="a3s-btn a3s-btn--ghost" data-add-read>Add the ticked serials</button> ' : "") +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-clear-read>Close</button>';
		}
		return html;
	}

	function paint() {
		var t = state.task;
		var html = '<div class="a3s-paytask__head"><h3 class="a3s-edit__card-title">' + esc(t.name) + "</h3>" +
			'<span class="a3s-status-pill">' + esc(t.status) + (t.completed_on ? " &middot; " + esc(t.completed_on) : "") + "</span></div>" +
			'<p class="a3s-field__hint">' + esc(state.consumer_name || state.installation) +
			" &middot; every module, inverter and other unit's serial number, as the project's register keeps it.</p>";
		html += label("From the supplier invoice") + billsTable();
		html += label("Serial numbers") + boxes();
		html += "<div data-readwrap>" + readPanel() + "</div>";
		if (state.can_edit) {
			html += '<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--primary" data-save>Save serials</button>' +
				(state.can_complete ? '<button type="button" class="a3s-btn a3s-btn--ghost" data-done>Mark done</button>' : "") + "</div>";
		}
		body.innerHTML = html;
		dirty = false;
	}

	function refresh() {
		var lists = typed();
		state.types.forEach(function (t) {
			var lab = body.querySelector('label[for="se-' + t + '"] .a3s-serent__count');
			if (lab) lab.outerHTML = countText(t, lists[t].length);
		});
		var dup = duplicates(lists), note = body.querySelector("[data-dups]");
		note.hidden = !dup.length;
		note.textContent = dup.length ? "Entered twice: " + dup.join(", ") + "." : "";
		return dup;
	}

	function args() {
		var lists = typed(), out = { installation: installation };
		state.types.forEach(function (t) { out[FIELDS[t]] = lists[t].join("\n"); });
		return out;
	}

	function run(method, extra, done) {
		if (busy) return;
		busy = true;
		call(method, extra || { installation: installation }).then(function (s) {
			state = s; paint(); setStatus(done, "ok");
		}).catch(function (e) { setStatus(e.message, "error"); }).then(function () { busy = false; });
	}

	function save() {
		if (refresh().length) { setStatus("A serial is entered twice: remove the repeat, then save.", "error"); return; }
		run("save", args(), "Serial numbers saved.");
	}

	body.addEventListener("input", function (e) { if (e.target.dataset.kind) { dirty = true; refresh(); } });
	body.addEventListener("click", function (e) {
		if (e.target.closest("[data-save]")) save();
		else if (e.target.closest("[data-fetch]")) {
			if (dirty && !window.confirm("Save what is typed here first? Fetching saves the register.")) return;
			run("fetch_from_bills", { installation: installation }, "Serial numbers fetched from the supplier invoice.");
		} else if (e.target.closest("[data-done]")) {
			if (dirty) { setStatus("Save the serial numbers first.", "error"); return; }
			run("mark_done", { installation: installation }, "Enter Serial Numbers is done.");
		} else if (e.target.closest("[data-pick]")) picker.click();
		else if (e.target.closest("[data-clear-read]")) { read = null; repaintRead(); }
		else if (e.target.closest("[data-add-read]")) {
			var box = body.querySelector('[data-kind="' + read.kind + '"]');
			var lines = box.value.split("\n").map(function (s) { return s.trim(); }).filter(Boolean);
			var n = 0;
			Array.prototype.forEach.call(body.querySelectorAll("[data-pick-serial]:checked"), function (c) {
				var s = read.serials[+c.dataset.pickSerial].serial_no;
				if (lines.map(function (l) { return l.toUpperCase(); }).indexOf(s.toUpperCase()) === -1) { lines.push(s); n++; }
			});
			box.value = lines.join("\n");
			read = null; dirty = true; repaintRead(); refresh();
			setStatus(n + " serial numbers added to " + LABELS[box.dataset.kind] + ". Check them, then Save serials.", "ok");
		}
	});

	/* Only the read panel redraws: what is typed in the boxes stays. */
	function repaintRead() {
		var holder = body.querySelector("[data-readwrap]");
		var kind = (holder.querySelector("[data-read-kind]") || {}).value;
		holder.innerHTML = readPanel();
		var sel = holder.querySelector("[data-read-kind]");
		if (sel) sel.value = read ? read.kind : (kind || sel.value);
	}

	picker.addEventListener("change", function () {
		var f = picker.files[0];
		if (!f || busy) return;
		var kind = body.querySelector("[data-read-kind]").value;
		busy = true;
		setStatus("Reading " + f.name + "… (a photo takes a few seconds)");
		var form = new FormData();
		form.append("file", f, f.name);
		call("read_upload", { installation: installation }, form).then(function (res) {
			var have = {};
			var lists = typed();
			Object.keys(lists).forEach(function (t) { lists[t].forEach(function (s) { have[s.toUpperCase()] = true; }); });
			read = { kind: kind, name: f.name, serials: (res.serials || []).map(function (s) { return { serial_no: s, have: !!have[s.toUpperCase()] }; }) };
			repaintRead();
			setStatus(read.serials.length ? "Read " + read.serials.length + " serial numbers. Tick the ones to add." :
				"No serial numbers could be read from " + f.name + ". Try a sharper photo, or type them.", read.serials.length ? "ok" : "error");
		}).catch(function (e) { setStatus(e.message, "error"); }).then(function () { busy = false; picker.value = ""; });
	});

	paint();
	/* The first time: an empty register takes the supplier bill's serials by itself. */
	var empty = state.types.every(function (t) { return !(state.register[t] || []).length; });
	if (state.can_edit && empty && state.bills.length) {
		run("fetch_from_bills", { installation: installation },
			"The supplier invoice's " + state.bills.length + " serial numbers are entered. Check them, then Mark done.");
	}
})();
