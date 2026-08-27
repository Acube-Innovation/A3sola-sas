# Content guide — editing the public site without a developer

Nothing on the marketing site is written into a template. Every section renders from
records in the desk, so you can change the site and see it immediately. This is the map.

## Which doctype drives which part of the page

| Homepage section | Doctype | Notes |
|---|---|---|
| Hero eyebrow, headline chrome | **A3 Sola Settings → Platform** | `partner_badge_text`, `product_name`, `product_tagline` |
| Hero product mockup | **A3 Sola Settings → Platform** | The three KPI tiles and the delta row are settings fields |
| Stat strip | **Platform Stat** | Four records look best; more will wrap |
| Features grid | **Platform Feature** | Only those with *Show on Homepage* ticked |
| Solutions row | **Platform Solution** | Only those with *Show on Homepage* ticked |
| Subsidy & compliance tiles | *In code* — see below | The one place you need a developer |
| Powered by ERPNext tiles | *In code* — see below | |
| Integrations | **Platform Integration** | Grouped by category automatically |
| Pricing cards and table | **Subscription Plan** | Change a price and the site changes |
| Apps section | *In code* — see below | |
| Contact details | **A3 Sola Settings → Platform** | `sales_email`, `sales_phone`, `office_address`, `demo_scheduler_url` |
| Footer | **A3 Sola Settings → Platform** | `footer_tagline`, `company_legal_name`, `parent_company_url` |

| Other page | Doctype |
|---|---|
| `/features` and each feature page | **Platform Feature** |
| `/solutions` and each solution page | **Platform Solution** |
| `/pricing` FAQ | **Platform FAQ** |
| `/legal/privacy`, `/legal/terms`, `/legal/refund-policy` | **Platform Legal Page** |

### The three sections that are still in code

The subsidy tiles, the ERPNext backbone tiles and the apps cards are constants in
`a3_sola/api/platform.py` (`DOMAIN_TILES`, `BACKBONE_TILES`, `APP_TILES`). They are four
to six fixed items each that describe the product's architecture rather than its
marketing, and giving each one a doctype would have meant three doctypes for fourteen
rows. **Changing them needs a developer.** If you find yourself wanting to edit them
often, that is the signal to promote them to a content doctype.

## Writing a good feature record

- **Feature name** — what it does, not what it is called internally.
- **Short description** — one sentence, and make it a claim rather than a category.
  "Every KSEB and bank document generated from one record" beats "Document management".
- **Card bullets** — at most three; the card shows three and the form refuses more.
  Specifics beat adjectives. Name the actual forms, the actual makes, the actual numbers.
- **Icon** — an emoji is fine and renders everywhere. Leave it blank and a neutral mark
  is used.
- **Group** — decides which block it appears under on `/features`.
- **Display order** — lower comes first. Leave gaps of ten so you can insert later.

## Publishing and unpublishing safely

Unticking **Published** removes a record from the homepage, from the index page, from the
sitemap, and makes its detail page return 404 — immediately, with no deploy. That is the
safe way to take something down.

**Do not change a route** on a feature or solution that is already live. The route is the
URL; changing it breaks every link anyone has to it, including from search results. If you
must, ask a developer to add a redirect.

**Do not change a plan code.** It appears in every pricing link on the site and in every
signup already in flight. The form will warn you.

## Images

| Where | Recommended size | Notes |
|---|---|---|
| Brand logo | 240 × 64 px, transparent PNG or SVG | Shown at 32 px tall; supply 2× for sharpness |
| Favicon | 64 × 64 px | |
| Open Graph image | 1200 × 630 px | What appears when the site is shared |
| Integration logo | 128 × 128 px, square | Falls back to a coloured initial if absent — which looks deliberate, so a missing logo is not urgent |
| Detail section image | 1200 px wide | Keep under 300 KB |

## SEO fields

Every feature, solution and legal page has **Meta Title** and **Meta Description**. Both
fall back to the record's own name and short description, so they are optional — but a
written one is better than a fallback.

- **Meta title** — under about 60 characters, or search engines truncate it.
- **Meta description** — 140 to 160 characters. Write it as the sentence you would want
  to read in a search result, not as a keyword list.

The site-wide defaults live in **A3 Sola Settings → Platform → SEO & Analytics**.

## Analytics events

If analytics is switched on, the site pushes these to `dataLayer`. Build funnels from
them without asking a developer:

| Event | Fired when | Payload |
|---|---|---|
| `pricing_toggle` | Monthly/annual is switched | `cycle` |
| `plan_selected` | A plan CTA or signup card is chosen | `plan`, `source` |
| `signup_started` | Any "Get started" or "Sign up" is clicked | `source` |
| `signup_step_completed` | A signup step is passed | `step` |
| `signup_submitted` | The signup form is submitted | — |
| `email_verified` | A verification link is opened successfully | — |
| `payment_initiated` | "Proceed to payment" is clicked | — |
| `demo_requested` | The demo form is submitted | — |

Analytics loads **only** when `enable_analytics` is on and a GA or GTM id is configured.

## Maintenance mode

**A3 Sola Settings → Platform → Site Behaviour → Maintenance Mode** replaces every public
page with a branded panel showing your `maintenance_message`. The legal pages stay up
deliberately — somebody may be relying on the privacy policy, and a maintenance banner is
not a substitute for one.

`enable_public_signup` and `enable_demo_requests` switch off those forms individually,
with a message pointing at your sales email, without taking the whole site down.


## The design tokens, and where they came from

Every value below was **extracted from the live reference product** at
`https://3-108-28-240.sslip.io/` on 2026-08-25 by fetching its compiled stylesheet
(`/_next/static/css/bb65a052aac628ca.css`) and reading the actual declarations — not by
eye, and not from the fallback set in the brief.

They are defined once, at the top of `a3_sola/public/css/platform.css`. Change one there
and it changes everywhere on the site.

| Token | Value | Where it came from |
|---|---|---|
| `--font-sans` | `"Plus Jakarta Sans", system-ui, sans-serif` | the reference's `:root --font-sans` |
| `--color-text` | `#2a3342` | the reference's `ink` |
| `--color-bg` | `#f7f9fc` | the reference's `canvas` |
| `--color-surface` | `#ffffff` | card backgrounds |
| `--color-border` | `rgba(42, 51, 66, 0.12)` | the reference's hairline border |
| `--color-accent` / gradient | `#f7941e` → `#fbb040` | the reference's `.btn-primary` gradient |
| `--color-sky` gradient | `#1b8dc0` → `#29abe2` → `#5bc2ec` | the reference's `.eyebrow` gradient |
| `--shadow-soft` | `0 10px 40px -12px rgba(42,51,66,.12)` | the reference's card shadow |
| `--shadow-raised` | `0 20px 50px -12px rgba(42,51,66,.22)` | the reference's hover shadow |
| `--container-max` | `80rem` | the reference's `.container-px` |
| `--section-pad` | `5rem`, `7rem` at ≥1024px | the reference's `.section` |
| Button shape | pill, `.75rem 1.5rem`, `.875rem/600`, 200 ms | the reference's `.btn-primary` |
| Breakpoints | 640, 768, 1024 px | the reference's media queries |

**One deliberate difference.** The brief asked for a solar/energy accent — amber or warm
orange — rather than the hospitality accent. The reference's primary accent already *is*
that orange gradient, so it carries over unchanged and reads correctly for solar; the sky
blue stays as the secondary, used on eyebrow pills. Nothing was invented.

Dark mode was not built: the brief explicitly excluded it from this phase.
