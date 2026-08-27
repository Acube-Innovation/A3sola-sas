# UAT — Phase 4 (Platform)

Each case traces to the prompt that specified it. Run against a site with demo data:
`bench --site <site> execute a3_sola.demo.generate_demo_data.run`

Most are automated; `bench --site <site> run-tests --app a3_sola` runs the whole suite
across all four modules. Cases marked **manual** need a human at the screen.

## Content model and pricing API (P4-A3S-001)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U4-01 | Price Starter monthly with no add-ons | 3,000 base plus 10,000 implementation = 13,000 | `test_pricing` |
| U4-02 | Price Starter annually | 30,000, implementation waived | `test_pricing` |
| U4-03 | Check the waived fee on the annual card | Shown struck through, not silently dropped | `test_pricing` |
| U4-04 | Price Starter monthly with 3 extra users | 900 added at the monthly per-user rate | `test_pricing` |
| U4-05 | Price Starter annually with 3 extra users | Uses the annual per-user rate, not twelve times the monthly | `test_pricing` |
| U4-06 | Price Enterprise | "Contact sales", no number, same dict shape | `test_pricing` |
| U4-07 | Ask for more users than the plan allows | Refused | `test_pricing` |
| U4-08 | Ask for an unknown plan or cycle | Refused, never defaulted | `test_pricing` |
| U4-09 | Call the pricing function twice | Identical result, and nothing written | `test_pricing` |
| U4-10 | Add up the line items | They reconcile to the subtotal, every plan and cycle | `test_pricing` |
| U4-11 | Check Starter's modules | CRM and Operations; **not** Projects | `test_pricing` |
| U4-12 | Save a plan code with a space | Refused | `test_pricing` |
| U4-13 | Save a self-serve plan with no price | Refused | `test_pricing` |
| U4-14 | Set an annual price that is not 10 × monthly | Warned, not blocked — marketing may run a promotion | **manual** |
| U4-15 | Add a Platform tab field that already exists elsewhere | Caught by the duplicate-fieldname guard | `test_settings` |

## Marketing site (P4-A3S-002)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U4-16 | Open the homepage logged out | 200, all eleven sections present | `test_pages` |
| U4-17 | Check every published plan | Name and price on the page | `test_pages` |
| U4-18 | Check every published feature | On the homepage grid | `test_pages` |
| U4-19 | Unpublish a feature | Gone from the homepage immediately | `test_pages` |
| U4-20 | Open its detail route | 404 | `test_pages` |
| U4-21 | Check an integration with no logo | Renders a coloured initial chip | `test_pages` |
| U4-22 | Change a plan price in the desk | The site shows it with no deploy | `test_pages` |
| U4-23 | Check every pricing CTA | Carries both `package` and `cycle` | `test_pages` |
| U4-24 | Check the Enterprise CTA | Goes to contact, never to self-serve signup | `test_pages` |
| U4-25 | Toggle Monthly/Annual | Cards, sub-lines, table and every CTA href update with no reload | **manual** |
| U4-26 | Open the pricing page | Comparison table with the correct additional-user rates | `test_pages` |
| U4-27 | Check the pricing page schema | SoftwareApplication with offers, and FAQPage | `test_pages` |
| U4-28 | Open a feature detail page | Breadcrumb schema, hero, sections, sibling strip | `test_pages` |
| U4-29 | Open the three legal pages | All 200, all inside the site's own chrome | `test_pages` |
| U4-30 | Check unreviewed legal text | Shows a draft banner saying no lawyer has read it | `test_pages` |
| U4-31 | Record a lawyer's review on a legal page | Banner replaced by the reviewer's name | `test_pages` |
| U4-32 | Claim a review without naming the reviewer | Refused | `test_pages` |
| U4-33 | Switch maintenance mode on | Homepage and pricing intercepted | `test_pages` |
| U4-34 | Open /legal/privacy during maintenance | Still up — a banner is not a substitute for a privacy policy | `test_pages` |
| U4-35 | View the homepage at 375, 768, 1024 and 1440 px | Readable at each; the comparison table stacks below 768 | **manual** |
| U4-36 | Run Lighthouse on the homepage | Accessibility score — record the actual number | **manual** |
| U4-37 | Check the browser console | No errors, no external CDN requests except the font | `test_pages` (scripts) |

