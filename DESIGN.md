# DESIGN.md — opencode.ai/docs, end to end

A complete design reference for the documentation site at **https://opencode.ai/docs**, written so
it can be used to rebuild a different docs site (here: Universal Data Cleaner on MkDocs Material)
in the same layout and visual language.

It is based on the live pages plus the site's own source of truth, `services/site` in
`github.com/anomalyco/opencode` (`dev` branch): `DESIGN.md`, `src/docs/AGENTS.md`,
`src/docs/styles/docs.css`, `src/docs/layouts/DocsLayout.tsx`, `src/docs/lib/navigation.ts`,
`src/component/site/*.css`, and the shared token files in `src/style/token/`. Every number quoted
below is taken from those files, not estimated from screenshots.

- **Scope**: the V2 docs at `/docs/*` (the V1 docs at `/v1/docs` reuse the shell with an extra
  notice and are noindexed).
- **Read this as**: a system, not a skin. Values are the ones in use; structure matters more than
  any single hex.
- **Date**: November 2026.

---

## 0. The one-paragraph version

The docs look like a **technical manual printed on paper**, rendered on a **strict four-column
grid**. Neutral greys only, square corners, hairline rules, and **OpenTUI Mono for every label,
heading and piece of chrome** with **Inter only for running prose**. There is no card UI, no
gradient, no drop shadow on content, no rounded "pill". Navigation is a bracket list (`[ ]`, `[-]`)
in the left column, contents is a **pipe rail** in the right column, search is a `⌘K` palette, and
code is a **ruled plate with a header row and an always-visible copy button**. Everything is
prerendered HTML; the JS is islands for search, copy, theme and scroll-spy. The page never shifts.

---

## 1. Design DNA (the rules that generate everything else)

These are the invariants. If a decision is not covered below, derive it from these.

1. **Square, ruled, ruled-off.** Corners are `0` (or `50%` for a true circle, `999px` for a pill
   where a pill is meaningful). Separation is a **1px hairline**, never a shadow. Cards are plates
   with a ruled header, not floating tiles.
2. **Neutral greys only.** One shared 11-step grey scale carries the entire UI. Colour appears only
   as **meaning**: the link blue, the three status colours, and the code syntax set. Never decorate
   with hue.
3. **Mono is the voice of the interface.** All chrome — nav, group titles, buttons, captions,
   headings h1–h6, labels, kbd, tables' headers — is OpenTUI Mono. Inter is reserved for the
   paragraph text you actually read. The mono face is the brand.
4. **One baseline, one content line.** The logo, the left nav's first item, the page title, the
   search trigger and the contents rail's first item all sit on **one horizontal line**, 84px from
   the top at default settings. Nothing "floats near" it.
5. **Two rails, one article.** Left column = where you are (section pages). Right column = where
   you can jump (this page). The article is the only thing that grows.
6. **Text is capped, blocks are not.** Prose stops at ~90 characters; code, tables, callouts, tabs
   and cards run the full article column. Text *inside* a block takes that block's width.
7. **States are instant or 150ms.** Hover/current/active change colour, not geometry. Motion is
   transform and opacity only. Reduced motion removes it, never breaks it.
8. **The document is the app.** Pages are separate documents with cross-document view transitions
   and speculative prerendering. No client-side router, no skeleton screens, no layout shift.
