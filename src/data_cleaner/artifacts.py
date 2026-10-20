"""Reproducibility helpers: data fingerprints and environment metadata."""

from __future__ import annotations

import hashlib
import json
import math
import platform
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
import sklearn

from ._roles import _series_kind
from ._version import __version__


def package_versions() -> dict[str, str]:
    """Return the versions of the runtime that produced an artifact."""
    return {
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "scikit_learn": sklearn.__version__,
        "universal_data_cleaner": __version__,
    }


def _json_default(value: object) -> str:
    """Render unknown scalar types (timestamps, decimals) for JSON encoding."""
    return str(value)


def _canonical_number(value: Any) -> float | str | None:
    """Normalize a number so JSON hashing is stable and NaN-safe."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "nan"
    if math.isinf(number):
        return "inf" if number > 0 else "-inf"
    return round(number, 10)


def _column_stats(series: pd.Series) -> dict[str, object]:
    kind = _series_kind(series)
    stats: dict[str, object] = {
        "name": str(series.name),
        "kind": kind,
        "nulls": int(series.isna().sum()),
    }

    if kind == "numeric":
        numeric = pd.to_numeric(series, errors="coerce")
        numeric = numeric.replace([np.inf, -np.inf], np.nan).dropna()
        stats.update(
            {
                "count": int(numeric.size),
                "mean": _canonical_number(numeric.mean()) if numeric.size else None,
                "std": _canonical_number(numeric.std()) if numeric.size > 1 else None,
                "min": _canonical_number(numeric.min()) if numeric.size else None,
                "max": _canonical_number(numeric.max()) if numeric.size else None,
            }
        )
    elif kind == "boolean":
        valid = series.dropna()
        flags = valid.astype(bool)
        stats.update(
            {
                "count": int(valid.size),
                "true": int(flags.sum()),
                "false": int((~flags).sum()),
            }
        )
    elif kind == "datetime":
        valid = series.dropna()
        stats.update(
            {
                "count": int(valid.size),
                "min": str(valid.min()) if not valid.empty else None,
                "max": str(valid.max()) if not valid.empty else None,
            }
        )
    else:
        try:
            unique: int | None = int(series.nunique(dropna=True))
        except TypeError:
            unique = None
        stats.update({"count": int(series.notna().sum()), "unique": unique})

    return stats


def fingerprint_dataframe(
    frame: pd.DataFrame, columns: Sequence[str] | None = None
) -> str:
    """Return a stable SHA-256 fingerprint of a frame's schema and summary stats.

    The hash deliberately excludes raw values: it is a lineage fingerprint, not
    a row-level checksum. Column order participates in the hash, and summary
    statistics are rounded so the result is stable across platforms.

    Parameters
    ----------
    frame:
        DataFrame to fingerprint.
    columns:
        Optional subset/order of columns. Defaults to all columns in frame
        order.

    Raises
    ------
    TypeError
        If ``frame`` is not a pandas DataFrame.
    ValueError
        If ``frame`` has duplicate column names.
    KeyError
        If a requested column is missing from ``frame``.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    if frame.columns.has_duplicates:
        duplicates = frame.columns[frame.columns.duplicated()].tolist()
        raise ValueError(f"Duplicate column names are not allowed: {duplicates}")

    if columns is None:
        selected = list(frame.columns)
    else:
        selected = [str(column) for column in columns]
        missing = [column for column in selected if column not in frame.columns]
        if missing:
            raise KeyError(f"Columns not found in frame: {missing}")

    payload = {
        "n_rows": len(frame),
        "n_columns": len(selected),
        "columns": [_column_stats(frame[column]) for column in selected],
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compare_fingerprints(left: str, right: str) -> bool:
    """Return ``True`` when two fingerprints are identical."""
    return left == right


def assert_schema_stable(
    frame: pd.DataFrame, expected: str, *, name: str = "frame"
) -> None:
    """Raise ``ValueError`` when ``frame`` does not match ``expected``.

    ``expected`` is a fingerprint produced by :func:`fingerprint_dataframe`.
    """
    actual = fingerprint_dataframe(frame)
    if not compare_fingerprints(actual, expected):
        raise ValueError(
            f"{name} fingerprint {actual} does not match expected {expected}. "
            "The schema or summary statistics changed."
        )
