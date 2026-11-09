/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * How a document read on the lead's or the customer's form fills it. The documents are
 * uploaded on the Attachments card and read one by one with its Read button (portal_attachments.js,
 * api/portal_attachments.read_file): the KSEB bill, each side of the Aadhaar card, the bank
 * proof. What a document says comes back as the record's fields, and goes in through
 * window.a3sReadFill:
 *
 * - what the document says comes first: a field is filled and marked, whatever was typed in
 *   before - the person can still change it, and saving asks them to check it, with what it was;
 * - the customer's name is the Aadhaar card's: read, it replaces any other, and a different one
 *   is said in a Name mismatch pop-up; once read from the card, no other document offers a name;
 * - the permanent address likewise: the KSEB bill gives it until the Aadhaar card is read, and
 *   the card's then stands;
 * - "From Aadhaar card" goes under each field filled (portal_read_from.js).
 *
 * Nothing is saved until the form is.
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
	/* Parents before the fields that depend on them - the section last, its list being the
	   DISCOM's sections in the connection's district. */
	var ORDER = ["discom", "state", "district", "site_state", "site_district",
		"permanent_address_same", "permanent_state", "permanent_district", "discom_section"];
	/* The customer's name is the one on the Aadhaar card: read, it replaces any other - the
	   KSEB bill's, or one typed in - and a different one is shown in a pop-up. Until then
	   the bill's or the typed name stands. */
	var AADHAAR = "Aadhaar card", NAME = "consumer_name";
	/* The permanent address, likewise: the Aadhaar card's, else the KSEB bill's until a card is read.
	   Not the "site the same?" answer: a bill gives the site, so it answers No and shows it beside
	   the card's address, for the person to say Yes if they are one place. */
	var PERMANENT = ["permanent_address_line1", "permanent_address_line2", "permanent_city",
		"permanent_state", "permanent_district", "permanent_pincode"];
	function permanentFromAadhaar() { return PERMANENT.some(function (n) { return readFrom(n) === AADHAAR; }); }

	var style = document.createElement("style");
	style.textContent =
		".a3s-kseb-filled{outline:2px solid #f79009;outline-offset:1px;background:#fffaeb}" +
		".a3s-kseb-offer{display:block;font-size:.8rem;color:#b54708;margin-top:.2rem}.a3s-kseb-offer button{border:0;background:none;color:inherit;text-decoration:underline;cursor:pointer;padding:0 0 0 .3rem}";
	document.head.appendChild(style);

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

	function set(el, value, source) {
		if (el.tagName === "SELECT") {
			if (!hasOption(el, value)) return false;
		}
		var before = el.tagName === "SELECT" && el.selectedIndex >= 0 && el.value ? el.options[el.selectedIndex].textContent : el.value;
		el.value = value;
		el.dispatchEvent(new Event("change", { bubbles: true }));
		mark(el);
		/* "From Aadhaar card" under it, and what it held before (portal_read_from.js). */
		if (source && window.a3sReadFrom) window.a3sReadFrom.mark(el, source, before);
		return true;
	}

	function readFrom(name) { return window.a3sReadFrom ? window.a3sReadFrom.of(name) : ""; }

	/* Two spellings of one name: the same letters, whatever the case, spaces and dots. */
	function sameName(a, b) {
		var letters = function (v) { return String(v || "").toLowerCase().replace(/[^a-z]/g, ""); };
		return letters(a) === letters(b);
	}

	function esc(v) {
		return String(v).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
	}

	/* The name the customer had, replaced by the Aadhaar card's: said in a pop-up. */
	function nameMismatch(before, after) {
		var modal = document.createElement("div");
		modal.className = "a3s-modal";
		modal.setAttribute("role", "dialog");
		modal.setAttribute("aria-modal", "true");
		modal.setAttribute("aria-labelledby", "a3s-name-mismatch-title");
		modal.innerHTML = '<div class="a3s-modal__panel a3s-modal__panel--mismatch">' +
			'<p class="a3s-modal__title" id="a3s-name-mismatch-title">&#9888; Name mismatch</p>' +
			"<p>The Aadhaar card is in the name of <b>" + esc(after) + "</b>, but this customer was <b>" + esc(before) + "</b>.</p>" +
			"<p>The customer&rsquo;s name is now <b>" + esc(after) + "</b>, as on the Aadhaar card. Save changes to keep it.</p>" +
			'<div class="a3s-form__actions" style="margin-top:1rem"><button type="button" class="a3s-btn a3s-btn--primary" data-close>OK</button></div></div>';
		document.body.appendChild(modal);
		function close() { modal.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		modal.addEventListener("click", function (e) { if (e.target === modal || e.target.closest("[data-close]")) close(); });
		document.addEventListener("keydown", onKey);
		modal.querySelector("[data-close]").focus();
	}

	/* The fields in, one after another; done is told what happened ({filled, replaced, missed}). */
	function fill(values, source, done) {
		var missed = [], filled = [], replaced = [], mismatch = null;
		var names = Object.keys(values).sort(function (a, b) {
			var ia = ORDER.indexOf(a), ib = ORDER.indexOf(b);
			return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
		});
		var queue = names.slice();
		(function next() {
			var name = queue.shift();
			if (!name) {
				if (mismatch) nameMismatch(mismatch.before, mismatch.after);
				return done({ filled: filled, replaced: replaced, offered: 0, missed: missed });
			}
			var el = field(name), value = values[name] === null || values[name] === undefined ? "" : String(values[name]);
			if (!el) return next();
			var current = el.value;
			if (doctype === "Solar Consumer" && name === NAME) {
				if (source === AADHAAR) {
					/* The Aadhaar card's name is the customer's, whatever was there. */
					if (current && !sameName(current, value)) mismatch = { before: current, after: value };
					if (current !== value) { set(el, value, source); (current ? replaced : filled).push(el); }
					else window.a3sReadFrom && window.a3sReadFrom.mark(el, source);
					return next();
				}
				/* Read from the Aadhaar card already: no other document offers a name. */
				if (readFrom(name) === AADHAAR) return next();
			}
			/* The card's permanent address stands: no other document replaces it. */
			if (source !== AADHAAR && PERMANENT.indexOf(name) !== -1 && permanentFromAadhaar()) return next();
			if (current === value) {
				/* The same value: this document is its source too, if it had none. */
				if (source && !readFrom(name) && window.a3sReadFrom) window.a3sReadFrom.mark(el, source);
				return next();
			}
			/* The document's value comes first, whatever was typed in. */
			var go = function () {
				if (!set(el, value, source)) missed.push(name.replace(/_/g, " "));
				else (current ? replaced : filled).push(el);
				next();
			};
			/* A list still reloading for its parent (set just before) would drop a value set now. */
			if (el.tagName === "SELECT" && el.dataset.dependsOn && (el.disabled || !hasOption(el, value))) {
				whenOffered(el, value, function () { go(); });
			} else go();
		})();
	}

	/* A section the bill names that the list lacks: under the field, a button that adds it in
	   one click, with the bill's code and name, and chooses it (portal_combo_fields.html). */
	function offerSection(missing) {
		var select = document.getElementById("fld-discom_section");
		var wrap = select && select.closest("[data-combo-add]");
		if (!wrap) return;
		/* Kept on the field too: the add panel from the list starts on this bill's section. */
		var row = wrap.querySelector(".a3s-section-add__row");
		if (!missing) { delete wrap.dataset.billSection; if (row) row.innerHTML = ""; return; }
		wrap.dataset.billSection = JSON.stringify(missing);
		if (!row) return;
		/* A bill read again: its button replaces the last one's. */
		row.innerHTML = "";
		var near = document.createElement("button");
		near.type = "button";
		near.className = "a3s-section-add__open a3s-section-add__bill";
		var label = "+ Add section [" + missing.code + "] " + (missing.name || "");
		near.textContent = label;
		near.title = "The section the KSEB bill names is not on file: add it and choose it";
		var note = document.createElement("span");
		note.className = "a3s-form__status";
		note.setAttribute("role", "status");
		near.addEventListener("click", function () {
			if (!window.a3sAddBillSection) return;
			near.disabled = true;
			near.textContent = "Adding…";
			note.textContent = ""; delete note.dataset.tone;
			window.a3sAddBillSection(missing).catch(function (e) {
				near.disabled = false;
				near.textContent = label;
				note.textContent = e.message; note.dataset.tone = "error";
			});
		});
		row.appendChild(near);
		row.appendChild(note);
		/* Once added, the button is done with. */
		document.addEventListener("a3s:section-added", function () { near.remove(); note.remove(); }, { once: true });
	}

	/* The Attachments card's Read (portal_attachments.js): a document's fields into this form. Its
	   warnings are the card's to show; a section the bill names that the list lacks is offered here. */
	window.a3sReadFill = function (values, source, extras) {
		if (extras && extras.missing_section) offerSection(extras.missing_section);
		return new Promise(function (resolve) { fill(values || {}, source, resolve); });
	};
})();
