"""The page shell — ``DocsLayout.tsx``'s HTML, in Python.

The document is composed as upstream composes it, so the stylesheet's selectors
apply unchanged:

* ``<head>``: description, ``noindex``, two ``theme-color`` metas, the colour
  scheme, canonical, the Markdown twin when there is one, title, stylesheet.
* ``div[data-site][data-page=docs][data-layout=docs]``: the pre-paint theme
  script, skip link, topbar, ``div[data-slot=frame]`` with three columns
  (sidebar / content / aside), the phone Contents bar, the footer, the search
  dialog.
* ``aside[data-component=sidebar][data-section-nav]``: the lockup, the logo and
  ``div[data-component=section-nav]`` (toggle + body) around ``docs-nav``.
* ``main[data-component=content]#content > div[data-slot=page] > article``: the
  generated ``<h1>``, the rendered body, ``footer[data-slot=article-footer]``.
* ``aside[data-component=aside] > div[data-component=docs-aside]``: the search
  button over the Contents rail.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field

from nav import Section, depth_of, page_order

from pipeline.render import Heading
from pipeline.wordmark import wordmark

SITE_NAME = "Universal Data Cleaner"
REPO = "https://github.com/devlprkhan/universal-data-cleaner"
COPY_LABELS = (
    ("idle", "Copy as Markdown"),
    ("copied", "Copied"),
    ("failed", "Press \u2318C"),
)
STRINGS = {
    "copied": "Copied",
    "copyFailed": "Press \u2318C",
    "linkCopied": "Link copied",
    "markdownCopied": "Copied the page as Markdown",
    "noResults": "No results for",
    "empty": "Type to search the docs, or browse the sidebar.",
    "browse": "Browse the docs",
    "search": "Search",
    "previous": "Previous",
    "next": "Next",
    "contents": "Contents",
    "system": "System",
    "light": "Light",
    "dark": "Dark",
}


def _mark() -> str:
    """The brand mark: noisy cells settling into clean columns, then cyan output.

    The "white" cells take the surrounding ink (`currentColor`) so one file serves both
    themes; the cyan cells take the brand accent. Geometry from the official SVG.
    """
    ink = (
        (18, 24, 0.30),
        (50, 20, 0.45),
        (34, 48, 0.35),
        (2, 70, 0.25),
        (26, 74, 0.40),
        (52, 70, 0.55),
        (18, 98, 0.35),
        (52, 120, 0.40),
        (76, 20, 0.60),
        (76, 44, 0.60),
        (76, 70, 0.60),
        (76, 94, 0.60),
        (100, 20, 1.0),
        (100, 44, 1.0),
        (100, 70, 1.0),
        (100, 94, 1.0),
        (100, 120, 1.0),
    )
    cyan = (
        (54, 44, 0.65),
        (44, 94, 0.65),
        (76, 120, 0.75),
        (124, 20, 1.0),
        (148, 20, 1.0),
        (124, 44, 1.0),
        (148, 44, 1.0),
        (124, 70, 1.0),
        (148, 70, 1.0),
        (124, 94, 1.0),
        (148, 94, 1.0),
        (124, 120, 1.0),
        (148, 120, 1.0),
    )

    def cells(items: tuple[tuple[int, int, float], ...]) -> str:
        return "".join(
            f'<rect x="{x}" y="{y}" width="16" height="16"'
            + (f' fill-opacity="{o}"' if o < 1 else "")
            + "/>"
            for x, y, o in items
        )

    return (
        '<svg viewBox="0 0 166 156" width="30" height="28" aria-hidden="true">'
        f'<g fill="currentColor">{cells(ink)}</g>'
        f'<g class="brand-cells">{cells(cyan)}</g>'
        "</svg>"
    )


ICONS = {
    "logo": _mark(),
    "search": (
        '<svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true">'
        '<circle cx="7" cy="7" r="4.25" fill="none" stroke="currentColor" '
        'stroke-width="1.5"/>'
        '<path d="m10.5 10.5 3 3" stroke="currentColor" stroke-width="1.5"/></svg>'
    ),
    "chevron": (
        '<svg viewBox="0 0 16 16" width="10" height="10" aria-hidden="true">'
        '<path d="m4 6.25 4 4 4-4" fill="none" stroke="currentColor" '
        'stroke-width="1.5"/></svg>'
    ),
    "github": (
        '<svg viewBox="0 0 16 16" width="20" height="20" aria-hidden="true">'
        '<path fill="currentColor" d="M8 .8a7.2 7.2 0 0 0-2.28 14.03c.36.07.49-.16.49-.35v'
        "-1.24c-2 .43-2.43-.96-2.43-.96-.33-.84-.8-1.06-.8-1.06-.66-.45.05-.44.05-.44"
        ".73.05 1.11.75 1.11.75.65 1.11 1.7.79 2.12.6.07-.47.25-.79.46-.97-1.6-.18-3.29"
        "-.8-3.29-3.56 0-.79.28-1.43.75-1.94-.08-.18-.33-.92.07-1.92 0 0 .6-.19 1.98.74"
        "a6.9 6.9 0 0 1 3.6 0c1.38-.93 1.98-.74 1.98-.74.4 1 .15 1.74.07 1.92.47.51.75 "
        "1.15.75 1.94 0 2.77-1.69 3.38-3.3 3.56.26.22.49.66.49 1.33v1.97c0 .19.13.42.5 "
        '.35A7.2 7.2 0 0 0 8 .8Z"/></svg>'
    ),
    "system": (
        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" '
        'stroke-width="1.25" aria-hidden="true"><rect x="2" y="2.75" width="12" '
        'height="8.5"></rect><path d="M5.5 14H10.5M8 11.25V14"></path></svg>'
    ),
    "light": (
        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" '
        'stroke-width="1.25" aria-hidden="true"><circle cx="8" cy="8" r="2"></circle>'
        '<path d="M8 1V4M8 12V15M1 8H4M12 8H15M3.125 3.125L5.125 5.125M10.875 10.875'
        'L12.875 12.875M12.875 3.125L10.875 5.125M5.125 10.875L3.125 12.875"></path></svg>'
    ),
    "dark": (
        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" '
        'stroke-width="1.25" aria-hidden="true"><path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 '
        '2.5A5.5 5.5 0 1 0 13.5 9.5Z" stroke-linejoin="round"></path></svg>'
    ),
    "markdown": (
        '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" '
        'stroke-width="1.25" aria-hidden="true"><rect x="2.125" y="2.125" width="11.75" '
        'height="11.75"></rect><path d="M0.875 6V10M15.125 6V10"></path>'
        '<rect x="4.875" y="5.75" width="2" height="4.5" fill="currentColor" stroke="none">'
        '</rect><rect x="9.125" y="5.75" width="2" height="4.5" fill="currentColor" '
        'stroke="none"></rect></svg>'
    ),
}

BRACKET = (
    '<span data-slot="box" aria-hidden="true">[<span data-slot="fill"></span>]</span>'
)
# The sticky row names the current page as the nav marks it: "[-] Intro".
BRACKET_CURRENT = BRACKET.replace(
    'data-slot="fill"', 'data-slot="fill" data-state="current"'
)
# A row that leaves the site shows the external arrow in its cell, at rest.
ARROW = (
    '<svg data-slot="external" viewBox="0 0 16 16" width="10" height="10" aria-hidden="true">'
    '<path d="M5 11 11 5M6 5h5v5" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>'
)
EXTERNAL_BRACKET = (
    '<span data-slot="box" aria-hidden="true">['
    f'<span data-slot="fill" data-state="external">{ARROW}</span>]</span>'
)
SPACE = " "
CURRENT = ' aria-current="page"'


@dataclass
class Page:
    slug: str
    title: str
    description: str
    body: str
    headings: list[Heading] = field(default_factory=list)
    noindex: bool = False
    table_of_contents: bool = True
    section: Section | None = None
    source: str | None = None
    markdown: str | None = None

    @property
    def depth(self) -> int:
        return depth_of(self.slug)

    @property
    def up(self) -> str:
        return "../" * self.depth


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def page_href(slug: str, depth: int) -> str:
    """A page's URL from a page at ``depth`` — relative, so the site is portable."""
    up = "../" * depth
    if not slug or slug == "index":
        return up or "./"
    return up + slug.removesuffix("/index") + "/"


