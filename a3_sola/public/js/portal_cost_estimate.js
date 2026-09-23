/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The cost estimate builder. Packages and their bill of materials on the left, a
 * point-of-sale cost panel on the right. The panel never prices anything itself: every
 * change posts the draft to the server, ERPNext prices, discounts and taxes it, and the
 * numbers that come back are the numbers the saved Quotation will carry.
 */
(function () {
	"use strict";

	var root = document.getElementById("a3s-ce");
	var dataEl = document.getElementById("a3s-ce-data");
	if (!root || !dataEl) return;

	var data = JSON.parse(dataEl.textContent || "{}");
	var cat = data.catalogue || {};
	var readonly = !!root.dataset.readonly;
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var API = "/api/method/a3_sola.api.cost_estimate.";
	var SETTINGS_TERMS = "__settings";
	var CUSTOM_TERMS = "__custom";
	var SOLAR_LINKS = ["solar_consumer", "solar_design_estimate", "selected_option", "subsidy_eligibility_check", "solar_proposal", "solar_package"];
	var FINANCE = ["is_financed", "lender", "lender_branch", "loan_scheme", "jan_samarth_id", "loan_sanction_no", "sanctioned_amount", "finance_status"];

	var money = (function () {
		var f;
		try { f = new Intl.NumberFormat("en-IN", { style: "currency", currency: cat.currency || "INR", maximumFractionDigits: 2 }); } catch (e) { f = null; }
		return function (v) { v = Number(v) || 0; return f ? f.format(v) : v.toFixed(2); };
	})();
	function num(v, d) { return (Number(v) || 0).toLocaleString("en-IN", { maximumFractionDigits: d === undefined ? 2 : d }); }
	function esc(s) { return String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
	function el(id) { return document.getElementById(id); }
	function addDays(iso, days) {
		var d = new Date(iso + "T00:00:00");
		if (isNaN(d.getTime())) return iso;
		d.setDate(d.getDate() + (Number(days) || 0));
		return d.toISOString().slice(0, 10);
	}
	function debounce(fn, ms) { var t; return function () { clearTimeout(t); var a = arguments; t = setTimeout(function () { fn.apply(null, a); }, ms); }; }

	/* ------------------------------------------------------------- state */
	var state = {
		name: null, docstatus: 0, status: null,
		quotation_to: "Lead", party_name: "", party_label: "",
		transaction_date: cat.today, valid_till: addDays(cat.today, cat.validity_days || 30),
		taxes_and_charges: cat.default_tax_template || "",
		discount_type: "amount", discount: 0,
		items: [],
		solar: {},
		terms: { tc_name: "", html: "", notes: "", dirty: false },
		refs: null, parties: data.parties || [], summary: null,
	};
	SOLAR_LINKS.concat(FINANCE).forEach(function (f) { state.solar[f] = null; });
	state.solar.finance_status = "Not Applied";
	// Opened from the record the chain led here from: the links it carries across are
	// seeded so the builder starts already attached to the proposal it prices.
	SOLAR_LINKS.forEach(function (f) {
		if (data.prefill && data.prefill[f]) state.solar[f] = data.prefill[f];
	});
	var firstTerms = (cat.terms_templates || [])[0];
	if (firstTerms) { state.terms.tc_name = firstTerms.name; state.terms.html = firstTerms.terms || ""; }

	/* -------------------------------------------------------------- api */
	function call(method, args) {
		return fetch(API + method, {
			method: "POST", credentials: "same-origin",
			headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
			body: JSON.stringify(args || {}),
		}).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (d) {
				if (r.ok && d && d.message !== undefined) return d.message;
				var err = new Error(serverMessage(d) || (r.status === 403 ? "You do not have permission to do that." : "The server could not process the request."));
				err.code = r.status;
				throw err;
			});
		});
	}
	function serverMessage(d) {
		try {
			var msgs = JSON.parse((d && d._server_messages) || "[]");
			if (msgs.length) {
				var first = JSON.parse(msgs[0]);
				if (first && first.message) return String(first.message).replace(/<[^>]*>/g, "");
			}
		} catch (e) { /* fall through */ }
		if (d && d.exception) return String(d.exception).split(":").slice(1).join(":").trim() || String(d.exception);
		return "";
	}
	function setMsg(text, kind) {
		var m = el("ce-msg");
		m.textContent = text || "";
		m.classList.toggle("is-error", kind === "error");
		m.classList.toggle("is-success", kind === "success");
	}

	/* ----------------------------------------------------------- payload */
	function payload() {
		var out = {
			quotation_to: state.quotation_to, party_name: state.party_name,
			transaction_date: state.transaction_date, valid_till: state.valid_till,
			order_type: "Sales", taxes_and_charges: state.taxes_and_charges, apply_discount_on: "Grand Total",
			additional_discount_percentage: state.discount_type === "percent" ? Number(state.discount) || 0 : 0,
			discount_amount: state.discount_type === "amount" ? Number(state.discount) || 0 : 0,
			items: state.items.map(function (it) {
				return { item_code: it.item_code, item_name: it.item_name, description: it.description, qty: it.qty, rate: it.rate, uom: it.uom, solar_package: it.solar_package, package_option: it.package_option };
			}),
		};
		SOLAR_LINKS.concat(FINANCE).forEach(function (f) { out[f] = state.solar[f]; });
		if (state.terms.dirty) {
			out.tc_name = (state.terms.tc_name && state.terms.tc_name.indexOf("__") !== 0) ? state.terms.tc_name : "";
			out.terms = composeTerms();
		}
		return out;
	}
	function composeTerms() {
		var lines = String(state.terms.notes || "").split(/\r?\n/).map(function (s) { return s.trim(); }).filter(Boolean);
		var extra = lines.length ? "<ul>" + lines.map(function (l) { return "<li>" + esc(l) + "</li>"; }).join("") + "</ul>" : "";
		return (state.terms.html || "") + extra;
	}

	/* ----------------------------------------------------------- preview */
	var preview = debounce(function () {
		if (!state.items.length) { state.summary = null; renderTotals(); renderSolarFacts(); return; }
		if (!state.party_name) {
			// Price without a party by pretending: the server needs one, so show the
			// subtotal locally and ask for the lead.
			renderTotals(); setMsg("Choose who this estimate is for to see GST and totals.", ""); return;
		}
		call("preview", { payload: payload() }).then(function (s) {
			state.summary = s; setMsg("");
			renderTotals(); renderSolarFacts();
		}).catch(function (e) { setMsg(e.message, "error"); });
	}, 300);

	function changed() {
		renderLines();
		if (!readonly) preview();
	}

	/* ----------------------------------------------------------- catalogue */
	function packageOf(name) { return (cat.packages || []).find(function (p) { return p.name === name; }); }

	function renderPackages() {
		var q = (el("ce-filter").value || "").trim().toLowerCase();
		var wrap = el("ce-packages");
		var suggested = state.refs && state.refs.party ? Number(state.refs.party.capacity_kw) || 0 : 0;
		var added = {};
		state.items.forEach(function (it) { if (it.solar_package) added[it.solar_package] = true; });
		var html = (cat.packages || []).filter(function (p) {
			if (!q) return true;
			var hay = [p.package_name, p.specification_code, p.capacity_kw + " kw", p.connection_type, p.inverter_topology]
				.concat((p.options || []).map(function (o) { return o.inverter_make; })).join(" ").toLowerCase();
			return hay.indexOf(q) !== -1;
		}).map(function (p) {
			var tags = [
				p.connection_type ? '<span class="a3s-pkg__tag">' + esc(p.connection_type) + "</span>" : "",
				p.system_type ? '<span class="a3s-pkg__tag a3s-pkg__tag--sky">' + esc(p.system_type) + "</span>" : "",
				p.is_dcr_compliant ? '<span class="a3s-pkg__tag a3s-pkg__tag--green">DCR</span>' : "",
				suggested && Math.abs(Number(p.capacity_kw) - suggested) < 0.01 ? '<span class="a3s-pkg__tag a3s-pkg__tag--amber">Suggested for this lead</span>' : "",
			].join("");
			var options = (p.options || []).map(function (o) {
				return '<div class="a3s-pkg__opt">' +
					'<span class="a3s-pkg__opt-name">' + esc(o.label) + (o.inverter_make ? " &middot; " + esc(o.inverter_make) : "") +
					'<small>' + esc(o.inverter_specification || "") + "</small></span>" +
					'<span class="a3s-pkg__opt-price">' + (o.rate ? money(o.rate) : '<small class="a3s-muted">price on save</small>') + "</span>" +
					(readonly ? "" : '<button type="button" class="a3s-pkg__add" data-add-package="' + esc(p.name) + '" data-option="' + o.option + '">Add</button>') +
					"</div>";
			}).join("");
			if (!options && !readonly) {
				options = '<div class="a3s-pkg__opt"><span class="a3s-pkg__opt-name">Package</span><span class="a3s-pkg__opt-price">' + money(p.net_rate) + '</span><button type="button" class="a3s-pkg__add" data-add-package="' + esc(p.name) + '" data-option="0">Add</button></div>';
			}
			var bom = p.bom_items && p.bom_items.length
				? p.bom_items.map(function (b) { return "<li><span><span class=\"a3s-bom__type\">" + esc(b.item_name || b.item_code) + "</span></span><span class=\"a3s-bom__qty\">" + num(b.qty) + " " + esc(b.uom || "") + "</span></li>"; }).join("")
				: (p.components || []).map(function (c) {
					return "<li><span><span class=\"a3s-bom__type\">" + esc(c.component_type) + (c.make ? " &middot; " + esc(c.make) : "") + "</span>" +
						(c.specification ? '<span class="a3s-bom__spec">' + esc(c.specification) + "</span>" : "") + "</span>" +
						'<span class="a3s-bom__qty">' + num(c.qty) + " " + esc(c.uom || "") + "</span></li>";
				}).join("");
			var meta = [
				p.module_count ? p.module_count + " &times; " + num(p.module_wattage, 0) + " Wp " + esc(p.module_make_name || "") : "",
				p.area_required_sqft ? num(p.area_required_sqft, 0) + " sq ft" : "",
				p.expected_daily_units_low ? num(p.expected_daily_units_low, 0) + "&ndash;" + num(p.expected_daily_units_high, 0) + " units/day" : "",
				p.indicative_subsidy ? "Subsidy " + money(p.indicative_subsidy) : "",
			].filter(Boolean).map(function (m) { return "<span>" + m + "</span>"; }).join("");
			return '<article class="a3s-pkg' + (added[p.name] ? " is-added" : "") + '" data-package="' + esc(p.name) + '">' +
				'<div class="a3s-pkg__top"><span class="a3s-pkg__kw">' + num(p.capacity_kw, 1) + "<small>kWp</small></span><span class=\"a3s-pkg__tags\">" + tags + "</span></div>" +
				'<p class="a3s-pkg__name">' + esc(p.package_name) + " <small>" + esc(p.specification_code) + "</small></p>" +
				'<div class="a3s-pkg__meta">' + meta + "</div>" +
				'<div class="a3s-pkg__options">' + options + "</div>" +
				(bom ? '<details class="a3s-pkg__bom"><summary><svg class="a3s-ic" aria-hidden="true"><use href="#ic-clipboard"></use></svg> Bill of materials (' + ((p.bom_items && p.bom_items.length) || (p.components || []).length) + ")</summary><ul class=\"a3s-bom\">" + bom + "</ul></details>" : "") +
				"</article>";
		}).join("");
		wrap.innerHTML = html || '<p class="a3s-pos__empty">No packages match. <a href="/app/solar-package" target="_blank" rel="noopener">Define packages in ERPNext</a>.</p>';
	}

	function renderAddons() {
		var wrap = el("ce-addons");
		var list = cat.addons || [];
		if (!list.length) { wrap.innerHTML = '<p class="a3s-pos__empty">No add-on items yet. Sales items you create in ERPNext appear here.</p>'; return; }
		wrap.innerHTML = list.map(function (a) {
			return '<div class="a3s-addon">' +
				'<span class="a3s-addon__name">' + esc(a.item_name) + "<small>" + esc(a.item_group || "") + (a.description ? " &middot; " + esc(a.description) : "") + "</small></span>" +
				'<span class="a3s-pkg__opt-price">' + (a.rate ? money(a.rate) : '<small class="a3s-muted">set price</small>') + "</span>" +
				(readonly ? "" : '<button type="button" class="a3s-pkg__add" data-add-item="' + esc(a.item_code) + '">Add</button>') +
				"</div>";
		}).join("");
	}

	function addPackage(name, optionNo) {
		var p = packageOf(name);
		if (!p) return;
		var opt = (p.options || []).find(function (o) { return String(o.option) === String(optionNo); });
		var key = name + "#" + (opt ? opt.option : 0);
		var existing = state.items.find(function (it) { return it.key === key; });
		if (existing) { existing.qty += 1; changed(); return; }
		state.items.push({
			key: key, item_code: p.item || "", item_name: p.package_name, solar_package: p.name,
			package_option: opt ? opt.label + (opt.inverter_make ? " - " + opt.inverter_make : "") : "",
			description: p.package_name + (opt ? " with " + (opt.inverter_make ? opt.inverter_make + " " : "") + "inverter (" + opt.label + ")" : "") +
				(p.module_count ? ". " + p.module_count + " x " + num(p.module_wattage, 0) + " Wp modules" : "") +
				(p.warranty_years ? ", " + p.warranty_years + " year system warranty" : "") + ".",
			qty: 1, rate: opt ? Number(opt.rate) || 0 : Number(p.net_rate) || 0, uom: "Nos",
		});
		if (!state.solar.solar_package) { state.solar.solar_package = p.name; syncSolarControls(); }
		changed(); renderPackages();
		switchTab("items");
	}

	function addItem(code) {
		var a = (cat.addons || []).find(function (x) { return x.item_code === code; });
		if (!a) return;
		var existing = state.items.find(function (it) { return it.key === "item:" + code; });
		if (existing) { existing.qty += 1; changed(); return; }
		state.items.push({ key: "item:" + code, item_code: a.item_code, item_name: a.item_name, description: a.description || a.item_name, qty: 1, rate: Number(a.rate) || 0, uom: a.uom || "Nos", solar_package: null, package_option: null });
		changed();
	}

	/* ------------------------------------------------------------ lines */
	function renderLines() {
		var wrap = el("ce-lines");
		el("ce-tab-items-n").textContent = state.items.length;
		el("ce-count").textContent = state.items.length ? state.items.length + (state.items.length === 1 ? " line" : " lines") : "";
		if (!state.items.length) {
			wrap.innerHTML = '<p class="a3s-pos__empty">Nothing added yet. Pick a package on the left.</p>';
			el("ce-save").disabled = true;
			return;
		}
		el("ce-save").disabled = false;
		var priced = {};
		((state.summary && state.summary.items) || []).forEach(function (r, i) { priced[i] = r; });
		wrap.innerHTML = state.items.map(function (it, i) {
			var amount = priced[i] && priced[i].item_code === it.item_code ? priced[i].amount : it.qty * it.rate;
			return '<div class="a3s-posline" data-index="' + i + '">' +
				'<span class="a3s-posline__name">' + esc(it.item_name) + (it.package_option ? ' <small class="a3s-muted">' + esc(it.package_option) + "</small>" : "") + "</span>" +
				'<span class="a3s-posline__amt">' + money(amount) + "</span>" +
				(it.description ? '<span class="a3s-posline__desc">' + esc(it.description) + "</span>" : "") +
				(readonly
					? '<span class="a3s-posline__desc">' + num(it.qty) + " " + esc(it.uom || "") + " &times; " + money(it.rate) + "</span>"
					: '<div class="a3s-posline__ctrl">' +
						'<span class="a3s-stepper"><button type="button" data-step="-1" aria-label="Less">&minus;</button>' +
						'<input type="number" min="1" step="1" value="' + esc(it.qty) + '" data-qty aria-label="Quantity">' +
						'<button type="button" data-step="1" aria-label="More">+</button></span>' +
						'<label class="a3s-posline__rate">&#64; <input type="number" min="0" step="any" value="' + esc(it.rate) + '" data-rate aria-label="Rate"> / ' + esc(it.uom || "Nos") + "</label>" +
						'<button type="button" class="a3s-posline__remove" data-remove>Remove</button>' +
					"</div>") +
				"</div>";
		}).join("");
	}

	function renderTotals() {
		var s = state.summary;
		var t = s ? s.totals : null;
		var lines = el("ce-totals");
		var subtotal = state.items.reduce(function (a, it) { return a + it.qty * it.rate; }, 0);
		if (!t) {
			lines.innerHTML = state.items.length
				? '<div class="a3s-line"><span>Subtotal</span><span>' + money(subtotal) + '</span></div><div class="a3s-line"><small>GST and totals appear once the ' + (state.quotation_to || "lead").toLowerCase() + ' is chosen.</small></div>'
				: "";
			el("ce-grand").textContent = money(state.items.length ? subtotal : 0);
			el("ce-words").textContent = "";
			el("ce-pos-solar").hidden = true;
			return;
		}
		var rows = [
			'<div class="a3s-line"><span>Subtotal</span><span>' + money(t.total) + "</span></div>",
		];
		if (t.discount_amount) rows.push('<div class="a3s-line"><span>Discount' + (t.additional_discount_percentage ? " (" + num(t.additional_discount_percentage) + "%)" : "") + "</span><span>&minus; " + money(t.discount_amount) + "</span></div>");
		if (t.discount_amount) rows.push('<div class="a3s-line"><span>Taxable value</span><span>' + money(t.net_total) + "</span></div>");
		(s.taxes || []).forEach(function (tx) {
			rows.push('<div class="a3s-line"><span>' + esc(tx.description) + (tx.rate ? " <small>" + num(tx.rate) + "%</small>" : "") + "</span><span>" + money(tx.tax_amount) + "</span></div>");
		});
		if (!(s.taxes || []).length) rows.push('<div class="a3s-line"><small>No GST template applied.</small><span></span></div>');
		if (t.rounding_adjustment) rows.push('<div class="a3s-line"><small>Rounding</small><small>' + money(t.rounding_adjustment) + "</small></div>");
		lines.innerHTML = rows.join("");
		el("ce-grand").textContent = money(t.rounded_total || t.grand_total);
		el("ce-words").textContent = t.in_words || "";

		var so = s.solar || {};
		var box = el("ce-pos-solar");
		if (Number(so.expected_subsidy_to_customer) || Number(so.statutory_total)) {
			box.hidden = false;
			box.innerHTML =
				(Number(so.expected_subsidy_to_customer) ? '<div class="a3s-line"><span>Expected government subsidy</span><strong>' + money(so.expected_subsidy_to_customer) + "</strong></div>" +
					'<div class="a3s-line a3s-line--total"><span>Net payable by customer</span><strong>' + money(so.net_payable_by_customer) + "</strong></div>" : "") +
				(Number(so.statutory_total) ? '<div class="a3s-line"><span>DISCOM fees <small>reimbursed against receipts</small></span><span>' + money(so.statutory_total) + "</span></div>" : "") +
				'<p class="a3s-pos__solar-note">The subsidy is paid to the customer by the government after commissioning. It is not a discount and is shown for information only.</p>';
		} else {
			box.hidden = true;
		}
	}

	/* ------------------------------------------------------------ solar */
	function fact(label, value) {
		return '<div class="a3s-ce-fact"><span>' + esc(label) + "</span><strong>" + (value === "" || value === null || value === undefined ? "&mdash;" : value) + "</strong></div>";
	}
	function renderSolarFacts() {
		var so = (state.summary && state.summary.solar) || {};
		el("ce-solar-facts").innerHTML = [
			fact("Capacity", Number(so.capacity_kw) ? num(so.capacity_kw, 3) + " kW" : ""),
			fact("Subsidy scheme", esc(so.subsidy_scheme || "")),
			fact("Gross amount", Number(so.gross_amount) ? money(so.gross_amount) : ""),
			fact("Expected subsidy to customer", Number(so.expected_subsidy_to_customer) ? money(so.expected_subsidy_to_customer) : ""),
			fact("Net payable by customer", Number(so.net_payable_by_customer) ? money(so.net_payable_by_customer) : ""),
			fact("Estimated annual savings", Number(so.estimated_annual_savings) ? money(so.estimated_annual_savings) : ""),
			fact("Simple payback", Number(so.simple_payback_years) ? num(so.simple_payback_years) + " years" : ""),
		].join("");
		el("ce-statutory-facts").innerHTML = [
			fact("Net meter mode", esc(so.net_meter_mode || "")),
			fact("Application fee", Number(so.kseb_application_fee) ? money(so.kseb_application_fee) : ""),
			fact("Registration fee", Number(so.kseb_registration_fee) ? money(so.kseb_registration_fee) : ""),
			fact("Registration refundable", Number(so.kseb_registration_refundable) ? money(so.kseb_registration_refundable) : ""),
			fact("Net meter charge", Number(so.net_meter_charge) ? money(so.net_meter_charge) : ""),
			fact("Statutory total", Number(so.statutory_total) ? money(so.statutory_total) : ""),
		].join("");
	}

	function fillSelect(select, options, value, emptyLabel) {
		var html = '<option value="">' + (emptyLabel || "&mdash;") + "</option>";
		options.forEach(function (o) { html += '<option value="' + esc(o.value) + '"' + (o.value === value ? " selected" : "") + ">" + esc(o.label) + "</option>"; });
		if (value && !options.some(function (o) { return o.value === value; })) html += '<option value="' + esc(value) + '" selected>' + esc(value) + "</option>";
		select.innerHTML = html;
	}

	function syncSolarControls() {
		var r = state.refs || {};
		fillSelect(el("ce-solar-consumer"), (r.consumers || []).map(function (c) { return { value: c.name, label: (c.consumer_name || c.name) + (c.consumer_number ? " · " + c.consumer_number : "") }; }), state.solar.solar_consumer);
		fillSelect(el("ce-solar-estimate"), (r.estimates || []).map(function (e) { return { value: e.name, label: e.name + " · " + num(e.final_capacity_kw, 2) + " kW" + (e.docstatus === 1 ? "" : " (draft)") }; }), state.solar.solar_design_estimate);
		var est = (r.estimates || []).find(function (e) { return e.name === state.solar.solar_design_estimate; });
		fillSelect(el("ce-selected-option"), ((est && est.options) || []).map(function (o) { return { value: o.option_name, label: o.option_name + (o.total_option_cost ? " · " + money(o.total_option_cost) : "") + (o.is_recommended ? " ★" : "") }; }), state.solar.selected_option);
		fillSelect(el("ce-eligibility"), (r.eligibility_checks || []).map(function (c) { return { value: c.name, label: c.name + (c.overall_result ? " · " + c.overall_result : "") }; }), state.solar.subsidy_eligibility_check);
		fillSelect(el("ce-proposal"), (r.proposals || []).map(function (p) { return { value: p.name, label: p.name + (p.status ? " · " + p.status : "") }; }), state.solar.solar_proposal);
		fillSelect(el("ce-solar-package"), (cat.packages || []).map(function (p) { return { value: p.name, label: p.package_name }; }), state.solar.solar_package, "&mdash; from the first package line &mdash;");
		FINANCE.forEach(function (f) {
			var c = root.querySelector('[data-solar="' + f + '"]');
			if (!c) return;
			if (c.type === "checkbox") c.checked = !!Number(state.solar[f]);
			else c.value = state.solar[f] === null || state.solar[f] === undefined ? "" : state.solar[f];
		});
		el("ce-finance").hidden = !Number(state.solar.is_financed);
		renderReference();
	}

	function renderReference() {
		var r = state.refs || {};
		var sel = el("ce-reference");
		var groups = [
			["Solar consumer", "solar_consumer", (r.consumers || []).map(function (c) { return { value: c.name, label: (c.consumer_name || c.name) + (c.consumer_number ? " · " + c.consumer_number : "") }; })],
			["Design estimate", "solar_design_estimate", (r.estimates || []).map(function (e) { return { value: e.name, label: e.name + " · " + num(e.final_capacity_kw, 2) + " kW" }; })],
			["Solar proposal", "solar_proposal", (r.proposals || []).map(function (p) { return { value: p.name, label: p.name + (p.status ? " · " + p.status : "") }; })],
			["Eligibility check", "subsidy_eligibility_check", (r.eligibility_checks || []).map(function (c) { return { value: c.name, label: c.name + (c.overall_result ? " · " + c.overall_result : "") }; })],
		];
		var current = "";
		["solar_design_estimate", "solar_proposal", "subsidy_eligibility_check", "solar_consumer"].some(function (f) {
			if (state.solar[f]) { current = f + "::" + state.solar[f]; return true; }
			return false;
		});
		var html = '<option value="">&mdash; ' + (groups.some(function (g) { return g[2].length; }) ? "choose" : "none on file") + " &mdash;</option>";
		groups.forEach(function (g) {
			if (!g[2].length) return;
			html += '<optgroup label="' + esc(g[0]) + '">' + g[2].map(function (o) {
				var v = g[1] + "::" + o.value;
				return '<option value="' + esc(v) + '"' + (v === current ? " selected" : "") + ">" + esc(o.label) + "</option>";
			}).join("") + "</optgroup>";
		});
		sel.innerHTML = html;
	}

	/* ------------------------------------------------------------ party */
	function renderPartyList(q) {
		var list = el("ce-party-list");
		q = (q || "").trim().toLowerCase();
		var rows = state.parties.filter(function (p) {
			return !q || (p.label + " " + p.value + " " + (p.sub || "")).toLowerCase().indexOf(q) !== -1;
		}).slice(0, 30);
		if (!rows.length) { list.innerHTML = '<p class="a3s-combo__none">No ' + esc(state.quotation_to.toLowerCase()) + ' matches. <a href="/a3solaportal/leads/new">Create a lead</a>.</p>'; }
		else {
			list.innerHTML = rows.map(function (p) {
				return '<button type="button" class="a3s-combo__opt" role="option" data-party="' + esc(p.value) + '">' + esc(p.label) + "<small>" + esc(p.sub || p.value) + "</small></button>";
			}).join("");
		}
		list.hidden = false;
		el("ce-party").setAttribute("aria-expanded", "true");
	}
	function closePartyList() { el("ce-party-list").hidden = true; el("ce-party").setAttribute("aria-expanded", "false"); }

	function choosePartyByName(name) {
		var p = state.parties.find(function (x) { return x.value === name; });
		state.party_name = name;
		state.party_label = p ? p.label : name;
		el("ce-party").value = state.party_label;
		el("ce-party-sub").textContent = p && p.sub ? p.sub : name;
		closePartyList();
		loadReferences();
	}

	function loadReferences() {
		if (!state.party_name) { state.refs = null; syncSolarControls(); renderPackages(); return; }
		call("references", { quotation_to: state.quotation_to, party_name: state.party_name }).then(function (r) {
			state.refs = r || {};
			var d = (r && r.defaults) || {};
			// First time this party is chosen on a fresh estimate, adopt what is on file.
			if (!state.name) {
				["solar_consumer", "solar_design_estimate", "subsidy_eligibility_check", "solar_proposal"].forEach(function (f) {
					if (!state.solar[f] && d[f]) state.solar[f] = d[f];
				});
			}
			if (r && r.party) {
				var bits = [r.party.mobile_no, r.party.email_id, r.party.city, r.party.capacity_kw ? num(r.party.capacity_kw, 1) + " kW proposed" : ""].filter(Boolean);
				if (bits.length) el("ce-party-sub").textContent = bits.join(" · ");
			}
			syncSolarControls(); renderPackages(); changed();
		}).catch(function (e) { setMsg(e.message, "error"); });
	}

	function loadParties() {
		return call("parties", { quotation_to: state.quotation_to }).then(function (rows) { state.parties = rows || []; });
	}

	/* ------------------------------------------------------------ terms */
	function termsTemplate(name) { return (cat.terms_templates || []).find(function (t) { return t.name === name; }); }
	function renderTerms() {
		var sel = el("ce-terms-template");
		var opts = (cat.terms_templates || []).map(function (t) { return { value: t.name, label: t.title }; });
		if (state.terms.tc_name === CUSTOM_TERMS) opts.push({ value: CUSTOM_TERMS, label: "As saved on this estimate" });
		fillSelect(sel, opts, state.terms.tc_name, "&mdash; no terms &mdash;");
		el("ce-terms-preview").innerHTML = state.terms.html || '<p class="a3s-muted">No terms template selected.</p>';
		el("ce-terms-notes").value = state.terms.notes || "";
		el("ce-note-delivery").innerHTML = (cat.notes && cat.notes.delivery) || "<p class=\"a3s-muted\">Not set in Settings.</p>";
		el("ce-note-gst").innerHTML = (cat.notes && cat.notes.gst) || "<p class=\"a3s-muted\">Not set in Settings.</p>";
		el("ce-note-subsidy").innerHTML = (cat.notes && cat.notes.subsidy) || "<p class=\"a3s-muted\">Not set in Settings.</p>";
	}

	/* ------------------------------------------------------------ header */
	function renderHeader() {
		el("ce-quotation-to").value = state.quotation_to;
		el("ce-party-label").textContent = state.quotation_to;
		el("ce-party").placeholder = state.quotation_to === "Lead" ? "Search by name, phone or email" : "Search customers";
		el("ce-party").value = state.party_label || state.party_name || "";
		el("ce-date").value = state.transaction_date || "";
		el("ce-valid-till").value = state.valid_till || "";
		var tax = el("ce-tax");
		fillSelect(tax, (cat.taxes || []).map(function (t) {
			return { value: t.name, label: (t.title || t.name) + ((t.rows || []).length ? " · " + t.rows.map(function (r) { return r.description + " " + num(r.rate) + "%"; }).join(" + ") : "") };
		}), state.taxes_and_charges, "No GST");
		el("ce-discount-type").value = state.discount_type;
		el("ce-discount").value = state.discount || "";
	}

	function renderStatus() {
		var badge = el("ce-status");
		if (state.name) {
			el("ce-eyebrow").textContent = state.name;
			badge.hidden = false;
			badge.textContent = state.status || (state.docstatus === 1 ? "Submitted" : "Draft");
			badge.className = "a3s-badge a3s-badge--" + String(badge.textContent).toLowerCase().replace(/\s+/g, "-");
			el("ce-submit").hidden = readonly || state.docstatus !== 0;
			if (!el("ce-desk")) {
				var a = document.createElement("a");
				a.className = "a3s-btn a3s-btn--ghost"; a.id = "ce-desk"; a.target = "_blank"; a.rel = "noopener";
				a.href = "/app/quotation/" + encodeURIComponent(state.name); a.textContent = "Open in ERPNext";
				el("ce-actions").appendChild(a);
			}
		}
		if (state.party_label) el("ce-title").textContent = state.party_label;
	}

	/* ---------------------------------------------------------- hydrate */
	function hydrate(record) {
		var h = record.header || {}, so = record.solar || {}, t = record.totals || {};
		state.name = record.name; state.docstatus = record.docstatus; state.status = record.status;
		state.quotation_to = h.quotation_to || "Lead"; state.party_name = h.party_name || "";
		state.party_label = h.customer_name || h.party_name || "";
		state.transaction_date = h.transaction_date; state.valid_till = h.valid_till;
		state.taxes_and_charges = h.taxes_and_charges || "";
		if (Number(t.additional_discount_percentage)) { state.discount_type = "percent"; state.discount = Number(t.additional_discount_percentage); }
		else { state.discount_type = "amount"; state.discount = Number(t.discount_amount) || 0; }
		state.items = (record.items || []).map(function (r) {
			return { key: (r.solar_package ? r.solar_package + "#" : "item:") + r.item_code + ":" + r.idx, item_code: r.item_code, item_name: r.item_name, description: r.description, qty: r.qty, rate: r.rate, uom: r.uom, solar_package: r.solar_package, package_option: r.package_option };
		});
		SOLAR_LINKS.concat(FINANCE).forEach(function (f) { state.solar[f] = so[f] === undefined ? null : so[f]; });
		if (h.terms) {
			var known = h.tc_name && termsTemplate(h.tc_name);
			state.terms = { tc_name: known ? h.tc_name : CUSTOM_TERMS, html: h.terms, notes: "", dirty: false };
		}
		state.summary = record;
	}

	/* ------------------------------------------------------------- save */
	function save() {
		if (!state.party_name) { setMsg("Choose who this estimate is for.", "error"); el("ce-party").focus(); return; }
		if (!state.items.length) { setMsg("Add at least one package or item.", "error"); return; }
		var btn = el("ce-save"); btn.disabled = true; setMsg("Saving…");
		call("save", { payload: payload(), name: state.name }).then(function (s) {
			var created = !state.name;
			state.summary = s; state.name = s.name; state.docstatus = s.docstatus; state.status = s.status;
			if (created && s.route) history.replaceState(null, "", s.route);
			renderStatus(); renderLines(); renderTotals(); renderSolarFacts();
			state.terms.dirty = false;
			setMsg("Saved as " + s.name + ".", "success");
		}).catch(function (e) { setMsg(e.message, "error"); }).then(function () { btn.disabled = false; });
	}

	function submit() {
		if (!state.name) return;
		if (!window.confirm("Submit " + state.name + "? A submitted estimate can only be amended from ERPNext.")) return;
		var btn = el("ce-submit"); btn.disabled = true; setMsg("Submitting…");
		call("submit", { name: state.name }).then(function (s) {
			setMsg("Submitted.", "success");
			window.location.assign(s.route || (data.list_route || "/a3solaportal/quotations"));
		}).catch(function (e) { setMsg(e.message, "error"); btn.disabled = false; });
	}

	/* ------------------------------------------------------------- tabs */
	var tabs = Array.prototype.slice.call(root.querySelectorAll(".a3s-ce-tabs [role=tab]"));
	function switchTab(key) {
		tabs.forEach(function (t) {
			var on = t.dataset.tab === key;
			t.setAttribute("aria-selected", on ? "true" : "false");
			t.tabIndex = on ? 0 : -1;
			var panel = el(t.getAttribute("aria-controls"));
			if (panel) panel.hidden = !on;
		});
	}
	tabs.forEach(function (t, i) {
		t.addEventListener("click", function () { switchTab(t.dataset.tab); });
		t.addEventListener("keydown", function (e) {
			if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
			var next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
			next.focus(); switchTab(next.dataset.tab);
		});
	});

	/* ------------------------------------------------------------ events */
	el("ce-filter").addEventListener("input", renderPackages);
	root.addEventListener("click", function (e) {
		var add = e.target.closest("[data-add-package]");
		if (add) { addPackage(add.dataset.addPackage, add.dataset.option); return; }
		var addI = e.target.closest("[data-add-item]");
		if (addI) { addItem(addI.dataset.addItem); return; }
		var line = e.target.closest(".a3s-posline");
		if (line) {
			var i = Number(line.dataset.index);
			if (e.target.closest("[data-remove]")) { state.items.splice(i, 1); changed(); renderPackages(); return; }
			var step = e.target.closest("[data-step]");
			if (step) { state.items[i].qty = Math.max(1, (Number(state.items[i].qty) || 1) + Number(step.dataset.step)); changed(); return; }
		}
		var opt = e.target.closest("[data-party]");
		if (opt) { choosePartyByName(opt.dataset.party); return; }
	});
	root.addEventListener("change", function (e) {
		var line = e.target.closest(".a3s-posline");
		if (line) {
			var i = Number(line.dataset.index);
			if (e.target.hasAttribute("data-qty")) state.items[i].qty = Math.max(1, Math.round(Number(e.target.value) || 1));
			if (e.target.hasAttribute("data-rate")) state.items[i].rate = Math.max(0, Number(e.target.value) || 0);
			changed(); return;
		}
		var solar = e.target.getAttribute("data-solar");
		if (solar) {
			state.solar[solar] = e.target.type === "checkbox" ? (e.target.checked ? 1 : 0) : (e.target.value || null);
			if (solar === "is_financed") el("ce-finance").hidden = !e.target.checked;
			if (solar === "solar_design_estimate") { state.solar.selected_option = null; }
			syncSolarControls(); if (!readonly) preview(); return;
		}
	});
	el("ce-reference").addEventListener("change", function () {
		var v = this.value;
		if (!v) return;
		var parts = v.split("::");
		state.solar[parts[0]] = parts[1];
		if (parts[0] === "solar_design_estimate") {
			var est = ((state.refs || {}).estimates || []).find(function (x) { return x.name === parts[1]; });
			if (est && est.solar_consumer) state.solar.solar_consumer = est.solar_consumer;
			state.solar.selected_option = null;
		}
		syncSolarControls(); if (!readonly) preview();
	});
	el("ce-quotation-to").addEventListener("change", function () {
		state.quotation_to = this.value; state.party_name = ""; state.party_label = ""; state.refs = null;
		el("ce-party-sub").textContent = "";
		renderHeader(); syncSolarControls();
		loadParties().then(function () { renderPartyList(""); el("ce-party").focus(); }).catch(function (e) { setMsg(e.message, "error"); });
	});
	var party = el("ce-party");
	party.addEventListener("focus", function () { renderPartyList(party.value === state.party_label ? "" : party.value); });
	party.addEventListener("input", function () { state.party_name = ""; renderPartyList(party.value); });
	party.addEventListener("keydown", function (e) {
		var list = el("ce-party-list");
		var opts = Array.prototype.slice.call(list.querySelectorAll("[data-party]"));
		if (!opts.length) return;
		var active = opts.findIndex(function (o) { return o.classList.contains("is-active"); });
		if (e.key === "ArrowDown" || e.key === "ArrowUp") {
			e.preventDefault();
			opts.forEach(function (o) { o.classList.remove("is-active"); });
			active = (active + (e.key === "ArrowDown" ? 1 : opts.length - 1) + (active < 0 && e.key === "ArrowUp" ? 1 : 0)) % opts.length;
			opts[active].classList.add("is-active"); opts[active].scrollIntoView({ block: "nearest" });
		} else if (e.key === "Enter") {
			e.preventDefault(); choosePartyByName((opts[active >= 0 ? active : 0]).dataset.party);
		} else if (e.key === "Escape") { closePartyList(); }
	});
	document.addEventListener("click", function (e) { if (!e.target.closest(".a3s-combo")) closePartyList(); });
	el("ce-date").addEventListener("change", function () {
		state.transaction_date = this.value;
		if (!state.valid_till || state.valid_till < state.transaction_date) { state.valid_till = addDays(state.transaction_date, cat.validity_days || 30); el("ce-valid-till").value = state.valid_till; }
	});
	el("ce-valid-till").addEventListener("change", function () { state.valid_till = this.value; });
	el("ce-tax").addEventListener("change", function () { state.taxes_and_charges = this.value; if (!readonly) preview(); });
	el("ce-discount-type").addEventListener("change", function () { state.discount_type = this.value; if (!readonly) preview(); });
	el("ce-discount").addEventListener("input", debounce(function () { state.discount = Math.max(0, Number(el("ce-discount").value) || 0); if (!readonly) preview(); }, 250));
	el("ce-terms-template").addEventListener("change", function () {
		var t = termsTemplate(this.value);
		state.terms.tc_name = this.value; state.terms.html = t ? t.terms : (this.value === CUSTOM_TERMS ? state.terms.html : ""); state.terms.dirty = true;
		renderTerms();
	});
	el("ce-terms-notes").addEventListener("input", function () { state.terms.notes = this.value; state.terms.dirty = true; });
	el("ce-save").addEventListener("click", save);
	el("ce-submit").addEventListener("click", submit);

	/* -------------------------------------------------------------- init */
	if (data.record) hydrate(data.record);
	renderHeader(); renderPackages(); renderAddons(); renderTerms(); renderLines(); renderTotals(); renderSolarFacts(); renderStatus();
	if (readonly) {
		Array.prototype.forEach.call(root.querySelectorAll("input, select, textarea, button"), function (c) {
			if (c.closest(".a3s-ce-tabs") || c.closest("details")) return;
			c.disabled = true;
		});
		el("ce-save").hidden = true; el("ce-submit").hidden = true;
	}
	if (state.party_name) {
		var pre = state.parties.find(function (p) { return p.value === state.party_name; });
		if (pre && !state.party_label) { state.party_label = pre.label; el("ce-party").value = pre.label; }
		loadReferences();
	} else if (data.lead) {
		state.quotation_to = "Lead"; choosePartyByName(data.lead);
	}
})();
