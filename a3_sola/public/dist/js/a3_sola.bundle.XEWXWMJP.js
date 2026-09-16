(() => {
  var __defProp = Object.defineProperty;
  var __getOwnPropSymbols = Object.getOwnPropertySymbols;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __propIsEnum = Object.prototype.propertyIsEnumerable;
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __spreadValues = (a, b) => {
    for (var prop in b || (b = {}))
      if (__hasOwnProp.call(b, prop))
        __defNormalProp(a, prop, b[prop]);
    if (__getOwnPropSymbols)
      for (var prop of __getOwnPropSymbols(b)) {
        if (__propIsEnum.call(b, prop))
          __defNormalProp(a, prop, b[prop]);
      }
    return a;
  };

  // ../a3_sola/a3_sola/public/js/lead_outreach.js
  frappe.ui.form.on("Lead", {
    refresh(frm) {
      if (frm.doc.__islocal)
        return;
      if (!frm.doc.solar_consumer && frm.doc.discom) {
        frm.add_custom_button(__("Create Solar Consumer"), () => {
          frappe.call({
            method: "a3_sola.overrides.lead.create_solar_consumer",
            args: { lead: frm.doc.name },
            freeze: true,
            callback(r) {
              if (r.message)
                frappe.set_route("Form", "Solar Consumer", r.message);
            }
          });
        }, __("Solar"));
      }
      frm.add_custom_button(__("Log Outreach"), () => log_outreach(frm), __("Solar"));
      if (frm.doc.followup_status === "FOLLOW UP DUE") {
        frm.dashboard.add_indicator(__("Follow up due"), "red");
      }
      if (frm.doc.consecutive_non_connects >= 3) {
        frm.dashboard.add_comment(
          __("{0} consecutive non-connects. Consider the breakup message.", [
            frm.doc.consecutive_non_connects
          ]),
          "orange",
          true
        );
      }
    }
  });
  function log_outreach(frm) {
    const d = new frappe.ui.Dialog({
      title: __("Log Outreach"),
      fields: [
        {
          fieldname: "channel",
          label: __("Channel"),
          fieldtype: "Select",
          reqd: 1,
          default: "Call",
          options: "Call\nWhatsApp\nEmail\nSMS\nSite Visit\nWalk-in"
        },
        {
          fieldname: "call_status",
          label: __("Call Status"),
          fieldtype: "Select",
          options: "\nNot Answered\nBusy\nSwitched Off\nConnected\nNot Applicable",
          depends_on: "eval:doc.channel=='Call'"
        },
        {
          fieldname: "outreach_step",
          label: __("Cadence Step"),
          fieldtype: "Select",
          default: frm.doc.outreach_stage || "Step 1: First Contact",
          options: [
            "Step 1: First Contact",
            "Step 2: 24hr Nudge",
            "Step 3: Value/ROI",
            "Step 4: Breakup/Close",
            "Completed: Proposal Sent",
            "Ad-hoc"
          ].join("\n")
        },
        { fieldname: "outcome", label: __("Outcome"), fieldtype: "Small Text" },
        { fieldname: "next_action", label: __("Next Action"), fieldtype: "Small Text" }
      ],
      primary_action_label: __("Log"),
      primary_action(values) {
        frappe.call({
          method: "a3_sola.api.outreach.log_outreach",
          args: __spreadValues({ lead: frm.doc.name }, values),
          freeze: true,
          callback(r) {
            d.hide();
            frm.reload_doc();
            if (r.message && r.message.next_followup_date) {
              frappe.show_alert({
                message: __("Next follow-up: {0}", [frappe.datetime.str_to_user(r.message.next_followup_date)]),
                indicator: "green"
              });
            }
          }
        });
      }
    });
    d.show();
  }

  // ../a3_sola/a3_sola/public/js/audit_trail.js
  frappe.provide("a3_sola.audit");
  a3_sola.audit.show_trail = function(frm) {
    frappe.call({
      method: "a3_sola.api.admin_actions.audit_trail",
      args: { reference_doctype: frm.doctype, reference_name: frm.doc.name },
      callback(r) {
        const rows = r.message || [];
        if (!rows.length) {
          frappe.msgprint({
            title: __("Audit Trail"),
            message: __("Nothing has been recorded against this record yet.")
          });
          return;
        }
        const body = rows.map(
          (row) => `<tr>
						<td style="white-space:nowrap;">${frappe.datetime.str_to_user(row.occurred_on)}</td>
						<td>${frappe.utils.escape_html(row.entry_type || "")}</td>
						<td>${frappe.utils.escape_html(row.subject || "")}</td>
						<td>${frappe.utils.escape_html(row.actor || "")}</td>
						<td>${frappe.utils.escape_html(row.reason || "")}</td>
					</tr>`
        ).join("");
        frappe.msgprint({
          title: __("Audit Trail"),
          wide: true,
          message: `<div style="overflow-x:auto;"><table class="table table-bordered" style="font-size:12px;">
					<thead><tr>
						<th>${__("When")}</th><th>${__("Event")}</th><th>${__("Summary")}</th>
						<th>${__("By")}</th><th>${__("Reason")}</th>
					</tr></thead>
					<tbody>${body}</tbody>
				</table></div>`
        });
      }
    });
  };
  a3_sola.audit.add_button = function(frm, group) {
    frm.add_custom_button(__("Audit Trail"), () => a3_sola.audit.show_trail(frm), group);
  };

  // ../a3_sola/a3_sola/public/js/sales_order_kyc.js
  frappe.ui.form.on("Sales Order", {
    refresh(frm) {
      if (!frm.doc.solar_consumer)
        return;
      render_kyc(frm);
      frm.add_custom_button(__("Fetch KYC"), () => render_kyc(frm, true), __("Solar"));
      frm.add_custom_button(__("Open Consumer KYC"), () => frappe.set_route("Form", "Solar Consumer", frm.doc.solar_consumer), __("Solar"));
    },
    solar_consumer(frm) {
      if (frm.doc.solar_consumer)
        render_kyc(frm);
    }
  });
  function render_kyc(frm, announce) {
    frappe.call({
      method: "a3_sola.api.kyc.get_kyc_status",
      args: { solar_consumer: frm.doc.solar_consumer, sales_order: frm.doc.name },
      callback(r) {
        const status = r.message || { rows: [], missing: [], complete: false };
        const rows = status.rows.map(
          (d) => `<tr><td>${frappe.utils.escape_html(d.kyc_type)}</td>
						<td>${d.attachment ? `<a href="${d.attachment}" target="_blank">${__("Open")}</a>` : "\u2014"}</td>
						<td>${frappe.utils.escape_html(d.document_no || "")}</td>
						<td>${d.is_verified ? "\u2713" : ""}</td></tr>`
        ).join("");
        const missing = status.missing.length ? `<p class="text-danger" style="margin:6px 0 0">${__("Missing")}: ${status.missing.map(frappe.utils.escape_html).join(", ")}</p>` : `<p class="text-success" style="margin:6px 0 0">${__("KYC complete")}</p>`;
        const table = rows ? `<table class="table table-bordered" style="font-size:12px;margin:0">
					<thead><tr><th>${__("Document")}</th><th>${__("File")}</th><th>${__("Number")}</th><th>${__("Verified")}</th></tr></thead>
					<tbody>${rows}</tbody></table>` : `<p class="text-muted" style="margin:0">${__("No KYC documents on the consumer yet.")}</p>`;
        if (frm.fields_dict.kyc_html)
          frm.fields_dict.kyc_html.$wrapper.html(table + missing);
        if (announce)
          frappe.show_alert({ message: status.complete ? __("KYC complete") : __("KYC incomplete"), indicator: status.complete ? "green" : "orange" });
      }
    });
  }
})();
//# sourceMappingURL=a3_sola.bundle.XEWXWMJP.js.map
