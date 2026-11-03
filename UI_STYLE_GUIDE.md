# Acube SaaS UI Style Guide

The look of the **A3 Sola portal** (`/a3solaportal`), written down so every new Acube SaaS app is built the same way. Every value here is taken from the A3 Sola code: `a3_sola/public/css/platform.css`, `a3_sola/templates/portal_shell.html`, `a3_sola/templates/includes/*` and `a3_sola/public/js/portal_*.js`. When in doubt, open those files. They are the source of truth, and section 11 lists them.

---

## 1. How to use this guide

1. Copy the **tokens** (section 2) into the new app's stylesheet, unchanged.
2. Load **Plus Jakarta Sans** (section 3).
3. Build every signed-in page inside the **app shell** (section 4): fixed top bar, fixed left sidebar, scrolling main column.
4. Build pages from the **components** (section 5) using the same class names. Keep the `a3s-` prefix, or rename it once for the whole app (for example `acs-`), but keep the block, element and modifier structure.
5. Talk to the server and give feedback the same way (section 6), and write UI text in the same voice (section 7).

**Rules of the look**
- One accent: orange `#f7941e`, used as the gradient `#f7941e → #fbb040` on primary buttons, active states and icons. Sky blue `#29abe2` is the only secondary colour.
- Calm canvas: light grey page (`#f7f9fc`), white cards, hairline borders at 12% ink, soft shadows.
- Everything is rounded: cards 1.25rem, tiles 1rem, inputs 0.75rem, buttons and pills fully round.
- Small, bold, uppercase labels give structure: card titles, field labels, table headers, section and sidebar group titles.
- Portal cards do **not** lift on hover. Only marketing cards lift.
- Focus is always visible, as a 3px orange outline.
- Don't add new colours. Use the tone pairs in section 2.3.
- Don't use shadows heavier than `--shadow-raised`, square corners, or more than one primary button per card.

---

## 2. Design tokens

### 2.1 Paste this block

```css
:root {
	/* Colour */
	--color-text: #2a3342;
	--color-text-muted: #6b7383;
	--color-bg: #f7f9fc;
	--color-surface: #ffffff;
	--color-border: rgba(42, 51, 66, 0.12);
	--color-border-strong: rgba(42, 51, 66, 0.15);

	/* Accent: the brand orange */
	--color-accent: #f7941e;
	--color-accent-hover: #e07f0c;
	--color-accent-light: #fbb040;
	--color-accent-gradient: linear-gradient(135deg, #f7941e, #fbb040);
	--color-accent-soft: rgba(247, 148, 30, 0.08);
	--color-accent-tint: rgba(247, 148, 30, 0.3);

	/* Secondary: sky */
	--color-sky: #29abe2;
	--color-sky-ink: #106d94;           /* sky that stays readable as text */
	--color-sky-gradient: linear-gradient(135deg, #1b8dc0, #29abe2 50%, #5bc2ec);

	/* State */
	--color-success: #28c840;
	--color-warning: #febc2e;
	--color-danger: #ff5f57;

	/* Type */
	--font-sans: "Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;

	/* Layout */
	--container-max: 80rem;
	--container-pad: 1.25rem;            /* 2rem from 1024px */
	--section-pad: 5rem;                 /* 7rem from 1024px */

	/* Elevation */
	--shadow-soft: 0 10px 40px -12px rgba(42, 51, 66, 0.12);
	--shadow-raised: 0 20px 50px -12px rgba(42, 51, 66, 0.22);

	/* Shape */
	--radius-card: 1.25rem;
	--radius-tile: 1rem;
	--radius-pill: 9999px;

	/* Motion */
	--ease: cubic-bezier(0.4, 0, 0.2, 1);
	--duration: 200ms;

	/* App shell */
	--a3s-topbar-h: 4rem;
	--a3s-side-w: 17rem;                 /* 4.75rem when the menu is collapsed */
}
@media (min-width: 1024px) {
	:root { --container-pad: 2rem; --section-pad: 7rem; }
}
html.a3s-side-collapsed { --a3s-side-w: 4.75rem; }
```

### 2.2 Base and focus

```css
.a3s * { box-sizing: border-box; }
.a3s {
	margin: 0;
	font-family: var(--font-sans);
	color: var(--color-text);
	background: var(--color-bg);
	font-size: 1rem;
	line-height: 1.65;
	-webkit-font-smoothing: antialiased;
}
.a3s a { color: inherit; text-decoration: none; }
.a3s a:hover { color: var(--color-accent); }
/* Focus must always be visible. Removing it is not a style choice. */
.a3s :focus-visible { outline: 3px solid var(--color-accent); outline-offset: 2px; border-radius: 4px; }
```

### 2.3 Tone pairs (background + text)

These are the only status colours. Use the pair as it is; don't mix halves.

| Tone | Background | Text | Use for |
|---|---|---|---|
| Success | `rgba(40,200,64,0.14)` (0.1–0.16) | `#1a7a2b` | Done, paid, saved, converted |
| Danger | `rgba(255,95,87,0.14)` | `#c0392b` | Error, lost, blocked |
| Strong red | `rgba(217,45,32,0.1)` | `#b42318` (`#d92d20` for borders and the destructive button) | Overdue, mismatch, delete |
| Info / sky | `rgba(41,171,226,0.12)` | `#1b8dc0` (or `--color-sky-ink`) | Open, new, informational |
| Accent / pending | `var(--color-accent-soft)` | `var(--color-accent-hover)` | Pending, in hand, quotation |
| Warning | `rgba(247,144,9,0.12)` + `border-left: 3px solid #f79009` | `#93370d` | Check this before going on |
| Notice | `rgba(41,171,226,0.10)`, border `rgba(41,171,226,.25)` | `#1b6f92` | An information banner |
| Neutral | `rgba(42,51,66,0.08)` | `var(--color-text-muted)` | Default badge, draft |
| "Who" pill | `#e3edfb` (hover `#cfe0f6`) | `#1c4e8a` | A person's name chip |
| Purple | `rgba(122,90,248,0.12)` | `#5b3fd1` | Tickets |
| WhatsApp | `#25d366` (hover `#1da851`) | `#fff` | The WhatsApp share button only |

