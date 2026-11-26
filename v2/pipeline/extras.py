"""The three side artefacts upstream also writes.

``llms.txt``      a plain-text index of the docs, in nav order (``lib/llms.ts``)
``sitemap.xml``   the latest docs' URLs
Markdown twins    each page's source beside its HTML, for ``Copy as Markdown``
                  and ``<link rel="alternate" type="text/markdown">``
"""

from __future__ import annotations

from datetime import date

from nav import Section

HEADER = (
    "# Universal Data Cleaner Documentation",
    "",
    "> Leak-safe data cleaning for pandas and scikit-learn: one transformer that "
    "fits its rules on training data and reuses them for validation, test and production.",
)


def llms_txt(sections: list[Section], *, base_url: str) -> str:
    root = base_url.rstrip("/") + "/"
    lines: list[str] = list(HEADER)
    for section in sections:
        lines += ["", f"## {section.title}", ""]
        for group in section.groups:
            if group.title and group.title != section.title:
                lines += [f"### {group.title}", ""]
            for item in group.items:
                if item.external:
                    continue
                path = (
                    ""
                    if item.slug == "index"
                    else f"{item.slug.removesuffix('/index')}/"
                )
                lines.append(f"- [{item.title}]({root}{path})")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def sitemap_xml(urls: list[str], *, base_url: str, today: date | None = None) -> str:
    lastmod = (today or date.today()).isoformat()
    entries = "".join(
        f"  <url>\n    <loc>{url}</loc>\n    <lastmod>{lastmod}</lastmod>\n  </url>\n"
        for url in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}"
        "</urlset>\n"
    )
