"""The search index.

Upstream builds Pagefind per docs set and fails the build when a page's markup
grows past its budgets. This build emits the same shape of data Pagefind would
return — title, section, url, headings, text — as one JSON payload the client
reads, so the palette can be judged without shipping a search binary.
"""

from __future__ import annotations

import html
import json
import re

from .render import Heading

TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


def plain_text(body_html: str, limit: int = 4000) -> str:
    text = TAG.sub(" ", body_html)
    return SPACE.sub(" ", html.unescape(text)).strip()[:limit]


def record(
    *,
    title: str,
    section: str,
    url: str,
    body_html: str,
    headings: list[Heading],
) -> dict[str, str]:
    return {
        "title": title,
        "section": section,
        "href": url,
        "headings": " \u00b7 ".join(heading.text for heading in headings),
        "text": plain_text(body_html),
    }


def payload(records: list[dict[str, str]]) -> str:
    return "window.__UDC_SEARCH__ = " + json.dumps(records, ensure_ascii=False) + ";\n"