- **Overlays:** modal backdrop `rgba(42,51,66,0.45)`, mobile menu backdrop `rgba(42,51,66,0.4)`.
- **Layers (z-index):** skip link 200, mobile nav 150, backdrop 140, modal 100, task menu 90, top bar 50, help popover 30, dropdown lists 20, sticky step bar 5.
- **Motion:** `var(--duration) var(--ease)` by default; the sidebar width animates over 0.25s and progress bars over 0.3s. Always honour `prefers-reduced-motion`.
- **Not defined yet:** there's no dark mode, and no spacing or z-index tokens. Spacing is written as rem values in the steps 0.35 / 0.5 / 0.75 / 1 / 1.25 / 1.5 / 1.75 / 2 rem.

---

## 3. Typography

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

**Headings**
```css
.a3s h1, .a3s h2, .a3s h3, .a3s h4 { margin: 0 0 0.5rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.12; }
.a3s h1 { font-size: clamp(2.5rem, 5vw, 4rem); }   /* marketing */
.a3s h2 { font-size: clamp(1.9rem, 3.2vw, 2.6rem); }
.a3s h3 { font-size: 1.35rem; letter-spacing: -0.01em; }
.a3s-main__title { margin: 0 0 0.35rem; font-size: 1.75rem; }  /* a portal page's title */
.a3s-main__sub { margin: 0; color: var(--color-text-muted); }
```

**Uppercase labels**: these are the signature of the look.

| Where | Size / weight / spacing | Colour |
|---|---|---|
| Card title `.a3s-edit__card-title`, modal title | 0.8125rem / 800 / 0.1em | `--color-accent-hover` |
| Field label (edit forms, modals) | 0.6875rem / 800 / 0.06em | `--color-text` |
| Table header | 0.6875rem / 600 / 0.05em | muted |
| Sidebar group label | 0.6875rem / 700 / 0.06em | muted |
| Section title | 0.75rem / 700 / 0.06em | muted |
| Stat label | 0.6875rem / 700 / 0.05em | muted |
| Board column head | 0.75rem / 800 / 0.08em | text |

**Sizes in use:** body 1rem; table and input text 0.9375rem; buttons and sidebar titles 0.875rem; meta, hints and breadcrumbs 0.8125rem; sub-lines 0.75rem.

**Numbers**
- Big stat values are 1.6rem/700. Tile values are 1.35rem/800, and a headline figure is 2.5rem/800.
- Money and totals use `font-variant-numeric: tabular-nums`.
- `.a3s-num` is right-aligned and doesn't wrap, for item tables and totals.
- `.a3s-table__num` in list tables stays **left-aligned** and muted, on purpose.

---

## 4. Layout and app shell

### 4.1 Skeleton

```html
<body class="a3s a3s-app">
  <!-- SVG icon sprite (section 5.17) -->
  <header class="a3s-topbar">
    <div class="a3s-topbar__left">
      <div class="a3s-topbar__brand">                      <!-- exactly as wide as the sidebar -->
        <a class="a3s-logo" href="/app/dashboard"><span class="a3s-logo__mark">☼</span><span class="a3s-logo__text">Product <span class="a3s-logo__ai">. AI</span></span></a>
        <button type="button" class="a3s-side-toggle" aria-label="Collapse menu" aria-expanded="true">
          <svg class="a3s-ic" aria-hidden="true"><use href="#ic-sidebar"></use></svg>
        </button>
      </div>
      <h1 class="a3s-topbar__heading a3s-workspace">       <!-- the tenant: accent-soft pill -->
        <span class="a3s-workspace__initial">R</span><span class="a3s-workspace__name">Company Name</span>
      </h1>
    </div>
    <div class="a3s-topbar__right">
      <button type="button" class="a3s-btn a3s-btn--primary a3s-topbar__signout">
        <svg class="a3s-ic"><use href="#ic-logout"></use></svg><span>Sign out</span>
      </button>
    </div>
  </header>

  <div class="a3s-shell">
    <aside class="a3s-side" aria-label="Primary">
      <div class="a3s-side__scroll">
        <div class="a3s-side__group" data-group="customer-relations">
          <button type="button" class="a3s-side__label" data-group-toggle aria-expanded="true" aria-controls="nav-cr">
            <span class="a3s-side__label-text">Customer Relations</span>
            <svg class="a3s-ic a3s-side__chevron"><use href="#ic-chevron"></use></svg>
          </button>
          <ul class="a3s-side__list" id="nav-cr">
            <li><a class="a3s-side__item is-active" href="/app/leads" aria-current="page">
              <span class="a3s-side__icon"><svg class="a3s-ic"><use href="#ic-lead"></use></svg></span>
              <span class="a3s-side__text"><span class="a3s-side__title">Lead</span><span class="a3s-side__sub">Prospects and enquiries</span></span>
            </a></li>
          </ul>
        </div>
      </div>
      <div class="a3s-side__user"><div class="a3s-user">
        <span class="a3s-user__avatar">A</span>
        <span class="a3s-user__meta"><span class="a3s-user__name">Full Name</span><span class="a3s-user__email">user@example.com</span></span>
      </div></div>
    </aside>

    <main class="a3s-main" id="main">                       <!-- add a3s-main--wide for dashboards and boards -->
      <div class="a3s-main__topline">
        <nav class="a3s-crumbs a3s-main__crumbs" aria-label="Breadcrumb"><ol>
          <li><a href="/app/dashboard">Home</a></li><li aria-current="page">Leads</li>
        </ol></nav>
        <a class="a3s-backlink" href="/app/leads">&larr; Back to leads</a>
      </div>
      <!-- page content -->
    </main>
  </div>
</body>
```

