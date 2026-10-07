/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The editable rows grid on a collection's create and edit pages
 * (templates/includes/portal_item_table.html). The row inputs carry no `name`, so the
 * form's own script never posts them one by one; instead every change is written as JSON
 * into the hidden `__items` input, which the form posts like any other value.
 *
 * Amounts and the total are shown as the controller will work them out. They are a
 * preview: the server recomputes both on save and never takes them from the browser.
 */
(function () {
	"use strict";

	var root = document.querySelector("[data-item-table]");
	if (!root) return;

	var spec = JSON.parse(root.querySelector("[data-item-spec]").textContent || "{}");
	var columns = spec.columns || [];
	var body = root.querySelector("[data-rows]");
	var hidden = root.querySelector('input[name="__items"]');
	var totalEl = root.querySelector("[data-total]");
	var rows = (spec.rows || []).map(function (r) { return Object.assign({}, r); });

	var money = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

	function num(v) {
		var n = parseFloat(v);
		return isNaN(n) ? 0 : n;
	}

	/* Mirrors the controllers: Additional Structure, Additional Cable, Special Discount. */
	function amountOf(row) {
		if (spec.rule === "qty*rate") return num(row.qty) * num(row.rate);
		if (spec.rule === "length*rate") return num(row.length) * num(row.rate);
		if (spec.rule === "discount") {
			return row.discount_type === "Percentage"
				? num(row.base_amount) * num(row.discount_value) / 100
				: num(row.discount_value);
		}
		return num(row.amount);
	}

	function blankRow() {
		var row = {};
		columns.forEach(function (c) {
			if (!c.readonly) row[c.fieldname] = c.default || (c.type === "Select" && c.reqd ? (c.options || []).filter(Boolean)[0] || "" : "");
		});
		return row;
	}

	function sync() {
		var total = 0;
		Array.prototype.forEach.call(body.querySelectorAll("tr[data-index]"), function (tr) {
			var row = rows[Number(tr.dataset.index)];
			var amount = amountOf(row);
			row.amount = amount;
			total += amount;
			var cell = tr.querySelector("[data-amount]");
			if (cell) cell.textContent = money.format(amount);
		});
		totalEl.textContent = "₹ " + money.format(total);
		hidden.value = JSON.stringify(rows.map(function (row) {
			var out = {};
			columns.forEach(function (c) { if (!c.readonly) out[c.fieldname] = row[c.fieldname]; });
			return out;
		}));
		hidden.dispatchEvent(new Event("change", { bubbles: true }));
	}

	function control(c, row) {
		var el;
		if (c.type === "Select") {
			el = document.createElement("select");
			(c.options || []).forEach(function (opt) {
				var o = document.createElement("option");
				o.value = opt;
				o.textContent = opt || "—";
				if (opt === (row[c.fieldname] || "")) o.selected = true;
				el.appendChild(o);
			});
		} else {
			el = document.createElement("input");
			el.type = c.numeric ? "number" : "text";
			if (c.numeric) { el.step = c.type === "Int" ? "1" : "any"; el.min = "0"; }
			el.value = row[c.fieldname] == null ? "" : row[c.fieldname];
		}
		el.className = "a3s-items__input";
		el.setAttribute("aria-label", c.label);
		el.addEventListener("input", function () {
			row[c.fieldname] = el.value;
			sync();
		});
		el.addEventListener("change", function () {
			row[c.fieldname] = el.value;
			sync();
		});
		return el;
	}

	function render() {
		body.innerHTML = "";
		if (!rows.length) {
			var empty = document.createElement("tr");
			var td = document.createElement("td");
			td.colSpan = columns.length + 2;
			td.className = "a3s-table__muted";
			td.textContent = "No rows yet. Add one below.";
			empty.appendChild(td);
			body.appendChild(empty);
		}
		rows.forEach(function (row, i) {
			var tr = document.createElement("tr");
			tr.dataset.index = i;
			var idx = document.createElement("td");
			idx.className = "a3s-items__idx";
			idx.textContent = i + 1;
			tr.appendChild(idx);
			columns.forEach(function (c) {
				var cell = document.createElement("td");
				cell.dataset.label = c.label;
				if (c.numeric) cell.className = "a3s-items__num";
				if (c.readonly) cell.setAttribute("data-amount", "");
				else cell.appendChild(control(c, row));
				tr.appendChild(cell);
			});
			var act = document.createElement("td");
			var remove = document.createElement("button");
			remove.type = "button";
			remove.className = "a3s-btn a3s-btn--ghost a3s-items__remove";
			remove.setAttribute("aria-label", "Remove row " + (i + 1));
			remove.textContent = "×";
			remove.addEventListener("click", function () {
				rows.splice(i, 1);
				render();
			});
			act.appendChild(remove);
			tr.appendChild(act);
			body.appendChild(tr);
		});
		sync();
	}

	root.querySelector("[data-add-row]").addEventListener("click", function () {
		rows.push(blankRow());
		render();
		var inputs = body.querySelectorAll("tr[data-index]:last-child .a3s-items__input");
		if (inputs.length) inputs[0].focus();
	});

	if (!rows.length) rows.push(blankRow());
	render();
})();
