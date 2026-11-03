/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Administration > Menu (www/a3solaportal/menu, api/portal_menu): a checkbox per menu item,
 * and one per group that ticks or clears all of it (half-ticked while only some are shown).
 * Save posts the unticked items - the ones hidden - and reloads, so the menu on the left shows
 * what was saved.
 */
(function () {
	"use strict";

	var set = document.querySelector("[data-menu-set]");
	if (!set) return;
	var save = document.querySelector("[data-menu-save]");
	var status = document.querySelector("[data-menu-status]");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function boxes(scope) { return Array.prototype.slice.call((scope || set).querySelectorAll("input[data-route]")); }
	function hiddenRoutes() { return boxes().filter(function (b) { return !b.checked; }).map(function (b) { return b.dataset.route; }); }
	var saved = JSON.stringify(hiddenRoutes());

	function setStatus(text, tone) {
		status.textContent = text || "";
		status.dataset.tone = tone || "";
		status.hidden = !text;
	}

	/* Each group's own box and count follow its items; Save is live only when something changed. */
	function refresh() {
		Array.prototype.forEach.call(set.querySelectorAll("[data-group]"), function (group) {
			var items = boxes(group), on = items.filter(function (b) { return b.checked; }).length;
			var toggle = group.querySelector("[data-group-toggle]");
			toggle.checked = on === items.length;
			toggle.indeterminate = on > 0 && on < items.length;
			group.querySelector("[data-group-count]").textContent = on + " of " + items.length + " shown";
		});
		boxes().forEach(function (b) { b.closest(".a3s-menuset__item").classList.toggle("is-off", !b.checked); });
		save.disabled = JSON.stringify(hiddenRoutes()) === saved;
	}

	set.addEventListener("change", function (e) {
		if (e.target.matches("[data-group-toggle]")) {
			var on = e.target.checked;
			boxes(e.target.closest("[data-group]")).forEach(function (b) { if (!b.dataset.locked) b.checked = on; });
		}
		setStatus("");
		refresh();
	});

	save.addEventListener("click", function () {
		save.disabled = true;
		setStatus("Saving…");
		var form = new FormData();
		form.append("hidden_routes", JSON.stringify(hiddenRoutes()));
		fetch("/api/method/a3_sola.api.portal_menu.save", { method: "POST", credentials: "same-origin", body: form,
			headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } })
			.then(function (r) {
				return r.json().catch(function () { return {}; }).then(function (body) {
					if (!r.ok) throw new Error(r.status === 403 ? "Only an administrator can change the menu." : "That did not save. Try again.");
					return body;
				});
			})
			.then(function () {
				setStatus("Saved. Updating the menu…", "ok");
				window.location.reload();
			})
			.catch(function (err) { setStatus(err.message, "error"); refresh(); });
	});

	refresh();
})();