9. **Every interactive target is at least 44px on touch**, with the visible affordance allowed to
   stay small (a link's hit area may be padded invisibly).
10. **Neutral copy, no hype.** Sentences state what a thing is and what it does. No exclamation
    marks, no "supercharge", no emoji in chrome.

---

## 2. Foundations

### 2.1 Colour: one grey scale, 11 steps

The scale is **role-based**: step *n* does the same job in both themes. Data, Console and Status use
the same numbers.

| Step | Light | Dark | Role |
|---|---|---|---|
| `grey-1` | `#fbfbfb` | `#0c0c0c` | page |
| `grey-2` | `#ffffff` | `#161616` | raised surface (code body, pop-ups) |
| `grey-3` | `#f5f5f5` | `#1a1a1a` | subtle fill (pressed rows) |
| `grey-4` | `#eeeeee` | `#242424` | hover fill |
| `grey-5` | `#e0e0e0` | `#2e2e2e` | borders, press |
| `grey-6` | `#d2d2d2` | `#4b4b4b` | strong borders, decoration |
| `grey-7` | `#888888` | `#6a6a6a` | marks at 3:1 (quiet icons, nav markers) |
| `grey-8` | `#6b6b6b` | `#8f8f8f` | muted text at 4.5:1 |
| `grey-9` | `#5c5c5c` | `#aeaeae` | body text |
| `grey-10` | `#3a3a3a` | `#dbdbdb` | emphasis |
| `grey-11` | `#161616` | `#fafafa` | ink |

Semantic tokens (always use these, never a raw step):

```
--bg            grey-1    page
--bg-weak       grey-3    pressed rows, quiet fill
--bg-weaker     grey-4    hover fill
--bg-strong     grey-11   ink panels (inverted bars)
--text-strong   grey-11   headings, current item, emphasis
--text          grey-9    body copy
--text-weak     grey-8    secondary text (AA on page and on fills)
--text-muted    grey-8    muted labels that still carry meaning
--text-faint    grey-7    decorative-but-visible marks ([01] shortcuts)
--text-disabled grey-7    off controls
--border        grey-5    hairlines: tables, code frames, rails
--border-strong grey-6    hover edge, stronger divider
--link          light #3b5cf6 / dark #4f8bff
```

Rules of thumb:

- A hairline is `--border`; a 2px **pipe** or bar is a state or a mark.
- Text on any surface must reach **4.5:1**; marks and controls **3:1**.
- Inverted/"ink" panels are `--bg-strong` with `--text-inverted` (`#ffffff` in light, `#0c0c0c` in
  dark) — used for the V1 notice and terminal blocks.
- Use `light-dark()` pairs rather than two stylesheets. Set
  `color-scheme: light dark` on the root and force it with `[data-theme="light"|"dark"]`.

### 2.2 Syntax colours

Chosen for ≥4.5:1 on the code body in both themes. Keywords and flags are violet, commands and
functions orange, strings green, numbers/constants teal, comments the output grey.

| Token | Light | Dark |
|---|---|---|
| command / function | `#a64b14` | `#fab283` |
| keyword / flag | `#7a3fc4` | `#9d7cd8` |
| string | `#2b7a3d` | `#7fd88f` |
| operator / constant | `#0f6e7a` | `#56b6c2` |
| output / comment | `grey-8` | `grey-8` |
| mark (highlight row) | `#3b5cf6` on `#eff2fe` | `#6b8fff` on `#1e2637` |
| diff delete | `#d61f1f` on `#fceded` | `#f04c4c` on `#351e1e` |
| diff insert | `#1a9347` on `#e8f4ed` | `#2dd269` on `#192d20` |

### 2.3 Type

Two families, one job each.

```
--font-mono: "OpenTUI Mono", "OC Arabic", "OC Thai", ui-monospace, SFMono-Regular,
             Menlo, Monaco, Consolas, monospace;
--font-sans: "Inter", "OC Arabic", "OC Thai", ui-sans-serif, system-ui, -apple-system,
             "Segoe UI", sans-serif;
```

The mono face ships in **Regular and Bold only**, so "medium" is faked with a hairline stroke
(`--title-stroke: 0.2px currentColor`). If you substitute a family with a real 500, drop the stroke.

The scale is fixed at desktop, steps **once at 960px**, and only page/hero titles are fluid. Nothing
is below 12px; nothing meaningful on phones is below 14px.

| Token | Desktop | ≤960 | Used for |
|---|---|---|---|
| `--fs-micro` | 12px | 12px | badges, code labels, group titles, footnotes |
| `--fs-meta` | 13px | 14px | code body, dates, refs, captions |
| `--fs-small` | 14px | 15px | buttons, secondary menu text |
| `--fs-ui` | 15px | 16px | **mono UI** — nav, footer, breadcrumbs, tabs, labels |
| `--fs-body` | 15px | 17px | marketing copy |
| `--fs-read` | 16px | 17px | **long-form reading** (docs, legal, changelog) |
| `--fs-title` | 17px | 18px | section headings (h2) |
| `--fs-large` | 18px | 19px | accordion questions, phone menu |
| `--fs-lead` | 18px | 20px | text under a page title |
| `--fs-h1` | `clamp(28px, 25px + 0.5vw, 32px)` | same | docs page title |
| `--fs-display-max` | 64px | 48px | hero titles (site, not docs) |
| `--fs-input` | 14px | 16px | text fields (16 on touch so iOS never zooms) |

Article-level typography:

| Element | Spec |
|---|---|
| `h1` | mono 400, `--fs-h1`/1.15, `letter-spacing: -0.02em`, margin `0 0 1.5rem`, `text-box: trim-start cap` |
| `h2` | mono 400, `--fs-title`/1.35, +0.2px stroke, `scroll-margin-top: 2rem` |
| `h3`–`h6` | mono 700, `--fs-*`/1.5, `--text-strong` (option-2 variant); h3 `2.25rem 0 .75rem`, h4 `2rem 0 .75rem` |
| body | `400 var(--fs-read)/1.6 var(--font-sans)`, `--text` |
| `strong` | 600, `--text-strong` |
| prose width | `--text-measure: calc(42 * var(--fs-read))` ≈ 672px / ~90ch |
| `kbd` | mono `--fs-micro`/1.4, 1px `--border`, padding `0.05em 0.35em`, `white-space: nowrap` |
| `hr` | 2rem above/below, 1px `--border`, no other styling |
| inline `code` | mono, `--fs-meta`, quiet tint, square |
| links in prose | body colour, underlined, `text-underline-offset: 0.2em`; blue on hover/focus/active |

Note the deliberate split: **headings are mono, paragraphs are Inter**. That single decision is what
makes the page read as documentation rather than a blog.

### 2.4 Space, radii, borders

A 4px-based scale, expressed as tokens: `0, 1px, 0.125, 0.1875, 0.25, 0.375, 0.5, 0.625, 0.75,
0.875, 1, 1.125, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 2.75, 3, 3.5, 4, 4.25, 4.5, 4.75, 5, 6, 7, 8, 9, 10,
11, 12, 13, 14, 15, 16, 18, 20, 24rem` (`--space-*`).

In the docs, the recurring rhythm is small and consistent:

| Gap | Value |
|---|---|
| nav row pitch | 20px line + 10px gap = **30px** |
| nav row hit area | `padding-block: 5px; margin-block: -5px` (rows touch, text does not move) |
| group → group | `2rem` |
| group title → items | `0.75rem` |
| block → block (code, table, image) | `1.5rem` bottom margin |
| paragraph → paragraph | `1rem` |
| aside children | `2rem` |
| code frame header | `2.5rem` |
| code body padding | `1rem` |

Radii: the system allows `0`, `50%`, `999px` and `22.5%`. The docs themselves use **0** everywhere:
code frames, tables, callouts, cards, tabs, buttons, images, the search dialog.

### 2.5 Breakpoints and the layout grid

| Breakpoint | What changes |
|---|---|
| **1728px** (`--page-max`) | layout stops growing and centres; the page behind it stays full-bleed |
| **960px** (`60rem`) | the single big step: mobile type scale, desktop rails collapse, top bar appears |
| **960.0625px** | desktop-only rules (min-width), so the two sides never both apply |
| **640px** (`40rem`) | phone: search becomes a full-screen sheet, some spacing tightens |
| coarse pointer | 44px targets regardless of width |

Core layout tokens:

```
--page-max    1728px
--page-width  min(100vw, 1728px)
--page-offset max(0px, (100vw - 1728px) / 2)   /* padding-inline on the root */
--sidebar-width 14.75rem  (236px)
--gutter      1rem        (16px)
--edge        1.5rem      (24px)   /* also --top */
--logo-height 1.75rem     (28px)
--logo-gap    --top + 8px (32px)
--content-top --top + --logo-height + --logo-gap  (84px)
--topbar-height 3.5rem    (56px)
```

Desktop docs columns (≥960):

```
--aside-width: calc((var(--page-width) - var(--sidebar-width) - 4 * var(--gutter) - var(--edge)) / 4 + var(--edge));

grid-template-columns: var(--sidebar-width) minmax(0, 1fr) var(--aside-width);
```

Read that as: the page is a **four-column grid**; the sidebar takes the left edge plus column 1, the
article takes columns 2–3, the contents rail takes column 4 and the right edge. The article then
gives up `2 * gutter + 40px` (72px) on its end side, which is the visual gutter before the rail.

`[data-sidebar="column"]` (a site setting) instead makes the sidebar exactly one of five equal
columns; the docs work with either.

---

## 3. Page anatomy

A docs page is one HTML document with this skeleton (trimmed to structure):

```html
<body>
  <div data-site data-page="docs" data-layout="docs" data-theme="system"
       data-docs-base="/docs/" data-locale="en">
    <a href="#content" data-component="skip-link">Skip to content</a>

    <header data-component="topbar">                 <!-- ≤960 only -->
      <a href="/" data-slot="logo">…</a>
      <div data-component="docs-lockup" inline="topbar">DOCS ⌄</div>
      <button data-slot="search-button" data-search-open>⌕</button>
      <a data-component="github-link">…</a>
    </header>

    <div data-slot="frame">                           <!-- the sticky frame -->
      <aside data-component="sidebar" data-section-nav>
        <div data-component="docs-lockup" inline="sidebar">DOCS ⌄</div>
        <a href="/" data-slot="logo">…</a>
        <div data-component="section-nav">
          <button data-slot="section-toggle">[-] Intro ⌄</button>     <!-- ≤960 -->
          <div data-slot="section-body">
            <nav data-component="docs-nav">
              <div data-slot="group">
                <span data-slot="group-title">CONFIGURE</span>
                <ul>
                  <li><a href="/docs/agents/" aria-current="page">[ ]<span data-slot="label">Agents</span></a></li>
                </ul>
              </div>
            </nav>
          </div>
        </div>
      </aside>

      <details data-component="contents-menu">…</details>  <!-- ≤960 -->
      <a data-component="github-link" owner="corner">…</a>

      <main data-component="content" id="content" tabindex="-1">
        <div data-slot="page">
          <article data-component="docs-article">
            <h1>Agents</h1>
            …MDX…
            <footer data-slot="article-footer">
              <nav data-component="pagination">Previous / Next</nav>
              <p data-component="edit-link">Edit this page · Copy as Markdown</p>
            </footer>
          </article>
        </div>
      </main>

      <aside data-component="aside" aria-label="On this page">
        <div data-component="docs-aside">
          <button data-slot="search">Search <kbd>⌘K</kbd></button>
          <nav data-component="on-this-page">CONTENTS · …</nav>
        </div>
      </aside>
    </div>

    <footer data-component="site-footer" data-layout="list">…</footer>
    <dialog data-search-dialog>…</dialog>
  </div>
</body>
```

### 3.1 The frame is what makes it feel stable

`[data-slot="frame"]` is a grid whose rows end where the footer begins. Both rails are
`position: sticky; height: 100dvh` inside it, so:

- they stay while the article scrolls;
- at the end of the document they scroll away with it, so the footer arrives *below* them rather
  than sliding under them;
- the aside is `height: auto; max-height: 100dvh` — a short rail releases early instead of hanging
  on an empty column.

The sidebar's nav is its own scroll box (`scrollbar-width: none`), padded inside so its inset sits
outside the scroll area, and it only takes the wheel when it actually overflows (`data-scrolls`).

### 3.2 The content line (do not skip this)

Three separate elements must land on the same line, `--content-top` (84px) from the top:

1. the left nav's **first item's text top**,
2. the article's **h1 cap top**,
3. the right rail's **first item** (the search trigger).

This is achieved with:

```css
[data-component="docs-nav"] { margin-top: calc(0.3253em - 15px); }   /* mono cap offset */
[data-component="docs-article"] h1 { margin: 0 0 1.5rem; text-box: trim-start cap alphabetic; }
[data-component="aside"] { padding-block: var(--content-top) var(--edge); }
```

If you port only one alignment rule, port this one. Without it the three columns feel "assembled";
with it the page looks drawn.

### 3.3 The logo row

- Fixed logo mark at `top: --top; left: --edge`; its box is `--logo-height` tall and 4:5 wide.
- The **DOCS lockup** sits beside it: `position: absolute; top: --top; inset-inline-start:
  calc(--edge + logo-box + 12px - 6px)`, so the word's ink, not its padding, starts 12px after the
  logo.
- The lockup is `OpenTUI Mono Bold 15px`, uppercase, with the version ("V1") in regular weight and
  `--text-weak` after a `/` separator in `--text-weaker`.
- Split form (default): the word is a link to the section home, and a 10px chevron *is its own
  button* for the section/version menu. The chevron flips instantly on open; the two segments share
  hover/press fills, and hovering the chevron fills the word at 50% so they read as one control.
- Segment hit areas are 32px tall on desktop, 44px on touch, drawn with a transparent `::before` so
  the visual fill stays the logo's height.

### 3.4 Where the article begins

`main` has no top padding; the article starts at the top of the frame, and the h1's cap is trimmed
onto the content line. The article column ends 72px before the aside, giving the rail air without a
visible divider.

---

## 4. Left navigation (the bracket list)

Anatomy: **section → groups → items**, one group per sidebar block, no disclosure triangles at
desktop (everything is visible and the list scrolls).

```
┌─ DOCS ⌄
│
│  Intro              ← ungrouped first group (no title)
│  Config
│  Migrate from V1
│
│  CONFIGURE          ← group title: 12px mono, uppercase, 0.04em tracking, --text-muted
│  [ ] Agents         ← idle: marker --nav-marker, label --text-weak
│  [-] Models         ← current: marker + label --text-strong, label gets the 0.2px stroke
│  [ ] Skills         ← hover: same as current, colour transition 150ms
```

Specs:

| Property | Value |
|---|---|
| type | `--font-mono`, `--mono-size` (15px), `line-height: 20px` |
| item gap | `10px` between `li`s |
| marker | literal `[ ]` box, `[-]` when current; the box is a flex cell so `[` and `]` stay aligned |
| marker→label gap | `0.625rem` |
| item padding | `padding-block: 5px; margin-block: -5px` (hit area without moving text) |
| group title | `--fs-micro`, uppercase, `0.04em`, `--text-muted`, `margin-bottom: 0.75rem`, offset by `--bracket-bearing` |
| group gap | `2rem` |
| focus | `outline: 2px solid var(--link); outline-offset: 2px` |
| edge fade | `mask-image` 2.5rem gradient at top and/or bottom while items pass under the logo row |
| scroll | own scroll box, hidden scrollbar, `overscroll-behavior: contain` when scrollable |

The `[-]` on the current page is the whole "you are here" signal — there is no coloured background,
no bold block, no left bar in the nav. Restraint is the point. (A bar-on-left alternative exists as
a variant in `docs-variants.css`; it is not the default.)

### 4.1 ≤960: the nav becomes two sticky rows

The three desktop columns collapse into a stack of sticky bars, each exactly one joining hairline:

1. **Top bar** — 56px: logo, DOCS lockup, search button (44px), GitHub mark. The bar's own hairline
   is removed because the section row below draws it.
2. **Section row** — sticky under the top bar, edge-to-edge, one 1px line above and below. It shows
   the current page **as the nav marks it** (`[-] Intro`) with a chevron, and opens a full-width
   list of the section that scrolls when taller than the window. Its press fill and the open list
   bleach to the screen edges (the row is widened by `2 * --edge` and padded back in).
3. **Contents bar** — sticky under the section row, its top line shared with the row's bottom line.
   Collapsed, it names the **section currently being read**; the label swaps in place as you scroll
   (the outgoing word is absolutely positioned over the incoming one, both clipped to one line,
   each ending in `…`). Open, it lists h2/h3.

Anchor jumps below the bars use `scroll-margin-top: calc(var(--contents-top) + 1rem)`.

---

## 5. Right rail: search over contents

The rail is two things, stacked with a 2rem gap, pinning at `--content-top`.

### 5.1 Search trigger

A text button, not an input: `SEARCH` + `<kbd>⌘K</kbd>`, mono at `--mono-size`,
`--text-weak`, turning `--text-strong` on hover, 150ms. Clicking (or `⌘K`, `Ctrl+K`, `/`) opens the
dialog. On phones the same action is a 44×44 icon button in the top bar, before the GitHub mark.

### 5.2 Contents: the pipe rail

```
CONTENTS            ← 12px mono uppercase, 0.04em, --text-muted (matches "CONFIGURE")

  Installing        ← idle: no pipe, --text-weak
│ Configuration     ← current: 2px pipe --text-strong, label --text-strong
  Providers         ← hover: 2px pipe --border-strong, label --text
```

| Property | Value |
|---|---|
| gutter | `--rail-gutter: 14px` = 2px pipe + 12px gap |
| item line box | 20px; pitch 30px (20px + 10px gap), same as the left nav |
| pipe | `::before` on the first line, fixed 20px tall, at the rail's left edge at every level |
| h3 nesting | indented one step, pipe still at the rail's edge |
| states | instant colour change (no transition), like legal tabs |
| long pages | the list scrolls inside the rail and keeps the current heading in view |

Contents only includes **h2 and h3** (`depth === 2 || depth === 3`), generated from the rendered
headings, and the page's `h1` is never in it.

---

## 6. Search

A `⌘K` palette, not a page.

| Aspect | Spec |
|---|---|
| placement | centred, `top: 16vh`, `width: min(640px, 100vw - 2rem)`, `max-height: min(480px, 76vh)` |
| surface | `--popover-bg` + 1px ring + four tight shadows; square corners |
| backdrop | `black` at 24% (light) / 56% (dark), optional blur |
| field | 3rem tall, 0.875rem inline padding, 1px bottom border, input at `--fs-input` (16px on touch) |
| results | grouped by page, 0.5rem rows, 2px bar on the active row, `mark` in `--link` |
| empty state | one line, with a link to browse the docs |
| keyboard | `/`, `⌘K`, `Ctrl+K` open; arrows move; `Enter` goes; `Esc` closes |
| motion | 150ms in (`opacity` + 4px translate or 0.98 scale), 120ms out (fade only) |
| reduced motion | fade only |
| phones (≤640) | full-screen sheet from the top, `Cancel` in `--link` at `--fs-ui`, rows ≥44px |
| a11y | focus trapped, `aria-haspopup="dialog"`, results in a listbox, `aria-keyshortcuts` on the trigger |

Empty panel behaviour: with nothing typed the panel is **just the field** — no divider, no empty
list. The results list fades and slides in only when a query fills it, so growth reads as one
motion. When the dialog closes, the V1 bottom bar (if present) is hidden first so nothing sits half
under it.

---

## 7. Code

Code is the most designed thing on the page. Every code surface is a **plate**: 1px border, a
header row in the page tone, a body one step lighter, and a copy control that is always visible.

```
┌───────────────────────────────────────────────┐
│ ⧉ opencode.json                    Copy      │  header 2.5rem, --code-head, 12px mono label
├───────────────────────────────────────────────┤
│ {                                             │  body --code-body, padding 1rem
│   "model": "…"                                │  13px/1.6 mono, horizontal scroll
│ }                                             │
└───────────────────────────────────────────────┘
```

| Token | Value |
|---|---|
| `--code-body` | `grey-2` |
| `--code-head` | `grey-1` (header is the *darker* of the two in both themes, like Vercel) |
| `--code-border` | `grey-5` (decorative ~1.3:1) |
| `--code-text` | `grey-11` |
| `--code-label` | `grey-8` |
| header | `display: flex; justify-content: space-between; height: 2.5rem; padding-inline: 1rem 0.375rem; border-bottom: 1px` |
| label | `inline-flex; gap: .5rem; 12px/1 mono; ellipsis`; 16px mark at 1.5px stroke before it |
| marks | file (page), folder (tree), terminal window, prompt, titlebar — inline SVG masks, square joins |
| copy | text-only `Copy`, 2.5rem tall, `padding: 0 .75rem`, `margin-inline-end: -0.375rem`; swaps to `Copied` **inside a one-cell grid** so the width never changes |
| body | `padding: 1rem; overflow-x: auto; font-size: --fs-meta; line-height: 1.6; white-space: pre` |
| focus | `outline: 2px solid var(--link); outline-offset: -2px` (inside, because it scrolls) |

Variants, all on the same plate:

- **Titled** — `figure` with a caption becomes the header label (file name / `>_ Terminal`).
- **Tabs** — `CodeTabs`: a tab row that scrolls sideways under a pinned copy button; each panel
  scrolls its own code. Panels are `role="tab"`; arrow keys move between them.
- **Line numbers** — 3rem right-aligned gutter in `--code-number`; `data-mark` rows tint with
  `--code-mark-tint` and a 2px inset bar; non-focused lines step back to `--code-label`
  (still 4.5:1) so focus reads.
- **Diff** — `+`/`-` in a 2rem gutter, row tints, 2px inset bars in `--code-add`/`--code-del`.
- **Terminal** — dark in both themes (an "ink" plate) for command/output blocks.
- **File tree** — folder/file marks, one line per entry, em-dash tree marks.
- **Collapse** — folded lines read as one block when open; the expand button is 12px mono in
  `--code-label`, hover `--code-text`, focus ring inside.
- **Config / CLI / API** — reference plates with the same header grammar (label left, copy right)
  and a ruled section per option/flag/endpoint.

Inside a tinted callout, code and tables **blend with the callout's tint** (`mix-blend-mode`) so no
flat grey rectangle appears inside a coloured panel.

---

## 8. Content components

All of them share one vocabulary: hairline rules, mono micro-labels in uppercase with slight
tracking, square corners, neutral greys, a 2px pipe or bar where a state needs marking.

| Component | Design |
|---|---|
| **Callout** `note/tip/caution/danger` | Tinted surface, 1px hairline, no radius. A mono micro-label in the header position (uppercase, tracked) and a 2px pipe on the inline-start edge for severity. Nested code and tables inherit the tint rather than sitting on grey. |
| **Steps** | Numbered list on a vertical rule; the number sits in the rule, mono, and never wraps the text. Steps are full-column blocks, so their body text is not capped to the prose measure. |
| **Cards / CardGroup** | Plates with a ruled header row and a hairline between cards; no shadow, no lift, hover changes border/tint only. Grid for groups, single column on phones. |
| **Tables** | Full column width, wrapped in a horizontal scroll container (`role="region"`, `tabindex="0"` so keyboards can scroll). Header row in `--ref-head` = 12px uppercase mono in ink with the fake medium stroke. 1px row rules in `--border`; no zebra striping. Wide tables scroll rather than widen the page. |
| **Details / FAQ** | `details > summary` with a 12×1px plus that becomes a minus (`::after` rotated 90°, `scale: 0 1` when open, 200ms). Summary gets a 44px hit area; the rule under a closed item is removed. |
| **Badges** | 12px mono uppercase, 1px border, square, no fill by default. |
| **Images / video** | 1px `--border` frame, no radius, `max-width: 100%`, `height: auto`, 1.5rem below. Captions in `--fs-meta`, `--text-weak`. |
| **API operation** | One `<details>` per endpoint: header row is the summary with method, path and a plus; `operation-id` in mono micro; schema types are links in code text; the whole card opens in place. |
| **Pagination** | Two columns, `PREVIOUS`/`NEXT` in mono micro above the title, hairline rule on top only, no arrows-as-buttons. |
| **Edit link + Copy as Markdown** | One row at the article's end: `Edit this page ↗` on the start edge, `Copy as Markdown` pushed to the end edge. The copy control keeps the width of its longest label (`idle`/`copied`/`failed` stacked in one grid cell) so nothing moves. |
| **Version notice (V1)** | A dark bar in the logo row, centred on the logo, as wide as the article: `V1` badge, a sentence that ellipsizes, and a link with a chevron that nudges 2px on hover. On phones it becomes a dark strip on the screen's bottom edge, extending under the home indicator. |

---

## 9. Interaction and states

| Element | Idle | Hover | Active/press | Current | Focus |
|---|---|---|---|---|---|
| nav item | `--text-weak` | `--text-strong` (150ms) | same | `--text-strong` + stroke, `[-]` | 2px ring, offset 2px |
| contents item | `--text-weak`, no pipe | `--text`, 2px `--border-strong` pipe | — | `--text-strong`, 2px `--text-strong` pipe | ring |
| prose link | underlined, body colour | `--link` | `--link` | — | ring |
| code copy | `--code-label` | `--code-text` (150ms) | `--code-text` | — | ring inside |
| menu row | — | `--menu-hover` tint + 2px `--menu-hint` bar | `--menu-press` | 2px `--menu-bar` | focus moves the highlight |
| lockup segment | — | 50% of `--logo-inner` | full `--logo-inner` | open = pressed | 2px ring |
| segmented control | — | text `--text-strong` | — | `--bg-weak` fill | ring |

Principles:

- **Only one highlighted row exists at a time.** Menus have no per-row fade, so a row being left
  never lingers beside the next; a resting pointer yields to keyboard focus.
- **Hover is a colour change, not a movement.** No translate, no scale on nav, tables or cards.
  The only scale in the system is the 0.985 press on large buttons.
- **Pressed states persist into "open"**, so a toggled control still looks engaged.
- **Nothing is hidden behind hover.** Copy buttons are always visible; the copy action is not a
  hover reveal.

### 9.1 Motion

```
--ease-out: cubic-bezier(0.23, 1, 0.32, 1);
```

| Motion | Duration |
|---|---|
| colour / opacity state changes | 150ms (100ms for the notice link) |
| menu open | 150ms transform + opacity from the trigger's origin |
| search in / out | 150ms / 120ms |
| plus→minus | 200ms `scale` |
| page navigation | cross-document `@view-transition { navigation: auto }`: the shell stays put, the document content fades |
| chevron nudge | 150ms `translate: 2px 0` (mirrored in RTL) |

Only `transform`, `translate`, `scale` and `opacity` are animated. Everything is wrapped in
`@media (prefers-reduced-motion: reduce)` and degrades to an instant change or a plain fade. No
animation runs on load, and no scroll position is restored or animated by script.

---

## 10. Accessibility

Non-negotiables in this design:

- **Contrast**: 4.5:1 for all text on every surface it can appear on (including raised surfaces and
  hover fills); 3:1 for marks, pipes, borders that carry state, and icons.
- **Focus**: a 2px `--link` ring with 2px offset, visible on every interactive element, including
  `pre` and table scroll containers (offset `-2px` when the element clips).
- **Skip link** to `#content`; `main` has `tabindex="-1"` so the jump moves focus.
- **Landmarks**: `header`, `aside` + `aria-label` for the section nav, `main#content`, `aside` +
  `aria-label` for the page rail, `footer`, `nav` inside each list.
- **Current page** is `aria-current="page"`, never colour alone (`[-]` marker + stroke + colour).
- **Disclosure** uses real `<button aria-expanded aria-controls>` and `<details>`; menus use
  `role="menuitem"`, `aria-haspopup`, `aria-expanded`.
- **Tap targets** are 44px on coarse pointers and on phones, even when the visible affordance is
  20px (extended with a transparent `::before`/`::after`).
- **Search** is a dialog with a focus trap, a labelled input, results as options with `mark`
  highlighting, and `Esc`/`Cancel` that returns focus to the trigger.
- **Code** is keyboard-scrollable; the copy button is a real button with an `aria-live` confirmation.
- **Motion** respects `prefers-reduced-motion`; **transparency** respects
  `prefers-reduced-transparency` (no blur, solid panels).
- **Zoom**: layout survives 200% text zoom because type is in `px`/`em` on a fluid grid and nothing
  is measured in script for layout.
- **No colour-only diff**: `+`/`-` signs accompany the tints.
- **Images** carry alt text; decorative marks are `aria-hidden`.

---

## 11. Internationalisation and RTL

- 17 locales; Arabic is RTL (`<html dir="rtl">`), and the whole layout uses **logical properties**
  (`inset-inline-start`, `margin-inline`, `padding-block`) so it mirrors without a second stylesheet.
- Directional icons (chevrons, arrows) are mirrored with `scale: -1 1` and their hover nudge flips
  sign.
- Arabic and Thai get their own faces (`OC Arabic`, `OC Thai`) inserted **before** the Latin
  fallbacks in both stacks, so script runs never fall back to a Courier with monospaced Arabic.
- Copy lives in one dictionary (`src/i18n/en.ts`) with placeholders (`{{section}}`) filled at
  runtime for client strings; the server renders the page's language.
- No text is baked into an image; no fixed-width label boxes except where a label is swapped in
  place (copy button, contents bar), and there the widest translation reserves the space.
- Code is `<bdi dir="ltr">` / `dir="ltr"` inside RTL prose.

---

## 12. Content and copy rules

These shape the page more than any CSS.

- **One `h1` per page**, and it is the page's title, not a sentence.
- Headings are **noun phrases**: "Configuration", "Providers", "Troubleshooting" — not questions.
- **No colons in copy.** Rewrite instead ("Set the model in `opencode.json`, then…").
- Sentence case for body, **uppercase only for micro-labels** (group titles, `CONTENTS`, `COPY`).
- The product is "an open source coding agent" — no adjective stacking, no "revolutionary".
- Second person, imperative for procedures; present tense for behaviour.
- Code samples are complete enough to run; every block has a language for highlighting and, where
  it is a file, a `title=` so the header can label it.
- Warnings are earned: `Caution` for data loss, `Note` for a surprise, nothing else.
- **Never put raw user data in examples.** Use obviously synthetic values.

Typographic details worth copying: `text-wrap: pretty` on headings, `letter-spacing: -0.02em` on the
h1 only, no letter-spacing on body, `text-underline-offset: 0.2em` on links, `font-variant-numeric`
left default (the mono face handles numerals).

---

## 13. How it is built (and why that matters to the design)

- **Static HTML per page**, prerendered at build. No client router. Navigation is a normal link.
- **Speculation rules**: `prerender` with `eagerness: "moderate"` for `/docs/*`, so resting a pointer
  on a link preloads the page.
- **Cross-document view transitions** (`@view-transition { navigation: auto }`), so the shell and
  the rails stay put and only the content fades.
- **Theme before first paint**: a tiny inline script reads the saved theme (and migrates an old
  `docs-theme` key), sets `data-theme` on the root, and the `<meta name="theme-color">` matches
  (`#fbfbfb` / `#0c0c0c`).
- **Two font preloads** only (Inter Latin, mono Latin), `crossorigin`, `font-display: swap` with
  metric-compatible stand-ins, so the swap does not shift lines.
- **Islands**: search palette, copy buttons, scroll-spy for contents, the contents label swap, the
  theme cycle, the status bars. Everything else is static.
- **CLS is 0** as a constraint: every async surface (copy label, contents bar label, V1 notice,
  status) reserves its space in the initial HTML.
- **CSS**: one stylesheet per docs set, built with the site's production pipeline; only the chosen
  component variants ship. Logical properties throughout, `@property` for anything that animates a
  colour, no runtime CSS-in-JS.
- **Markdown twins**: each page links `<link rel="alternate" type="text/markdown">` and a "Copy as
  Markdown" action — a docs page is data as well as a page.
- **Pagefind** indexes the article (`data-pagefind-body`), with `title` and `section` metadata, and
  `data-pagefind-ignore` on pagination/edit rows. Sections are cluster keys, so search results are
  grouped by section.

### 13.1 Information architecture

Five top-level sections, each its own nav set, its own mount path and its own search index:

| Section | Path | Landing |
|---|---|---|
| Docs | `/docs/` | `/docs/` |
| CLI | `/docs/cli/` | `/docs/cli/` |
| Build | `/docs/build/` | `/docs/build/` |
| API | `/docs/api/` | `/docs/api/` |
| Console | `/docs/console/` | `/docs/console/` |

Inside a section, groups are ordered explicitly in one file (`lib/navigation.ts`) — not alphabetised,
not derived from filenames. A section's own title as a group title is dropped (the lockup already
says it). Pagination stays inside the current section. URL = file path (`content/cli/keybinds.mdx`
→ `/docs/cli/keybinds/`), and other repositories read those paths, so paths are an API.

