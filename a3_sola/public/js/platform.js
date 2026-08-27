/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * a3 sola public site behaviour. Vanilla, no dependencies, no CDN.
 * Everything here degrades: with JS off the page still reads and every link still works.
 */
(function () {
	"use strict";

	var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

	/* ------------------------------------------------------------ analytics */
	function track(event, payload) {
		window.dataLayer = window.dataLayer || [];
		window.dataLayer.push(Object.assign({ event: event }, payload || {}));
	}
	window.a3sTrack = track;

	/* --------------------------------------------------------- sticky header */
	function stickyHeader() {
		var header = document.getElementById("a3s-header");
		if (!header) return;
		var apply = function () {
			header.classList.toggle("is-scrolled", window.scrollY > 40);
		};
		apply();
		window.addEventListener("scroll", apply, { passive: true });
	}

	/* -------------------------------------------------------------- mobile nav */
	function mobileNav() {
		var burger = document.getElementById("a3s-burger");
		var panel = document.getElementById("a3s-mobile-nav");
		var backdrop = document.getElementById("a3s-backdrop");
		if (!burger || !panel) return;

		var lastFocused = null;

		function focusable() {
			return panel.querySelectorAll("a[href], button:not([disabled])");
		}

		function open() {
			lastFocused = document.activeElement;
			panel.hidden = false;
			if (backdrop) backdrop.hidden = false;
			// Next frame, so the transition actually runs from the closed position.
			requestAnimationFrame(function () {
				panel.classList.add("is-open");
				if (backdrop) backdrop.classList.add("is-open");
			});
			burger.setAttribute("aria-expanded", "true");
			burger.setAttribute("aria-label", "Close menu");
			document.body.style.overflow = "hidden";
			var first = focusable()[0];
			if (first) first.focus();
		}

		function close() {
			panel.classList.remove("is-open");
			if (backdrop) backdrop.classList.remove("is-open");
			burger.setAttribute("aria-expanded", "false");
			burger.setAttribute("aria-label", "Open menu");
			document.body.style.overflow = "";
			window.setTimeout(function () {
				panel.hidden = true;
				if (backdrop) backdrop.hidden = true;
			}, reduceMotion ? 0 : 250);
			if (lastFocused) lastFocused.focus();
		}

		burger.addEventListener("click", function () {
			if (burger.getAttribute("aria-expanded") === "true") close();
			else open();
		});
		if (backdrop) backdrop.addEventListener("click", close);
		panel.addEventListener("click", function (e) {
			if (e.target.tagName === "A") close();
		});

		document.addEventListener("keydown", function (e) {
			if (burger.getAttribute("aria-expanded") !== "true") return;
			if (e.key === "Escape") {
				close();
				return;
			}
			// Trap focus: a menu you can tab out of behind a backdrop is a trap of its own.
			if (e.key !== "Tab") return;
			var items = focusable();
			if (!items.length) return;
			var first = items[0];
			var last = items[items.length - 1];
			if (e.shiftKey && document.activeElement === first) {
				e.preventDefault();
				last.focus();
			} else if (!e.shiftKey && document.activeElement === last) {
				e.preventDefault();
				first.focus();
			}
		});
	}

	/* ------------------------------------------------------------ scroll reveal */
	function reveal() {
		var items = document.querySelectorAll(".a3s-reveal");
		if (!items.length) return;
		if (reduceMotion || !("IntersectionObserver" in window)) {
			items.forEach(function (el) { el.classList.add("is-visible"); });
			return;
		}
		var observer = new IntersectionObserver(function (entries) {
			entries.forEach(function (entry) {
				if (!entry.isIntersecting) return;
				entry.target.classList.add("is-visible");
				observer.unobserve(entry.target);
			});
		}, { rootMargin: "0px 0px -10% 0px", threshold: 0.05 });
		items.forEach(function (el) { observer.observe(el); });
	}

	/* ---------------------------------------------------------- anchor scrolling */
	function anchors() {
		var header = document.getElementById("a3s-header");
		document.addEventListener("click", function (e) {
			var link = e.target.closest('a[href^="#"]');
			if (!link) return;
			var id = link.getAttribute("href").slice(1);
			if (!id) return;
			var target = document.getElementById(id);
			if (!target) return;
			e.preventDefault();
			var offset = (header ? header.offsetHeight : 0) + 16;
			var top = target.getBoundingClientRect().top + window.scrollY - offset;
			window.scrollTo({ top: top, behavior: reduceMotion ? "auto" : "smooth" });
			history.replaceState(null, "", "#" + id);
		});
	}

	/* ------------------------------------------------------------- pricing cycle */
	function pricingToggle() {
		var toggles = document.querySelectorAll("[data-cycle-toggle]");
		if (!toggles.length) return;

		function apply(cycle) {
			document.querySelectorAll("[data-cycle-toggle] button").forEach(function (btn) {
				var active = btn.dataset.cycle === cycle;
				btn.classList.toggle("is-active", active);
				btn.setAttribute("aria-pressed", active ? "true" : "false");
			});
			// Prices, sub-lines and the comparison table all switch together.
			document.querySelectorAll("[data-price-monthly]").forEach(function (el) {
				el.textContent = cycle === "annual"
					? el.dataset.priceAnnual
					: el.dataset.priceMonthly;
			});
			document.querySelectorAll("[data-suffix]").forEach(function (el) {
				el.textContent = cycle === "annual" ? "/year" : "/month";
			});
			document.querySelectorAll("[data-subline-monthly]").forEach(function (el) {
				el.textContent = cycle === "annual"
					? el.dataset.sublineAnnual
					: el.dataset.sublineMonthly;
			});
			document.querySelectorAll("[data-impl-monthly]").forEach(function (el) {
				el.textContent = cycle === "annual"
					? el.dataset.implAnnual
					: el.dataset.implMonthly;
			});
			// Every CTA carries the selected cycle through to the signup form.
			document.querySelectorAll("a[data-cta-plan]").forEach(function (link) {
				link.href = "/get-started?package=" + encodeURIComponent(link.dataset.ctaPlan) +
					"&cycle=" + cycle;
			});
			document.documentElement.setAttribute("data-billing-cycle", cycle);
			track("pricing_toggle", { cycle: cycle });
		}

		toggles.forEach(function (group) {
			group.addEventListener("click", function (e) {
				var btn = e.target.closest("button[data-cycle]");
				if (btn) apply(btn.dataset.cycle);
			});
		});

		var params = new URLSearchParams(window.location.search);
		apply(params.get("cycle") === "annual" ? "annual" : "monthly");
	}

	/* --------------------------------------------------------------- accordion */
	function accordion() {
		document.querySelectorAll("[data-accordion] button").forEach(function (btn) {
			btn.addEventListener("click", function () {
				var expanded = btn.getAttribute("aria-expanded") === "true";
				btn.setAttribute("aria-expanded", expanded ? "false" : "true");
				var panel = document.getElementById(btn.getAttribute("aria-controls"));
				if (panel) panel.hidden = expanded;
			});
		});
	}

	/* ------------------------------------------------------- declared analytics */
	function declaredEvents() {
		document.querySelectorAll("[data-analytics]").forEach(function (el) {
			el.addEventListener("click", function () {
				track(el.dataset.analytics, {
					source: el.dataset.analyticsSource || null,
					plan: el.dataset.ctaPlan || null
				});
			});
		});
	}

	function init() {
		stickyHeader();
		mobileNav();
		reveal();
		anchors();
		pricingToggle();
		accordion();
		declaredEvents();
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
