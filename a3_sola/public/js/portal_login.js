/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The portal sign-in form. It posts to Frappe's own /api/method/login and does no
 * authentication of its own - rate limiting, lockout and password policy all live on
 * the server, and a second implementation here could only ever disagree with them.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-login-form");
	if (!form) return;

	var usr = document.getElementById("a3s-login-usr");
	var pwd = document.getElementById("a3s-login-pwd");
	var usrField = document.getElementById("a3s-login-usr-field");
	var pwdField = document.getElementById("a3s-login-pwd-field");
	var submit = document.getElementById("a3s-login-submit");
	var status = document.getElementById("a3s-login-status");

	/* One message for a wrong password and for an address that has no account. Telling
	   the two apart would turn this form into a way to enumerate who has an account. */
	var REFUSED = "Those details did not match an account.";

	function setStatus(text, kind) {
		status.textContent = text || "";
		status.classList.toggle("is-error", kind === "error");
		status.classList.toggle("is-success", kind === "success");
	}

	function markInvalid(invalid) {
		usrField.classList.toggle("a3s-field--error", invalid);
		pwdField.classList.toggle("a3s-field--error", invalid);
		usr.setAttribute("aria-invalid", invalid ? "true" : "false");
		pwd.setAttribute("aria-invalid", invalid ? "true" : "false");
	}

	function busy(isBusy) {
		submit.disabled = isBusy;
		submit.textContent = isBusy ? "Signing in…" : "Sign in";
	}

	/* Only ever follow a path on this site. The server applies the same rule to the
	   redirect-to it renders; this repeats it because the value also passes through
	   the DOM, where a stored-XSS bug elsewhere could otherwise redirect the visitor. */
	function safeRedirect(target) {
		if (!target || target.charAt(0) !== "/") return "";
		if (target.indexOf("//") === 0 || target.indexOf("/\\") === 0) return "";
		return target;
	}

	function landing() {
		// The portal dashboard is where a sign-in lands. Frappe's own home_page is
		// deliberately ignored - for a system user it is /app, which is the desk, not
		// this portal. An explicit, same-site redirect-to still wins (a deep link the
		// visitor was sent to before being asked to sign in).
		return safeRedirect(form.dataset.redirectTo) || "/a3solaportal/dashboard";
	}

	form.addEventListener("submit", function (event) {
		event.preventDefault();
		markInvalid(false);

		if (!usr.value.trim() || !pwd.value) {
			setStatus("Enter your email or username and your password.", "error");
			(usr.value.trim() ? pwd : usr).focus();
			return;
		}

		busy(true);
		setStatus("Signing in…");

		fetch("/api/method/login", {
			method: "POST",
			credentials: "same-origin",
			headers: { "Content-Type": "application/json", "Accept": "application/json" },
			body: JSON.stringify({ usr: usr.value.trim(), pwd: pwd.value })
		}).then(function (response) {
			return response.json().catch(function () {
				return {};
			}).then(function (payload) {
				return { ok: response.ok, statusCode: response.status, payload: payload };
			});
		}).then(function (result) {
			if (result.ok) {
				setStatus("Signed in. Taking you through…", "success");
				/* Leave the button disabled - the page is on its way out, and a second
				   submit while navigating would fire a pointless duplicate login. */
				window.location.assign(landing());
				return;
			}

			busy(false);
			pwd.value = "";
			if (result.statusCode === 429) {
				setStatus("Too many attempts. Wait a moment and try again.", "error");
				return;
			}
			if (result.statusCode === 401 || result.statusCode === 403) {
				markInvalid(true);
				setStatus(REFUSED, "error");
				usr.focus();
				return;
			}
			setStatus(
				(result.payload && result.payload.message) || "Something went wrong. Try again.",
				"error"
			);
		}).catch(function () {
			busy(false);
			setStatus("Could not reach the server. Check your connection and try again.", "error");
		});
	});
})();
