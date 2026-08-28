# UAT — Phase 6 (Tenant provisioning)

Each case traces to the prompt that specified it. Run against a site with demo data:
`bench --site <site> execute a3_sola.demo.generate_demo_data.run`

Cases marked **manual** need a human at the screen. Everything else names the test that
proves it.

## The orchestrator (P6-A3S-001)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U6-01 | Call provisioning five times for one subscription | One job, one tenant | `test_provisioning_core` |
| U6-02 | Derive the idempotency key twice | Identical; a different subscription differs | `test_provisioning_core` |
| U6-03 | Call it twice and count companies and users | Neither changes | `test_provisioning_core` |
| U6-04 | Call it while the lock is held | Returns the in-flight job, creates nothing | `test_provisioning_core` |
| U6-05 | Provision from a browser-callback-only payment | Refused, naming the webhook | `test_provisioning_core` |
| U6-06 | Pay a renewal on a provisioned subscription | No second tenant | `test_provisioning_core` |
| U6-07 | Provision with the signup email unverified | Refused | `test_provisioning_core` |
| U6-08 | Fail step 3 deliberately | Rolled Back, no tenant, no identifier | `test_provisioning_core` |
| U6-09 | Fail step 4, then resume | Resumes at step 4, not step 1 | `test_provisioning_core` |
| U6-10 | Check the step order | Ascending, and no reversible step after an irreversible one | `test_provisioning_core` |
| U6-11 | Check which step is the point of no return | Exactly one: `09_CREATE_ADMIN_USER` | `test_provisioning_core` |
| U6-12 | Check every reversible step | All define a rollback | `test_provisioning_core` |
| U6-13 | Derive a code from a name full of SQL, HTML and path characters | Safe, lowercase, hyphenated | `test_provisioning_core` |
| U6-14 | Derive a code from a name in Malayalam | Valid code, deterministic | `test_provisioning_core` |
| U6-15 | Use a reserved word as a tenant code | Refused | `test_provisioning_core` |
| U6-16 | Derive a code from "Admin" | Never lands on the reserved word | `test_provisioning_core` |
| U6-17 | Provision two tenants with the same organisation name | Deterministic disambiguation | `test_provisioning_core` |
| U6-18 | Change the plan's included users after provisioning | The tenant's quota does not move | `test_provisioning_core` |
| U6-19 | Leave a job Running past the timeout | The watchdog marks it Failed and alerts | `test_provisioning_core` |
| U6-20 | Set Manual Approval and pay | Job Queued, no tenant, waits | `test_provisioning_core` |

## Workspace and masters (P6-A3S-002)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U6-21 | Check the created company | Right currency, country and tenant back-link | `test_provisioning_company` |
| U6-22 | Check the abbreviation | Derived, uppercase, unique site-wide | `test_provisioning_company` |
| U6-23 | Derive a company name from a hostile string | No quote, angle bracket, slash or backtick survives | `test_provisioning_company` |
| U6-24 | Provision "M/s Sūrya Energy & Co." | Clean company and a valid code | `test_provisioning_company` |
| U6-25 | Provision into an existing company name | Disambiguated | `test_provisioning_company` |
| U6-26 | Check cost centres | Sales, Projects, Service, Administration | `test_provisioning_company` |
| U6-27 | Check warehouses | Main Store, Site Store, Service Van Stock, Scrap Store | `test_provisioning_company` |
| U6-28 | Check the company's default cost centre | Set — without it every P&L posting fails | `test_provisioning_company` |
| U6-29 | Check the Operations settings | Point at the new warehouses | `test_provisioning_company` |
| U6-30 | Check item groups and UOMs | Solar groups and kW/kWp/kWh present | `test_provisioning_company` |
| U6-31 | Check the seeded masters | DISCOM, roof types, scheme, tariff, packages, stage chain, checklists, makes | `test_provisioning_company` |
| U6-32 | Check every seeded master's company | All the new one | `test_provisioning_company` |
| U6-33 | Open the account mapping | Every account **empty** | `test_provisioning_company` |
| U6-34 | Check the GST valuation rule | Seeded inactive | `test_provisioning_company` |
| U6-35 | Break a mandatory blueprint item | Step 07 fails, naming what is missing | `test_provisioning_company` |
| U6-36 | Provision a second tenant | Gets its own roof types, not none | `test_provisioning_company` |
| U6-37 | Check the entitlement snapshot on the tenant | Quota and modules from the plan | `test_provisioning_company` |
| U6-38 | Check seats after provisioning | One used (the admin), the rest free | `test_provisioning_company` |
| U6-39 | Roll back after the company has a transaction | Refused, naming the reason | `test_provisioning_company` |
| U6-40 | Grep for a forced company delete | None anywhere | `test_provisioning_company` |
| U6-41 | Time a full provision | Under 60 seconds — measured at ~12s | **manual** |

