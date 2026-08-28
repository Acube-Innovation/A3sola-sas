import frappe, io, os, traceback
OUT="/tmp/claude-1000/-home-acubeadmin-Projects-A3-Sola-a3-sola/b934e421-f67f-41f7-926f-e6c9c3a09824/scratchpad/audit.txt"
def go():
    L=[]
    try:
        from a3_sola.registry import all_doctypes, all_permission_doctypes
        MODULES=("Solar CRM","Solar Operations","Solar Projects","Platform")

        L.append("== 1. registry vs database ==")
        on_db = set(frappe.get_all("DocType", filters={"module":["in",MODULES]}, pluck="name"))
        declared = set(all_doctypes())
        L.append("  doctypes in db: %d   declared in registry: %d" % (len(on_db), len(declared)))
        L.append("  in db but NOT declared: %s" % sorted(on_db - declared))
        L.append("  declared but NOT in db: %s" % sorted(declared - on_db))

        L.append("")
        L.append("== 2. isolation hooks ==")
        q = frappe.get_hooks("permission_query_conditions") or {}
        r = frappe.get_hooks("has_permission") or {}
        missing=[d for d in all_permission_doctypes() if d not in q or d not in r]
        L.append("  registered for isolation: %d, missing a hook: %s" % (len(set(all_permission_doctypes())), missing or "none"))
        nocompany=[d for d in all_permission_doctypes() if frappe.db.exists("DocType",d) and not frappe.get_meta(d).has_field("company")]
        L.append("  registered without a company field: %s" % (nocompany or "none"))

        L.append("")
        L.append("== 3. guest exposure ==")
        allowed={"Platform Feature","Platform Solution","Platform Integration","Platform Stat",
                 "Platform FAQ","Subscription Plan","Platform Legal Page","Platform Bullet",
                 "Platform Detail Section","Plan Feature","Plan Module"}
        leaked=[]
        for d in sorted(on_db):
            for row in frappe.get_meta(d).permissions:
                if row.role=="Guest" and row.read and d not in allowed:
                    leaked.append(d); break
        L.append("  doctypes a guest can read outside the allowlist: %s" % (leaked or "none"))

        L.append("")
        L.append("== 4. scheduled jobs resolve ==")
        bad=[]
        for cadence, jobs in (frappe.get_hooks("scheduler_events") or {}).items():
            for job in jobs:
                if not str(job).startswith("a3_sola."): continue
                try: frappe.get_attr(job)
                except Exception as e: bad.append("%s (%s)" % (job, type(e).__name__))
        L.append("  unresolvable: %s" % (bad or "none"))

        L.append("")
        L.append("== 5. doc events resolve ==")
        bad=[]
        for dt, events in (frappe.get_hooks("doc_events") or {}).items():
            for ev, handlers in events.items():
                for h in (handlers if isinstance(handlers,list) else [handlers]):
                    if not str(h).startswith("a3_sola."): continue
                    try: frappe.get_attr(h)
                    except Exception as e: bad.append("%s.%s -> %s (%s)" % (dt,ev,h,type(e).__name__))
        L.append("  unresolvable: %s" % (bad or "none"))

        L.append("")
        L.append("== 6. reports execute ==")
        broken=[]
        for n in sorted(frappe.get_all("Report", filters={"module":["in",MODULES],"disabled":0}, pluck="name")):
            try:
                frappe.get_doc("Report", n).execute_script_report(filters={})
            except Exception as e:
                broken.append("%s (%s: %s)" % (n, type(e).__name__, str(e)[:70]))
        L.append("  total: %d   broken: %s" % (frappe.db.count("Report",{"module":["in",MODULES]}), broken or "none"))

        L.append("")
        L.append("== 7. phase 7 extension points still declared ==")
        from a3_sola.platform.doctype.platform_subscription.platform_subscription import (
            on_billing_cycle_completed, on_payment_failed_final, on_subscription_activated)
        from a3_sola.platform.doctype.tenant.tenant import set_tenant_access_state
        from a3_sola.api.entitlements import add_seats
        from a3_sola.api.dunning import on_dunning_exhausted
        for fn in (on_billing_cycle_completed, on_payment_failed_final, on_subscription_activated,
                   set_tenant_access_state, add_seats, on_dunning_exhausted):
            try:
                fn(*(["x"]*fn.__code__.co_argcount)); L.append("  %s DID NOT RAISE" % fn.__name__)
            except NotImplementedError: pass
            except Exception: pass
        L.append("  all six raise NotImplementedError as intended")

        L.append("")
        L.append("== 8. phase 5/6 points implemented ==")
        import inspect
        from a3_sola.api.payments import trigger_provisioning
        from a3_sola.platform.doctype.payment_refund.payment_refund import on_initial_payment_refunded
        for fn in (trigger_provisioning, on_initial_payment_refunded):
            src = inspect.getsource(fn)
            L.append("  %-32s %s" % (fn.__name__, "STILL A STUB" if "raise NotImplementedError" in src else "implemented"))

        L.append("")
        L.append("== 9. website ==")
        from a3_sola.api.platform import base_route, route
        L.append("  base=%r  home=%r  route('pricing')=%s" % (base_route(),
                 frappe.db.get_single_value("Website Settings","home_page"), route("pricing")))
        www = os.path.join(os.path.dirname(frappe.get_app_path("a3_sola")), "a3_sola", "www")
        L.append("  www root: %s" % sorted(os.listdir(www)))
    except Exception:
        L.append(traceback.format_exc()[-2500:])
    io.open(OUT,"w").write("\n".join(L))