### 4.2 Shell CSS (essentials)

```css
.a3s-app { background: var(--color-bg); min-height: 100vh; }
.a3s-topbar { position: fixed; top: 0; left: 0; right: 0; z-index: 50; height: var(--a3s-topbar-h);
	display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0 1.5rem;
	background: var(--color-surface); border-bottom: 1px solid var(--color-border); }
.a3s .a3s-topbar__heading { margin: 0; font-size: 1rem; font-weight: 700; letter-spacing: -0.01em;
	white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.a3s-topbar__signout { gap: 0.45rem; padding: 0.45rem 0.9rem; font-size: 0.8125rem; }

.a3s-shell { padding-top: var(--a3s-topbar-h); }
.a3s-side { position: fixed; top: var(--a3s-topbar-h); bottom: 0; left: 0; width: var(--a3s-side-w);
	display: flex; flex-direction: column; background: var(--color-surface); border-right: 1px solid var(--color-border); }
.a3s-side__scroll { flex: 1; overflow-y: auto; padding: 1.25rem 0.75rem; }
.a3s-side__group + .a3s-side__group { margin-top: 1.75rem; }
.a3s-side__label { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
	margin: 0 0 0.5rem; padding: 0.3rem 0.65rem; border: 0; border-radius: var(--radius-tile); background: none;
	font: inherit; font-size: 0.6875rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
	color: var(--color-text-muted); cursor: pointer; }
.a3s-side__group.is-collapsed .a3s-side__chevron { transform: rotate(-90deg); }
.a3s-side__group.is-collapsed .a3s-side__list { display: none; }
.a3s-side__list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.15rem; }
.a3s-side__item { display: flex; align-items: center; gap: 0.75rem; padding: 0.6rem 0.7rem; border-radius: var(--radius-tile); }
.a3s-side__item:hover { background: var(--color-bg); }
.a3s-side__icon { flex: none; width: 2rem; height: 2rem; display: grid; place-items: center; border-radius: 0.6rem;
	background: var(--color-bg); color: var(--color-text-muted); }
.a3s-side__item:hover .a3s-side__icon { background: var(--color-accent-soft); color: var(--color-accent-hover); }
.a3s-side__title { font-size: 0.875rem; font-weight: 600; line-height: 1.3; }
.a3s-side__sub { font-size: 0.75rem; color: var(--color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.a3s-side__item.is-active { background: var(--color-accent-soft); }
.a3s-side__item.is-active .a3s-side__title { color: var(--color-accent-hover); }
.a3s-side__item.is-active .a3s-side__icon { background: var(--color-accent); color: #fff; }
.a3s-side__user { border-top: 1px solid var(--color-border); padding: 0.85rem; }
.a3s-user__avatar { width: 2.25rem; height: 2.25rem; display: grid; place-items: center; border-radius: 50%;
	background-image: var(--color-accent-gradient); color: #fff; font-weight: 700; font-size: 0.95rem; }

.a3s-main { margin-left: var(--a3s-side-w); padding: 2.25rem 2.5rem; max-width: 82rem; }
.a3s-main--wide { max-width: none; }
.a3s-crumbs ol { display: flex; align-items: center; gap: 0.5rem; margin: 0; padding: 0; list-style: none; font-size: 0.8125rem; }
.a3s-crumbs li { display: flex; align-items: center; gap: 0.5rem; color: var(--color-text-muted); }
.a3s-crumbs li + li::before { content: "/"; color: var(--color-border-strong); }
.a3s-crumbs [aria-current="page"] { color: var(--color-text); font-weight: 600; }
.a3s-backlink { color: var(--color-sky-ink); font-size: 0.8125rem; font-weight: 600; }
```

**The menu remembers its state** (per browser, in `localStorage`):
- **Collapsed menu:** `"a3s-side" = "collapsed"` adds `a3s-side-collapsed` to `<html>`. It is applied in an inline `<script>` in `<head>`, before first paint, so the menu never flashes open.
- **Collapsed menu, from 900px:** the sidebar becomes 4.75rem wide and shows icons only, and the toggle turns into a small round button on its edge.
- **Closed groups:** stored as `"a3s-nav-groups"`, a JSON map of the group keys that are closed.

### 4.3 Breakpoints

| Width | What changes |
|---|---|
| ≤ 480px | Definition lists stack |
| ≤ 640px | Form grids go to one column; record-header actions go full width |
| ≤ 899px | The sidebar becomes a static horizontal scrolling strip; main has no left margin and padding `1.5rem 1.25rem`; the Sign out label and menu toggle are hidden |
| ≥ 640px | Dashboard stats go to 3 columns |
| ≥ 900px | Dashboard cards and "My work" columns go to 3 |
| ≥ 1100px | Record detail goes to 2 columns; 4-up stats |
| ≥ 1200px | Edit layout `minmax(0,2fr) minmax(18rem,1fr)` (form + side cards); the task board shows all its columns |
| ≥ 1400px | The project header goes to 4 columns |

**Grid helpers**
- `.a3s-form__grid`: 2 columns with gap 1rem. Inside edit pages the gap is `1.1rem 1.5rem`.
- `.a3s-field--wide`: spans the full row. `.a3s-form__grid--3`: 3 columns.
- Auto-fit card grids: `repeat(auto-fit, minmax(13rem, 1fr))`.
- **Always** give grid children `min-width: 0`, so long text and tables can't push a column wider.

---

## 5. Components