## Signup funnel (P4-A3S-003)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U4-38 | Deep-link /get-started?package=growth&cycle=annual | Growth and annual pre-selected | **manual** |
| U4-39 | Submit a valid signup | Record created, status Awaiting Email Verification | `test_signup` |
| U4-40 | Check the price snapshot | Base, implementation and total stored | `test_signup` |
| U4-41 | Change the plan price afterwards | The snapshot does not move | `test_signup` |
| U4-42 | Sign up annually | Implementation fee snapshotted as waived | `test_signup` |
| U4-43 | Sign up with 3 extra users | Priced and counted onto total users | `test_signup` |
| U4-44 | Check the response body | Reference and next step only — never the record | `test_signup` |
| U4-45 | Submit the same email twice | Resends; one record; identical response body | `test_signup` |
| U4-46 | Resend on an unknown reference | Same response as a known one | `test_signup` |
| U4-47 | Fill the honeypot | Looks like success; nothing created | `test_signup` |
| U4-48 | Submit six times from one IP | The sixth is throttled | `test_signup` |
| U4-49 | Read the throttle message | Never states the limit | `test_signup` |
| U4-50 | Reuse one email from fresh IPs | Capped per day | `test_signup` |
| U4-51 | Submit a malformed email | Refused | `test_signup` |
| U4-52 | Submit a blocked or disposable domain | Refused, including subdomains | `test_signup` |
| U4-53 | Submit a non-Indian mobile for India | Refused | `test_signup` |
| U4-54 | Submit a bad GSTIN | Refused; a good one is uppercased | `test_signup` |
| U4-55 | Choose Enterprise in the self-serve flow | Refused and routed to a demo | `test_signup` |
| U4-56 | Switch `enable_public_signup` off | The form and the endpoint both refuse | `test_signup` |
| U4-57 | Open a valid verification link | Verified; status moves; event logged | `test_signup` |
| U4-58 | Open it again | Refused — links are single use | `test_signup` |
| U4-59 | Open an expired link | Refused | `test_signup` |
| U4-60 | Open a wrong link | Refused | `test_signup` |
| U4-61 | Compare all four failure messages | Identical — they cannot be told apart | `test_signup` |
| U4-62 | Exceed the attempt cap | Refused thereafter | `test_signup` |
| U4-63 | Change plan after verifying | Re-snapshotted and logged | `test_signup` |
| U4-64 | Change plan with only the reference | Refused — the key is required | `test_signup` |
| U4-65 | Open the summary page | Order, price breakdown, user count | `test_signup` |
| U4-66 | Inspect the summary payload | No token, IP, user agent or internal field | `test_signup` |
| U4-67 | Open the summary with a wrong key | Same error as a record that does not exist | `test_signup` |
| U4-68 | Press "Proceed to payment" | Friendly pending state; sales notified | `test_signup` |
| U4-69 | Call `initiate_payment` | Raises NotImplementedError with the Phase 5 contract in its docstring | `test_signup` |
| U4-70 | Count Users, Companies, Roles before and after a full signup | Unchanged | `test_signup` |
| U4-71 | Grep the signup module for privileged calls | None present | `test_signup` |
| U4-72 | Submit a demo request | Created; thank-you page; sales notified | **manual** |
| U4-73 | Fill the demo honeypot | Nothing created | `test_signup` |
| U4-74 | Leave a signup unverified past the window | Marked Abandoned by the daily job, token cleared | **manual** |
| U4-75 | Run the purge job | IP, user agent and spent tokens cleared past retention | **manual** |

## Permissions and structure (P4-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U4-76 | Enumerate every doctype in the app | Only the eleven content doctypes are guest-readable | `test_guest_permissions` |
| U4-77 | Check guest write permissions anywhere | None, on any doctype | `test_guest_permissions` |
| U4-78 | List a Solar Installation as a guest | PermissionError | `test_guest_permissions` |
| U4-79 | List a Subscription Signup as a guest | PermissionError | `test_signup` |
| U4-80 | Read A3 Sola Settings as a guest | Refused — it holds the captcha secret | `test_guest_permissions` |
| U4-81 | Open an unpublished legal page as a guest | 404 | `test_guest_permissions` |
| U4-82 | Check IP, user agent, token and breakdown | All at permlevel 1 | `test_guest_permissions` |
| U4-83 | Check who holds level 1 | Platform Admin and System Manager only | `test_guest_permissions` |
| U4-84 | Check Platform Sales | Never holds level 1 | `test_guest_permissions` |
| U4-85 | Check the token's field flags | Hidden, no_copy, not in any list view, filter or search field | `test_guest_permissions` |
| U4-86 | Export a Subscription Signup list as Platform Sales | The token is absent | **manual** |
| U4-87 | Check modules.txt | Exactly four modules | `test_tenancy` |
| U4-88 | Check the singletons | Still exactly one | `test_settings` |
| U4-89 | Check every Platform doctype for a company field | None — these are platform-level, not tenant-level, by design | **manual** |

## Routes, SEO and operations (P4-A3S-004)

| ID | Steps | Expected | Automated |
|---|---|---|---|
| U4-90 | Open every public route as a guest | All 200, each rendering its own content | `test_routes` |
| U4-91 | Check every page controller filename | All importable by Frappe | `test_routes` |
| U4-92 | Check every template has a controller | None rendering a silent fallback | `test_routes` |
| U4-93 | Check the signup routes | All carry noindex | `test_routes` |
| U4-94 | Check the marketing routes | None carry noindex | `test_routes` |
| U4-95 | Fetch /robots.txt | Disallows every signup route; names the sitemap | **manual** |
| U4-96 | Fetch /sitemap.xml | Every published feature, solution and marketing page; no signup routes | **manual** |
| U4-97 | Unpublish a feature and refetch the sitemap | Gone | **manual** |
| U4-98 | Open the homepage with analytics off | No GA or GTM script loaded | **manual** |
| U4-99 | Switch analytics on and toggle pricing | A `pricing_toggle` event reaches dataLayer | **manual** |
| U4-100 | Run every Platform report | All return columns and reconcile to the demo data | **manual** |
| U4-101 | Open the Signup Funnel report | Reconciles to the demo data: 20 submitted, 14 verified, 5 paid | **manual** |
| U4-102 | Open the Platform workspace | Four cards under the A3 Sola parent | **manual** |