def asset(name: str, depth: int, build_id: str) -> str:
    return f"{'../' * depth}assets/{name}?v={build_id}"


def _lockup(page: Page, host: str) -> str:
    home = page_href("index", page.depth)
    # V2 is published under `/v2/`, V1 stays at the site root: one level above a page's
    # own directory is the root, whichever page is open.
    v1 = "../" * (page.depth + 1) or "./"
    section_title = page.section.title if page.section else "Docs"
    rows = [
        (home, "Docs v2", CURRENT, ""),
        (v1, "Docs v1", "", ""),
        (REPO, "Source", "", ' target="_blank" rel="noopener"'),
    ]
    menu = "".join(
        f'<a role="menuitem" href="{href}"{current}{external}>{esc(label)}</a>'
        for href, label, current, external in rows
    )
    return (
        f'<div data-component="docs-lockup" data-host="{host}">'
        f'<button type="button" data-slot="trigger" aria-expanded="false" aria-haspopup="menu">'
        f'<span data-slot="current">{esc(section_title)}</span>{ICONS["chevron"]}</button>'
        f'<div data-slot="menu" role="menu" hidden>{menu}</div>'
        "</div>"
    )


def _logo(page: Page, v1_available: bool) -> str:
    return (
        f'<a href="{page_href("index", page.depth)}" data-slot="logo" data-variant="icon" '
        f'aria-label="Universal Data Cleaner home">{ICONS["logo"]}</a>'
    )


