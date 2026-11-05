"""One audit report for a batch: profile, contract, validation, and decisions."""

from __future__ import annotations

import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import IO, Any

import numpy as np
import pandas as pd

from ._version import __version__
from .contract import DataContract, DriftReport
from .decisions import DECISION_COLUMNS
from .ingestion import IngestionPolicy, IngestionReport, read_csv_safe
from .profiling import dataset_summary, profile_dataframe
from .validation import Expectation, ValidationReport, validate

_FINDING_COLUMNS = [
    "source",
    "column",
    "check",
    "severity",
    "message",
    "count",
]
_PROFILE_COLUMNS = [
    "dataset",
    "column",
    "dtype",
    "non_null",
    "missing",
    "missing_pct",
    "unique",
    "top",
    "top_freq",
]


def _json_safe(value: Any) -> object:
    """Convert pandas/numpy scalars into JSON-friendly values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, np.datetime64):
        return None if pd.isna(value) else pd.Timestamp(value).isoformat()
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Return rows with JSON-safe keys and values."""
    return [
        {str(key): _json_safe(value) for key, value in record.items()}
        for record in frame.to_dict("records")
    ]


def _markdown_table(frame: pd.DataFrame) -> str:
    """Render a DataFrame as Markdown, falling back to plain text."""
    if frame.empty:
        return "_No rows._"
    try:
        return frame.to_markdown(index=False)
    except ImportError:  # tabulate is optional
        return "```\n" + frame.to_string(index=False) + "\n```"


def _finding(
    source: str,
    column: str,
    check: str,
    severity: str,
    message: str,
    count: int,
) -> dict[str, object]:
    return {
        "source": source,
        "column": column,
        "check": check,
        "severity": severity,
        "message": message,
        "count": int(count),
    }


def _as_int(value: object, default: int = 0) -> int:
    """Coerce an overview metric to ``int`` without trusting its declared type."""
    if isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    return default


