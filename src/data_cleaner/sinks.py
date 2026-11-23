"""Append-only JSON Lines report sink for batch history and drift comparisons.

The sink stores one JSON object per line. It accepts a
:class:`~data_cleaner.CleanerReport`, a
:class:`~data_cleaner.DistributionDriftReport`, or a mapping, so a scheduled job
can keep a compact audit trail without a database. Drift reports include their
reference profile, which is what makes a later comparison against history
possible.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ._serialization import json_safe
from .drift import DistributionDriftReport, DriftPolicy, DriftProfile
from .reporting import CleanerReport

_SCHEMA_VERSION = 1


def _recorded_at(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value
    raise TypeError("recorded_at must be a datetime, a non-empty string, or None")


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _as_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float, np.integer, np.floating)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return default


class JsonlReportSink:
    """Append reports to a JSON Lines file and read the batch history back.

    Parameters
    ----------
    path:
        Destination file. It is created on first write.
    create_parents:
        Create missing parent directories when the sink is constructed.
    fsync:
        Flush each appended record to disk before returning. Off by default
        because it trades throughput for crash durability. When enabled, the
        parent directory is also synced the first time a file is created so the
        new entry itself is durable.
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        create_parents: bool = True,
        fsync: bool = False,
    ) -> None:
        self.path = Path(path)
        if create_parents:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fsync = fsync

    def __repr__(self) -> str:
        return f"JsonlReportSink({str(self.path)!r})"

    def write(
        self,
        report: CleanerReport | DistributionDriftReport | Mapping[str, Any],
        *,
        recorded_at: datetime | str | None = None,
        metadata: Mapping[str, Any] | None = None,
        source: str | None = None,
    ) -> dict[str, object]:
        """Append one report and return the stored record.

        Each record is a single line. The sink does not lock the file, so give
        each concurrent writer its own file or serialize writes externally.
        """
        if isinstance(report, CleanerReport):
            payload = report.to_dict()
            kind = "cleaner_report"
            report_source = source or report.source
            rows = _as_int(report.overview.get("rows"))
            success = report.success
            errors = len(report.errors)
            warnings = len(report.warnings)
            drifted: list[str] = []
        elif isinstance(report, DistributionDriftReport):
            payload = report.to_dict()
            kind = "drift_report"
            report_source = source or str((metadata or {}).get("source", "drift"))
            rows = report.current_rows
            success = not report.has_errors
            errors = len(report.errors)
            warnings = len(report.warnings)
            drifted = list(report.drifted_columns)
        elif isinstance(report, Mapping):
            payload = {str(key): json_safe(value) for key, value in report.items()}
            raw_kind = payload.get("kind", "record")
            kind = str(raw_kind)
            report_source = source or str(payload.get("source", "record"))
            rows = _as_int(payload.get("rows"))
            success = _as_bool(payload.get("success", True))
            errors = _as_int(payload.get("errors"))
            warnings = _as_int(payload.get("warnings"))
            raw_drifted = payload.get("drifted_columns", [])
            drifted = (
                [str(value) for value in raw_drifted]
                if isinstance(raw_drifted, (list, tuple))
                else []
            )
        else:
            raise TypeError(
                "report must be a CleanerReport, DistributionDriftReport, or mapping"
            )

        record: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "kind": kind,
            "recorded_at": _recorded_at(recorded_at),
            "source": report_source,
            "rows": rows,
            "success": success,
            "errors": errors,
            "warnings": warnings,
            "drifted_columns": drifted,
            "report": payload,
            "metadata": (
                {}
                if metadata is None
                else {str(key): json_safe(value) for key, value in metadata.items()}
            ),
        }
        self._append(record)
        return record

    def _append(self, record: Mapping[str, object]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        payload = line.encode("utf-8")
        created = not self.path.exists()
        descriptor = os.open(
            str(self.path),
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError(f"could not append to {self.path}")
                view = view[written:]
            if self.fsync:
                os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if self.fsync and created:
            self._sync_parent()

    def _sync_parent(self) -> None:
        try:
            descriptor = os.open(str(self.path.parent), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def read(self) -> list[dict[str, object]]:
        """Read every stored record, in append order."""
        if not self.path.exists():
            return []
        records: list[dict[str, object]] = []
        for number, line in enumerate(
            self.path.read_text(encoding="utf-8").split("\n"), start=1
        ):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSON in {self.path} on line {number}: {exc.msg}"
                ) from exc
            if not isinstance(record, dict):
                raise ValueError(
                    f"record on line {number} of {self.path} is not a JSON object"
                )
            records.append(record)
        return records

    def history(self) -> pd.DataFrame:
        """Return a one-row-per-batch summary of the stored records."""
        rows = [
            {
                "recorded_at": record.get("recorded_at"),
                "kind": record.get("kind"),
                "source": record.get("source"),
                "rows": record.get("rows"),
                "success": record.get("success"),
                "errors": record.get("errors"),
                "warnings": record.get("warnings"),
                "drifted_columns": record.get("drifted_columns", []),
            }
            for record in self.read()
        ]
        return pd.DataFrame(
            rows,
            columns=[
                "recorded_at",
                "kind",
                "source",
                "rows",
                "success",
                "errors",
                "warnings",
                "drifted_columns",
            ],
        )

    def latest(
        self,
        *,
        kind: str | None = None,
        source: str | None = None,
    ) -> dict[str, object] | None:
        """Return the most recently appended matching record, or ``None``."""
        for record in reversed(self.read()):
            if kind is not None and record.get("kind") != kind:
                continue
            if source is not None and record.get("source") != source:
                continue
            return record
        return None

    def drift_against_previous(
        self,
        frame: pd.DataFrame,
        *,
        policy: DriftPolicy | None = None,
        source: str | None = None,
    ) -> DistributionDriftReport:
        """Compare ``frame`` with the reference profile of the latest drift report.

        The recorded policy is reused when ``policy`` is omitted, so a historical
        comparison is reproducible with the thresholds that were in force when
        the reference report was written.
        """
        record = self.latest(kind="drift_report", source=source)
        if record is None:
            raise LookupError("the sink contains no matching drift report")
        payload = record.get("report")
        if not isinstance(payload, dict):
            raise ValueError("the stored drift report has no payload")
        raw_reference = payload.get("reference")
        if not isinstance(raw_reference, dict):
            raise ValueError("the stored drift report has no reference profile")
        profile = DriftProfile.from_dict(raw_reference)
        if policy is None:
            raw_policy = payload.get("policy")
            policy = (
                DriftPolicy.from_dict(raw_policy)
                if isinstance(raw_policy, dict)
                else None
            )
        return profile.compare(frame, policy=policy)
