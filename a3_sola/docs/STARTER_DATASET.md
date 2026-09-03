# The starter dataset

One company, one login, and one job followed from the first enquiry to its fourth year of
service — every document in the chain linked to the one before it, so the whole thing can
be walked from the **Connections** panel without ever using the search bar.

It is installed by the patch `a3_sola.patches.v1_0.install_starter_dataset`, which runs on
the next `bench migrate` on every site. Nothing has to be configured for it to run.

---

## Signing in

    starter.engineer@example.com / a3sola-starter

That password is in the source (`a3_sola/setup/starter.py`). On a real site it is a real
credential — change it, or remove the dataset, once the site is in use:

    bench --site <site> execute a3_sola.setup.starter.teardown

The user holds every solar role, is confined to **Starter Solar EPC** by a User Permission,
and sees only the four A3 Sola workspaces.

---

## Walking the job

Open the Lead and follow the **Connections** panel at the foot of each form. Every panel
also carries a **+** on each row, which opens the next document with the link back to the
current one already filled in — the same route a real job takes.

    Lead  "Starter Enquiry"
     └─ Solar Consumer                          the enquiry, qualified
         ├─ Site Survey                          what the surveyor measured
         │   └─ Solar Design Estimate            the system that fits the roof
         │       ├─ Subsidy Eligibility Check    eleven rules, all passing
         │       └─ Solar Proposal               the offer that goes to the customer
         │           └─ Quotation                the priced offer, figures fetched
         │               └─ Sales Order          submitting this opens the job
         └─ Solar Installation                   ten stages, ordered to tested
             ├─ Installation Work Order  (×5)    the crew's day, with real hours
             │   └─ Installation Snag            found at QC, rectified under a work order
             │       └─ Service Ticket           the same defect once the job was live
             ├─ Portal Application               the DISCOM's file, and its query
             │   └─ Statutory Fee Payment        fronted by the company
             │       └─ Statutory Fee Recovery   and recovered from the customer
             ├─ Loan Application                 sanctioned and part-disbursed
             ├─ Subsidy Claim                    company-funded gap, recovered
             ├─ Commissioning Report             the inspection, protection settings and all
             │   └─ Net Metering Agreement       executed with the DISCOM
             └─ Project                          opened automatically on commissioning
                 ├─ Solar Billing Plan           milestones, two of them triggered
                 └─ Solar OM Contract            five years of preventive maintenance
                     ├─ Solar OM Visit  (×2)     visits made, on time
                     ├─ Service Ticket           raised, worked, closed
                     │   └─ Solar Warranty Claim  module replaced under warranty
                     └─ Generation Reading (×4)  output tracked against the guarantee

The platform side is a second, shorter chain, from a prospective tenant's signup to their
first invited user:

    Subscription Signup
     ├─ Payment Order            ─ Payment Transaction (captured)
     │                            ─ Subscription Invoice
     ├─ Platform Subscription    ─ Payment Mandate (auto debit)
     └─ Provisioning Job         ─ Tenant ─ Tenant Invitation

**42 documents across 34 doctypes**, all reachable from those two starting points.

---

## The one document it does not create

There is no **Sales Invoice** against the billing plan, and that is deliberate.

Drafting one needs an active *Solar GST Valuation Rule* with its items and tax templates
attached. The app ships that rule inactive and empty on purpose: the valuation basis for a
composite solar supply is the client's chartered accountant's decision, and the app refuses
to guess it. Two milestones are triggered and the plan's Connections panel carries the
**+ Sales Invoice** button; raising it is the one step of this chain a person takes, once
the treatment is confirmed and recorded on A3 Sola Settings.

Faking it would have produced an invoice stating a tax treatment nobody agreed to — which
is the exact thing the rest of the app is built to prevent.

---

## Rebuilding it

    bench --site <site> execute a3_sola.setup.starter.teardown
    bench --site <site> execute a3_sola.setup.starter.install

`install` is idempotent — a second run creates nothing — and commits after every step, so a
step that fails leaves everything before it standing. It reports what it made, what it did
not, and how many of the app's sixty documents have at least one record.

`teardown` removes every record the dataset created, leaves the company and its chart of
accounts in place, and does not touch the other companies on the site.

## How the dates work

The chain is dated backwards from today — surveyed about four months ago, ordered four
months ago, commissioned ten days ago — because a job cannot be ordered this morning and
commissioned last week; the project ERPNext opens on commissioning validates that its end
date follows its start.

How far back it can go is read from the site, not assumed: a design estimate quotes the
DISCOM's fee schedule as it stood on the estimate date and refuses outright if none was in
force then, so the dates are clamped to that schedule's effective date.
