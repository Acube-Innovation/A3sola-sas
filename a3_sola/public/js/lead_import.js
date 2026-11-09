/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Import from Google Sheet, on the leads list (templates/includes/lead_import_dialog.html):
 * the sheet is checked first - a3_sola.api.lead_import.preview says what each row will do,
 * saving nothing - and then imported a batch at a time (run), with its progress, the rows
 * that did not go in said with why, and the list reloaded when the dialog is closed.
 */
(function () {
	"use strict";

	var modal = document.querySelector("[data-lead-import]");
	if (!modal) return;
	var API = "/api/method/a3_sola.api.lead_import.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var $ = function (sel) { return modal.querySelector(sel); };
	var campaign = $("[data-li-campaign]"), newCampaign = $("[data-li-new-campaign]"), newField = $("[data-li-new-campaign-field]");
	var LAST = "a3s-lead-import-campaign";
	var url = $("[data-li-url]"), status = $("[data-li-status]"), check = $("[data-li-check]"), runBtn = $("[data-li-run]");
	var preview = null, imported = 0, opener = null, running = false;
	var WILL = { add: "Add", update: "Update", same: "No change", skip: "Skip" };

	function el(tag, cls, text) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text != null) n.textContent = text;
		return n;
	}

	function message(data, fallback) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (msgs.length) return JSON.parse(msgs[0]).message.replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception ? String(data.exception).split(":").slice(1).join(":").trim() : "") || fallback;
	}

	function post(method, args) {
		var body = new URLSearchParams();
		Object.keys(args).forEach(function (k) { body.append(k, args[k]); });
		return fetch(API + method, {
			method: "POST", credentials: "same-origin", body: body,
			headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" }
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (data) {
				if (!r.ok) throw new Error(message(data, "That did not go through. Try again."));
				return data.message;
			});
		});
	}

	function step(name) {
		Array.prototype.forEach.call(modal.querySelectorAll("[data-li-step]"), function (s) { s.hidden = s.dataset.liStep !== name; });
	}

	function say(text, tone) {
		status.textContent = text || "";
		status.hidden = !text;
		status.dataset.tone = tone || "";
	}

	function mode() {
		var picked = modal.querySelector('input[name="a3s-li-mode"]:checked');
		return picked ? picked.value : "add";
	}

	function open() {
		opener = document.activeElement;
		step("link"); say("");
		modal.hidden = false;
		url.focus();
	}

	function close() {
		/* Not while an import runs: it would stop half way. */
		if (running) return;
		modal.hidden = true;
		/* Leads went in or changed: the list shows them. */
		if (imported) { window.location.reload(); return; }
		if (opener && opener.focus) opener.focus();
	}

	/* 1. The sheet, checked: what each row will do. */
	function checkSheet() {
		if (!/^https:\/\/docs\.google\.com\/spreadsheets\//.test(url.value.trim())) {
			say("Paste the link of a Google Sheet - it starts with https://docs.google.com/spreadsheets/", "error");
			url.focus();
			return;
		}
		check.disabled = true;
		say("Reading the sheet…");
		var making = campaign.value === "__new__";
		if (making && !newCampaign.value.trim()) {
			say("Name the new campaign, or choose one from the list.", "error");
			newCampaign.focus(); check.disabled = false;
			return;
		}
		post("preview", { url: url.value.trim(), mode: mode(), campaign: making ? "" : campaign.value, new_campaign: making ? newCampaign.value.trim() : "" }).then(function (data) {
			preview = data;
			say("");
			showPreview(data);
		}).catch(function (e) { say(e.message, "error"); }).then(function () { check.disabled = false; });
	}

	function counts(box, parts) {
		box.textContent = "";
		parts.forEach(function (p) {
			if (!p[1] && !p[3]) return;
			var chip = el("span", "a3s-li__count a3s-li__count--" + p[0]);
			chip.appendChild(el("strong", "", String(p[1])));
			chip.appendChild(document.createTextNode(" " + p[2]));
			box.appendChild(chip);
		});
	}

	function showPreview(data) {
		var c = data.counts, adding = data.mode === "add";
		counts($("[data-li-counts]"), [
			["add", c.add, "to add", adding], ["update", c.update, "to update", !adding],
			["same", c.same, "unchanged"], ["skip", c.skip, "skipped"]
		]);
		var cols = $("[data-li-cols]");
		cols.textContent = "";
		cols.appendChild(el("span", "", "Columns read: "));
		cols.appendChild(el("strong", "", data.columns.join(", ") || "none"));
		if (data.ignored.length) cols.appendChild(el("span", "a3s-li__ignored", " · Left out: " + data.ignored.join(", ")));
		if (data.campaign) {
			cols.appendChild(el("span", "", " · Campaign: "));
			cols.appendChild(el("strong", "", data.campaign + (data.campaign_is_new ? " (new - made when you import)" : "")));
		}

		var body = $("[data-li-rows]");
		body.textContent = "";
		data.rows.forEach(function (r) {
			var tr = el("tr", "is-" + r.action);
			tr.appendChild(el("td", "a3s-li__rownum", String(r.row)));
			var who = el("td");
			who.appendChild(el("span", "a3s-li__who", r.title || "—"));
			if (r.lead) who.appendChild(el("small", "", r.lead));
			tr.appendChild(who);
			var will = el("td");
			will.appendChild(el("span", "a3s-li__badge a3s-li__badge--" + r.action, WILL[r.action]));
			tr.appendChild(will);
			var why = el("td", "a3s-li__why");
			why.textContent = r.errors.length ? r.errors.join(" ") : r.changes.length ? "Changes " + r.changes.join(", ") : r.action === "add" ? "New lead" : "Already as the sheet says";
			tr.appendChild(why);
			body.appendChild(tr);
		});
		var n = adding ? c.add : c.update;
		runBtn.disabled = !n;
		runBtn.textContent = n ? (adding ? "Add " : "Update ") + n + " lead" + (n === 1 ? "" : "s") : "Nothing to import";
		step("preview");
	}

	/* 3. The import, a batch at a time. */
	function runImport() {
		if (!preview || running) return;
		/* The campaign is offered first next time. */
		try { window.localStorage.setItem(LAST, campaign.value === "__new__" ? "" : campaign.value); } catch (e) { /* private window */ }
		running = true;
		runBtn.disabled = true;
		step("run");
		var failed = [], ok = 0, verb = preview.mode === "add" ? "Added" : "Updated";
		var bar = $("[data-li-bar]"), progress = $("[data-li-progress]"), finish = $("[data-li-finish]");
		finish.hidden = true;
		$("[data-li-failed]").hidden = true;
		$("[data-li-result-counts]").hidden = true;
		function batch(start) {
			progress.textContent = (preview.mode === "add" ? "Adding" : "Updating") + " leads… " + start + " of " + (preview.counts[preview.mode]);
			return post("run", { token: preview.token, start: start }).then(function (data) {
				data.results.forEach(function (r) { if (r.ok) ok += 1; else failed.push(r); });
				imported = ok;
				bar.style.width = (data.total ? Math.round(100 * data.next / data.total) : 100) + "%";
				if (!data.done) return batch(data.next);
				return data;
			});
		}
		batch(0).then(function () {
			progress.textContent = verb + " " + ok + " lead" + (ok === 1 ? "" : "s") + "." + (failed.length ? " " + failed.length + " could not be saved:" : "");
		}).catch(function (e) {
			progress.textContent = e.message + (ok ? " " + verb + " " + ok + " before it stopped." : "");
		}).then(function () {
			counts($("[data-li-result-counts]"), [["add", ok, preview.mode === "add" ? "added" : "updated", true], ["skip", failed.length, "not saved"]]);
			$("[data-li-result-counts]").hidden = false;
			var rows = $("[data-li-failed-rows]");
			rows.textContent = "";
			failed.forEach(function (r) {
				var tr = el("tr");
				tr.appendChild(el("td", "a3s-li__rownum", String(r.row)));
				tr.appendChild(el("td", "", r.lead || "—"));
				tr.appendChild(el("td", "a3s-li__why", r.error));
				rows.appendChild(tr);
			});
			$("[data-li-failed]").hidden = !failed.length;
			running = false;
			finish.hidden = false;
			finish.focus();
		});
	}

	document.addEventListener("click", function (e) {
		if (e.target.closest && e.target.closest("[data-lead-import-open]")) { e.preventDefault(); open(); }
	});
	Array.prototype.forEach.call(modal.querySelectorAll("[data-li-close]"), function (b) { b.addEventListener("click", close); });
	$("[data-li-finish]").addEventListener("click", close);
	$("[data-li-back]").addEventListener("click", function () { step("link"); url.focus(); });
	check.addEventListener("click", checkSheet);
	runBtn.addEventListener("click", runImport);
	url.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); checkSheet(); } });
	/* A changed choice or link is checked again before importing. */
	Array.prototype.forEach.call(modal.querySelectorAll('input[name="a3s-li-mode"]'), function (r) {
		r.addEventListener("change", function () { preview = null; say(""); });
	});
	url.addEventListener("input", function () { preview = null; });
	function campaignShown() {
		newField.hidden = campaign.value !== "__new__";
		if (!newField.hidden) newCampaign.focus();
	}
	campaign.addEventListener("change", function () { preview = null; campaignShown(); });
	try {
		var last = window.localStorage.getItem(LAST);
		if (last && campaign.querySelector('option[value="' + last.replace(/"/g, "") + '"]')) campaign.value = last;
	} catch (e) { /* private window */ }
	modal.addEventListener("click", function (e) { if (e.target === modal) close(); });
	document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) close(); });
})();