Frontmatter is small and validated at build (a bad page fails the build):

```yaml
title: string
description?: string
noindex?: boolean
tableOfContents?: boolean | { minHeadingLevel?: 1..6, maxHeadingLevel?: 1..6 }
```

The V1 docs live in their old Starlight MDX in 18 languages, are `noindex`, and carry a notice that
links the latest docs. The shell is shared; the content model is not.

---

## 14. Applying this to this repository (MkDocs Material → v2)

The current site is MkDocs Material with a "pine + ink" theme
(`docs/assets/extra.css`, `mkdocs.yml`): IBM Plex Sans + JetBrains Mono, 8/12px radii, green accent,
rounded admonitions. To move to the opencode layout, keep Material's machinery and replace the
surface.

### 14.1 What to keep, what to replace

| Keep (Material does it well) | Replace |
|---|---|
| `search` plugin + suggest/highlight | rounded search **modal** → square palette, ⌘K |
| `toc.follow` + `navigation.tracking` | the rail's look → pipe rail, h2/h3 only |
| `content.code.copy` / `select` | the copy button → text label in a ruled header |
| `pymdownx.tabbed`, `superfences` | tab look → ruled tab row on the code plate |
| `admonition`, `pymdownx.details` | rounded tiles → tinted plates with mono labels |
| `navigation.sections`, `navigation.indexes` | sidebar ordering → explicit, group titles in mono caps |
| `mkdocstrings` API pages | output → API operation cards, mono micro labels |
| palette toggle | theme → `light-dark()` pairs, no second stylesheet |