### 5.1 Buttons
```css
.a3s-btn { display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem;
	border-radius: var(--radius-pill); padding: 0.75rem 1.5rem; font: inherit; font-size: 0.875rem; font-weight: 600;
	border: 1px solid transparent; cursor: pointer; transition: all var(--duration) var(--ease); white-space: nowrap; }
.a3s-btn--primary { background-image: var(--color-accent-gradient); color: #fff; box-shadow: var(--shadow-soft); }
.a3s-btn--primary:hover { color: #fff; transform: translateY(-1px); box-shadow: var(--shadow-raised); }
.a3s-btn--secondary { background: var(--color-surface); border-color: var(--color-border-strong); color: var(--color-text); }
.a3s-btn--secondary:hover { border-color: var(--color-accent); color: var(--color-accent); }
.a3s-btn--ghost { background: transparent; color: var(--color-text); }
.a3s-btn--ghost:hover { color: var(--color-accent); }
.a3s-btn--sm { padding: 0.4rem 0.85rem; font-size: 0.8125rem; }
.a3s-btn--block { width: 100%; }
.a3s-btn[disabled], .a3s-btn[aria-disabled="true"] { opacity: 0.55; cursor: not-allowed; transform: none; }
/* Busy: a spinner before the label */
.a3s-btn.is-busy { cursor: progress; }
.a3s-btn.is-busy::before { content: ""; width: 1rem; height: 1rem; border: 2px solid currentColor;
	border-right-color: transparent; border-radius: 50%; animation: a3s-spin 0.7s linear infinite; }
@keyframes a3s-spin { to { transform: rotate(360deg); } }
/* A link styled as a button keeps its colours */
.a3s a.a3s-btn--primary, .a3s a.a3s-btn--primary:hover { color: #fff; }
```
```html
<button type="button" class="a3s-btn a3s-btn--primary"><svg class="a3s-ic"><use href="#ic-save"></use></svg><span>Save changes</span></button>
<button type="button" class="a3s-btn a3s-btn--secondary"><svg class="a3s-ic"><use href="#ic-upload"></use></svg><span>Upload Invoice</span></button>
```
- **Primary:** one main action per card or page, such as Save, Create or Send.
- **Secondary:** a supporting action, such as Upload, View or Export.
- **Ghost:** Cancel or Discard.
- **Destructive confirm:** inside modals only, using `#d92d20`.

**Icon buttons**
- `.a3s-square-btn` is 2.9rem with radius 0.8rem, a strong border and a soft shadow. Variants: `--primary`, `--whatsapp`.
- `.a3s-icon-btn` is 1.9rem with radius 0.55rem and transparent. Variants: `--framed`, `--primary`, `--danger`.

**Text link button** (an action that should read as a link)
```css
.a3s-textlink { padding: 0.15rem 0; border: 0; background: none; cursor: pointer; font: inherit; font-size: 0.875rem;
	font-weight: 700; color: var(--color-accent-hover); text-decoration: underline; text-underline-offset: 0.2em; }
.a3s-textlink:hover { color: var(--color-accent); }
```

### 5.2 Cards
```css
.a3s-card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-card);
	padding: 1.75rem; box-shadow: var(--shadow-soft); display: flex; flex-direction: column; }
/* Portal cards do not lift: */
.a3s-edit__card { display: block; height: auto; padding: 1.5rem 1.75rem; }    /* 1.25rem at <=640px */
.a3s-edit__card:hover { transform: none; box-shadow: var(--shadow-soft); }
.a3s-edit__card-title { margin: 0 0 1rem; font-size: 0.8125rem; font-weight: 800; letter-spacing: 0.1em;
	text-transform: uppercase; color: var(--color-accent-hover); }
```
```html
<section class="a3s-card a3s-edit__card">
  <h3 class="a3s-edit__card-title">Supplier details</h3>
  …
</section>
```
A **collapsible card** puts a `<button class="a3s-edit__toggle">` inside the title, with a chevron icon `.a3s-edit__chevron` that rotates.

### 5.3 Form fields
```css
.a3s-field { display: grid; gap: 0.35rem; }
.a3s-field label { font-size: 0.8125rem; font-weight: 600; }
.a3s-field input, .a3s-field select, .a3s-field textarea { font: inherit; font-size: 0.9375rem; color: var(--color-text);
	background: var(--color-bg); border: 1px solid var(--color-border); border-radius: 0.75rem; padding: 0.7rem 0.9rem;
	width: 100%; transition: border-color var(--duration) var(--ease); }
.a3s-field input:focus, .a3s-field select:focus, .a3s-field textarea:focus { border-color: var(--color-accent); background: var(--color-surface); }
.a3s-field--error input, .a3s-field--error select { border-color: var(--color-danger); }
.a3s-field__error { font-size: 0.8125rem; color: var(--color-danger); }
.a3s-field__hint { margin: -0.25rem 0 0; font-size: 0.8125rem; color: var(--color-text-muted); }
.a3s-req { color: var(--color-danger); }
.a3s-check input { accent-color: var(--color-accent); }
/* In edit pages and modals the labels become the small uppercase kind: */
.a3s-edit .a3s-field > label { font-size: 0.6875rem; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; }
.a3s-edit .a3s-field input, .a3s-edit .a3s-field select { padding: 0.62rem 0.85rem; border-radius: 0.7rem; }
```
```html
<div class="a3s-form__grid">
  <div class="a3s-field">
    <label for="fld-name">Supplier name <span class="a3s-req">*</span></label>
    <input id="fld-name" name="supplier_name">
    <p class="a3s-field__hint">As printed on the invoice.</p>
  </div>
  <div class="a3s-field a3s-field--wide">…</div>
</div>
```
- **Inline note:** a small tag beside a label, such as "from the invoice", is coloured in sky-ink at weight 700.
- **Read-only facts:** shown as `.a3s-facts`, a grid of label/value pairs with the uppercase label style.

### 5.4 Searchable dropdown (combo)
- Wrap a native `<select>` as `<div class="a3s-field a3s-combo a3s-combo--field" data-combo>`, then call `window.a3sCombo.wireAll(document)`. The code is in `public/js/portal_combo.js`.
- The script adds `<input type="search" role="combobox" placeholder="Search or pick">` and hides the select.
- The list `.a3s-combo__list` has radius 0.85rem, `--shadow-raised` and a max height of 17rem. Each item is a `button.a3s-combo__opt`, with a `<small>` id line under it; the active item is accent-soft.
- No results shows "No match." An optional row `.a3s-combo__add` offers "+ Add a new …".
- Keyboard: ↑ ↓ Enter Esc. Dispatch `a3s:sync` on the select after changing it from code.

