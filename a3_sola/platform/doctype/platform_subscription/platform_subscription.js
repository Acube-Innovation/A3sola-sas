// Copyright (c) 2026, Acube Innovations and contributors
// For license information, please see license.txt

frappe.ui.form.on("Platform Subscription", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;
		if (!frappe.user.has_role(["Platform Billing Manager", "Platform Admin", "System Manager"]))
			return;

		frm.add_custom_button(
			__("Request New Mandate"),
			() => {
				frappe.prompt(
					[
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Why does the mandate need replacing?"),
							description: __(
								"The current mandate is cancelled and collection moves to assisted renewal until the customer authorises a new one."
							),
						},
					],
					(values) => {
						frappe.call({
							method: "a3_sola.api.admin_actions.reregister_mandate",
							args: { platform_subscription: frm.doc.name, reason: values.reason },
							freeze: true,
							callback() {
								frm.reload_doc();
							},
						});
					},
					__("Request a New Mandate"),
					__("Request")
				);
			},
			__("Mandate")
		);

		if (frm.doc.payment_mandate) {
			frm.add_custom_button(
				__("Cancel Mandate"),
				() => {
					frappe.prompt(
						[
							{
								fieldname: "reason",
								fieldtype: "Small Text",
								label: __("What did the customer say?"),
								reqd: 1,
							},
						],
						(values) => {
							frappe.call({
								method: "a3_sola.api.admin_actions.cancel_mandate_as_operator",
								args: { platform_subscription: frm.doc.name, reason: values.reason },
								freeze: true,
								callback() {
									frm.reload_doc();
								},
							});
						},
						__("Cancel on the customer's behalf"),
						__("Cancel Mandate")
					);
				},
				__("Mandate")
			);
		}

		a3_sola.audit.add_button(frm);
		lifecycle_state(frm);
		lifecycle_actions(frm);

		if (frm.doc.route_reason) {
			frm.dashboard.set_headline_alert(
				frappe.utils.escape_html(frm.doc.route_reason),
				frm.doc.collection_route === "Auto Debit" ? "green" : "blue"
			);
		}
	},
});

// --------------------------------------------------------------- where it stands
//
// Two lines at the top of the form: the state it is in, and what happens to it next.
// "What happens next and when" is the question support is asked, and it should not
// require reading a policy record to answer.
function lifecycle_state(frm) {
	if (!frm.doc.status) return;

	const tone = {
		Trialing: "blue",
		Active: "green",
		"Past Due": "orange",
		Grace: "orange",
		Suspended: "red",
		Cancelling: "yellow",
		Cancelled: "red",
		Terminated: "red",
	}[frm.doc.status];

	let line = __("{0} for {1} day(s)", [
		frm.doc.status,
		frappe.utils.escape_html(String(frm.doc.days_in_state || 0)),
	]);
	if (frm.doc.access_state && frm.doc.access_state !== "Full") {
		line += " — " + __("access: {0}", [frm.doc.access_state]);
	}
	frm.dashboard.add_indicator(line, tone);

	if (frm.doc.next_state_change_on && frm.doc.next_state_change_to) {
		frm.dashboard.set_headline_alert(
			__("Unless something changes, this becomes <b>{0}</b> on <b>{1}</b>{2}.", [
				frappe.utils.escape_html(frm.doc.next_state_change_to),
				frappe.datetime.str_to_user(frm.doc.next_state_change_on),
				frm.doc.current_policy_stage
					? " (" + frappe.utils.escape_html(frm.doc.current_policy_stage) + ")"
					: "",
			]),
			"orange"
		);
	}
}

