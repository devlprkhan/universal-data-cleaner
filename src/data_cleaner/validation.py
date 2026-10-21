"""Lightweight expectations and validation reports."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

import pandas as pd
from pandas.api import types as ptypes

from ._roles import _normalize_kind, _series_kind

Severity = Literal["error", "warning"]

_VALIDATION_COLUMNS = [
    "expectation",
    "column",
    "success",
    "severity",
    "message",
    "observed",
]

_BROAD_DTYPE_ALIASES = {
    "numeric",
    "number",
    "int",
    "integer",
    "float",
    "double",
    "boolean",
    "bool",
    "datetime",
    "date",
    "timestamp",
    "categorical",
    "category",
    "object",
    "string",
    "str",
    "text",
    "id",
}


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of a single expectation."""

    expectation: str
    column: str | None
    success: bool
    severity: Severity
    message: str
    observed: object = None

    def to_dict(self) -> dict[str, object]:
        """Return a tabular representation of the result."""
        return {
            "expectation": self.expectation,
            "column": self.column,
            "success": self.success,
            "severity": self.severity,
            "message": self.message,
            "observed": self.observed,
        }


@dataclass(frozen=True, slots=True)
class Expectation:
    """A single, reusable data expectation.

    Prefer the factory functions (:func:`not_null`, :func:`unique`,
    :func:`in_set`, :func:`between`, :func:`matches_pattern`,
    :func:`has_dtype`, :func:`row_count_between`) over constructing this class
    directly.
    """

    name: str
    column: str | None = None
    values: tuple[object, ...] | None = None
    lower: float | None = None
    upper: float | None = None
    inclusive: bool = True
    pattern: str | None = None
    dtype: str | None = None
    min_rows: int | None = None
    max_rows: int | None = None
    severity: Severity = "error"

    def __post_init__(self) -> None:
        if self.name not in _CHECKERS:
            raise ValueError(f"Unsupported expectation '{self.name}'")
        if self.severity not in {"error", "warning"}:
            raise ValueError("severity must be 'error' or 'warning'")

        if self.name == "row_count_between":
            if self.column is not None:
                raise ValueError("row_count_between does not take a column")
            if self.min_rows is None and self.max_rows is None:
                raise ValueError("row_count_between requires min_rows and/or max_rows")
            if (
                self.min_rows is not None
                and self.max_rows is not None
                and self.min_rows > self.max_rows
            ):
                raise ValueError("min_rows is greater than max_rows")
            if self.min_rows is not None and self.min_rows < 0:
                raise ValueError("min_rows must be non-negative")
            if self.max_rows is not None and self.max_rows < 0:
                raise ValueError("max_rows must be non-negative")
        elif not self.column:
            raise ValueError(f"{self.name} requires a column")

        if self.name == "in_set" and not self.values:
            raise ValueError("in_set requires at least one allowed value")
        if self.name == "between":
            if self.lower is None and self.upper is None:
                raise ValueError("between requires lower and/or upper")
            if (
                self.lower is not None
                and self.upper is not None
                and self.lower > self.upper
            ):
                raise ValueError("lower is greater than upper")
        if self.name == "matches_pattern":
            if self.pattern is None:
                raise ValueError("matches_pattern requires a pattern")
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"Invalid pattern: {exc}") from exc
        if self.name == "has_dtype" and self.dtype is None:
            raise ValueError("has_dtype requires a dtype")

    def check(self, frame: pd.DataFrame) -> ValidationResult:
        """Evaluate this expectation against ``frame``."""
        return _CHECKERS[self.name](self, frame)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation of the expectation."""
        return {
            "name": self.name,
            "column": self.column,
            "values": list(self.values) if self.values is not None else None,
            "lower": self.lower,
            "upper": self.upper,
            "inclusive": self.inclusive,
            "pattern": self.pattern,
            "dtype": self.dtype,
            "min_rows": self.min_rows,
            "max_rows": self.max_rows,
            "severity": self.severity,
        }


def _column(expectation: Expectation) -> str:
    if expectation.column is None:  # pragma: no cover - guarded by __post_init__
        raise ValueError(f"{expectation.name} requires a column")
    return expectation.column


def _missing_column(
    expectation: Expectation, frame: pd.DataFrame
) -> ValidationResult | None:
    column = expectation.column
    if column is not None and column not in frame.columns:
        return ValidationResult(
            expectation=expectation.name,
            column=column,
            success=False,
            severity=expectation.severity,
            message=f"column '{column}' is missing",
            observed=None,
        )
    return None


def _check_not_null(expectation: Expectation, frame: pd.DataFrame) -> ValidationResult:
    missing = _missing_column(expectation, frame)
    if missing is not None:
        return missing
    column = _column(expectation)
    count = int(frame[column].isna().sum())
    success = count == 0
    message = (
        f"column '{column}' has no missing values"
        if success
        else f"column '{column}' has {count} missing value(s)"
    )
    return ValidationResult(
        expectation.name, column, success, expectation.severity, message, count
    )


def _check_unique(expectation: Expectation, frame: pd.DataFrame) -> ValidationResult:
    missing = _missing_column(expectation, frame)
    if missing is not None:
        return missing
    column = _column(expectation)
    duplicates = int(frame[column].dropna().duplicated().sum())
    success = duplicates == 0
    message = (
        f"column '{column}' has no duplicate non-null values"
        if success
        else f"column '{column}' has {duplicates} duplicate non-null value(s)"
    )
    return ValidationResult(
        expectation.name, column, success, expectation.severity, message, duplicates
    )


def _check_in_set(expectation: Expectation, frame: pd.DataFrame) -> ValidationResult:
    missing = _missing_column(expectation, frame)
    if missing is not None:
        return missing
    column = _column(expectation)
    allowed = list(expectation.values or ())
    series = frame[column]
    mask = series.notna() & ~series.isin(allowed)
    count = int(mask.sum())
    success = count == 0
    if success:
        message = f"column '{column}' only contains allowed values"
        observed: object = count
    else:
        examples = [str(value) for value in pd.unique(series[mask])[:10]]
        message = (
            f"column '{column}' has {count} value(s) outside the allowed set: "
            f"{examples}"
        )
        observed = examples
    return ValidationResult(
        expectation.name, column, success, expectation.severity, message, observed
    )


def _bounds_text(expectation: Expectation) -> str:
    left = "[" if expectation.inclusive else "("
    right = "]" if expectation.inclusive else ")"
    lower = "-inf" if expectation.lower is None else str(expectation.lower)
    upper = "inf" if expectation.upper is None else str(expectation.upper)
    return f"{left}{lower}, {upper}{right}"


def _check_between(expectation: Expectation, frame: pd.DataFrame) -> ValidationResult:
    missing = _missing_column(expectation, frame)
    if missing is not None:
        return missing
    column = _column(expectation)
    series = frame[column]
    numeric = pd.to_numeric(series, errors="coerce")
    non_numeric = int((series.notna() & numeric.isna()).sum())
    valid = numeric.dropna()

    outside = 0
    if expectation.lower is not None:
        outside += int(
            (valid <= expectation.lower).sum()
            if not expectation.inclusive
            else (valid < expectation.lower).sum()
        )
    if expectation.upper is not None:
        outside += int(
            (valid >= expectation.upper).sum()
            if not expectation.inclusive
            else (valid > expectation.upper).sum()
        )

    total = outside + non_numeric
    success = total == 0
    bounds = _bounds_text(expectation)
    if success:
        message = f"column '{column}' is within {bounds}"
    else:
        parts: list[str] = []
        if outside:
            parts.append(f"{outside} value(s) outside {bounds}")
        if non_numeric:
            parts.append(f"{non_numeric} non-numeric value(s)")
        message = f"column '{column}' has " + " and ".join(parts)
    return ValidationResult(
        expectation.name, column, success, expectation.severity, message, total
    )


def _check_matches_pattern(
    expectation: Expectation, frame: pd.DataFrame
) -> ValidationResult:
    missing = _missing_column(expectation, frame)
    if missing is not None:
        return missing
    column = _column(expectation)
    pattern = expectation.pattern
    if pattern is None:  # pragma: no cover - guarded by __post_init__
        raise ValueError("matches_pattern requires a pattern")
    non_null = frame[column].dropna()
    matches = non_null.astype(str).str.fullmatch(pattern)
    mismatches = int((~matches.fillna(False)).sum())
    success = mismatches == 0
    message = (
        f"column '{column}' matches {pattern!r}"
        if success
        else f"column '{column}' has {mismatches} value(s) not matching {pattern!r}"
    )
    return ValidationResult(
        expectation.name, column, success, expectation.severity, message, mismatches
    )


def _check_has_dtype(expectation: Expectation, frame: pd.DataFrame) -> ValidationResult:
    missing = _missing_column(expectation, frame)
    if missing is not None:
        return missing
    column = _column(expectation)
    expected = expectation.dtype
    if expected is None:  # pragma: no cover - guarded by __post_init__
        raise ValueError("has_dtype requires a dtype")

    key = expected.strip().lower()
    if key in _BROAD_DTYPE_ALIASES:
        expected_label = _normalize_kind(key) or key
        observed: object = _series_kind(frame[column])
        success = observed == expected_label
    else:
        try:
            expected_dtype = ptypes.pandas_dtype(expected)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Unsupported dtype '{expected}'") from exc
        expected_label = str(expected_dtype)
        observed = str(frame[column].dtype)
        success = frame[column].dtype == expected_dtype

    message = (
        f"column '{column}' has expected dtype {expected_label}"
        if success
        else f"column '{column}' has dtype {observed}, expected {expected_label}"
    )
    return ValidationResult(
        expectation.name, column, success, expectation.severity, message, observed
    )


def _check_row_count_between(
    expectation: Expectation, frame: pd.DataFrame
) -> ValidationResult:
    rows = len(frame)
    lower_ok = expectation.min_rows is None or rows >= expectation.min_rows
    upper_ok = expectation.max_rows is None or rows <= expectation.max_rows
    success = lower_ok and upper_ok
    message = f"frame has {rows} row(s)"
    if not success:
        lower = "0" if expectation.min_rows is None else str(expectation.min_rows)
        upper = "inf" if expectation.max_rows is None else str(expectation.max_rows)
        message += f", expected between {lower} and {upper}"
    return ValidationResult(
        expectation.name,
        None,
        success,
        expectation.severity,
        message,
        rows,
    )


_CHECKERS: dict[str, Callable[[Expectation, pd.DataFrame], ValidationResult]] = {
    "not_null": _check_not_null,
    "unique": _check_unique,
    "in_set": _check_in_set,
    "between": _check_between,
    "matches_pattern": _check_matches_pattern,
    "has_dtype": _check_has_dtype,
    "row_count_between": _check_row_count_between,
}


def not_null(column: str, *, severity: Severity = "error") -> Expectation:
    """Expect ``column`` to contain no missing values."""
    return Expectation(name="not_null", column=column, severity=severity)


def unique(column: str, *, severity: Severity = "error") -> Expectation:
    """Expect non-null values in ``column`` to be unique."""
    return Expectation(name="unique", column=column, severity=severity)


def in_set(
    column: str,
    values: Sequence[object],
    *,
    severity: Severity = "error",
) -> Expectation:
    """Expect non-null values in ``column`` to belong to ``values``."""
    return Expectation(
        name="in_set", column=column, values=tuple(values), severity=severity
    )


def between(
    column: str,
    lower: float | None = None,
    upper: float | None = None,
    *,
    inclusive: bool = True,
    severity: Severity = "error",
) -> Expectation:
    """Expect numeric values in ``column`` to fall within the given bounds."""
    return Expectation(
        name="between",
        column=column,
        lower=lower,
        upper=upper,
        inclusive=inclusive,
        severity=severity,
    )


def matches_pattern(
    column: str, pattern: str, *, severity: Severity = "error"
) -> Expectation:
    """Expect non-null string values in ``column`` to fully match ``pattern``."""
    return Expectation(
        name="matches_pattern", column=column, pattern=pattern, severity=severity
    )


def has_dtype(column: str, dtype: str, *, severity: Severity = "error") -> Expectation:
    """Expect ``column`` to have a broad kind or an exact pandas dtype.

    Broad kinds are ``numeric``, ``categorical``, ``boolean``, and ``datetime``.
    Exact pandas dtypes such as ``float64`` or ``datetime64[ns]`` are compared
    directly.
    """
    return Expectation(name="has_dtype", column=column, dtype=dtype, severity=severity)


def row_count_between(
    min_rows: int | None = None,
    max_rows: int | None = None,
    *,
    severity: Severity = "error",
) -> Expectation:
    """Expect the frame to have between ``min_rows`` and ``max_rows`` rows."""
    return Expectation(
        name="row_count_between",
        min_rows=min_rows,
        max_rows=max_rows,
        severity=severity,
    )


@dataclass(eq=False)
class ValidationReport:
    """Container for expectation results or contract findings."""

    results: pd.DataFrame
    source: str = "expectations"

    @classmethod
    def from_results(cls, results: Sequence[ValidationResult]) -> ValidationReport:
        """Build a report from individual results."""
        return cls(
            pd.DataFrame(
                [result.to_dict() for result in results],
                columns=_VALIDATION_COLUMNS,
            ),
            source="expectations",
        )

    @classmethod
    def from_findings(cls, findings: pd.DataFrame) -> ValidationReport:
        """Build a report from :class:`~data_cleaner.DriftReport` findings."""
        records = [
            {
                "expectation": row["check"],
                "column": row["column"],
                "success": False,
                "severity": row["severity"],
                "message": row["message"],
                "observed": row["actual"],
            }
            for _, row in findings.iterrows()
        ]
        return cls(
            pd.DataFrame(records, columns=_VALIDATION_COLUMNS),
            source="contract",
        )

    @property
    def success(self) -> bool:
        """Whether every error-severity expectation passed."""
        if self.results.empty:
            return True
        failures = self.results[
            (~self.results["success"]) & (self.results["severity"] == "error")
        ]
        return failures.empty

    @property
    def failures(self) -> pd.DataFrame:
        """Rows for every failed expectation, including warnings."""
        if self.results.empty:
            return self.results
        return self.results[~self.results["success"]]

    @property
    def has_warnings(self) -> bool:
        """Whether any warning-severity expectation failed."""
        if self.results.empty:
            return False
        warnings = self.results[
            (~self.results["success"]) & (self.results["severity"] == "warning")
        ]
        return not warnings.empty

    def summary(self) -> str:
        """Return a short human-readable description of the failures."""
        if self.results.empty:
            if self.source == "contract":
                return "no contract violations"
            return "no expectations were evaluated"
        failed = self.failures
        if failed.empty:
            return f"all {len(self.results)} expectation(s) passed"
        lines: list[str] = []
        for _, row in failed.iterrows():
            column = row["column"]
            target = f" on '{column}'" if isinstance(column, str) and column else ""
            lines.append(
                f"- [{row['severity']}] {row['expectation']}{target}: {row['message']}"
            )
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render the report as Markdown (falls back to plain text)."""
        if self.results.empty:
            if self.source == "contract":
                return "**PASS** — no contract violations."
            return "No expectations were evaluated."
        status = "PASS" if self.success else "FAIL"
        lines = [
            f"**{status}** — {len(self.results)} expectation(s), "
            f"{len(self.failures)} failure(s)"
        ]
        if self.failures.empty:
            return lines[0]
        lines.append("")
        try:
            lines.append(self.failures.to_markdown(index=False))
        except ImportError:  # tabulate is optional
            lines.append(self.failures.to_string(index=False))
        return "\n".join(lines)

    def raise_if_failed(self, message: str = "Validation failed") -> None:
        """Raise ``ValueError`` when an error-severity expectation failed."""
        if not self.success:
            raise ValueError(f"{message}:\n{self.summary()}")


def validate(
    frame: pd.DataFrame,
    expectations: Expectation | Sequence[Expectation],
) -> ValidationReport:
    """Evaluate one or more expectations against ``frame``.

    Warning-severity failures are reported but do not make the report fail.
    """
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    items = (
        (expectations,)
        if isinstance(expectations, Expectation)
        else tuple(expectations)
    )
    if not items:
        raise ValueError("At least one expectation is required")
    return ValidationReport.from_results(
        [expectation.check(frame) for expectation in items]
    )
