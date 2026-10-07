// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
// Live row amounts and total, so the form agrees with what validate() will save.

function reprice_special_discount(frm) {
	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		row.amount = flt(row.discount_type === "Percentage" ? (flt(row.base_amount) * flt(row.discount_value)) / 100 : flt(row.discount_value), precision("amount", row));
		total += row.amount;
	});
	frm.set_value("total_amount", total);
	frm.refresh_field("items");
}

frappe.ui.form.on("Special Discount", {
	items_remove: reprice_special_discount,
});

frappe.ui.form.on("Special Discount Item", {
	discount_type: (frm) => reprice_special_discount(frm),
	base_amount: (frm) => reprice_special_discount(frm),
	discount_value: (frm) => reprice_special_discount(frm),
});
