/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The portal's record edit form - the Lead page and every collection edit page. The
 * form names its own endpoint (and collection slug) in data attributes. The sections are long cards down the left; the step bar above
 * them tracks which one is in view and scrolls to a section when its step is clicked.
 * Every control is in the one form, so a save posts all of them. Gathers every named control, posts them
 * with the lead's name to update_lead, and does no validation of its own beyond a
 * courtesy check - the server validates against the doctype and is the only thing that
 * decides what is written.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-lead-edit-form") || document.getElementById("a3s-record-edit-form");
	if (!form) return;

	var name = form.dataset.name;
	var slug = form.dataset.slug || "";
	var endpoint = form.dataset.endpoint || "a3_sola.api.leads.update_lead";
	var viewRoute = form.dataset.view || "/a3solaportal/leads";
	var submits = Array.prototype.slice.call(form.querySelectorAll("[data-submit]"));
	var statuses = Array.prototype.slice.call(form.querySelectorAll("[data-status]"));
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var submitLabel = submits.length ? submits[0].textContent : "Save changes";

	/* ---------------------------------------------------------------- steps */
	var steps = Array.prototype.slice.call(form.querySelectorAll(".a3s-wizard__step"));
	var panels = Array.prototype.slice.call(form.querySelectorAll(".a3s-wizard__panel"));
	var nav = form.querySelector(".a3s-edit__nav");
	var fill = document.getElementById("a3s-wizard-fill");
	var current = -1;
	var scrollingTo = null;

	function controls(root) {
		return Array.prototype.filter.call(root.querySelectorAll("input, select, textarea"), function (el) {
			return el.name;
		});
	}

	function isFilled(el) {
		if (el.type === "checkbox") return el.checked;
		return String(el.value || "").trim() !== "";
	}

	/* The offset a section should stop at when scrolled to: below the fixed top bar
	   and the sticky step bar. */
	function topOffset() {
		var bar = nav ? nav.getBoundingClientRect().height : 0;
		var top = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--a3s-topbar-h")) || 64;
		return top + bar + 24;
	}

	function setCurrent(index) {
		if (index === current || index < 0 || index >= steps.length) return;
		current = index;
		steps.forEach(function (step, i) {
			var tab = step.querySelector("[role=tab]");
			step.classList.toggle("is-current", i === index);
			step.classList.toggle("is-done", i < index);
			tab.setAttribute("aria-selected", i === index ? "true" : "false");
			tab.setAttribute("tabindex", i === index ? "0" : "-1");
		});
		if (fill) fill.style.width = (steps.length > 1 ? (index / (steps.length - 1)) * 100 : 100) + "%";
	}

	function goTo(index, focusTab, instant) {
		var panel = panels[index];
		if (!panel) return;
		scrollingTo = index;
		setCurrent(index);
		var y = panel.getBoundingClientRect().top + window.pageYOffset - topOffset();
		window.scrollTo({ top: Math.max(y, 0), behavior: instant ? "auto" : "smooth" });
		try { history.replaceState(null, "", "#" + steps[index].dataset.key); } catch (e) { /* no-op */ }
		if (focusTab) steps[index].querySelector("[role=tab]").focus();
		/* Let the smooth scroll land before the scroll-spy takes over again. */
		clearTimeout(goTo.timer);
		goTo.timer = setTimeout(function () { scrollingTo = null; }, 700);
	}

	/* Scroll-spy: the current section is the last one whose top has passed the bar. */
	function spy() {
		if (scrollingTo !== null) return;
		var line = topOffset() + 8;
		var index = 0;
		panels.forEach(function (panel, i) {
			if (panel.getBoundingClientRect().top <= line) index = i;
		});
		/* At the very bottom the last section counts, even if it is short. */
		if (window.innerHeight + window.pageYOffset >= document.documentElement.scrollHeight - 2) index = panels.length - 1;
		setCurrent(index);
	}

	var ticking = false;
	window.addEventListener("scroll", function () {
		if (ticking) return;
		ticking = true;
		requestAnimationFrame(function () { spy(); ticking = false; });
	}, { passive: true });

	steps.forEach(function (step, i) {
		var tab = step.querySelector("[role=tab]");
		tab.addEventListener("click", function () { goTo(i, false); });
		tab.addEventListener("keydown", function (event) {
			var to = null;
			if (event.key === "ArrowRight" || event.key === "ArrowDown") to = Math.min(i + 1, steps.length - 1);
			if (event.key === "ArrowLeft" || event.key === "ArrowUp") to = Math.max(i - 1, 0);
			if (event.key === "Home") to = 0;
			if (event.key === "End") to = steps.length - 1;
			if (to === null) return;
			event.preventDefault();
			goTo(to, true);
		});
	});

	/* "3 of 8 filled" under each step, and a done tick once a step is fully filled. */
	function refreshCounts() {
		panels.forEach(function (panel, i) {
			var all = controls(panel);
			var done = all.filter(isFilled).length;
			var step = steps[i];
			var count = step.querySelector("[data-count]");
			if (count) count.textContent = done + " of " + all.length + " filled";
			step.classList.toggle("is-complete", all.length > 0 && done === all.length);
		});
	}
	form.addEventListener("input", refreshCounts);
	form.addEventListener("change", refreshCounts);
	refreshCounts();

	var wanted = (location.hash || "").replace("#", "");
	var start = steps.findIndex(function (s) { return s.dataset.key === wanted; });
	/* A hashed section on load is a plain jump; smooth scrolling is for clicks. The web
	   font lands after first paint and moves everything, so jump again once it has. */
	if (start > 0) goTo(start, false, true); else spy();
	if (start > 0 && document.fonts && document.fonts.ready) {
		document.fonts.ready.then(function () { goTo(start, false, true); });
	}

	/* ----------------------------------------------------------------- save */
	function setStatus(text, kind) {
		statuses.forEach(function (status) {
			status.textContent = text || "";
			status.classList.toggle("is-error", kind === "error");
			status.classList.toggle("is-success", kind === "success");
		});
	}

	function markInvalid(id, invalid) {
		var field = document.getElementById("f-" + id);
		if (field) field.classList.toggle("a3s-field--error", invalid);
	}

	function busy(on) {
		submits.forEach(function (btn) {
			btn.disabled = on;
			btn.textContent = on ? "Saving…" : submitLabel;
		});
	}

	function value(fieldname) {
		var el = form.elements[fieldname];
		return el && typeof el.value === "string" ? el.value.trim() : "";
	}

	function stepFor(fieldname) {
		var el = form.elements[fieldname];
		var panel = el && el.closest ? el.closest(".a3s-wizard__panel") : null;
		return panel ? Number(panel.dataset.step) : 0;
	}

	function collect() {
		var out = { name: name };
		if (slug) out.slug = slug;
		Array.prototype.forEach.call(form.elements, function (el) {
			if (!el.name) return;
			if (el.type === "checkbox") out[el.name] = el.checked ? "1" : "0";
			else out[el.name] = el.value;
		});
		return out;
	}

	/* Pull the human-readable text out of Frappe's _server_messages envelope. */
	function serverMessage(data) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (!msgs.length) return "";
			var first = JSON.parse(msgs[0]);
			return (first && first.message) ? String(first.message).replace(/<[^>]*>/g, "") : "";
		} catch (e) {
			return "";
		}
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		markInvalid("lead_name", false);
		markInvalid("company_name", false);

		/* Same rule the server enforces, checked here only to spare a round trip. */
		if (form.elements.lead_name && form.elements.company_name && !value("lead_name") && !value("company_name")) {
			goTo(stepFor("lead_name"), false);
			markInvalid("lead_name", true);
			markInvalid("company_name", true);
			setStatus("Enter a lead name or a company name.", "error");
			form.elements.lead_name.focus({ preventScroll: true });
			return;
		}

		busy(true);
		setStatus("Saving…");

		fetch("/api/method/" + endpoint, {
			method: "POST",
			credentials: "same-origin",
			headers: {
				"Content-Type": "application/json",
				"Accept": "application/json",
				"X-Frappe-CSRF-Token": csrf
			},
			body: JSON.stringify(collect())
		}).then(function (response) {
			return response.json().catch(function () { return {}; })
				.then(function (data) { return { ok: response.ok, code: response.status, data: data }; });
		}).then(function (result) {
			if (result.ok && result.data && result.data.message) {
				setStatus("Saved. Taking you back…", "success");
				window.location.assign(result.data.message.route || viewRoute);
				return;
			}
			busy(false);
			if (result.code === 403) {
				setStatus("You do not have permission to change this record.", "error");
				return;
			}
			setStatus(serverMessage(result.data) || "Could not save. Check the fields and try again.", "error");
		}).catch(function () {
			busy(false);
			setStatus("Could not reach the server. Check your connection and try again.", "error");
		});
	});
})();
