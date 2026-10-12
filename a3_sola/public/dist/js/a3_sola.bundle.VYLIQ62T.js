(()=>{var p=Object.defineProperty;var n=Object.getOwnPropertySymbols;var u=Object.prototype.hasOwnProperty,m=Object.prototype.propertyIsEnumerable;var r=(e,t,a)=>t in e?p(e,t,{enumerable:!0,configurable:!0,writable:!0,value:a}):e[t]=a,c=(e,t)=>{for(var a in t||(t={}))u.call(t,a)&&r(e,a,t[a]);if(n)for(var a of n(t))m.call(t,a)&&r(e,a,t[a]);return e};frappe.ui.form.on("Lead",{refresh(e){e.doc.__islocal||(!e.doc.solar_consumer&&e.doc.discom&&e.add_custom_button(__("Create Solar Consumer"),()=>{frappe.call({method:"a3_sola.overrides.lead.create_solar_consumer",args:{lead:e.doc.name},freeze:!0,callback(t){t.message&&frappe.set_route("Form","Solar Consumer",t.message)}})},__("Solar")),e.add_custom_button(__("Log Outreach"),()=>h(e),__("Solar")),e.doc.followup_status==="FOLLOW UP DUE"&&e.dashboard.add_indicator(__("Follow up due"),"red"),e.doc.consecutive_non_connects>=3&&e.dashboard.add_comment(__("{0} consecutive non-connects. Consider the breakup message.",[e.doc.consecutive_non_connects]),"orange",!0))}});function h(e){let t=new frappe.ui.Dialog({title:__("Log Outreach"),fields:[{fieldname:"channel",label:__("Channel"),fieldtype:"Select",reqd:1,default:"Call",options:`Call
WhatsApp
Email
SMS
Site Visit
Walk-in`},{fieldname:"call_status",label:__("Call Status"),fieldtype:"Select",options:`
Not Answered
Busy
Switched Off
Connected
Not Applicable`,depends_on:"eval:doc.channel=='Call'"},{fieldname:"outreach_step",label:__("Cadence Step"),fieldtype:"Select",default:e.doc.outreach_stage||"Step 1: First Contact",options:["Step 1: First Contact","Step 2: 24hr Nudge","Step 3: Value/ROI","Step 4: Breakup/Close","Completed: Proposal Sent","Ad-hoc"].join(`
`)},{fieldname:"outcome",label:__("Outcome"),fieldtype:"Small Text"},{fieldname:"next_action",label:__("Next Action"),fieldtype:"Small Text"}],primary_action_label:__("Log"),primary_action(a){frappe.call({method:"a3_sola.api.outreach.log_outreach",args:c({lead:e.doc.name},a),freeze:!0,callback(o){t.hide(),e.reload_doc(),o.message&&o.message.next_followup_date&&frappe.show_alert({message:__("Next follow-up: {0}",[frappe.datetime.str_to_user(o.message.next_followup_date)]),indicator:"green"})}})}});t.show()}frappe.provide("a3_sola.audit");a3_sola.audit.show_trail=function(e){frappe.call({method:"a3_sola.api.admin_actions.audit_trail",args:{reference_doctype:e.doctype,reference_name:e.doc.name},callback(t){let a=t.message||[];if(!a.length){frappe.msgprint({title:__("Audit Trail"),message:__("Nothing has been recorded against this record yet.")});return}let o=a.map(s=>`<tr>
						<td style="white-space:nowrap;">${frappe.datetime.str_to_user(s.occurred_on)}</td>
						<td>${frappe.utils.escape_html(s.entry_type||"")}</td>
						<td>${frappe.utils.escape_html(s.subject||"")}</td>
						<td>${frappe.utils.escape_html(s.actor||"")}</td>
						<td>${frappe.utils.escape_html(s.reason||"")}</td>
					</tr>`).join("");frappe.msgprint({title:__("Audit Trail"),wide:!0,message:`<div style="overflow-x:auto;"><table class="table table-bordered" style="font-size:12px;">
					<thead><tr>
						<th>${__("When")}</th><th>${__("Event")}</th><th>${__("Summary")}</th>
						<th>${__("By")}</th><th>${__("Reason")}</th>
					</tr></thead>
					<tbody>${o}</tbody>
				</table></div>`})}})};a3_sola.audit.add_button=function(e,t){e.add_custom_button(__("Audit Trail"),()=>a3_sola.audit.show_trail(e),t)};frappe.ui.form.on("Sales Order",{refresh(e){!e.doc.solar_consumer||(_(e),e.add_custom_button(__("Fetch KYC"),()=>_(e,!0),__("Solar")),e.add_custom_button(__("Open Consumer KYC"),()=>frappe.set_route("Form","Solar Consumer",e.doc.solar_consumer),__("Solar")))},solar_consumer(e){e.doc.solar_consumer&&_(e)}});function _(e,t){frappe.call({method:"a3_sola.api.kyc.get_kyc_status",args:{solar_consumer:e.doc.solar_consumer,sales_order:e.doc.name},callback(a){let o=a.message||{rows:[],missing:[],complete:!1},s=o.rows.map(l=>`<tr><td>${frappe.utils.escape_html(l.kyc_type)}</td>
						<td>${l.attachment?`<a href="${l.attachment}" target="_blank">${__("Open")}</a>`:"\u2014"}</td>
						<td>${frappe.utils.escape_html(l.document_no||"")}</td>
						<td>${l.is_verified?"\u2713":""}</td></tr>`).join(""),d=o.missing.length?`<p class="text-danger" style="margin:6px 0 0">${__("Missing")}: ${o.missing.map(frappe.utils.escape_html).join(", ")}</p>`:`<p class="text-success" style="margin:6px 0 0">${__("KYC complete")}</p>`,i=s?`<table class="table table-bordered" style="font-size:12px;margin:0">
					<thead><tr><th>${__("Document")}</th><th>${__("File")}</th><th>${__("Number")}</th><th>${__("Verified")}</th></tr></thead>
					<tbody>${s}</tbody></table>`:`<p class="text-muted" style="margin:0">${__("No KYC documents on the consumer yet.")}</p>`;e.fields_dict.kyc_html&&e.fields_dict.kyc_html.$wrapper.html(i+d),t&&frappe.show_alert({message:o.complete?__("KYC complete"):__("KYC incomplete"),indicator:o.complete?"green":"orange"})}})}})();
//# sourceMappingURL=a3_sola.bundle.VYLIQ62T.js.map
