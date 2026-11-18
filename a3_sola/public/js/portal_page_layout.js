/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Administration > Page Layout (www/a3solaportal/page-layout, api/page_layout): the page
 * chosen at the top opens with a checkbox per field or part, and one per section that ticks or
 * clears all of it. Save posts the unticked ones - the ones hidden - for that page.
 */
(function () {
	"use strict";

	var set = document.querySelector("[data-layout-set]");
	if (!set) return;
	var save = document.querySelector("[data-layout-save]");
	var status = document.querySelector("[data-layout-status]");
	var picker = document.querySelector("[data-layout-page]");
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";

	function boxes(scope) { return Array.prototype.slice.call((scope || set).querySelectorAll("input[data-name]")); }
	function hiddenNames() { return boxes().filter(function (b) { return !b.checked; }).map(function (b) { return b.dataset.name; }); }
	var saved = JSON.stringify(hiddenNames());
	function dirty() { return JSON.stringify(hiddenNames()) !== saved; }

	function setStatus(text, tone) {
		status.textContent = text || "";
		status.dataset.tone = tone || "";
		status.hidden = !text;
	}

	/* Each section's own box and count follow its fields; Save is live only when something changed. */
	function refresh() {
		Array.prototype.forEach.call(set.querySelectorAll("[data-group]"), function (group) {
			var items = boxes(group), on = items.filter(function (b) { return b.checked; }).length;
			var toggle = group.querySelector("[data-group-toggle]");
			toggle.checked = on === items.length;
			toggle.indeterminate = on > 0 && on < items.length;
			group.querySelector("[data-group-count]").textContent = on + " of " + items.length + " shown";
		});
		boxes().forEach(function (b) { b.closest(".a3s-menuset__item").classList.toggle("is-off", !b.checked); });
		save.disabled = !dirty();
	}

	set.addEventListener("change", function (e) {
		if (e.target.matches("[data-group-toggle]")) {
			var on = e.target.checked;
			boxes(e.target.closest("[data-group]")).forEach(function (b) { if (!b.dataset.locked) b.checked = on; });
		}
		setStatus("");
		refresh();
	});

	/* Another page: opened in place, after asking if this one has changes not saved. */
	picker.addEventListener("change", function () {
		if (dirty() && !window.confirm("This page has changes not saved. Leave them?")) {
			picker.value = set.dataset.key;
			return;
		}
		window.location.search = "?page=" + encodeURIComponent(picker.value);
	});

	save.addEventListener("click", function () {
		save.disabled = true;
		setStatus("Saving…");
		var form = new FormData();
		form.append("key", set.dataset.key);
		form.append("hidden", JSON.stringify(hiddenNames()));
		fetch("/api/method/a3_sola.api.page_layout.save", { method: "POST", credentials: "same-origin", body: form,
			headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } })
			.then(function (r) {
				return r.json().catch(function () { return {}; }).then(function (body) {
					if (!r.ok) {
						var msg = r.status === 403 ? "Only an administrator can change the page layout." : "That did not save. Try again.";
						try { msg = JSON.parse(JSON.parse(body._server_messages)[0]).message || msg; } catch (err) { /* keep it */ }
						throw new Error(msg);
					}
					return body;
				});
			})
			.then(function () {
				saved = JSON.stringify(hiddenNames());
				setStatus("Saved. The page shows it from its next opening.", "ok");
				refresh();
			})
			.catch(function (err) { setStatus(err.message, "error"); refresh(); });
	});

	refresh();
})();
