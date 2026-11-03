/* The Packages page: an admin lists the Solar Packages, opens one to edit, duplicates,
   activates or sets it to Draft, and deletes it (a3_sola.api.portal_packages). */
(function () {
	"use strict";

	var API = "a3_sola.api.portal_packages.";
	var EDIT = "/a3solaportal/packages/edit";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var boot = JSON.parse(document.getElementById("a3s-packages-data").textContent);
	var state = { packages: boot.packages, counts: boot.counts, total: boot.total, status: "", q: "" };
	var rows = document.querySelector("[data-package-rows]");
	var empty = document.querySelector("[data-package-empty]");
	var pageStatus = document.querySelector("[data-page-status]");

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
		return (body && body.exception) ? String(body.exception).split("\n").pop().replace(/^[\w.]+(Error|Exception):\s*/, "").trim() : "";
	}
	function call(method, args) {
		return fetch("/api/method/" + API + method, {
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
	function icon(name) { return '<svg class="a3s-ic" aria-hidden="true"><use href="#ic-' + name + '"></use></svg>'; }
	function money(n) { return n ? "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—"; }
	function kw(n) { return (Number(n) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 }) + " kW"; }

	/* ------------------------------------------------------------------ the list */
	function render() {
		var q = state.q.toLowerCase();
		var list = state.packages.filter(function (p) {
			return (!state.status || p.status === state.status) &&
				(!q || [p.package_name, p.specification_code, p.name, kw(p.capacity_kw), p.system_type, p.tier].join(" ").toLowerCase().indexOf(q) !== -1);
		});
		rows.innerHTML = list.map(function (p) {
			var active = p.status === "Active";
			return '<tr data-package="' + esc(p.name) + '">' +
				'<td data-label="Package"><a class="a3s-table__link" href="' + EDIT + "?name=" + encodeURIComponent(p.name) + '">' + esc(p.package_name) + "</a>" +
				'<span class="a3s-table__meta">' + esc(p.specification_code || "") + " &middot; " + esc(p.name) + "</span></td>" +
				'<td data-label="System">' + esc(kw(p.capacity_kw)) + '<span class="a3s-table__meta">' + esc([p.system_type, p.connection_type, p.tier].filter(Boolean).join(" · ")) + "</span></td>" +
				'<td data-label="Net rate" class="a3s-table__num">' + money(p.net_rate) + (p.system_cost ? '<span class="a3s-table__meta">MRP ' + money(p.system_cost) + "</span>" : "") + "</td>" +
				'<td data-label="Status" class="a3s-table__status"><span class="a3s-badge ' + (active ? "a3s-badge--converted" : "a3s-badge--open") + '">' + esc(p.status) + "</span></td>" +
				'<td data-label="Item &amp; BOM"><span class="a3s-pkg__chips">' +
				'<span class="a3s-pkg__chip' + (p.item ? " is-set" : "") + '">' + (p.item ? "Item" : "No item") + "</span>" +
				'<span class="a3s-pkg__chip' + (p.bom ? " is-set" : "") + '">' + (p.bom ? esc(p.bom) : "No BOM") + "</span></span></td>" +
				'<td><div class="a3s-users__actions">' +
				'<a class="a3s-icon-btn a3s-icon-btn--framed" href="' + EDIT + "?name=" + encodeURIComponent(p.name) + '" title="Edit" aria-label="Edit ' + esc(p.package_name) + '">' + icon("edit") + "</a>" +
				'<a class="a3s-icon-btn a3s-icon-btn--framed" href="' + EDIT + "?copy=" + encodeURIComponent(p.name) + '" title="Duplicate" aria-label="Duplicate ' + esc(p.package_name) + '">' + icon("stack") + "</a>" +
				'<button type="button" class="a3s-icon-btn a3s-icon-btn--framed" data-act="toggle" title="' + (active ? "Set to Draft" : "Activate") + '" aria-label="' + (active ? "Set to Draft" : "Activate") + '">' + icon(active ? "power" : "check") + "</button>" +
				'<button type="button" class="a3s-icon-btn a3s-icon-btn--danger" data-act="delete" title="Delete" aria-label="Delete ' + esc(p.package_name) + '">' + icon("trash") + "</button>" +
				"</div></td></tr>";
		}).join("");
		empty.hidden = list.length > 0;
		["Active", "Draft"].forEach(function (t) {
			var n = document.querySelector('[data-count="' + t + '"]');
			if (n) n.textContent = state.counts[t] || 0;
		});
		var all = document.querySelector('[data-count=""]');
		if (all) all.textContent = state.total;
	}
	function reload() {
		return call("packages", {}).then(function (d) {
			state.packages = d.packages; state.counts = d.counts; state.total = d.total; render();
		});
	}
	function find(name) { return state.packages.find(function (p) { return p.name === name; }); }

	document.querySelector("[data-status-tabs]").addEventListener("click", function (e) {
		var b = e.target.closest("[data-status]");
		if (!b) return;
		state.status = b.dataset.status;
		document.querySelectorAll("[data-status-tabs] [data-status]").forEach(function (x) { x.setAttribute("aria-selected", String(x === b)); });
		render();
	});
	document.querySelector("[data-package-search]").addEventListener("input", function (e) { state.q = e.target.value.trim(); render(); });

	/* ------------------------------------------------------------------ delete */
	function confirmDelete(p) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML = '<div class="a3s-modal__panel a3s-users__danger" role="dialog" aria-modal="true" aria-label="Delete package">' +
			'<div class="a3s-users__modalhead"><h3 class="a3s-modal__title">Delete ' + esc(p.package_name) + "?</h3>" +
			'<button type="button" class="a3s-icon-btn" data-close aria-label="Close">&times;</button></div>' +
			'<p class="a3s-users__sub">If no estimate, project or quotation uses it, the package is deleted with its own Item and BOM. ' +
			"If one does, it is set to Draft instead: it is no longer offered, and those records keep it.</p>" +
			'<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-users__btn-danger" data-yes><span>Delete package</span></button>' +
			'<button type="button" class="a3s-btn a3s-btn--ghost" data-close>Cancel</button></div>' +
			'<p class="a3s-attach__status" data-status role="status" aria-live="polite" hidden></p></div>';
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
		back.querySelector("[data-yes]").addEventListener("click", function () {
			var btn = this;
			btn.disabled = true;
			call("delete_package", { name: p.name }).then(function (r) {
				close();
				return reload().then(function () {
					setStatus(pageStatus, r.deleted ? "Deleted " + p.package_name + "." + (r.kept && r.kept.length ? " Kept " + r.kept.join(", ") + ", which other records use." : "") : r.message, r.deleted ? "ok" : "");
				});
			}).catch(function (err) { btn.disabled = false; setStatus(back.querySelector("[data-status]"), err.message, "error"); });
		});
		document.body.appendChild(back);
		back.querySelector("[data-yes]").focus();
	}

	rows.addEventListener("click", function (e) {
		var btn = e.target.closest("button[data-act]");
		if (!btn) return;
		var p = find(btn.closest("tr").dataset.package);
		if (!p) return;
		if (btn.dataset.act === "delete") return confirmDelete(p);
		if (btn.dataset.act === "toggle") {
			var to = p.status === "Active" ? "Draft" : "Active";
			btn.disabled = true;
			call("set_status", { name: p.name, status: to }).then(function () {
				return reload().then(function () {
					setStatus(pageStatus, p.package_name + (to === "Active" ? " is active: estimates can offer it now." : " is Draft: it is no longer offered."), "ok");
				});
			}).catch(function (err) { btn.disabled = false; setStatus(pageStatus, err.message, "error"); });
		}
	});

	render();
})();
