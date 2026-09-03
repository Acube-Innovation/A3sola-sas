# Endpoint inventory

Generated from the code by `a3_sola.api.security.inventory`. It is walked, not written, so it cannot be out of date - and the guard test fails the build if a guest-facing endpoint appears that nobody has reviewed.

- Whitelisted methods: **133**
- Reachable without logging in: **15**
- Authenticated only: **118**

## Reachable without logging in

These are the entire unauthenticated attack surface.

| Method | Rate limited | Validates | Reviewed | What it does |
|---|---|---|---|---|
| `a3_sola.api.invitations.accept_invitation` | yes | throws on bad input, rate limited | yes | Turn an invitation into a user. Guest endpoint, so every failure looks identical. |
| `a3_sola.api.payments.cancel_mandate` | yes | input sanitised, reference and token verified | yes | Let a customer cancel their mandate at any time. |
| `a3_sola.api.payments.complete_mock_payment` | yes | throws on bad input, input sanitised, reference and token verified | yes | Simulate the outcome of a payment. ONLY in Mock mode. |
| `a3_sola.api.payments.get_payment_status` | yes | reference and token verified | yes | What the polling page needs, and nothing else. |
| `a3_sola.api.payments.initiate_payment` | yes | throws on bad input, reference and token verified | yes | Create the gateway order and return exactly what checkout needs. |
| `a3_sola.api.payments.verify_checkout_payment` | yes | throws on bad input, input sanitised, reference and token verified | yes | Handle the browser's success callback. |
| `a3_sola.api.platform.calculate_plan_total` | yes | throws on bad input, explicit validation, rate limited | yes | What this plan actually costs. The single source of truth for every price shown. |
| `a3_sola.api.signup.get_signup_summary` | yes | reference and token verified | yes | Exactly what the summary page needs to render, and not one field more. |
| `a3_sola.api.signup.request_payment_contact` | yes | input sanitised, reference and token verified | yes | What the summary page's Proceed button does. |
| `a3_sola.api.signup.resend_verification` | yes | input sanitised, rate limited per identifier, enumeration-safe response | yes | Send the verification link again. Hard capped per signup. |
| `a3_sola.api.signup.submit_demo_request` | yes | throws on bad input, explicit validation, input sanitised, rate limited per identifier, captcha | yes | Capture a demo request. Same discipline as signup. |
| `a3_sola.api.signup.submit_signup` | yes | throws on bad input, explicit validation, input sanitised, rate limited per identifier, enumeration-safe response, captcha | yes | Create a signup and send a verification email. |
| `a3_sola.api.signup.update_plan_selection` | yes | throws on bad input, input sanitised, reference and token verified | yes | Let a verified applicant change tier or cycle before paying. |
| `a3_sola.api.signup.verify_email` | yes | throws on bad input, input sanitised | yes | Consume a verification token. |
| `a3_sola.api.webhooks.receive` | yes | HMAC signature verified | yes | The single webhook endpoint. Always returns 200. |

## Authenticated

