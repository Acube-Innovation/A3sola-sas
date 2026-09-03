# FAQ

## For tenants

**Why can I not see costs?**
Cost and margin sit behind a permission level. Your site engineer sees what to build, not
what it cost. Your administrator can grant it.

**My payment failed — have I lost access?**
No. A failed payment changes nothing about your access. You get an email, then a banner if
it stays unpaid, then a clear warning with an exact date before anything is restricted. **And
paying restores everything immediately.**

**I was suspended. What happened to my data?**
Nothing. No record, user, permission or file is deleted by a suspension. Paying restores
every user to exactly the state they were in — including anyone you had disabled yourself,
who stays disabled.

**Can I get my data out?**
Yes, and if you cancel you get an export automatically before your access ends.

**Why does the subsidy not appear on my customer's invoice?**
Because it is not yours to give. It is a government transfer to their bank after
commissioning. They owe you the full contract value.

**I need one more user right now.**
Team & Seats → Add a seat. You see the prorated cost first, and if your account is in good
standing the seat is available immediately.

**I want to downgrade but I have too many users.**
You will be asked to choose who to remove. The app will not choose for you. If you have not
chosen by your renewal date you stay on your current plan for another month — your data is
never made unreachable.

**Someone from support looked at my account.**
You will have been emailed: what they were doing, when it started and when it ended. If you
were not expecting it, reply to that email.

## For operators

**A customer says they can see another customer's data.**
Sev-1. Escalate before you finish diagnosing. `ops/ON_CALL.md`.

**The circuit breaker fired.**
It worked — nobody was suspended. Find out why the engine wanted to suspend that many at
once. It is almost always a gateway outage.

**A scheduler stopped.**
`bench doctor`, restart the scheduler, then **run the missed jobs by hand**. Nothing catches
up on its own, and `run_daily_billing` will otherwise skip a day of renewals. It is
idempotent.

**Every webhook signature is failing.**
The secret has changed. After a restore, it is nearly always the encryption key —
`ops/BACKUP_AND_DR.md`.

**Can I just fix the data directly in the database?**
No. Suspension, entitlements and postings all read from records with audit trails; editing
underneath them produces a state nothing can explain later.

---

# Walkthrough outlines

For recording later. Steps and talking points, not scripts.

### 1. First day as a tenant admin (8 min)
Sign in → the four workspaces → the setup checklist and **why each item was left blank** →
letterhead → invite the team → seats.
*Talking point: the four blanks are deliberate. Guessing your ledger accounts would be worse
than leaving them empty.*

### 2. Lead to order (12 min)
Enquiry → outreach cadence → qualify to consumer → survey → design → **eligibility before
quoting** → proposal → quotation → order opening the installation.
*Talking point: every solar figure is fetched, never typed. If a number is wrong, fix the
design.*

### 3. Order to commissioning (15 min)
The stage chain and why it differs by scheme → evidence gates → serial capture and DCR →
portal application and a query → statutory fees → snags → commissioning opening the project.
*Talking point: the evidence gate is the product. Collecting it later means guessing.*

### 4. Money (10 min)
Milestone billing → the subsidy rule → statutory fees as pass-through → profitability → the
postings switch and its prerequisites.
*Talking point: postings are off until your CA confirms. Everything is still recorded.*

### 5. Five years of O&M (10 min)
The contract and visit plan → a visit → a ticket breaching SLA → a warranty claim using the
serial register → underperformance raising a ticket automatically.
*Talking point: the serial register you filled in at installation is what makes the warranty
claim possible.*

### 6. Running the platform (12 min)
Revenue at Risk → the approval queue → a suspension and a one-click restore → the console
and the mode switches → impersonation with its notification.
*Talking point: restore first, investigate second. And the customer is always told.*
