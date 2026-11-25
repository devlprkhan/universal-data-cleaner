"""``--8<-- "FILE"`` includes.

The two pages that mirror repository files (``CHANGELOG.md``, ``ROADMAP.md``)
stay single-sourced instead of being copied into ``content/``: the build inlines
them, as MkDocs' ``pymdownx.snippets`` did for V1. Paths resolve against the
repository root, then against the including file's directory.
"""

from __future__ import annotations

import re
from pathlib import Path

DIRECTIVE = re.compile(r'^\s*--8<--\s+"([^"]+)"\s*$')
MAX_DEPTH = 8


def resolve(
    text: str, *, root: Path, relative_to: Path | None = None, depth: int = 0
) -> str:
    """Inline every snippet directive, recursively."""
    if depth > MAX_DEPTH:
        return text
    out: list[str] = []
    for line in text.splitlines():
        match = DIRECTIVE.match(line)
        if not match:
            out.append(line)
            continue
        target = root / match.group(1)
        if not target.is_file() and relative_to is not None:
            target = relative_to / match.group(1)
        if not target.is_file():
            out.append(f"<!-- missing snippet: {match.group(1)} -->")
            continue
        out.append(
            resolve(
                target.read_text(encoding="utf-8"),
                root=root,
                relative_to=target.parent,
                depth=depth + 1,
            ).rstrip()
        )
    return "\n".join(out)
