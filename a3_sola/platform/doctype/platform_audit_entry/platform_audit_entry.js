// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

// The form is read-only by construction (the controller refuses every write), so the only
// thing worth offering here is the chain check - the thing that says whether these records
// can still be believed.

frappe.ui.form.on("Platform Audit Entry", {
	refresh(frm) {
		frm.disable_save();
		frm.dashboard.set_headline_alert(
			__("Audit entries are permanent. Nothing on this page can be edited or deleted."),
			"blue"
		);
		frm.add_custom_button(__("Verify the Chain"), () => {
			frappe.call({
				method: "a3_sola.api.audit.verify",
				freeze: true,
				freeze_message: __("Re-hashing every entry…"),
				callback(r) {
					const out = r.message || {};
					if (out.intact) {
						frappe.msgprint({
							title: __("Chain intact"),
							message: __(
								"All {0} entries hash to the values stored against them. Nothing has been altered in the database.",
								[out.checked]
							),
							indicator: "green",
						});
					} else {
						frappe.msgprint({
							title: __("Chain broken"),
							message: __(
								"{0} of {1} entries no longer match their own hash. The first break is at {2}. These rows were changed outside the application.",
								[out.broken.length, out.checked, out.first_break]
							),
							indicator: "red",
						});
					}
				},
			});
		});
	},
});