### 14.2 Concrete config changes

```yaml
theme:
  name: material
  font: false                      # load Inter + a mono yourself; do not let Material add Roboto
  logo: assets/logo.svg
  favicon: assets/favicon.svg
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: custom
      accent: custom
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: custom
      accent: custom
  features:
    - navigation.sections           # keep: groups become sidebar groups
    - navigation.indexes
    - navigation.tracking           # keep: scroll-spy writes the URL
    - navigation.top
    - navigation.footer             # keep: prev/next, but restyle to the hairline rule
    - toc.follow                    # keep: current heading highlighted
    - search.suggest
    - search.highlight
    - content.code.copy
    - content.code.select
    - content.action.edit
    - content.tabs.link
    - content.tooltips
```

Add `overrides/main.html` with `{% extends "base.html" %}` for the small structural things Material
does not expose:

1. a **fixed logo row** with the `DOCS` lockup (or your product word) beside the logo;
2. the **section name** in the mobile bar (Material puts a hamburger there — either keep the
   hamburger and style it as the section row, or set `navigation.tabs` and accept two rows);
3. a `⌘K` hint inside the search field's placeholder/`<kbd>`;
4. a `Skip to content` link if your Material version does not ship one.

### 14.3 Token layer (drop-in starting point)

```css
:root {
  /* greys: identical roles in both themes */
  --grey-1:  light-dark(#fbfbfb, #0c0c0c);
  --grey-2:  light-dark(#ffffff, #161616);
  --grey-3:  light-dark(#f5f5f5, #1a1a1a);
  --grey-4:  light-dark(#eeeeee, #242424);
  --grey-5:  light-dark(#e0e0e0, #2e2e2e);
  --grey-6:  light-dark(#d2d2d2, #4b4b4b);
  --grey-7:  light-dark(#888888, #6a6a6a);
  --grey-8:  light-dark(#6b6b6b, #8f8f8f);
  --grey-9:  light-dark(#5c5c5c, #aeaeae);
  --grey-10: light-dark(#3a3a3a, #dbdbdb);
  --grey-11: light-dark(#161616, #fafafa);

  --bg: var(--grey-1);
  --surface: var(--grey-2);
  --fill: var(--grey-3);
  --hover: var(--grey-4);
  --border: var(--grey-5);
  --border-strong: var(--grey-6);
  --text: var(--grey-9);
  --text-weak: var(--grey-8);
  --text-strong: var(--grey-11);
  --link: light-dark(#3b5cf6, #4f8bff);

  --font-mono: ui-monospace, "JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace;
  --font-sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;

  --fs-micro: 12px;
  --fs-meta: 13px;
  --fs-small: 14px;
  --fs-ui: 15px;
  --fs-read: 16px;
  --fs-title: 17px;
  --fs-h1: clamp(28px, 25px + 0.5vw, 32px);

  --page-max: 1728px;
  --sidebar-width: 14.75rem;
  --gutter: 1rem;
  --edge: 1.5rem;
  --aside-width: calc((min(100vw, var(--page-max)) - var(--sidebar-width)
                       - 4 * var(--gutter) - var(--edge)) / 4 + var(--edge));
  --content-top: 84px;             /* = edge + logo-height + edge + 8px at default edge */
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);

  --measure: 42em;                 /* prose cap, ~90ch of Inter */
}

@media (max-width: 60rem) {
  :root { --fs-meta: 14px; --fs-small: 15px; --fs-ui: 16px;
          --fs-read: 17px; --fs-title: 18px; --fs-input: 16px; }
}

/* Material surface overrides */
[data-md-color-scheme] {
  --md-default-bg-color: var(--bg);
  --md-default-fg-color: var(--text);
  --md-default-fg-color--light: var(--text-weak);
  --md-default-fg-color--lighter: var(--text-weak);
  --md-default-fg-color--lightest: var(--border);
  --md-typeset-color: var(--text);
  --md-typeset-a-color: var(--text-strong);
  --md-code-bg-color: var(--surface);
  --md-code-fg-color: var(--text-strong);
  --md-code-hl-color: color-mix(in srgb, var(--link) 10%, transparent);
  --md-primary-fg-color: var(--bg);
  --md-accent-fg-color: var(--link);
  --md-typeset-table-color: var(--border);
  --md-typeset-kbd-color: var(--surface);
  --md-text-font: var(--font-sans);
  --md-code-font: var(--font-mono);
}

/* Square everything. This single block removes 90% of the "Material look". */
:is(.md-typeset pre, .md-typeset code, .md-typeset .admonition,
    .md-typeset details, .md-typeset table, .md-typeset img,
    .md-search__form, .md-search__output, .md-button, .md-tabs,
    .md-nav__link, .md-typeset .tabbed-set) { border-radius: 0 !important; }

.md-header, .md-tabs, .md-footer { box-shadow: none !important; }
.md-header { border-bottom: 1px solid var(--border); }

/* Type: mono chrome, Inter prose. */
.md-header__title, .md-nav__title, .md-nav__link, .md-footer,
.md-typeset h1, .md-typeset h2, .md-typeset h3,
.md-typeset h4, .md-typeset h5, .md-typeset h6,
.md-search__input, .md-typeset .admonition-title { font-family: var(--font-mono); }

.md-typeset { font-size: var(--fs-read); line-height: 1.6; color: var(--text); }
.md-typeset h1 { font-weight: 400; font-size: var(--fs-h1); line-height: 1.15;
                 letter-spacing: -0.02em; color: var(--text-strong); }
.md-typeset h2 { font-weight: 400; font-size: var(--fs-title); line-height: 1.35;
                 color: var(--text-strong); }
.md-typeset :is(h3, h4, h5, h6) { font-weight: 700; line-height: 1.5; color: var(--text-strong); }
.md-typeset p, .md-typeset li { max-width: var(--measure); }

/* Prose links: underlined, blue only on interaction. */
.md-typeset a { color: inherit; text-decoration: underline; text-underline-offset: .2em; }
.md-typeset a:hover, .md-typeset a:focus-visible, .md-typeset a:active { color: var(--link); }

/* Focus ring, everywhere. */
:is(a, button, summary, input, select, [tabindex]):focus-visible {
  outline: 2px solid var(--link); outline-offset: 2px;
}

/* Tables: ruled, no zebra. */
.md-typeset table:not([class]) { border: 1px solid var(--border); }
.md-typeset table:not([class]) th {
  font: 400 var(--fs-micro)/1.4 var(--font-mono);
  text-transform: uppercase; letter-spacing: .04em;
  color: var(--text-strong); background: var(--bg);
  border-bottom: 1px solid var(--border-strong);
}
.md-typeset table:not([class]) td { border-top: 1px solid var(--border); }

/* Code plate with a ruled header: put the label in the copy button's row. */
.md-typeset pre > code { font-size: var(--fs-meta); line-height: 1.6; padding: 1rem; }
.md-typeset .highlight { border: 1px solid var(--border); background: var(--surface); }
.md-typeset .highlighttable .linenodiv { color: var(--text-weak); }
.md-clipboard { color: var(--text-weak); }
.md-clipboard:hover { color: var(--text-strong); }

/* Admonitions as callout plates. */
.md-typeset .admonition, .md-typeset details {
  border: 1px solid var(--border); border-left-width: 2px;
  background: var(--fill); box-shadow: none;
}
.md-typeset .admonition-title, .md-typeset summary {
  font: 400 var(--fs-micro)/1.4 var(--font-mono);
  text-transform: uppercase; letter-spacing: .06em;
  background: transparent;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
```

