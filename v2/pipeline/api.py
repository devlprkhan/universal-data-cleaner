"""The API reference: a generated page, not a Markdown one.

Upstream renders ``/docs/api`` from ``openapi.json`` through
``OpenApiReference.tsx`` and skips its Markdown twin
(``reference/PIPELINE.md`` §2). This build does the equivalent with the HTML
mkdocstrings already produced for the V1 site: it lifts the article body out of
``site/api/index.html`` and hands it to the v2 shell, so signatures, docstrings
and cross-references stay real instead of being re-typed.
"""

from __future__ import annotations

import re
from pathlib import Path

ARTICLE = '<article class="md-content__inner md-typeset">'
HEADERLINK = re.compile(r'<a class="headerlink"[^>]*>.*?</a>', re.DOTALL)
EDIT_BUTTON = re.compile(
    r'<a [^>]*class="[^"]*md-content__button[^"]*"[^>]*>.*?</a>', re.DOTALL
)
H1 = re.compile(r"<h1[^>]*>(.*?)</h1>", re.DOTALL)
TAGS = re.compile(r"<[^>]+>")
HEADING = re.compile(r'<h([23])[^>]*id="([^"]+)"[^>]*>(.*?)</h\1>', re.DOTALL)


def extract(v1_dir: Path) -> str | None:
    """The V1 API article's inner HTML, with Material's own chrome removed."""
    source = v1_dir / "api" / "index.html"
    if not source.exists():
        return None
    raw = source.read_text(encoding="utf-8")
    start = raw.find(ARTICLE)
    if start == -1:
        return None
    start = raw.find(">", start) + 1
    end = raw.find("</article>", start)
    body = raw[start:end]
    body = HEADERLINK.sub("", body)
    body = EDIT_BUTTON.sub("", body)
    return body


def title_of(body: str, fallback: str) -> str:
    match = H1.search(body)
    if not match:
        return fallback
    return TAGS.sub("", match.group(1)).strip() or fallback


def headings_of(body: str) -> list[tuple[int, str, str]]:
    """The h2/h3 list the Contents rail reads, from the body's own ids."""
    return [
        (int(level), anchor, TAGS.sub("", text).strip())
        for level, anchor, text in HEADING.findall(body)
    ]
