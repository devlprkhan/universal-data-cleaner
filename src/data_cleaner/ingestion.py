"""Safe CSV ingestion with explicit coercion and an audit report.

The reader starts by loading every field as text. It then applies either the
supplied :class:`~data_cleaner.DataContract` or a conservative inference pass,
recording every normalization it performs. The goal is not to guess silently:
the returned frame is typed, and the :class:`IngestionReport` explains what was
changed and why.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import IO, Any, Literal

import numpy as np
import pandas as pd

from ._roles import _ROLE_TO_KIND, _normalize_kind, _series_kind
from .contract import ColumnSpec, DataContract

LOGGER = logging.getLogger(__name__)

IngestionPolicy = Literal["warn", "raise", "ignore"]
IngestionSeverity = Literal["error", "warning"]

_INGESTION_COLUMNS = ["column", "check", "severity", "message", "count"]
_COLUMN_COLUMNS = [
    "column",
    "detected_kind",
    "output_kind",
    "output_dtype",
    "non_null",
    "missing",
]

_RESERVED_READ_KWARGS = {
    "converters",
    "decimal",
    "dtype",
    "keep_default_na",
    "na_filter",
    "na_values",
    "parse_dates",
    "thousands",
}

_CURRENCY_CHARS = "€£¥₹₽₩¢$"
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_THOUSANDS_RE = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?$")
_DECIMAL_COMMA_RE = re.compile(r"^[+-]?\d+,\d{1,6}$")
_AMBIGUOUS_DATE_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-]\d{2,4}$")
_DATE_STRUCTURE_RE = re.compile(
    r"(?:\d{1,4}[-/]\d{1,2}[-/]\d{1,4})|(?:[T:])|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    re.IGNORECASE,
)
_DATE_VALUE_RE = re.compile(
    r"^(?:\d{1,4}[-/]\d{1,2}[-/]\d{1,4})|"
    r"^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    re.IGNORECASE,
)

_TEXT_BOOLEAN_TOKENS = {
    "true": True,
    "t": True,
    "yes": True,
    "y": True,
    "false": False,
    "f": False,
    "no": False,
    "n": False,
}
_NUMERIC_BOOLEAN_TOKENS = {"1": True, "0": False}
_NONSTANDARD_BOOLEAN_TOKENS = {"t", "f", "yes", "no", "y", "n"}

_NUMERIC_FLAG_MESSAGES = {
    "currency_symbol": "column '{column}' had {count} value(s) with currency "
    "symbols; symbols were removed",
    "thousands_separator": "column '{column}' had {count} value(s) with thousands "
    "separators; separators were removed",
    "percent_symbol": "column '{column}' had {count} value(s) with percent signs; "
    "values were divided by 100",
    "parentheses_negative": "column '{column}' had {count} value(s) in accounting "
    "parentheses; values were treated as negative",
    "decimal_comma": "column '{column}' had {count} value(s) with decimal commas; "
    "commas were treated as decimal points",
}
_DATE_FLAG_MESSAGES = {
    "ambiguous_date_format": "column '{column}' had {count} date(s) with an "
    "ambiguous day/month order; pass ColumnSpec.date_format to make it explicit",
    "compact_date": "column '{column}' had {count} date(s) in YYYYMMDD form; "
    "values were parsed as dates",
    "excel_serial_date": "column '{column}' had {count} date(s) stored as Excel "
    "serial numbers; values were parsed as dates",
}
_BOOLEAN_FLAG_MESSAGES = {
    "boolean_tokens": "column '{column}' had {count} value(s) using Y/N-style "
    "boolean tokens; values were parsed as booleans",
}


@dataclass(eq=False)
class IngestionReport:
    """Audit report returned by :func:`read_csv_safe`.

    ``findings`` is a tidy DataFrame with ``column``, ``check``, ``severity``,
    ``message``, and ``count`` columns. ``columns`` summarizes how each input
    column was detected and typed. Neither table includes raw cell values.
    """

    source: str
    rows: int
    columns: pd.DataFrame
    findings: pd.DataFrame

    @property
    def success(self) -> bool:
        """Whether ingestion found no error-severity issues."""
        if self.findings.empty:
            return True
        return bool((self.findings["severity"] == "error").sum() == 0)

    @property
    def errors(self) -> pd.DataFrame:
        """Findings with error severity."""
        if self.findings.empty:
            return self.findings.copy()
        return self.findings[self.findings["severity"] == "error"]

    @property
    def warnings(self) -> pd.DataFrame:
        """Findings with warning severity."""
        if self.findings.empty:
            return self.findings.copy()
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
            return "no ingestion issues detected"
        lines = [
            f"- [{row['severity']}] {row['column']}: {row['message']}"
            for _, row in self.findings.iterrows()
        ]
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render the findings as a Markdown table (falls back to text)."""
        status = "PASS" if self.success else "FAIL"
        if self.findings.empty:
            return f"**{status}** — no ingestion issues detected."
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
        """Return a JSON-friendly representation of the report."""
        return {
            "source": self.source,
            "rows": self.rows,
            "success": self.success,
            "columns": [dict(record) for record in self.columns.to_dict("records")],
            "findings": [dict(record) for record in self.findings.to_dict("records")],
        }

    def raise_if_failed(self, message: str = "CSV ingestion failed") -> None:
        """Raise ``IngestionError`` when an error-severity finding exists."""
        if not self.success:
            raise IngestionError(f"{message}:\n{self.summary()}", self)