### 14.4 Structural work Material will not do for you

1. **Three-column frame with sticky rails that release before the footer.** Material's sidebars are
   already `position: sticky`, but they are sticky to the viewport, not to a frame that ends at the
   footer. Wrap the main area (`.md-main__inner`) in a grid with
   `grid-template-columns: var(--sidebar-width) minmax(0,1fr) var(--aside-width)` and give the rails
   `height: 100dvh`, `align-self: start`, inside a wrapper that ends where the footer begins.
2. **The content line.** Apply `margin-top: calc(0.3253em - 15px)` to `.md-nav--primary > .md-nav__list`
   and `text-box: trim-start cap` to `.md-typeset h1` so the nav, title and TOC align at 84px.
3. **The 84px top offset.** Material's header is 48px and not fixed on desktop. To match, either make
   the header fixed with `--content-top` padding on the rails, or drop the header on docs pages and
   pin only the logo + product word in the top-left corner.
4. **Bracket markers.** Use `.md-nav__link::before { content: "[ ]"; }` with
   `[aria-current="page"]::before { content: "[-]"; }` and `gap: .625rem`, or generate the marker in
   the template. Material's `::before` is also used by its expand icons; scope carefully.
5. **Pipe rail.** `.md-nav--secondary .md-nav__link::before { content:""; width:2px; height:20px;
   background: transparent; }` with current → `--text-strong`, hover → `--border-strong`, and
   `padding-inline-start: 14px` on the items.
