/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The signup form. Client-side validation is a courtesy to the visitor; the server
 * validates everything again and is the only thing that decides.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-signup-form");
	if (!form) return;

	var STORAGE_KEY = "a3s-signup-draft";
	var cycle = form.dataset.selectedCycle === "annual" ? "annual" : "monthly";
	var quote = null;
	var step = 1;

	/* ------------------------------------------------------------ attribution */
	function captureAttribution() {
		var params = new URLSearchParams(window.location.search);
		["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"].forEach(function (key) {
			var field = form.querySelector('[name="' + key + '"]');
			if (field) field.value = params.get(key) || "";
		});
		var referrer = form.querySelector('[name="referrer_url"]');
		if (referrer) referrer.value = document.referrer || "";
		var landing = form.querySelector('[name="landing_page"]');
		if (landing) landing.value = window.location.pathname + window.location.search;
	}

	/* ------------------------------------------------- keep what they typed */
	function saveDraft() {
		try {
			var data = {};
			new FormData(form).forEach(function (value, key) {
				if (key !== "website_url") data[key] = value;
			});
			data._cycle = cycle;
			sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
		} catch (e) {
			/* A private window without storage is not a reason to break the form. */
		}
	}

	function restoreDraft() {
		try {
			var raw = sessionStorage.getItem(STORAGE_KEY);
			if (!raw) return;
			var data = JSON.parse(raw);
			Object.keys(data).forEach(function (key) {
				if (key === "_cycle") return;
				var field = form.querySelector('[name="' + key + '"]');
				if (!field) return;
				if (field.type === "checkbox") field.checked = !!data[key];
				else if (field.type !== "radio") field.value = data[key];
			});
			if (data.plan_code) {
				var radio = form.querySelector('[name="plan_code"][value="' + data.plan_code + '"]');
				if (radio) radio.checked = true;
			}
			if (data._cycle) cycle = data._cycle;
		} catch (e) {
			/* Ignore a corrupt draft rather than trapping the visitor on a broken form. */
		}
	}

	/* ----------------------------------------------------------------- steps */
	function showStep(target) {
		step = target;
		form.querySelectorAll(".a3s-step").forEach(function (fieldset) {
			var isCurrent = Number(fieldset.dataset.step) === target;
			fieldset.hidden = !isCurrent;
			fieldset.classList.toggle("is-current", isCurrent);
		});
		document.querySelectorAll("#a3s-steps li").forEach(function (item) {
			var index = Number(item.dataset.step);
			item.classList.toggle("is-current", index === target);
			item.classList.toggle("is-done", index < target);
		});
		if (target === 4) renderReview();
		window.scrollTo({ top: form.offsetTop - 100, behavior: "smooth" });
		if (window.a3sTrack) window.a3sTrack("signup_step_completed", { step: target - 1 });
	}

	function validateStep(target) {
		var fieldset = form.querySelector('.a3s-step[data-step="' + target + '"]');
		var ok = true;
		fieldset.querySelectorAll("[required]").forEach(function (field) {
			var wrapper = field.closest(".a3s-field");
			var valid = field.type === "checkbox" ? field.checked : field.checkValidity() && field.value.trim();
			if (wrapper) {
				wrapper.classList.toggle("a3s-field--error", !valid);
				var existing = wrapper.querySelector(".a3s-field__error");
				if (existing) existing.remove();
				if (!valid) {
					var message = document.createElement("span");
					message.className = "a3s-field__error";
					message.textContent = field.validationMessage || "This is required.";
					wrapper.appendChild(message);
				}
			}
			if (!valid && ok) field.focus();
			ok = ok && valid;
		});
		return ok;
	}

	/* --------------------------------------------------------------- pricing */
	function selectedPlan() {
		var checked = form.querySelector('[name="plan_code"]:checked');
		return checked ? checked.value : null;
	}

	function selectedCard() {
		var checked = form.querySelector('[name="plan_code"]:checked');
		return checked ? checked.closest(".a3s-pick") : null;
	}

	function refreshQuote() {
		var plan = selectedPlan();
		var card = selectedCard();
		var isCustom = card && card.dataset.custom === "1";

		document.getElementById("a3s-custom-note").hidden = !isCustom;
		document.getElementById("a3s-users").hidden = !!isCustom;
		form.querySelectorAll('[data-next="2"]').forEach(function (btn) {
			btn.disabled = !!isCustom;
		});
		if (isCustom || !plan) {
			renderSummary(null);
			return;
		}

		var users = Number(document.getElementById("a3s-users-input").value || 0);
		// The server is the single source of truth for price - the form never computes one.
		frappe.call({
			method: "a3_sola.api.platform.calculate_plan_total",
			args: { plan_code: plan, cycle: cycle, additional_users: users },
		}).then(function (response) {
			quote = response.message;
			renderSummary(quote);
		}).catch(function () {
			renderSummary(null);
		});
	}

	function money(value, currency) {
		try {
			return new Intl.NumberFormat("en-IN", {
				style: "currency", currency: currency || "INR", maximumFractionDigits: 0,
			}).format(value);
		} catch (e) {
			return String(value);
		}
	}

	function linesHtml(data) {
		return data.line_items.map(function (line) {
			var amount = line.waived
				? '<s>' + money(line.struck_amount, data.currency) + "</s> " + money(0, data.currency)
				: money(line.amount, data.currency);
			return '<div class="a3s-line"><span><strong>' + line.label + "</strong>" +
				(line.detail ? '<br><small>' + line.detail + "</small>" : "") +
				"</span><span>" + amount + "</span></div>";
		}).join("");
	}

	function renderSummary(data) {
		var lines = document.getElementById("a3s-summary-lines");
		var total = document.getElementById("a3s-summary-total");
		var note = document.getElementById("a3s-summary-note");
		if (!data) {
			lines.innerHTML = "";
			total.textContent = "—";
			note.textContent = "Enterprise is priced with our team.";
			return;
		}
		lines.innerHTML = linesHtml(data) +
			'<div class="a3s-line a3s-line--total"><span><strong>Total</strong></span><span>' +
			money(data.total_amount, data.currency) + "</span></div>";
		total.textContent = money(data.total_amount, data.currency);
		note.textContent = data.cycle === "annual"
			? data.total_users + " users, billed yearly. Implementation waived."
			: data.total_users + " users, billed monthly.";
	}

	function renderReview() {
		var target = document.getElementById("a3s-review-lines");
		if (!quote) {
			target.innerHTML = "<p>Choose a plan to see your order.</p>";
			return;
		}
		target.innerHTML = linesHtml(quote) +
			'<div class="a3s-line a3s-line--total"><span><strong>Total</strong></span><span>' +
			money(quote.total_amount, quote.currency) + "</span></div>";
	}

	/* ----------------------------------------------------------------- wiring */
	form.addEventListener("click", function (e) {
		var next = e.target.closest("[data-next]");
		if (next && !next.disabled) {
			if (validateStep(step)) {
				saveDraft();
				showStep(Number(next.dataset.next));
			}
			return;
		}
		var prev = e.target.closest("[data-prev]");
		if (prev) {
			showStep(Number(prev.dataset.prev));
			return;
		}
		var cycleBtn = e.target.closest("[data-cycle]");
		if (cycleBtn) {
			cycle = cycleBtn.dataset.cycle;
			form.querySelector('[name="billing_cycle"]').value = cycle;
			form.querySelectorAll("[data-cycle]").forEach(function (btn) {
				var active = btn.dataset.cycle === cycle;
				btn.setAttribute("aria-pressed", active ? "true" : "false");
				btn.classList.toggle("is-active", active);
			});
			form.querySelectorAll("[data-price-monthly]").forEach(function (el) {
				el.textContent = cycle === "annual" ? el.dataset.priceAnnual : el.dataset.priceMonthly;
			});
			form.querySelectorAll("[data-suffix]").forEach(function (el) {
				el.textContent = cycle === "annual" ? "/year" : "/month";
			});
			refreshQuote();
			return;
		}
		var stepper = e.target.closest("[data-users]");
		if (stepper) {
			var input = document.getElementById("a3s-users-input");
			var card = selectedCard();
			var max = card ? Number(card.dataset.maxUsers || 0) : 0;
			var included = card ? Number(card.dataset.includedUsers || 0) : 0;
			var value = Math.max(0, Number(input.value || 0) + Number(stepper.dataset.users));
			if (max && included + value > max) value = max - included;
			input.value = value;
			refreshQuote();
		}
	});

	form.addEventListener("change", function (e) {
		if (e.target.name === "plan_code") {
			refreshQuote();
			if (window.a3sTrack) window.a3sTrack("plan_selected", { plan: e.target.value, source: "signup" });
		}
		saveDraft();
	});

	document.getElementById("a3s-users-input").addEventListener("input", refreshQuote);

	form.addEventListener("submit", function (e) {
		e.preventDefault();
		if (!validateStep(4)) return;

		var status = form.querySelector(".a3s-form__status");
		var button = form.querySelector('button[type="submit"]');
		var payload = {};
		new FormData(form).forEach(function (value, key) { payload[key] = value; });
		payload.accepted_terms = form.querySelector("#accepted_terms").checked ? 1 : 0;
		payload.marketing_consent = form.querySelector("#marketing_consent").checked ? 1 : 0;
		payload.billing_cycle = cycle === "annual" ? "Annual" : "Monthly";

		button.disabled = true;
		status.className = "a3s-form__status";
		status.textContent = "Creating your account…";

		frappe.call({ method: "a3_sola.api.signup.submit_signup", args: { payload: payload } })
			.then(function (response) {
				var result = response.message || {};
				try { sessionStorage.removeItem(STORAGE_KEY); } catch (err) {}
				window.location.href = result.next || "/get-started/check-email";
			})
			.catch(function (err) {
				button.disabled = false;
				status.className = "a3s-form__status is-error";
				status.textContent = (err && err.message) ||
					"We could not complete that. Please check your details and try again.";
			});
	});

	captureAttribution();
	restoreDraft();
	form.querySelectorAll("[data-cycle]").forEach(function (btn) {
		var active = btn.dataset.cycle === cycle;
		btn.setAttribute("aria-pressed", active ? "true" : "false");
		btn.classList.toggle("is-active", active);
	});
	if (cycle === "annual") {
		form.querySelectorAll("[data-price-monthly]").forEach(function (el) {
			el.textContent = el.dataset.priceAnnual;
		});
		form.querySelectorAll("[data-suffix]").forEach(function (el) { el.textContent = "/year"; });
	}
	showStep(1);
	refreshQuote();
})();
