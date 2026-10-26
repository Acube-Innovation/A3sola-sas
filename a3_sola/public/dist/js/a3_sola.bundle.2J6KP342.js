(()=>{var c=Object.defineProperty,p=Object.defineProperties;var u=Object.getOwnPropertyDescriptors;var _=Object.getOwnPropertySymbols;var m=Object.prototype.hasOwnProperty,f=Object.prototype.propertyIsEnumerable;var r=(e,t,a)=>t in e?c(e,t,{enumerable:!0,configurable:!0,writable:!0,value:a}):e[t]=a,s=(e,t)=>{for(var a in t||(t={}))m.call(t,a)&&r(e,a,t[a]);if(_)for(var a of _(t))f.call(t,a)&&r(e,a,t[a]);return e},i=(e,t)=>p(e,u(t));frappe.ui.form.on("Lead",{refresh(e){e.doc.__islocal||(!e.doc.solar_consumer&&e.doc.discom&&e.add_custom_button(__("Create Customer"),()=>y(e),__("Solar")),e.add_custom_button(__("Log Outreach"),()=>h(e),__("Solar")),e.doc.followup_status==="FOLLOW UP DUE"&&e.dashboard.add_indicator(__("Follow up due"),"red"),e.doc.consecutive_non_connects>=3&&e.dashboard.add_comment(__("{0} consecutive non-connects. Consider the breakup message.",[e.doc.consecutive_non_connects]),"orange",!0))}});function h(e){let t=new frappe.ui.Dialog({title:__("Log Outreach"),fields:[{fieldname:"channel",label:__("Channel"),fieldtype:"Select",reqd:1,default:"Call",options:`Call
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
`)},{fieldname:"outcome",label:__("Outcome"),fieldtype:"Small Text"},{fieldname:"next_action",label:__("Next Action"),fieldtype:"Small Text"}],primary_action_label:__("Log"),primary_action(a){frappe.call({method:"a3_sola.api.outreach.log_outreach",args:s({lead:e.doc.name},a),freeze:!0,callback(o){t.hide(),e.reload_doc(),o.message&&o.message.next_followup_date&&frappe.show_alert({message:__("Next follow-up: {0}",[frappe.datetime.str_to_user(o.message.next_followup_date)]),indicator:"green"})}})}});t.show()}function y(e){let t='eval:doc.permanent_address_same=="No"',a=(l,n)=>{let d=n?{depends_on:n}:{};return[s({fieldname:`${l}_address_line1`,fieldtype:"Data",label:__("House Name / Building No.")},d),s({fieldname:`${l}_address_line2`,fieldtype:"Data",label:__("Street / Area")},d),s({fieldname:`${l}_city`,fieldtype:"Data",label:__("City / Town / Village")},d),{fieldtype:"Column Break"},i(s({fieldname:`${l}_state`,fieldtype:"Link",options:"Indian State",label:__("State"),default:"Kerala"},d),{onchange:()=>o.set_value(`${l}_district`,null)}),i(s({fieldname:`${l}_district`,fieldtype:"Link",options:"Indian District",label:__("District")},d),{get_query:()=>({filters:o.get_value(`${l}_state`)?{state:o.get_value(`${l}_state`)}:{}})}),s({fieldname:`${l}_pincode`,fieldtype:"Data",label:__("PIN Code")},d)]},o=new frappe.ui.Dialog({title:__("Customer Address"),size:"large",fields:[{fieldtype:"Section Break",label:__("Installation Site Address")},...a("site"),{fieldtype:"Section Break",label:__("Permanent Address")},{fieldname:"permanent_address_same",fieldtype:"Select",label:__("Permanent Address Same as Installation Site?"),options:`Yes
No`,default:"Yes",reqd:1},{fieldtype:"Section Break",depends_on:t},...a("permanent",t)],primary_action_label:__("Create"),primary_action(l){frappe.call({method:"a3_sola.overrides.lead.create_solar_consumer",args:{lead:e.doc.name,address:l},freeze:!0,callback(n){o.hide(),n.message&&frappe.set_route("Form","Solar Consumer",n.message)}})}});o.set_values({site_city:e.doc.city,site_state:e.doc.state||"Kerala"}).then(()=>{e.doc.district&&o.set_value("site_district",e.doc.district)}),o.show()}frappe.provide("a3_sola.audit");a3_sola.audit.show_trail=function(e){frappe.call({method:"a3_sola.api.admin_actions.audit_trail",args:{reference_doctype:e.doctype,reference_name:e.doc.name},callback(t){let a=t.message||[];if(!a.length){frappe.msgprint({title:__("Audit Trail"),message:__("Nothing has been recorded against this record yet.")});return}let o=a.map(l=>`<tr>
						<td style="white-space:nowrap;">${frappe.datetime.str_to_user(l.occurred_on)}</td>
						<td>${frappe.utils.escape_html(l.entry_type||"")}</td>
						<td>${frappe.utils.escape_html(l.subject||"")}</td>
						<td>${frappe.utils.escape_html(l.actor||"")}</td>
						<td>${frappe.utils.escape_html(l.reason||"")}</td>
					</tr>`).join("");frappe.msgprint({title:__("Audit Trail"),wide:!0,message:`<div style="overflow-x:auto;"><table class="table table-bordered" style="font-size:12px;">
					<thead><tr>
						<th>${__("When")}</th><th>${__("Event")}</th><th>${__("Summary")}</th>
						<th>${__("By")}</th><th>${__("Reason")}</th>
					</tr></thead>
					<tbody>${o}</tbody>
				</table></div>`})}})};a3_sola.audit.add_button=function(e,t){e.add_custom_button(__("Audit Trail"),()=>a3_sola.audit.show_trail(e),t)};})();
//# sourceMappingURL=a3_sola.bundle.2J6KP342.js.map
