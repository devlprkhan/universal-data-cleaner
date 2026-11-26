"""Fenced code → the site's code frame.

The Python stand-in for ``rehype-shiki.ts``: one function decides the frame's
variant from the fence language and its ``title="…"`` meta, and each variant
renders the markup the stylesheet styles plus the text its Copy button must
place on the clipboard.

Variants (mirroring upstream):

``fileTree``   ``text`` fence with a ``├──`` tree and no title
``terminal``   ``bash``/``sh``/``shell``/``zsh``/``console``; Copy keeps only ``$ `` lines
``codeDiff``   ``diff``; Copy drops removed lines
``codeTitle``  any fence with a ``title="…"``; a file-ish title gets a file icon
``code``       everything else, labelled by language

The copy text is not embedded in the markup: the client derives it from the
rendered rows (prompt spans for terminals, ``data-diff`` rows for diffs), which
is what keeps long code out of attributes.
"""

from __future__ import annotations

import html
import re

from pygments import highlight as pyg_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console", "fish"}
TREE_LANGS = {"text", "txt", "plaintext"}
TREE_PATTERN = re.compile(r"[├└]──")

LANGUAGE_LABELS = {
    "python": "Python",
    "py": "Python",
    "bash": "Terminal",
    "sh": "Terminal",
    "shell": "Terminal",
    "zsh": "Terminal",
    "console": "Terminal",
    "json": "JSON",
    "jsonc": "JSONC",
    "yaml": "YAML",
    "yml": "YAML",
    "toml": "TOML",
    "ini": "INI",
    "sql": "SQL",
    "diff": "Diff",
    "text": "Output",
    "txt": "Output",
    "plaintext": "Output",
    "html": "HTML",
    "css": "CSS",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "typescript": "TypeScript",
    "ts": "TypeScript",
}


def label_for(lang: str) -> str:
    return LANGUAGE_LABELS.get(lang, lang.upper() if lang else "")


def looks_like_file(title: str) -> bool:
    """Upstream: ``/[./]/.test(file) && !/\\s/.test(file)``."""
    return bool(re.search(r"[./]", title)) and not re.search(r"\s", title)


def is_tree(code: str, lang: str, title: str | None) -> bool:
    return not title and lang in TREE_LANGS and bool(TREE_PATTERN.search(code))


def highlight(code: str, lang: str) -> str:
    """Pygments, falling back to plain text for unknown languages (as upstream warns)."""
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        lexer = TextLexer()
    return pyg_highlight(code, lexer, HtmlFormatter(nowrap=True)).rstrip("\n")


def _frame(
    *,
    variant: str,
    body: str,
    label: str,
    lang: str,
    icon: str | None = None,
) -> str:
    icon_attr = f' data-file-icon="{html.escape(icon, quote=True)}"' if icon else ""
    return (
        f'<figure data-component="code-frame" data-variant="{variant}" data-kind="{lang}"{icon_attr}>'
        '<div data-slot="code-head">'
        f'<span data-slot="code-label">{html.escape(label)}</span>'
        '<button type="button" data-slot="copy" data-code data-funnel-copy="snippet" '
        'aria-label="Copy code">Copy</button>'
        "</div>"
        f"{body}"
        "</figure>"
    )


def _pre(inner: str, lang: str, *, attrs: str = "") -> str:
    return f'<pre tabindex="0" data-language="{lang}"{attrs}><code>{inner}</code></pre>'


def _terminal(code: str, lang: str) -> str:
    rows: list[str] = []
    for line in code.split("\n"):
        if line.startswith("$ "):
            command = highlight(line[2:], lang)
            rows.append(
                '<span data-token="prompt">$ <span data-slot="command">'
                f"{command}</span></span>"
            )
        else:
            rows.append(
                f'<span data-token="output">{highlight(line, lang) or "&nbsp;"}</span>'
            )
    return _pre("\n".join(rows), lang)


def _diff(code: str) -> str:
    rows: list[str] = []
    for line in code.split("\n"):
        if line.startswith("+"):
            kind, rest = "+", line[1:]
        elif line.startswith("-"):
            kind, rest = "-", line[1:]
        else:
            kind, rest = " ", line[1:] if line.startswith(" ") else line
        sign = kind if kind != " " else "&nbsp;"
        rows.append(
            f'<code data-diff="{kind}"><span data-slot="sign">{sign}</span>'
            f"{html.escape(rest) or '&nbsp;'}</code>"
        )
    return f'<pre data-component="code-diff" tabindex="0" data-language="diff"><code>{"".join(rows)}</code></pre>'


def _tree(code: str) -> str:
    rows: list[str] = []
    for line in code.split("\n"):
        rest = line
        depth = 0
        while rest.startswith(("│   ", "    ")):
            depth += 1
            rest = rest[4:]
        marker = ""
        if rest.startswith(("├── ", "└── ")):
            marker = "branch"
            rest = rest[4:]
        elif rest.startswith("│"):
            marker = "pipe"
            rest = rest[1:]
        kind = "dir" if rest.endswith("/") else "file"
        marker_html = f'<span data-slot="tree-marker">{marker}</span>' if marker else ""
        rows.append(
            f'<span data-tree-row data-depth="{depth}" data-kind="{kind}">'
            f'{marker_html}<span data-slot="tree-name">{html.escape(rest)}</span></span>'
        )
    return (
        '<pre data-component="file-tree" tabindex="0"><code>'
        + "".join(rows)
        + "</code></pre>"
    )


def code_frame(code: str, lang: str, title: str | None = None) -> str:
    """Render one fenced block as a code frame."""
    lang = (lang or "text").strip().lower()
    code = code.rstrip("\n")

    if is_tree(code, lang, title):
        return _frame(variant="fileTree", body=_tree(code), label="", lang="tree")

    if lang in SHELL_LANGS:
        return _frame(
            variant="terminal",
            body=_terminal(code, lang),
            label=label_for(lang),
            lang=lang,
        )

    if lang == "diff":
        return _frame(variant="codeDiff", body=_diff(code), label="Diff", lang="diff")

    if title:
        icon = title.removesuffix(" (excerpt)")
        return _frame(
            variant="codeTitle",
            body=_pre(highlight(code, lang), lang),
            label=title,
            lang=lang,
            icon=icon if looks_like_file(icon) else None,
        )

    return _frame(
        variant="code",
        body=_pre(highlight(code, lang), lang),
        label=label_for(lang),
        lang=lang,
    )
