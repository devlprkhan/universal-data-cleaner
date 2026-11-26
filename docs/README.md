# Documentation website

The source of the documentation site at
<https://devlprkhan.github.io/universal-data-cleaner/>. It is a small static
generator: Markdown in `content/`, a Python pipeline, and a hand-written theme.
The layout and rules are documented in **[`STYLEGUIDE.md`](STYLEGUIDE.md)**.

```bash
uv run python docs/dev.py             # rebuild on change + serve at localhost:8000
uv run python docs/build.py           # build site/ once
```

`dev.py` watches `content/`, `theme/`, `pipeline/`, `nav.py` and `build.py`,
rebuilds on every save, serves the built site at <http://localhost:8000/>, and
reloads the page after a rebuild. CI runs `docs/build.py` and publishes `site/` to
GitHub Pages.

## Layout

```
docs/
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
  reference/
    PIPELINE.md          how upstream authors and builds its docs, with sources
  site/                  generated output (gitignored, at the repository root)
```

## Measuring it, not squinting at it

`tools/audit.html` loads a built page in an iframe and prints a pass/fail line for
every layout invariant: the content line, the 30px nav pitch, the bracket cell,
the rail's gutter and pipe, the prose measure, the code frame's header, the
table's grid, the footer links in the sidebar, and that syntax highlighting
actually has more than one ink.

```
http://localhost:8000/tools/audit.html?page=/quickstart/
http://localhost:8000/tools/audit.html?page=/leak-safe-workflow/&theme=dark
```

Query parameters: `page` (path under the server), `w` (viewport width), `theme`.

## Adding a page

1. Add the Markdown file under `content/` (a folder landing page is
   `content/<folder>/index.md`).
2. Add an `Item` to the `DOCS` section in `nav.py`; the path is the URL.
3. Run `uv run python docs/build.py` and commit the source changes. The build
   checks links, fragments, asset paths, reserved names, and size budgets.

The API page is generated from the package docstrings by `pipeline/api.py`, so
public names appear there automatically; edit `content/api.md` only for the
surrounding prose.
