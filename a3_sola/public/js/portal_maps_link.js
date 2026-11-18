/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * The customer's Google Location link fills its Latitude and Longitude as it is pasted
 * (api/maps_link.read_coordinates), on the create and the edit form. A link to a place by
 * name alone has no coordinates and leaves them as they are. Saving reads the link again,
 * so nothing depends on this having run.
 */
(function () {
	"use strict";

	var form = document.getElementById("a3s-record-form") || document.getElementById("a3s-record-edit-form");
	if (!form || !form.elements.google_location_url || !form.elements.latitude || !form.elements.longitude) return;
	var link = form.elements.google_location_url;
	var meta = document.querySelector('meta[name="csrf-token"]');
	var csrf = meta ? meta.getAttribute("content") : "";
	var asked = "";

	function set(name, value) {
		var el = form.elements[name];
		if (String(el.value) === String(value)) return;
		el.value = value;
		el.dispatchEvent(new Event("change", { bubbles: true }));
	}

	function read() {
		var value = (link.value || "").trim();
		if (!value || value === asked) return;
		asked = value;
		fetch("/api/method/a3_sola.api.maps_link.read_coordinates", {
			method: "POST", credentials: "same-origin",
			headers: { "Content-Type": "application/json", "Accept": "application/json", "X-Frappe-CSRF-Token": csrf },
			body: JSON.stringify({ link: value })
		}).then(function (r) { return r.json(); })
		  .then(function (body) {
			var found = body && body.message;
			if (!found || found.latitude == null || link.value.trim() !== value) return;
			set("latitude", found.latitude);
			set("longitude", found.longitude);
		  })
		  .catch(function () { /* read again when the form is saved */ });
	}

	link.addEventListener("change", read);
	link.addEventListener("paste", function () { setTimeout(read, 0); });
})();