class IngestionError(ValueError):
    """Raised when ingestion finds error-severity issues and policy is ``raise``."""

    def __init__(self, message: str, report: IngestionReport) -> None:
        super().__init__(message)
        self.report = report


def _add_finding(
    findings: list[dict[str, object]],
    column: str,
    check: str,
    severity: IngestionSeverity,
    message: str,
    count: int,
) -> None:
    findings.append(
        {
            "column": column,
            "check": check,
            "severity": severity,
            "message": message,
            "count": count,
        }
    )


def _add_flag_findings(
    findings: list[dict[str, object]],
    column: str,
    flags: dict[str, int],
    messages: dict[str, str],
) -> None:
    for flag, count in flags.items():
        if count:
            _add_finding(
                findings,
                column,
                flag,
                "warning",
                messages[flag].format(column=column, count=count),
                count,
            )


def _source_label(source: object) -> str:
    if isinstance(source, (str, os.PathLike)):
        return str(source)
    name = getattr(source, "name", None)
    return str(name) if name else "<stream>"


def _blank_to_na(frame: pd.DataFrame) -> pd.DataFrame:
    """Turn empty or whitespace-only text fields into missing values."""
    result = frame.copy(deep=True)
    for column in result.columns:
        series = result[column]
        blank = series.map(lambda value: isinstance(value, str) and not value.strip())
        result[column] = series.mask(blank, pd.NA)
    return result


def _normalize_numeric_text(value: str) -> tuple[str, set[str]]:
    """Normalize spreadsheet number spellings and report the changes made."""
    text = value.strip().replace("\u2212", "-")
    flags: set[str] = set()
    if not text:
        return "", flags

    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1].strip()
        flags.add("parentheses_negative")

    if text.endswith("%"):
        text = text[:-1].strip()
        flags.add("percent_symbol")

    if any(character in text for character in _CURRENCY_CHARS):
        text = "".join(
            character for character in text if character not in _CURRENCY_CHARS
        ).strip()
        flags.add("currency_symbol")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
            flags.add("decimal_comma")
            flags.add("thousands_separator")
        else:
            text = text.replace(",", "")
            flags.add("thousands_separator")
    elif "," in text:
        if _THOUSANDS_RE.fullmatch(text):
            text = text.replace(",", "")
            flags.add("thousands_separator")
        elif _DECIMAL_COMMA_RE.fullmatch(text):
            text = text.replace(",", ".")
            flags.add("decimal_comma")

    return text, flags


def _parse_numeric(
    series: pd.Series,
) -> tuple[pd.Series, dict[str, int], int, int]:
    """Parse numeric-looking text and return values, flags, invalid, infinite."""
    flags = dict.fromkeys(_NUMERIC_FLAG_MESSAGES, 0)
    normalized: list[str | float] = []
    percent_mask: list[bool] = []
    for value in series:
        if pd.isna(value):
            normalized.append(np.nan)
            percent_mask.append(False)
            continue
        text, value_flags = _normalize_numeric_text(str(value))
        for flag in value_flags:
            flags[flag] += 1
        normalized.append(text)
        percent_mask.append("percent_symbol" in value_flags)

    parsed = pd.to_numeric(
        pd.Series(normalized, index=series.index), errors="coerce"
    ).astype("float64")
    if any(percent_mask):
        parsed = parsed.mask(
            pd.Series(percent_mask, index=series.index), parsed / 100.0
        )

    non_finite = int((parsed.notna() & ~np.isfinite(parsed)).sum())
    unparseable = int((series.notna() & parsed.isna()).sum())
    parsed = parsed.mask(parsed.notna() & ~np.isfinite(parsed), np.nan)
    return parsed, flags, unparseable, non_finite


