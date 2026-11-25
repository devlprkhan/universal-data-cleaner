"""The v2 navigation manifest.

The single source of truth for the sidebar, the previous/next pager, the search
index order, ``llms.txt`` and ``sitemap.xml`` — the job ``lib/navigation.ts``
does upstream (see ``reference/PIPELINE.md``).

Structure mirrors upstream:

* :class:`Section` — a docs set: its key, display title, landing slug and groups.
* :class:`Group` — a sidebar group; ``title`` omitted means the group renders
  without a heading.
* :class:`Item` — one page: its label, slug and optional external ``href``.

Slugs are content-relative without the extension: ``quickstart``,
``adr/index``. A slug is also the page's URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    title: str
    slug: str
    href: str | None = None

    @property
    def external(self) -> bool:
        return self.href is not None


@dataclass(frozen=True)
class Group:
    items: list[Item] = field(default_factory=list)
    title: str | None = None


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    landing_slug: str
    groups: list[Group] = field(default_factory=list)

    @property
    def items(self) -> list[Item]:
        return [item for group in self.groups for item in group.items]

    @property
    def pages(self) -> list[Item]:
        """The items that are real pages, in reading order (for the pager)."""
        return [item for item in self.items if not item.external]

    def section_name(self, slug: str) -> str:
        return self.title


DOCS = Section(
    key="docs",
    title="Docs",
    landing_slug="index",
    groups=[
        Group(items=[Item("Intro", "index")]),
        Group(
            title="Start here",
            items=[
                Item("Quickstart", "quickstart"),
                Item("Leak-safe workflow", "leak-safe-workflow"),
            ],
        ),
        Group(
            title="Guides",
            items=[
                Item("Cleaning data", "cleaning"),
                Item("Contracts & drift", "contracts"),
                Item("Statistical drift", "drift"),
                Item("Safe ingestion", "ingestion"),
                Item("Batch reporting", "reporting"),
                Item("Validation & joins", "validation-joins"),
                Item("ML split audit", "ml-split-audit"),
                Item("Production guide", "production"),
                Item("Performance", "performance"),
            ],
        ),
        Group(
            title="Reference",
            items=[
                Item("API reference", "api"),
                Item("Artifacts", "artifacts"),
                Item("Changelog", "changelog"),
            ],
        ),
        Group(
            title="Project",
            items=[
                Item("Roadmap", "roadmap"),
                Item("Upcoming", "upcoming"),
                Item("ADR index", "adr/index"),
                Item("Hardening strategy", "adr/0001-production-hardening-strategy"),
            ],
        ),
    ],
)

SECTIONS: list[Section] = [DOCS]


def slug_of(path: str) -> str:
    """A content file's slug: its path under ``content/`` without ``.md``."""
    slug = path.removesuffix(".md")
    return slug if slug == "index" else slug.removesuffix("/index")


def folder_of(slug: str) -> str:
    """The output folder for a slug — a folder's landing page sits beside it."""
    if slug in ("", "index"):
        return ""
    return slug.removesuffix("/index")


def depth_of(slug: str) -> int:
    """How many path segments a page's URL has, which is what relative links need."""
    folder = folder_of(slug)
    return 0 if not folder else len(folder.split("/"))


def section_of(slug: str) -> Section:
    """The section a slug belongs to, falling back to the first (as upstream does)."""
    for section in SECTIONS:
        if any(item.slug == slug for item in section.pages):
            return section
    return SECTIONS[0]


def page_order(section: Section) -> list[str]:
    return [item.slug for item in section.pages]
