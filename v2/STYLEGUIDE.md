# v2 style guide

The rules this preview is built to, and the numbers behind them. Every value below was
either read from the reference stylesheets (`anomalyco/opencode`, `services/site`, branch
`dev` — see `reference/PIPELINE.md`) or measured in a browser against the built pages with
`tools/audit.html`. Where we deviate, the deviation is written down and justified.

Run it:

```bash
python3 v2/dev.py                   # rebuild on change and serve (recommended)
python3 v2/build.py                 # rebuild v2/site once
python3 -m http.server 8000         # serve the repository root yourself
```

`dev.py` watches `content/`, `theme/`, `pipeline/`, `nav.py` and `build.py`, rebuilds on
every save, serves the repository root at http://localhost:8000/v2/, and reloads the
page after a rebuild. Pass `--port 8080` for another port.

Then measure it rather than eyeball it:

```bash
# http://localhost:8000/v2/tools/audit.html?page=/v2/quickstart/
```

## 1. Tokens

All of it lives in `:root` at the top of `theme/v2.css`, so the theme can be retuned from
one place.

### Brand

The palette of `theme/logo.svg`: noisy cells, clean cells, cyan output.

| Token | Light | Dark | Used for |
| --- | --- | --- | --- |
| `--brand-accent` | `#02eff0` | `#02eff0` | the mark's cyan cells, focus rings, selection, search highlight, code constants, the note callout's rule |
| `--brand-accent-text` | `#087579` | `#41f3f4` | link ink where it must be legible as text |
| `--brand-ink` / `--brand-ink-weak` | `#102830` / `#0d353c` | `#0d353c` / `#0f2930` | the mark's ground, the favicon |
| `--link` | `--brand-accent-text` | same | `:focus-visible` rings, link hover |

The accent is a *fill* colour: it is never used for body text at small sizes on white,
because `#02eff0` does not carry enough contrast there.

### Greys, text and surfaces

Eleven steps, `light-dark()` pairs, as upstream: `--grey-1` `#fbfbfb`/`#0c0c0c` …
`--grey-11` `#161616`/`#fafafa`. `--bg` is `--grey-1`, `--surface` `--grey-2`,
`--bg-weak` `--grey-3`, `--border` `--grey-5`, `--border-strong` `--grey-6`,
`--text-faint` `--grey-7`, `--text-weak`/`--text-muted` `--grey-8`, `--text` `--grey-9`,
`--text-strong` `--grey-11`.

### Type

Mono for everything that is chrome — headings, nav, rail, code, labels — and the system UI
face for prose. `--font-mono` prefers OpenTUI Mono, then SF Mono/JetBrains Mono;
`--font-sans` prefers Inter. No webfonts ship with the preview yet: drop the files into
`site/assets/` and add `@font-face` when licensing allows, and only the metrics change.

| Token | ≤960px | Notes |
| --- | --- | --- |
| `--fs-micro` | 12px | labels, table headers, badge text |
| `--fs-meta` | 13px | code body, "Link copied" |
| `--fs-small` | 14px | card text, secondary UI |
| `--fs-ui` / `--mono-size` | 15px → 16px | all chrome |
| `--fs-read` | 16px → 17px | prose |
| `--fs-title` | 17px → 18px | `h2` |
| `--fs-h1` | `clamp(28px, 25px + .5vw, 32px)` | the page title |

`--title-stroke: 0.2px currentColor` is the "faux medium" on the current nav row and `h2`.
Line heights: prose `1.6`, chrome rows `20px`, `h1` `1.15`, `h2` `1.35`.

Spacing is a four-step scale — **8 / 12 / 16 / 24px** (`.5 / .75 / 1 / 1.5rem`) — plus
`2rem` between major blocks. Components use the step their density calls for; nothing
invents a value between steps.

### Space and shape

`--page-max: 1728px`, `--gutter: 1rem`, `--edge: 1.5rem`, `--top: var(--edge)`,
`--logo-height: 1.75rem`, `--logo-gap: calc(var(--top) + 8px)`,
`--content-top: calc(var(--top) + var(--logo-height) + var(--logo-gap))` = **84px**.
Corners are square everywhere. `--row-height: 2.75rem` for touch rows.
Motion is colour only, at 150ms, with `--ease-out: cubic-bezier(.23, 1, .32, 1)`; nothing
animates under `prefers-reduced-motion`.

The bracket lists carry `--bracket-bearing: calc(var(--mono-size) * 0.154)` (2.31px at
15px): the side bearing of `[`, which the container's padding gives back so the bracket's
ink lands on the content edge.

## 2. The shell

