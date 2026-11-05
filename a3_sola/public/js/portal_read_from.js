/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * "From Aadhaar card" under a field that was read from a document (OCR): the KSEB bill, the
 * Aadhaar card, a passbook or cheque, an approval letter, the portal's acknowledgement. The
 * readers (portal_kseb_bill.js, portal_attachments.js) call window.a3sReadFrom.mark as they
 * fill a field; the notes are kept in the form's hidden a3s_read_from field and saved with
 * the record (api/read_from), so they show again when it is opened. A field typed over by
 * hand is no longer the document's, and its note goes.
 *
 * Saving a form with fields read since it was opened asks first: OCR is not always right, so
 * the person checks what was read - listed, with the document each came from - and saves.
 */
(function () {
	"use strict";

	var FORMS = ["a3s-record-edit-form", "a3s-record-form", "a3s-lead-edit-form", "a3s-lead-form"];
	var form = null;
	FORMS.some(function (id) { form = document.getElementById(id); return !!form; });
	if (!form) return;

	var keep = form.elements.a3s_read_from;
	if (!keep) {
		keep = document.createElement("input");
		keep.type = "hidden"; keep.name = "a3s_read_from";
		form.appendChild(keep);
	}
	var notes = {};
	try { notes = JSON.parse(keep.value || "{}") || {}; } catch (e) { notes = {}; }

	function save() { keep.value = Object.keys(notes).length ? JSON.stringify(notes) : ""; }
	/* The fields read since the page was opened: what saving asks to be checked. */
	var fresh = {};

	function field(name) {
		var el = form.elements[name];
		return el && el.name && el.type !== "hidden" ? el : null;
	}

	function show(el, documentName) {
		var holder = el.closest(".a3s-field, .a3s-form__field") || el.parentNode;
		var note = holder.querySelector(".a3s-readfrom");
		if (!documentName) { if (note) note.remove(); return; }
		if (!note) {
			note = document.createElement("span");
			note.className = "a3s-readfrom";
			/* Under the input, above any "… says: Use" offer. */
			holder.insertBefore(note, holder.querySelector(".a3s-kseb-offer"));
		}
		note.textContent = "From " + documentName;
		note.title = "Read from the " + documentName;
	}

	/* Typed over by hand - a person's input, not a reader's - the value is no longer the document's. */
	function watch(el) {
		if (el.dataset.readFromWatch) return;
		el.dataset.readFromWatch = "1";
		/* A searchable list (portal_combo.js) sets its select for the person: a pick there -
		   a click on an option, Enter in its box - counts as theirs. */
		var picked = 0;
		var holder = el.closest(".a3s-field, .a3s-form__field") || el.parentNode;
		holder.addEventListener("mousedown", function (e) {
			if (e.isTrusted && e.target.closest('[role="option"]')) picked = Date.now();
		}, true);
		holder.addEventListener("keydown", function (e) {
			if (e.isTrusted && e.key === "Enter") picked = Date.now();
		}, true);
		function typed(e) {
			if (!(e.isTrusted || Date.now() - picked < 1500) || !notes[el.name]) return;
			delete notes[el.name];
			delete fresh[el.name];
			save();
			show(el, null);
		}
		el.addEventListener("input", typed);
		el.addEventListener("change", typed);
	}

	window.a3sReadFrom = {
		/* The field was just filled from this document. */
		mark: function (el, documentName, before) {
			if (!el || !el.name || !documentName) return;
			notes[el.name] = documentName;
			/* What it held before this reading, said when saving is checked; the first reading's
			   "before" is kept if another document is read into it too. */
			var was = fresh[el.name] ? fresh[el.name].before : (before || "");
			fresh[el.name] = { before: was };
			save();
			show(el, documentName);
			watch(el);
		},
		/* The document a field was read from, or "". */
		of: function (name) { return notes[name] || ""; }
	};

	Object.keys(notes).forEach(function (name) {
		var el = field(name);
		if (!el) return;
		show(el, notes[name]);
		watch(el);
	});

	/* ------------------------------------------------------- before saving */
	function esc(v) {
		return String(v == null ? "" : v).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}

	function labelOf(el) {
		/* A searchable list's label names its search box (portal_combo.js). */
		var label = el.id && (form.querySelector('label[for="' + el.id + '"]') || form.querySelector('label[for="' + el.id + '-search"]'));
		var text = label ? label.textContent : el.name.replace(/_/g, " ");
		return text.replace(/\*/g, "").trim();
	}

	function shown(el) {
		if (el.tagName === "SELECT") {
			var opt = el.options[el.selectedIndex];
			return opt ? opt.textContent : el.value;
		}
		return el.value;
	}

	/* What was read, to be checked against the documents: saved, or taken back to check. */
	function checkRead(names) {
		return new Promise(function (resolve) {
			var modal = document.createElement("div");
			modal.className = "a3s-modal";
			modal.setAttribute("role", "dialog");
			modal.setAttribute("aria-modal", "true");
			modal.setAttribute("aria-labelledby", "a3s-readcheck-title");
			var rows = names.map(function (name) {
				var el = field(name);
				var was = fresh[name].before && fresh[name].before !== shown(el) ? '<span class="a3s-readcheck__was">was ' + esc(fresh[name].before) + "</span>" : "";
				return "<li><span>" + esc(labelOf(el)) + "</span><b>" + esc(shown(el) || "\u2014") + '</b><span class="a3s-readcheck__from">from ' + esc(notes[name]) + "</span>" + was + "</li>";
			}).join("");
			modal.innerHTML = '<div class="a3s-modal__panel a3s-readcheck">' +
				'<p class="a3s-modal__title" id="a3s-readcheck-title">Check the details read from documents</p>' +
				"<p>These were read from the documents by OCR, which is not always right. Check each one against the document before saving. Where a field held something else, it is said.</p>" +
				'<ul class="a3s-readcheck__list">' + rows + "</ul>" +
				'<div class="a3s-form__actions" style="margin-top:1rem"><button type="button" class="a3s-btn a3s-btn--primary" data-rc-save>I have checked them, save</button>' +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-rc-back>Go back and check</button></div></div>';
			document.body.appendChild(modal);
			function close(answer) { modal.remove(); document.removeEventListener("keydown", onKey); resolve(answer); }
			function onKey(e) { if (e.key === "Escape") close(false); }
			modal.querySelector("[data-rc-save]").addEventListener("click", function () { close(true); });
			modal.querySelector("[data-rc-back]").addEventListener("click", function () { close(false); });
			modal.addEventListener("click", function (e) { if (e.target === modal) close(false); });
			document.addEventListener("keydown", onKey);
			modal.querySelector("[data-rc-save]").focus();
		});
	}

	var passing = false;
	document.addEventListener("submit", function (e) {
		if (passing || e.target !== form) return;
		var names = Object.keys(fresh).filter(function (name) { return notes[name] && field(name); });
		if (!names.length) return;
		e.preventDefault();
		e.stopImmediatePropagation();
		var by = e.submitter;
		checkRead(names).then(function (yes) {
			if (!yes) {
				/* Taken to the first of them, to check it. */
				var first = field(names[0]);
				var panel = first.closest(".a3s-wizard__panel.is-collapsed");
				if (panel) { var t = panel.querySelector(".a3s-edit__toggle"); if (t) t.click(); }
				first.scrollIntoView({ block: "center" });
				first.focus({ preventScroll: true });
				return;
			}
			/* Checked: not asked again for these, unless more are read. */
			fresh = {};
			passing = true;
			try { form.requestSubmit(by || undefined); } finally { passing = false; }
		});
	}, true);
})();