### 5.5 Tables
```css
.a3s-tablewrap { padding: 0; overflow-x: auto; }                      /* on a .a3s-card */
.a3s-tablewrap:hover { transform: none; box-shadow: var(--shadow-soft); }
.a3s-table { width: 100%; border-collapse: collapse; font-size: 0.9375rem; }
.a3s-table thead th { text-align: left; font-size: 0.6875rem; text-transform: uppercase; letter-spacing: 0.05em;
	color: var(--color-text-muted); font-weight: 600; padding: 1rem 1.25rem; border-bottom: 1px solid var(--color-border);
	white-space: nowrap; vertical-align: top; }
.a3s-table tbody td { padding: 0.9rem 1.25rem; border-bottom: 1px solid var(--color-border); vertical-align: top; }
.a3s-table tbody td.a3s-table__status { vertical-align: middle; }
.a3s-table tbody tr:last-child td { border-bottom: 0; }
.a3s-table tbody tr:hover { background: var(--color-bg); }
.a3s-table__link { font-weight: 600; color: var(--color-text); }
.a3s-table__meta { display: block; font-size: 0.8125rem; color: var(--color-text-muted); }
.a3s-table__muted { color: var(--color-text-muted); }               /* shows — when empty */
```
```html
<div class="a3s-card a3s-tablewrap"><table class="a3s-table">
  <thead><tr><th>Customer</th><th>Status</th><th>Amount</th></tr></thead>
  <tbody><tr>
    <td><a class="a3s-table__link" href="…">Name</a><span class="a3s-table__meta">SOL-INST-2026-00010</span></td>
    <td class="a3s-table__status"><span class="a3s-badge a3s-badge--open">Open</span></td>
    <td class="a3s-table__num">₹1,45,824.00</td>
  </tr></tbody>
</table></div>
```
- **Record cell:** `a.a3s-table__record` puts an `.a3s-avatar` before the name.
- **Totals:** totals rows and money cells in item tables use `.a3s-num` (right-aligned) with `tabular-nums`.

### 5.6 Badges, pills and chips
```css
.a3s-badge { display: inline-block; padding: 0.2rem 0.65rem; border-radius: var(--radius-pill); font-size: 0.75rem;
	font-weight: 600; white-space: nowrap; background: rgba(42,51,66,0.08); color: var(--color-text-muted); }
.a3s-badge--open { background: rgba(41,171,226,0.14); color: #1b8dc0; }
.a3s-badge--quotation { background: var(--color-accent-soft); color: var(--color-accent-hover); }
.a3s-badge--converted { background: rgba(40,200,64,0.16); color: #1a7a2b; }
.a3s-badge--lost-quotation { background: rgba(255,95,87,0.14); color: #c0392b; }
```
Name a status modifier after the status's slug, for example `a3s-badge--{slug}`, and colour it with a tone pair from section 2.3.
- **Pills:** `.a3s-pill` comes in `--green`, `--amber`, `--red`, `--sky`, `--muted`, `--grey`, `--due` and `--who`.
- **Document states:** `.a3s-taskdocs__state.is-missing`, `is-uploaded`, `is-generated`, `is-paid`, `is-pending-approval`, `is-approved`, `is-rejected` and `is-partly`.
- **Dots:** `.a3s-dot--red`, `--amber` and `--green`.

### 5.7 Tabs (segmented pills)
```css
.a3s-ce-tabs { display: flex; gap: 0.35rem; padding: 0.35rem; width: max-content; max-width: 100%; overflow-x: auto;
	background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-pill); }
.a3s-ce-tabs button { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.55rem 1.1rem; border: 0;
	border-radius: var(--radius-pill); background: transparent; color: var(--color-text-muted); font: inherit;
	font-weight: 600; font-size: 0.9rem; cursor: pointer; }
.a3s-ce-tabs button:hover { color: var(--color-text); background: var(--color-accent-soft); }
.a3s-ce-tabs button[aria-selected="true"] { background-image: var(--color-accent-gradient); color: #fff;
	box-shadow: 0 8px 20px -10px rgba(247,148,30,0.9); }
.a3s-ce-tabs__n { font-size: 0.7rem; font-weight: 800; padding: 0.05rem 0.5rem; border-radius: var(--radius-pill); background: rgba(42,51,66,0.08); }
```
Give the tab bar `role="tablist"` and each button `role="tab"` with `aria-selected`.

**Step wizard** (`.a3s-wizard`):
- A gradient fill track, with numbered circles in the states `is-done`, `is-current` and `is-complete`.
- The current circle is gradient-filled, at `scale(1.12)`, with a 4px accent-soft ring.
- The bar is sticky at the top of edit pages (`.a3s-edit__nav`).

### 5.8 Page header and record header
```css
.a3s-page__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.75rem; }
```
```html
<div class="a3s-page__head">
  <div><h2 class="a3s-main__title">Leads</h2><p class="a3s-main__sub">Prospects and enquiries, stored in ERPNext.</p></div>
  <a class="a3s-btn a3s-btn--primary" href="…/new"><svg class="a3s-ic"><use href="#ic-lead"></use></svg><span>New lead</span></a>
</div>
```
A record page uses `.a3s-detail__head`: an eyebrow `.a3s-detail__eyebrow` (0.75rem uppercase muted, holding the record ID), the title with a status badge, and `.a3s-detail__actions` on the right.