def _github(owner: str) -> str:
    return (
        f'<a data-component="github-link" data-owner="{owner}" href="{REPO}" '
        f'aria-label="GitHub repository" target="_blank" rel="noopener">'
        f"{ICONS['github']}</a>"
    )


def _docs_nav(page: Page) -> str:
    section = page.section
    if section is None:
        return ""
    groups: list[str] = []
    for index, group in enumerate(section.groups):
        rows = "".join(
            f'<li><a href="{page_href(item.slug, page.depth)}" title="{esc(item.title)}"'
            + (CURRENT if item.slug == page.slug else "")
            + ">"
            + BRACKET
            + f'<span data-slot="label">{esc(item.title)}</span></a></li>'
            for item in group.items
        )
        title = group.title if group.title != section.title else None
        if title:
            heading = f'<span data-slot="group-title" id="docs-nav-{index}">{esc(title)}</span>'
            labelled = f' aria-labelledby="docs-nav-{index}"'
        else:
            heading, labelled = "", ""
        groups.append(
            f'<div data-slot="group">{heading}<ul{labelled}>{rows}</ul></div>'
        )
    return f'<nav data-component="docs-nav" aria-label="Documentation">{"".join(groups)}</nav>'


def _contents(page: Page) -> list[Heading]:
    if not page.table_of_contents:
        return []
    return [heading for heading in page.headings if heading.depth in (2, 3)]


def _contents_items(page: Page) -> str:
    return "".join(
        f'<li{level}><a href="#{heading.slug}">{esc(heading.text)}</a></li>'
        for heading, level in (
            (heading, ' data-level="3"' if heading.depth == 3 else "")
            for heading in _contents(page)
        )
    )


def _aside(page: Page) -> str:
    contents = _contents(page)
    rail = ""
    if contents:
        rail = (
            '<nav data-component="on-this-page" aria-label="On this page">'
            f'<span data-slot="heading">{esc(STRINGS["contents"])}</span>'
            f"<ul>{_contents_items(page)}</ul></nav>"
        )
    return (
        '<aside data-component="aside" data-section="aside" aria-label="On this page">'
        '<div data-component="docs-aside">'
        '<button type="button" data-slot="search" data-search-open '
        'aria-label="Search the docs" aria-haspopup="dialog" '
        'aria-keyshortcuts="Meta+K Control+K /">'
        f'<span>{esc(STRINGS["search"])}</span><kbd dir="ltr">\u2318K</kbd></button>'
        f"{rail}"
        "</div></aside>"
    )