def _parse_boolean(
    series: pd.Series, *, allow_numeric: bool
) -> tuple[pd.Series, dict[str, int], int, bool]:
    flags = {"boolean_tokens": 0}
    mapping = dict(_TEXT_BOOLEAN_TOKENS)
    if allow_numeric:
        mapping.update(_NUMERIC_BOOLEAN_TOKENS)

    values: list[object] = []
    has_alpha = False
    unparseable = 0
    for value in series:
        if pd.isna(value):
            values.append(pd.NA)
            continue
        token = str(value).strip().lower()
        if token in _TEXT_BOOLEAN_TOKENS:
            has_alpha = True
        if token in _NONSTANDARD_BOOLEAN_TOKENS:
            flags["boolean_tokens"] += 1
        if token in mapping:
            values.append(mapping[token])
        else:
            values.append(pd.NA)
            unparseable += 1

    parsed = pd.Series(values, index=series.index, dtype="boolean")
    return parsed, flags, unparseable, has_alpha


def _parse_datetime(
    series: pd.Series,
    *,
    date_format: str | None,
    allow_serial: bool,
) -> tuple[pd.Series, dict[str, int], int]:
    flags = dict.fromkeys(_DATE_FLAG_MESSAGES, 0)
    raw = series.map(lambda value: "" if pd.isna(value) else str(value).strip())
    present = raw != ""
    if not present.any():
        return (
            pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]"),
            flags,
            0,
        )

    values = raw[present]
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    if date_format is not None:
        parsed = pd.to_datetime(raw.where(present), format=date_format, errors="coerce")
    elif allow_serial and values.str.fullmatch(r"\d{8}").all():
        parsed.loc[values.index] = pd.to_datetime(
            values, format="%Y%m%d", errors="coerce"
        )
        flags["compact_date"] = int(values.size)
    elif allow_serial and values.str.fullmatch(r"\d{5}(?:\.\d+)?").all():
        serial = pd.to_numeric(values, errors="coerce")
        parsed.loc[values.index] = pd.to_datetime(
            serial, unit="D", origin="1899-12-30", errors="coerce"
        )
        flags["excel_serial_date"] = int(values.size)
    else:
        try:
            parsed = pd.to_datetime(raw.where(present), errors="coerce", format="mixed")
        except (TypeError, ValueError):
            parsed = pd.to_datetime(raw.where(present), errors="coerce")

        ambiguous = values[values.str.fullmatch(_AMBIGUOUS_DATE_RE)]
        if not ambiguous.empty:
            parts = ambiguous.str.extract(_AMBIGUOUS_DATE_RE)
            first = pd.to_numeric(parts[0], errors="coerce")
            second = pd.to_numeric(parts[1], errors="coerce")
            flags["ambiguous_date_format"] = int(((first <= 12) & (second <= 12)).sum())

    invalid = int((present & parsed.isna()).sum())
    return parsed, flags, invalid


def _looks_like_identifier(values: pd.Series) -> bool:
    if values.empty:
        return False
    digits = values.str.fullmatch(r"\d+").fillna(False)
    return bool(
        digits.all()
        and values.str.startswith("0").any()
        and values.str.len().gt(1).any()
    )


def _leading_zero_count(series: pd.Series) -> int:
    values = series.dropna().astype(str).str.strip()
    return int(values.str.fullmatch(r"0\d+").fillna(False).sum())


def _classify_series(series: pd.Series) -> str:
    values = series.dropna().map(lambda value: str(value).strip())
    if values.empty:
        return "empty"
    if _looks_like_identifier(values):
        return "identifier"

    _, _, unparseable, _ = _parse_numeric(series)
    if unparseable == 0:
        return "numeric"

    _, _, invalid_boolean, has_alpha = _parse_boolean(series, allow_numeric=False)
    if invalid_boolean == 0 and has_alpha:
        return "boolean"

    if values.str.contains(_DATE_STRUCTURE_RE).any():
        _, _, invalid_date = _parse_datetime(
            series, date_format=None, allow_serial=False
        )
        if invalid_date == 0:
            return "datetime"
    return "text"