## Users, quota and invitations (P6-A3S-003)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U6-42 | Check the admin's password | None was ever set | `test_provisioning_users` |
| U6-43 | Check the reset link | Single-use, expires, delivered to the verified address | `test_provisioning_users` |
| U6-44 | Provision onto an email that already has an account | Step fails, needs a human, nothing reused | `test_provisioning_users` |
| U6-45 | Check the admin's tenant stamp | Set | `test_provisioning_users` |
| U6-46 | Check the company User Permission | Exists, read back after creation | `test_provisioning_users` |
| U6-47 | Check the tenant admin's roles | No internal Platform role | `test_provisioning_users` |
| U6-48 | Check a Starter admin's roles | No Solar Projects role | `test_provisioning_users` |
| U6-49 | Check a Growth admin's roles | Solar Projects roles present | `test_provisioning_users` |
| U6-50 | Check the admin's default company | Their own | `test_provisioning_users` |
| U6-51 | Run apply_module_entitlements twice | The second run changes nothing | `test_provisioning_users` |
| U6-52 | Grant a forbidden role by hand, then reconcile | Removed | `test_provisioning_users` |
| U6-53 | Add the sixth user to a five-seat tenant | Refused, message names the quota | `test_provisioning_users` |
| U6-54 | Read the refusal | Says how to get more seats | `test_provisioning_users` |
| U6-55 | Disable a user at quota | Never blocked | `test_provisioning_users` |
| U6-56 | Re-enable a user past quota | Blocked | `test_provisioning_users` |
| U6-57 | Save the Administrator at quota | Never blocked | `test_provisioning_users` |
| U6-58 | Create an internal user with no tenant stamp | Never blocked | `test_provisioning_users` |
| U6-59 | Save the tenant's own admin with quota zero | Never blocked | `test_provisioning_users` |
| U6-60 | Check the usage counters | Track reality | `test_provisioning_users` |
| U6-61 | Run the nightly job on an over-quota tenant | Reports it | `test_provisioning_users` |
| U6-62 | Create an invitation | Token and expiry set | `test_provisioning_users` |
| U6-63 | Invite the same address twice | Refused | `test_provisioning_users` |
| U6-64 | Accept an invitation | User created, confined to the company | `test_provisioning_users` |
| U6-65 | Accept an expired invitation | Refused, marked Expired | `test_provisioning_users` |
| U6-66 | Reuse an accepted token | Refused | `test_provisioning_users` |
| U6-67 | Accept a revoked invitation | Refused; the token died at revocation | `test_provisioning_users` |
| U6-68 | Fill the seats, then accept an older invitation | Refused, marked Failed, admin told | `test_provisioning_users` |
| U6-69 | Invite with no seat free | Refused | `test_provisioning_users` |
| U6-70 | Check pending invitations against seats | They count | `test_provisioning_users` |
| U6-71 | Compare the error for a taken address and a nonsense token | Identical | `test_provisioning_users` |
| U6-72 | Run the nightly expiry job | Stale invitations become Expired | `test_provisioning_users` |
| U6-73 | Check the onboarding checklist | Built, critical items present | `test_provisioning_users` |
| U6-74 | Read each checklist item | Every one says why it matters | `test_provisioning_users` |
| U6-75 | Log in as the tenant admin and open /seats | Their own seats, invite form, resend and revoke | **manual** |
| U6-76 | Open /account-mapping as the tenant admin | Their own accounts only | **manual** |
| U6-77 | Try to map an account from another company | Refused by name | **manual** |

## Isolation, activation and operations (P6-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U6-78 | Check the isolation checker's query API | `get_list`, never `get_all` | `test_provisioning_isolation` |
| U6-79 | Check the session is restored | `finally` block, always | `test_provisioning_isolation` |
| U6-80 | Check how doctypes are enumerated | From the registry, not a list | `test_provisioning_isolation` |
| U6-81 | Run isolation on a fresh tenant | Every check passes | `test_provisioning_isolation` |
| U6-82 | Count what is covered | Every company-scoped doctype in all four modules | `test_provisioning_isolation` |
| U6-83 | Check the platform doctypes covered | Payment Order, Signup, Tenant, Provisioning Job | `test_provisioning_isolation` |
| U6-84 | Delete the company User Permission, re-run | **Fails** — this is the bug the step exists for | `test_provisioning_isolation` |
| U6-85 | Activate a tenant that failed isolation | Refused | `test_provisioning_isolation` |
| U6-86 | Re-run the isolation test from the desk | Works at any time | `test_provisioning_isolation` |
| U6-87 | Run the monthly sweep | Covers every active tenant | `test_provisioning_isolation` |
| U6-88 | Run a report for another tenant's company | PermissionError | `test_provisioning_isolation` |
| U6-89 | Check every report taking a company filter | All go through the guard | `test_provisioning_isolation` |
| U6-90 | Check the subscription after activation | Active, period set, next billing date set | `test_provisioning_core` |
| U6-91 | Check the signup after activation | Active, company/site/admin written back | **manual** |
| U6-92 | Resume a job from the desk | Continues from the first incomplete step | **manual** |
| U6-93 | Retry one step | Re-runs that step only | **manual** |
| U6-94 | Skip a mandatory step | Refused | **manual** |
| U6-95 | Skip a non-mandatory step without a reason | Refused | **manual** |
| U6-96 | Roll back past the point of no return | Unavailable, and it says why | **manual** |
| U6-97 | Mark a job resolved with no notes | Refused | **manual** |
| U6-98 | Open the Provisioning Failures report | Open interventions, oldest first | **manual** |
| U6-99 | Refund a first payment | Tenant Suspended, users disabled, nothing deleted | **manual** |
| U6-100 | Terminate with the wrong confirmation text | Refused, nothing changed | **manual** |
| U6-101 | Terminate correctly | Data exported, users disabled, **company kept** | **manual** |
| U6-102 | Run all seven Phase 6 reports | All return columns | **manual** |
| U6-103 | Check `tenancy_strategy` with tenants present | Cannot be changed | **manual** |
| U6-104 | Uncheck the isolation gate without a justification | Refused | **manual** |
| U6-105 | Check guest permissions on every Phase 6 doctype | None at all | `test_guest_permissions` |
