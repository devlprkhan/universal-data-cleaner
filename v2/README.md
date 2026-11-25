# Docs v2 — preview

A side-by-side rebuild of this documentation site, to the layout and rules of
`opencode.ai/docs`, documented in **[`STYLEGUIDE.md`](STYLEGUIDE.md)**.

The V1 MkDocs site in `site/` is untouched: this is a separate static build so the two can
be compared page for page.

```bash
python3 v2/dev.py                   # rebuild on change + serve (recommended)
python3 v2/build.py                 # rebuild v2/site once
python3 -m http.server 8000         # serve the repository root yourself
```

`dev.py` watches `content/`, `theme/`, `pipeline/`, `nav.py` and `build.py`, rebuilds on
every save, serves the repository root at http://localhost:8000/v2/, and reloads the
page after a rebuild.

| | URL |
| --- | --- |
| V1 (MkDocs, current) | http://localhost:8000/ |
| V2 (this preview) | http://localhost:8000/v2/ |

## Layout

```
v2/
  STYLEGUIDE.md          the rules and the measured numbers
  nav.py                 the nav manifest: sidebar order, pager, search, llms/sitemap
  dev.py                 rebuild on change + local server with live reload
  content/               the pages (a file's path is its URL; bodies start at ##)
  theme/
    v2.css               tokens → shell → components → responsive
    v2.js                theme, copy, menus, Contents spy, ⌘K search
    logo.svg favicon.svg the mark and its favicon
  pipeline/
    frontmatter.py       title / description / noindex / tableOfContents
    render.py            headings + ids, components, tables, tabs, links
    code.py              fenced code → frame variants (terminal, diff, tree, titled)
    api.py               the generated API page (no Markdown twin)
    shell.py             the page shell (the docs layout's HTML)
    search.py            the search index
    extras.py            Markdown twins, llms.txt, sitemap.xml
    snippets.py          --8<-- "CHANGELOG.md" includes
    checks.py            link, fragment, asset-prefix, reserved-name and budget checks
  tools/
    audit.html           the measurement page every number in the style guide came from
    migrate_content.py   docs/*.md → content/*.md (V1 syntax → v2 syntax)
  reference/
    PIPELINE.md          how upstream authors and builds its docs, with sources
  site/                  generated output (gitignored)
```

## Measuring it, not squinting at it

`tools/audit.html` loads a built page in an iframe and prints a pass/fail line for every
layout invariant: the content line, the 30px nav pitch, the bracket cell, the rail's gutter
and pipe, the prose measure, the code frame's header, the table's grid, the footer links in
the sidebar, and that syntax highlighting actually has more than one ink.

```
http://localhost:8000/v2/tools/audit.html?page=/v2/quickstart/
http://localhost:8000/v2/tools/audit.html?page=/v2/leak-safe-workflow/&theme=dark
```

Query parameters: `page` (path under the server), `w` (viewport width), `theme`.

## Status

**Preview only.** Nothing here is wired into `mkdocs.yml`, CI or Pages, and `site/` was not
modified. Content is migrated from `docs/` by `tools/migrate_content.py`; once v2 is approved
it becomes the single source and `docs/` goes away. Do not publish until then.

### Where it stands

* 19 pages build from `v2/content/`; the build's own checks (links, fragments, asset prefix,
  reserved names, size budgets) pass.
* `tools/audit.html` is green on `quickstart`, the home page, `leak-safe-workflow` and the ADR
  page in dark at 1200px: content line, 30px nav pitch, bracket cell, rail gutter and pipe,
  prose measure, code frames, table grid, footer links in the sidebar, syntax inks.
* The brand layer is wired from the mark: `#02eff0` accent, teal ink, and a favicon.
* `STYLEGUIDE.md` documents every value and every deliberate deviation from upstream.

### Next

1. **Review the visual details** (the maintainer's eye — the agent cannot see images).
2. **Delete the scratch**: `v2/.shots/`, `v2/_probe.py`. `rm` is blocked by this repo's
   policy, so this needs a human hand.
3. **Fonts**: decide between the system stack (SF Mono / Inter when installed) and shipping
   OpenTUI Mono + Inter as woff2 with `@font-face`.
4. **Search**: swap the build-time JSON index for Pagefind before shipping.
5. **Content pass**: hand-review the 17 derived `description` strings; restyle or restructure
   the `.formula` block in `content/cleaning.md`.
6. **Small-screen audit**: run `tools/audit.html` at `w=900` and `w=500` (the phone layout has
   not been measured since the topbar became sticky).
7. **Then**: make v2 live, retire `docs/` + `mkdocs.yml` + `assets/extra.*`, wire CI and Pages.
   Publishing stays blocked until explicit approval.

