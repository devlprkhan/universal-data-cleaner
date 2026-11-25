"""Markdown → article HTML.

One renderer owns the transforms the docs' remark/rehype plugins do separately
upstream (``reference/PIPELINE.md`` §3):

* heading ids (GitHub style) + the h2/h3 list the Contents rail reads,
  with each h2/h3's text wrapped in a ``heading-link`` anchor
* ``<Callout>``/``<Card>``/``<CardGroup>``/``<CodeBlock>`` components, which are
  MDX upstream and a small scanner here
* tab sets (``=== "label"``, the one syntax this build keeps where upstream uses
  ``<CodeTabs tabs={[…]}/>``)
* every ``<table>`` wrapped in ``.docs-table-scroll``
* docs-root-relative links (``/quickstart/``) resolved for the page's depth
* smart punctuation, as ``remark-smartypants`` does

Content bodies start at ``##``; the ``<h1>`` comes from the frontmatter title.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from nav import depth_of

from . import code as code_module

# ───────────────────────────── inline ─────────────────────────────

CODE_SPAN = re.compile(r"`([^`]+)`")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
ITALIC = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<![\w_])_([^_\n]+)_(?![\w_])")
STRIKE = re.compile(r"~~(.+?)~~")

EXTERNAL = ("http://", "https://", "mailto:", "tel:")


def slugify(text: str) -> str:
    """Close to ``github-slugger`` for the heading text this site produces."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", " and ").replace("&", " and ")
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s_]+", "-", text).strip("-")


def smart(text: str) -> str:
    """The subset of ``remark-smartypants`` this content needs."""
    text = text.replace("...", "\u2026")
    text = re.sub(r"(?<=\d)--(?=\d)", "\u2013", text)
    text = text.replace("---", "\u2014").replace("--", "\u2013")
    text = re.sub(r'(^|[\s(\[{])"', lambda m: m.group(1) + "\u201c", text)
    text = text.replace('"', "\u201d")
    text = re.sub(r"(\w)'(\w)", lambda m: m.group(1) + "\u2019" + m.group(2), text)
    text = re.sub(r"(^|[\s(\[{])'", lambda m: m.group(1) + "\u2018", text)
    return text


@dataclass
class Heading:
    depth: int
    slug: str
    text: str


