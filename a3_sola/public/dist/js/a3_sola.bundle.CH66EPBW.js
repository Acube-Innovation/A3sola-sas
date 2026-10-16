(() => {
  var __defProp = Object.defineProperty;
  var __defProps = Object.defineProperties;
  var __getOwnPropDescs = Object.getOwnPropertyDescriptors;
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
  var __spreadProps = (a, b) => __defProps(a, __getOwnPropDescs(b));

  // ../a3_sola/a3_sola/public/js/lead_outreach.js
  frappe.ui.form.on("Lead", {
    refresh(frm) {
      if (frm.doc.__islocal)
        return;
      if (!frm.doc.solar_consumer && frm.doc.discom) {
        frm.add_custom_button(__("Create Customer"), () => consumer_address_dialog(frm), __("Solar"));
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
  function consumer_address_dialog(frm) {
    const different = 'eval:doc.permanent_address_same=="No"';
    const parts = (prefix, when) => {
      const reqd = when ? { depends_on: when, mandatory_depends_on: when } : { reqd: 1 };
      const shown = when ? { depends_on: when } : {};
      return [
        __spreadValues({ fieldname: `${prefix}_address_line1`, fieldtype: "Data", label: __("House Name / Building No.") }, reqd),
        __spreadValues({ fieldname: `${prefix}_address_line2`, fieldtype: "Data", label: __("Street / Area") }, shown),
        __spreadValues({ fieldname: `${prefix}_city`, fieldtype: "Data", label: __("City / Town / Village") }, reqd),
        { fieldtype: "Column Break" },
        __spreadProps(__spreadValues({
          fieldname: `${prefix}_state`,
          fieldtype: "Link",
          options: "Indian State",
          label: __("State"),
          default: "Kerala"
        }, reqd), {
          onchange: () => dialog.set_value(`${prefix}_district`, null)
        }),
        __spreadProps(__spreadValues({
          fieldname: `${prefix}_district`,
          fieldtype: "Link",
          options: "Indian District",
          label: __("District")
        }, reqd), {
          get_query: () => ({ filters: dialog.get_value(`${prefix}_state`) ? { state: dialog.get_value(`${prefix}_state`) } : {} })
        }),
        __spreadValues({ fieldname: `${prefix}_pincode`, fieldtype: "Data", label: __("PIN Code") }, reqd)
      ];
    };
    const dialog = new frappe.ui.Dialog({
      title: __("Customer Address"),
      size: "large",
      fields: [
        { fieldtype: "Section Break", label: __("Installation Site Address") },
        ...parts("site"),
        { fieldtype: "Section Break", label: __("Permanent Address") },
        {
          fieldname: "permanent_address_same",
          fieldtype: "Select",
          label: __("Permanent Address Same as Installation Site?"),
          options: "Yes\nNo",
          default: "Yes",
          reqd: 1
        },
        { fieldtype: "Section Break", depends_on: different },
        ...parts("permanent", different)
      ],
      primary_action_label: __("Create"),
      primary_action(values) {
        frappe.call({
          method: "a3_sola.overrides.lead.create_solar_consumer",
          args: { lead: frm.doc.name, address: values },
          freeze: true,
          callback(r) {
            dialog.hide();
            if (r.message)
              frappe.set_route("Form", "Solar Consumer", r.message);
          }
        });
      }
    });
    dialog.set_values({ site_city: frm.doc.city, site_state: frm.doc.state || "Kerala" }).then(() => {
      if (frm.doc.district)
        dialog.set_value("site_district", frm.doc.district);
    });
    dialog.show();
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
})();
//# sourceMappingURL=a3_sola.bundle.CH66EPBW.js.map
