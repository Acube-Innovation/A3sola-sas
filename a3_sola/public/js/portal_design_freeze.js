/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The design freeze pages (www/a3solaportal/projects/task.html, api/design_freeze): the job's
 * quotations; its site survey, with the survey's photographs; then the task's own side -
 * Solar Design Freeze: the material BOM, single line diagram and design images; Structural
 * Design Freeze: the structure BOM and structure drawing - and Freeze. A change is saved as it is made,
 * and the procurement tasks still in draft take the new BOM. Every step redraws the page
 * from the state the server returns.
 */
(function () {
	"use strict";

	var root = document.querySelector("[data-design]");
	if (!root) return;
	var API = "/api/method/a3_sola.api.design_freeze.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var installation = root.dataset.installation;
	var body = root.querySelector("[data-design-body]");
	var status = root.querySelector("[data-design-status]");
	var picker = root.querySelector("[data-design-file]");
	var state = JSON.parse(root.querySelector("[data-design-data]").textContent);
	var pickFor = "images";
	var taskCode = state.task.code;
	var structural = taskCode === "SDSGN";
	/* The single line diagram (or, structural, the structure drawing): one file, a PDF or an
	   image, filed under the task's documents. */
	var sldPicker = document.createElement("input");
	sldPicker.type = "file"; sldPicker.accept = "application/pdf,image/*"; sldPicker.hidden = true;
	root.appendChild(sldPicker);
	sldPicker.addEventListener("change", function () {
		if (!sldPicker.files.length) return;
		var form = new FormData();
		form.append("file", sldPicker.files[0]);
		form.append("installation", installation); form.append("task_code", taskCode);
		if (state.sld && state.sld.row && !state.sld.url) form.append("row", state.sld.row);
		else form.append("document_name", (state.sld && state.sld.name) || "Approved single line diagram");
		setStatus("Uploading the " + (structural ? "structure drawing" : "single line diagram") + "…");
		fetch("/api/method/a3_sola.api.portal_tasks.upload", { method: "POST", credentials: "same-origin", body: form,
			headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } })
			.then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(message(d, "Upload failed.")); }); })
			.then(function () { return call("state", {}); })
			.then(function (s) { apply(s, (structural ? "Structure drawing" : "Single line diagram") + " uploaded."); })
			.catch(function (err) { setStatus(err.message, "error"); });
		sldPicker.value = "";
	});

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}

	function message(data, fallback) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (msgs.length) return JSON.parse(msgs[0]).message.replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception ? String(data.exception).split(":").slice(1).join(":").trim() : "") || fallback;
	}

	function call(method, args, form) {
		form = form || new FormData();
		form.append("installation", installation);
		form.append("task_code", taskCode);
		Object.keys(args || {}).forEach(function (k) { form.append(k, args[k]); });
		return fetch(API + method, { method: "POST", credentials: "same-origin", body: form,
			headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } })
			.then(function (r) {
				return r.json().catch(function () { return {}; }).then(function (data) {
					if (!r.ok) throw new Error(message(data, "Something went wrong (" + r.status + ")."));
					return data.message || {};
				});
			});
	}

	function setStatus(text, tone) {
		status.textContent = text || "";
		status.dataset.tone = tone || "";
		status.hidden = !text;
	}

	function card(title, inner, extra) {
		return '<section class="a3s-card a3s-edit__card"><h3 class="a3s-edit__card-title">' + esc(title) +
			(extra ? ' <span class="a3s-edit__toggle-count">' + extra + "</span>" : "") + "</h3>" + inner + "</section>";
	}

	function select(name, current, choices, blank) {
		return '<select data-field="' + name + '"><option value="">' + esc(blank) + "</option>" +
			choices.map(function (c) {
				return '<option value="' + esc(c.value) + '"' + (c.value === current ? " selected" : "") + ">" + esc(c.label) + "</option>";
			}).join("") + "</select>";
	}

	function lines(rows) {
		if (!rows.length) return '<p class="a3s-field__hint">No lines.</p>';
		return '<div class="a3s-tablewrap"><table class="a3s-table"><thead><tr><th>Item</th><th>Qty</th><th>UOM</th></tr></thead><tbody>' +
			rows.map(function (l) {
				return "<tr><td>" + esc(l.item_name) + (l.item_code && l.item_code !== l.item_name ? ' <small class="a3s-field__hint">' + esc(l.item_code) + "</small>" : "") +
					(l.note ? '<br><small class="a3s-field__hint">' + esc(l.note) + "</small>" : "") +
					"</td><td>" + esc(l.qty) + (l.note ? "*" : "") + "</td><td>" + esc(l.uom || "") + "</td></tr>";
			}).join("") + "</tbody></table></div>";
	}

	function images(list, removable) {
		if (!list.length) return '<p class="a3s-field__hint">No images.</p>';
		return '<div class="a3s-dsgn__grid">' + list.map(function (i) {
			return '<figure class="a3s-dsgn__img"><a href="' + esc(i.url) + '" target="_blank" rel="noopener"><img src="' + esc(i.url) + '" alt="' + esc(i.caption) + '" loading="lazy"></a>' +
				(i.caption ? "<figcaption>" + esc(i.caption) + "</figcaption>" : "") +
				(removable && i.row ? '<button type="button" class="a3s-btn a3s-btn--ghost a3s-btn--sm" data-remove="' + esc(i.row) + '">Remove</button>' : "") +
				"</figure>";
		}).join("") + "</div>";
	}

	function bomCard(title, field, bom, frozen) {
		var inner = "";
		if (state.can_edit) {
			inner += '<div class="a3s-dsgn__pick">' + select(field, bom.value, bom.choices, "— the package's —") + "</div>";
		} else {
			inner += '<p class="a3s-field__hint">' + esc(bom.value || "None chosen") + "</p>";
		}
		if (!frozen && bom.value) inner += '<p class="a3s-field__hint">From the package; freezing the design keeps it on the job.</p>';
		return card(title, inner + lines(bom.lines), bom.lines.length ? bom.lines.length + " lines" : "");
	}

	function paint() {
		var s = state, t = s.task, html = "";
		var head = '<p class="a3s-taskdocs__meta">Status: <span class="a3s-taskdocs__state is-' + esc(t.status.toLowerCase().replace(/ /g, "-")) + '">' +
			esc(t.status) + "</span>" + (t.completed_on ? " · frozen " + esc(t.completed_on) + (t.completed_by ? " by " + esc(t.completed_by) : "") : "") + "</p>";
		if (s.can_freeze) {
			head += '<div class="a3s-form__actions"><button type="button" class="a3s-btn a3s-btn--primary" data-act="freeze">Freeze design</button></div>' +
				'<p class="a3s-field__hint">Freezing keeps the ' + (structural ? "structure" : "material") + ' BOM below on the job and completes the task. Everything here stays changeable afterwards.</p>';
		}
		html += card(t.name, head);

		var q = s.quotations;
		html += card("Quotations", q.length ? '<div class="a3s-tablewrap"><table class="a3s-table"><thead><tr><th>Quotation</th><th>Date</th><th>Option</th><th>Total</th><th>Status</th></tr></thead><tbody>' +
			q.map(function (r) {
				return '<tr><td><a href="' + esc(r.route) + '">' + esc(r.name) + "</a>" + (r.is_job ? ' <span class="a3s-pill a3s-pill--amber">This job</span>' : "") +
					"</td><td>" + esc(r.date) + "</td><td>" + esc(r.option) + "</td><td>" + esc(r.total) + "</td><td>" + esc(r.status) + "</td></tr>";
			}).join("") + "</tbody></table></div>" : '<p class="a3s-field__hint">No quotations on file.</p>', q.length ? String(q.length) : "");

		/* Listed as the quotations are: each opens its survey; another can be made the job's. */
		var sv = s.survey, survey = "";
		if (sv.surveys.length) {
			survey += '<div class="a3s-tablewrap"><table class="a3s-table"><thead><tr><th>Site survey</th><th>Date</th><th>Feasibility</th><th>Installable</th><th>Status</th><th></th></tr></thead><tbody>' +
				sv.surveys.map(function (r) {
					return '<tr><td><a href="' + esc(r.route) + '">' + esc(r.name) + "</a>" + (r.is_job ? ' <span class="a3s-pill a3s-pill--amber">This job</span>' : "") +
						"</td><td>" + esc(r.date) + "</td><td>" + esc(r.feasibility) + "</td><td>" + esc(r.capacity) + "</td><td>" + esc(r.status) + "</td><td>" +
						(!r.is_job && s.can_edit ? '<button type="button" class="a3s-btn a3s-btn--secondary a3s-btn--sm" data-use-survey="' + esc(r.name) + '">Use for this job</button>' : "") +
						"</td></tr>";
				}).join("") + "</tbody></table></div>";
			if (sv.name) survey += images(sv.images, false);
		} else {
			survey += '<p class="a3s-field__hint">No site survey on file for this customer.</p>' +
				(sv.create_route && s.can_edit ? '<div class="a3s-form__actions"><a class="a3s-btn a3s-btn--primary a3s-btn--sm" href="' + esc(sv.create_route) + '">Create site survey</a></div>' : "");
		}
		html += card("Site Survey", survey, sv.surveys.length ? String(sv.surveys.length) : "");

		if (s.structure_bom) html += bomCard("Structure BOM", "structure_bom", s.structure_bom, s.frozen.structure_bom);
		if (s.material_bom) html += bomCard("Material BOM", "material_bom", s.material_bom, s.frozen.material_bom);

		var sld = s.sld || {};
		html += card(structural ? "Structure Drawing" : "Single Line Diagram", '<ul class="a3s-taskdocs"><li class="a3s-taskdocs__row"><div class="a3s-taskdocs__info">' +
			'<p class="a3s-taskdocs__name">' + esc(sld.name) + "</p>" +
			'<p class="a3s-taskdocs__meta"><span class="a3s-taskdocs__state is-' + (sld.url ? "uploaded" : "missing") + '">' + (sld.url ? "Uploaded" : "Missing") +
			"</span> " + (structural ? "The structure the crew erects, for the structure BOM above." : "Sent to the electrical contractor with the Installation work order.") + "</p></div>" +
			'<div class="a3s-taskdocs__actions">' +
			(sld.url ? '<a class="a3s-btn a3s-btn--secondary a3s-btn--sm" href="' + esc(sld.url) + '" target="_blank" rel="noopener">Open</a>' : "") +
			(s.can_edit ? '<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-act="sld">' + (sld.url ? "Replace" : "Upload") + "</button>" : "") +
			"</div></li></ul>");

		if (s.images) {
			var imgs = images(s.images, s.can_edit);
			if (s.can_edit) imgs += '<div class="a3s-dsgn__pick"><input type="text" data-caption placeholder="Caption (optional), e.g. Module layout">' +
				'<button type="button" class="a3s-btn a3s-btn--primary a3s-btn--sm" data-act="upload">Upload images</button>' +
				'<span class="a3s-field__hint">Up to ' + esc(s.max_file_mb) + " MB each.</span></div>";
			html += card("Design Images", imgs, s.images.length ? String(s.images.length) : "");
		}

		if (s.procurement.length) {
			html += card("Procurement", '<ul class="a3s-taskdocs">' + s.procurement.map(function (p) {
				var note = p.locked ? "Submitted - keeps the list it was bought with." : (p.document ? "Draft - follows the BOMs above." : "Not started - will start from the BOMs above.");
				return '<li class="a3s-taskdocs__row"><div class="a3s-taskdocs__info"><p class="a3s-taskdocs__name">' + esc(p.name) + "</p>" +
					'<p class="a3s-taskdocs__meta">' + esc(p.status) + " · " + esc(note) + "</p></div></li>";
			}).join("") + "</ul>");
		}
		body.innerHTML = html;
	}

	function apply(s, done) {
		state = s; paint();
		var updated = (s.updated_tasks || []).length;
		setStatus(done + (updated ? " " + updated + " procurement task" + (updated === 1 ? "" : "s") + " updated." : ""), "ok");
	}

	body.addEventListener("change", function (e) {
		var field = e.target.dataset && e.target.dataset.field;
		if (!field) return;
		var args = {};
		args[field === "structure_bom" ? "structure_bom_name" : field] = e.target.value;
		setStatus("Saving…");
		call("save", args).then(function (s) { apply(s, "Saved."); }).catch(function (err) { setStatus(err.message, "error"); paint(); });
	});

	body.addEventListener("click", function (e) {
		var act = e.target.closest("[data-act]"), remove = e.target.closest("[data-remove]");
		var use = e.target.closest("[data-use-survey]");
		if (use) {
			setStatus("Saving…");
			call("save", { site_survey: use.dataset.useSurvey }).then(function (s) { apply(s, "Site survey set for this job."); })
				.catch(function (err) { setStatus(err.message, "error"); });
		}
		if (remove) {
			setStatus("Removing…");
			call("remove_image", { row: remove.dataset.remove }).then(function (s) { apply(s, "Removed."); })
				.catch(function (err) { setStatus(err.message, "error"); });
		}
		if (!act) return;
		if (act.dataset.act === "upload") { pickFor = "images"; picker.click(); }
		if (act.dataset.act === "sld") { pickFor = "sld"; sldPicker.click(); }
		if (act.dataset.act === "freeze") {
			setStatus("Freezing…");
			call("freeze").then(function (s) { apply(s, "Design frozen."); }).catch(function (err) { setStatus(err.message, "error"); });
		}
	});

	picker.addEventListener("change", function () {
		if (!picker.files.length) return;
		var form = new FormData();
		Array.prototype.forEach.call(picker.files, function (f) { form.append("file", f, f.name); });
		var caption = body.querySelector("[data-caption]");
		setStatus("Uploading…");
		call("add_image", { caption: caption ? caption.value : "" }, form)
			.then(function (s) { apply(s, "Uploaded."); }).catch(function (err) { setStatus(err.message, "error"); });
		picker.value = "";
	});

	paint();
})();
