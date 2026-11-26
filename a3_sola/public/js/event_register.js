/* The page an event's QR code opens (www/register): the visitor's details, their papers if
   they have them, then the thank-you with their instant estimate, their proposal and our
   WhatsApp (a3_sola.api.event_registration). */
(function () {
	"use strict";

	var form = document.querySelector("[data-reg-form]");
	if (!form) return;
	var boot = JSON.parse(document.getElementById("a3s-reg-data").textContent);
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var statusEl = form.querySelector("[data-status]");
	var steps = [].slice.call(form.querySelectorAll("[data-step]"));
	var tabs = [].slice.call(form.querySelectorAll("[data-tab]"));
	var step = 1;
	var ref = "";       // the lead tab 1 saved, signed: Register updates it
	var savedKey = "";  // what tab 1 last saved, so going back and on again does not save twice
	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
	/* Phone photos are large: anything over this is redrawn smaller before it is sent. */
	var SHRINK_OVER = 1.5 * 1024 * 1024;
	var MAX_SIDE = 2000;

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}
	function serverMessage(body) {
		try {
			var msgs = JSON.parse((body && body._server_messages) || "[]");
			if (msgs.length) return String(JSON.parse(msgs[0]).message || "").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (body && body.exception) ? String(body.exception).split(":").slice(1).join(":").trim() : "";
	}
	function setStatus(text, tone) {
		statusEl.textContent = text || "";
		statusEl.dataset.tone = tone || "";
		statusEl.hidden = !text;
	}
	function showStep(n) {
		step = n;
		steps.forEach(function (s) { s.hidden = Number(s.dataset.step) !== n; });
		tabs.forEach(function (t) {
			var i = Number(t.dataset.tab);
			t.classList.toggle("is-on", i === n);
			t.classList.toggle("is-done", i < n);
		});
		setStatus("");
		window.scrollTo({ top: 0, behavior: "smooth" });
	}

	/* ------------------------------------------------------------------ step 1 */
	var other = form.querySelector("[data-other-whatsapp]");
	var waField = form.querySelector("[data-whatsapp-field]");
	other.addEventListener("change", function () {
		waField.hidden = !other.checked;
		if (other.checked) waField.querySelector("input").focus();
		else waField.querySelector("input").value = "";
	});

	function digits(v) { return String(v || "").replace(/\D/g, "").replace(/^(91|0)(?=\d{10}$)/, ""); }
	function mobileOk(v) { return /^[6-9]\d{9}$/.test(digits(v)); }
	function fieldError(input, message) {
		var field = input.closest(".a3s-field") || input.closest("label");
		if (field) field.classList.add("a3s-field--error");
		setStatus(message, "error");
		input.focus();
		return false;
	}
	function checkStep1() {
		form.querySelectorAll(".a3s-field--error").forEach(function (f) { f.classList.remove("a3s-field--error"); });
		if (form.full_name.value.trim().length < 2) return fieldError(form.full_name, "Enter your name.");
		if (!mobileOk(form.mobile_no.value)) return fieldError(form.mobile_no, "Enter your 10-digit mobile number.");
		if (other.checked && !mobileOk(form.whatsapp_no.value)) return fieldError(form.whatsapp_no, "Enter your 10-digit WhatsApp number.");
		if (!form.district.value) return fieldError(form.district, "Choose your district.");
		return true;
	}
	function clearErrors() { form.querySelectorAll(".a3s-field--error").forEach(function (f) { f.classList.remove("a3s-field--error"); }); }
	function checkStep2() {
		clearErrors();
		var bill = form.bill_amount.value;
		if (bill && (Number(bill) < 0 || Number(bill) > 1000000)) return fieldError(form.bill_amount, "Enter the bill amount in rupees.");
		return true;
	}
	function checkStep3() {
		clearErrors();
		if (!form.whatsapp_consent.checked) return fieldError(form.whatsapp_consent, "Tick the box to agree to hear from us on WhatsApp.");
		return true;
	}

	/* ------------------------------------------------------------------ step 2: the papers */
	form.querySelectorAll("[data-doc]").forEach(function (box) {
		var input = box.querySelector("input");
		input.addEventListener("change", function () {
			var f = input.files && input.files[0];
			box.classList.toggle("is-set", !!f);
			box.querySelector("[data-doc-name]").textContent = f ? f.name : "Photo or PDF";
			box.querySelector(".a3s-reg__doc-ic").textContent = f ? "✓" : "+";
		});
	});
	form.querySelectorAll("[data-back]").forEach(function (b) {
		b.addEventListener("click", function () { showStep(Math.max(1, step - 1)); });
	});

	/* A photo redrawn as a JPEG at most MAX_SIDE across - a 5 MB phone photo becomes a few
	   hundred KB, and still reads. A PDF, or a small photo, goes as it is. */
	function shrink(file) {
		if (!file || !/^image\//.test(file.type) || file.size <= SHRINK_OVER || !window.createImageBitmap) return Promise.resolve(file);
		return createImageBitmap(file).then(function (img) {
			var scale = Math.min(1, MAX_SIDE / Math.max(img.width, img.height));
			var canvas = document.createElement("canvas");
			canvas.width = Math.round(img.width * scale);
			canvas.height = Math.round(img.height * scale);
			canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
			return new Promise(function (resolve) {
				canvas.toBlob(function (blob) {
					resolve(blob ? new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : file);
				}, "image/jpeg", 0.82);
			});
		}).catch(function () { return file; });
	}

	function captchaToken() {
		var box = form.querySelector("[data-captcha]");
		if (!box) return Promise.resolve("");
		if (box.dataset.provider === "Cloudflare Turnstile") {
			var t = form.querySelector('[name="cf-turnstile-response"]');
			return Promise.resolve(t ? t.value : "");
		}
		if (window.grecaptcha && window.grecaptcha.execute) {
			return new Promise(function (resolve) {
				window.grecaptcha.ready(function () {
					window.grecaptcha.execute(box.dataset.siteKey, { action: "register" }).then(resolve, function () { resolve(""); });
				});
			});
		}
		return Promise.resolve("");
	}

	/* ------------------------------------------------------------------ sending */
	var busy = false;
	function setBusy(on) {
		busy = on;
		form.querySelectorAll("button").forEach(function (b) { b.disabled = on; });
		var btn = form.querySelector('[data-step="' + step + '"] .a3s-reg__submit');
		if (btn) {
			btn.classList.toggle("is-busy", on);
			btn.querySelector("span").textContent = on ? (step === 1 ? "Saving…" : "Registering…") : (step === 3 ? "Register" : "Next");
		}
	}
	function send() {
		if (busy) return;
		setBusy(true);
		setStatus("");
		var data = new FormData();
		["key", "website_url", "full_name", "mobile_no", "whatsapp_no", "district", "bill_amount", "system_type"].forEach(function (k) {
			if (form[k]) data.append(k, form[k].value);
		});
		["interest", "bill_months", "call_time"].forEach(function (k) {
			var on = form.querySelector('[name="' + k + '"]:checked');
			if (on) data.append(k, on.value);
		});
		data.append("whatsapp_consent", form.whatsapp_consent.checked ? "1" : "0");
		data.append("show_on_screen", form.show_on_screen.checked ? "1" : "0");
		if (ref) data.append("ref", ref);
		var files = [].slice.call(form.querySelectorAll('[data-doc] input[type="file"]')).filter(function (i) {
			return i.files && i.files[0];
		});
		Promise.all(files.map(function (i) { return shrink(i.files[0]).then(function (f) { data.append(i.name, f, f.name); }); }))
			.then(captchaToken)
			.then(function (token) {
				if (token) data.append("captcha_token", token);
				var headers = { "Accept": "application/json" };
				if (csrf) headers["X-Frappe-CSRF-Token"] = csrf;
				return fetch("/api/method/a3_sola.api.event_registration.submit", { method: "POST", credentials: "same-origin", headers: headers, body: data });
			})
			.then(function (r) {
				return r.json().catch(function () { return {}; }).then(function (body) {
					if (!r.ok) {
						throw new Error(serverMessage(body) || (r.status === 429 ? "Too many attempts. Please wait a little and try again."
							: r.status === 413 ? "The files are too large together. Add fewer, or smaller photos." : "That did not go through. Try again."));
					}
					return body.message;
				});
			})
			.then(done)
			.catch(function (err) {
				setBusy(false);
				setStatus(err && err.message && err.message !== "Failed to fetch" ? err.message
					: "Could not reach the server. Check your connection and try again.", "error");
			});
	}

	/* Tab 1's Next: the lead is saved now (the stall screen says they have just scanned), then tab 2. */
	function contactKey() {
		return [form.full_name.value.trim(), digits(form.mobile_no.value), other.checked ? digits(form.whatsapp_no.value) : "",
			form.district.value, form.show_on_screen.checked ? 1 : 0].join("|");
	}
	function saveContact() {
		if (busy) return;
		if (ref && savedKey === contactKey()) { showStep(2); return; }
		setBusy(true);
		setStatus("");
		var data = new FormData();
		["key", "website_url", "full_name", "mobile_no", "whatsapp_no", "district"].forEach(function (k) {
			if (form[k]) data.append(k, form[k].value);
		});
		data.append("show_on_screen", form.show_on_screen.checked ? "1" : "0");
		captchaToken().then(function (token) {
			if (token) data.append("captcha_token", token);
			var headers = { "Accept": "application/json" };
			if (csrf) headers["X-Frappe-CSRF-Token"] = csrf;
			return fetch("/api/method/a3_sola.api.event_registration.start", { method: "POST", credentials: "same-origin", headers: headers, body: data });
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 429 ? "Too many attempts. Please wait a little and try again." : "That did not go through. Try again."));
				return body.message || {};
			});
		}).then(function (m) {
			ref = m.ref || "";
			savedKey = contactKey();
			setBusy(false);
			showStep(2);
		}).catch(function (err) {
			setBusy(false);
			setStatus(err && err.message && err.message !== "Failed to fetch" ? err.message
				: "Could not reach the server. Check your connection and try again.", "error");
		});
	}

	form.addEventListener("submit", function (e) {
		e.preventDefault();
		if (step === 1) { if (checkStep1()) saveContact(); return; }
		if (step === 2) { if (checkStep2()) showStep(3); return; }
		if (checkStep3()) send();
	});

	/* ------------------------------------------------------------------ thank you */
	function done(r) {
		var box = document.querySelector("[data-done]");
		form.hidden = true;
		box.hidden = false;
		var first = (r && r.first_name) || form.full_name.value.trim().split(/\s+/)[0];
		box.querySelector("[data-done-title]").textContent = "Thank you, " + first + "!";
		box.querySelector("[data-done-lead]").textContent = r && r.proposal_url
			? "You are registered. Your solar proposal is ready below, and our team will send it on WhatsApp and call you soon."
			: "You are registered. Our team will send you our offer on WhatsApp and call you soon.";
		var est = r && r.estimate;
		var estBox = box.querySelector("[data-estimate]");
		if (est && est.custom) {
			/* No package covers it: a size range and a price, and our engineer designs the rest. */
			estBox.innerHTML = '<p class="a3s-reg__est-head">Your indicative estimate</p>' +
				'<dl class="a3s-reg__est-rows">' + [["Estimated capacity", est.kw_min + "\u2013" + est.kw_max + " kW"],
					["Estimated price", "about " + money.format(est.price)]].map(function (row, i) {
					return '<div class="a3s-reg__est-row" style="--i:' + i + '"><dt>' + esc(row[0]) + "</dt><dd>" + esc(row[1]) + "</dd></div>";
				}).join("") + "</dl>" +
				'<p class="a3s-field__hint">Your energy needs call for a custom-designed solar system. Our engineer will carry out a site survey and prepare a tailored design and proposal for you. Our team will be in touch shortly to schedule the visit.</p>';
			estBox.hidden = false;
		} else if (est) {
			var rows = [["System size", est.kw + " kW"], ["Price", money.format(est.price)]];
			if (est.subsidy) {
				rows.push(["Government subsidy", "− " + money.format(est.subsidy)]);
				rows.push(["Effective Price After Subsidy", money.format(est.net)]);
			}
			if (est.monthly_saving) rows.push(["You save", "about " + money.format(est.monthly_saving) + " a month"]);
			if (est.payback_years) rows.push(["Pays for itself in", "about " + est.payback_years + " years"]);
			estBox.innerHTML = '<p class="a3s-reg__est-head">Your indicative estimate</p>' +
				'<dl class="a3s-reg__est-rows">' + rows.map(function (row, i) {
					return '<div class="a3s-reg__est-row' + (row[0] === "Effective Price After Subsidy" ? " is-total" : "") + '" style="--i:' + i + '"><dt>' + esc(row[0]) + "</dt><dd>" + esc(row[1]) + "</dd></div>";
				}).join("") + "</dl>" +
				(est.battery ? '<p class="a3s-field__hint">For an off-grid or hybrid system our engineer designs the battery and confirms the price; the PM Surya Ghar subsidy is for on-grid systems.</p>' : "") +
				'<p class="a3s-field__hint">Indicative only &ndash; our engineer will confirm it after a site visit.</p>';
			estBox.hidden = false;
		}
		var actions = [];
		if (r && r.proposal_url && !(est && est.custom)) {
			actions.push('<a class="a3s-btn a3s-btn--primary" href="' + esc(r.proposal_url) + '" target="_blank" rel="noopener"><span>Download your proposal</span></a>');
		}
		if (r && r.chat_url) {
			actions.push('<a class="a3s-btn a3s-btn--secondary a3s-reg__wa" href="' + esc(r.chat_url) + '" target="_blank" rel="noopener">' +
				'<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 18.2c-1.5 0-3-.4-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.3-.4.3-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3c-.2.3-.9.9-.9 2.2s.9 2.5 1 2.7c.1.2 1.8 2.8 4.4 3.9 1.6.7 2.3.8 3.1.6.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2-.1-.1-.3-.2-.5-.3z"/></svg>' +
				"<span>Chat with us on WhatsApp</span></a>");
		}
		box.querySelector("[data-done-actions]").innerHTML = actions.join("");
		box.focus();
		window.scrollTo({ top: 0, behavior: "smooth" });
	}
})();