### 5.9 Dashboard: stats, "My work", action cards
```css
.a3s-dash-stats { display: grid; gap: 1.5rem; grid-template-columns: 1fr; margin-bottom: 1.75rem; }   /* 3 cols >=640px */
.a3s-dash-stat { flex-direction: row; align-items: center; gap: 1rem; padding: 1.6rem; }            /* on .a3s-card */
.a3s-dash-stat:hover { transform: none; box-shadow: var(--shadow-soft); }
.a3s-dash-stat__icon { width: 3rem; height: 3rem; display: grid; place-items: center; border-radius: var(--radius-tile); }
.a3s-dash-stat__icon--sky { background: rgba(41,171,226,0.12); color: #1b8dc0; }
.a3s-dash-stat__icon--amber { background: var(--color-accent-soft); color: var(--color-accent-hover); }
.a3s-dash-stat__icon--green { background: rgba(40,200,64,0.14); color: #1a7a2b; }
.a3s-dash-stat__label { display: block; font-size: 0.6875rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted); }
.a3s-dash-stat__value { display: block; font-size: 1.6rem; font-weight: 700; line-height: 1.2; }
.a3s-dash-stat__note { display: block; font-size: 0.8125rem; color: var(--color-text-muted); }
.a3s-dash-card { min-height: 15rem; }  /* icon 2.5rem tile, title 1.05rem, text muted, CTA pinned to the bottom */
```
- **"My work" columns:** each is `<details class="a3s-card a3s-work__col a3s-work__col--red|amber|sky">` with a 4px coloured top border. The `<summary class="a3s-work__summary">` holds a count pill and a chevron that rotates. Columns start closed and show only their count.
- **Work items:** each carries a kind chip `.a3s-work__kind--task|followup|assignment|ticket` with radius 4px. A late due date `.a3s-work__due.is-late` is shown in `#b42318`.

### 5.10 Snapshot tiles and progress bar
- **Tiles:** `.a3s-tile` has a 2.75rem icon with a white glyph on a green, amber or sky gradient, a value at 1.35rem/800, and a label. The `--link` variant lifts on hover.
- **Progress bar:**
```css
.a3s-progress { height: 0.5rem; border-radius: 999px; background: var(--color-border); overflow: hidden; }
.a3s-progress__fill { display: block; height: 100%; border-radius: inherit; background-image: var(--color-accent-gradient); transition: width 0.3s var(--ease); }
.a3s-progress__fill.is-overdue { background: var(--color-danger); }
```
```html
<div class="a3s-progress" role="progressbar" aria-valuenow="7" aria-valuemin="0" aria-valuemax="100"><span class="a3s-progress__fill" style="width:7%"></span></div>
```

### 5.11 Modals
```css
.a3s-modal { position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; padding: 1.25rem; background: rgba(42,51,66,0.45); }
.a3s-modal[hidden] { display: none; }
.a3s-modal__panel { width: min(30rem, 100%); max-height: 90vh; overflow-y: auto; background: var(--color-surface);
	border-radius: var(--radius-card); box-shadow: var(--shadow-raised); padding: 1.5rem 1.75rem 1.75rem; }
.a3s-modal__title { margin: 0 0 0.5rem; font-size: 0.8125rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--color-accent-hover); }
```
- **Widths:** default 30rem, a task panel 40rem, a wide editor 46rem.
- **Closing:** a modal closes on Esc, on a backdrop click and on any `[data-close]` element.
- **Destructive confirm:** a red pop-up such as "Name mismatch" gets a 4px top border in `#d92d20`, its title in `#b42318`, and a confirm button in `#d92d20`.

### 5.12 Menus
A **row menu** (`.a3s-taskmenu`) is fixed in place at z-index 90. A **print or export menu** is `<details class="a3s-printmenu">` with a list of options.

### 5.13 Status messages and notices
```css
.a3s-form__status { margin: 0; font-size: 0.875rem; }
.a3s-form__status.is-error { color: var(--color-danger); }
.a3s-form__status.is-success { color: #1a7a2b; }
/* The boxed kind: */
.a3s-attach__status { margin: 0.85rem 0 0; padding: 0.55rem 0.8rem; border-radius: 0.65rem; font-size: 0.8125rem; background: var(--color-bg); color: var(--color-text-muted); }
.a3s-attach__status[data-tone="ok"] { background: rgba(40,200,64,0.1); color: #1a7a2b; }
.a3s-attach__status[data-tone="error"] { background: rgba(255,95,87,0.1); color: #c0392b; }
.a3s-attach__status[data-tone="warn"] { background: rgba(247,144,9,0.12); color: #93370d; border-left: 3px solid #f79009; }
```
```html
<p class="a3s-attach__status" data-status role="status" aria-live="polite" hidden></p>
```
- **Notice banner:** `.a3s-notice` uses the Notice tone.
- **Highlighted callout:** a warning such as "Name mismatch: …" is a soft red box with a 4px left border in `#d92d20`. The key words are bold, and the names inside are in `#b42318`.

### 5.14 Attachments card
A dashed accent-soft drop panel with a 2.75rem gradient icon, a "Document type…" select and a "Choose files" primary button.
- **States:** the panel takes `.is-dragging` and `.is-busy`.
- **Files:** each file is a row in a 3-column grid. A type badge comes first (`--pdf`, `--img`, `--doc`, `--xls`, `--file`), then the name and meta, then the type and actions: View and Remove.
- **Header and empty state:** the header shows a count pill, and `.a3s-attach__empty` reads "No files attached yet."
- **Code:** `templates/includes/portal_attachments.html` and `public/js/portal_attachments.js`.

### 5.15 Empty state
```css
.a3s-empty { text-align: center; padding: 3rem 2rem; }                 /* on .a3s-card */
.a3s-empty__icon { display: inline-grid; place-items: center; width: 3rem; height: 3rem; border-radius: var(--radius-tile);
	background: var(--color-accent-soft); color: var(--color-accent-hover); margin-bottom: 1rem; }
.a3s-empty__title { font-size: 1.15rem; margin-bottom: 0.35rem; }
.a3s-empty__text { color: var(--color-text-muted); margin: 0 auto 1.25rem; max-width: 26rem; }
```
The copy is "No leads yet" / "Create the first one and it will appear here.", followed by a primary button.

