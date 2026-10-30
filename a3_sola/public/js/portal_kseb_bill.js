/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * "Read KSEB bill" on the lead and customer forms (api/kseb_bill.py). The bill - a PDF or a
 * photo - is read on the server and its details come back as the record's fields. A blank
 * field - or, on a new record, one still at the page's default - is filled and marked; a
 * field already holding something else is left alone, the bill's value offered beside it. Nothing is saved until the form is. On a record that
 * exists, the server also attaches the bill as its KSEB Bill.
 */
(function () {
	"use strict";

	var FORMS = [
		{ id: "a3s-record-form", doctype: function (f) { return f.dataset.doctype === "Solar Consumer" ? "Solar Consumer" : ""; } },
		{ id: "a3s-record-edit-form", doctype: function (f) { return f.dataset.slug === "consumers" ? "Solar Consumer" : ""; } },
		{ id: "a3s-lead-edit-form", doctype: function () { return "Lead"; } },
		{ id: "a3s-lead-form", doctype: function () { return "Lead"; } }
	];
	var form = null, doctype = "";
	FORMS.some(function (f) {
		var el = document.getElementById(f.id);
		if (el && f.doctype(el)) { form = el; doctype = f.doctype(el); return true; }
		return false;
	});
	if (!form) return;
	var recordName = form.dataset.name || "";
	/* A new record's defaults are the page's, not anyone's choice: the bill may replace them. */
	var defaults = {};
	if (!recordName) {
		Array.prototype.forEach.call(form.elements, function (el) { if (el.name) defaults[el.name] = el.value; });
	}
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	/* Parents before the fields that depend on them. */
	var ORDER = ["discom", "discom_section"];

	var bar = document.createElement("div");
	bar.className = "a3s-kseb";
	bar.innerHTML =
		'<div class="a3s-kseb__row">' +
		'<button type="button" class="a3s-btn a3s-btn--secondary a3s-btn--sm" data-kseb-pick>Read KSEB bill</button>' +
		'<span class="a3s-field__hint">Upload the bill (PDF or a clear photo) and its details fill in below' +
		(recordName ? "; it is also kept as the KSEB Bill." : ".") + "</span>" +
		'<input type="file" accept="application/pdf,image/*" hidden data-kseb-file>' +
		"</div>" +
		'<p class="a3s-kseb__status" data-kseb-status hidden></p>' +
		'<ul class="a3s-kseb__warnings" data-kseb-warnings hidden></ul>';
	form.insertBefore(bar, form.firstElementChild);
	var style = document.createElement("style");
	style.textContent =
		".a3s-kseb{border:1px dashed var(--color-border,#d9dee5);border-radius:10px;padding:.75rem 1rem;margin:0 0 1rem;background:var(--color-surface-muted,#fafbfc)}" +
		".a3s-kseb__row{display:flex;flex-wrap:wrap;gap:.75rem;align-items:center}" +
		".a3s-kseb__status{margin:.5rem 0 0;font-size:.9rem}.a3s-kseb__status.is-error{color:#b42318}.a3s-kseb__status.is-success{color:#067647}" +
		".a3s-kseb__warnings{margin:.35rem 0 0 1.1rem;font-size:.85rem;color:#b54708}" +
		".a3s-kseb-filled{outline:2px solid #f79009;outline-offset:1px;background:#fffaeb}" +
		".a3s-kseb-offer{display:block;font-size:.8rem;color:#b54708;margin-top:.2rem}.a3s-kseb-offer button{border:0;background:none;color:inherit;text-decoration:underline;cursor:pointer;padding:0 0 0 .3rem}";
	document.head.appendChild(style);

	var pick = bar.querySelector("[data-kseb-pick]");
	var file = bar.querySelector("[data-kseb-file]");
	var status = bar.querySelector("[data-kseb-status]");
	var warningsList = bar.querySelector("[data-kseb-warnings]");

	function say(text, kind) {
		status.textContent = text || "";
		status.hidden = !text;
		status.classList.toggle("is-error", kind === "error");
		status.classList.toggle("is-success", kind === "success");
	}

	function serverMessage(body) {
		try {
			var msgs = JSON.parse((body && body._server_messages) || "[]");
			if (msgs.length) return String(JSON.parse(msgs[0]).message || "").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (body && body.exception ? String(body.exception).split(":").slice(1).join(":").trim() : "") || "The bill could not be read.";
	}

	function field(name) {
		var el = form.elements[name];
		return el && el.name && el.type !== "hidden" && el.type !== "file" ? el : null;
	}

	function hasOption(select, value) {
		return Array.prototype.some.call(select.options, function (o) { return o.value === value; });
	}

	/* A dependent list (a DISCOM's sections) reloads after its parent changes: wait for the
	   value to be offered, then set it. */
	function whenOffered(select, value, done) {
		var tries = 0;
		(function poll() {
			if (!select.disabled && hasOption(select, value)) return done(true);
			if (++tries > 40) return done(false);
			setTimeout(poll, 150);
		})();
	}

	function mark(el) {
		el.classList.add("a3s-kseb-filled");
		el.addEventListener("input", function () { el.classList.remove("a3s-kseb-filled"); }, { once: true });
		el.addEventListener("change", function () { el.classList.remove("a3s-kseb-filled"); }, { once: true });
	}

	function set(el, value) {
		if (el.tagName === "SELECT") {
			if (!hasOption(el, value)) return false;
		}
		el.value = value;
		el.dispatchEvent(new Event("change", { bubbles: true }));
		mark(el);
		return true;
	}

	function offer(el, value) {
		var holder = el.closest(".a3s-field, .a3s-form__field, label, div") || el.parentNode;
		var old = holder.querySelector(".a3s-kseb-offer");
		if (old) old.remove();
		var label = el.tagName === "SELECT"
			? (Array.prototype.filter.call(el.options, function (o) { return o.value === value; })[0] || {}).textContent || value
			: value;
		var note = document.createElement("span");
		note.className = "a3s-kseb-offer";
		note.textContent = "Bill says: " + label;
		var use = document.createElement("button");
		use.type = "button";
		use.textContent = "Use";
		use.addEventListener("click", function () { set(el, value); note.remove(); });
		note.appendChild(use);
		holder.appendChild(note);
	}

	function fill(values) {
		var filled = 0, offered = 0, missed = [];
		var names = Object.keys(values).sort(function (a, b) {
			var ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
			return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
		});
		var queue = names.slice();
		(function next() {
			var name = queue.shift();
			if (!name) {
				var parts = [];
				if (filled) parts.push(filled + " field" + (filled === 1 ? "" : "s") + " filled in (marked)");
				if (offered) parts.push(offered + " already set - the bill's value is shown beside them");
				say((parts.join("; ") || "Nothing new to fill in") + ". Check them and save.", "success");
				if (missed.length) warn(["Not offered on this form: " + missed.join(", ") + "."], true);
				return;
			}
			var el = field(name), value = values[name] === null || values[name] === undefined ? "" : String(values[name]);
			if (!el) return next();
			var current = el.value;
			if (current === value) return next();
			var chosen = current && !(name in defaults && current === defaults[name]);
			var go = function () {
				if (chosen) { offer(el, value); offered++; }
				else if (set(el, value)) filled++;
				else missed.push(name.replace(/_/g, " "));
				next();
			};
			if (el.tagName === "SELECT" && el.dataset.dependsOn && !hasOption(el, value)) {
				whenOffered(el, value, function () { go(); });
			} else go();
		})();
	}

	function warn(list, append) {
		if (!append) warningsList.innerHTML = "";
		(list || []).forEach(function (w) {
			var li = document.createElement("li");
			li.textContent = w;
			warningsList.appendChild(li);
		});
		warningsList.hidden = !warningsList.children.length;
	}

	pick.addEventListener("click", function () { file.click(); });
	file.addEventListener("change", function () {
		var chosen = file.files && file.files[0];
		if (!chosen) return;
		var body = new FormData();
		body.append("doctype", doctype);
		if (recordName) body.append("name", recordName);
		body.append("file", chosen, chosen.name);
		pick.disabled = true;
		warn([]);
		say(/\.pdf$/i.test(chosen.name) ? "Reading the bill…" : "Reading the photo… (this can take a few seconds)");
		fetch("/api/method/a3_sola.api.kseb_bill.read", {
			method: "POST", credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json" }, body: body
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (b) { return { ok: r.ok, body: b }; });
		}).then(function (res) {
			if (!res.ok) throw new Error(serverMessage(res.body));
			var out = res.body.message || {};
			warn(out.warnings);
			fill(out.fields || {});
			if (out.attached) {
				document.dispatchEvent(new CustomEvent("a3s:attachments-reload", { detail: { doctype: doctype, name: recordName } }));
			}
			if (out.pending_file) {
				/* No record yet: the bill is kept and becomes the new record's KSEB Bill as it is created. */
				var keep = form.elements.kseb_bill_file;
				if (!keep) {
					keep = document.createElement("input");
					keep.type = "hidden"; keep.name = "kseb_bill_file";
					form.appendChild(keep);
				}
				keep.value = out.pending_file;
				warn(["The bill will be kept as the " + (doctype === "Lead" ? "lead" : "customer") + "'s KSEB Bill when you create it."], true);
			}
		}).catch(function (e) {
			say(e.message || "The bill could not be read.", "error");
		}).then(function () {
			pick.disabled = false;
			file.value = "";
		});
	});
})();
