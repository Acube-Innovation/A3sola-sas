/* Copyright (c) 2026, Acube Innovations and contributors
 * For license information, please see license.txt
 *
 * Checkout. The card is entered on the gateway's own hosted page - nothing card-shaped
 * is ever posted to a Frappe endpoint, which is what keeps this server out of PCI scope.
 */
(function () {
	"use strict";

	var button = document.getElementById("a3s-pay-btn");
	if (!button) return;
	var status = document.querySelector("#a3s-pay .a3s-form__status");
	var reference = button.dataset.reference;
	var key = button.dataset.key;

	function fail(message) {
		button.disabled = false;
		status.className = "a3s-form__status is-error";
		status.textContent = message;
	}

	function goToStatus() {
		window.location.href = "/payment-status?ref=" + encodeURIComponent(reference) +
			"&t=" + encodeURIComponent(key);
	}

	// Mock mode: no gateway, no card, no money. The server still runs the same
	// apply_successful_payment path, so what you see here is what the real flow does.
	var pane = document.getElementById("a3s-pay");
	if (pane && pane.dataset.mock === "1") {
		pane.querySelectorAll("button[data-outcome]").forEach(function (btn) {
			btn.addEventListener("click", function () {
				pane.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
				status.className = "a3s-form__status";
				status.textContent = "Simulating…";
				frappe.call({
					method: "a3_sola.api.payments.complete_mock_payment",
					args: {
						signup_reference: reference,
						token: key,
						outcome: btn.dataset.outcome,
					},
				}).then(goToStatus).catch(function (err) {
					pane.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
					status.className = "a3s-form__status is-error";
					status.textContent = (err && err.message) || "That did not work.";
				});
			});
		});
		return;
	}

	button.addEventListener("click", function () {
		button.disabled = true;
		status.className = "a3s-form__status";
		status.textContent = "Opening secure payment…";

		frappe.call({
			method: "a3_sola.api.payments.initiate_payment",
			args: { signup_reference: reference, token: key },
		}).then(function (response) {
			var order = response.message;
			if (!order || !order.order_id) {
				fail("We could not start that payment. Please try again.");
				return;
			}
			if (typeof Razorpay === "undefined") {
				fail("The payment window could not load. Check your connection and try again.");
				return;
			}

			var checkout = new Razorpay({
				key: order.key_id,
				amount: order.amount,
				currency: order.currency,
				name: order.name,
				description: order.description,
				order_id: order.order_id,
				prefill: order.prefill,
				notes: order.notes,
				theme: { color: "#f7941e" },
				handler: function (result) {
					status.textContent = "Confirming your payment…";
					frappe.call({
						method: "a3_sola.api.payments.verify_checkout_payment",
						args: {
							payload: {
								signup_reference: reference,
								token: key,
								razorpay_order_id: result.razorpay_order_id,
								razorpay_payment_id: result.razorpay_payment_id,
								razorpay_signature: result.razorpay_signature,
							},
						},
					}).then(goToStatus).catch(function () {
						// The callback is only a hint. If it fails to verify here the
						// webhook still settles it, so send them to the polling page
						// rather than telling them something went wrong.
						goToStatus();
					});
				},
				modal: {
					ondismiss: function () {
						button.disabled = false;
						status.className = "a3s-form__status";
						status.textContent = "Payment window closed. Nothing has been charged.";
					},
				},
			});

			checkout.on("payment.failed", function (event) {
				var description = (event && event.error && event.error.description) ||
					"The payment did not go through.";
				fail(description + " Nothing has been charged. Please try again.");
			});

			checkout.open();
		}).catch(function (err) {
			fail((err && err.message) || "We could not start that payment. Please try again.");
		});
	});
})();