class Renderer:
    def __init__(self, slug: str, *, heading_levels: tuple[int, ...] = (2, 3)) -> None:
        self.slug = slug
        self.depth = depth_of(slug)
        self.up = "../" * self.depth
        self.heading_levels = heading_levels
        self.headings: list[Heading] = []
        self._seen_slugs: dict[str, int] = {}
        self._tabs = 0

    # ── urls ──

    def href(self, target: str) -> str:
        if not target or target.startswith(("#", *EXTERNAL)):
            return target
        path, _, frag = target.partition("#")
        suffix = f"#{frag}" if frag else ""
        if path.startswith("/"):
            resolved = self.up + path.lstrip("/")
        elif path.endswith(".md"):
            base = PurePosixPath(self.slug).parent
            merged = PurePosixPath(base, path).with_suffix("")
            resolved = self.up + str(merged)
        else:
            resolved = path
        if resolved.endswith("index/"):
            resolved = resolved[: -len("index/")]
        return resolved + suffix

    # ── inline ──

    def inline(self, text: str, *, smart_punct: bool = True) -> str:
        stash: list[str] = []

        def keep(value: str) -> str:
            stash.append(value)
            return f"\x00{len(stash) - 1}\x00"

        text = CODE_SPAN.sub(
            lambda m: keep(f"<code>{html.escape(m.group(1))}</code>"), text
        )
        text = IMAGE.sub(
            lambda m: keep(
                f'<img src="{html.escape(self.href(m.group(2)), quote=True)}" '
                f'alt="{html.escape(m.group(1), quote=True)}" loading="lazy">'
            ),
            text,
        )
        text = html.escape(text, quote=False)
        if smart_punct:
            text = smart(text)

        def link(match: re.Match[str]) -> str:
            label, target = match.group(1), match.group(2)
            resolved = self.href(target)
            external = target.startswith(EXTERNAL)
            extra = ' target="_blank" rel="noopener"' if external else ""
            return f'<a href="{html.escape(resolved, quote=True)}"{extra}>{label}</a>'

        text = LINK.sub(link, text)
        text = BOLD.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text)
        text = STRIKE.sub(r"<del>\1</del>", text)
        text = ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", text)
        text = re.sub(r"\x00(\d+)\x00", lambda m: stash[int(m.group(1))], text)
        return text

    # ── headings ──

    def heading(self, level: int, text: str, *, inline_html: str | None = None) -> str:
        slug = slugify(text) or "section"
        count = self._seen_slugs.get(slug, 0)
        self._seen_slugs[slug] = count + 1
        if count:
            slug = f"{slug}-{count}"
        plain = re.sub(r"<[^>]+>", "", re.sub(r"`([^`]*)`", r"\1", text)).strip()
        if level in self.heading_levels:
            self.headings.append(Heading(level, slug, plain))
            # The title is a button that copies the section's address (on-this-page.css),
            # so the heading's ink is never a link colour or underline.
            inner = (
                f'<button type="button" data-slot="heading-link" data-heading-link="#{slug}" '
                f'title="Copy link to {html.escape(plain, quote=True)}">'
                f"{inline_html or self.inline(text)}</button>"
            )
        else:
            inner = inline_html or self.inline(text)
        return f'<h{level} id="{slug}">{inner}</h{level}>'

    # ── components ──

    def callout(self, kind: str, title: str, body: str) -> str:
        kind = "caution" if kind == "warning" else (kind or "note")
        label = title or kind.capitalize()
        return (
            f'<aside data-component="callout" data-type="{html.escape(kind, quote=True)}" '
            f'aria-label="{html.escape(label, quote=True)}">'
            f"<strong>{html.escape(label)}</strong>"
            f"<div>{self.blocks(body.splitlines())}</div>"
            "</aside>"
        )

    def card(self, title: str, href: str, body: str) -> str:
        return (
            f'<a data-component="docs-card" href="{html.escape(self.href(href), quote=True)}">'
            f"<strong>{html.escape(title)}</strong>"
            f"<div>{self.blocks(body.splitlines())}</div>"
            "</a>"
        )

    def card_group(self, cols: str | None, body: str) -> str:
        style = (
            f' style="--card-columns: {html.escape(cols, quote=True)}"' if cols else ""
        )
        return (
            f'<div data-component="card-group"{style}>'
            f"{self.scan_components(body)}"
            "</div>"
        )

    def tabs(self, panels: list[tuple[str, str]]) -> str:
        self._tabs += 1
        group = f"code-tabs-{self._tabs}"
        buttons: list[str] = []
        bodies: list[str] = []
        for index, (label, body) in enumerate(panels):
            selected = index == 0
            panel_id = f"{group}-panel-{index}"
            buttons.append(
                f'<button type="button" role="tab" id="{group}-tab-{index}" data-code-tab '
                f'aria-selected="{"true" if selected else "false"}" '
                f'aria-controls="{panel_id}" tabindex="{0 if selected else -1}">{html.escape(label)}</button>'
            )
            hidden = "" if selected else " hidden"
            bodies.append(
                f'<div role="tabpanel" id="{panel_id}" data-slot="code" '
                f'aria-labelledby="{group}-tab-{index}"{hidden}>'
                f"{self.blocks(body.splitlines())}</div>"
            )
        return (
            '<div data-component="code-tabs">'
            '<div data-slot="head">'
            f'<div data-slot="tabs" role="tablist">{"".join(buttons)}</div>'
            '<button type="button" data-slot="copy" data-code aria-label="Copy code">Copy</button>'
            "</div>"
            f'<div data-slot="panels">{"".join(bodies)}</div>'
            "</div>"
        )

    # ── block scanning ──

    def blocks(self, lines: list[str]) -> str:
        out: list[str] = []
        index = 0
        total = len(lines)

        while index < total:
            line = lines[index]
            stripped = line.strip()

            if not stripped:
                index += 1
                continue

            # component: <Name ...>…</Name> or self-closing
            component = re.match(r"^<([A-Z][A-Za-z]*)\b", line)
            if component:
                block, index = self._component_block(lines, index)
                if block is not None:
                    out.append(block)
                    continue

            # raw HTML block: <div …> … </div>, <p …>, etc.
            if stripped.startswith("<"):
                block, index = self._raw_html(lines, index)
                out.append(block)
                continue

            fence = re.match(r"^```([\w+-]*)\s*(.*)$", line)
            if fence:
                lang = fence.group(1)
                info = fence.group(2)
                title = re.search(r'title="([^"]+)"', info)
                index += 1
                buf: list[str] = []
                while index < total and not lines[index].startswith("```"):
                    buf.append(lines[index])
                    index += 1
                index += 1
                out.append(
                    code_module.code_frame(
                        "\n".join(buf), lang, title.group(1) if title else None
                    )
                )
                continue

            if re.match(r'^===\s+"', line):
                panels: list[tuple[str, str]] = []
                while index < total:
                    match = re.match(r'^===\s+"([^"]*)"\s*$', lines[index])
                    if not match:
                        break
                    body, index = self._indented(lines, index + 1)
                    panels.append((match.group(1), body))
                    while index < total and not lines[index].strip():
                        index += 1
                out.append(self.tabs(panels))
                continue

            heading = re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
            if heading:
                out.append(self.heading(len(heading.group(1)), heading.group(2)))
                index += 1
                continue

            if re.match(r"^(-{3,}|\*{3,})\s*$", line):
                out.append("<hr>")
                index += 1
                continue

            if (
                stripped.startswith("|")
                and index + 1 < total
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[index + 1])
            ):
                rows: list[str] = []
                while index < total and lines[index].strip().startswith("|"):
                    rows.append(lines[index].strip())
                    index += 1
                out.append(self._table(rows))
                continue

            if stripped.startswith(">"):
                buf = []
                while index < total and lines[index].strip().startswith(">"):
                    buf.append(re.sub(r"^\s*>\s?", "", lines[index]))
                    index += 1
                out.append(f"<blockquote>{self.blocks(buf)}</blockquote>")
                continue

            if re.match(r"^\s*([-*+]|\d+[.)])\s+", line):
                block, index = self._list(lines, index)
                out.append(block)
                continue

            buf = []
            while index < total:
                current = lines[index]
                if not current.strip():
                    break
                if buf and self._starts_block(current) and not current.startswith(" "):
                    break
                buf.append(current.strip())
                index += 1
            text = " ".join(buf)
            if re.match(r"^\{:\s*\.lead\s*\}$", text):
                continue
            lead = False
            if text.endswith("{: .lead }"):
                text = text[: -len("{: .lead }")].strip()
                lead = True
            if re.match(r"^\{:[^}]*\}$", text):
                continue
            klass = ' class="lead"' if lead else ""
            out.append(f"<p{klass}>{self.inline(text)}</p>")

        return "\n".join(out)

    def _starts_block(self, line: str) -> bool:
        return bool(
            re.match(r"^(#{1,6}\s|```|===\s\"|>\s?|\||-{3,}\s*$)", line)
            or re.match(r"^\s*([-*+]|\d+[.)])\s+", line)
            or re.match(r"^<[A-Za-z/!]", line)
        )

    # ── helpers ──

    def _indented(
        self, lines: list[str], index: int, width: int = 4
    ) -> tuple[str, int]:
        buf: list[str] = []
        total = len(lines)
        while index < total:
            line = lines[index]
            if not line.strip():
                buf.append("")
                index += 1
                continue
            indent = len(line) - len(line.lstrip(" "))
            if indent < width:
                break
            buf.append(line[width:])
            index += 1
        while buf and not buf[-1].strip():
            buf.pop()
        return "\n".join(buf), index

    def _component_block(self, lines: list[str], index: int) -> tuple[str | None, int]:
        """A balanced ``<Name …>`` block, if the line starts a known component."""
        line = lines[index]
        head = re.match(r"^<([A-Z][A-Za-z]*)((?:\s+[^>]*?)?)>\s*$", line)
        self_closing = re.match(r"^<([A-Z][A-Za-z]*)((?:\s+[^>]*?)?)\s*/>\s*$", line)
        if self_closing:
            block = self._render_component(
                self_closing.group(1), self_closing.group(2), "", index
            )
            return block, index + 1
        if not head:
            return None, index

        name = head.group(1)
        open_tag = f"<{name}"
        close_tag = f"</{name}>"
        depth = 1
        body_lines: list[str] = []
        cursor = index + 1
        total = len(lines)
        while cursor < total:
            current = lines[cursor]
            depth += len(re.findall(rf"{re.escape(open_tag)}[\s>]", current))
            if close_tag in current:
                depth -= current.count(close_tag)
                if depth <= 0:
                    body_lines.append(current.split(close_tag)[0])
                    break
            body_lines.append(current)
            cursor += 1
        block = self._render_component(
            name, head.group(2), "\n".join(body_lines), index
        )
        if block is None:
            return None, index
        return block, cursor + 1

    def _attributes(self, raw: str) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for match in re.finditer(
            r'([A-Za-z][\w-]*)=(?:"([^"]*)"|\{([^}]*)\})', raw or ""
        ):
            attrs[match.group(1)] = (
                match.group(2) if match.group(2) is not None else match.group(3)
            )
        return attrs

    def _render_component(
        self, name: str, raw_attrs: str, body: str, index: int
    ) -> str | None:
        attrs = self._attributes(raw_attrs)
        if name == "Callout":
            return self.callout(attrs.get("type", "note"), attrs.get("title", ""), body)
        if name == "Card":
            return self.card(attrs.get("title", ""), attrs.get("href", "#"), body)
        if name == "CardGroup":
            return self.card_group(attrs.get("cols"), body)
        if name == "CodeBlock":
            code = attrs.get("code", "").replace("\\n", "\n")
            return code_module.code_frame(
                code, attrs.get("language", "text"), attrs.get("label")
            )
        return None

    def scan_components(self, body: str) -> str:
        """Render a component body that is mostly components (a card group)."""
        return self.blocks(body.splitlines())

    def _raw_html(self, lines: list[str], index: int) -> tuple[str, int]:
        """Pass an HTML block through until it closes (or a blank line ends it)."""
        buf: list[str] = []
        tag = re.match(r"^<([a-zA-Z][\w-]*)", lines[index])
        name = tag.group(1) if tag else ""
        closable = name.lower() not in {"br", "hr", "img", "input", "meta", "link"}
        depth = 0
        total = len(lines)
        while index < total:
            line = lines[index]
            if buf and not line.strip() and depth <= 0:
                break
            buf.append(line)
            if closable:
                depth += len(re.findall(rf"<{name}\b", line))
                depth -= len(re.findall(rf"</{name}>", line))
                if depth <= 0 and len(buf) > 1:
                    index += 1
                    break
            elif not line.strip():
                break
            index += 1
        return "\n".join(buf).strip(), index

    def _table(self, rows: list[str]) -> str:
        def cells(row: str) -> list[str]:
            row = row.strip().strip("|")
            return [cell.strip() for cell in re.split(r"(?<!\\)\|", row)]

        head = cells(rows[0])
        body = [cells(row) for row in rows[2:]]
        thead = "".join(f"<th>{self.inline(cell)}</th>" for cell in head)
        tbody = "".join(
            "<tr>" + "".join(f"<td>{self.inline(cell)}</td>" for cell in row) + "</tr>"
            for row in body
        )
        return (
            '<div class="docs-table-scroll" tabindex="0">'
            f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>"
            "</div>"
        )

    def _list(self, lines: list[str], index: int) -> tuple[str, int]:
        first = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[index])
        assert first is not None
        base = len(first.group(1))
        ordered = first.group(2)[0].isdigit()
        items: list[tuple[list[str], list[str]]] = []
        total = len(lines)

        while index < total:
            match = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", lines[index])
            if not match or len(match.group(1)) != base:
                break
            text = [match.group(3)]
            index += 1
            nested: list[str] = []
            while index < total:
                current = lines[index]
                if not current.strip():
                    look = index + 1
                    while look < total and not lines[look].strip():
                        look += 1
                    if (
                        look < total
                        and len(lines[look]) - len(lines[look].lstrip(" ")) > base
                    ):
                        index = look
                        continue
                    break
                indent = len(current) - len(current.lstrip(" "))
                if indent <= base:
                    break
                if re.match(r"^\s*([-*+]|\d+[.)])\s+", current) or nested:
                    nested.append(current)
                else:
                    text.append(current.strip())
                index += 1
            items.append((text, nested))

        tag = "ol" if ordered else "ul"
        out = [f"<{tag}>"]
        for text, nested in items:
            inner = self.inline(" ".join(text))
            if nested:
                dedented = [
                    line[base + 2 :]
                    if line.startswith(" " * (base + 2))
                    else line.lstrip(" ")
                    for line in nested
                ]
                inner += self.blocks(dedented)
            out.append(f"<li>{inner}</li>")
        out.append(f"</{tag}>")
        while index < total and not lines[index].strip():
            index += 1
        return "\n".join(out), index