// ------------------------------------------------------------------- the actions
//
// Grouped under Lifecycle. Which appear depends on the state, because offering
// "Restore" on a healthy subscription invites somebody to click it and wonder what
// they did.
function lifecycle_actions(frm) {
	const operator = frappe.user.has_role([
		"Platform Lifecycle Operator",
		"Platform Admin",
		"System Manager",
	]);
	const retention = frappe.user.has_role([
		"Platform Retention Manager",
		"Platform Admin",
		"System Manager",
	]);
	const group = __("Lifecycle");

	if (retention && ["Active", "Trialing", "Past Due", "Grace"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Change Plan"), () => change_plan(frm), group);
	}

	if (retention && ["Active", "Trialing"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Add Seats"), () => add_seats(frm), group);
	}

	if (operator && ["Past Due", "Grace"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Extend Grace"), () => extend_grace(frm), group);
	}

	// Restoration is offered wherever it could help, and needs no approval anywhere.
	if (operator && ["Past Due", "Grace", "Suspended"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Restore Access"), () => restore(frm), group).addClass(
			"btn-primary"
		);
	}

	if (retention && ["Active", "Trialing", "Past Due", "Grace"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Cancel Subscription"), () => cancel(frm), group);
	}

	if (retention && ["Cancelled", "Cancelling"].includes(frm.doc.status)) {
		frm.add_custom_button(__("Reactivate"), () => reactivate(frm), group).addClass(
			"btn-primary"
		);
	}

	// Deliberately absent: a Suspend button. A customer is suspended by the policy, through
	// the approval queue, having been warned - not by somebody on this form deciding to.
}

function change_plan(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Change Plan"),
		fields: [
			{
				fieldname: "new_plan",
				fieldtype: "Link",
				options: "Subscription Plan",
				label: __("New Plan"),
				reqd: 1,
			},
			{
				fieldname: "new_cycle",
				fieldtype: "Select",
				options: ["", "Monthly", "Annual"].join("\n"),
				label: __("New Cycle"),
			},
			{ fieldname: "preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Request the change"),
		primary_action(values) {
			frappe.call({
				method: "a3_sola.api.lifecycle.plan_change.request_change",
				args: {
					subscription: frm.doc.name,
					new_plan: values.new_plan,
					new_cycle: values.new_cycle || null,
				},
				freeze: true,
				callback(response) {
					dialog.hide();
					frappe.set_route("Form", "Plan Change Request", response.message);
				},
			});
		},
	});

	// The breakdown is shown before anything is committed. Nobody should agree to a
	// proration figure they have not seen.
	const refresh_preview = frappe.utils.debounce(() => {
		const plan = dialog.get_value("new_plan");
		if (!plan) return;
		frappe.call({
			method: "a3_sola.api.lifecycle.plan_change.preview",
			args: {
				subscription: frm.doc.name,
				new_plan: plan,
				new_cycle: dialog.get_value("new_cycle") || null,
			},
			callback(response) {
				dialog.fields_dict.preview.$wrapper.html(render_proration(response.message));
			},
		});
	}, 400);

	dialog.fields_dict.new_plan.df.onchange = refresh_preview;
	dialog.fields_dict.new_cycle.df.onchange = refresh_preview;
	dialog.show();
}

function render_proration(quote) {
	if (!quote) return "";
	const rows = (quote.lines || [])
		.map(
			(line) =>
				`<tr><td>${frappe.utils.escape_html(line.description || "")}</td>
				 <td class="text-right">${format_currency(line.prorated_amount)}</td></tr>`
		)
		.join("");
	const mandate =
		quote.mandate_impact && quote.mandate_impact !== "None"
			? `<div class="alert alert-warning" style="margin-top:8px">
			     <b>${frappe.utils.escape_html(quote.mandate_impact)}</b><br>
			     ${frappe.utils.escape_html(quote.mandate_impact_detail || "")}
			   </div>`
			: "";
	const blockers = (quote.blockers || []).length
		? `<div class="alert alert-danger" style="margin-top:8px">
		     <b>${__("This cannot be applied yet")}</b><ul>${quote.blockers
				.map((b) => `<li>${frappe.utils.escape_html(b)}</li>`)
				.join("")}</ul></div>`
		: "";
	return `
		<p class="text-muted">${__("{0} of {1} day(s) remaining in this period.", [
			quote.days_remaining,
			quote.period_days,
		])}</p>
		<table class="table table-bordered table-sm"><tbody>${rows}
			<tr><td><b>${__("Payable now")}</b></td>
			    <td class="text-right"><b>${format_currency(quote.net_amount_payable)}</b></td></tr>
		</tbody></table>${mandate}${blockers}`;
}

function add_seats(frm) {
	frappe.prompt(
		[
			{
				fieldname: "count",
				fieldtype: "Int",
				label: __("How many seats?"),
				reqd: 1,
				default: 1,
			},
		],
		(values) => {
			frappe.call({
				method: "a3_sola.api.lifecycle.seats.request_seats",
				args: { tenant: frm.doc.__onload?.tenant, count: values.count },
				freeze: true,
				callback(response) {
					if (response.message) {
						frappe.set_route("Form", "Seat Change Request", response.message);
					}
				},
			});
		},
		__("Add Seats"),
		__("Continue")
	);
}

function extend_grace(frm) {
	frappe.prompt(
		[
			{ fieldname: "days", fieldtype: "Int", label: __("Extend by (days)"), reqd: 1, default: 7 },
			{
				fieldname: "reason",
				fieldtype: "Small Text",
				label: __("Why?"),
				reqd: 1,
				description: __("This goes in the event log and the customer may be told it."),
			},
		],
		(values) => {
			frappe.call({
				method: "a3_sola.api.lifecycle.admin.bulk_extend_grace",
				args: {
					subscriptions: [frm.doc.name],
					days: values.days,
					reason: values.reason,
					confirm: "EXTEND",
				},
				freeze: true,
				callback() {
					frm.reload_doc();
				},
			});
		},
		__("Extend Grace"),
		__("Extend")
	);
}

function restore(frm) {
	frappe.prompt(
		[{ fieldname: "reason", fieldtype: "Small Text", label: __("Why?"), reqd: 1 }],
		(values) => {
			frappe.call({
				method: "a3_sola.api.lifecycle.suspension.restore",
				args: {
					tenant: frm.doc.__onload?.tenant,
					trigger: "Manual",
					reason: values.reason,
				},
				freeze: true,
				callback() {
					frappe.show_alert({ message: __("Access restored"), indicator: "green" });
					frm.reload_doc();
				},
			});
		},
		__("Restore access now. Nobody has to approve this."),
		__("Restore")
	);
}

function cancel(frm) {
	frappe.prompt(
		[
			{
				fieldname: "reason",
				fieldtype: "Select",
				label: __("Reason"),
				reqd: 1,
				options: [
					"Too Expensive",
					"Missing Features",
					"Switching Provider",
					"Business Closed",
					"Poor Support",
					"Implementation Difficulty",
					"Temporary Pause",
					"Other",
				].join("\n"),
			},
			{
				fieldname: "reason_detail",
				fieldtype: "Small Text",
				label: __("In their words"),
				description: __("Worth capturing verbatim - it is what the churn report is for."),
			},
		],
		(values) => {
			frappe.call({
				method: "a3_sola.api.lifecycle.cancellation.request_cancellation",
				args: {
					subscription: frm.doc.name,
					reason: values.reason,
					reason_detail: values.reason_detail,
					requested_by: "Internal User",
				},
				freeze: true,
				callback(response) {
					frappe.set_route("Form", "Cancellation Request", response.message);
				},
			});
		},
		__("They keep full access until the period they have paid for expires."),
		__("Record the cancellation")
	);
}

function reactivate(frm) {
	frappe.confirm(
		__(
			"This restores every user to exactly the state they were in, and restarts billing from today. Continue?"
		),
		() => {
			frappe.call({
				method: "a3_sola.api.lifecycle.cancellation.reactivate_subscription",
				args: { subscription: frm.doc.name, trigger: "Internal User" },
				freeze: true,
				callback() {
					frm.reload_doc();
				},
			});
		}
	);
}
