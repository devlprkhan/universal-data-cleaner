"""Join diagnostics, referential integrity, and business-key deduplication."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

JoinHow = Literal["left", "right", "inner", "outer"]
JoinCardinality = Literal["1:1", "1:m", "m:1", "m:m"]
Keep = Literal["first", "last"]


def _normalize_keys(keys: str | Sequence[str], *, argument: str) -> tuple[str, ...]:
    normalized = (keys,) if isinstance(keys, str) else tuple(keys)
    if not normalized:
        raise ValueError(f"{argument} must contain at least one column")
    if not all(isinstance(key, str) for key in normalized):
        raise TypeError(f"{argument} columns must be strings")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{argument} contains duplicate columns: {list(normalized)}")
    return normalized


def _require_columns(
    frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str
) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"{frame_name} is missing key column(s): {missing}")


def _require_unique_columns(frame: pd.DataFrame, *, frame_name: str) -> None:
    if frame.columns.has_duplicates:
        duplicates = frame.columns[frame.columns.duplicated()].tolist()
        raise ValueError(f"{frame_name} contains duplicate column names: {duplicates}")


def _duplicate_stats(
    frame: pd.DataFrame, keys: tuple[str, ...]
) -> tuple[int, int, int]:
    """Return (duplicate keys, duplicate rows, null-key rows)."""
    valid = frame.dropna(subset=list(keys))
    null_rows = int(len(frame) - len(valid))
    if valid.empty:
        return 0, 0, null_rows
    counts = valid.groupby(list(keys), dropna=False, observed=True).size()
    duplicate_keys = int((counts > 1).sum())
    duplicate_rows = int(counts[counts > 1].sum())
    return duplicate_keys, duplicate_rows, null_rows


def _cardinality_matches(
    validate: str | None, left_cardinality: str, right_cardinality: str
) -> bool:
    if validate is None or validate == "m:m":
        return True
    if validate == "1:1":
        return left_cardinality == "1" and right_cardinality == "1"
    if validate == "1:m":
        return left_cardinality == "1"
    if validate == "m:1":
        return right_cardinality == "1"
    return True


@dataclass(frozen=True, slots=True)
class JoinDiagnosis:
    """Findings from a join cardinality and row-preservation check."""

    how: str
    on: tuple[str, ...]
    validate: str | None
    left_rows: int
    right_rows: int
    output_rows: int
    row_multiplier: float
    left_cardinality: str
    right_cardinality: str
    cardinality: str
    cardinality_matches: bool
    left_duplicate_keys: int
    right_duplicate_keys: int
    left_duplicate_rows: int
    right_duplicate_rows: int
    left_null_keys: int
    right_null_keys: int
    unmatched_left: int
    unmatched_right: int
    safe: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation of the diagnosis."""
        return {
            "how": self.how,
            "on": list(self.on),
            "validate": self.validate,
            "left_rows": self.left_rows,
            "right_rows": self.right_rows,
            "output_rows": self.output_rows,
            "row_multiplier": self.row_multiplier,
            "left_cardinality": self.left_cardinality,
            "right_cardinality": self.right_cardinality,
            "cardinality": self.cardinality,
            "cardinality_matches": self.cardinality_matches,
            "left_duplicate_keys": self.left_duplicate_keys,
            "right_duplicate_keys": self.right_duplicate_keys,
            "left_duplicate_rows": self.left_duplicate_rows,
            "right_duplicate_rows": self.right_duplicate_rows,
            "left_null_keys": self.left_null_keys,
            "right_null_keys": self.right_null_keys,
            "unmatched_left": self.unmatched_left,
            "unmatched_right": self.unmatched_right,
            "safe": self.safe,
            "warnings": list(self.warnings),
        }

    def to_markdown(self) -> str:
        """Render the diagnosis as a Markdown table."""
        rows = [
            ("how", self.how),
            ("on", ", ".join(self.on)),
            ("observed cardinality", self.cardinality),
            ("expected cardinality", self.validate or "not specified"),
            ("left rows", self.left_rows),
            ("right rows", self.right_rows),
            ("output rows", self.output_rows),
            ("row multiplier", f"{self.row_multiplier:.2f}"),
            ("left duplicate keys", self.left_duplicate_keys),
            ("right duplicate keys", self.right_duplicate_keys),
            ("unmatched left rows", self.unmatched_left),
            ("unmatched right rows", self.unmatched_right),
            ("safe", self.safe),
        ]
        lines = ["| metric | value |", "| --- | --- |"]
        lines.extend(f"| {name} | {value} |" for name, value in rows)
        if self.warnings:
            lines.append("")
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines)

    def raise_if_unsafe(self, message: str = "Join is not safe") -> None:
        """Raise ``ValueError`` when the diagnosis is not safe."""
        if not self.safe:
            details = "\n".join(f"- {warning}" for warning in self.warnings)
            raise ValueError(f"{message}:\n{details}" if details else message)