### 5.16 Task board
- **Layout:** `.a3s-proj__board > .a3s-proj__cols > .a3s-proj__col`. The column count comes from `--a3s-proj-cols`.
- **Column head:** a bg-colour strip with a 1.75rem gradient icon, the uppercase title and a done/total count.
- **Cards:** `.a3s-proj__task` is 5.9rem tall with radius 0.65rem. It holds a 2rem tile icon, the task name, dates, a white status pill (0.625rem/800) and the assignee.
- **Status colours:** set with the `--tk-*` variables.

| State | ink | tile | card | line |
|---|---|---|---|---|
| Pending (default) | `#b8650a` | `#fde3c2` | `#fff` | `#fbd3a1` |
| `is-in-progress` | `#8a6a00` | `#fdf0b0` | `#fffbe6` | `#f3df84` |
| `is-blocked` | `#c0392b` | `#ffd9d6` | `#fff1f0` | `#ffc4c0` |
| `is-completed` | `#1a7a2b` | `#cdf2d4` | `#effbf1` | `#b7e9c0` |
| `is-locked` | `#8a6d1f` | `#fff3cf` | `#fffbef` | `#f1dfa6` (opacity 0.85) |
| `is-skipped` | `#6b7383`, name struck through | | | |

### 5.17 Icons
- **Format:** one inline SVG sprite at the top of `<body>`. Each `<symbol>` is Feather style: `viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"`.
- **Usage:** `<svg class="a3s-ic" aria-hidden="true"><use href="#ic-upload"></use></svg>`.
- **Sizes:** `.a3s-ic` is 1.15rem; `.a3s-ic--lg` is 1.35rem. In small buttons and tabs, set the icon to 1rem.
- **IDs in A3 Sola** (`templates/includes/portal_icons.html`): user, lead, doc, pen, edit, trash, back, download, upload, whatsapp, eye, mail, share, save, pin, check, wrench, clipboard, bolt, power, wallet, calc, logout, sidebar, chevron, cart, checklist, cash, globe, bank, scroll, box, truck, package, stack, star, briefcase, calendar, receipt, shield, ticket, gauge, refund, request, inbox, transfer, barcode, ledger, alert, phone.
- **New icons:** copy the sprite and add symbols in the same stroke style.

### 5.18 Avatars and initials
- `.a3s-avatar` is 2.25rem and round. `--initials` gives it the accent gradient with white 0.75rem/700 text; `--sm` makes it 1.75rem.
- A record photo is a 4rem square with radius 1rem. Its initials version is 1.15rem/800.
- The workspace initial in the top bar is a white circle with accent-hover text.

---

## 6. JavaScript conventions

Each page has **one self-contained script**: an IIFE in `"use strict"` mode, with no framework and no build step. Each page's script carries its own copy of these helpers.

```js
(function () {
	"use strict";

	var meta = document.querySelector('meta[name="csrf-token"]');   // <meta name="csrf-token" content="…"> in the shell
	var csrf = meta ? meta.getAttribute("content") : "";

	function esc(s) {
		return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
		});
	}

	/* The readable text out of Frappe's _server_messages envelope. */
	function serverMessage(body) {
		try {
			var msgs = JSON.parse((body && body._server_messages) || "[]");
			if (msgs.length) return String(JSON.parse(msgs[0]).message || "").replace(/<[^>]*>/g, "");
		} catch (e) { /* fall through */ }
		return (body && body.exception) ? String(body.exception).split(":").slice(1).join(":").trim() : "";
	}

	/* POST a whitelisted method; JSON args, or FormData for uploads. Resolves to body.message. */
	function call(method, args, formData) {
		var opts = { method: "POST", credentials: "same-origin", headers: { "X-Frappe-CSRF-Token": csrf, "Accept": "application/json" } };
		if (formData) { opts.body = formData; }
		else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(args || {}); }
		return fetch("/api/method/" + method, opts).then(function (r) {
			return r.json().catch(function () { return {}; }).then(function (body) {
				if (!r.ok) throw new Error(serverMessage(body) || (r.status === 403 ? "You do not have permission to do that." : "That did not go through. Try again."));
				return body.message;
			});
		});
	}

	/* One status line per page or card: tone = "ok" | "error" | "warn" | "" */
	function setStatus(el, text, tone) {
		el.textContent = text || "";
		el.dataset.tone = tone || "";
		el.hidden = !text;
	}

	/* A modal: closes on Esc, backdrop click and [data-close]; removes itself. */
	function modal(title) {
		var back = document.createElement("div");
		back.className = "a3s-modal";
		back.innerHTML = '<div class="a3s-modal__panel" role="dialog" aria-modal="true" aria-label="' + esc(title) + '">' +
			'<h3 class="a3s-modal__title">' + esc(title) + '</h3><div data-body></div>' +
			'<p class="a3s-form__status" data-status role="status" aria-live="polite"></p></div>';
		function close() { back.remove(); document.removeEventListener("keydown", onKey); }
		function onKey(e) { if (e.key === "Escape") close(); }
		document.addEventListener("keydown", onKey);
		back.addEventListener("click", function (e) { if (e.target === back || e.target.closest("[data-close]")) close(); });
		document.body.appendChild(back);
		return { el: back, body: back.querySelector("[data-body]"), close: close };
	}

	var money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
	// money.format(145824) -> "₹1,45,824.00"
})();
```

- **Busy states:** while saving, set `btn.disabled = true` and add `.is-busy` (the spinner), or change the label to "Saving…". Then restore the button.
  - A panel being worked on gets `.is-busy` or `.is-loading` (opacity 0.55–0.7, `pointer-events: none`).
- **Escaping:** every server value written into `innerHTML` goes through `esc()`.
- **Asset versioning:** link CSS and JS with `?v=<file mtime>`, so a deploy is never served stale. In A3 Sola this is `a3s_asset_version('js/x.js')`.
- **Per-browser preferences:** menu state, open groups and remembered tabs live in `localStorage`, wrapped in `try { } catch { }`.

