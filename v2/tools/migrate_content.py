"""Migrate ``docs/*.md`` (the V1, MkDocs-authored set) to ``v2/content/``.

The point is the authoring technique the V2 docs use upstream
(``reference/PIPELINE.md`` sections 1 and 2):

* a page's frontmatter carries its ``title``; the body starts at ``##``
* internal links are docs-root-relative: ``[Config](/config)``
* callouts are components: ``<Callout type="caution" title="…">``
* a lead paragraph is ``<p class="lead">``

Tabs stay as ``=== "label"`` blocks: upstream passes an array to ``CodeTabs``,
which needs JSX, and this build renders that same markup from the fence syntax.

Run:  python3 v2/tools/migrate_content.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = V2.parent
SOURCE = ROOT / "docs"
TARGET = V2 / "content"

sys.path.insert(0, str(V2))

from nav import DOCS  # noqa: E402
from pipeline import snippets  # noqa: E402

NAV_TITLES = {item.slug: item.title for item in DOCS.pages}

SKIP = {"index.md", "api.md"}
ADMONITION = re.compile(r'^!!!\s+(\w+)(?:\s+"([^"]*)")?\s*$')
LEAD = re.compile(r"^\{:\s*\.lead\s*\}\s*$")
H1 = re.compile(r"^#\s+(.*?)\s*$")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+?)\)")
FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---(?:\r?\n|$)", re.DOTALL)


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def dedent(lines: list[str], width: int = 4) -> list[str]:
    return [line[width:] if line.startswith(" " * width) else line for line in lines]


def link_target(url: str, base: Path) -> str:
    """A source link as the docs write it: docs-root-relative (``/config``)."""
    if url.startswith(("http://", "https://", "mailto:", "tel:", "#", "{")):
        return url
    page, _, fragment = url.partition("#")
    if page.endswith(".md"):
        merged = (base / page).with_suffix("") if base != Path(".") else Path(page[:-3])
        slug = merged.as_posix().removesuffix("/index")
        page = "/" if slug in ("", "index") else f"/{slug}/"
    return page + (f"#{fragment}" if fragment else "")


def convert_links(text: str, base: Path) -> str:
    return LINK.sub(lambda m: f"[{m.group(1)}]({link_target(m.group(2), base)})", text)


DIV_ROW = re.compile(
    r'<div class="doc-links__row"[^>]*>\s*\[([^\]]+)\]\(([^)]+)\)\s*'
    r'<span class="doc-links__desc">(.*?)</span>\s*</div>',
    re.DOTALL,
)


def collect_div(lines: list[str], index: int) -> tuple[str, int]:
    """The whole ``<div …>…</div>`` block that starts at ``index``."""
    depth = 0
    buf: list[str] = []
    while index < len(lines):
        line = lines[index]
        buf.append(line)
        depth += len(re.findall(r"<div\b", line))
        depth -= len(re.findall(r"</div>", line))
        index += 1
        if depth <= 0:
            break
    return "\n".join(buf), index


def cards_from_links(block: str, base: Path) -> str:
    rows = DIV_ROW.findall(block)
    cards = "".join(
        f'<Card title="{label.strip()}" href="{link_target(href, base)}">{desc.strip()}</Card>'
        for label, href, desc in rows
    )
    return f"<CardGroup cols={{3}}>\n{cards}\n</CardGroup>"


def description_of(body: str, base: Path) -> str:
    for raw in body.split("\n\n"):
        text = raw.strip()
        if not text or text.startswith(("#", "<", "```", "!", "|", "*", "-", ":")):
            continue
        text = re.sub(r"[*`\[\]]", "", convert_links(text, base))
        text = re.sub(r"\([^)]*\)", "", text)
        text = " ".join(text.split())
        if len(text) < 40:
            continue
        if len(text) > 155:
            text = text[:152].rsplit(" ", 1)[0] + "…"
        return text
    return ""


SHELL_FENCE = re.compile(
    r"^([ \t]*)```(bash|sh|shell|zsh|console)\s*\n(.*?)^\1```",
    re.DOTALL | re.MULTILINE,
)


def prefix_shell_commands(text: str) -> str:
    """A shell fence holds commands, so each line gets the ``$ `` prompt upstream writes.

    Without a prompt a shell fence renders as *output* (muted), which is what upstream's
    ``rehype-shiki`` does with it; the prompt is what makes it a session whose Copy keeps
    only the commands.
    """

    def add(match: re.Match[str]) -> str:
        indent, lang, body = match.group(1), match.group(2), match.group(3)
        if any(line.lstrip().startswith("$ ") for line in body.splitlines()):
            return match.group(0)
        lines = [
            f"{indent}$ {line[len(indent) :]}" if line.strip() else line
            for line in body.split("\n")
        ]
        return f"{indent}```{lang}\n" + "\n".join(lines)

    return SHELL_FENCE.sub(add, text)


def convert_body(body: str, base: Path) -> tuple[str, list[str]]:
    lines = body.split("\n")
    out: list[str] = []
    notes: list[str] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]

        # V1's link grid becomes the v2 card group (the same component upstream uses).
        if '<div class="doc-links"' in line:
            block, index = collect_div(lines, index)
            out.append(cards_from_links(block, base))
            notes.append("link grid -> CardGroup")
            continue

        admonition = ADMONITION.match(line)
        if admonition:
            kind, title = admonition.group(1), admonition.group(2) or ""
            index += 1
            buf: list[str] = []
            while index < total:
                if not lines[index].strip():
                    buf.append("")
                    index += 1
                    continue
                if indent_of(lines[index]) < 4:
                    break
                buf.append(lines[index])
                index += 1
            while buf and not buf[-1].strip():
                buf.pop()
            attrs = f'type="{kind}"'
            if title:
                attrs += f' title="{title}"'
            out.append(f"<Callout {attrs}>")
            out.append("")
            out.extend(dedent(buf))
            out.append("")
            out.append("</Callout>")
            notes.append(f"callout: {kind} “{title}”")
            continue

        # A lead paragraph: the paragraph before "{: .lead }".
        if LEAD.match(line):
            start = len(out)
            while start > 0 and out[start - 1].strip():
                start -= 1
            paragraph = " ".join(part.strip() for part in out[start:] if part.strip())
            del out[start:]
            out.append(f'<p class="lead">{paragraph}</p>')
            index += 1
            notes.append("lead paragraph")
            continue

        if line.lstrip().startswith("<div"):
            notes.append(f"raw HTML kept: {line.strip()[:60]}")

        if "`" not in line and "<" not in line:
            line = convert_links(line, base)

        out.append(line)
        index += 1

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Keep one blank line between sibling components, as the pages are written.
    text = re.sub(r"</(Callout|CardGroup)>\n<", r"</\1>\n\n<", text)
    text = prefix_shell_commands(text)
    return text.strip(), notes


def main() -> int:
    if not SOURCE.is_dir():
        print(f"no source docs at {SOURCE}")
        return 1

    converted = 0
    for source in sorted(SOURCE.rglob("*.md")):
        relative = source.relative_to(SOURCE)
        if relative.as_posix() in SKIP:
            print(f"skip   {relative} (authored by hand)")
            continue

        raw = FRONTMATTER.sub("", source.read_text(encoding="utf-8"))
        lines = raw.split("\n")
        title = ""
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            match = H1.match(line)
            if match:
                title = match.group(1).strip()
                lines = lines[:index] + lines[index + 1 :]
            break
        body = "\n".join(lines).strip()

        converted_body, notes = convert_body(body, relative.parent)
        slug = relative.with_suffix("").as_posix()
        title = title or NAV_TITLES.get(slug, slug)
        # Descriptions come from the page's own first paragraph, with includes inlined.
        expanded = snippets.resolve(
            converted_body, root=ROOT, relative_to=source.parent
        )
        description = description_of(expanded, relative.parent)

        target = TARGET / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "---\n"
            f'title: "{title}"\n'
            f'description: "{description}"\n'
            "---\n"
            "\n"
            f"{converted_body}\n",
            encoding="utf-8",
        )
        converted += 1
        print(f"write  {target.relative_to(ROOT)}   {', '.join(notes) or 'plain'}")

    print(f"\nmigrated {converted} pages into {TARGET.relative_to(ROOT)}")
    print("review the derived descriptions: they are the first paragraph, truncated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
