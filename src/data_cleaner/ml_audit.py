"""Train/test split audits for leakage and distribution problems.

The helpers in this module are pure functions: they inspect frames and return a
report. They never fit anything, never mutate their inputs, and never change a
split for the caller.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from pandas.api import types as ptypes

TaskType = Literal["auto", "classification", "regression"]
ResolvedTask = Literal["classification", "regression"]
AuditSeverity = Literal["error", "warning"]

_AUDIT_COLUMNS = ["check", "column", "severity", "message", "train", "test"]
_HASH_MULTIPLIER = np.uint64(1_000_003)


@dataclass(eq=False)
class SplitAudit:
    """Findings from :func:`audit_split`.

    ``findings`` is a tidy DataFrame with ``check``, ``column``, ``severity``,
    ``message``, ``train``, and ``test`` columns. The report only describes
    problems; it never modifies the data or repairs a split.
    """

    findings: pd.DataFrame
    train_rows: int
    test_rows: int
    task: ResolvedTask | None
    duplicate_overlap_rows: int = 0
    near_duplicate_overlap_rows: int = 0
    group_overlap: int = 0
    time_overlap_rows: int = 0

    @property
    def valid(self) -> bool:
        """Whether the audit found no error-severity issues."""
        if self.findings.empty:
            return True
        return bool((self.findings["severity"] == "error").sum() == 0)

    @property
    def errors(self) -> pd.DataFrame:
        """Findings with error severity."""
        if self.findings.empty:
            return self.findings
        return self.findings[self.findings["severity"] == "error"]

    @property
    def warnings(self) -> pd.DataFrame:
        """Findings with warning severity."""
        if self.findings.empty:
            return self.findings
        return self.findings[self.findings["severity"] == "warning"]

    @property
    def has_errors(self) -> bool:
        """Whether at least one error-severity finding exists."""
        return not self.errors.empty

    @property
    def has_warnings(self) -> bool:
        """Whether at least one warning-severity finding exists."""
        return not self.warnings.empty

    def summary(self) -> str:
        """Return a short human-readable description of the findings."""
        if self.findings.empty:
            return "no split issues detected"
        lines: list[str] = []
        for _, row in self.findings.iterrows():
            column = row["column"]
            target = f" ({column})" if isinstance(column, str) and column else ""
            lines.append(
                f"- [{row['severity']}] {row['check']}{target}: {row['message']}"
            )
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render the findings as a Markdown table (falls back to text)."""
        status = "PASS" if self.valid else "FAIL"
        if self.findings.empty:
            return f"**{status}** — no split issues detected."
        lines = [
            f"**{status}** — {len(self.findings)} finding(s): "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)."
        ]
        try:
            lines.append(self.findings.to_markdown(index=False))
        except ImportError:  # tabulate is optional
            lines.append(self.findings.to_string(index=False))
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation of the audit."""
        return {
            "train_rows": self.train_rows,
            "test_rows": self.test_rows,
            "task": self.task,
            "valid": self.valid,
            "duplicate_overlap_rows": self.duplicate_overlap_rows,
            "near_duplicate_overlap_rows": self.near_duplicate_overlap_rows,
            "group_overlap": self.group_overlap,
            "time_overlap_rows": self.time_overlap_rows,
            "findings": [dict(record) for record in self.findings.to_dict("records")],
        }

    def raise_if_invalid(self, message: str = "Split audit failed") -> None:
        """Raise ``ValueError`` when at least one error-severity finding exists."""
        if not self.valid:
            raise ValueError(f"{message}:\n{self.summary()}")


def _require_unique_columns(frame: pd.DataFrame, *, frame_name: str) -> None:
    if frame.columns.has_duplicates:
        duplicates = frame.columns[frame.columns.duplicated()].tolist()
        raise ValueError(f"{frame_name} contains duplicate column names: {duplicates}")


def _require_columns(
    frame: pd.DataFrame, columns: Sequence[str], *, frame_name: str
) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"{frame_name} is missing column(s): {missing}")


def _normalize_columns(
    values: str | Sequence[str] | None, *, argument: str
) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized = (values,) if isinstance(values, str) else tuple(values)
    if not normalized:
        raise ValueError(f"{argument} must contain at least one column")
    if not all(isinstance(column, str) for column in normalized):
        raise TypeError(f"{argument} columns must be strings")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{argument} contains duplicate columns: {list(normalized)}")
    return normalized


def _as_series(values: object, *, name: str) -> pd.Series:
    if isinstance(values, pd.DataFrame):
        raise TypeError(f"{name} must be one-dimensional")
    series = values if isinstance(values, pd.Series) else pd.Series(values)
    if series.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    return series.reset_index(drop=True)


def _require_length(series: pd.Series, expected: int, *, name: str) -> pd.Series:
    if len(series) != expected:
        raise ValueError(
            f"{name} has {len(series)} value(s), expected {expected} to match the frame"
        )
    return series


def _is_numeric(series: pd.Series) -> bool:
    return bool(ptypes.is_numeric_dtype(series) and not ptypes.is_bool_dtype(series))


def _is_datetime(series: pd.Series) -> bool:
    return bool(ptypes.is_datetime64_any_dtype(series))


def _scalar_text(value: Any) -> str | None:
    """Render a scalar deterministically, preserving nulls as ``None``."""
    if value is None:
        return None
    if isinstance(value, dict):
        items = sorted((repr(key), repr(item)) for key, item in value.items())
        return repr(items)
    if isinstance(value, (set, frozenset)):
        return repr(sorted(repr(item) for item in value))
    if isinstance(value, (list, tuple, np.ndarray)):
        return repr(value)
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return repr(value)
    if not isinstance(missing, (bool, np.bool_)):
        return repr(value)
    if bool(missing):
        return None
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    return str(value)


def _text_series(series: pd.Series) -> pd.Series:
    return series.astype(object).map(_scalar_text)


def _hash_frame(frame: pd.DataFrame) -> np.ndarray:
    """Hash rows after making every value hashable and null-stable."""
    columns: dict[int, np.ndarray] = {}
    for position, column in enumerate(frame.columns):
        series = frame[column]
        if _is_numeric(series) or _is_datetime(series):
            columns[position] = series.to_numpy()
        else:
            columns[position] = _text_series(series).to_numpy()
    normalized = pd.DataFrame(columns)
    if normalized.empty:
        return np.empty(0, dtype=np.uint64)
    return pd.util.hash_pandas_object(normalized, index=False).to_numpy()


def _near_signature(frame: pd.DataFrame, decimals: int) -> np.ndarray:
    """Hash a rounded / textual row signature for near-duplicate detection."""
    parts: list[np.ndarray] = []
    for column in frame.columns:
        series = frame[column]
        if _is_numeric(series):
            rounded = series.astype(float).round(decimals)
            text = rounded.map(
                lambda value: "" if pd.isna(value) else f"{float(value):.{decimals}f}"
            ).astype(str)
        elif _is_datetime(series):
            text = series.dt.strftime("%Y-%m-%dT%H:%M:%S").fillna("")
        else:
            text = _text_series(series).fillna("").astype(str)
        parts.append(
            pd.util.hash_pandas_object(text, index=False).to_numpy(dtype=np.uint64)
        )
    if not parts:
        return np.empty(0, dtype=np.uint64)
    combined = parts[0].copy()
    for part in parts[1:]:
        # A deterministic order-sensitive mix of the per-column hashes.
        combined = combined * _HASH_MULTIPLIER ^ part
    return combined


def _overlap_mask(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    if len(left) == 0 or len(right) == 0:
        return np.zeros(len(left), dtype=bool)
    return np.isin(left, right)


def _stringify_groups(series: pd.Series) -> pd.Series:
    return series.astype(object).map(_scalar_text)


def _resolve_task(
    task: TaskType,
    y_train: pd.Series,
    *,
    classification_max_classes: int,
) -> ResolvedTask:
    if task not in {"auto", "classification", "regression"}:
        raise ValueError("task must be 'auto', 'classification', or 'regression'")
    if task != "auto":
        return task

    non_null = y_train.dropna()
    if non_null.empty:
        return "classification"
    if (
        ptypes.is_bool_dtype(non_null)
        or ptypes.is_object_dtype(non_null)
        or ptypes.is_string_dtype(non_null)
        or isinstance(non_null.dtype, pd.CategoricalDtype)
    ):
        return "classification"
    if ptypes.is_integer_dtype(non_null):
        if non_null.nunique() <= classification_max_classes:
            return "classification"
        return "regression"
    if ptypes.is_numeric_dtype(non_null):
        unique = non_null.unique()
        if len(unique) <= 2 and bool((pd.Series(unique) % 1 == 0).all()):
            return "classification"
    return "regression"


def _encode_target(series: pd.Series) -> pd.Series:
    try:
        codes, _ = pd.factorize(series, sort=True)
    except TypeError:
        codes, _ = pd.factorize(series, sort=False)
    return pd.Series(codes, index=series.index, dtype="float64").where(
        series.notna(), np.nan
    )


def _abs_correlation(left: pd.Series, right: pd.Series) -> float | None:
    frame = pd.DataFrame(
        {
            "left": pd.to_numeric(left, errors="coerce"),
            "right": pd.to_numeric(right, errors="coerce"),
        }
    ).dropna()
    if len(frame) < 10:
        return None
    if frame["left"].nunique() < 2 or frame["right"].nunique() < 2:
        return None
    correlation = frame["left"].corr(frame["right"])
    if pd.isna(correlation):
        return None
    return float(abs(correlation))


def _normalized_mutual_information(left: pd.Series, right: pd.Series) -> float | None:
    frame = pd.DataFrame(
        {"left": _stringify_groups(left), "right": _stringify_groups(right)}
    ).dropna()
    if len(frame) < 10:
        return None
    left_values = frame["left"]
    right_values = frame["right"]
    left_counts = left_values.value_counts(normalize=True)
    right_counts = right_values.value_counts(normalize=True)
    if len(left_counts) < 2 or len(right_counts) < 2:
        return None

    joint = pd.crosstab(left_values, right_values, normalize=True)
    aligned_left = left_counts.reindex(joint.index, fill_value=0.0)
    aligned_right = right_counts.reindex(joint.columns, fill_value=0.0)
    expected = np.outer(aligned_left.to_numpy(), aligned_right.to_numpy())
    observed = joint.to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = observed * np.log(observed / expected)
    mutual_information = float(np.nansum(terms))
    entropy_left = float(
        -(aligned_left.to_numpy() * np.log(aligned_left.to_numpy())).sum()
    )
    entropy_right = float(
        -(aligned_right.to_numpy() * np.log(aligned_right.to_numpy())).sum()
    )
    if entropy_left <= 0 or entropy_right <= 0:
        return None
    return mutual_information / ((entropy_left + entropy_right) / 2)


def _standardized_mean_difference(left: pd.Series, right: pd.Series) -> float | None:
    left_numeric = pd.to_numeric(left, errors="coerce").dropna()
    right_numeric = pd.to_numeric(right, errors="coerce").dropna()
    if len(left_numeric) < 2 or len(right_numeric) < 2:
        return None
    difference = float(left_numeric.mean() - right_numeric.mean())
    pooled = float(np.sqrt((left_numeric.var(ddof=1) + right_numeric.var(ddof=1)) / 2))
    if pooled == 0:
        return 0.0 if difference == 0 else float("inf")
    return abs(difference) / pooled


def _total_variation_distance(left: pd.Series, right: pd.Series) -> float | None:
    left_text = _stringify_groups(left).dropna()
    right_text = _stringify_groups(right).dropna()
    if left_text.empty or right_text.empty:
        return None
    left_share = left_text.value_counts(normalize=True)
    right_share = right_text.value_counts(normalize=True)
    index = left_share.index.union(right_share.index)
    aligned_left = left_share.reindex(index, fill_value=0.0)
    aligned_right = right_share.reindex(index, fill_value=0.0)
    return float((aligned_left - aligned_right).abs().sum() / 2)


def _add_finding(
    findings: list[dict[str, object]],
    check: str,
    *,
    message: str,
    severity: AuditSeverity = "warning",
    column: str | None = None,
    train: object = None,
    test: object = None,
) -> None:
    findings.append(
        {
            "check": check,
            "column": column,
            "severity": severity,
            "message": message,
            "train": train,
            "test": test,
        }
    )


def _constant_findings(
    findings: list[dict[str, object]],
    *,
    columns: Sequence[str],
    frames: Sequence[tuple[str, pd.DataFrame]],
    threshold: float,
) -> None:
    for column in columns:
        details: list[str] = []
        worst_check: str | None = None
        for name, frame in frames:
            if frame.empty:
                continue
            series = _text_series(frame[column]).dropna()
            if series.empty:
                continue
            counts = series.value_counts()
            unique = len(counts)
            top_share = float(counts.iloc[0] / len(series))
            if unique <= 1:
                details.append(f"{name}: constant ({_scalar_text(counts.index[0])!r})")
                worst_check = "constant_column"
            elif top_share >= threshold:
                details.append(
                    f"{name}: {top_share:.0%} '{_scalar_text(counts.index[0])}'"
                )
                if worst_check is None:
                    worst_check = "near_constant_column"
        if worst_check is None:
            continue
        _add_finding(
            findings,
            worst_check,
            column=column,
            message="; ".join(details),
        )


def _high_cardinality_findings(
    findings: list[dict[str, object]],
    *,
    columns: Sequence[str],
    frames: Sequence[tuple[str, pd.DataFrame]],
    id_columns: Sequence[str],
    threshold: float,
    min_unique: int,
) -> None:
    ids = set(id_columns)
    for column in columns:
        if column not in ids and all(
            _is_numeric(frame[column]) for _, frame in frames if not frame.empty
        ):
            # Continuous numeric features are expected to be mostly unique.
            continue
        details: list[str] = []
        flagged = False
        for name, frame in frames:
            if frame.empty:
                continue
            series = _text_series(frame[column]).dropna()
            if series.empty:
                continue
            unique = int(series.nunique())
            share = unique / len(series)
            if unique >= min_unique and share >= threshold:
                flagged = True
                details.append(f"{name}: {unique} unique ({share:.0%})")
        if not flagged:
            continue
        message = "; ".join(details)
        if column in ids:
            message = f"declared identifier column — {message}"
        else:
            message = f"high-cardinality column — {message}"
        _add_finding(findings, "high_cardinality", column=column, message=message)


def _missingness_findings(
    findings: list[dict[str, object]],
    *,
    columns: Sequence[str],
    train: pd.DataFrame,
    test: pd.DataFrame,
    threshold: float,
) -> None:
    if train.empty or test.empty:
        return
    for column in columns:
        train_rate = float(_text_series(train[column]).isna().mean())
        test_rate = float(_text_series(test[column]).isna().mean())
        difference = abs(train_rate - test_rate)
        if difference >= threshold:
            _add_finding(
                findings,
                "missingness_shift",
                column=column,
                message=(
                    f"missing rate changed from {train_rate:.1%} (train) to "
                    f"{test_rate:.1%} (test)"
                ),
                train=train_rate,
                test=test_rate,
            )


def _distribution_findings(
    findings: list[dict[str, object]],
    *,
    columns: Sequence[str],
    train: pd.DataFrame,
    test: pd.DataFrame,
    numeric_threshold: float,
    categorical_threshold: float,
) -> None:
    if train.empty or test.empty:
        return
    for column in columns:
        train_series = train[column]
        test_series = test[column]
        if _is_numeric(train_series) and _is_numeric(test_series):
            shift = _standardized_mean_difference(train_series, test_series)
            if shift is None or shift < numeric_threshold:
                continue
            _add_finding(
                findings,
                "distribution_shift",
                column=column,
                message=(
                    "numeric distribution shifted "
                    f"(standardized mean difference {shift:.2f})"
                ),
                train=round(
                    float(pd.to_numeric(train_series, errors="coerce").mean()), 6
                ),
                test=round(
                    float(pd.to_numeric(test_series, errors="coerce").mean()), 6
                ),
            )
        elif _is_datetime(train_series) and _is_datetime(test_series):
            continue
        else:
            distance = _total_variation_distance(train_series, test_series)
            if distance is None or distance < categorical_threshold:
                continue
            _add_finding(
                findings,
                "distribution_shift",
                column=column,
                message=(
                    "categorical distribution shifted "
                    f"(total variation distance {distance:.2f})"
                ),
                train=round(distance, 6),
            )


def _target_leakage_findings(
    findings: list[dict[str, object]],
    *,
    train: pd.DataFrame,
    y_train: pd.Series,
    task: ResolvedTask,
    columns: Sequence[str],
    correlation_threshold: float,
    nmi_threshold: float,
    max_categories: int,
) -> None:
    if train.empty:
        return
    encoded = _encode_target(y_train) if task == "classification" else None
    binary = encoded is not None and int(y_train.dropna().nunique()) == 2
    for column in columns:
        series = train[column]
        if _is_numeric(series) and task == "regression":
            correlation = _abs_correlation(series, y_train)
            if correlation is not None and correlation >= correlation_threshold:
                _add_finding(
                    findings,
                    "target_leakage",
                    column=column,
                    message=(
                        f"feature correlates {correlation:.2f} with the target "
                        f"(threshold {correlation_threshold:.2f})"
                    ),
                    train=round(correlation, 6),
                )
        elif _is_numeric(series) and binary and encoded is not None:
            correlation = _abs_correlation(series, encoded)
            if correlation is not None and correlation >= correlation_threshold:
                _add_finding(
                    findings,
                    "target_leakage",
                    column=column,
                    message=(
                        f"feature correlates {correlation:.2f} with the binary target "
                        f"(threshold {correlation_threshold:.2f})"
                    ),
                    train=round(correlation, 6),
                )
        elif not _is_datetime(series) and encoded is not None:
            non_null = _text_series(series).dropna()
            unique = int(non_null.nunique())
            if (
                unique < 2
                or unique > max_categories
                or unique > max(len(train) // 2, 2)
            ):
                continue
            score = _normalized_mutual_information(series, y_train)
            if score is not None and score >= nmi_threshold:
                _add_finding(
                    findings,
                    "target_leakage",
                    column=column,
                    message=(
                        f"feature and target are nearly identical "
                        f"(normalized mutual information {score:.2f}, "
                        f"threshold {nmi_threshold:.2f})"
                    ),
                    train=round(score, 6),
                )


def _target_shift_findings(
    findings: list[dict[str, object]],
    *,
    y_train: pd.Series,
    y_test: pd.Series,
    task: ResolvedTask,
    threshold: float,
) -> None:
    if y_train.empty or y_test.empty:
        return
    if task == "classification":
        train_labels = _stringify_groups(y_train).dropna()
        test_labels = _stringify_groups(y_test).dropna()
        if train_labels.empty or test_labels.empty:
            return
        unseen = sorted(set(test_labels) - set(train_labels))
        if unseen:
            examples = ", ".join(unseen[:10])
            more = "" if len(unseen) <= 10 else f" (+{len(unseen) - 10} more)"
            _add_finding(
                findings,
                "unseen_target_class",
                message=f"test target contains classes unseen in train: {examples}{more}",
                test=len(unseen),
            )
        distance = _total_variation_distance(train_labels, test_labels)
        if distance is not None and distance >= threshold:
            _add_finding(
                findings,
                "target_shift",
                message=(
                    "target class distribution shifted "
                    f"(total variation distance {distance:.2f}, "
                    f"threshold {threshold:.2f})"
                ),
                train=round(distance, 6),
            )
    else:
        shift = _standardized_mean_difference(y_train, y_test)
        if shift is not None and shift >= threshold:
            _add_finding(
                findings,
                "target_shift",
                message=(
                    "target distribution shifted "
                    f"(standardized mean difference {shift:.2f}, "
                    f"threshold {threshold:.2f})"
                ),
                train=round(float(pd.to_numeric(y_train, errors="coerce").mean()), 6),
                test=round(float(pd.to_numeric(y_test, errors="coerce").mean()), 6),
            )


def audit_split(
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: Sequence[object] | pd.Series | np.ndarray | None = None,
    y_test: Sequence[object] | pd.Series | np.ndarray | None = None,
    *,
    groups: Sequence[object] | pd.Series | np.ndarray | None = None,
    groups_test: Sequence[object] | pd.Series | np.ndarray | None = None,
    time_col: str | None = None,
    id_cols: str | Sequence[str] | None = None,
    task: TaskType = "auto",
    near_duplicate_decimals: int | None = 3,
    constant_threshold: float = 0.99,
    high_cardinality_threshold: float = 0.9,
    high_cardinality_min_unique: int = 20,
    missingness_shift_threshold: float = 0.1,
    distribution_shift_threshold: float = 0.5,
    categorical_shift_threshold: float = 0.2,
    target_correlation_threshold: float = 0.95,
    target_nmi_threshold: float = 0.9,
    target_shift_threshold: float = 0.5,
    classification_max_classes: int = 20,
    max_target_leak_categories: int = 50,
) -> SplitAudit:
    """Audit a train/test split for leakage and distribution problems.

    Parameters
    ----------
    X_train, X_test:
        Feature frames. They are never modified.
    y_train, y_test:
        Optional targets, aligned by position. Both must be supplied together.
    groups:
        Group labels for the training rows. If ``groups_test`` is omitted,
        ``groups`` may contain ``len(X_train) + len(X_test)`` labels; the
        trailing labels are used for the test rows.
    groups_test:
        Group labels for the test rows when ``groups`` only covers train.
    time_col:
        Optional timestamp column. When supplied, the audit treats the split as
        temporal and reports train timestamps after the earliest test timestamp.
    id_cols:
        Optional identifier columns. They are excluded from duplicate,
        constant, high-cardinality, distribution, and target-leakage checks and
        are reported as declared identifiers instead.
    task:
        ``"auto"``, ``"classification"``, or ``"regression"``. ``"auto"``
        infers classification from a boolean, categorical, string, or
        low-cardinality integer target.
    near_duplicate_decimals:
        Decimal places used to round numeric features before near-duplicate
        detection. ``None`` disables near-duplicate checks.
    constant_threshold:
        Share of the most frequent value at or above which a column is
        near-constant.
    high_cardinality_threshold:
        Unique-value share at or above which a column is high-cardinality.
    high_cardinality_min_unique:
        Minimum number of unique values before a column is called
        high-cardinality.
    missingness_shift_threshold:
        Absolute missing-rate change at or above which a finding is emitted.
    distribution_shift_threshold:
        Standardized mean difference at or above which a numeric feature is
        reported as shifted.
    categorical_shift_threshold:
        Total variation distance at or above which a categorical feature is
        reported as shifted.
    target_correlation_threshold:
        Absolute correlation at or above which a numeric feature is suspected
        of target leakage.
    target_nmi_threshold:
        Normalized mutual information at or above which a categorical feature
        is suspected of target leakage.
    target_shift_threshold:
        Target-distribution shift threshold. Used as total variation distance
        for classification and standardized mean difference for regression.
    classification_max_classes:
        Maximum unique integer target values inferred as classification when
        ``task="auto"``.
    max_target_leak_categories:
        Maximum feature cardinality considered for the categorical
        target-leakage heuristic.

    Returns
    -------
    SplitAudit
        A severity-tagged findings table plus convenience properties and
        ``raise_if_invalid()``.

    Notes
    -----
    Exact duplicate, group, and temporal leakage are errors. Statistical and
    heuristic checks (near-duplicates, constants, cardinality, missingness,
    distribution shift, target leakage, and target shift) are warnings because
    they can be legitimate dataset properties.

    Duplicate checks exclude ``id_cols`` and ``time_col``. Near-duplicates are
    approximated by hashing features rounded to ``near_duplicate_decimals``;
    this is deterministic and dependency-light, not an exact nearest-neighbour
    search.
    """
    if not isinstance(X_train, pd.DataFrame) or not isinstance(X_test, pd.DataFrame):
        raise TypeError("X_train and X_test must be pandas DataFrames")
    _require_unique_columns(X_train, frame_name="X_train")
    _require_unique_columns(X_test, frame_name="X_test")

    if task not in {"auto", "classification", "regression"}:
        raise ValueError("task must be 'auto', 'classification', or 'regression'")
    if near_duplicate_decimals is not None and near_duplicate_decimals < 0:
        raise ValueError("near_duplicate_decimals must be non-negative or None")
    if not 0 < constant_threshold <= 1:
        raise ValueError("constant_threshold must be in (0, 1]")
    if not 0 < high_cardinality_threshold <= 1:
        raise ValueError("high_cardinality_threshold must be in (0, 1]")
    if high_cardinality_min_unique < 2:
        raise ValueError("high_cardinality_min_unique must be at least 2")
    if not 0 <= missingness_shift_threshold <= 1:
        raise ValueError("missingness_shift_threshold must be in [0, 1]")
    if distribution_shift_threshold <= 0:
        raise ValueError("distribution_shift_threshold must be positive")
    if not 0 < categorical_shift_threshold <= 1:
        raise ValueError("categorical_shift_threshold must be in (0, 1]")
    if not 0 < target_correlation_threshold <= 1:
        raise ValueError("target_correlation_threshold must be in (0, 1]")
    if not 0 < target_nmi_threshold <= 1:
        raise ValueError("target_nmi_threshold must be in (0, 1]")
    if target_shift_threshold <= 0:
        raise ValueError("target_shift_threshold must be positive")
    if classification_max_classes < 2:
        raise ValueError("classification_max_classes must be at least 2")
    if max_target_leak_categories < 2:
        raise ValueError("max_target_leak_categories must be at least 2")

    if time_col is not None and not isinstance(time_col, str):
        raise TypeError("time_col must be a string or None")
    if time_col is not None:
        _require_columns(X_train, (time_col,), frame_name="X_train")
        _require_columns(X_test, (time_col,), frame_name="X_test")
    id_columns = _normalize_columns(id_cols, argument="id_cols")
    if id_columns:
        _require_columns(X_train, id_columns, frame_name="X_train")
        _require_columns(X_test, id_columns, frame_name="X_test")

    if (y_train is None) != (y_test is None):
        raise ValueError("y_train and y_test must be supplied together")
    has_target = y_train is not None and y_test is not None
    train_target: pd.Series | None = None
    test_target: pd.Series | None = None
    resolved_task: ResolvedTask | None = None
    if has_target:
        train_target = _require_length(
            _as_series(y_train, name="y_train"), len(X_train), name="y_train"
        )
        test_target = _require_length(
            _as_series(y_test, name="y_test"), len(X_test), name="y_test"
        )
        resolved_task = _resolve_task(
            task,
            train_target,
            classification_max_classes=classification_max_classes,
        )

    train_groups: pd.Series | None = None
    test_groups: pd.Series | None = None
    if groups is None and groups_test is not None:
        raise ValueError("groups_test requires groups")
    if groups is not None:
        group_values = _as_series(groups, name="groups")
        if groups_test is None:
            if len(group_values) != len(X_train) + len(X_test):
                raise ValueError(
                    "groups must cover train and test when groups_test is omitted"
                )
            train_groups = group_values.iloc[: len(X_train)].reset_index(drop=True)
            test_groups = group_values.iloc[len(X_train) :].reset_index(drop=True)
        else:
            train_groups = _require_length(group_values, len(X_train), name="groups")
            test_groups = _require_length(
                _as_series(groups_test, name="groups_test"),
                len(X_test),
                name="groups_test",
            )

    findings: list[dict[str, object]] = []
    train_columns = tuple(X_train.columns)
    test_columns = tuple(X_test.columns)
    common = tuple(column for column in train_columns if column in test_columns)

    for column in train_columns:
        if column not in test_columns:
            _add_finding(
                findings,
                "missing_column",
                column=column,
                severity="error",
                message="column is present in train but missing from test",
                train="present",
                test="missing",
            )
    for column in test_columns:
        if column not in train_columns:
            _add_finding(
                findings,
                "extra_column",
                column=column,
                message="column is present in test but missing from train",
                train="missing",
                test="present",
            )

    if X_train.empty or X_test.empty:
        _add_finding(
            findings,
            "empty_split",
            message=(
                f"empty split: train has {len(X_train)} row(s), "
                f"test has {len(X_test)} row(s)"
            ),
            train=len(X_train),
            test=len(X_test),
        )

    for column in common:
        train_dtype = str(X_train[column].dtype)
        test_dtype = str(X_test[column].dtype)
        if train_dtype != test_dtype:
            _add_finding(
                findings,
                "dtype_change",
                column=column,
                message=f"dtype differs: {train_dtype} (train) vs {test_dtype} (test)",
                train=train_dtype,
                test=test_dtype,
            )

    duplicate_columns = [
        column
        for column in common
        if column not in set(id_columns) and column != time_col
    ]
    duplicate_overlap = 0
    near_duplicate_overlap = 0
    if duplicate_columns and not X_train.empty and not X_test.empty:
        train_duplicates = X_train.loc[:, duplicate_columns]
        test_duplicates = X_test.loc[:, duplicate_columns]
        exact_overlap = _overlap_mask(
            _hash_frame(train_duplicates), _hash_frame(test_duplicates)
        )
        duplicate_overlap = int(exact_overlap.sum())
        if near_duplicate_decimals is not None:
            near_overlap = _overlap_mask(
                _near_signature(train_duplicates, near_duplicate_decimals),
                _near_signature(test_duplicates, near_duplicate_decimals),
            )
            near_duplicate_overlap = int((near_overlap & ~exact_overlap).sum())
        if duplicate_overlap:
            _add_finding(
                findings,
                "duplicate_rows",
                severity="error",
                message=(
                    f"{duplicate_overlap} test row(s) exactly duplicate a training "
                    "row (excluding id/time columns)"
                ),
                test=duplicate_overlap,
            )
        if near_duplicate_overlap:
            _add_finding(
                findings,
                "near_duplicate_rows",
                message=(
                    f"{near_duplicate_overlap} test row(s) are near-duplicates of "
                    f"training rows at {near_duplicate_decimals}-decimal precision"
                ),
                test=near_duplicate_overlap,
            )

    group_overlap = 0
    if train_groups is not None and test_groups is not None:
        train_group_text = _stringify_groups(train_groups)
        test_group_text = _stringify_groups(test_groups)
        train_group_values = set(train_group_text.dropna())
        test_group_values = set(test_group_text.dropna())
        overlap = train_group_values & test_group_values
        group_overlap = len(overlap)
        leaking_test_rows = int(test_group_text.isin(overlap).sum())
        train_nulls = int(train_group_text.isna().sum())
        test_nulls = int(test_group_text.isna().sum())
        if train_nulls or test_nulls:
            _add_finding(
                findings,
                "group_nulls",
                message=(
                    f"null group labels: {train_nulls} in train, "
                    f"{test_nulls} in test; nulls are not treated as one group"
                ),
                train=train_nulls,
                test=test_nulls,
            )
        if group_overlap:
            _add_finding(
                findings,
                "group_leakage",
                severity="error",
                message=(
                    f"{group_overlap} group(s) appear in both splits, covering "
                    f"{leaking_test_rows} test row(s)"
                ),
                train=group_overlap,
                test=leaking_test_rows,
            )

    time_overlap = 0
    if time_col is not None:
        train_times = pd.to_datetime(X_train[time_col], errors="coerce", utc=True)
        test_times = pd.to_datetime(X_test[time_col], errors="coerce", utc=True)
        train_invalid = int(X_train[time_col].notna().sum() - train_times.notna().sum())
        test_invalid = int(X_test[time_col].notna().sum() - test_times.notna().sum())
        if train_invalid or test_invalid:
            _add_finding(
                findings,
                "time_parse_error",
                column=time_col,
                message=(
                    f"could not parse timestamps: {train_invalid} in train, "
                    f"{test_invalid} in test"
                ),
                train=train_invalid,
                test=test_invalid,
            )
        train_valid_times = train_times.dropna()
        test_valid_times = test_times.dropna()
        if not train_valid_times.empty and not test_valid_times.empty:
            train_max = train_valid_times.max()
            test_min = test_valid_times.min()
            if train_max > test_min:
                time_overlap = int((train_valid_times > test_min).sum())
                test_before = int((test_valid_times < train_max).sum())
                _add_finding(
                    findings,
                    "temporal_leakage",
                    column=time_col,
                    severity="error",
                    message=(
                        f"train extends past the earliest test timestamp "
                        f"(train max {train_max.isoformat()}, "
                        f"test min {test_min.isoformat()}): "
                        f"{time_overlap} train row(s) after test start, "
                        f"{test_before} test row(s) before train end"
                    ),
                    train=time_overlap,
                    test=test_before,
                )

    feature_columns = [
        column
        for column in common
        if column not in set(id_columns) and column != time_col
    ]
    _constant_findings(
        findings,
        columns=feature_columns,
        frames=(("train", X_train), ("test", X_test)),
        threshold=constant_threshold,
    )
    _high_cardinality_findings(
        findings,
        columns=[column for column in common if column != time_col],
        frames=(("train", X_train), ("test", X_test)),
        id_columns=id_columns,
        threshold=high_cardinality_threshold,
        min_unique=high_cardinality_min_unique,
    )
    _missingness_findings(
        findings,
        columns=common,
        train=X_train,
        test=X_test,
        threshold=missingness_shift_threshold,
    )
    _distribution_findings(
        findings,
        columns=feature_columns,
        train=X_train,
        test=X_test,
        numeric_threshold=distribution_shift_threshold,
        categorical_threshold=categorical_shift_threshold,
    )

    if (
        train_target is not None
        and test_target is not None
        and resolved_task is not None
    ):
        _target_leakage_findings(
            findings,
            train=X_train,
            y_train=train_target,
            task=resolved_task,
            columns=feature_columns,
            correlation_threshold=target_correlation_threshold,
            nmi_threshold=target_nmi_threshold,
            max_categories=max_target_leak_categories,
        )
        _target_shift_findings(
            findings,
            y_train=train_target,
            y_test=test_target,
            task=resolved_task,
            threshold=target_shift_threshold,
        )

    return SplitAudit(
        findings=pd.DataFrame(findings, columns=_AUDIT_COLUMNS),
        train_rows=len(X_train),
        test_rows=len(X_test),
        task=resolved_task,
        duplicate_overlap_rows=duplicate_overlap,
        near_duplicate_overlap_rows=near_duplicate_overlap,
        group_overlap=group_overlap,
        time_overlap_rows=time_overlap,
    )
