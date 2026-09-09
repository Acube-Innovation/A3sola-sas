# Test drive — 30 minutes, end to end

The short version of `UAT_MASTER.md`. Follow it top to bottom and you will have touched
every one of the eight phases.

Each step says **what good looks like**. If you see that, it works.

---

## 0. Start it up (2 min)

```bash
cd ~/Projects/A3-Sola/a3_sola
bench start                 # leave this running in its own terminal
```

Open **http://127.0.0.1:8000/app** and sign in:

```
starter.engineer@example.com  /  a3sola-starter
```

**Good:** you land on a workspace list showing only **A3 Sola · Solar CRM · Solar
Operations · Solar Projects**. No Accounts, no HR, no Buying. That is the confinement
working — this user is scoped to one company and four workspaces.

---

## 1. The public site (2 min)

| Go to | Good |
|---|---|
| http://127.0.0.1:8000/ | **ERPNext desk**, not the marketing site |
| http://127.0.0.1:8000/a3sola | the A3 Sola marketing homepage |
| http://127.0.0.1:8000/a3sola/pricing | three plans; toggle monthly/annual and the prices recompute |

**Good:** `/` is the app and `/a3sola` is the product site. They do not collide.

---

## 2. Follow one job from enquiry to service (10 min)

This is the whole business in one chain. Start at the Lead and use the **Connections**
panel at the foot of each form — never the search bar.

1. **Solar CRM → Lead** → open **Starter Enquiry**
2. Scroll to **Connections** → **Solar Consumer** → open it
3. From the consumer's Connections, walk forward:

```
Site Survey → Solar Design Estimate → Subsidy Eligibility Check
            → Solar Proposal → Quotation → Sales Order
            → Solar Installation  (thirty tasks; the Task button opens each one's document)
                 ├ Installation Task · Installation Work Order (×5)
                 ├ Portal Application → Statutory Fee Payment
                 ├ Loan Application · Subsidy Claim
                 ├ Solar Agreement · Material Dispatch Notice · Document Pack
                 ├ Commissioning Report · Customer Review
                 └ Project → Billing Plan · O&M Contract
                              → O&M Visit → Service Ticket → Warranty Claim
```

**Good:** you reach the last document without typing a search once. Every document the
starter job owns is reachable from that one Lead.

**Try the + button.** On any Connections row, click **+**. The new document opens with the
link back already filled in, and the company inherited.

### Four things worth opening while you are in there

| Open | Look for |
|---|---|
| **Subsidy Eligibility Check** | eleven rules, each pass/fail with a reason in words |
| **Solar Installation → Tasks** | thirty rows with owner, assignee, due date and the document that carries each; skipped tasks carry a reason |
| **Solar Installation → Document Register** | every generated and uploaded file, with the task document it came from |
| **Solar Installation → Serials** | module and inverter serials with DCR numbers |
| **Commissioning Report** | protection settings, each with its proof |
| **Solar Agreement** | the KSEB agreement text, generated - nobody typed it |

### The stamp paper and the agreement (2 min)

Three acts, in the app and in life. Open the installation's **Solar Agreement**.

1. **STMP task.** On **Solar Installation**, click **Task → STMP · Stamp Paper Purchase**.
   The Solar Agreement opens (or is created, linked back). **Stamp Paper Data Sheet** prints
   what the treasury needs before the paper is bought.
2. **Record Stamp Paper.** On the agreement, click the button, enter the serial and value.
   Back on the job the STMP row is Completed, names the agreement as its document, carries
   the serial as its reference and the paper's value as its cost.
3. **Generate Text.** The button only appears once the paper is recorded. The body arrives
   filled in — consumer, address, SPIN, capacity, section — from the Lead, the Consumer,
   the Survey, the Estimate, the Installation and the Commissioning Report.
4. **Print → Solar Agreement.** The KSEB instrument, with Schedules I, II and III.

**Try to break it.** Edit a sentence in the text area, save, then hit **Regenerate**. It
refuses: the edit may be negotiated wording and it exists nowhere else. Confirm to discard.

---

## 3. Try to break the rules (3 min)

The refusals are the product. Each of these **should fail**.

