"""Safe CSV and Excel ingestion with explicit coercion and an audit report.

The readers start by loading every field as text. They then apply either the
supplied :class:`~data_cleaner.DataContract` or a conservative inference pass,
recording every normalization they perform. The goal is not to guess silently:
the returned frame is typed, and the :class:`IngestionReport` explains what was
changed and why.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import IO, Any, Literal, cast
from urllib.parse import urlsplit, urlunsplit

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
    "dtype_backend",
    "false_values",
    "keep_default_na",
    "na_filter",
    "na_values",
    "parse_dates",
    "thousands",
    "true_values",
}

_RESERVED_EXCEL_KWARGS = {
    "converters",
    "decimal",
    "dtype",
    "dtype_backend",
    "false_values",
    "keep_default_na",
    "na_filter",
    "na_values",
    "parse_dates",
    "thousands",
    "true_values",
}

_CURRENCY_CHARS = "€£¥₹₽₩¢$"
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_INTEGER_RE = re.compile(r"^[+-]?\d+$")
_MAX_EXACT_FLOAT_INT = 2**53
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
    "integer_precision": "column '{column}' had {count} integer value(s) beyond "
    "2^53; float64 conversion may lose precision, so store large identifiers as text",
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
    """Audit report returned by :func:`read_csv_safe` or :func:`read_excel_safe`.

    ``findings`` is a tidy DataFrame with ``column``, ``check``, ``severity``,
    ``message``, and ``count`` columns. ``columns`` summarizes how each input
    column was detected and typed. Neither table includes raw cell values.

    ``sheet`` is the resolved worksheet name for Excel input and ``None`` for
    CSV input.
    """

    source: str
    rows: int
    columns: pd.DataFrame
    findings: pd.DataFrame
    sheet: str | None = None

    @property
    def location(self) -> str:
        """Source label, including the resolved sheet for Excel input."""
        if self.sheet:
            return f"{self.source} (sheet: {self.sheet})"
        return self.source

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
            return f"**{status}** — no ingestion issues detected in {self.location}."
        lines = [
            f"**{status}** — {len(self.findings)} finding(s) in {self.location}: "
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
            "sheet": self.sheet,
            "rows": self.rows,
            "success": self.success,
            "columns": [dict(record) for record in self.columns.to_dict("records")],
            "findings": [dict(record) for record in self.findings.to_dict("records")],
        }

    def raise_if_failed(self, message: str = "Ingestion failed") -> None:
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


def _redact_location(text: str) -> str:
    """Strip credentials and query strings from a URL-like source label."""
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if not parts.scheme or not parts.netloc:
        return text
    netloc = parts.netloc.rsplit("@", 1)[-1]
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _source_label(source: object) -> str:
    if isinstance(source, (str, os.PathLike)):
        return _redact_location(str(source))
    name = getattr(source, "name", None)
    return _redact_location(str(name)) if name else "<stream>"


def _is_missing(value: object) -> bool:
    """Return whether a single cell value is missing, without raising."""
    try:
        return bool(pd.isna(cast(Any, value)))
    except (TypeError, ValueError):
        return False


def _blank_to_na(frame: pd.DataFrame, *, copy: bool = True) -> pd.DataFrame:
    """Turn empty or whitespace-only text fields into missing values."""
    result = frame.copy(deep=True) if copy else frame
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
        if _INTEGER_RE.fullmatch(text):
            try:
                if abs(int(text)) > _MAX_EXACT_FLOAT_INT:
                    flags["integer_precision"] += 1
            except ValueError:  # pragma: no cover - regex guarantees digits
                pass
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


def _datetime_cell_to_text(value: object, date_format: str | None) -> str:
    """Render a native datetime cell without losing the declared format."""
    if _is_missing(value):
        return ""
    if isinstance(value, (pd.Timestamp, datetime, date, np.datetime64)):
        timestamp = pd.Timestamp(value)
        if date_format is not None:
            return timestamp.strftime(date_format)
        return timestamp.isoformat()
    return str(value).strip()


def _parse_datetime(
    series: pd.Series,
    *,
    date_format: str | None,
    allow_serial: bool,
) -> tuple[pd.Series, dict[str, int], int]:
    flags = dict.fromkeys(_DATE_FLAG_MESSAGES, 0)
    raw = series.map(lambda value: _datetime_cell_to_text(value, date_format))
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
    else:
        try:
            parsed = pd.to_datetime(raw.where(present), errors="coerce", format="mixed")
        except (TypeError, ValueError):
            parsed = pd.to_datetime(raw.where(present), errors="coerce")

    compact = pd.Series(False, index=series.index)
    serial = pd.Series(False, index=series.index)
    if allow_serial:
        compact = raw.str.fullmatch(r"\d{8}").fillna(False) & present
        serial = raw.str.fullmatch(r"\d{5}(?:\.\d+)?").fillna(False) & present
        if date_format is not None:
            fallback = present & parsed.isna()
            compact = compact & fallback
            serial = serial & fallback

        if compact.any():
            parsed.loc[compact] = pd.to_datetime(
                raw[compact], format="%Y%m%d", errors="coerce"
            )
            flags["compact_date"] = int(compact.sum())
        if serial.any():
            serial_values = pd.to_numeric(raw[serial], errors="coerce")
            parsed.loc[serial] = pd.to_datetime(
                serial_values, unit="D", origin="1899-12-30", errors="coerce"
            )
            flags["excel_serial_date"] = int(serial.sum())

    ambiguous_pool = values
    if allow_serial:
        ambiguous_pool = values[~(compact.loc[values.index] | serial.loc[values.index])]
    ambiguous = ambiguous_pool[ambiguous_pool.str.fullmatch(_AMBIGUOUS_DATE_RE)]
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


def _ingest_frame(
    frame: pd.DataFrame,
    contract: DataContract | None,
    *,
    source: str,
    sheet: str | None,
    on_error: IngestionPolicy,
    format_name: str,
    input_label: str,
    numeric_identifiers: dict[str, int] | None = None,
) -> tuple[pd.DataFrame, IngestionReport]:
    """Coerce a string-normalized frame and build the shared audit report."""
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
                    f"expected column '{spec.name}' is missing from the {input_label}",
                    1,
                )
        for column in frame.columns:
            if column not in specs:
                _add_finding(
                    findings,
                    str(column),
                    "undeclared_column",
                    "warning",
                    f"column '{column}' is not declared in the contract; it was "
                    "typed by inference",
                    1,
                )

    for column, count in (numeric_identifiers or {}).items():
        _add_finding(
            findings,
            column,
            "numeric_identifier",
            "warning",
            f"column '{column}' is an identifier stored as numbers in the "
            "spreadsheet; leading zeros may already be lost, so store identifiers "
            "as text",
            count,
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
        source=source,
        rows=len(frame),
        columns=pd.DataFrame(column_rows, columns=_COLUMN_COLUMNS),
        findings=pd.DataFrame(findings, columns=_INGESTION_COLUMNS),
        sheet=sheet,
    )

    if on_error == "raise" and not report.success:
        raise IngestionError(
            f"{format_name} ingestion failed for {report.location}:\n"
            f"{report.summary()}",
            report,
        )
    if on_error == "warn" and not report.findings.empty:
        LOGGER.warning(
            "%s ingestion issues for %s:\n%s",
            format_name,
            report.location,
            report.summary(),
        )
    return result, report


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
        role, dtype, and date format. Undeclared columns are inferred
        conservatively and reported as ``undeclared_column``; the report lists
        their detected and output kinds.
    on_error:
        ``"warn"`` logs error findings and returns the frame (default),
        ``"raise"`` raises :class:`IngestionError` when an error finding exists,
        and ``"ignore"`` suppresses logging while still returning the report.
    **read_csv_kwargs:
        Extra options passed to :func:`pandas.read_csv`. Options that would
        bypass the string-first read (``dtype``, ``dtype_backend``,
        ``na_filter``, ``keep_default_na``, ``na_values``, ``parse_dates``,
        ``converters``, ``decimal``, ``thousands``, ``true_values``, or
        ``false_values``) are rejected.

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

    This function reads the whole file into memory. For large files, use
    :func:`iter_csv_safe`, which yields typed chunks and a per-chunk report.
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
    frame = _blank_to_na(raw, copy=False)
    return _ingest_frame(
        frame,
        contract,
        source=_source_label(source),
        sheet=None,
        on_error=on_error,
        format_name="CSV",
        input_label="CSV",
    )


def iter_csv_safe(
    source: str | os.PathLike[str] | IO[Any],
    contract: DataContract | None = None,
    *,
    chunksize: int = 100_000,
    on_error: IngestionPolicy = "warn",
    **read_csv_kwargs: Any,
) -> Iterator[tuple[pd.DataFrame, IngestionReport]]:
    """Read a CSV in chunks, yielding a typed frame and report per chunk.

    This is the memory-aware counterpart to :func:`read_csv_safe`. Each chunk is
    read as text, coerced under ``contract``, and audited independently, so the
    peak memory stays close to ``chunksize`` rows instead of the whole file.

    Parameters
    ----------
    source:
        Path or file-like object accepted by :func:`pandas.read_csv`.
    contract:
        Optional :class:`~data_cleaner.DataContract`. Passing a contract keeps
        typing consistent across chunks; without one, each chunk is inferred
        independently.
    chunksize:
        Number of rows per chunk. Must be a positive integer.
    on_error:
        ``"warn"`` logs findings, ``"raise"`` raises
        :class:`IngestionError` on the first failing chunk, and ``"ignore"``
        suppresses logging.
    **read_csv_kwargs:
        Extra options passed to :func:`pandas.read_csv`. The same reserved
        string-first options as :func:`read_csv_safe` are rejected.

    Yields
    ------
    tuple[pandas.DataFrame, IngestionReport]
        One typed frame and report per chunk. The report's ``rows`` is the chunk
        size, not the file size.
    """
    if contract is not None and not isinstance(contract, DataContract):
        raise TypeError("contract must be a DataContract instance or None")
    if on_error not in {"warn", "raise", "ignore"}:
        raise ValueError("on_error must be one of: warn, raise, ignore")
    if isinstance(chunksize, bool) or not isinstance(chunksize, int) or chunksize <= 0:
        raise ValueError("chunksize must be a positive integer")

    conflicts = sorted(_RESERVED_READ_KWARGS.intersection(read_csv_kwargs))
    if conflicts:
        raise TypeError(
            "iter_csv_safe manages these read_csv options itself: "
            f"{', '.join(conflicts)}"
        )

    reader = pd.read_csv(
        source,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        chunksize=chunksize,
        **read_csv_kwargs,
    )
    label = _source_label(source)
    for raw in reader:
        frame = _blank_to_na(raw, copy=False)
        yield _ingest_frame(
            frame,
            contract,
            source=label,
            sheet=None,
            on_error=on_error,
            format_name="CSV",
            input_label="CSV",
        )


def _excel_cell_to_text(value: object, date_format: str | None) -> object:
    """Turn one spreadsheet cell into the text form used by the guards."""
    if _is_missing(value):
        return pd.NA
    if isinstance(value, (pd.Timestamp, datetime, date, np.datetime64)):
        timestamp = pd.Timestamp(value)
        if date_format is not None:
            return timestamp.strftime(date_format)
        return timestamp.isoformat()
    if isinstance(value, (bool, np.bool_)):
        return "True" if value else "False"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)
    return str(value)


def _excel_frame_to_text(
    frame: pd.DataFrame, contract: DataContract | None
) -> pd.DataFrame:
    """Normalize every Excel cell to text and turn blanks into missing values."""
    specs = {spec.name: spec for spec in contract.columns} if contract else {}
    result = frame.copy(deep=True)
    for column in result.columns:
        spec = specs.get(str(column))
        date_format = spec.date_format if spec is not None else None
        result[column] = result[column].map(
            lambda value, fmt=date_format: _excel_cell_to_text(value, fmt)
        )
    return _blank_to_na(result, copy=False)


def _is_numeric_cell(value: object) -> bool:
    """Return whether an Excel cell holds a real number rather than a boolean."""
    if _is_missing(value):
        return False
    if isinstance(value, (bool, np.bool_)):
        return False
    return isinstance(value, (int, float, np.integer, np.floating))


def _numeric_identifier_counts(
    frame: pd.DataFrame, contract: DataContract | None
) -> dict[str, int]:
    """Count identifier cells that Excel stored as numbers."""
    if contract is None:
        return {}
    counts: dict[str, int] = {}
    for spec in contract.columns:
        if spec.role != "id" and not spec.preserve_leading_zeros:
            continue
        if spec.name not in frame.columns:
            continue
        numeric: pd.Series = frame[spec.name].map(_is_numeric_cell)
        count = int(numeric.sum())
        if count:
            counts[str(spec.name)] = count
    return counts


def read_excel_safe(
    source: str | os.PathLike[str] | IO[Any],
    contract: DataContract | None = None,
    *,
    sheet_name: str | int = 0,
    on_error: IngestionPolicy = "warn",
    **read_excel_kwargs: Any,
) -> tuple[pd.DataFrame, IngestionReport]:
    """Read one Excel worksheet, coerce it under a contract, and audit it.

    Parameters
    ----------
    source:
        Path or file-like object accepted by :func:`pandas.ExcelFile`.
    contract:
        Optional :class:`~data_cleaner.DataContract`. Declared columns use their
        role, dtype, and date format. Undeclared columns are inferred
        conservatively and reported as ``undeclared_column``; the report lists
        their detected and output kinds.
    sheet_name:
        Worksheet to read, either a name or a non-negative zero-based index. The
        default is the first sheet. The resolved sheet name is recorded on the
        report.
    on_error:
        ``"warn"`` logs error findings and returns the frame (default),
        ``"raise"`` raises :class:`IngestionError` when an error finding exists,
        and ``"ignore"`` suppresses logging while still returning the report.
    **read_excel_kwargs:
        Extra options passed to :meth:`pandas.ExcelFile.parse`. Options that would
        bypass the string-first read (``dtype``, ``dtype_backend``,
        ``na_filter``, ``keep_default_na``, ``na_values``, ``parse_dates``,
        ``converters``, ``decimal``, ``thousands``, ``true_values``, or
        ``false_values``) are rejected. ``engine``,
        ``storage_options``, and ``engine_kwargs`` are forwarded to
        :class:`pandas.ExcelFile` so the matching pandas engine is used.

    Returns
    -------
    tuple[pandas.DataFrame, IngestionReport]
        The typed frame and an audit report. String columns are kept as
        ``object`` dtype for consistency across pandas 2.x and 3.x.

    Notes
    -----
    Excel cells carry native types. The reader keeps those types long enough to
    detect identifiers stored as numbers, then applies the same identifier,
    date, numeric, and boolean guards as :func:`read_csv_safe`. Real date cells
    are parsed directly; numeric serials in a datetime column are parsed as
    dates and flagged with ``excel_serial_date``.

    An identifier cell that Excel stored as a number has already lost any
    leading zeros. The report emits a ``numeric_identifier`` warning when a
    contract declares such a column as an ID. Store identifiers as text in the
    workbook to preserve them.

    The ``excel`` extra installs ``openpyxl`` for ``.xlsx`` and ``.xlsm`` files.
    Legacy ``.xls``, ``.xlsb``, and ``.ods`` files need the matching optional
    pandas engine (``xlrd``, ``pyxlsb``, or ``odfpy``).
    """
    if contract is not None and not isinstance(contract, DataContract):
        raise TypeError("contract must be a DataContract instance or None")
    if on_error not in {"warn", "raise", "ignore"}:
        raise ValueError("on_error must be one of: warn, raise, ignore")
    if isinstance(sheet_name, bool) or not isinstance(sheet_name, (str, int)):
        raise TypeError("sheet_name must be a single worksheet name or index")
    if isinstance(sheet_name, int) and sheet_name < 0:
        raise ValueError("sheet_name index must be zero or greater")

    conflicts = sorted(_RESERVED_EXCEL_KWARGS.intersection(read_excel_kwargs))
    if conflicts:
        raise TypeError(
            "read_excel_safe manages these read_excel options itself: "
            f"{', '.join(conflicts)}"
        )

    engine = read_excel_kwargs.pop("engine", None)
    storage_options = read_excel_kwargs.pop("storage_options", None)
    engine_kwargs = read_excel_kwargs.pop("engine_kwargs", None)

    try:
        workbook = pd.ExcelFile(
            source,
            engine=engine,
            storage_options=storage_options,
            engine_kwargs=engine_kwargs,
        )
    except ImportError as exc:
        raise ImportError(
            "Excel ingestion requires an optional pandas engine. Install the "
            'Excel extra with `pip install "universal-data-cleaner[excel]"` '
            "(openpyxl for .xlsx/.xlsm), or install xlrd, pyxlsb, or odfpy for "
            "legacy formats."
        ) from exc

    try:
        sheet_names = list(workbook.sheet_names)
        resolved_sheet: str
        if isinstance(sheet_name, int):
            try:
                resolved_sheet = str(sheet_names[sheet_name])
            except IndexError as exc:
                raise ValueError(
                    f"sheet index {sheet_name} is out of range for "
                    f"{_source_label(source)}; available sheets: {sheet_names}"
                ) from exc
        else:
            resolved_sheet = sheet_name
            if resolved_sheet not in sheet_names:
                raise ValueError(
                    f"sheet '{resolved_sheet}' is missing from "
                    f"{_source_label(source)}; available sheets: {sheet_names}"
                )

        raw = workbook.parse(
            sheet_name=resolved_sheet,
            dtype=object,
            keep_default_na=False,
            na_filter=False,
            **read_excel_kwargs,
        )
    finally:
        workbook.close()

    raw = raw.copy(deep=True)
    raw.columns = [str(column) for column in raw.columns]
    header_index = pd.Index(raw.columns)
    if header_index.has_duplicates:
        duplicates = sorted(set(header_index[header_index.duplicated()].tolist()))
        raise ValueError(
            f"duplicate column headers in {_source_label(source)} "
            f"(sheet: {resolved_sheet}): {duplicates}"
        )
    numeric_identifiers = _numeric_identifier_counts(raw, contract)
    frame = _excel_frame_to_text(raw, contract)
    return _ingest_frame(
        frame,
        contract,
        source=_source_label(source),
        sheet=resolved_sheet,
        on_error=on_error,
        format_name="Excel",
        input_label="Excel worksheet",
        numeric_identifiers=numeric_identifiers,
    )
