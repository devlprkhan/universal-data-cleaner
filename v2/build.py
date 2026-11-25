"""Build the v2 docs site into ``v2/site/``.

Run:   python3 v2/build.py
Serve: python3 -m http.server 8000      (from the repository root, then /v2/site/)

The pipeline mirrors ``services/site`` in ``anomalyco/opencode`` — the same
split of responsibilities, in Python (see ``reference/PIPELINE.md``):

``nav.py``                  the nav manifest: sidebar, pager, search, llms/sitemap order
``content/``                the pages; a file's path is its URL, the body starts at ``##``
``pipeline/frontmatter.py`` title/description/noindex/tableOfContents, title required
``pipeline/render.py``      headings + ids, components, tables, tabs, links
``pipeline/code.py``        fenced code → code frame variants (terminal/diff/tree/…)
``pipeline/api.py``         the generated API page (no Markdown twin)
``pipeline/shell.py``       the page shell (DocsLayout's HTML + head)
``pipeline/search.py``      the search index
``pipeline/extras.py``      Markdown twins, llms.txt, sitemap.xml
``pipeline/checks.py``      reserved names, asset prefix, link+fragment, size budgets
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nav import DOCS, Item, folder_of
from pipeline import api, checks, extras, frontmatter, search, shell, snippets
from pipeline.render import Heading, Renderer

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONTENT = HERE / "content"
THEME = HERE / "theme"
OUT = HERE / "site"
V1_BUILD = ROOT / "site"
V1_ASSETS = ROOT / "docs" / "assets"

BASE_URL = "https://devlprkhan.github.io/universal-data-cleaner/"
BUDGETS = {"assets/v2.js": 8 * 1024, "assets/v2.css": 30 * 1024}


def build_id() -> str:
    """A cache-buster that changes whenever a theme file changes."""
    stamps = [
        (THEME / name).stat().st_mtime
        for name in ("v2.css", "v2.js")
        if (THEME / name).exists()
    ]
    return str(int(max(stamps))) if stamps else "0"


def copy_assets() -> None:
    assets = OUT / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("v2.css", "v2.js"):
        shutil.copy2(THEME / name, assets / name)
    # The mark and its favicon live with the theme; the V1 assets are the fallback.
    for name in ("logo.svg", "favicon.svg"):
        source = THEME / name
        if not source.exists():
            source = V1_ASSETS / name
        if source.exists():
            shutil.copy2(source, assets / name)


def source_path(item: Item) -> Path:
    return CONTENT / f"{item.slug}.md"


def twin(meta: frontmatter.Frontmatter, body: str) -> str:
    """The page's Markdown twin: its frontmatter and body, snippets inlined."""
    lines = ["---", f'title: "{meta.title}"']
    if meta.description:
        lines.append(f'description: "{meta.description}"')
    lines += ["---", "", body.strip(), ""]
    return "\n".join(lines)


def render_page(
    item: Item, section_title: str
) -> tuple[shell.Page, dict[str, str]] | None:
    source = source_path(item)
    if not source.exists():
        print(f"  skip missing content/{item.slug}.md")
        return None

    meta, body = frontmatter.parse(
        source.read_text(encoding="utf-8"), source=str(source)
    )
    body = snippets.resolve(body, root=ROOT, relative_to=source.parent)
    renderer = Renderer(item.slug)
    is_api = item.slug == "api"
    v1_body = api.extract(V1_BUILD) if is_api else None

    if v1_body is not None:
        body_html = v1_body
        # The rail reads the generated page's own h2/h3 ids.
        headings = [
            Heading(level, anchor, text)
            for level, anchor, text in api.headings_of(v1_body)
        ]
        renderer.headings = headings
        markdown = None
    else:
        body_html = renderer.blocks(body.splitlines())
        markdown = twin(meta, body)

    page = shell.Page(
        slug=item.slug,
        title=meta.title,
        description=meta.meta_description,
        body=body_html,
        headings=renderer.headings,
        noindex=meta.noindex,
        table_of_contents=meta.table_of_contents,
        section=DOCS,
        source=f"v2/content/{item.slug}.md",
        markdown=markdown,
    )
    record = search.record(
        title=meta.title,
        section=section_title,
        url=shell.page_href(item.slug, page.depth),
        body_html=body_html,
        headings=renderer.headings,
    )
    return page, record


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    out_id = build_id()
    copy_assets()

    records: list[dict[str, str]] = []
    slugs: list[str] = []
    urls: list[str] = []

    for item in DOCS.pages:
        rendered = render_page(item, DOCS.title)
        if rendered is None:
            continue
        page, record = rendered
        # A folder's landing page is written beside its folder, as upstream writes
        # ``docsHref``: ``adr/index`` → ``adr/index.html`` → the URL ``/adr/``.
        folder = folder_of(item.slug)
        target = OUT / folder / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            shell.document(page, build_id=out_id, v1_available=V1_BUILD.is_dir()),
            encoding="utf-8",
        )
        if page.markdown:
            (target.parent / "index.md").write_text(page.markdown, encoding="utf-8")
        records.append(record)
        slugs.append(item.slug if item.slug != "index" else "")
        urls.append(f"{BASE_URL}{'' if item.slug == 'index' else item.slug + '/'}")

    (OUT / "assets" / "search-index.js").write_text(
        search.payload(records), encoding="utf-8"
    )
    (OUT / "llms.txt").write_text(
        extras.llms_txt([DOCS], base_url=BASE_URL), encoding="utf-8"
    )
    (OUT / "sitemap.xml").write_text(
        extras.sitemap_xml(urls, base_url=BASE_URL), encoding="utf-8"
    )

    problems = [
        *checks.check_reserved_names(OUT, slugs),
        *checks.check_asset_prefix(OUT),
        *checks.validate_links(OUT),
    ]
    budget_problems, budget_log = checks.check_budgets(OUT, BUDGETS)
    problems += budget_problems

    print(f"built {len(records)} pages into {OUT.relative_to(ROOT)}")
    for line in budget_log:
        print(f"  {line}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("checks: links, fragments, asset prefix, reserved names, budgets — ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