6. **Contents label.** Material's TOC has an "On this page" title; set it to `CONTENTS` in mono
   micro uppercase, or override the `.md-nav__title` text.
7. **Search as a palette.** Material's search is a full-width overlay. To get the 640px centred
   panel: `.md-search__inner { max-width: 640px; margin: 16vh auto 0; }`,
   `.md-search__form { border: 1px solid var(--border); box-shadow: <ring + 4 tight shadows>; }`,
   remove `border-radius`, and hide the results divider until there is a query
   (`.md-search__output:empty { display: none; }` plus a `:has()` rule on the form if needed).
8. **Mobile bars.** Material gives you a header + optional tabs. The opencode layout wants **two**
   sticky rows with one shared hairline plus a contents bar. Simplest port: keep the header and add a
   `docs-contents` bar in `overrides/main.html`, sticky at `top: 48px` (or your header height),
   with the current heading name swapped in by `extra.js` and a `<details>` list beneath.
9. **44px targets.** Material's touch targets are 48px in the drawer but 20px in the TOC. Add
   `@media (pointer: coarse) { .md-nav__link, .md-typeset summary { min-height: 2.75rem; display: flex; align-items: center; } }`.
10. **Skip the rounded logo/wordmark treatment.** Square the logo box and set the product word in
    mono bold caps immediately after it; that single change does most of the "this is a different
    site" work.