| Method | Checks a role | Validates | What it does |
|---|---|---|---|
| `a3_sola.api.accounting.cancel_and_repost` | no | throws on bad input | Cancel the linked entry and post it again. Never silently edit a submitted entry. |
| `a3_sola.api.accounting.write_off_subsidy_recovery` | yes | throws on bad input, permission checked | Give up on a subsidy gap the customer is never going to pay back. |
| `a3_sola.api.accounting_payments.cancel_and_repost` | no | throws on bad input | Correct an entry by reversing it, never by editing a submitted one. |
| `a3_sola.api.admin_actions.audit_trail` | yes | none visible | What the desk shows in the 'History' dialog on a payment record. |
| `a3_sola.api.admin_actions.cancel_mandate_as_operator` | no | throws on bad input | Cancel on the customer's behalf - they rang up rather than clicking the button. |
| `a3_sola.api.admin_actions.mark_paid_manually` | yes | throws on bad input, role required | Assert a payment the gateway cannot confirm - a NEFT transfer, a cheque, a cash deal. |
| `a3_sola.api.admin_actions.refetch_payment_status` | no | throws on bad input | Ask the gateway what it thinks, and reconcile our record to the answer. |
| `a3_sola.api.admin_actions.reissue_payment_link` | no | throws on bad input | Send the customer a fresh link when the old one expired or never arrived. |
| `a3_sola.api.admin_actions.reprocess_webhook` | no | throws on bad input | Run a stored webhook through its handler again. |
| `a3_sola.api.admin_actions.reregister_mandate` | no | none visible | Ask the customer to authorise a new mandate. |
| `a3_sola.api.admin_actions.run_reconciliation_for_range` | no | none visible | Re-run matching across a date range, for when a settlement arrived out of order. |
| `a3_sola.api.audit.verify` | yes | none visible | Desk-callable chain check. Read access to the trail is enough to run it. |
| `a3_sola.api.billing.create_milestone_invoice` | yes | throws on bad input, explicit validation, permission checked | Build a DRAFT Sales Invoice for one milestone. NEVER auto-submit. |
| `a3_sola.api.billing.create_statutory_reimbursement_invoice` | yes | throws on bad input, permission checked | Bill the statutory fees the company fronted, OUTSIDE the composite supply. |
| `a3_sola.api.billing_portal.available_plans` | yes | none visible | Every plan they could move to, with what each would cost them. |
| `a3_sola.api.billing_portal.cancel_my_mandate` | yes | ownership checked | The customer's own cancellation route. |
| `a3_sola.api.billing_portal.cancel_my_subscription` | yes | none visible | End of period, always, from here. Immediate cancellation may involve a refund and |
| `a3_sola.api.billing_portal.change_my_plan` | yes | none visible |  |
| `a3_sola.api.billing_portal.change_my_seats` | yes | none visible | Buying a seat mid-workday should take under a minute, so this is the whole flow. |
| `a3_sola.api.billing_portal.download_invoice` | yes | throws on bad input, ownership checked | Resolve an invoice only after proving the caller owns its subscription. |
| `a3_sola.api.billing_portal.my_history` | yes | none visible | Their own subscription events, in language a customer can read. |
| `a3_sola.api.billing_portal.my_plan` | yes | none visible | The current plan, what it costs, and when it renews. |
| `a3_sola.api.billing_portal.my_team` | no | none visible | The user list with last activity - what a downgrade decision needs. |
| `a3_sola.api.billing_portal.pay_outstanding` | yes | ownership checked | A pay-now link for an outstanding invoice. |
| `a3_sola.api.billing_portal.preview_plan_change` | yes | none visible | The proration and any consequence for how they pay - BEFORE they confirm. |
| `a3_sola.api.billing_portal.preview_seat_change` | no | none visible |  |
| `a3_sola.api.billing_portal.reactivate_my_subscription` | yes | none visible |  |
| `a3_sola.api.calculations.build_cashflow` | no | none visible | Year-wise projection with generation degradation and tariff escalation. |
| `a3_sola.api.calculations.calculate_bill` | no | throws on bad input | Bill `units` against a telescopic tariff, slab by slab. |
| `a3_sola.api.calculations.calculate_savings` | no | none visible | Differential bill between pre- and post-solar consumption. |
| `a3_sola.api.calculations.estimate_daily_generation_band` | no | none visible | The daily unit range the proposal prints. |
| `a3_sola.api.calculations.estimate_generation` | no | none visible | Annual and monthly generation for a capacity, derated for shading. |
| `a3_sola.api.calculations.get_subsidy_amount` | no | throws on bad input | Resolve the central financial assistance for a capacity under a scheme. |
| `a3_sola.api.costing.recalculate_project_costs` | yes | explicit validation, permission checked | Rebuild the cost entry table and every costing field from source documents. |
| `a3_sola.api.documents.generate_document` | yes | throws on bad input, explicit validation, permission checked | Render one template, attach it and log it. Idempotent - regenerating replaces. |
| `a3_sola.api.documents.generate_document_pack` | yes | throws on bad input, permission checked | Generate every due, applicable, active template. |
| `a3_sola.api.invitations.invite` | yes | throws on bad input, rate limited | Called by the tenant admin from their own seats page. |
| `a3_sola.api.invitations.my_seats` | yes | throws on bad input | What the tenant admin's own seats page shows. |
| `a3_sola.api.invitations.resend` | yes | throws on bad input |  |
| `a3_sola.api.invitations.revoke` | yes | throws on bad input | Kills the token immediately. A revoked link that still works is not revoked. |
| `a3_sola.api.isolation.rerun` | yes | role required | Available at any time, because a regression in a later phase is exactly the risk. |
| `a3_sola.api.lifecycle.admin.bulk_extend_grace` | yes | throws on bad input, role required | For a gateway outage: push everybody's next state change out by N days. |
| `a3_sola.api.lifecycle.admin.bulk_reassign_policy` | yes | throws on bad input, role required |  |
| `a3_sola.api.lifecycle.admin.bulk_restore` | yes | throws on bad input, role required | After an incident: put everybody back. Each restoration is its own event. |
| `a3_sola.api.lifecycle.admin.enable_automatic_suspension` | yes | throws on bad input, role required | Refuse until pre-flight passes, and name what is missing. |
| `a3_sola.api.lifecycle.admin.kill_switch` | yes | throws on bad input, role required | Halt every lifecycle state change at once. Evaluation and logging carry on. |
| `a3_sola.api.lifecycle.admin.preflight` | no | none visible | Every precondition for automatic suspension, each reported pass or fail. |
| `a3_sola.api.lifecycle.admin.run_simulation` | yes | role required | Every decision the engine would make, writing nothing. Stamps that it was run. |
| `a3_sola.api.lifecycle.admin.tenant_360` | yes | role required | One page per tenant, so support answers a question without opening six doctypes. |
| `a3_sola.api.lifecycle.cancellation.reactivate_subscription` | no | throws on bad input | Bring a cancelled tenant back, exactly as they were. Idempotent. |
| `a3_sola.api.lifecycle.cancellation.request_cancellation` | no | throws on bad input | Record the cancellation and schedule it. Nothing is switched off here. |
| `a3_sola.api.lifecycle.cancellation.withdraw` | no | none visible | The customer changed their mind before it matured. |
| `a3_sola.api.lifecycle.plan_change.preview` | no | none visible | The breakdown the customer sees before confirming. Writes nothing. |
| `a3_sola.api.lifecycle.plan_change.request_change` | no | none visible | Build the Plan Change Request, priced and checked, and submit it. |
| `a3_sola.api.lifecycle.seats.preview_seats` | no | none visible | What another seat costs, right now, before the customer commits. |
| `a3_sola.api.lifecycle.seats.request_seats` | no | throws on bad input | Create the Seat Change Request. Additions are immediate; removals wait. |
| `a3_sola.api.lifecycle.suspension.approve` | yes | throws on bad input, role required | Apply a pending suspension. The warning gate is checked here, loudly. |
| `a3_sola.api.lifecycle.suspension.reject` | yes | throws on bad input, role required | Cancel a pending suspension. The reason is mandatory and is written to the log. |
| `a3_sola.api.lifecycle.suspension.restore` | no | none visible | One click, from anywhere. The payment webhook, the engine and the admin button all |
| `a3_sola.api.materials.create_material_request` | yes | throws on bad input, permission checked | Material Transfer request from the package BOM, exploded to installed capacity. |
| `a3_sola.api.materials.get_installation_material_summary` | yes | permission checked | Per item: BOM required, requested, received at site, consumed, returned, variance. |
| `a3_sola.api.om.create_om_contract` | no | throws on bad input | Create the five-year obligation record with its visit calendar. Idempotent. |
| `a3_sola.api.om.renew_contract` | yes | throws on bad input, permission checked | Raise the successor contract when the five years are up. |
| `a3_sola.api.onboarding.complete_task` | no | throws on bad input |  |
| `a3_sola.api.onboarding.my_checklist` | no | none visible | What the tenant's own onboarding page reads. |
| `a3_sola.api.outreach.log_outreach` | yes | permission checked | Append an Outreach Log row and advance the cadence. |
| `a3_sola.api.outreach.render_message` | no | none visible | Render an Outreach Message Template for a document. |
| `a3_sola.api.outreach.whatsapp_link` | no | none visible | A wa.me deep link prefilled with the rendered text. |
| `a3_sola.api.portal.download` | yes | throws on bad input, ownership checked | Resolve a document's file URL only after proving the caller owns the job. |
| `a3_sola.api.portal.raise_ticket` | yes | throws on bad input, ownership checked | Let a customer report a fault against their own system, and only their own. |
| `a3_sola.api.provisioning.orchestrator.enqueue_provisioning` | yes | role required | Queue a run. This is what everything outside the worker calls. |
| `a3_sola.api.reconciliation.fetch_settlement` | yes | throws on bad input, role required | Pull a settlement from the gateway. Falls back to the CSV path when unavailable. |
| `a3_sola.api.reconciliation.import_settlement_csv` | yes | throws on bad input, role required | Build a reconciliation from a pasted settlement report. |
| `a3_sola.api.regulation.check_connection_type` | no | none visible | Is this capacity allowed on this connection type today? |
| `a3_sola.api.regulation.get_active_rules` | no | none visible | Every Grid Regulation Rule in force on a date, with its stay resolved. |
| `a3_sola.api.regulation.get_customer_clauses` | no | none visible | The proposal clauses for the rules in force, rendered from the rules themselves. |
| `a3_sola.api.security.audit.run_isolation_audit` | yes | role required | Re-run the attack suite against live data. Read-only by default. |
| `a3_sola.api.serials.export_serial_manifest` | yes | permission checked | CSV in the format chosen in Settings, for portal submission and DCR audit. |
| `a3_sola.api.serials.get_completion_report_data` | yes | permission checked | The exact field set the bank and DISCOM completion reports carry. |
| `a3_sola.api.serials.pull_serials_from_delivery_note` | yes | explicit validation, permission checked | Import every serialised item from Delivery Notes linked to this installation. |
| `a3_sola.api.sla.capture_reading` | yes | throws on bad input, permission checked | Record the meter while the technician is still on the roof. |
| `a3_sola.api.sla.import_readings` | yes | throws on bad input, permission checked | Load a month of readings from an inverter portal export. |
| `a3_sola.api.sla.performance_series` | yes | permission checked | Expected against actual by month, for the contract's own chart. |
| `a3_sola.api.stages.advance_stage` | yes | throws on bad input, permission checked | Complete a stage and start the next. |
| `a3_sola.api.stages.block_stage` | yes | throws on bad input, permission checked |  |
| `a3_sola.api.stages.revert_stage` | yes | throws on bad input, permission checked | Manager-only. Clears this stage and every stage after it. |
| `a3_sola.api.stages.skip_stage` | yes | throws on bad input, permission checked | Manager-only, and refused for a mandatory stage. |
| `a3_sola.api.stages.unblock_stage` | yes | throws on bad input, permission checked |  |
| `a3_sola.api.statutory.get_refund_due` | no | none visible | The registration-fee refund recoverable after commissioning. |
| `a3_sola.api.statutory.get_statutory_fees` | no | none visible | Resolve every statutory charge for one job. |
| `a3_sola.api.tenant_admin.apply_entitlements` | yes | role required | Reconcile every user's roles against the snapshot. Also Phase 7's upgrade path. |
| `a3_sola.api.tenant_admin.export_tenant_data` | yes | throws on bad input, role required | Everything belonging to this tenant, as a downloadable archive. |
| `a3_sola.api.tenant_admin.recalculate_usage` | yes | role required |  |
| `a3_sola.api.tenant_admin.resend_welcome` | yes | role required |  |
| `a3_sola.api.tenant_admin.tenant_dashboard` | yes | role required | What the Tenant form's dashboard shows: everything about one customer, in one call. |
| `a3_sola.api.tenant_admin.terminate_tenant` | yes | throws on bad input, role required | End a tenant's access. Exports first, disables second, deletes nothing. |
| `a3_sola.api.tenant_settings.get_account_mapping` | no | none visible |  |
| `a3_sola.api.tenant_settings.my_accounts` | no | none visible | Account options for the mapping form - the caller's own company, nothing else. |
| `a3_sola.api.tenant_settings.save_account_mapping` | no | throws on bad input | Write the caller's own mapping row. Refuses any account outside their company. |
| `a3_sola.api.webhooks.reprocess` | yes | role required | Admin action on a Payment Webhook Log. |
| `a3_sola.overrides.company.copy_from_company` | yes | permission checked | Fill all three blocks from the standard Company fields. |
| `a3_sola.overrides.lead.create_solar_consumer` | yes | throws on bad input, permission checked | Map a Lead's solar fields into a new Solar Consumer and link it back. |
| `a3_sola.platform.doctype.provisioning_job.provisioning_job.health` | yes | role required | Every job waiting on a human, oldest first - because the oldest is the worst. |
| `a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate.add_option_from_package` | yes | permission checked | Append a priced option from a package, using inverter option 1 or 2. |
| `a3_sola.solar_crm.doctype.solar_design_estimate.solar_design_estimate.compare_packages` | yes | permission checked | Run the calculation across every active package within +/- 2 kW of the recommendation. |
| `a3_sola.solar_crm.doctype.solar_package.solar_package.create_item_and_bom` | yes | permission checked | Create the ERPNext Item and BOM from the component table, then link them back. |
| `a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.generate_proposal` | yes | permission checked | Render the PDF, name it on the client's convention, and render the greeting message. |
| `a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.get_whatsapp_link` | yes | permission checked | A wa.me deep link prefilled with the greeting, so sending is one tap. |
| `a3_sola.solar_crm.doctype.solar_proposal.solar_proposal.mark_sent` | yes | permission checked | Record dispatch, advance the lead's cadence and log the outreach. |
| `a3_sola.solar_crm.doctype.subsidy_eligibility_check.subsidy_eligibility_check.waive_rule` | yes | throws on bad input, explicit validation, permission checked | Waive one failing rule. Manager-only, reason mandatory, stamped and auditable. |
| `a3_sola.solar_operations.doctype.installation_work_order.installation_work_order.get_technician_schedule` | no | none visible | Crew utilisation, for the calendar and the dashboard chart. |
| `a3_sola.solar_operations.doctype.net_metering_agreement.net_metering_agreement.terminate` | yes | throws on bad input, permission checked | Either party may terminate on thirty days' notice. Record it; never delete. |
| `a3_sola.solar_operations.doctype.portal_application.portal_application.approve_and_advance` | yes | throws on bad input, permission checked | Approve the application, file its letter and advance the mapped stage. |
| `a3_sola.solar_operations.doctype.solar_installation.solar_installation.get_stage_chain_html` | yes | permission checked | The visual stage chain rendered on the form. |
| `a3_sola.solar_operations.doctype.solar_installation.solar_installation.verify_document` | yes | throws on bad input, explicit validation, permission checked | Stamp a checklist row as verified. Evidence must be checked, not just attached. |
| `a3_sola.solar_projects.doctype.generation_reading.generation_reading.import_readings` | no | none visible | Bulk import - most clients export from an inverter portal rather than key them in. |
| `a3_sola.solar_projects.doctype.solar_billing_plan.solar_billing_plan.trigger_milestone` | yes | throws on bad input, explicit validation, permission checked | Manual and On Date triggers. |
| `a3_sola.solar_projects.doctype.solar_om_contract.solar_om_contract.renew_contract` | yes | throws on bad input, permission checked | Create a paid successor dated from the predecessor's end date. |
