// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Installation Work Order", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open Installation"), () =>
			frappe.set_route("Form", "Solar Installation", frm.doc.solar_installation)
		);
		const untagged = (frm.doc.photos || []).filter((p) => !(p.latitude && p.longitude));
		if (untagged.length && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Capture Location for {0} Untagged", [untagged.length]), () =>
				capture_here(frm, untagged)
			);
		}
	},
});

frappe.ui.form.on("Work Order Type Item", {
	work_types_add(frm) {
		frm.refresh_field("work_order_type");
	},
	work_type(frm, cdt, cdn) {
		if (!frm.doc.work_order_type && frm.doc.work_types && frm.doc.work_types.length) {
			frm.set_value("work_order_type", frm.doc.work_types[0].work_type);
		}
	},
});

// Ask the phone where it is the moment a photo row is added - that is when the person is
// standing under the array. A photo uploaded later may still carry EXIF; ask the server.
frappe.ui.form.on("Site Photo", {
	photos_add(frm, cdt, cdn) {
		capture_here(frm, [locals[cdt][cdn]]);
	},
	image(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.image || (row.latitude && row.longitude)) return;
		frappe.call({
			method: "a3_sola.api.photos.read_exif_gps",
			args: { file_url: row.image },
			callback(r) {
				if (r.message) {
					frappe.model.set_value(cdt, cdn, {
						latitude: r.message.latitude,
						longitude: r.message.longitude,
						geo_source: "EXIF",
					});
				}
			},
		});
	},
});

function capture_here(frm, rows) {
	if (!navigator.geolocation) {
		frappe.show_alert({ message: __("This browser cannot report a location. Enter the coordinates on the row."), indicator: "orange" });
		return;
	}
	navigator.geolocation.getCurrentPosition(
		(position) => {
			rows.forEach((row) => {
				frappe.model.set_value(row.doctype, row.name, {
					latitude: position.coords.latitude,
					longitude: position.coords.longitude,
					accuracy_m: position.coords.accuracy,
					captured_on: frappe.datetime.now_datetime(),
					geo_source: "Browser",
				});
			});
			frappe.show_alert({ message: __("Location captured (±{0} m)", [Math.round(position.coords.accuracy)]), indicator: "green" });
		},
		(err) => {
			frappe.show_alert({ message: __("Location not available: {0}. Enter the coordinates on the row.", [err.message]), indicator: "orange" });
		},
		{ enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
	);
}
