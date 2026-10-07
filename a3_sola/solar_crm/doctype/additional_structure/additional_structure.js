// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
// Live row amounts and total, so the form agrees with what validate() will save.

function reprice_additional_structure(frm) {
	let total = 0;
	(frm.doc.items || []).forEach((row) => {
		row.amount = flt(flt(row.qty) * flt(row.rate), precision("amount", row));
		total += row.amount;
	});
	frm.set_value("total_amount", total);
	frm.refresh_field("items");
}

frappe.ui.form.on("Additional Structure", {
	items_remove: reprice_additional_structure,
});

frappe.ui.form.on("Additional Structure Item", {
	qty: (frm) => reprice_additional_structure(frm),
	rate: (frm) => reprice_additional_structure(frm),
});
