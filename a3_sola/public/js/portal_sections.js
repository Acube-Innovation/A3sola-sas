/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Collapsible sections on a record's view page, as on its edit page: each section opens
 * and closes from its heading, one open at a time, and all start closed so the page opens
 * short. A link to a section (#sec-...) opens it. The edit form has its own copy of this
 * in portal_record_edit.js, tied to its step bar; this one is for pages without a form.
 */
(function () {
	"use strict";

	var panels = Array.prototype.slice.call(document.querySelectorAll("[data-collapsible]"));
	if (!panels.length) return;

	function setOpen(panel, open) {
		panels.forEach(function (p) {
			var isThis = p === panel;
			var show = isThis ? open : (open ? false : !p.classList.contains("is-collapsed"));
			var toggle = p.querySelector(".a3s-edit__toggle");
			var body = p.querySelector(".a3s-edit__body");
			if (!toggle || !body) return;
			p.classList.toggle("is-collapsed", !show);
			body.hidden = !show;
			toggle.setAttribute("aria-expanded", show ? "true" : "false");
		});
	}

	panels.forEach(function (panel) {
		var toggle = panel.querySelector(".a3s-edit__toggle");
		if (toggle) toggle.addEventListener("click", function () { setOpen(panel, panel.classList.contains("is-collapsed")); });
	});

	function openFromHash() {
		var id = (location.hash || "").replace("#", "");
		var panel = id && panels.find(function (p) { return p.id === id; });
		if (!panel) return;
		setOpen(panel, true);
		panel.scrollIntoView({ block: "start" });
	}
	window.addEventListener("hashchange", openFromHash);
	openFromHash();
})();