```
[data-site]
  header[data-component=topbar]                    ← phones only
  div[data-slot=frame]
    aside[data-component=sidebar]                  ← sticky, 100dvh
      [data-component=docs-lockup][data-host=sidebar]
      a[data-slot=logo]
      div[data-component=section-nav]              ← scroll box
        button[data-slot=section-toggle]           ← phones only
        div[data-slot=section-body]
          nav[data-component=docs-nav]
    details[data-component=contents-menu]          ← phones only
    a[data-component=github-link][data-owner=corner]
    main[data-component=content]#content
      div[data-slot=page] > article[data-component=docs-article]
    aside[data-component=aside] > div[data-component=docs-aside]
  footer[data-component=site-footer]
    div[data-slot=secondary]                        ← links, controls, ©2026 Haseeb Khan
    div[data-slot=main]
      svg[data-component=wordmark]                  ← the blueprint wordmark
  div[data-component=site-search] > dialog[data-search-dialog]
```

Desktop grid: `var(--sidebar-width) minmax(0, 1fr) var(--aside-width)` — both rails sticky
at `100dvh`, the frame ending at the footer. The sidebar is one of five equal page columns
and the aside the fourth, so both rails have the same width:
`edge + (page − 2·edge − 4·gutter) / 5`. Breakpoint **60rem / 960px**: below it the
topbar, the section row and the Contents row take over and the rails are hidden.

| Landmark | Value | Verified |
| --- | --- | --- |
| Content line | 84px | title cap, first nav row cap, and the rail's search button all sit on it |
| Sidebar width | `edge + (page − 2·edge − 4·gutter) / 5` | 347px at 1728, 290px at 1440 |
| Article column | page − sidebar − aside | 787px at 1440px |
| Article end padding | `2 * gutter + 40px` = 72px | measured 72px before the rail |
| Rail width | same five-column width as the sidebar | 290px at 1440px |
| Nav row pitch | 30px (20px line + 10px gap) | measured 30, 30, 30 |
| Rail row pitch | 30px (20px line, 5px padding each side) | matches the nav |
| Code frame header | 2.5rem | measured 40px |
| Table | 12px cells, 1px full grid, `--code-head` head | the head is a band, the cells a grid |
| Footer links | foot of the sidebar; the footer carries them on phones | aligns with the nav above |
| Footer mark | a pixel-block SVG drawn in the page's muted inks: hatch and outline `--border`, hollow nodes on `--bg` with a `--border` stroke; only the 'i' dot and hyphen carry `--brand-accent`, so the wordmark stays a quiet sign-off | generated from `pipeline/wordmark.py`; no font file |

## 3. The nav's bracket list

The most particular thing in the layout, so it is spelled out:

* `li` is a flex row and the link carries `padding-block: 5px; margin-block: -5px`
  (`li + li { margin-top: 10px }`). The flex row is what stops the negative margins
  collapsing into the `li` and turning the pitch into 35px — a bug worth remembering.
* The row is `[` + a 2ch cell + `]` + `0.625rem` + the label. The dash is **drawn**
  (`0.75em × 0.09em`, `translate: 0 0.05em`), not typed, so nothing shifts when it appears.
* The current page's dash is shown by `[data-slot="fill"][data-state="current"]` (the
  sticky phone row) or `a[aria-current="page"]`; hover shows it too.
* Group titles are **left-aligned with the brackets' ink**, not with the labels: they carry
  `margin-inline-start: var(--bracket-bearing)` while the container's left padding is
  `calc(var(--edge) - var(--bracket-bearing))`.
* Labels are one line each with an ellipsis; the sidebar's width is chosen so no label needs
  it (all 19 fit at the five-column width), and each link carries `title` for the ones that ever would.

## 4. The rails' contents

The Contents rail is mono, 20px lines on a 30px pitch, `--rail-gutter: 14px` with a 2px pipe
for the current section (`aria-current="location"`, which is what the stylesheet expects) and
`--border-strong` on hover. Items are one line with an ellipsis. `h2`/`h3` only.

Section titles carry a **button** (`[data-slot="heading-link"]`) that copies the section's
address and says "Link copied" beside the title; it looks like the title, never underlined.

## 5. Components in content

| Component | Written as | Renders |
| --- | --- | --- |
| Callout | `<Callout type="note\|tip\|caution\|danger" title="…">` | `aside[data-component=callout][data-type]` with a coloured inline-start rule |
| Card, CardGroup | `<CardGroup cols={2}>` + `<Card title href>` | `div[data-component=card-group]` + `a[data-component=docs-card]` |
| Code tabs | `=== "label"` with an indented block | `div[data-component=code-tabs]` with a tablist and one Copy |
| CodeBlock | `<CodeBlock label language code />` | a code frame |