### 14.5 Mapping the current content to the new components

| Current | New |
|---|---|
| `!!! note` / `warning` admonitions | callout plate, mono uppercase label, 2px inline-start pipe |
| `=== "pip"` tabbed blocks with `pip install` | code plate, ruled tab row, pinned copy |
| `mkdocstrings` class/function pages | API operation cards, mono micro signatures, plus-to-expand |
| `pymdownx.details` FAQ | `<details>` with the 12×1px plus/minus, 44px summary |
| the pine/pine-soft palette | 11-step grey scale + link blue; pine survives only as the logo mark |
| `--udc-radius: 8px` / `12px` | `0` |
| Material's "On this page" | `CONTENTS` pipe rail, h2/h3 only |
| GitHub/PyPI icon links | footer bracket list (`[ ] GitHub`) with an external arrow |
| `Copyright © 2026` | same, in mono micro, plus a status entry if you want parity |

---

## 15. Rebuild checklist

Work in this order; each step is visible on its own.

**Foundations**
- [ ] Replace the palette with the 11 greys + link blue; audit every text/background pair for 4.5:1.
- [ ] Set body text to Inter `--fs-read`/1.6, chrome to a mono at `--fs-ui`; headings h1–h6 to mono.
- [ ] Set `border-radius: 0` globally, remove all content shadows, replace card edges with 1px borders.
- [ ] Add the type step at 960px and the 44px touch floor.

**Shell**
- [ ] Build the 1728px-capped, `--page-offset`-centred root.
- [ ] Build the three-column frame (sidebar / article / aside) with rails sticky to a frame that ends
      at the footer.
- [ ] Land the logo, nav first item, h1 cap and rail first item on the 84px content line.
- [ ] Add the edge masks on the left nav and the hidden-scrollbar scroll boxes.

**Navigation**
- [ ] Bracket markers `[ ]` / `[-]`, 20px lines on a 30px pitch, mono group titles in caps.
- [ ] Contents rail with 2px pipes, current heading tracked on scroll.
- [ ] ≤960: top bar, section row, contents bar — one hairline per join, label swap on scroll.

**Content**
- [ ] Code plate: ruled header, inline-start label with a 16px mark, always-visible Copy with
      no-width-change states, token colours at 4.5:1.
- [ ] Tabs, line numbers, diff, terminal, file tree, collapse on the same plate.
- [ ] Tables: full width, scroll container, mono uppercase head, 1px rules, no zebra.
- [ ] Callouts, steps, cards, details, badges, images with the 1px frame.
- [ ] Pagination, edit link, copy-as-markdown, footer bracket list.

**Behaviour**
- [ ] `⌘K` palette with the empty-panel rule, focus trap, `Esc`, phone sheet.
- [ ] Copy buttons with the one-cell label swap and an `aria-live` confirmation.
- [ ] Theme before first paint; `theme-color` meta; two font preloads; CLS 0 verified.
- [ ] View transitions + speculative prerender (or, on MkDocs, at least avoid a white flash).
- [ ] Reduced motion and reduced transparency paths verified.

