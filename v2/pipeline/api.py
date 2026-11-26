"""The API reference: generated from the package's own docstrings.

The page body in ``content/api.md`` is ordinary Markdown with one directive per
public object::

    ::: data_cleaner.DataCleaner

``render`` replaces each directive with the object's signature, docstring,
parameters, returns, and public methods. The markup uses the same ``doc``
classes the theme already styles (``.doc-heading``, ``.doc-signature``,
``.doc-contents``), so the reference keeps the look of the rest of the site
without depending on a separate MkDocs build.

The generator reads the installed package through :mod:`inspect`; the build
puts ``src/`` on ``sys.path`` first so the local sources are the source of
truth.
"""

from __future__ import annotations

import dataclasses
import html
import inspect
import re
import textwrap
from typing import Any

import data_cleaner

from .code import code_frame, highlight
from .render import Heading, Renderer

DIRECTIVE = re.compile(r"^::: +([\w.]+) *$", re.MULTILINE)
ROLE = re.compile(r":(?:class|func|meth|mod|attr|data|obj|exc|const):`([^`]+)`")
SECTION_RULE = re.compile(r"^\s*-{3,}\s*$")
SECTION_NAMES = {
    "Parameters",
    "Returns",
    "Yields",
    "Raises",
    "Attributes",
    "Examples",
    "Notes",
    "See Also",
    "Warnings",
    "References",
}
PUBLIC = frozenset(name for name in data_cleaner.__all__ if not name.startswith("__"))


# ───────────────────────────── docstrings ─────────────────────────────


def _short(name: str) -> str:
    return name.rsplit(".", 1)[-1]


def _role(match: re.Match[str]) -> str:
    """Turn a Sphinx role into a code span, linked when the name is on this page."""
    target = match.group(1).lstrip("~").strip().removesuffix("()")
    if target.startswith("data_cleaner."):
        short = target.removeprefix("data_cleaner.")
        shown = short
        anchor = target if short in PUBLIC else None
    elif "." not in target and target in PUBLIC:
        shown = target
        anchor = f"data_cleaner.{target}"
    else:
        shown = target
        anchor = None
    if anchor:
        return f"[`{shown}`](#{anchor})"
    return f"`{shown}`"


def _markdown(text: str) -> str:
    text = ROLE.sub(_role, text)
    # Docstrings use reStructuredText's double-backtick literal.
    return text.replace("``", "`")


def _is_section(lines: list[str], index: int) -> bool:
    return (
        lines[index].strip() in SECTION_NAMES
        and index + 1 < len(lines)
        and bool(SECTION_RULE.match(lines[index + 1]))
    )