def diagnose_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: str | Sequence[str],
    how: JoinHow = "left",
    validate: JoinCardinality | None = "1:1",
) -> JoinDiagnosis:
    """Diagnose key duplication, cardinality, and row preservation for a join.

    Parameters
    ----------
    left, right:
        Frames to join. Only key columns are inspected.
    on:
        Key column name or names. Both frames must contain every key.
    how:
        One of ``"left"``, ``"right"``, ``"inner"``, or ``"outer"``.
    validate:
        Expected maximum cardinality: ``"1:1"``, ``"1:m"``, ``"m:1"``,
        ``"m:m"``, or ``None`` to skip the cardinality check.

    Notes
    -----
    ``row_multiplier`` is ``output_rows / len(left)`` and is ``0.0`` when the
    left frame is empty. ``safe`` is false when the join violates the requested
    cardinality, multiplies rows on the preserved side of a left/right join, or
    has null keys.
    """
    if not isinstance(left, pd.DataFrame) or not isinstance(right, pd.DataFrame):
        raise TypeError("left and right must be pandas DataFrames")
    if how not in {"left", "right", "inner", "outer"}:
        raise ValueError("how must be one of 'left', 'right', 'inner', 'outer'")
    if validate not in {None, "1:1", "1:m", "m:1", "m:m"}:
        raise ValueError("validate must be one of None, '1:1', '1:m', 'm:1', 'm:m'")

    keys = _normalize_keys(on, argument="on")
    _require_unique_columns(left, frame_name="left")
    _require_unique_columns(right, frame_name="right")
    _require_columns(left, keys, frame_name="left")
    _require_columns(right, keys, frame_name="right")

    left_dup_keys, left_dup_rows, left_null = _duplicate_stats(left, keys)
    right_dup_keys, right_dup_rows, right_null = _duplicate_stats(right, keys)
    left_cardinality = "1" if left_dup_keys == 0 else "m"
    right_cardinality = "1" if right_dup_keys == 0 else "m"
    cardinality = f"{left_cardinality}:{right_cardinality}"
    cardinality_matches = _cardinality_matches(
        validate, left_cardinality, right_cardinality
    )

    outer = left[list(keys)].merge(
        right[list(keys)], on=list(keys), how="outer", indicator=True
    )
    if "_merge" in outer.columns:
        merge_values = outer["_merge"]
    else:  # pragma: no cover - pandas always adds the indicator
        merge_values = pd.Series([], dtype=object)
    both = int((merge_values == "both").sum())
    left_only = int((merge_values == "left_only").sum())
    right_only = int((merge_values == "right_only").sum())

    if how == "left":
        output_rows = both + left_only
    elif how == "right":
        output_rows = both + right_only
    elif how == "inner":
        output_rows = both
    else:
        output_rows = both + left_only + right_only

    unmatched_left = left_only
    unmatched_right = right_only
    row_multiplier = output_rows / len(left) if len(left) else 0.0

    warnings: list[str] = []
    if left_dup_keys:
        warnings.append(
            f"left key is not unique ({left_dup_keys} duplicate key(s); m:m join)"
        )
    if right_dup_keys:
        warnings.append(
            f"right key is not unique ({right_dup_keys} duplicate key(s); m:m join)"
        )
    if left_null:
        warnings.append(f"left key contains {left_null} row(s) with null values")
    if right_null:
        warnings.append(f"right key contains {right_null} row(s) with null values")
    if validate is not None and not cardinality_matches:
        warnings.append(
            f"observed cardinality {cardinality} does not match expected {validate}"
        )
    if how == "left" and output_rows > len(left):
        warnings.append(
            f"join multiplied rows from {len(left)} to {output_rows} "
            f"(x{row_multiplier:.2f})"
        )
    if how == "right" and output_rows > len(right):
        warnings.append(
            f"join multiplied rows from {len(right)} to {output_rows} "
            f"(x{row_multiplier:.2f})"
        )
    if how == "inner" and (unmatched_left or unmatched_right):
        warnings.append(
            f"inner join dropped {unmatched_left} left and "
            f"{unmatched_right} right unmatched row(s)"
        )
    if how in {"left", "outer"} and unmatched_left:
        warnings.append(f"{unmatched_left} left row(s) had no match")
    if how in {"right", "outer"} and unmatched_right:
        warnings.append(f"{unmatched_right} right row(s) had no match")

    no_null_keys = left_null == 0 and right_null == 0
    if how == "left":
        row_preserved = output_rows == len(left)
    elif how == "right":
        row_preserved = output_rows == len(right)
    elif how == "outer":
        row_preserved = output_rows >= max(len(left), len(right))
    else:
        row_preserved = True
    safe = cardinality_matches and row_preserved and no_null_keys

    return JoinDiagnosis(
        how=how,
        on=keys,
        validate=validate,
        left_rows=len(left),
        right_rows=len(right),
        output_rows=output_rows,
        row_multiplier=float(row_multiplier),
        left_cardinality=left_cardinality,
        right_cardinality=right_cardinality,
        cardinality=cardinality,
        cardinality_matches=cardinality_matches,
        left_duplicate_keys=left_dup_keys,
        right_duplicate_keys=right_dup_keys,
        left_duplicate_rows=left_dup_rows,
        right_duplicate_rows=right_dup_rows,
        left_null_keys=left_null,
        right_null_keys=right_null,
        unmatched_left=unmatched_left,
        unmatched_right=unmatched_right,
        safe=safe,
        warnings=tuple(warnings),
    )