def _contents_menu(page: Page) -> str:
    contents = _contents(page)
    if not contents:
        return ""
    return (
        '<details data-component="contents-menu" data-docs-contents>'
        f'<summary aria-label="Contents of {esc(contents[0].text)}">'
        f'<span data-slot="label"><span data-slot="word">{esc(contents[0].text)}</span></span>'
        f"{ICONS['chevron']}</summary><ul>{_contents_items(page)}</ul></details>"
    )


def _pagination(page: Page) -> str:
    section = page.section
    if section is None:
        return ""
    order = page_order(section)
    if page.slug not in order:
        return ""
    index = order.index(page.slug)
    links: list[str] = []
    if index > 0:
        previous = section.pages[index - 1]
        links.append(
            f'<a href="{page_href(previous.slug, page.depth)}" rel="prev">'
            f"<small>{esc(STRINGS['previous'])}</small>"
            f"<span>{esc(previous.title)}</span></a>"
        )
    if index + 1 < len(order):
        following = section.pages[index + 1]
        links.append(
            f'<a href="{page_href(following.slug, page.depth)}" rel="next">'
            f"<small>{esc(STRINGS['next'])}</small>"
            f"<span>{esc(following.title)}</span></a>"
        )
    if not links:
        return ""
    return f'<nav aria-label="Pages" data-component="pagination">{"".join(links)}</nav>'


def _article_footer(page: Page) -> str:
    labels = "".join(
        f'<span data-label="{state}">{esc(text)}</span>' for state, text in COPY_LABELS
    )
    copy = ""
    if page.markdown:
        copy = (
            '<button type="button" data-copy-markdown data-md="index.md" data-state="idle">'
            f'<span data-slot="copy-labels" aria-hidden="true">{labels}</span>'
            '<span data-slot="sr-only">Copy this page as Markdown</span></button>'
            '<span data-slot="sr-only" aria-live="polite"></span>'
        )
    footer = (
        '<footer data-slot="article-footer" data-pagefind-ignore>'
        f"{_pagination(page)}"
        f'<p data-component="edit-link">{copy}</p>'
        "</footer>"
    )
    return footer if (copy or _pagination(page)) else ""


def _secondary_nav() -> str:
    """The links that leave the site: GitHub, Changelog, PyPI, Issues.

    They live at the foot of the sidebar, in the same bracket column as the docs nav,
    so the bar reads as one list from the logo to the page's end. On phones, where the
    sidebar is gone, the footer carries the same list.
    """
    links = (
        (REPO, "GitHub"),
        (f"{REPO}/blob/main/CHANGELOG.md", "Changelog"),
        ("https://pypi.org/project/universal-data-cleaner/", "PyPI"),
        (f"{REPO}/issues", "Issues"),
    )
    rows = "".join(
        f'<li><a href="{href}" target="_blank" rel="noopener">{BRACKET}'
        f'<span data-slot="label">{esc(text)}</span></a></li>'
        for href, text in links
    )
    return (
        '<nav data-component="secondary-nav" aria-label="Project">'
        f"<ul>{rows}</ul></nav>"
    )


def _controls(page: Page) -> str:
    """Upstream's footer controls: one button that cycles System > Light > Dark (its
    monitor, sun and moon cross-fade), and the page's Markdown beside it."""
    icons = "".join(
        f'<span data-slot="icon"{" data-current" if mode == "system" else ""}>'
        f"{ICONS[mode]}</span>"
        for mode in ("system", "light", "dark")
    )
    markdown = (
        '<a data-slot="markdown-view" href="index.md" aria-label="View this page as Markdown" '
        f'title="View this page as Markdown">{ICONS["markdown"]}</a>'
        if page.markdown
        else ""
    )
    return (
        '<div data-component="theme-toggle" data-variant="cycle" role="group" '
        'aria-label="Theme and view">'
        '<button type="button" data-slot="cycle" data-theme-cycle '
        'aria-label="System theme. Switch to light">'
        f"{icons}</button>{markdown}</div>"
    )


def _site_footer(page: Page) -> str:
    """The footer, in two columns: the bar's foot on the left, the blueprint wordmark on
    the right — the same split as upstream's docs footer."""
    return (
        '<footer data-component="site-footer" data-section="footer" id="footer">'
        f'<div data-slot="secondary">{_secondary_nav()}{_controls(page)}'
        '<span data-slot="copyright">\u00a92026 Haseeb Khan</span></div>'
        f'<div data-slot="main">{wordmark()}</div>'
        "</footer>"
    )


