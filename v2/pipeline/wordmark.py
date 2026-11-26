"""The footer wordmark: ``universal-data-cleaner`` as a vector blueprint.

The letters are a blocky lowercase alphabet, five cells wide and seven tall, drawn on
a pixel grid. Each glyph's filled cells merge into horizontal runs, so a letter is one
path of rectangles; a thin stroke behind the fill traces the perimeter and the counters
(the fill covers the stroke's inner half, so no seams show between runs). A diagonal
hatch fills the letters, and every corner on the union's boundary gets a hollow square
node, like a vector editor's anchor points.

Geometry is in glyph cells (six units of advance, so one unit of gap) and scaled once
into the footer's own viewBox, so the wordmark scales with the reading column.
"""

from __future__ import annotations

CELL = 5  # a glyph is five cells wide
ROWS = 7  # and seven tall: x-height from row 2, ascenders from row 0
ADVANCE = CELL + 1
LINE_GAP = 2
LINES = ("universal", "data-cleaner")

GLYPHS: dict[str, tuple[str, ...]] = {
    "u": (
        ".....",
        ".....",
        "10001",
        "10001",
        "10001",
        "10001",
        "11111",
    ),
    "n": (
        ".....",
        ".....",
        "11111",
        "10001",
        "10001",
        "10001",
        "10001",
    ),
    "i": (
        "..1..",
        ".....",
        "..1..",
        "..1..",
        "..1..",
        "..1..",
        "..1..",
    ),
    "v": (
        ".....",
        ".....",
        "10001",
        "10001",
        "11011",
        "01110",
        "00100",
    ),
    "e": (
        ".....",
        ".....",
        "01110",
        "10000",
        "11110",
        "10000",
        "01110",
    ),
    "r": (
        ".....",
        ".....",
        "11111",
        "10001",
        "10000",
        "10000",
        "10000",
    ),
    "s": (
        ".....",
        ".....",
        "11111",
        "10000",
        "11111",
        "00001",
        "11111",
    ),
    "a": (
        ".....",
        ".....",
        "01111",
        "00001",
        "01111",
        "10001",
        "11111",
    ),
    "l": (
        "..1..",
        "..1..",
        "..1..",
        "..1..",
        "..1..",
        "..1..",
        "..1..",
    ),
    "d": (
        "....1",
        "....1",
        "11111",
        "10001",
        "10001",
        "10001",
        "01111",
    ),
    "t": (
        "..1..",
        "..1..",
        "11111",
        "..1..",
        "..1..",
        "..1..",
        "..111",
    ),
    "c": (
        ".....",
        ".....",
        "01110",
        "10000",
        "10000",
        "10000",
        "01110",
    ),
    "-": (
        ".....",
        ".....",
        ".....",
        "11111",
        ".....",
        ".....",
        ".....",
    ),
}

VIEW_WIDTH = 1000
PAD = 6  # room for the nodes and the outline, so nothing clips at the viewBox edge
NODE = 4  # viewBox units, about 4px at a 787px column
EDGE = 2.8  # outline width: half of it shows outside the fill, about 1px on screen


def _filled(glyph: str) -> set[tuple[int, int]]:
    rows = GLYPHS[glyph]
    return {
        (row, col)
        for row, line in enumerate(rows)
        for col, cell in enumerate(line)
        if cell == "1"
    }


def _runs(cells: set[tuple[int, int]]) -> list[tuple[int, int, int]]:
    """Merge a glyph's cells into horizontal runs: (col, row, width)."""
    runs: list[tuple[int, int, int]] = []
    for row in range(ROWS):
        col = 0
        while col < CELL:
            if (row, col) not in cells:
                col += 1
                continue
            start = col
            while col < CELL and (row, col) in cells:
                col += 1
            runs.append((start, row, col - start))
    return runs


def _corners(cells: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Every true corner on the union's boundary: a grid point where exactly one cell is
    filled (convex) or exactly three are (concave). Points along a straight edge have two
    filled neighbours and get no node, so the handles mark corners, not every cell."""
    points: set[tuple[int, int]] = set()
    for row, col in cells:
        for y, x in ((row, col), (row, col + 1), (row + 1, col), (row + 1, col + 1)):
            around = (
                (y - 1, x - 1),
                (y - 1, x),
                (y, x - 1),
                (y, x),
            )
            filled = sum(1 for cell in around if cell in cells)
            if filled in (1, 3):
                points.add((x, y))
    return points


def _num(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def wordmark() -> str:
    widest = max(len(line) for line in LINES)
    width_units = widest * ADVANCE - 1
    scale = VIEW_WIDTH / width_units
    height = ((len(LINES) * ROWS) + (len(LINES) - 1) * LINE_GAP) * scale

    letters: list[str] = []
    accents: list[str] = []
    nodes: list[str] = []
    for index, line in enumerate(LINES):
        top = PAD + index * (ROWS + LINE_GAP) * scale
        for slot, glyph in enumerate(line):
            cells = _filled(glyph)
            left = PAD + slot * ADVANCE * scale
            for col, row, run in _runs(cells):
                x = left + col * scale
                y = top + row * scale
                w = run * scale
                # The 'i' dot and the hyphen carry the brand accent, like the mark's
                # cyan cells; everything else is drawn in the theme's inks.
                target = (
                    accents
                    if (glyph == "-" or (glyph == "i" and row == 0))
                    else letters
                )
                target.append(
                    f"M{_num(x)} {_num(y)}h{_num(w)}v{_num(scale)}h-{_num(w)}z"
                )
            for x, y in _corners(cells):
                nodes.append(
                    f'<use href="#wm-node" x="{_num(left + x * scale)}" '
                    f'y="{_num(top + y * scale)}"/>'
                )

    return (
        f'<svg data-component="wordmark" '
        f'viewBox="0 0 {VIEW_WIDTH + 2 * PAD} {round(height + 2 * PAD)}" '
        f'role="img" aria-label="{"-".join(line for line in LINES)}">'
        "<defs>"
        '<pattern id="wm-hatch" width="8" height="8" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)">'
        '<rect class="wm-plate" width="8" height="8"/>'
        '<line class="wm-line" x1="0" y1="0" x2="0" y2="8" stroke-width="1.2"/>'
        "</pattern>"
        f'<rect id="wm-node" class="wm-node" x="{-NODE / 2}" y="{-NODE / 2}" '
        f'width="{NODE}" height="{NODE}" stroke-width="1" '
        'vector-effect="non-scaling-stroke"/>'
        "</defs>"
        f'<path class="wm-outline" d="{"".join(letters + accents)}" '
        f'stroke-width="{EDGE * 2}" stroke-linejoin="miter"/>'
        f'<path class="wm-letter" d="{"".join(letters)}"/>'
        f'<path class="wm-accent" d="{"".join(accents)}"/>'
        f'<g data-slot="nodes">{"".join(nodes)}</g>'
        "</svg>"
    )