@dataclass(frozen=True, slots=True)
class ReferentialIntegrityReport:
    """Findings from a child-to-parent key integrity check."""

    child_key: tuple[str, ...]
    parent_key: tuple[str, ...]
    child_rows: int
    parent_rows: int
    matched_rows: int
    orphan_rows: int
    orphan_key_count: int
    orphan_keys: tuple[tuple[object, ...], ...]
    null_child_keys: int
    null_parent_keys: int
    parent_duplicate_keys: int
    valid: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation of the report."""
        return {
            "child_key": list(self.child_key),
            "parent_key": list(self.parent_key),
            "child_rows": self.child_rows,
            "parent_rows": self.parent_rows,
            "matched_rows": self.matched_rows,
            "orphan_rows": self.orphan_rows,
            "orphan_key_count": self.orphan_key_count,
            "orphan_keys": [list(key) for key in self.orphan_keys],
            "null_child_keys": self.null_child_keys,
            "null_parent_keys": self.null_parent_keys,
            "parent_duplicate_keys": self.parent_duplicate_keys,
            "valid": self.valid,
            "warnings": list(self.warnings),
        }

    def to_markdown(self) -> str:
        """Render the report as a Markdown table."""
        rows = [
            ("child key", ", ".join(self.child_key)),
            ("parent key", ", ".join(self.parent_key)),
            ("child rows", self.child_rows),
            ("parent rows", self.parent_rows),
            ("matched rows", self.matched_rows),
            ("orphan rows", self.orphan_rows),
            ("orphan keys", self.orphan_key_count),
            ("null child keys", self.null_child_keys),
            ("null parent keys", self.null_parent_keys),
            ("parent duplicate keys", self.parent_duplicate_keys),
            ("valid", self.valid),
        ]
        lines = ["| metric | value |", "| --- | --- |"]
        lines.extend(f"| {name} | {value} |" for name, value in rows)
        if self.orphan_keys:
            lines.append("")
            examples = ", ".join(str(key) for key in self.orphan_keys)
            lines.append(f"Orphan key examples: {examples}")
        if self.warnings:
            lines.append("")
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines)

    def raise_if_invalid(
        self, message: str = "Referential integrity check failed"
    ) -> None:
        """Raise ``ValueError`` when the relationship is not valid."""
        if not self.valid:
            details = "\n".join(f"- {warning}" for warning in self.warnings)
            raise ValueError(f"{message}:\n{details}" if details else message)


def check_referential_integrity(
    child: pd.DataFrame,
    parent: pd.DataFrame,
    child_key: str | Sequence[str],
    parent_key: str | Sequence[str] | None = None,
    *,
    allow_null_keys: bool = True,
) -> ReferentialIntegrityReport:
    """Check that every non-null child key exists in the parent table.

    ``parent_key`` defaults to ``child_key``. Null child keys are reported
    separately and are allowed by default; set ``allow_null_keys=False`` to
    make them invalid. Duplicate parent keys make the relationship invalid
    because the parent key is not a unique reference target. ``orphan_keys``
    contains up to 10 distinct examples; ``orphan_key_count`` is the total.
    """
    if not isinstance(child, pd.DataFrame) or not isinstance(parent, pd.DataFrame):
        raise TypeError("child and parent must be pandas DataFrames")
    _require_unique_columns(child, frame_name="child")
    _require_unique_columns(parent, frame_name="parent")

    child_keys = _normalize_keys(child_key, argument="child_key")
    parent_keys = (
        child_keys
        if parent_key is None
        else _normalize_keys(parent_key, argument="parent_key")
    )
    if len(child_keys) != len(parent_keys):
        raise ValueError(
            "child_key and parent_key must have the same number of columns"
        )
    _require_columns(child, child_keys, frame_name="child")
    _require_columns(parent, parent_keys, frame_name="parent")

    child_non_null = child.dropna(subset=list(child_keys))
    null_child_keys = int(len(child) - len(child_non_null))
    parent_non_null = parent.dropna(subset=list(parent_keys))
    null_parent_keys = int(len(parent) - len(parent_non_null))

    if parent_non_null.empty:
        parent_duplicate_keys = 0
    else:
        counts = parent_non_null.groupby(
            list(parent_keys), dropna=False, observed=True
        ).size()
        parent_duplicate_keys = int((counts > 1).sum())

    parent_unique = parent_non_null[list(parent_keys)].drop_duplicates()

    orphan_rows = 0
    orphan_key_count = 0
    orphan_keys: tuple[tuple[object, ...], ...] = ()
    matched_rows = 0
    if not child_non_null.empty:
        if child_keys == parent_keys:
            merged = child_non_null[list(child_keys)].merge(
                parent_unique, on=list(child_keys), how="left", indicator=True
            )
        else:
            merged = child_non_null[list(child_keys)].merge(
                parent_unique,
                left_on=list(child_keys),
                right_on=list(parent_keys),
                how="left",
                indicator=True,
            )
        orphan_mask = merged["_merge"] == "left_only"
        orphan_rows = int(orphan_mask.sum())
        orphan_frame = merged.loc[orphan_mask, list(child_keys)].drop_duplicates()
        orphan_key_count = len(orphan_frame)
        orphan_keys = tuple(
            tuple(row) for row in orphan_frame.itertuples(index=False, name=None)
        )[:10]
        matched_rows = int(len(child_non_null) - orphan_rows)

    warnings: list[str] = []
    if orphan_rows:
        warnings.append(f"{orphan_rows} child row(s) reference missing parent key(s)")
    if parent_duplicate_keys:
        warnings.append(
            f"parent key is not unique ({parent_duplicate_keys} duplicate key(s))"
        )
    if null_child_keys:
        suffix = "" if allow_null_keys else " (not allowed)"
        warnings.append(f"child key contains {null_child_keys} null row(s){suffix}")
    if null_parent_keys:
        warnings.append(f"parent key contains {null_parent_keys} null row(s)")

    valid = (
        orphan_rows == 0
        and parent_duplicate_keys == 0
        and (allow_null_keys or null_child_keys == 0)
    )

    return ReferentialIntegrityReport(
        child_key=child_keys,
        parent_key=parent_keys,
        child_rows=len(child),
        parent_rows=len(parent),
        matched_rows=matched_rows,
        orphan_rows=orphan_rows,
        orphan_key_count=orphan_key_count,
        orphan_keys=orphan_keys,
        null_child_keys=null_child_keys,
        null_parent_keys=null_parent_keys,
        parent_duplicate_keys=parent_duplicate_keys,
        valid=valid,
        warnings=tuple(warnings),
    )


@dataclass(eq=False)
class DeduplicationReport:
    """Audit trail for :func:`deduplicate_by_business_key`."""

    key: tuple[str, ...]
    keep: str
    tie_breaker: tuple[str, ...] | None
    input_rows: int
    output_rows: int
    removed_rows: int
    duplicate_keys: int
    null_key_rows: int
    removed: pd.DataFrame
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly summary (without the removed rows)."""
        return {
            "key": list(self.key),
            "keep": self.keep,
            "tie_breaker": list(self.tie_breaker) if self.tie_breaker else None,
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "removed_rows": self.removed_rows,
            "duplicate_keys": self.duplicate_keys,
            "null_key_rows": self.null_key_rows,
            "warnings": list(self.warnings),
        }

    def to_markdown(self) -> str:
        """Render the report as a Markdown table."""
        rows = [
            ("key", ", ".join(self.key)),
            ("keep", self.keep),
            (
                "tie breaker",
                ", ".join(self.tie_breaker) if self.tie_breaker else "none",
            ),
            ("input rows", self.input_rows),
            ("output rows", self.output_rows),
            ("removed rows", self.removed_rows),
            ("duplicate keys", self.duplicate_keys),
            ("null-key rows", self.null_key_rows),
        ]
        lines = ["| metric | value |", "| --- | --- |"]
        lines.extend(f"| {name} | {value} |" for name, value in rows)
        if self.warnings:
            lines.append("")
            lines.extend(f"- {warning}" for warning in self.warnings)
        lines.append("")
        lines.append("Removed rows are available in `.removed`.")
        return "\n".join(lines)


