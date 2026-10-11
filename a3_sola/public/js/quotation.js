// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt
//
// Quotation: one option of a proposal. Choose the proposal (or the lead) and one of its
// options - a design estimate - and the quotation takes the option as the proposal
// finalised it. The Quotation Details box shows that option: its details, its bill of
// materials and price, its terms. Nothing there is typed; the price is set on save.
const QO = "a3_sola.api.quotation_option";

frappe.ui.form.on("Quotation", {
	setup(frm) {
		frm.set_query("solar_design_estimate", () => {
			const names = frm.__option_estimates;
			if (names && names.length) return { filters: { name: ["in", names] } };
			const filters = { docstatus: 1 };
			if (frm.doc.quotation_to === "Lead" && frm.doc.party_name) filters.lead = frm.doc.party_name;
			if (frm.doc.solar_consumer) filters.solar_consumer = frm.doc.solar_consumer;
			return { filters };
		});
		frm.set_query("solar_proposal", () => {
			const filters = { docstatus: ["<", 2] };
			if (frm.doc.quotation_to === "Lead" && frm.doc.party_name) filters.lead = frm.doc.party_name;
			return { filters };
		});
	},

	refresh(frm) {
		load_option_estimates(frm);
		render_option(frm);
	},

	solar_proposal(frm) {
		load_option_estimates(frm).then((names) => {
			// A proposal's Option 1 is its base: the quotation starts there.
			if (frm.doc.docstatus === 0 && names.length && !names.includes(frm.doc.solar_design_estimate)) {
				frm.set_value("solar_design_estimate", names[0]);
			}
		});
	},

	solar_design_estimate(frm) {
		const estimate = frm.doc.solar_design_estimate;
		if (!estimate || frm.doc.docstatus !== 0) return render_option(frm);
		frappe.call({
			method: `${QO}.option_head`,
			args: { estimate, proposal: frm.doc.solar_proposal || null },
			callback(r) {
				const v = r.message || {};
				["quotation_to", "party_name", "solar_consumer", "solar_proposal", "selected_option",
					"subsidy_eligibility_check", "solar_package"].forEach((f) => {
					if (v[f] && frm.doc[f] !== v[f]) frm.doc[f] = v[f];
				});
				frm.refresh_fields();
				if (v.item_code) {
					// One package line; the server prices it at the option's plant total on save.
					frm.clear_table("items");
					const row = frm.add_child("items");
					frappe.model.set_value(row.doctype, row.name, "item_code", v.item_code);
					frappe.model.set_value(row.doctype, row.name, "qty", 1);
					frm.refresh_field("items");
				}
				render_option(frm);
			},
		});
	},
});

function load_option_estimates(frm) {
	const proposal = frm.doc.solar_proposal;
	const lead = frm.doc.quotation_to === "Lead" ? frm.doc.party_name : null;
	if (!proposal && !lead) {
		frm.__option_estimates = null;
		return Promise.resolve([]);
	}
	return frappe
		.call({ method: `${QO}.proposal_estimates`, args: { proposal: proposal || null, lead } })
		.then((r) => (frm.__option_estimates = r.message || []));
}

function render_option(frm) {
	const field = frm.fields_dict.a3s_option_html;
	if (!field) return;
	if (!frm.doc.solar_design_estimate) {
		field.$wrapper.html(`<p class="text-muted">${__("Choose a proposal and one of its options (Design Estimate) to see the quotation's details, bill of materials and terms.")}</p>`);
		return;
	}
	frappe.call({
		method: `${QO}.option_view`,
		args: {
			estimate: frm.doc.solar_design_estimate,
			proposal: frm.doc.solar_proposal || null,
			quotation: frm.is_new() ? null : frm.doc.name,
		},
		callback(r) {
			const v = r.message || {};
			field.$wrapper.html(`
				<div class="a3q-tabs">
					<h5 style="margin:4px 0 8px">${__("Quotation Details")}</h5>${v.details || ""}
					<h5 style="margin:18px 0 8px">${__("Bill of Materials")}</h5>${v.bom || ""}
					<h5 style="margin:18px 0 8px">${__("Terms")}</h5>${v.terms || ""}
				</div>`);
		},
	});
}
