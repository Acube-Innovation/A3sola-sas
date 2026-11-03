/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The Attachments card (templates/includes/portal_attachments.html), a child table of the
 * record's files: each row says what the file is - KSEB Bill, Aadhaar Front, PAN, ... -
 * and can be retyped or removed; new files are uploaded, picked or dropped, as the type
 * chosen above them. All of it goes straight onto the record through
 * a3_sola.api.portal_attachments, and the Snapshot's Attachments count follows.
 */
(function () {
	"use strict";

	var API = "/api/method/a3_sola.api.portal_attachments.";
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var SVG = "http://www.w3.org/2000/svg";

	function message(data, fallback) {
		try {
			var msgs = JSON.parse((data && data._server_messages) || "[]");
			if (msgs.length) return JSON.parse(msgs[0]).message.replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (data && data.exception ? String(data.exception).split(":").slice(1).join(":").trim() : "") || fallback;
	}

	function size(bytes) {
		if (!bytes) return "";
		if (bytes < 1024) return bytes + " B";
		if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
		return (bytes / (1024 * 1024)).toFixed(1) + " MB";
	}

	/* The badge on a row: what kind of file it is, read off its extension. */
	function kind(fileName) {
		var ext = (String(fileName).split(".").pop() || "").toLowerCase();
		if (ext === "pdf") return { label: "PDF", tone: "pdf" };
		if (["png", "jpg", "jpeg", "webp", "gif", "heic", "bmp", "svg"].indexOf(ext) !== -1) return { label: "IMG", tone: "img" };
		if (["doc", "docx", "odt", "rtf", "txt"].indexOf(ext) !== -1) return { label: "DOC", tone: "doc" };
		if (["xls", "xlsx", "ods", "csv"].indexOf(ext) !== -1) return { label: "XLS", tone: "xls" };
		return { label: ext ? ext.slice(0, 4).toUpperCase() : "FILE", tone: "file" };
	}

	function call(method, body, isGet) {
		var opts = { credentials: "same-origin", headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" } };
		var url = API + method;
		if (isGet) url += "?" + new URLSearchParams(body).toString();
		else { opts.method = "POST"; opts.body = body; }
		return fetch(url, opts).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (data) {
				if (!r.ok) throw new Error(message(data, "Something went wrong (" + r.status + ")."));
				return data.message || {};
			});
		});
	}

	function el(tag, cls, text) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text != null) n.textContent = text;
		return n;
	}

	function icon(id) {
		var svg = document.createElementNS(SVG, "svg");
		svg.setAttribute("class", "a3s-ic");
		svg.setAttribute("aria-hidden", "true");
		var use = document.createElementNS(SVG, "use");
		use.setAttribute("href", "#" + id);
		svg.appendChild(use);
		return svg;
	}

	function fillTypes(select, types, value, blank) {
		select.textContent = "";
		var none = el("option", "", blank); none.value = ""; select.appendChild(none);
		types.forEach(function (t) {
			var o = el("option", "", t); o.value = t;
			if (t === value) o.selected = true;
			select.appendChild(o);
		});
	}

	/* Documents read as they are picked, filling the form's fields: {doctype: {type: method}}.
	   The Jan Samarth letter gives the task its reference and approval date. */
	var READERS = {
		"Installation Task": { "Digital Approval Letter": "a3_sola.api.approval_letter.read" },
		"Portal Application": { "PM Surya Ghar Acknowledgement": "a3_sola.api.portal_ack.read" }
	};
	var LABELS = { approval_reference: "Jan Samarth Reference", approval_received_on: "Approval Received On",
		application_number: "Application Number", application_date: "Application Date",
		national_portal_application_id: "National Portal Application ID" };

	/* A field is filled only while blank, or still as this reader last filled it. */
	function fillFields(fields) {
		var filled = [];
		Object.keys(fields || {}).forEach(function (name) {
			var input = document.getElementById("fld-" + name);
			if (!input || (input.value && input.value !== input.dataset.readFilled)) return;
			input.value = fields[name];
			input.dataset.readFilled = fields[name];
			input.dispatchEvent(new Event("input", { bubbles: true }));
			input.dispatchEvent(new Event("change", { bubbles: true }));
			filled.push((LABELS[name] || name) + " " + fields[name]);
		});
		return filled;
	}

	Array.prototype.forEach.call(document.querySelectorAll("[data-attach]"), function (card) {
		var doctype = card.dataset.doctype, name = card.dataset.name;
		var list = card.querySelector("[data-attach-list]");
		var table = card.querySelector("[data-attach-table]");
		var empty = card.querySelector("[data-attach-empty]");
		var count = card.querySelector("[data-attach-count]");
		var drop = card.querySelector("[data-attach-new]");
		var hint = card.querySelector("[data-attach-hint]");
		var typeSelect = card.querySelector("[data-attach-type]");
		var input = card.querySelector("[data-attach-input]");
		var button = card.querySelector("[data-attach-upload]");
		var status = card.querySelector("[data-attach-status]");
		var types = [];
		var busy = false;
		/* A record not yet created (data-held): the files picked wait here, as rows, and go up
		   once the form has created it - window.a3sAttachHeld. */
		var held = card.hasAttribute("data-held") ? [] : null;

		/* tone: "" for progress, "ok" or "error". */
		function setStatus(text, tone) {
			status.textContent = text || "";
			status.hidden = !text;
			status.dataset.tone = tone || "";
		}

		function form(extra) {
			var body = new FormData();
			body.append("doctype", doctype); body.append("name", name);
			Object.keys(extra || {}).forEach(function (k) { body.append(k, extra[k]); });
			return body;
		}

		function row(f) {
			var tr = el("div", "a3s-attach__row"); tr.setAttribute("role", "row");

			var fileCell = el("span", "a3s-attach__file"); fileCell.setAttribute("role", "cell");
			var k = kind(f.file_name);
			fileCell.appendChild(el("span", "a3s-attach__badge a3s-attach__badge--" + k.tone, k.label));
			var text = el("span", "a3s-attach__text");
			var a = el("a", "a3s-attach__name", f.file_name);
			var openUrl = f.file_url || (f.file && window.URL ? (f.blobUrl = f.blobUrl || URL.createObjectURL(f.file)) : "");
			if (openUrl) { a.href = openUrl; a.target = "_blank"; a.rel = "noopener"; a.title = "Open " + f.file_name; }
			text.appendChild(a);
			text.appendChild(el("span", "a3s-attach__meta", [size(f.size), f.by, f.on].filter(Boolean).join(" · ")));
			fileCell.appendChild(text);
			tr.appendChild(fileCell);

			/* A saved file's type is fixed, so it reads as a label. Only a file filed before
			   types existed still has none, and gets one chosen - once. */
			var typeCell = el("span", "a3s-attach__type"); typeCell.setAttribute("role", "cell");
			if (f.document_type) {
				var tag = el("span", "a3s-attach__tag", f.document_type);
				tag.title = "Filed as " + f.document_type;
				typeCell.appendChild(tag);
			} else if (f.can_remove) {
				var pick = el("select", "a3s-attach__select a3s-attach__select--row is-unset");
				pick.setAttribute("aria-label", "Document type of " + f.file_name);
				fillTypes(pick, types, "", "Set document type…");
				pick.addEventListener("change", function () {
					if (!pick.value) return;
					if (!window.confirm("File " + f.file_name + " as " + pick.value + "? It cannot be changed afterwards.")) { pick.value = ""; return; }
					setStatus("Saving…");
					call("set_type", form({ file: f.name, document_type: pick.value }))
						.then(function (data) { paint(data.files || [], true); setStatus(f.file_name + " is filed as " + pick.value + ".", "ok"); })
						.catch(function (e) { pick.value = ""; setStatus(e.message, "error"); });
				});
				typeCell.appendChild(pick);
			} else {
				typeCell.appendChild(el("span", "a3s-attach__tag is-unset", "Not set"));
			}
			tr.appendChild(typeCell);

			var act = el("span", "a3s-attach__act"); act.setAttribute("role", "cell");
			/* View opens the file in a new tab, as its name does - one not uploaded yet from
			   the browser's own copy of it. */
			var viewUrl = f.file_url || (f.file && window.URL ? (f.blobUrl = f.blobUrl || URL.createObjectURL(f.file)) : "");
			if (viewUrl) {
				var view = el("a", "a3s-attach__remove a3s-attach__view");
				view.href = viewUrl; view.target = "_blank"; view.rel = "noopener";
				view.title = "View " + f.file_name;
				view.setAttribute("aria-label", "View " + f.file_name);
				view.appendChild(icon("ic-eye"));
				act.appendChild(view);
			}
			if (f.held) {
				var drop1 = el("button", "a3s-attach__remove");
				drop1.type = "button"; drop1.title = "Remove " + f.file_name;
				drop1.setAttribute("aria-label", "Remove " + f.file_name);
				drop1.appendChild(icon("ic-trash"));
				drop1.addEventListener("click", function () {
					held.splice(held.indexOf(f), 1);
					paint(held);
				});
				act.appendChild(drop1);
			} else if (f.can_remove) {
				var x = el("button", "a3s-attach__remove");
				x.type = "button"; x.title = "Remove " + f.file_name;
				x.setAttribute("aria-label", "Remove " + f.file_name);
				x.appendChild(icon("ic-trash"));
				x.addEventListener("click", function () {
					if (!window.confirm("Remove " + f.file_name + " from " + name + "?")) return;
					setStatus("Removing…");
					call("remove", form({ file: f.name }))
						.then(function (data) { paint(data.files || [], true); setStatus("Removed " + f.file_name + ".", "ok"); })
						.catch(function (e) { setStatus(e.message, "error"); });
				});
				act.appendChild(x);
			}
			tr.appendChild(act);
			return tr;
		}

		function paint(files, changed) {
			list.textContent = "";
			files.forEach(function (f) { list.appendChild(row(f)); });
			table.hidden = !files.length;
			empty.hidden = files.length > 0;
			count.hidden = !files.length;
			count.textContent = files.length + " file" + (files.length === 1 ? "" : "s");
			// The Snapshot tile counts the same files.
			Array.prototype.forEach.call(document.querySelectorAll("[data-attachment-count]"), function (n) {
				n.textContent = String(files.length);
			});
			// The KYC Documents card counts the same files (portal_kyc.js).
			if (changed) document.dispatchEvent(new CustomEvent("a3s:attachments-changed", { detail: { doctype: doctype, name: name } }));
		}

		function needType() {
			if (typeSelect.value) return false;
			setStatus("Choose the document type first.", "error");
			typeSelect.classList.add("is-invalid");
			typeSelect.focus();
			return true;
		}

		/* Read the first file picked, where its type has a reader, into the form's fields. */
		function readInto(file, what) {
			var method = (READERS[doctype] || {})[what];
			if (!method || !file) return;
			var body = new FormData();
			body.append("file", file, file.name);
			/* The job it is for - the new task's, posted with its form - or the task itself,
			   so a letter naming someone else is caught. */
			var source = document.querySelector('#a3s-record-edit-form [name="source"]');
			if (source && source.value) body.append("installation", source.value);
			if (name) body.append("task", name);
			fetch("/api/method/" + method, {
				method: "POST", credentials: "same-origin",
				headers: { "X-Frappe-CSRF-Token": csrf, Accept: "application/json" }, body: body
			}).then(function (r) { return r.json().catch(function () { return {}; }); }).then(function (data) {
				var fields = (data && data.message && data.message.fields) || {};
				var warned = (data && data.message && data.message.warnings) || [];
				var filled = fillFields(fields);
				/* Said after what the upload said, whichever answered first. */
				var before = status.dataset.tone === "ok" && !status.hidden ? status.textContent + " " : "";
				var said = filled.length ? "Read from the " + what + ": " + filled.join(", ") + "." : "";
				/* A letter naming someone other than the job's customer: said, and shown as a warning. */
				if (warned.length) setStatus([before + said].concat(warned).join(" ").trim(), "warn");
				else if (filled.length) setStatus(before + said, "ok");
				else if (!Object.keys(fields).length) setStatus("The " + what + " was kept, but its details could not be read. Enter them above.", "error");
			}).catch(function () { /* the file is still attached; the fields are typed */ });
		}

		function upload(files) {
			if (!files || !files.length || busy || needType()) return;
			readInto(files[files.length - 1], typeSelect.value);
			var body = form({ document_type: typeSelect.value });
			Array.prototype.forEach.call(files, function (file) { body.append("file", file, file.name); });
			var n = files.length, what = typeSelect.value;
			var label = n + " file" + (n === 1 ? "" : "s");
			if (held) {
				Array.prototype.forEach.call(files, function (file) {
					held.push({ held: true, file: file, file_name: file.name, size: file.size, document_type: what, by: "Uploads when saved" });
				});
				paint(held);
				setStatus(label + " added as " + what + ". They upload when you save.", "ok");
				typeSelect.value = ""; input.value = "";
				return;
			}
			busy = true; button.disabled = true; drop.classList.add("is-busy");
			setStatus("Uploading " + label + " as " + what + "…");
			call("upload", body).then(function (data) {
				paint(data.files || [], true);
				setStatus("Uploaded " + label + " as " + what + ".", "ok");
				typeSelect.value = "";
			}).catch(function (e) { setStatus(e.message, "error"); }).then(function () {
				busy = false; button.disabled = false; drop.classList.remove("is-busy"); input.value = "";
			});
		}

		typeSelect.addEventListener("change", function () {
			typeSelect.classList.remove("is-invalid");
			if (status.dataset.tone === "error" && typeSelect.value) setStatus("");
		});
		button.addEventListener("click", function () { if (!needType()) input.click(); });
		input.addEventListener("change", function () { upload(input.files); });

		/* Files dropped on the panel upload as the type chosen in it. */
		["dragenter", "dragover"].forEach(function (ev) {
			drop.addEventListener(ev, function (e) {
				if (!e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") === -1) return;
				e.preventDefault(); drop.classList.add("is-dragging");
			});
		});
		["dragleave", "dragend"].forEach(function (ev) {
			drop.addEventListener(ev, function (e) {
				if (ev === "dragleave" && drop.contains(e.relatedTarget)) return;
				drop.classList.remove("is-dragging");
			});
		});
		drop.addEventListener("drop", function (e) {
			e.preventDefault(); drop.classList.remove("is-dragging");
			upload(e.dataTransfer && e.dataTransfer.files);
		});

		/* A file uploaded elsewhere on the page - the KYC Documents card - is listed here too. */
		document.addEventListener("a3s:attachments-reload", function (e) {
			if (!e.detail || e.detail.doctype !== doctype || e.detail.name !== name) return;
			call("list_files", { doctype: doctype, name: name }, true).then(function (data) { paint(data.files || []); });
		});

		/* Held files go up to the record the form has just created, a call per type. */
		if (held) window.a3sAttachHeld = function (newName) {
			var byType = {};
			held.forEach(function (f) { (byType[f.document_type] = byType[f.document_type] || []).push(f.file); });
			return Object.keys(byType).reduce(function (chain, what) {
				return chain.then(function () {
					var body = new FormData();
					body.append("doctype", doctype); body.append("name", newName); body.append("document_type", what);
					byType[what].forEach(function (file) { body.append("file", file, file.name); });
					return call("upload", body);
				});
			}, Promise.resolve());
		};
		if (held) window.a3sAttachHeld.count = function () { return held.length; };

		/* A new task's record, opened from the project board: the task's own documents are offered too. */
		var from = new URLSearchParams(window.location.search);
		var heldArgs = { doctype: doctype };
		if (from.get("source_dt") === "Solar Installation" && from.get("source") && from.get("task")) {
			heldArgs.installation = from.get("source"); heldArgs.task = from.get("task");
		}
		(held ? call("held_card", heldArgs, true) : call("list_files", { doctype: doctype, name: name }, true)).then(function (data) {
			types = data.document_types || [];
			fillTypes(typeSelect, types, "", "Document type…");
			if (data.max_file_mb) hint.textContent = "Pick a document type, then choose or drop files. Up to " + data.max_file_mb + " MB each.";
			paint(data.files || []);
			drop.hidden = !data.can_upload;
		}).catch(function (e) { setStatus(e.message, "error"); });
	});

	/* The Snapshot's Attachments tile opens this panel: scrolled to, flashed, focused. Bound
	   once, whichever page includes the card. */
	if (!window.a3sAttachJump) {
		window.a3sAttachJump = true;
		document.addEventListener("click", function (e) {
			var tile = e.target.closest && e.target.closest("[data-attach-jump]");
			var panel = tile && document.getElementById("a3s-attachments");
			if (!panel) return;
			e.preventDefault();
			var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
			panel.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
			panel.focus({ preventScroll: true });
			panel.classList.remove("is-flash");
			void panel.offsetWidth; // restart the flash on a second click
			panel.classList.add("is-flash");
		});
	}
})();