def deduplicate_by_business_key(
    frame: pd.DataFrame,
    key: str | Sequence[str],
    keep: Keep = "first",
    tie_breaker: str | Sequence[str] | None = None,
) -> tuple[pd.DataFrame, DeduplicationReport]:
    """Deduplicate rows by a business key and report what was removed.

    ``keep`` selects the first or last row per key. ``tie_breaker`` sorts rows
    within each key before selecting and prefers non-null values. The returned
    frame preserves the input row order and index, and the input is never
    mutated.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    if keep not in {"first", "last"}:
        raise ValueError("keep must be 'first' or 'last'")
    _require_unique_columns(frame, frame_name="frame")

    keys = _normalize_keys(key, argument="key")
    _require_columns(frame, keys, frame_name="frame")
    tie_breakers = (
        None
        if tie_breaker is None
        else _normalize_keys(tie_breaker, argument="tie_breaker")
    )
    if tie_breakers is not None:
        _require_columns(frame, tie_breakers, frame_name="frame")

    counts = frame.groupby(list(keys), dropna=False, observed=True).size()
    duplicate_keys = int((counts > 1).sum())
    null_key_rows = int(frame[list(keys)].isna().any(axis=1).sum())

    temp = "__udc_position__"
    while temp in frame.columns:
        temp = "_" + temp
    working = frame.copy()
    working[temp] = np.arange(len(frame), dtype=np.int64)

    if tie_breakers is not None:
        na_position: Literal["first", "last"] = "last" if keep == "first" else "first"
        working = working.sort_values(
            by=[*tie_breakers, temp],
            ascending=[True] * (len(tie_breakers) + 1),
            na_position=na_position,
            kind="mergesort",
        )

    keep_mask = ~working.duplicated(subset=list(keys), keep=keep)
    kept_positions = working[temp].to_numpy()[keep_mask.to_numpy()]
    mask = working[temp].isin(kept_positions).to_numpy()
    deduplicated = (
        working.iloc[np.flatnonzero(mask)].sort_values(temp).drop(columns=[temp])
    )
    removed = working.iloc[np.flatnonzero(~mask)].sort_values(temp).drop(columns=[temp])

    warnings: list[str] = []
    if null_key_rows:
        warnings.append(
            f"{null_key_rows} row(s) have null key values and were deduplicated "
            "as a group"
        )
    if tie_breakers is not None and set(tie_breakers) & set(keys):
        warnings.append("tie_breaker overlaps with key and cannot break ties")

    report = DeduplicationReport(
        key=keys,
        keep=keep,
        tie_breaker=tie_breakers,
        input_rows=len(frame),
        output_rows=len(deduplicated),
        removed_rows=len(removed),
        duplicate_keys=duplicate_keys,
        null_key_rows=null_key_rows,
        removed=removed,
        warnings=tuple(warnings),
    )
    return deduplicated, report
