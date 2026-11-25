/* The Events pages (a3_sola.api.events): the event form (new or edit), and on an event's page
   the funnel and the registrations - live, with each visitor's proposal one tap away on
   WhatsApp and their name kept off the stall screen when they ask. */
(function () {
	"use strict";

	var API = "a3_sola.api.events.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var pageStatus = document.querySelector("[data-page-status]");
	var REFRESH_MS = 15000;

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
	function call(method, args, formData, get) {
		var opts = { method: get ? "GET" : "POST", credentials: "same-origin", headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json" } };
		var url = "/api/method/" + API + method;
		if (get) url += "?" + new URLSearchParams(args || {}).toString();
		else if (formData) opts.body = formData;
		else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(args || {}); }
		return fetch(url, opts).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
				return body.message;
			});
		});
	}
	function setStatus(el, text, tone) {
		if (!el) return;
		el.textContent = text || "";
		el.dataset.tone = tone || "";
		el.hidden = !text;
	}
	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

	/* ------------------------------------------------------------------ the event form */
	function modal(title, sub) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML = '<div class="a3s-modal__panel a3s-ev__panel" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
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
		return { el: back, body: back.querySelector("[data-body]"), close: close, status: function (t, tone) { setStatus(status, t, tone); } };
	}
	function field(label, html, opts) {
		opts = opts || {};
		return '<div class="a3s-field' + (opts.wide ? " a3s-field--wide" : "") + '"><label' + (opts.id ? ' for="' + opts.id + '"' : "") + ">" + label +
			(opts.req ? ' <span class="a3s-req">*</span>' : "") + "</label>" + html + (opts.hint ? '<p class="a3s-field__hint">' + opts.hint + "</p>" : "") + "</div>";
	}
	function options(list, chosen, blank) {
		return (blank != null ? '<option value="">' + esc(blank) + "</option>" : "") + list.map(function (o) {
			var v = typeof o === "string" ? o : o.value, l = typeof o === "string" ? o : o.label;
			return '<option value="' + esc(v) + '"' + (v === chosen ? " selected" : "") + ">" + esc(l) + "</option>";
		}).join("");
	}
	function eventForm(values) {
		var editing = !!(values && values.name);
		var m = modal(editing ? "Edit event" : "New event", editing ? esc(values.name)
			: "An exhibition, event or campaign. It gets its own QR code; every visitor who scans it becomes a lead.");
		m.body.innerHTML = '<p class="a3s-field__hint">Loading…</p>';
		call("form_options", {}, null, true).then(function (o) {
			var v = values || { company: o.default_company, lead_owner: o.me, is_active: 1, ask_documents: 1, show_estimate_on_screen: 1,
				lead_source: o.sources.indexOf("Exhibition") !== -1 ? "Exhibition" : "", welcome_message: o.default_welcome, packages: [] };
			var pk = (v.packages || []);
			var packages = o.packages.filter(function (p) { return !v.company || p.company === v.company; });
			m.body.innerHTML = '<form class="a3s-modal__form" novalidate><div class="a3s-form__grid">' +
				field("Event name", '<input id="ev-name" name="event_name" maxlength="140" required value="' + esc(v.event_name) + '">', { id: "ev-name", req: 1, wide: 1 }) +
				field("Venue", '<input id="ev-venue" name="venue" value="' + esc(v.venue) + '">', { id: "ev-venue", wide: o.companies.length <= 1 }) +
				(o.companies.length > 1 ? field("Company", '<select id="ev-co" name="company">' + options(o.companies, v.company) + "</select>", { id: "ev-co", req: 1 })
					: '<input type="hidden" name="company" value="' + esc(v.company || o.companies[0] || "") + '">') +
				field("Starts", '<input id="ev-start" type="date" name="start_date" value="' + esc(v.start_date) + '">', { id: "ev-start" }) +
				field("Ends", '<input id="ev-end" type="date" name="end_date" value="' + esc(v.end_date) + '">', { id: "ev-end" }) +
				field("Lead owner", '<select id="ev-owner" name="lead_owner" required>' + options(o.staff, v.lead_owner, "Choose…") + "</select>",
					{ id: "ev-owner", req: 1, hint: "Every lead registered at the event is theirs." }) +
				field("Lead source", '<select id="ev-src" name="lead_source">' + options(o.sources, v.lead_source, "Choose…") + "</select>", { id: "ev-src" }) +
				field("Our WhatsApp number", '<input id="ev-wa" name="whatsapp_number" inputmode="tel" value="' + esc(v.whatsapp_number) + '">',
					{ id: "ev-wa", hint: "\"Chat with us on WhatsApp\" on the thank-you page opens it." }) +
				field("Brochure (PDF)", '<input id="ev-br" type="file" name="brochure" accept="application/pdf">',
					{ id: "ev-br", hint: v.brochure_name ? "Now: " + esc(v.brochure_name) + ". Choose a file to replace it." : "Optional, up to 10 MB. Each visitor gets their own proposal; a brochure goes too where the message names {brochure}." }) +
				field("WhatsApp welcome message", '<textarea id="ev-msg" name="welcome_message" rows="6">' + esc(v.welcome_message || o.default_welcome) + "</textarea>",
					{ id: "ev-msg", wide: 1, hint: "{name}, {event}, {company}, {proposal} (their proposal link), {brochure}, {estimate} and {call_time} are filled in for each visitor. *Bold* stays bold in WhatsApp." }) +
				'<fieldset class="a3s-field a3s-field--wide a3s-ev__pkgs"><legend class="a3s-users__legend">Packages for the instant estimate</legend>' +
				'<p class="a3s-field__hint">Tick the packages the estimate may offer. None ticked: every active subsidy package.</p>' +
				'<div class="a3s-ev__pkglist">' + (packages.length ? packages.map(function (p) {
					return '<label class="a3s-check"><input type="checkbox" name="packages" value="' + esc(p.name) + '"' + (pk.indexOf(p.name) !== -1 ? " checked" : "") +
						"><span>" + esc(p.package_name) + ' <span class="a3s-table__meta">' + esc(p.capacity_kw) + " kW · " + esc(p.connection_type || "") + "</span></span></label>";
				}).join("") : '<p class="a3s-field__hint">No active packages.</p>') + "</div></fieldset>" +
				field("Stall screen headline", '<input id="ev-head" name="screen_headline" maxlength="140" value="' + esc(v.screen_headline) + '" placeholder="Welcome to …">', { id: "ev-head" }) +
				field("Exhibition logo", '<input id="ev-logo" type="file" name="event_logo" accept="image/png,image/jpeg,image/webp">',
					{ id: "ev-logo", hint: v.event_logo_name ? "Now: " + esc(v.event_logo_name) + ". Choose a file to replace it." : "The exhibition's logo, on the right of the stall screen. PNG, JPG or WebP." }) +
				'<div class="a3s-field a3s-ev__checks">' +
				'<label class="a3s-check"><input type="checkbox" name="ask_documents"' + (v.ask_documents ? " checked" : "") + "><span>Ask for documents (optional for the visitor)</span></label>" +
				'<label class="a3s-check"><input type="checkbox" name="show_estimate_on_screen"' + (v.show_estimate_on_screen ? " checked" : "") + "><span>Show the estimate on the stall screen</span></label>" +
				(editing ? '<label class="a3s-check"><input type="checkbox" name="is_active"' + (v.is_active ? " checked" : "") + "><span>Taking registrations</span></label>" : "") +
				"</div></div>" +
				'<div class="a3s-form__actions"><button type="submit" class="a3s-btn a3s-btn--primary"><span>' + (editing ? "Save changes" : "Create event") + "</span></button>" +
				'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div></form>';
			var form = m.body.querySelector("form");
			form.addEventListener("submit", function (e) {
				e.preventDefault();
				if (!form.event_name.value.trim()) { m.status("Enter the event's name.", "error"); form.event_name.focus(); return; }
				if (!form.lead_owner.value) { m.status("Choose who owns the leads.", "error"); form.lead_owner.focus(); return; }
				var file = form.brochure.files && form.brochure.files[0];
				if (file && !/\.pdf$/i.test(file.name)) { m.status("The brochure must be a PDF.", "error"); return; }
				var logo = form.event_logo.files && form.event_logo.files[0];
				if (logo && !/\.(png|jpe?g|webp)$/i.test(logo.name)) { m.status("The logo must be a PNG, JPG or WebP image.", "error"); return; }
				var data = {};
				["event_name", "venue", "company", "start_date", "end_date", "lead_owner", "lead_source", "whatsapp_number", "welcome_message", "screen_headline"].forEach(function (k) {
					if (form[k]) data[k] = form[k].value;
				});
				["ask_documents", "show_estimate_on_screen", "is_active"].forEach(function (k) { if (form[k]) data[k] = form[k].checked ? 1 : 0; });
				data.packages = [].slice.call(form.querySelectorAll('[name="packages"]:checked')).map(function (b) { return b.value; });
				var btn = form.querySelector('[type="submit"]');
				btn.disabled = true; btn.classList.add("is-busy"); m.status("Saving…");
				call("save_event", { data: data, name: editing ? values.name : null }).then(function (r) {
					if (!file) return r;
					var fd = new FormData();
					fd.append("name", r.name);
					fd.append("file", file, file.name);
					m.status("Uploading the brochure…");
					return call("upload_brochure", null, fd).then(function () { return r; });
				}).then(function (r) {
					if (!logo) return r;
					var fd = new FormData();
					fd.append("name", r.name);
					fd.append("file", logo, logo.name);
					m.status("Uploading the logo…");
					return call("upload_event_logo", null, fd).then(function () { return r; });
				}).then(function (r) {
					window.location.assign(r.route);
				}).catch(function (err) {
					btn.disabled = false; btn.classList.remove("is-busy");
					m.status(err.message, "error");
				});
			});
		}).catch(function (err) { m.body.innerHTML = ""; m.status(err.message, "error"); });
	}
	var newBtn = document.querySelector("[data-new-event]");
	if (newBtn) newBtn.addEventListener("click", function () { eventForm(null); });

	/* ------------------------------------------------------------------ one event */
	var bootEl = document.getElementById("a3s-event-data");
	if (!bootEl) return;
	var boot = JSON.parse(bootEl.textContent);
	var state = { rows: boot.data.rows, funnel: boot.data.funnel, today: boot.data.today, filter: "", q: "" };
	var rowsEl = document.querySelector("[data-reg-rows]");
	var emptyEl = document.querySelector("[data-reg-empty]");

	var editBtn = document.querySelector("[data-edit-event]");
	if (editBtn) editBtn.addEventListener("click", function () { eventForm(boot.form); });

	/* Copy to the clipboard: the Clipboard API where the page is secure (https, localhost), else
	   the older copy command on a selected field - the portal opened by its network address
	   (http://192.168…) has no Clipboard API. */
	function copyText(text) {
		if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
		return new Promise(function (resolve, reject) {
			var area = document.createElement("textarea");
			area.value = text;
			area.setAttribute("readonly", "");
			area.style.position = "fixed"; area.style.top = "-1000px"; area.style.opacity = "0";
			document.body.appendChild(area);
			area.select();
			area.setSelectionRange(0, text.length);
			var ok = false;
			try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
			area.remove();
			(ok ? resolve : reject)();
		});
	}
	/* The Copy button, or a click in the link itself: the link is copied and the button says so. */
	document.querySelectorAll("[data-copy]").forEach(function (b) {
		var input = b.parentNode.querySelector("input");
		function copy() {
			if (input) input.select();
			copyText(b.dataset.copy).then(function () {
				b.textContent = "Copied"; b.classList.add("is-copied");
				setTimeout(function () { b.textContent = "Copy"; b.classList.remove("is-copied"); }, 1800);
			}, function () { setStatus(pageStatus, "Copy did not work here: the link is selected, press Ctrl+C.", "warn"); });
		}
		b.addEventListener("click", copy);
		if (input) { input.style.cursor = "pointer"; input.title = "Click to copy"; input.addEventListener("click", copy); }
	});

	function renderFunnel() {
		var max = Math.max.apply(null, state.funnel.map(function (s) { return s.count; }).concat([1]));
		document.querySelector("[data-funnel]").innerHTML = state.funnel.map(function (s) {
			return '<li><span class="a3s-ev__stage">' + esc(s.label) + '</span><span class="a3s-ev__barwrap"><span class="a3s-ev__barfill" style="width:' +
				Math.max(s.count ? 4 : 0, Math.round(100 * s.count / max)) + '%"></span></span><b>' + s.count + "</b></li>";
		}).join("");
		document.querySelector("[data-today]").textContent = state.today + (state.today === 1 ? " registration" : " registrations") + " today.";
	}
	function matches(r) {
		var q = state.q.toLowerCase();
		return (!state.filter || (state.filter === "unsent" && !r.sent)) &&
			(!q || [r.full_name, r.mobile, r.district].join(" ").toLowerCase().indexOf(q) !== -1);
	}
	function render() {
		var list = state.rows.filter(matches);
		rowsEl.innerHTML = list.map(function (r) {
			var est = r.kw ? esc(r.kw) + " kW" + (r.bill ? '<span class="a3s-table__meta">Bill ' + money.format(r.bill) + " a month</span>" : "")
				: (r.bill ? money.format(r.bill) + " a month" : '<span class="a3s-table__muted">—</span>');
			var brochure = r.sent
				? '<span class="a3s-badge a3s-badge--converted">Sent</span><span class="a3s-table__meta">' + esc(r.sent) + (r.sent_via ? " · " + esc(r.sent_via) : "") + "</span>"
					+ (r.whatsapp ? '<a class="a3s-ev__again" href="' + esc(r.whatsapp) + '" target="_blank" rel="noopener" data-send="' + esc(r.name) + '">Send again</a>' : "")
				: (r.whatsapp ? '<a class="a3s-btn a3s-btn--primary a3s-ev__send" href="' + esc(r.whatsapp) + '" target="_blank" rel="noopener" data-send="' + esc(r.name) + '">' +
					'<svg class="a3s-ic" aria-hidden="true"><use href="#ic-whatsapp"></use></svg><span>Send proposal</span></a>' : '<span class="a3s-table__muted">No number</span>');
			return "<tr data-lead=\"" + esc(r.name) + "\">" +
				'<td><a class="a3s-table__link" href="/a3solaportal/leads/' + encodeURIComponent(r.name) + '">' + esc(r.full_name) + "</a>" +
				'<span class="a3s-table__meta">' + esc(r.mobile) + (r.district ? " · " + esc(r.district) : "") + (r.interest ? " · " + esc(r.interest) : "") + "</span></td>" +
				"<td>" + esc(r.registered) + (r.call_time ? '<span class="a3s-table__meta">Call: ' + esc(r.call_time) + "</span>" : "") + "</td>" +
				"<td>" + est + (r.proposal ? '<a class="a3s-table__meta a3s-table__link" href="/a3solaportal/proposals/' + encodeURIComponent(r.proposal) + '">' + esc(r.proposal) + "</a>" : "") + "</td>" +
				"<td>" + (r.papers ? '<span class="a3s-badge a3s-badge--open">' + r.papers + (r.papers === 1 ? " paper" : " papers") + "</span>" : '<span class="a3s-table__muted">—</span>') + "</td>" +
				'<td class="a3s-ev__brochure">' + brochure + "</td>" +
				'<td><button type="button" class="a3s-ev__screen' + (r.hidden ? " is-hidden" : "") + '" data-hide="' + esc(r.name) + '" aria-pressed="' + (r.hidden ? "true" : "false") + '">' +
				(r.hidden ? "Hidden" : "Shown") + "</button></td>" +
				'<td class="a3s-table__status"><span class="a3s-badge a3s-badge--open">' + esc(r.status || "New") + "</span></td></tr>";
		}).join("");
		emptyEl.hidden = list.length > 0;
		document.querySelector("[data-reg-count]").textContent = state.rows.length;
		document.querySelector("[data-unsent-count]").textContent = state.rows.filter(function (r) { return !r.sent; }).length;
		renderFunnel();
	}
	render();

	document.querySelector("[data-reg-tabs]").addEventListener("click", function (e) {
		var b = e.target.closest("[data-filter]");
		if (!b) return;
		state.filter = b.dataset.filter;
		document.querySelectorAll("[data-reg-tabs] [data-filter]").forEach(function (x) { x.setAttribute("aria-selected", String(x === b)); });
		render();
	});
	document.querySelector("[data-reg-search]").addEventListener("input", function (e) { state.q = e.target.value.trim(); render(); });

	/* Send proposal: the link opens WhatsApp (left to the browser, so it is never blocked as a
	   pop-up); the send is recorded on the lead at the same moment. */
	rowsEl.addEventListener("click", function (e) {
		var send = e.target.closest("[data-send]");
		if (send) {
			var lead = send.dataset.send;
			call("mark_sent", { lead: lead }).then(function (r) {
				var row = state.rows.find(function (x) { return x.name === lead; });
				if (row && !row.sent) { row.sent = r.sent; row.sent_via = "WhatsApp"; }
				render();
			}).catch(function (err) { setStatus(pageStatus, err.message, "error"); });
			return;
		}
		var hide = e.target.closest("[data-hide]");
		if (hide) {
			var on = hide.getAttribute("aria-pressed") !== "true";
			hide.disabled = true;
			call("set_hidden", { lead: hide.dataset.hide, hidden: on ? 1 : 0 }).then(function (r) {
				var row = state.rows.find(function (x) { return x.name === hide.dataset.hide; });
				if (row) row.hidden = r.hidden;
				render();
			}).catch(function (err) { hide.disabled = false; setStatus(pageStatus, err.message, "error"); });
		}
	});

	/* Live: new registrations appear while the page is open. */
	setInterval(function () {
		if (document.hidden) return;
		call("registrations", { event: boot.name }, null, true).then(function (d) {
			state.rows = d.rows; state.funnel = d.funnel; state.today = d.today;
			render();
		}).catch(function () { /* the next refresh tries again */ });
	}, REFRESH_MS);
})();