def _value_category(value: str) -> str:
    text = value.strip()
    if text.lower() in _TEXT_BOOLEAN_TOKENS:
        return "boolean"
    normalized, _ = _normalize_numeric_text(text)
    if _NUMBER_RE.fullmatch(normalized):
        return "numeric"
    if _DATE_VALUE_RE.search(text):
        return "datetime"
    return "text"


def _mixed_value_count(series: pd.Series) -> int:
    categories = Counter(_value_category(str(value)) for value in series.dropna())
    if len(categories) <= 1:
        return 0
    dominant = max(categories.values())
    return int(sum(categories.values()) - dominant)


def _target_kind(spec: ColumnSpec) -> str | None:
    if spec.role == "ignore":
        return "text"
    if spec.role is not None:
        return _ROLE_TO_KIND.get(spec.role)
    if spec.dtype is not None:
        return _normalize_kind(spec.dtype)
    return None


def _ingest_column(
    series: pd.Series,
    spec: ColumnSpec | None,
    findings: list[dict[str, object]],
) -> tuple[pd.Series, str]:
    detected = _classify_series(series)
    target = _target_kind(spec) if spec is not None else None
    preserve_zeros = bool(spec is not None and spec.preserve_leading_zeros)
    if preserve_zeros and target in {"numeric", None}:
        target = "text"
    if target is None:
        if detected == "numeric":
            target = "numeric"
        elif detected == "boolean":
            target = "boolean"
        elif detected == "datetime":
            target = "datetime"
        else:
            target = "text"

    column = str(series.name)
    if target == "numeric":
        parsed, flags, unparseable, non_finite = _parse_numeric(series)
        _add_flag_findings(findings, column, flags, _NUMERIC_FLAG_MESSAGES)
        if unparseable:
            _add_finding(
                findings,
                column,
                "unparseable_values",
                "error",
                f"column '{column}' has {unparseable} value(s) that could not be "
                "parsed as numeric",
                unparseable,
            )
        if non_finite:
            _add_finding(
                findings,
                column,
                "non_finite_values",
                "warning",
                f"column '{column}' has {non_finite} non-finite value(s) that were "
                "set to missing",
                non_finite,
            )
        return parsed, detected

    if target == "datetime":
        parsed, flags, invalid = _parse_datetime(
            series,
            date_format=spec.date_format if spec is not None else None,
            allow_serial=True,
        )
        _add_flag_findings(findings, column, flags, _DATE_FLAG_MESSAGES)
        if invalid:
            _add_finding(
                findings,
                column,
                "unparseable_values",
                "error",
                f"column '{column}' has {invalid} value(s) that could not be "
                "parsed as dates",
                invalid,
            )
        return parsed, detected

    if target == "boolean":
        parsed, flags, invalid, _ = _parse_boolean(series, allow_numeric=True)
        _add_flag_findings(findings, column, flags, _BOOLEAN_FLAG_MESSAGES)
        if invalid:
            _add_finding(
                findings,
                column,
                "unparseable_values",
                "error",
                f"column '{column}' has {invalid} value(s) that could not be "
                "parsed as booleans",
                invalid,
            )
        return parsed, detected

    result = series.astype(object)
    zeros = _leading_zero_count(series)
    if zeros and (detected == "identifier" or preserve_zeros):
        _add_finding(
            findings,
            column,
            "leading_zeros_preserved",
            "warning",
            f"column '{column}' has {zeros} value(s) with leading zeros; values "
            "were kept as text",
            zeros,
        )
    if detected == "empty":
        _add_finding(
            findings,
            column,
            "empty_column",
            "warning",
            f"column '{column}' has no non-missing values",
            0,
        )
    if detected == "text" and spec is None:
        mixed = _mixed_value_count(series)
        if mixed:
            _add_finding(
                findings,
                column,
                "mixed_types",
                "warning",
                f"column '{column}' has {mixed} value(s) that do not match the "
                "dominant value type; the column was kept as text",
                mixed,
            )
    return result, detected