---

## 7. Copy and voice

- **Sentence case for actions and messages:** "Save changes", "Choose files", "Record payment", "Upload Invoice", "New lead".
- **Title Case for menu items and record types:** "Solar Installation", "Payment Schedule". The sidebar groups are "Customer Relations", "Operations Management", "Project Management" and "Stores & Accounts".
- **Menu subtitles** are short noun phrases: "Prospects and enquiries", "Delivery and service".
- **Standard messages:**
  - "Saving…" and "Saved."
  - "That did not go through. Try again."
  - "Could not reach the server. Check your connection and try again."
  - "You do not have permission to do that."
- **Empty states:** "No {things} yet" / "Create the first one and it will appear here.", "No files attached yet.", "No match."
- **Punctuation:** use a real ellipsis "…", "·" as a separator, "—" for an empty value, and "← Back to …" for back links.
- **Tone:** plain and in the second person: "Here is what you have to do." Say what will happen, not how the system works.
- **Domain words:** use the business's own words consistently. In A3 Sola the work is a **Project**, never a "job".
- **Warnings:** name the thing and what to do. For example: "Name mismatch: the bill is for X, but this project is Y's. You will be asked to confirm before it is entered."

---

## 8. Accessibility checklist

- Visible focus everywhere: the 3px accent outline.
- Status lines use `role="status" aria-live="polite"`.
- Modals use `role="dialog" aria-modal="true"` and an `aria-label`, and close on Esc.
- Tabs use `role="tab"` and `aria-selected`; collapsible headers use `aria-expanded` and `aria-controls`.
- The current page carries `aria-current="page"`, in both the menu and the breadcrumb.
- Decorative icons have `aria-hidden="true"`; icon-only buttons have an `aria-label`.
- Include a skip link (`.a3s-skip`) to `#main`.
- Honour `prefers-reduced-motion`.
- Required fields show `*` in `.a3s-req`, and errors appear as text, not only as a red border.

---

## 9. Page recipes

- **List page:**
  - `.a3s-page__head` (title, sub, "New …" primary button);
  - a toolbar (search input and a status select, radius 0.75rem);
  - `.a3s-card.a3s-tablewrap > table.a3s-table`;
  - an `.a3s-empty` card when there are no rows.
- **Record page:**
  - `.a3s-detail__head` (eyebrow ID, title with badge, actions);
  - a snapshot row of `.a3s-tile`s;
  - two columns from 1100px of `.a3s-edit__card`s: facts, related records, attachments.
- **Edit or create page:**
  - a sticky `.a3s-wizard` step bar;
  - `.a3s-edit` grid (2fr form + 1fr side cards from 1200px);
  - each step an `.a3s-edit__card` with an uppercase title and an `.a3s-form__grid`;
  - `.a3s-form__actions` at the end (primary Save, ghost Cancel) with the status line beside it.
- **Dashboard:**
  - title "Welcome, {first name}" and "Here is what you have to do.";
  - `.a3s-dash-stats` (Overdue, Due today, Next 7 days, No date);
  - "My work" columns;
  - three `.a3s-dash-card` action cards.
- **Task page:**
  - one or more `.a3s-edit__card`s in task order;
  - feedback through `.a3s-attach__status[data-tone]`;
  - "Mark done" as the final primary action.

---

## 10. Starting a new app

1. Copy `platform.css` from A3 Sola, or extract the portal part from line 1126 onwards plus the tokens, reset and button, card and badge sections above it. Rename the prefix once if needed.
2. Copy `templates/portal_shell.html` and `templates/includes/portal_icons.html`, then change the product name, logo and nav groups.
3. Copy the helpers in section 6 into each page script.
4. Keep this file next to the code, and update it whenever a new pattern is added, so it never drifts from the real UI.

---

## 11. Reference files in A3 Sola

| File | What it holds |
|---|---|
| `a3_sola/public/css/platform.css` | The single stylesheet (~3,660 lines): tokens at the top, marketing site, then the portal shell from line 1126 and every component |
| `a3_sola/templates/portal_shell.html` | Page skeleton: fonts, CSRF meta, collapsed-menu script, top bar, sidebar, main column, blocks `portal_head`, `portal_content` and `portal_scripts` |
| `a3_sola/templates/includes/portal_icons.html` | The SVG icon sprite |
| `a3_sola/templates/includes/portal_list_body.html` | List page: header, table, empty state |
| `a3_sola/templates/includes/portal_detail_body.html` | Record page |
| `a3_sola/templates/includes/portal_edit_body.html`, `portal_form_body.html` | Edit and create forms with the step wizard |
| `a3_sola/templates/includes/portal_attachments.html` | Attachments card |
| `a3_sola/templates/includes/portal_combo_fields.html` + `public/js/portal_combo.js` | Searchable dropdowns |
| `a3_sola/templates/includes/portal_project_overview.html` | Project header, payment schedule, task board |
| `a3_sola/www/a3solaportal/dashboard.html` | Dashboard |
| `a3_sola/www/a3solaportal/__init__.py` | Menu groups and items (`NAV_GROUPS`), shell context |
| `a3_sola/public/js/portal_project_board.js` | The best reference for `call`, `esc` and `modal` |
| `a3_sola/public/js/portal_record_edit.js` | Form save, status and busy-button pattern |
| `a3_sola/public/js/portal_supplier_bill.js` | A full task page: upload, read, edit tables, modals |

**Known quirks** (don't copy them as rules):
- `.a3s-badge` is defined twice in `platform.css` (around lines 282 and 1615). The later definition wins.
- `#e8840c` and `#f5a524` appear only in the **print** templates (PDF letterheads) and one inline task style. The portal orange is `#f7941e` (hover `#e07f0c`).
- A few pages carry an inline `<style>` block (for example `www/a3solaportal/projects/task.html`). Move new styles into the stylesheet instead.