def _search_dialog() -> str:
    return (
        '<div data-component="site-search">'
        '<dialog data-search-dialog aria-label="Search documentation">'
        '<div data-slot="field">'
        f"{ICONS['search']}"
        '<input type="search" placeholder="Search docs" autocomplete="off" spellcheck="false" '
        'aria-label="Search docs" aria-controls="search-results">'
        '<button type="button" data-slot="close" aria-label="Close search">'
        '<span data-slot="esc">Esc</span><span data-slot="cancel">Cancel</span></button>'
        "</div>"
        '<div data-slot="results" id="search-results" role="listbox" aria-label="Results"></div>'
        "</dialog></div>"
    )


SPECULATION = (
    '<script type="speculationrules">'
    '{"prerender":[{"where":{"href_matches":"*"},"eagerness":"moderate"}]}'
    "</script>"
)


def document(page: Page, *, build_id: str, v1_available: bool) -> str:
    """The whole page, as upstream's ``DocsLayout`` renders it."""
    stylesheet = asset("v2.css", page.depth, build_id)
    script = asset("v2.js", page.depth, build_id)
    canonical = f"https://devlprkhan.github.io/universal-data-cleaner/{page.slug}/"
    alternate = (
        '<link rel="alternate" type="text/markdown" href="index.md">'
        if page.markdown
        else ""
    )
    robots = '<meta name="robots" content="noindex">' if page.noindex else ""
    strings = json.dumps(STRINGS, ensure_ascii=False)
    lockup = _lockup(page, "sidebar")

    return f"""<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{esc(page.description)}">
{robots}
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#fbfbfb">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0c0c0c">
<meta name="color-scheme" content="light dark">
{SPECULATION}
<link rel="canonical" href="{canonical}">
<link rel="icon" type="image/svg+xml" href="{asset("favicon.svg", page.depth, build_id)}">
{alternate}
<title>{esc(page.title)} | {esc(SITE_NAME)}</title>
<link rel="stylesheet" href="{stylesheet}">
</head>
<body>
<div data-site data-page="docs" data-layout="docs" data-theme="system" data-strings='{strings}'>
<script>try{{var t=localStorage.getItem("udc-theme");if(t==="light"||t==="dark"){{document.documentElement.dataset.theme=t}}}}catch(e){{}}</script>
<a href="#content" data-component="skip-link">Skip to content</a>

<header data-component="topbar">
  {_logo(page, v1_available)}
  {_lockup(page, "topbar")}
  <button type="button" data-slot="search-button" data-search-open aria-label="Search the docs" aria-haspopup="dialog">{ICONS["search"]}</button>
  {_github("topbar")}
</header>

<div data-slot="frame">
  <aside data-component="sidebar" data-section-nav data-section="nav" aria-label="Documentation">
    {lockup}
    {_logo(page, v1_available)}
    <div data-component="section-nav">
      <button type="button" data-slot="section-toggle" aria-expanded="false" aria-controls="section-nav">
        <span data-slot="current">{BRACKET_CURRENT}<span data-slot="label">{esc(page.title)}</span></span>
        {ICONS["chevron"]}
      </button>
      <div data-slot="section-body" id="section-nav">
        {_docs_nav(page)}
      </div>
    </div>
  </aside>

  {_contents_menu(page)}

  {_github("corner")}

  <main data-component="content" id="content" tabindex="-1">
    <div data-slot="page">
      <article data-component="docs-article" data-section="article" data-pagefind-body data-pagefind-meta="title:{esc(page.title)}">
        <h1 data-pagefind-meta="section:docs">{esc(page.title)}</h1>
        {page.body}
        {_article_footer(page)}
      </article>
    </div>
  </main>

  {_aside(page)}
</div>

{_site_footer(page)}
{_search_dialog()}
</div>
<script src="{asset("search-index.js", page.depth, build_id)}"></script>
<script src="{script}" defer></script>
</body>
</html>
"""