| Try | Expected refusal |
|---|---|
| On a **Quotation**, add an item row called "Subsidy discount" and save | *"The subsidy is a government transfer to the customer after commissioning — it can never be an item, a tax or a discount"* |
| Create a **Solar Consumer** with an existing consumer number | duplicate refused |
| **Solar Installation** → **Task → IWOI**, submit the work order with fewer than four geo-tagged photographs | refused, saying how many it has |
| **Solar Installation** → complete a task by hand while its document is still live (as an executive) | refused; the document completes it |
| **Document Pack** → create a Bank Completion Pack on a self-funded job | *"A bank completion pack is for a financed job"* |
| **Subsidy Claim** → submit with an open Major snag | refused, naming the snag |
| **Solar Agreement** → Generate Text before recording the stamp paper | *"The agreement is written on it, so there is nothing to generate until it is bought"* |
| **Solar Agreement** → submit a second agreement for the same installation | refused, naming the executed one |
| Open **A3 Sola Settings → Projects** → tick *enable accounting postings* | blocked until the CA confirmation is recorded |

**Good:** every one is refused with a sentence explaining why, not a stack trace.

---

## 4. The reports that matter (3 min)

**Solar CRM / Operations / Projects workspaces → the report cards.**

Open at least these four:

- **Installation Stage Ageing** — what is stuck and for how long
- **Project Profitability** — quoted against actual
- **Subsidy Receivable Ageing** — money the company fronted
- **Generation Performance** — plants sliding below their guarantee

**Good:** each opens with rows, and every figure is for **one company only**.

---

## 5. The platform side (5 min)

Switch to Administrator for this part:

```bash
bench --site local set-admin-password <your-password>
```

Sign in as **Administrator** → **Platform** workspace.

| Card | What to open |
|---|---|
| Lifecycle | **Subscription Policy** — the five stages, all editable data |
| Lifecycle | **Subscription Event** — try to edit one. It refuses; the log is append-only |
| Operations console | **Platform Audit** — every trail in one searchable report |
| Lifecycle reports | **Revenue at Risk**, **Subscription Health**, **MRR Movement** |

**Good:** MRR Movement reconciles — every row's *Reconciles* column says `yes`.

### See the lifecycle engine think, without it doing anything

```bash
bench --site local execute a3_sola.api.lifecycle.admin.run_simulation
```

**Good:** it reports what it *would* do to every subscription and changes nothing. That is
the shipped default — dry run on, automatic suspension off.

---

## 6. Prove the isolation (2 min)

The single most important thing in a product where two solar companies share one instance.

```bash
bench --site local run-tests --module a3_sola.tests.security.test_isolation_attacks
```

**Good:**

```
Attempts   : 5,871      Blocked : 5,052
Vectors    : 34         SUCCESSFUL : 0
Doctypes   : 254
negative control: 66 leak(s) detected with the boundary removed, as expected
```

The last line is the important one — it proves the test would notice a real breach.

---

## 7. Health and monitoring (2 min)

```bash
bench --site local execute a3_sola.api.health.detail
bench --site local execute a3_sola.api.monitoring.heartbeat.status
```

**Good:** on this machine it reports **degraded/down with 30 jobs stopped** — because the
scheduler is switched off. That is the watchdog working correctly.

To make it green:

```bash
bench --site local set-config -g enable_scheduler 1
bench --site local execute a3_sola.api.lifecycle.engine.run_lifecycle
```

---

## 8. The whole suite (optional, ~45 min)

```bash
bench --site local run-tests --app a3_sola
```

**Good:** 1159 tests, 64 modules, 0 failures (one skipped).

---

## If something looks wrong

| Symptom | Cause, nine times out of ten |
|---|---|
| A list view is empty | You are signed in as a user scoped to a different company |
| A report shows nothing | Same |
| Nothing posts to the ledger | Correct. Postings ship off until the CA confirms the GST treatment |
| The lifecycle changed nothing | Correct. Dry run is on |
| A background job never runs | The scheduler is disabled on this machine |
| `bench execute` says `NameError: name 'a3_sola' is not defined` | The real error is being hidden. Quote the path: `bench --site local execute "a3_sola.module.function"` |
