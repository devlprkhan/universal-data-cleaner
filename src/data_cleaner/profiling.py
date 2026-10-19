"""Standalone profiling and validation helpers."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd


def profile_dataframe(frame: pd.DataFrame, name: str = "dataset") -> pd.DataFrame:
    """Create a column-level data quality profile."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")

    rows: list[dict[str, object]] = []
    row_count = len(frame)
    for column in frame.columns:
        series = frame[column]
        non_null = int(series.notna().sum())
        missing = int(row_count - non_null)
        mode_values = series.dropna().mode()
        rows.append(
            {
                "dataset": name,
                "column": column,
                "dtype": str(series.dtype),
                "non_null": non_null,
                "missing": missing,
                "missing_pct": round(
                    (missing / row_count * 100) if row_count else 0.0, 2
                ),
                "unique": int(series.nunique(dropna=True)),
                "top": mode_values.iloc[0] if not mode_values.empty else None,
                "top_freq": int(series.eq(mode_values.iloc[0]).sum())
                if not mode_values.empty
                else 0,
            }
        )
    return pd.DataFrame(rows)


def dataset_summary(frame: pd.DataFrame) -> dict[str, object]:
    """Return dataset-level quality metrics."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    total_cells = int(frame.shape[0] * frame.shape[1])
    missing_cells = int(frame.isna().sum().sum())
    return {
        "rows": int(frame.shape[0]),
        "columns": int(frame.shape[1]),
        "duplicate_rows": int(frame.duplicated().sum()),
        "total_cells": total_cells,
        "missing_cells": missing_cells,
        "missing_pct": round(
            (missing_cells / total_cells * 100) if total_cells else 0.0, 2
        ),
        "memory_bytes": int(frame.memory_usage(deep=True).sum()),
    }


def drop_duplicate_rows(
    frame: pd.DataFrame,
    subset: list[str] | None = None,
    keep: Literal["first", "last"] = "first",
) -> tuple[pd.DataFrame, int]:
    """Drop exact duplicates and return ``(deduplicated_frame, rows_removed)``."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    deduplicated = frame.drop_duplicates(subset=subset, keep=keep)
    return deduplicated, int(len(frame) - len(deduplicated))


def assert_frame_clean(frame: pd.DataFrame, *, allow_empty: bool = True) -> None:
    """Assert that a cleaned frame has no missing/infinite values."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    if frame.columns.has_duplicates:
        raise AssertionError("cleaned frame contains duplicate column names")
    if not allow_empty and frame.empty:
        raise AssertionError("cleaned frame is empty")

    missing_by_column = frame.isna().sum()
    if bool((missing_by_column > 0).any()):
        details = missing_by_column[missing_by_column > 0].to_dict()
        raise AssertionError(f"cleaned frame still has missing values: {details}")

    numeric = frame.select_dtypes(include=[np.number])
    if not numeric.empty:
        values = numeric.to_numpy(dtype="float64", na_value=np.nan)
        if not bool(np.isfinite(values).all()):
            raise AssertionError("cleaned frame still has infinite numeric values")