def read_csv_safe(
    source: str | os.PathLike[str] | IO[Any],
    contract: DataContract | None = None,
    *,
    on_error: IngestionPolicy = "warn",
    **read_csv_kwargs: Any,
) -> tuple[pd.DataFrame, IngestionReport]:
    """Read a CSV as text, coerce it under an optional contract, and audit it.

    Parameters
    ----------
    source:
        Path or file-like object accepted by :func:`pandas.read_csv`.
    contract:
        Optional :class:`~data_cleaner.DataContract`. Declared columns use their
        role, dtype, and date format. Undeclared columns are kept as text and
        reported instead of being silently typed.
    on_error:
        ``"warn"`` logs error findings and returns the frame (default),
        ``"raise"`` raises :class:`IngestionError` when an error finding exists,
        and ``"ignore"`` suppresses logging while still returning the report.
    **read_csv_kwargs:
        Extra options passed to :func:`pandas.read_csv`. Options that would
        bypass the string-first read (``dtype``, ``na_filter``,
        ``keep_default_na``, ``na_values``, ``parse_dates``, ``converters``,
        ``decimal``, or ``thousands``) are rejected.

    Returns
    -------
    tuple[pandas.DataFrame, IngestionReport]
        The typed frame and an audit report. String columns are kept as
        ``object`` dtype for consistency across pandas 2.x and 3.x.

    Notes
    -----
    The reader recognizes common spreadsheet spellings: thousands separators,
    currency symbols, percent signs, accounting parentheses, decimal commas,
    ``YYYYMMDD`` dates, Excel serial dates, and Y/N-style booleans. Normalization
    is reported, never performed silently. Values that cannot be parsed in a
    declared numeric/date/boolean column become missing values and produce an
    error finding.

    Identifier columns and columns with leading zeros are kept as text. Passing
    a contract is the safest way to protect identifiers and to make date formats
    unambiguous.
    """
    if contract is not None and not isinstance(contract, DataContract):
        raise TypeError("contract must be a DataContract instance or None")
    if on_error not in {"warn", "raise", "ignore"}:
        raise ValueError("on_error must be one of: warn, raise, ignore")

    conflicts = sorted(_RESERVED_READ_KWARGS.intersection(read_csv_kwargs))
    if conflicts:
        raise TypeError(
            "read_csv_safe manages these read_csv options itself: "
            f"{', '.join(conflicts)}"
        )

    raw = pd.read_csv(
        source,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        **read_csv_kwargs,
    )
    frame = _blank_to_na(raw)

    findings: list[dict[str, object]] = []
    specs = {spec.name: spec for spec in contract.columns} if contract else {}
    if contract is not None:
        for spec in contract.columns:
            if spec.role != "ignore" and spec.name not in frame.columns:
                _add_finding(
                    findings,
                    spec.name,
                    "missing_column",
                    "error",
                    f"expected column '{spec.name}' is missing from the CSV",
                    1,
                )
        for column in frame.columns:
            if column not in specs:
                _add_finding(
                    findings,
                    str(column),
                    "undeclared_column",
                    "warning",
                    f"column '{column}' is not declared in the contract; kept as text",
                    1,
                )

    parsed_columns: dict[str, pd.Series] = {}
    column_rows: list[dict[str, object]] = []
    for column in frame.columns:
        parsed, detected = _ingest_column(frame[column], specs.get(column), findings)
        parsed_columns[str(column)] = parsed
        column_rows.append(
            {
                "column": str(column),
                "detected_kind": detected,
                "output_kind": _series_kind(parsed),
                "output_dtype": str(parsed.dtype),
                "non_null": int(parsed.notna().sum()),
                "missing": int(parsed.isna().sum()),
            }
        )

    result = pd.DataFrame(parsed_columns, index=frame.index)
    report = IngestionReport(
        source=_source_label(source),
        rows=len(frame),
        columns=pd.DataFrame(column_rows, columns=_COLUMN_COLUMNS),
        findings=pd.DataFrame(findings, columns=_INGESTION_COLUMNS),
    )

    if on_error == "raise" and not report.success:
        raise IngestionError(f"CSV ingestion failed:\n{report.summary()}", report)
    if on_error == "warn" and not report.findings.empty:
        LOGGER.warning(
            "CSV ingestion issues for %s:\n%s", report.source, report.summary()
        )
    return result, report