**Verification**
- [ ] Lighthouse on a long page (e.g. config reference) and a short one: CLS 0, no blocked paint.
- [ ] Keyboard-only pass: skip link, nav, contents, code scroll, copy, search, pagination.
- [ ] 200% zoom and 320px width.
- [ ] Both themes at every contrast pair; RTL pass with `dir="rtl"` on the root.
- [ ] Print a page: rails hidden, article readable, code not clipped.

---

## 16. Anti-patterns (what this design refuses)

- Rounded cards, pills, floating shadows, glassmorphism, gradient text.
- A coloured sidebar background, an active item with a filled tint block, or "chip" navigation.
- Sans-serif page titles over mono body, or mono body text "for the terminal vibe".
- Hamburger menus on desktop; nav that scrolls away with the article.
- Hover-revealed copy buttons; copy confirmation that changes the button's width.
- A separate "on this page" boxed card, or a floating TOC that overlaps the footer.
- Images without a frame, tables that widen the page, code that scrolls the whole page.
- Scroll animations, reveal-on-scroll, parallax, animated counters.
- Two stylesheets for two themes; `prefers-color-scheme` decisions made in JS.
- Coloured callouts that are only differentiated by hue.
- A search that opens a page instead of a panel; a panel that hides results behind a divider.
- Copy with colons in headings, exclamation marks, or marketing adjectives.

---

## Appendix A — Token reference (copy-paste)

```css
:root {
  --page-max: 1728px;
  --page-width: min(100vw, var(--page-max));
  --page-offset: max(0px, (100vw - var(--page-max)) / 2);

  --grey-1:  light-dark(#fbfbfb, #0c0c0c);
  --grey-2:  light-dark(#ffffff, #161616);
  --grey-3:  light-dark(#f5f5f5, #1a1a1a);
  --grey-4:  light-dark(#eeeeee, #242424);
  --grey-5:  light-dark(#e0e0e0, #2e2e2e);
  --grey-6:  light-dark(#d2d2d2, #4b4b4b);
  --grey-7:  light-dark(#888888, #6a6a6a);
  --grey-8:  light-dark(#6b6b6b, #8f8f8f);
  --grey-9:  light-dark(#5c5c5c, #aeaeae);
  --grey-10: light-dark(#3a3a3a, #dbdbdb);
  --grey-11: light-dark(#161616, #fafafa);

  --bg: var(--grey-1);
  --bg-weak: var(--grey-3);
  --bg-weaker: var(--grey-4);
  --bg-strong: var(--grey-11);
  --text-strong: var(--grey-11);
  --text: var(--grey-9);
  --text-weak: var(--grey-8);
  --text-muted: var(--grey-8);
  --text-faint: var(--grey-7);
  --text-inverted: light-dark(#ffffff, #0c0c0c);
  --border: var(--grey-5);
  --border-strong: var(--grey-6);
  --link: light-dark(#3b5cf6, #4f8bff);
  --link-visited: light-dark(#6a4fd6, #4f8bff);
  --nav-marker: var(--text-faint);

  --popover-bg: var(--grey-2);
  --popover-text-weak: var(--grey-9);
  --popover-shadow:
    0 0 0 1px light-dark(rgb(0 0 0 / .10), rgb(255 255 255 / .10)),
    0 1px 1px light-dark(rgb(0 0 0 / .04), rgb(0 0 0 / .30)),
    0 2px 4px -1px light-dark(rgb(0 0 0 / .06), rgb(0 0 0 / .35)),
    0 6px 12px -4px light-dark(rgb(0 0 0 / .08), rgb(0 0 0 / .45));

  /* type */
  --fs-micro: 12px;  --fs-meta: 13px;  --fs-small: 14px;  --fs-ui: 15px;
  --fs-body: 15px;   --fs-read: 16px;  --fs-title: 17px;  --fs-large: 18px;
  --fs-lead: 18px;   --fs-h1: clamp(28px, 25px + .5vw, 32px);
  --fs-input: 14px;  --fs-display-max: 64px;
  --mono-size: var(--fs-ui);
  --measure: 33em;
  --title-stroke: .2px currentColor;

  /* shell */
  --sidebar-width: 14.75rem;
  --gutter: 1rem;
  --edge: 1.5rem;
  --top: var(--edge);
  --logo-height: 1.75rem;
  --logo-gap: calc(var(--top) + 8px);
  --content-top: calc(var(--top) + var(--logo-height) + var(--logo-gap));
  --topbar-height: 3.5rem;
  --phone-logo-height: 30px;
  --aside-width: calc((var(--page-width) - var(--sidebar-width)
                       - 4 * var(--gutter) - var(--edge)) / 4 + var(--edge));
  --rail-gutter: 14px;

  /* code */
  --code-body: var(--grey-2);
  --code-head: var(--grey-1);
  --code-border: var(--grey-5);
  --code-text: var(--grey-11);
  --code-label: var(--grey-8);
  --code-number: var(--grey-8);
  --code-mark: light-dark(#3b5cf6, #6b8fff);
  --code-mark-tint: light-dark(#eff2fe, #1e2637);
  --token-command: light-dark(#a64b14, #fab283);
  --token-flag: light-dark(#7a3fc4, #9d7cd8);
  --token-string: light-dark(#2b7a3d, #7fd88f);
  --token-operator: light-dark(#0f6e7a, #56b6c2);
  --token-output: var(--grey-8);

  /* motion */
  --ease-out: cubic-bezier(.23, 1, .32, 1);
  --search-duration: 150ms;
}

@media (max-width: 60rem) {
  :root {
    --fs-meta: 14px; --fs-small: 15px; --fs-ui: 16px; --fs-body: 17px;
    --fs-read: 17px; --fs-title: 18px; --fs-large: 19px; --fs-lead: 20px;
    --fs-input: 16px; --fs-display-max: 48px;
  }
}
```

## Appendix B — Reference measurements cheat sheet

| Thing | Value |
|---|---|
| page cap / centring | 1728px, `--page-offset` padding each side |
| sidebar | 236px (14.75rem) |
| gutters | 16px; page edge 24px |
| article → rail gutter | 2 × 16 + 40 = 72px |
| content line | 84px from top |
| rail pitch | 20px line, 10px gap |
| rail pipe | 2px, 14px total gutter |
| prose cap | 42 × 16px ≈ 672px (~90ch) |
| h1 | 28–32px mono, 1.15, −0.02em |
| h2 | 17px mono, 1.35, +0.2px stroke |
| body | 16px Inter, 1.6 |
| code | 13px mono, 1.6, 1rem padding |
| code header | 40px tall, 1px bottom border |
| code corner radius | 0 |
| nav item hit height | 30px (20 + 5 + 5) |
| touch target | 44px minimum |
| focus ring | 2px `--link`, ±2px offset |
| hover/state transition | 150ms |
| search panel | 640px wide, 16vh from top, 480px tall max |
| breakpoints | 1728 / 960 / 640 / coarse pointer |
| CLS budget | 0 |

---

*Source of truth: `anomalyco/opencode@dev`, `services/site` — `DESIGN.md`, `src/docs/AGENTS.md`,
`src/docs/styles/docs.css`, `src/docs/layouts/DocsLayout.tsx`, `src/docs/components/*`,
`src/docs/lib/navigation.ts`, `src/component/site/{site,docs-lockup,on-this-page,search-palette,docs-variants}.css`,
`src/style/token/*`. If the site changes, those files change first.*
