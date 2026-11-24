/* The Users page: an admin lists, adds, edits, disables or deletes users, resets their
   passwords and sends their welcome by WhatsApp or e-mail (a3_sola.api.portal_users). */
(function () {
	"use strict";

	var API = "a3_sola.api.portal_users.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var boot = JSON.parse(document.getElementById("a3s-users-data").textContent);
	var state = { users: boot.users, counts: boot.counts, total: boot.total, type: "", enabled: "active", q: "" };
	var choices = boot.choices;
	var rows = document.querySelector("[data-user-rows]");
	var empty = document.querySelector("[data-user-empty]");
	var pageStatus = document.querySelector("[data-page-status]");
	var TYPE_HINT = {
		Admin: "Runs the company's setup and this page.",
		Employee: "Staff: everything from the lead to the project's tasks.",
		Contractor: "Sees only the projects he is contractor on.",
		Dealer: "Sees only the customers he brought in."
	};
	var BADGE = { Admin: "a3s-badge--quotation", Employee: "a3s-badge--open", Contractor: "a3s-users__badge--contractor", Dealer: "a3s-badge--converted" };

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
	/* A method of this page's API by its short name, or any whitelisted method by its full path. */
	function call(method, args) {
		return fetch("/api/method/" + (method.indexOf(".") !== -1 ? method : API + method), {
			method: "POST", credentials: "same-origin",
			headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json", "Content-Type": "application/json" },
			body: JSON.stringify(args || {})
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
				return body.message;
			});
		});
	}
	function setStatus(el, text, tone) {
		el.textContent = text || "";
		el.dataset.tone = tone || "";
		el.hidden = !text;
	}
	function initials(name) {
		return String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join("").toUpperCase();
	}
	function busy(btn, on, label) {
		btn.disabled = on;
		btn.classList.toggle("is-busy", on);
		if (label) btn.querySelector("span") ? (btn.querySelector("span").textContent = label) : (btn.textContent = label);
	}

	/* ------------------------------------------------------------------ the list */
	function icon(name) { return '<svg class="a3s-ic" aria-hidden="true"><use href="#ic-' + name + '"></use></svg>'; }
	function render() {
		var q = state.q.toLowerCase();
		/* Each filter's counts are of the users the other filters and the search leave. */
		function matches(u, skip) {
			return (skip === "type" || !state.type || u.type === state.type) &&
				(skip === "enabled" || !state.enabled || (state.enabled === "active" ? u.enabled : !u.enabled)) &&
				(!q || [u.full_name, u.name, u.mobile_no, u.designation, u.department_name].join(" ").toLowerCase().indexOf(q) !== -1);
		}
		var list = state.users.filter(function (u) { return matches(u); });
		var byType = state.users.filter(function (u) { return matches(u, "type"); });
		var byStatus = state.users.filter(function (u) { return matches(u, "enabled"); });
		rows.innerHTML = list.map(function (u) {
			var job = [u.designation, u.department_name].filter(Boolean).map(esc).join(" &middot; ");
			var STAFF_ACCESS = { Admin: "Administration", Employee: "Full staff access" };
			var access = STAFF_ACCESS[u.type]
				? (job ? '<span class="a3s-users__job">' + job + '</span><span class="a3s-table__meta">' + STAFF_ACCESS[u.type] + "</span>" : STAFF_ACCESS[u.type]) +
					(u.needs_employee ? '<span class="a3s-table__meta a3s-users__missing">No Employee record: edit to add one</span>' : "")
				: u.type === "Contractor" ? (u.contractor ? esc(u.contractor.contractor_name) + '<span class="a3s-table__meta">' + esc(u.contractor.contractor_type || "") + " contractor</span>" : '<span class="a3s-table__muted">No contractor record</span>')
				: "Dealer";
			return '<tr data-user="' + esc(u.name) + '"' + (u.enabled ? "" : ' class="is-disabled"') + ">" +
				'<td><span class="a3s-table__record"><span class="a3s-avatar a3s-avatar--initials">' + esc(initials(u.full_name)) + "</span>" +
				'<span><span class="a3s-table__link">' + esc(u.full_name) + (u.is_me ? ' <span class="a3s-users__me">You</span>' : "") +
				(u.shared ? ' <span class="a3s-users__shared" title="This login also works in another company">Also in another company</span>' : "") + "</span>" +
				'<span class="a3s-table__meta">' + esc(u.name) + (u.mobile_no ? " &middot; " + esc(u.mobile_no) : "") + "</span></span></span></td>" +
				'<td class="a3s-table__status"><span class="a3s-badge ' + (BADGE[u.type] || "") + '">' + esc(u.type) + "</span></td>" +
				"<td>" + access + "</td>" +
				'<td class="a3s-table__status"><span class="a3s-badge ' + (u.enabled ? "a3s-badge--converted" : "a3s-badge--lost-quotation") + '">' + (u.enabled ? "Active" : "Disabled") + "</span></td>" +
				'<td class="a3s-table__muted">' + (esc(u.last_login) || "Never") + "</td>" +
				'<td><div class="a3s-users__actions">' +
				'<button type="button" class="a3s-icon-btn a3s-icon-btn--framed" data-act="edit" title="Edit" aria-label="Edit ' + esc(u.full_name) + '">' + icon("edit") + "</button>" +
				/* A login shared with another company keeps its own password: no welcome or reset here. */
				(u.shared ? "" :
				'<button type="button" class="a3s-icon-btn a3s-icon-btn--framed" data-act="welcome" title="Send welcome" aria-label="Send welcome">' + icon("whatsapp") + "</button>" +
				'<button type="button" class="a3s-icon-btn a3s-icon-btn--framed" data-act="password" title="Reset password" aria-label="Reset password">' + icon("shield") + "</button>") +
				(u.can_impersonate ? '<button type="button" class="a3s-icon-btn a3s-icon-btn--framed" data-act="login-as" title="Log in as ' + esc(u.full_name) + '" aria-label="Log in as ' + esc(u.full_name) + '">' + icon("eye") + "</button>" : "") +
				(u.is_me ? "" :
				'<button type="button" class="a3s-icon-btn a3s-icon-btn--framed" data-act="toggle" title="' + (u.enabled ? "Disable" : "Enable") + '" aria-label="' + (u.enabled ? "Disable" : "Enable") + '">' + icon("power") + "</button>" +
				'<button type="button" class="a3s-icon-btn a3s-icon-btn--danger" data-act="delete" title="Delete" aria-label="Delete">' + icon("trash") + "</button>") +
				"</div></td></tr>";
		}).join("");
		empty.hidden = list.length > 0;
		document.querySelectorAll("[data-type-tabs] [data-count]").forEach(function (n) {
			var t = n.dataset.count;
			n.textContent = byType.filter(function (u) { return !t || u.type === t; }).length;
		});
		var enabledCount = { active: byStatus.filter(function (u) { return u.enabled; }).length,
			disabled: byStatus.filter(function (u) { return !u.enabled; }).length, "": byStatus.length };
		document.querySelectorAll("[data-enabled-count]").forEach(function (n) { n.textContent = enabledCount[n.dataset.enabledCount]; });
	}
	function reload() {
		return call("users", {}).then(function (d) {
			state.users = d.users; state.counts = d.counts; state.total = d.total; render();
		});
	}
	function find(name) { return state.users.find(function (u) { return u.name === name; }); }

	document.querySelector("[data-type-tabs]").addEventListener("click", function (e) {
		var b = e.target.closest("[data-type]");
		if (!b) return;
		state.type = b.dataset.type;
		document.querySelectorAll("[data-type-tabs] [data-type]").forEach(function (x) { x.setAttribute("aria-selected", String(x === b)); });
		render();
	});
	document.querySelector("[data-enabled-tabs]").addEventListener("click", function (e) {
		var b = e.target.closest("[data-enabled]");
		if (!b) return;
		state.enabled = b.dataset.enabled;
		document.querySelectorAll("[data-enabled-tabs] [data-enabled]").forEach(function (x) { x.setAttribute("aria-selected", String(x === b)); });
		render();
	});
	document.querySelector("[data-user-search]").addEventListener("input", function (e) { state.q = e.target.value.trim(); render(); });

	/* ------------------------------------------------------------------ modals */
	function modal(title, sub, wide) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML = '<div class="a3s-modal__panel' + (wide ? " a3s-users__panel" : "") + '" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
			'<div class="a3s-users__modalhead"><h3 class="a3s-modal__title">' + esc(title) + "</h3>" +
			'<button type="button" class="a3s-icon-btn" data-close aria-label="Close">&times;</button></div>' +
			(sub ? '<p class="a3s-users__sub">' + sub + "</p>" : "") +
			'<div data-body></div><p class="a3s-attach__status" data-status role="status" aria-live="polite" hidden></p></div>';
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
		document.body.appendChild(back);
		var status = back.querySelector("[data-status]");
		return { el: back, body: back.querySelector("[data-body]"), close: close,
			status: function (t, tone) { setStatus(status, t, tone); } };
	}

	/* Add or edit a user. */
	function userForm(u) {
		var editing = !!u;
		u = u || { type: "Employee", enabled: 1 };
		var m = modal(editing ? "Edit user" : "Add user", editing ? esc(u.name) + (u.shared ? " &middot; also works in another company: only their access here can be changed." : "")
			: "They will get a link to set their own password. Someone who already has a login in another company is added to this one instead, with their own login.", true);
		var own = editing && u.shared ? " disabled" : "";
		var con = u.contractor || null;
		m.body.innerHTML =
			'<form class="a3s-modal__form" novalidate>' +
			'<fieldset class="a3s-users__types"><legend class="a3s-users__legend">Kind of user</legend>' +
			choices.types.map(function (t) {
				return '<label class="a3s-users__type"><input type="radio" name="type" value="' + t + '"' + (u.type === t ? " checked" : "") + ">" +
					'<span class="a3s-users__type-name">' + t + '</span><span class="a3s-users__type-hint">' + esc(TYPE_HINT[t]) + "</span></label>";
			}).join("") + "</fieldset>" +
			'<div class="a3s-form__grid">' +
			'<div class="a3s-field"><label for="u-first">First name <span class="a3s-req">*</span></label><input id="u-first" name="first_name" value="' + esc(u.first_name) + '" required' + own + '></div>' +
			'<div class="a3s-field"><label for="u-last">Last name</label><input id="u-last" name="last_name" value="' + esc(u.last_name) + '"' + own + '></div>' +
			'<div class="a3s-field"><label for="u-email">E-mail (login) <span class="a3s-req">*</span></label><input id="u-email" name="email" type="email" value="' + esc(editing ? u.name : "") + '"' + (editing ? " disabled" : "") + ' required>' +
			(editing ? '<p class="a3s-field__hint">The login stays as it is.</p>' : "") + "</div>" +
			'<div class="a3s-field"><label for="u-mobile">Mobile</label><input id="u-mobile" name="mobile_no" inputmode="tel" value="' + esc(u.mobile_no) + '"' + own + '><p class="a3s-field__hint">' + (own ? "Theirs to change, on their own login." : "For the WhatsApp welcome.") + '</p></div>' +
			'<p class="a3s-notice a3s-field--wide a3s-users__access" data-for="Employee">Full staff access: leads, surveys, designs, proposals, projects and their tasks, accounts and service. ' +
			"Only the company's setup is left to Admin.</p>" +
			'<div class="a3s-field a3s-field--wide" data-for="Contractor"><label for="u-con">Contractor record</label><select id="u-con" name="contractor">' +
			'<option value="">+ New contractor record</option>' + choices.contractors.map(function (c) {
				var taken = c.user && c.user !== u.name;
				return '<option value="' + esc(c.name) + '"' + (con && con.name === c.name ? " selected" : "") + (taken ? " disabled" : "") + ">" +
					esc(c.contractor_name) + " · " + esc(c.contractor_type || "") + (taken ? " (login: " + esc(c.user) + ")" : "") + "</option>";
			}).join("") + "</select><p class=\"a3s-field__hint\">His projects are those with this contractor as structure or electrical contractor.</p></div>" +
			'<div class="a3s-field" data-for="Contractor" data-new-con><label for="u-con-name">Contractor name</label><input id="u-con-name" name="contractor_name" placeholder="Firm or person"></div>' +
			'<div class="a3s-field" data-for="Contractor" data-new-con><label for="u-con-type">Contractor type</label><select id="u-con-type" name="contractor_type">' +
			choices.contractor_types.map(function (t) { return "<option>" + t + "</option>"; }).join("") + "</select></div>" +
			'<div class="a3s-field" data-for="Admin Employee"><label for="u-desig">Designation <span class="a3s-req">*</span></label><select id="u-desig" name="designation" required>' +
			'<option value="">Choose…</option>' + choices.designations.map(function (d) { return "<option" + (u.designation === d ? " selected" : "") + ">" + esc(d) + "</option>"; }).join("") +
			'</select><p class="a3s-field__hint">Their job: Project Engineer, Sales Coordinator, Accountant. Tasks for that position go to them.</p></div>' +
			'<div class="a3s-field" data-for="Admin Employee"><label for="u-dept">Department <span class="a3s-req">*</span></label><select id="u-dept" name="department" required>' +
			'<option value="">Choose…</option>' + choices.departments.map(function (d) { return '<option value="' + esc(d.value) + '"' + (u.department === d.value ? " selected" : "") + ">" + esc(d.label) + "</option>"; }).join("") +
			"</select></div>" +
			'<p class="a3s-field__hint a3s-field--wide" data-new-emp>No Employee record yet: one is made with these details.</p>' +
			'<div class="a3s-field" data-new-emp><label for="u-gender">Gender <span class="a3s-req">*</span></label><select id="u-gender" name="gender"><option value="">Choose…</option>' +
			choices.genders.map(function (g) { return "<option>" + esc(g) + "</option>"; }).join("") + "</select></div>" +
			'<div class="a3s-field" data-new-emp><label for="u-dob">Date of birth <span class="a3s-req">*</span></label><input id="u-dob" name="date_of_birth" type="date" max="' + esc(choices.today) + '"></div>' +
			'<div class="a3s-field" data-new-emp><label for="u-doj">Date of joining</label><input id="u-doj" name="date_of_joining" type="date" value="' + esc(choices.today) + '"></div>' +
			(editing ? '<label class="a3s-check a3s-field--wide"><input type="checkbox" name="enabled"' + (u.enabled ? " checked" : "") + (u.is_me ? " disabled" : "") + "><span>Active (can sign in)</span></label>" : "") +
			"</div>" +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary"><span>' + (editing ? "Save changes" : "Add user") + "</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
		var form = m.body.querySelector("form");
		function sync() {
			var type = form.querySelector('[name="type"]:checked').value;
			form.querySelectorAll("[data-for]").forEach(function (el) {
				el.hidden = el.dataset.for.split(" ").indexOf(type) === -1;
			});
			/* Staff are on an Employee record: one is made for them when they have none. */
			var newEmp = choices.staff_types.indexOf(type) !== -1 && !u.employee && !u.shared;
			form.querySelectorAll("[data-new-emp]").forEach(function (el) { el.hidden = !newEmp; });
			var newCon = type === "Contractor" && !form.contractor.value;
			form.querySelectorAll("[data-new-con]").forEach(function (el) { el.hidden = !newCon; });
		}
		form.addEventListener("change", sync);
		sync();
		form.addEventListener("submit", function (e) {
			e.preventDefault();
			var type = form.querySelector('[name="type"]:checked').value;
			var data = { type: type, first_name: form.first_name.value, last_name: form.last_name.value, email: form.email.value,
				mobile_no: form.mobile_no.value, contractor: form.contractor.value,
				new_contractor: { contractor_name: form.contractor_name.value, contractor_type: form.contractor_type.value },
				enabled: editing ? (form.enabled.checked ? 1 : 0) : 1,
				designation: form.designation.value, department: form.department.value, gender: form.gender.value,
				date_of_birth: form.date_of_birth.value, date_of_joining: form.date_of_joining.value };
			var btn = form.querySelector('[type="submit"]');
			busy(btn, true); m.status("");
			call("save_user", { data: data, name: editing ? u.name : null }).then(function (r) {
				return reload().then(function () {
					if (r.created) { m.close(); welcomePanel(find(r.name), "User added", true); }
					else if (r.added) { m.close(); setStatus(pageStatus, "Added " + (r.user ? r.user.full_name : r.name) + " to this company. They sign in with the login they already have and choose this company at the top of the page.", "ok"); }
					else { m.close(); setStatus(pageStatus, "Saved " + (r.user ? r.user.full_name : r.name) + ".", "ok"); }
				});
			}).catch(function (err) { m.status(err.message, "error"); busy(btn, false); });
		});
	}

	/* The welcome: sign-in address, login and a set-password link - by WhatsApp, e-mail or copied. */
	function welcomePanel(u, title, fresh) {
		var m = modal(title || "Send welcome", esc(u.full_name) + " &middot; " + esc(u.name), true);
		m.body.innerHTML = '<p class="a3s-users__sub">' + (fresh ? "Send the welcome now: it has their login and a link to set their password." : "A new set-password link is made each time; any earlier one stops working.") + "</p>" +
			'<div class="a3s-users__welcome" data-welcome><p class="a3s-field__hint">Making the link…</p></div>';
		call("welcome", { name: u.name, channel: "whatsapp" }).then(function (r) { showWelcome(m, u, r); })
			.catch(function (err) { m.status(err.message, "error"); });
	}
	function showWelcome(m, u, r) {
		var box = m.body.querySelector("[data-welcome]");
		box.innerHTML =
			'<dl class="a3s-users__facts"><dt>Sign in at</dt><dd>' + esc(choices.login_url) + "</dd><dt>Login</dt><dd>" + esc(u.name) + "</dd>" +
			'<dt>Set-password link</dt><dd><input class="a3s-users__link" readonly value="' + esc(r.link) + '"></dd></dl>' +
			'<pre class="a3s-users__msg">' + esc(r.text) + "</pre>" +
			'<div class="a3s-form__actions">' +
			'<a class="a3s-btn a3s-btn--primary a3s-users__wa" href="' + esc(r.whatsapp) + '" target="_blank" rel="noopener">' + icon("whatsapp") + "<span>Send on WhatsApp</span></a>" +
			'<button type="button" class="a3s-btn a3s-btn--secondary" data-email' + (choices.can_email ? "" : " disabled") + ">" + icon("mail") + "<span>Send e-mail</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-copy>' + icon("clipboard") + "<span>Copy message</span></button></div>" +
			(r.has_mobile ? "" : '<p class="a3s-field__hint">No mobile number on this user: WhatsApp will ask who to send it to.</p>') +
			(choices.can_email ? "" : '<p class="a3s-field__hint">E-mail needs the company\'s outgoing mailbox, which your administrator sets up.</p>');
		box.querySelector("[data-copy]").addEventListener("click", function () {
			navigator.clipboard.writeText(r.text).then(function () { m.status("Message copied.", "ok"); }, function () { m.status("Select the message above and copy it.", "warn"); });
		});
		var mail = box.querySelector("[data-email]");
		mail.addEventListener("click", function () {
			busy(mail, true); m.status("");
			call("welcome", { name: u.name, channel: "email" }).then(function (x) {
				showWelcome(m, u, Object.assign({}, r, x, { whatsapp: r.whatsapp }));
				m.status("Sent to " + u.name + ". That e-mail's link replaces the one shown before.", "ok");
			}).catch(function (err) { m.status(err.message, "error"); busy(mail, false); });
		});
	}

	/* Reset a password: a new set-password link, or a temporary password typed here. */
	function passwordPanel(u) {
		var m = modal("Reset password", esc(u.full_name) + " &middot; " + esc(u.name), true);
		m.body.innerHTML =
			'<div class="a3s-users__choice">' +
			'<button type="button" class="a3s-users__option" data-link><span class="a3s-users__type-name">Send a set-password link</span>' +
			'<span class="a3s-users__type-hint">They choose their own password. Sent by WhatsApp or e-mail.</span></button>' +
			'<button type="button" class="a3s-users__option" data-temp><span class="a3s-users__type-name">Set a temporary password</span>' +
			'<span class="a3s-users__type-hint">You type it and tell them; they can change it later.</span></button></div>' +
			'<form class="a3s-modal__form" data-temp-form hidden novalidate><div class="a3s-field"><label for="u-pw">New password</label>' +
			'<input id="u-pw" type="password" autocomplete="new-password" minlength="8"><p class="a3s-field__hint">At least 8 characters. They are signed out of every device.</p></div>' +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary"><span>Set password</span></button></div></form>' +
			'<div data-welcome></div>';
		m.body.querySelector("[data-link]").addEventListener("click", function () {
			m.body.querySelector(".a3s-users__choice").hidden = true;
			m.body.querySelector("[data-welcome]").innerHTML = '<div class="a3s-users__welcome" data-welcome><p class="a3s-field__hint">Making the link…</p></div>';
			call("welcome", { name: u.name, channel: "whatsapp" }).then(function (r) { showWelcome(m, u, r); })
				.catch(function (err) { m.status(err.message, "error"); });
		});
		m.body.querySelector("[data-temp]").addEventListener("click", function () {
			m.body.querySelector(".a3s-users__choice").hidden = true;
			var f = m.body.querySelector("[data-temp-form]"); f.hidden = false; f.querySelector("input").focus();
		});
		m.body.querySelector("[data-temp-form]").addEventListener("submit", function (e) {
			e.preventDefault();
			var btn = e.target.querySelector('[type="submit"]');
			busy(btn, true); m.status("");
			call("set_password", { name: u.name, password: e.target.querySelector("input").value }).then(function () {
				m.status("Password set for " + u.full_name + ". Tell them, and ask them to change it.", "ok");
				e.target.hidden = true;
			}).catch(function (err) { m.status(err.message, "error"); busy(btn, false); });
		});
	}

	function confirmPanel(title, text, label, danger, run) {
		var m = modal(title, "");
		m.el.querySelector(".a3s-modal__panel").classList.toggle("a3s-users__danger", !!danger);
		m.body.innerHTML = '<p class="a3s-users__sub">' + text + "</p>" +
			'<div class="a3s-form__actions"><button type="button" class="a3s-btn ' + (danger ? "a3s-users__btn-danger" : "a3s-btn--primary") + '" data-ok><span>' + esc(label) + "</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div>';
		var ok = m.body.querySelector("[data-ok]");
		ok.addEventListener("click", function () {
			busy(ok, true); m.status("");
			run().then(function (msg) { m.close(); reload(); if (msg) setStatus(pageStatus, msg[0], msg[1]); })
				.catch(function (err) { m.status(err.message, "error"); busy(ok, false); });
		});
	}

	/* Log in as: see the portal exactly as they see it. A reason and a time limit; recorded. */
	function loginAsPanel(u) {
		var m = modal("Log in as", esc(u.full_name) + " &middot; " + esc(u.name), false);
		var limit = choices.impersonation_minutes || 60;
		var opts = [15, 30, 60, 120].filter(function (n) { return n <= limit; });
		m.body.innerHTML = '<form class="a3s-modal__form" novalidate>' +
			'<p class="a3s-users__sub">You will see the portal as ' + esc(u.full_name) + ' sees it, until you return to your own account or the time runs out. ' +
			"Everything you do is recorded as done by you on their behalf.</p>" +
			'<div class="a3s-field"><label for="la-reason">Why <span class="a3s-req">*</span></label>' +
			'<textarea id="la-reason" name="reason" rows="3" minlength="15" required placeholder="For example: checking why the dealer cannot see his new lead"></textarea>' +
			'<p class="a3s-field__hint" data-count>At least 15 characters. Kept in the audit trail and shown to them.</p></div>' +
			'<div class="a3s-field"><label for="la-min">For</label><select id="la-min" name="minutes">' +
			opts.map(function (n) { return '<option value="' + n + '"' + (n === 30 ? " selected" : "") + ">" + n + " minutes</option>"; }).join("") + "</select></div>" +
			'<label class="a3s-check"><input type="checkbox" name="notify"' + (choices.notify_on_impersonation ? " checked" : "") + "><span>Tell " + esc(u.first_name || u.full_name) + " by e-mail</span></label>" +
			'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary"><span>Log in as ' + esc(u.first_name || u.full_name) + "</span></button>" +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
		var form = m.body.querySelector("form");
		var count = form.querySelector("[data-count]");
		form.reason.addEventListener("input", function () {
			var n = form.reason.value.trim().length;
			count.textContent = n < 15 ? (15 - n) + " more characters needed." : "Kept in the audit trail and shown to them.";
		});
		form.reason.focus();
		form.addEventListener("submit", function (e) {
			e.preventDefault();
			if (form.reason.value.trim().length < 15) { m.status("Say why, in at least 15 characters.", "error"); return; }
			var btn = form.querySelector('[type="submit"]');
			busy(btn, true, "Opening…"); m.status("");
			call("a3_sola.api.impersonation.start", { user: u.name, reason: form.reason.value.trim(),
				minutes: form.minutes.value, notify_user: form.notify.checked ? 1 : 0 })
				.then(function (r) { window.location.assign((r && r.redirect) || "/a3solaportal/dashboard"); })
				.catch(function (err) { m.status(err.message, "error"); busy(btn, false); });
		});
	}

	rows.addEventListener("click", function (e) {
		var b = e.target.closest("[data-act]");
		if (!b) return;
		var u = find(b.closest("[data-user]").dataset.user);
		if (!u) return;
		if (b.dataset.act === "edit") userForm(u);
		else if (b.dataset.act === "welcome") welcomePanel(u);
		else if (b.dataset.act === "password") passwordPanel(u);
		else if (b.dataset.act === "login-as") loginAsPanel(u);
		else if (b.dataset.act === "toggle") {
			confirmPanel(u.enabled ? "Disable user" : "Enable user",
				u.enabled ? "<b>" + esc(u.full_name) + "</b> will be signed out and can no longer sign in. Their records stay as they are."
					: "<b>" + esc(u.full_name) + "</b> will be able to sign in again.",
				u.enabled ? "Disable" : "Enable", u.enabled,
				function () { return call("set_enabled", { name: u.name, enabled: u.enabled ? 0 : 1 }).then(function () {
					return [(u.enabled ? "Disabled " : "Enabled ") + u.full_name + ".", "ok"]; }); });
		} else if (b.dataset.act === "delete") {
			confirmPanel(u.shared ? "Remove from this company" : "Delete user", u.shared
				? "Remove <b>" + esc(u.full_name) + "</b> (" + esc(u.name) + ") from this company? Their login stays for the other company they work in."
				: "Delete <b>" + esc(u.full_name) + "</b> (" + esc(u.name) + ")? If records in the system name them, they are disabled instead, so the history stays intact.",
				u.shared ? "Remove" : "Delete", true,
				function () { return call("delete_user", { name: u.name }).then(function (r) {
					return r.deleted ? ["Deleted " + u.full_name + ".", "ok"] : [r.message, "warn"]; }); });
		}
	});
	document.querySelector("[data-add-user]").addEventListener("click", function () { userForm(null); });

	render();
})();
