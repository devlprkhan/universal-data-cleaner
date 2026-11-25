"""Frontmatter parsing — the Python stand-in for ``src/docs/frontmatter.ts``.

Only the four keys upstream defines are meaningful; anything else is stripped,
exactly as the upstream zod object strips unknown keys:

``title``            required — becomes the ``<h1>``, ``<title>`` and search title
``description``      optional — ``<meta name="description">``
``noindex``          optional bool — adds ``robots noindex`` and drops the page from search
``tableOfContents``  optional bool — ``false`` empties the Contents rail

A page body must not repeat the title as an ``# H1``; content starts at ``##``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", re.DOTALL)

KNOWN_KEYS = ("title", "description", "noindex", "tableOfContents")


class FrontmatterError(ValueError):
    """Raised when a page's frontmatter is missing or malformed."""


@dataclass
class Frontmatter:
    title: str
    description: str | None = None
    noindex: bool = False
    table_of_contents: bool = True

    @property
    def meta_description(self) -> str:
        return (
            self.description
            or f"{self.title} documentation for Universal Data Cleaner."
        )


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "yes", "on"}


def parse(raw: str, *, source: str = "<page>") -> tuple[Frontmatter, str]:
    """Split a source document into its frontmatter and its body."""
    match = FRONTMATTER.match(raw)
    if not match:
        raise FrontmatterError(f"{source}: missing frontmatter block")

    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in KNOWN_KEYS:
            fields[key] = value

    title = _unquote(fields.get("title", ""))
    if not title:
        raise FrontmatterError(f'{source}: frontmatter needs a "title"')

    toc_raw = fields.get("tableOfContents", "").strip().lower()
    return (
        Frontmatter(
            title=title,
            description=_unquote(fields["description"])
            if "description" in fields
            else None,
            noindex=_as_bool(fields.get("noindex", "false")),
            table_of_contents=not (toc_raw == "false" or toc_raw.startswith("false")),
        ),
        raw[match.end() :],
    )
