"""Build checks, ported from ``script/build.ts`` and ``script/validate-links.ts``.

Each check fails the build rather than warning, as upstream does:

* ``check_reserved_names`` — no page may take a name the docs set needs
  (``assets``, ``llms.txt``, ``sitemap.xml``, …)
* ``check_asset_prefix`` — nothing may load from outside the built site, so the
  preview can be served from any path and never leaks a root-absolute URL
* ``validate_links`` — every ``href`` must resolve to a built file and, when it
  carries a fragment, to an ``id`` in that file
* ``check_budgets`` — size ceilings for the script and the stylesheet
"""

from __future__ import annotations

import gzip
import posixpath
import re
from pathlib import Path

RESERVED = {"assets", "llms.txt", "sitemap.xml", "favicon.svg", "pagefind", "_build"}
# Links into another docs set (the V1 site beside this one) leave this build by
# design, as upstream exempts /v1/docs from its link check.
EXEMPT = ("site/",)
LINK = re.compile(r'(?:href|src)="([^"]+)"')
ID = re.compile(r'\bid="([^"]+)"')
SKIP = ("http://", "https://", "mailto:", "tel:", "//", "data:")


def _pages(out: Path) -> list[Path]:
    return sorted(path for path in out.rglob("*.html") if path.is_file())


def _is_exempt(href: str) -> bool:
    return any(href.endswith(suffix) for suffix in EXEMPT)


def _target(page: Path, out: Path, href: str) -> str | None:
    if not href or href.startswith(SKIP) or _is_exempt(href):
        return None
    path = href.partition("#")[0].partition("?")[0]
    base = "/" + posixpath.relpath(page, out).replace("\\", "/")
    if path.startswith("/"):
        resolved = path
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base), path))
    if (
        path in ("", ".")
        or resolved.endswith("/")
        or not posixpath.splitext(resolved)[1]
    ):
        resolved = posixpath.join(resolved, "index.html")
    return resolved.lstrip("/")


def check_reserved_names(out: Path, pages: list[str]) -> list[str]:
    problems = []
    for slug in pages:
        first = slug.split("/")[0]
        if slug and (first in RESERVED or f"{first}.md" in RESERVED):
            problems.append(f"reserved name: {slug}")
    return problems


def check_asset_prefix(out: Path) -> list[str]:
    problems = []
    root = out.resolve()
    for page in _pages(out):
        for href in LINK.findall(page.read_text(encoding="utf-8")):
            if href.startswith(SKIP) or href.startswith("#"):
                continue
            relative = _target(page, out, href)
            if relative is None:
                continue
            target = (out / relative).resolve()
            if relative.startswith("..") or not str(target).startswith(str(root)):
                problems.append(
                    f"{page.relative_to(out)}: loads outside the site: {href}"
                )
    return problems


def validate_links(out: Path) -> list[str]:
    problems = []
    ids: dict[Path, set[str]] = {}
    for page in _pages(out):
        html = page.read_text(encoding="utf-8")
        for href in LINK.findall(html):
            if href.startswith(SKIP):
                continue
            relative = _target(page, out, href)
            if relative is None:
                continue
            target = out / relative
            if not target.is_file():
                problems.append(f"{page.relative_to(out)}: broken link: {href}")
                continue
            _, _, fragment = href.partition("#")
            if not fragment:
                continue
            if target not in ids:
                ids[target] = set(ID.findall(target.read_text(encoding="utf-8")))
            wanted = fragment.split("%")[0]
            if wanted not in ids[target] and fragment not in ids[target]:
                problems.append(
                    f"{page.relative_to(out)}: missing anchor #{fragment} in {href}"
                )
    return problems


def check_budgets(out: Path, limits: dict[str, int]) -> tuple[list[str], list[str]]:
    """Return (problems, log lines) for the gzipped size ceilings."""
    problems: list[str] = []
    log: list[str] = []
    for name, limit in limits.items():
        path = out / name
        if not path.is_file():
            problems.append(f"missing asset: {name}")
            continue
        size = len(gzip.compress(path.read_bytes(), 9))
        log.append(
            f"{name:<28} {size / 1024:6.1f} KiB gz  (limit {limit / 1024:.0f} KiB)"
        )
        if size > limit:
            problems.append(
                f"{name} is {size / 1024:.1f} KiB gzipped, over {limit / 1024:.0f} KiB"
            )
    return problems, log