def _split_sections(doc: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    lines = doc.splitlines()
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    index = 0
    while index < len(lines):
        if _is_section(lines, index):
            title = lines[index].strip()
            index += 2
            body: list[str] = []
            while index < len(lines) and not _is_section(lines, index):
                body.append(lines[index])
                index += 1
            sections.append((title, body))
        else:
            preamble.append(lines[index])
            index += 1
    return preamble, sections


def _entries(body: list[str]) -> list[dict[str, Any]]:
    """Parse ``name:`` / ``name : type`` entries and their indented descriptions."""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in body:
        if not line.strip():
            if current is not None:
                current["desc"].append("")
            continue
        if not line.startswith((" ", "\t")):
            head, _, type_ = line.partition(":")
            names = [name.strip() for name in head.split(",") if name.strip()]
            current = {"names": names, "type": type_.strip(), "desc": []}
            entries.append(current)
        elif current is not None:
            current["desc"].append(line)
    for entry in entries:
        entry["desc"] = textwrap.dedent("\n".join(entry["desc"])).strip()
    return entries


def _return_entry(body: list[str]) -> tuple[str, str]:
    lines = list(body)
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return "", ""
    first = lines[0].strip()
    rest = textwrap.dedent("\n".join(lines[1:])).strip()
    if ":" in first and not first.startswith(("tuple[", "list[", "dict[")):
        _, _, first = first.partition(":")
        first = first.strip()
    return first, rest


# ───────────────────────────── html helpers ─────────────────────────────


def _code(text: str) -> str:
    return f"<code>{html.escape(text, quote=False)}</code>"


class _Raw:
    """A string annotation rendered without the quotes ``inspect`` adds."""

    def __init__(self, text: str) -> None:
        self.text = text

    def __repr__(self) -> str:
        return self.text


def _annotation(value: object) -> str:
    if value is inspect.Parameter.empty or value is inspect.Signature.empty:
        return ""
    if isinstance(value, _Raw):
        return value.text
    if isinstance(value, str):
        return value.strip("'\"")
    return inspect.formatannotation(value)  # type: ignore[arg-type]


def _clean(signature: inspect.Signature) -> inspect.Signature:
    """Render string annotations as written, not as quoted literals."""
    params = [
        param.replace(
            annotation=_Raw(param.annotation.strip("'\""))
            if isinstance(param.annotation, str)
            else param.annotation
        )
        for param in signature.parameters.values()
    ]
    returns = (
        _Raw(signature.return_annotation.strip("'\""))
        if isinstance(signature.return_annotation, str)
        else signature.return_annotation
    )
    return signature.replace(parameters=params, return_annotation=returns)


def _table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return (
        '<div class="docs-table-scroll" tabindex="0"><table>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _description(renderer: Renderer, text: str) -> str:
    if not text:
        return ""
    return (
        '<div class="doc-md-description">'
        + renderer.blocks(_markdown(text).splitlines())
        + "</div>"
    )


def _default(param: inspect.Parameter | None, field: Any = None) -> str:
    if param is not None and param.default is not inspect.Parameter.empty:
        return _code(repr(param.default))
    if field is not None:
        if field.default is not dataclasses.MISSING:
            return _code(repr(field.default))
        if field.default_factory is not dataclasses.MISSING:
            return _code(f"default_factory={field.default_factory!r}")
    return "<em>required</em>"


def _parameters_table(
    renderer: Renderer,
    body: list[str],
    signature: inspect.Signature | None,
) -> str:
    entries = _entries(body)
    documented = {
        name.lstrip("*"): entry for entry in entries for name in entry["names"]
    }
    rows: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()

    if signature is not None:
        for name, param in signature.parameters.items():
            seen.add(name)
            entry = documented.get(name)
            kind = param.kind
            shown = name
            if kind is inspect.Parameter.VAR_POSITIONAL:
                shown = f"*{name}"
            elif kind is inspect.Parameter.VAR_KEYWORD:
                shown = f"**{name}"
            type_ = _annotation(param.annotation) or (entry or {}).get("type", "")
            rows.append(
                (
                    _code(shown),
                    _code(type_) if type_ else "",
                    _description(renderer, (entry or {}).get("desc", "")),
                    _default(param),
                )
            )

    for name, entry in documented.items():
        if name in seen:
            continue
        rows.append(
            (
                _code(name),
                _code(entry["type"]) if entry["type"] else "",
                _description(renderer, entry["desc"]),
                "<em>required</em>",
            )
        )

    if not rows:
        return ""
    return '<p><span class="doc-section-title">Parameters:</span></p>' + _table(
        ("Name", "Type", "Description", "Default"), rows
    )


def _dataclass_parameters(obj: type[Any]) -> inspect.Signature | None:
    """A signature for a dataclass so its fields still get a parameter table."""
    try:
        return inspect.signature(obj)
    except (TypeError, ValueError):
        return None


def _returns_table(
    renderer: Renderer,
    title: str,
    body: list[str],
    signature: inspect.Signature | None,
) -> str:
    type_, description = _return_entry(body)
    if not type_ and signature is not None:
        type_ = _annotation(signature.return_annotation)
    if not type_ and not description:
        return ""
    rows = [
        (
            _code(type_) if type_ else "",
            _description(renderer, description),
        )
    ]
    return (
        f'<p><span class="doc-section-title">{html.escape(title)}:</span></p>'
        + _table(("Type", "Description"), rows)
    )


def _raises_table(renderer: Renderer, body: list[str]) -> str:
    rows = [
        (
            _code(name),
            _description(renderer, entry["desc"]),
        )
        for entry in _entries(body)
        for name in entry["names"]
    ]
    if not rows:
        return ""
    return '<p><span class="doc-section-title">Raises:</span></p>' + _table(
        ("Type", "Description"), rows
    )


def _attributes_table(renderer: Renderer, body: list[str]) -> str:
    rows = [
        (
            _code(name),
            _code(entry["type"]) if entry["type"] else "",
            _description(renderer, entry["desc"]),
        )
        for entry in _entries(body)
        for name in entry["names"]
    ]
    if not rows:
        return ""
    return '<p><span class="doc-section-title">Attributes:</span></p>' + _table(
        ("Name", "Type", "Description"), rows
    )


def _section(renderer: Renderer, title: str, body: list[str]) -> str:
    text = textwrap.dedent("\n".join(body)).strip()
    if not text:
        return ""
    heading = f'<p><span class="doc-section-title">{html.escape(title)}:</span></p>'
    if title == "Examples" and ">>>" in text:
        prose, _, example = text.partition(">>>")
        example = ">>>" + example
        parts = [heading]
        if prose.strip():
            parts.append(renderer.blocks(_markdown(prose).splitlines()))
        parts.append(code_frame(example, "python"))
        return "".join(parts)
    return heading + renderer.blocks(_markdown(text).splitlines())


def _doc_html(
    renderer: Renderer,
    doc: str | None,
    signature: inspect.Signature | None,
    *,
    fallback: str = "",
) -> str:
    if not doc and not fallback:
        return ""
    preamble, sections = _split_sections(doc or "")
    out: list[str] = []
    text = _markdown("\n".join(preamble)).strip()
    if text:
        out.append(renderer.blocks(text.splitlines()))
    if fallback:
        out.append(fallback)
    for title, body in sections:
        if title == "Parameters":
            out.append(_parameters_table(renderer, body, signature))
        elif title in ("Returns", "Yields"):
            out.append(_returns_table(renderer, title, body, signature))
        elif title == "Raises":
            out.append(_raises_table(renderer, body))
        elif title == "Attributes":
            out.append(_attributes_table(renderer, body))
        else:
            out.append(_section(renderer, title, body))
    return "\n".join(part for part in out if part)


# ───────────────────────────── objects ─────────────────────────────


def _bases(obj: type[Any]) -> str:
    names = [
        base.__name__
        for base in obj.__bases__
        if base is not object and base.__name__ != "Protocol"
    ]
    if not names:
        return ""
    rendered = ", ".join(_code(name) for name in names)
    return f'<p class="doc doc-class-bases">Bases: {rendered}</p>'


def _signature(obj: Any, name: str) -> tuple[inspect.Signature | None, str]:
    try:
        signature = _clean(inspect.signature(obj))
    except (TypeError, ValueError):
        return None, ""
    text = f"{name}{signature}"
    if inspect.isclass(obj):
        text = re.sub(r" -> (?:None|'None'|\"None\")$", "", text)
    return signature, text


def _signature_html(text: str) -> str:
    return (
        '<div class="doc-signature highlight"><pre><span></span><code>'
        + highlight(text, "python")
        + "</code></pre></div>"
    )


def _heading(
    level: int,
    anchor: str,
    symbol: str,
    display: str,
    *,
    dataclass: bool = False,
) -> str:
    label = (
        '<span class="doc doc-labels"><small class="doc doc-label '
        'doc-label-dataclass"><code>dataclass</code></small></span>'
        if dataclass
        else ""
    )
    return (
        f'<h{level} id="{html.escape(anchor, quote=True)}" class="doc doc-heading">'
        f'<code class="doc-symbol doc-symbol-heading doc-symbol-{symbol}"></code>'
        f'<span class="doc doc-object-name doc-{symbol}-name">'
        f"{html.escape(display, quote=False)}</span>{label}</h{level}>"
    )


def _members(
    renderer: Renderer, obj: type[Any], anchor: str
) -> tuple[str, list[Heading]]:
    blocks: list[str] = []
    headings: list[Heading] = []
    for name, raw in obj.__dict__.items():
        if name.startswith("_"):
            continue
        func = None
        kind = "method"
        if isinstance(raw, (staticmethod, classmethod)):
            func = raw.__func__
        elif isinstance(raw, property):
            func = raw.fget
            kind = "attribute"
        elif inspect.isfunction(raw):
            func = raw
        if func is None:
            continue

        member_anchor = f"{anchor}.{name}"
        doc = inspect.getdoc(func)
        if kind == "attribute":
            blocks.append(
                '<div class="doc doc-object doc-attribute">'
                + _heading(3, member_anchor, "attribute", name)
                + '<div class="doc doc-contents">'
                + _doc_html(renderer, doc, None)
                + "</div></div>"
            )
        else:
            signature, text = _signature(func, name)
            if signature is not None:
                params = list(signature.parameters.values())
                if params and params[0].name in ("self", "cls"):
                    signature = signature.replace(parameters=params[1:])
                    text = f"{name}{signature}"
            blocks.append(
                '<div class="doc doc-object doc-function">'
                + _heading(3, member_anchor, "method", name)
                + _signature_html(text)
                + '<div class="doc doc-contents">'
                + _doc_html(renderer, doc, signature)
                + "</div></div>"
            )
        headings.append(Heading(3, member_anchor, name))
    if not blocks:
        return "", []
    return '<div class="doc doc-children">' + "".join(blocks) + "</div>", headings


def _object(renderer: Renderer, name: str) -> tuple[str, list[Heading]]:
    obj = getattr(data_cleaner, name)
    anchor = f"data_cleaner.{name}"
    headings = [Heading(2, anchor, anchor)]

    if inspect.isclass(obj):
        signature, text = _signature(obj, name)
        if signature is not None:
            params = list(signature.parameters.values())
            if params and params[0].name in ("self", "cls"):
                signature = signature.replace(parameters=params[1:])
                text = f"{name}{signature}"
        is_dataclass = dataclasses.is_dataclass(obj)
        doc = inspect.getdoc(obj)
        fallback = ""
        if is_dataclass and "Parameters" not in (doc or ""):
            fallback = _parameters_table(renderer, [], _dataclass_parameters(obj))
        doc_html = _doc_html(renderer, doc, signature, fallback=fallback)
        children, child_headings = _members(renderer, obj, anchor)
        headings.extend(child_headings)
        return (
            '<div class="doc doc-object doc-class">'
            + _heading(2, anchor, "class", anchor, dataclass=is_dataclass)
            + '<div class="doc doc-contents first">'
            + _bases(obj)
            + doc_html
            + children
            + "</div></div>",
            headings,
        )

    signature, text = _signature(obj, name)
    symbol = "function"
    return (
        '<div class="doc doc-object doc-function">'
        + _heading(2, anchor, symbol, anchor)
        + _signature_html(text)
        + '<div class="doc doc-contents">'
        + _doc_html(renderer, inspect.getdoc(obj), signature)
        + "</div></div>",
        headings,
    )


def render(renderer: Renderer, body: str) -> str:
    """Render the API page body, expanding every ``::: name`` directive."""
    parts: list[str] = []
    position = 0
    for match in DIRECTIVE.finditer(body):
        chunk = body[position : match.start()]
        if chunk.strip():
            parts.append(renderer.blocks(chunk.splitlines()))
        name = match.group(1).removeprefix("data_cleaner.")
        if name in PUBLIC:
            block, headings = _object(renderer, name)
            parts.append(block)
            renderer.headings.extend(headings)
        else:
            parts.append(
                f"<p><strong>Unknown API object:</strong> {html.escape(name)}</p>"
            )
        position = match.end()
    tail = body[position:]
    if tail.strip():
        parts.append(renderer.blocks(tail.splitlines()))
    return "\n".join(parts)