Fenced code picks its frame from the language and the `title="…"` meta:

| Fence | Frame | Copy keeps |
| --- | --- | --- |
| `bash`/`sh`/`shell`/`zsh`/`console` with `$ ` lines | terminal, prompts in the command colour, other lines as output | only the `$ ` lines' commands |
| `bash` without any `$ ` | terminal, every line as output | the text |
| `diff` | a row per line with signs | added and unchanged lines, signs stripped |
| `text` with `├──`/`└──` and no title | a file tree | the tree, indented |
| anything with `title="file.py"` | a titled frame with a file icon | the code |
| anything else | a frame labelled by language | the code |

**Shell fences hold commands, so they carry the `$ ` prompt** — that is what upstream writes
and what makes a fence a session rather than a screenful of muted output.

## 6. Writing a page

1. `content/<slug>.md`. The path *is* the URL: `content/adr/index.md` → `/adr/`.
2. Frontmatter: `title` (required), `description`, `noindex`, `tableOfContents`.
3. **The body starts at `##`.** The `<h1>` is generated from `title`.
4. Internal links are docs-root-relative: `[Quickstart](/quickstart/)`.
5. `<!-- prettier-ignore -->`-free markdown: GFM tables, fenced code, lists, blockquotes,
   plus the components above. Smart punctuation (`'` `"` `--` `...`) is applied for you.
6. To add the page to the site, list it in `nav.py` — that file is the single source of truth
   for the sidebar order, the prev/next pager, the search index order, `llms.txt` and
   `sitemap.xml`.
7. **Nav labels are short** (1–2 words, ≤ 20 characters). They may differ from the page
   title, which is what gives the h1 its full wording.

`--8<-- "CHANGELOG.md"` inlines a repository file, so release notes stay single-sourced.

## 7. What the build checks

`python3 v2/build.py` fails on:

* **broken links** — every `href` must resolve to a built file;
* **missing anchors** — every `#fragment` must exist as an `id` in the target;
* **asset prefix** — nothing may load from outside the built site (the V1 link is exempt,
  as upstream exempts `/v1/docs`);
* **reserved names** — no page may take `assets`, `llms.txt`, `sitemap.xml`, `favicon.svg`;
* **budgets** — the script ≤ 8 KiB gzipped, the stylesheet ≤ 30 KiB gzipped (currently 5.0
  and 12.0).

It also writes each page's Markdown twin (`index.md` beside `index.html`) for *Copy as
Markdown*, `llms.txt`, and `sitemap.xml`.

## 8. Deliberate deviations

| Upstream | Here | Why |
| --- | --- | --- |
| MDX components compiled by Vite | a Python scanner over the same component syntax | no JS toolchain in this repository |
| `CodeTabs tabs={[…]}` with the code as props | `=== "label"` fences rendering the same markup | keeps code in fences, where editors can read it |
| `.mdx` sources, `docs/` published set | `.md` under `content/`, migrated from `docs/` by `tools/migrate_content.py` | V1 keeps its own sources until v2 goes live |
| Pagefind index | a build-time JSON index (`assets/search-index.js`) | no binary dependency; swap in Pagefind before shipping |
| API page rendered from `openapi.json` | lifted from the mkdocstrings HTML the V1 build already produced | keeps real signatures without re-generating them |
| `Footer wordmark is a 234×42 SVG` | a generated pixel-block blueprint: `universal / data-cleaner`, hatch fill, 1px outline, anchor nodes (`pipeline/wordmark.py`) | same technique as upstream's wordmark, in this project's letters |
| Wordmark stays a dark hatch in dark mode | it draws itself from the page's tokens (`--bg`, `--border-strong`, `--text-weak`), so both themes get their own drawing; the cyan dot and hyphen are the accent | an exact `#0a0a0a` fill disappears against a `#0c0c0c` page |
| `--link` is a blue | the brand's cyan/teal | the mark's palette (see §1) |

`--content-top` is achieved by a slightly different mechanism than upstream's (their sidebar
pads to the content line and pulls the nav up with a negative margin; ours offsets the nav's
container) — the measured result is identical and ours cannot clip the first row inside its
scroll box.

## 9. Reference material

`reference/PIPELINE.md` is the write-up of how upstream authors and builds its docs, with
the file list it was derived from. `reference/css/` and `reference/src/` are raw copies of
their stylesheets and sources (gitignored); `tools/audit.html` is the measurement page used
for every number in this document.