@dataclass(eq=False)
class CleanerReport:
    """A single review object for one DataFrame or CSV batch.

    The report combines the dataset profile with contract findings, validation
    results, ingestion findings, and (when available) the cleaner's decision
    log. It never mutates the input frame and never transforms it.

    Parameters
    ----------
    source:
        Human-readable label for the batch, usually a file name.
    overview:
        Dataset-level metrics from :func:`dataset_summary`.
    profile:
        Column-level profile from :func:`profile_dataframe`.
    drift:
        Contract findings for the batch, when a contract is available.
    validation:
        Expectation results, when expectations are supplied.
    ingestion:
        CSV ingestion findings, when the batch came from :func:`read_csv_safe`.
    decisions:
        The fitted cleaner's decision log, when auditing with a cleaner.
    high_missing_threshold:
        Missing-percentage at which the profile emits a ``high_missing``
        warning. Set to ``None`` to disable that warning.
    library_version:
        Version of Universal Data Cleaner that produced the report.
    """

    source: str
    overview: dict[str, object]
    profile: pd.DataFrame
    drift: DriftReport | None = None
    validation: ValidationReport | None = None
    ingestion: IngestionReport | None = None
    decisions: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=DECISION_COLUMNS)
    )
    high_missing_threshold: float | None = 50.0
    library_version: str = __version__

    def __post_init__(self) -> None:
        if self.high_missing_threshold is not None and not (
            0 <= self.high_missing_threshold <= 100
        ):
            raise ValueError("high_missing_threshold must be between 0 and 100")

    def __repr__(self) -> str:
        return (
            f"CleanerReport(source={self.source!r}, "
            f"rows={self.overview.get('rows')}, "
            f"columns={self.overview.get('columns')}, "
            f"success={self.success})"
        )

    @classmethod
    def from_frame(
        cls,
        frame: pd.DataFrame,
        *,
        source: str = "dataset",
        name: str = "dataset",
        contract: DataContract | None = None,
        expectations: Expectation | Sequence[Expectation] | None = None,
        ingestion: IngestionReport | None = None,
        decisions: pd.DataFrame | None = None,
        include_profile: bool = True,
        high_missing_threshold: float | None = 50.0,
    ) -> CleanerReport:
        """Build a report for an in-memory DataFrame.

        Parameters
        ----------
        frame:
            The batch to inspect. It is never modified.
        source:
            Label recorded in the report.
        name:
            Dataset name used in the column profile.
        contract:
            Optional contract. When provided, its findings become the report's
            contract section.
        expectations:
            Optional expectation or sequence of expectations to evaluate.
        ingestion:
            Optional ingestion report to attach, for example from
            :func:`read_csv_safe`.
        decisions:
            Optional decision log to attach, for example from a fitted cleaner.
        include_profile:
            Compute the column-level profile. Disable it for very large batches
            when only findings are needed.
        high_missing_threshold:
            Missing-percentage threshold for a ``high_missing`` warning.
        """
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("frame must be a pandas DataFrame")
        if contract is not None and not isinstance(contract, DataContract):
            raise TypeError("contract must be a DataContract instance or None")

        overview = dataset_summary(frame)
        profile = (
            profile_dataframe(frame, name=name)
            if include_profile
            else pd.DataFrame(columns=_PROFILE_COLUMNS)
        )
        drift = contract.check(frame) if contract is not None else None
        validation = validate(frame, expectations) if expectations is not None else None
        decision_log = (
            decisions
            if decisions is not None
            else pd.DataFrame(columns=DECISION_COLUMNS)
        )
        return cls(
            source=source,
            overview=overview,
            profile=profile,
            drift=drift,
            validation=validation,
            ingestion=ingestion,
            decisions=decision_log,
            high_missing_threshold=high_missing_threshold,
        )

    @classmethod
    def from_csv(
        cls,
        source: str | os.PathLike[str] | IO[Any],
        *,
        contract: DataContract | None = None,
        expectations: Expectation | Sequence[Expectation] | None = None,
        name: str | None = None,
        include_profile: bool = True,
        high_missing_threshold: float | None = 50.0,
        on_error: IngestionPolicy = "ignore",
        **read_csv_kwargs: Any,
    ) -> CleanerReport:
        """Read a CSV with :func:`read_csv_safe` and audit the result.

        The default ``on_error="ignore"`` always returns a report; error
        findings still make :attr:`success` false. Pass ``"raise"`` to stop at
        the first unparseable value instead.
        """
        frame, ingestion = read_csv_safe(
            source,
            contract=contract,
            on_error=on_error,
            **read_csv_kwargs,
        )
        dataset_name = name or os.path.splitext(os.path.basename(ingestion.source))[0]
        return cls.from_frame(
            frame,
            source=ingestion.source,
            name=dataset_name or "dataset",
            contract=contract,
            expectations=expectations,
            ingestion=ingestion,
            include_profile=include_profile,
            high_missing_threshold=high_missing_threshold,
        )

    @classmethod
    def from_cleaner(
        cls,
        cleaner: Any,
        frame: pd.DataFrame,
        *,
        source: str = "batch",
        name: str = "batch",
        expectations: Expectation | Sequence[Expectation] | None = None,
        ingestion: IngestionReport | None = None,
        include_profile: bool = True,
        high_missing_threshold: float | None = 50.0,
    ) -> CleanerReport:
        """Audit a batch against a fitted :class:`~data_cleaner.DataCleaner`.

        The cleaner's fitted contract supplies the drift section and its
        decision log is attached to the report. The cleaner is not re-fitted
        and the batch is not transformed.
        """
        from .cleaner import DataCleaner

        if not isinstance(cleaner, DataCleaner):
            raise TypeError("cleaner must be a DataCleaner")
        contract = cleaner.fitted_contract()
        decisions = cleaner.decision_log()
        return cls.from_frame(
            frame,
            source=source,
            name=name,
            contract=contract,
            expectations=expectations,
            ingestion=ingestion,
            decisions=decisions,
            include_profile=include_profile,
            high_missing_threshold=high_missing_threshold,
        )

    def _profile_findings(self) -> list[dict[str, object]]:
        rows = _as_int(self.overview.get("rows"))
        columns = _as_int(self.overview.get("columns"))
        duplicates = _as_int(self.overview.get("duplicate_rows"))
        findings: list[dict[str, object]] = []

        if rows == 0:
            findings.append(
                _finding(
                    "profile",
                    "*",
                    "empty_dataset",
                    "warning",
                    "dataset has no rows",
                    0,
                )
            )
        if duplicates:
            findings.append(
                _finding(
                    "profile",
                    "*",
                    "duplicate_rows",
                    "warning",
                    f"dataset has {duplicates} duplicate row(s)",
                    duplicates,
                )
            )
        if self.profile.empty:
            return findings

        for _, row in self.profile.iterrows():
            column = str(row["column"])
            non_null = int(row["non_null"])
            missing = int(row["missing"])
            missing_pct = float(row["missing_pct"])
            unique = int(row["unique"])

            if rows and non_null == 0:
                findings.append(
                    _finding(
                        "profile",
                        column,
                        "empty_column",
                        "warning",
                        f"column '{column}' has no non-null values",
                        rows,
                    )
                )
            elif non_null and unique == 1:
                findings.append(
                    _finding(
                        "profile",
                        column,
                        "constant_column",
                        "warning",
                        f"column '{column}' has a single distinct value",
                        non_null,
                    )
                )

            if (
                self.high_missing_threshold is not None
                and rows
                and non_null
                and missing_pct >= self.high_missing_threshold
            ):
                findings.append(
                    _finding(
                        "profile",
                        column,
                        "high_missing",
                        "warning",
                        f"column '{column}' is {missing_pct:.1f}% missing",
                        missing,
                    )
                )

        if columns == 0:
            findings.append(
                _finding(
                    "profile",
                    "*",
                    "empty_dataset",
                    "warning",
                    "dataset has no columns",
                    0,
                )
            )
        return findings

    @property
    def findings(self) -> pd.DataFrame:
        """A tidy table of every error and warning in the report."""
        rows: list[dict[str, object]] = []

        if self.ingestion is not None and not self.ingestion.findings.empty:
            for _, row in self.ingestion.findings.iterrows():
                rows.append(
                    _finding(
                        "ingestion",
                        str(row["column"]),
                        str(row["check"]),
                        str(row["severity"]),
                        str(row["message"]),
                        int(row["count"]),
                    )
                )

        if self.drift is not None and self.drift.has_drift:
            for _, row in self.drift.findings.iterrows():
                rows.append(
                    _finding(
                        "contract",
                        str(row["column"]),
                        str(row["check"]),
                        str(row["severity"]),
                        str(row["message"]),
                        1,
                    )
                )

        if self.validation is not None and not self.validation.failures.empty:
            for _, row in self.validation.failures.iterrows():
                observed = row["observed"]
                count = (
                    int(observed)
                    if isinstance(observed, (int, np.integer))
                    and not isinstance(observed, (bool, np.bool_))
                    else 1
                )
                rows.append(
                    _finding(
                        "validation",
                        str(row["column"]) if row["column"] is not None else "*",
                        str(row["expectation"]),
                        str(row["severity"]),
                        str(row["message"]),
                        count,
                    )
                )

        rows.extend(self._profile_findings())
        frame = pd.DataFrame(rows, columns=_FINDING_COLUMNS)
        if frame.empty:
            return frame
        frame = frame.drop_duplicates(
            subset=["column", "check", "severity"], keep="first"
        )
        return frame.sort_values(
            ["severity", "source", "column"], kind="stable"
        ).reset_index(drop=True)

    @property
    def errors(self) -> pd.DataFrame:
        """Findings with error severity."""
        findings = self.findings
        if findings.empty:
            return findings
        return findings[findings["severity"] == "error"].reset_index(drop=True)

    @property
    def warnings(self) -> pd.DataFrame:
        """Findings with warning severity."""
        findings = self.findings
        if findings.empty:
            return findings
        return findings[findings["severity"] == "warning"].reset_index(drop=True)

    @property
    def has_errors(self) -> bool:
        """Whether at least one error-severity finding exists."""
        return not self.errors.empty

    @property
    def has_warnings(self) -> bool:
        """Whether at least one warning-severity finding exists."""
        return not self.warnings.empty

    @property
    def success(self) -> bool:
        """Whether the batch has no error-severity findings."""
        return not self.has_errors

    def _status_line(self) -> str:
        status = "PASS" if self.success else "FAIL"
        return (
            f"{status} — {_as_int(self.overview.get('rows'))} row(s), "
            f"{_as_int(self.overview.get('columns'))} column(s), "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )

    def summary(self) -> str:
        """Return a short human-readable description of the report."""
        lines = [self._status_line()]
        for _, row in self.findings.iterrows():
            lines.append(
                f"- [{row['severity']}] {row['source']}/{row['check']} "
                f"on '{row['column']}': {row['message']}"
            )
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render the whole report as Markdown."""
        lines = [f"# Cleaner report: {self.source}", "", self._status_line(), ""]

        lines.extend(["## Overview", ""])
        overview = pd.DataFrame(
            [
                {"metric": key, "value": _json_safe(value)}
                for key, value in self.overview.items()
            ]
        )
        lines.extend([_markdown_table(overview), ""])

        lines.extend(["## Findings", ""])
        lines.extend([_markdown_table(self.findings), ""])

        lines.extend(["## Column profile", ""])
        lines.extend([_markdown_table(self.profile), ""])

        lines.extend(["## Contract drift", ""])
        if self.drift is None:
            lines.extend(["No contract configured.", ""])
        elif not self.drift.has_drift:
            lines.extend(["No contract drift detected.", ""])
        else:
            lines.extend([_markdown_table(self.drift.findings), ""])

        lines.extend(["## Validation", ""])
        if self.validation is None:
            lines.extend(["No expectations were evaluated.", ""])
        else:
            lines.extend([_markdown_table(self.validation.results), ""])

        if self.ingestion is not None:
            lines.extend(["## Ingestion", "", self.ingestion.to_markdown(), ""])

        lines.extend(["## Decisions", ""])
        if self.decisions.empty:
            lines.extend(["No cleaner decisions available.", ""])
        else:
            lines.extend([_markdown_table(self.decisions), ""])

        return "\n".join(lines).rstrip() + "\n"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation of the report."""
        return {
            "source": self.source,
            "library_version": self.library_version,
            "success": self.success,
            "overview": {
                str(key): _json_safe(value) for key, value in self.overview.items()
            },
            "findings": _records(self.findings),
            "profile": _records(self.profile),
            "contract": (
                None
                if self.drift is None
                else {
                    "has_drift": self.drift.has_drift,
                    "has_errors": self.drift.has_errors,
                    "findings": _records(self.drift.findings),
                }
            ),
            "validation": (
                None
                if self.validation is None
                else {
                    "source": self.validation.source,
                    "success": self.validation.success,
                    "results": _records(self.validation.results),
                }
            ),
            "ingestion": (None if self.ingestion is None else self.ingestion.to_dict()),
            "decisions": _records(self.decisions),
            "high_missing_threshold": self.high_missing_threshold,
        }

    def to_json(self, **kwargs: object) -> str:
        """Serialize the report to JSON."""
        return json.dumps(self.to_dict(), **kwargs)  # type: ignore[arg-type]

    def raise_if_failed(self, message: str = "Batch audit failed") -> None:
        """Raise ``ValueError`` when any error-severity finding exists."""
        if not self.success:
            raise ValueError(f"{message}:\n{self.summary()}")
