"""Statistical distribution drift against a reference frame.

The drift layer is intentionally dependency-light: PSI, Wasserstein distance,
missingness deltas, and category deltas are computed with NumPy and pandas only.
A :class:`DriftProfile` stores a compact, JSON-friendly summary of a reference
frame, so the same reference can be reused or persisted without keeping the raw
data.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields
from numbers import Integral, Real
from typing import Literal, cast

import numpy as np
import pandas as pd

from ._roles import _series_kind
from ._serialization import json_records, json_safe
from .validation import Severity

Status = Literal["stable", "warning", "error"]

_EPSILON = 1e-6
_STABLE = "stable"
_OTHER_LABEL = "(other)"


def _require_frame(frame: object) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    return frame


def _validate_columns(frame: pd.DataFrame) -> None:
    if frame.columns.duplicated().any():
        raise ValueError("frame has duplicate column labels")
    non_string = [name for name in frame.columns if not isinstance(name, str)]
    if non_string:
        raise TypeError(
            f"drift profiling requires string column labels; found {non_string[:3]!r}"
        )


def _column_kind(series: pd.Series) -> str:
    """Return the drift kind for a column: numeric, datetime, or categorical."""
    kind = _series_kind(series)
    if kind == "datetime":
        return "datetime"
    if kind == "numeric":
        return "numeric"
    return "categorical"


def _kind_matches(expected: str, current: str) -> bool:
    if expected == "datetime":
        return current == "datetime"
    if expected == "numeric":
        return current == "numeric"
    return current in {"categorical", "boolean"}


def _pct(count: float, total: int) -> float:
    return 100.0 * count / total if total else 0.0


def _worst(*severities: str | None) -> Severity | None:
    if "error" in severities:
        return "error"
    if "warning" in severities:
        return "warning"
    return None


def _severity_for(
    value: float | None,
    warning: float | None,
    error: float | None,
) -> Severity | None:
    if value is None or not math.isfinite(value):
        return None
    if error is not None and value >= error:
        return "error"
    if warning is not None and value >= warning:
        return "warning"
    return None


def _check_thresholds(name: str, warning: float | None, error: float | None) -> None:
    for label, threshold in (("warning", warning), ("error", error)):
        if threshold is not None and threshold < 0:
            raise ValueError(f"{name}_{label} must be non-negative")
    if warning is not None and error is not None and error < warning:
        raise ValueError(
            f"{name}_error must be greater than or equal to {name}_warning"
        )


@dataclass(frozen=True, slots=True)
class DriftPolicy:
    """Thresholds and sampling controls for a distribution comparison.

    PSI follows the conventional interpretation: below ``psi_warning`` the
    distributions are considered stable, at or above ``psi_warning`` the shift is
    moderate, and at or above ``psi_error`` it is major. Missingness and category
    deltas are expressed in percentage points. Wasserstein thresholds apply to a
    scale-free ratio (distance divided by the reference standard deviation, or
    by the value range when the deviation is zero), so the same policy works
    across columns with different units.

    ``min_sample`` downgrades an error-severity finding to a warning when either
    side has fewer than that many rows, because small samples make every metric
    unstable. Set it to ``0`` to disable the downgrade.

    Thresholds must be finite and non-negative, with each error threshold greater
    than or equal to its warning threshold. Counts must be integers. Values are
    normalized when the policy is created, so NumPy integers round-trip cleanly
    through JSON.
    """

    psi_warning: float | None = 0.10
    psi_error: float | None = 0.25
    wasserstein_warning: float | None = None
    wasserstein_error: float | None = None
    missing_delta_warning: float | None = 5.0
    missing_delta_error: float | None = None
    category_delta_warning: float | None = 10.0
    category_delta_error: float | None = None
    min_sample: int = 20
    bins: int = 10
    max_categories: int = 20
    max_columns: int = 200
    wasserstein_points: int = 512

    def __post_init__(self) -> None:
        for name in (
            "psi_warning",
            "psi_error",
            "wasserstein_warning",
            "wasserstein_error",
            "missing_delta_warning",
            "missing_delta_error",
            "category_delta_warning",
            "category_delta_error",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, Real):
                raise TypeError(f"{name} must be a number or None")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"{name} must be finite")
            if number < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, number)
        for name in (
            "min_sample",
            "bins",
            "max_categories",
            "max_columns",
            "wasserstein_points",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral):
                raise TypeError(f"{name} must be an integer")
            object.__setattr__(self, name, int(value))
        _check_thresholds("psi", self.psi_warning, self.psi_error)
        _check_thresholds(
            "wasserstein", self.wasserstein_warning, self.wasserstein_error
        )
        _check_thresholds(
            "missing_delta", self.missing_delta_warning, self.missing_delta_error
        )
        _check_thresholds(
            "category_delta", self.category_delta_warning, self.category_delta_error
        )
        if not 2 <= self.bins <= 200:
            raise ValueError("bins must be between 2 and 200")
        if not 1 <= self.max_categories <= 1000:
            raise ValueError("max_categories must be between 1 and 1000")
        if not 1 <= self.max_columns <= 10_000:
            raise ValueError("max_columns must be between 1 and 10000")
        if not 2 <= self.wasserstein_points <= 10_000:
            raise ValueError("wasserstein_points must be between 2 and 10000")
        if self.min_sample < 0:
            raise ValueError("min_sample must be non-negative")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the policy."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DriftPolicy:
        """Rebuild a policy from :meth:`to_dict` output."""
        known = {field.name for field in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"Unknown drift policy field(s): {unknown}")
        return cls(**dict(data.items()))  # type: ignore[arg-type]

    def to_json(self, **kwargs: object) -> str:
        """Serialize the policy to JSON."""
        return json.dumps(self.to_dict(), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, text: str) -> DriftPolicy:
        """Parse a policy from JSON."""
        return cls.from_dict(json.loads(text))


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class _NumericProfile:
    kind: str
    missing_pct: float
    edges: tuple[float, ...]
    proportions: tuple[float, ...]
    scale: float | None
    quantiles: tuple[float, ...]

    def __repr__(self) -> str:
        return (
            f"_NumericProfile(kind={self.kind!r}, missing_pct={self.missing_pct!r}, "
            f"bins={len(self.proportions)})"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "missing_pct": self.missing_pct,
            "edges": list(self.edges),
            "proportions": list(self.proportions),
            "scale": self.scale,
            "quantiles": list(self.quantiles),
        }


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class _CategoricalProfile:
    kind: str
    missing_pct: float
    levels: tuple[str, ...]
    proportions: tuple[float, ...]
    other_proportion: float

    def __repr__(self) -> str:
        return (
            f"_CategoricalProfile(kind={self.kind!r}, "
            f"missing_pct={self.missing_pct!r}, levels={len(self.levels)})"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "missing_pct": self.missing_pct,
            "levels": list(self.levels),
            "proportions": list(self.proportions),
            "other_proportion": self.other_proportion,
        }


_ColumnProfile = _NumericProfile | _CategoricalProfile


def _numeric_values(series: pd.Series, kind: str) -> np.ndarray:
    values = series.dropna()
    if kind == "datetime":
        timezone = getattr(values.dt, "tz", None)
        epoch = pd.Timestamp("1970-01-01", tz="UTC" if timezone is not None else None)
        return ((values - epoch) / pd.Timedelta(seconds=1)).to_numpy(dtype="float64")
    numeric = pd.to_numeric(values, errors="coerce")
    numeric = numeric.replace([np.inf, -np.inf], np.nan).dropna()
    return numeric.to_numpy(dtype="float64")


def _numeric_profile(
    series: pd.Series, total: int, policy: DriftPolicy, kind: str
) -> _NumericProfile:
    values = _numeric_values(series, kind)
    missing = total - values.size
    if values.size == 0:
        return _NumericProfile(
            kind=kind,
            missing_pct=100.0,
            edges=(0.0, 0.0),
            proportions=(0.0, 0.0, 1.0),
            scale=None,
            quantiles=(),
        )
    quartiles = np.quantile(values, np.linspace(0.0, 1.0, policy.bins + 1))
    edges = np.unique(quartiles)
    if edges.size <= 2:
        # One or two distinct quantile edges (constant or binary/tied data).
        # Split at the first edge so a full shift between the two values is
        # still visible to PSI instead of collapsing into a single bin.
        threshold = float(edges[0])
        below = float(np.count_nonzero(values <= threshold))
        counts = np.array([below, float(values.size) - below])
        if edges.size == 2:
            edges = np.array([threshold, float(edges[1])])
    else:
        codes = np.searchsorted(edges[1:-1], values, side="right")
        counts = np.bincount(codes, minlength=edges.size - 1).astype("float64")
    proportions = np.append(counts / total, missing / total)

    std = float(np.std(values))
    spread = float(values.max() - values.min())
    scale = std if std > 0 else (spread if spread > 0 else None)
    # Store a bounded quantile summary, never the raw sorted column. Midpoint
    # probabilities keep the smallest and largest values out of the profile.
    probabilities = (
        np.arange(policy.wasserstein_points, dtype="float64") + 0.5
    ) / policy.wasserstein_points
    quantiles = np.quantile(values, probabilities)
    return _NumericProfile(
        kind=kind,
        missing_pct=_pct(missing, total),
        edges=tuple(float(edge) for edge in edges),
        proportions=tuple(float(value) for value in proportions),
        scale=scale,
        quantiles=tuple(float(value) for value in quantiles),
    )


def _ordered_categories(values: pd.Series) -> list[tuple[str, int]]:
    counts = values.astype(str).value_counts()
    return sorted(
        ((str(label), int(count)) for label, count in counts.items()),
        key=lambda item: (-item[1], item[0]),
    )


def _categorical_profile(
    series: pd.Series, total: int, policy: DriftPolicy
) -> _CategoricalProfile:
    ordered = _ordered_categories(series.dropna())
    levels = tuple(label for label, _ in ordered[: policy.max_categories])
    level_counts = dict(ordered)
    kept = sum(level_counts[label] for label in levels)
    other = int(series.notna().sum()) - kept
    missing = int(series.isna().sum())
    proportions = tuple(float(level_counts[label]) / total for label in levels)
    return _CategoricalProfile(
        kind="categorical",
        missing_pct=_pct(missing, total),
        levels=levels,
        proportions=proportions,
        other_proportion=float(other) / total,
    )


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class DriftProfile:
    """A compact reference summary for distribution comparisons.

    Build it once from a reference (training) frame and reuse it for every
    batch. Numeric columns keep quantile bin edges and a bounded quantile sample
    used for the Wasserstein distance; categorical columns keep the most common
    levels plus an ``other`` bucket. Everything is JSON-serializable, so a
    profile survives a round trip through a report sink.

    The profile is a derived summary, not a copy of the reference rows. It still
    contains quantile values and retained category labels, so treat it as you
    would treat a schema and avoid logging it. The default ``repr`` is redacted.
    """

    columns: dict[str, _ColumnProfile]
    policy: DriftPolicy
    rows: int
    skipped_columns: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return (
            f"DriftProfile(rows={self.rows!r}, "
            f"columns={len(self.columns)}, "
            f"skipped_columns={len(self.skipped_columns)})"
        )

    @classmethod
    def from_frame(
        cls,
        frame: pd.DataFrame,
        *,
        columns: list[str] | tuple[str, ...] | None = None,
        policy: DriftPolicy | None = None,
    ) -> DriftProfile:
        """Profile a reference frame.

        Parameters
        ----------
        frame:
            Reference data. It is never modified.
        columns:
            Columns to profile. When omitted, every numeric, categorical,
            boolean, and datetime column is profiled, up to ``policy.max_columns``
            in frame order. An explicit list is never truncated.
        policy:
            Thresholds and sampling controls stored with the profile.

        Raises
        ------
        ValueError
            If the frame is empty or no comparable columns are available.
        KeyError
            If an explicitly requested column is missing.
        """
        data = _require_frame(frame)
        if len(data) == 0:
            raise ValueError("reference frame is empty")
        _validate_columns(data)
        active = policy if policy is not None else DriftPolicy()

        skipped: tuple[str, ...] = ()
        if columns is None:
            selected = [
                name
                for name in data.columns
                if _column_kind(data[name]) in {"numeric", "categorical", "datetime"}
            ]
            if len(selected) > active.max_columns:
                skipped = tuple(selected[active.max_columns :])
                selected = selected[: active.max_columns]
        else:
            if isinstance(columns, str):  # type: ignore[unreachable]
                raise TypeError(
                    "columns must be a list or tuple of column names, not a string"
                )
            selected = list(columns)
            if len(set(selected)) != len(selected):
                raise ValueError("columns must not contain duplicates")
            for name in selected:
                if name not in data.columns:
                    raise KeyError(f"column '{name}' is not in the reference frame")
        if not selected:
            raise ValueError("reference frame has no comparable columns")

        total = len(data)
        profiled: dict[str, _ColumnProfile] = {}
        for name in selected:
            series = data[name]
            kind = _column_kind(series)
            if kind == "categorical":
                profiled[name] = _categorical_profile(series, total, active)
            else:
                profiled[name] = _numeric_profile(series, total, active, kind)
        return cls(
            columns=profiled,
            policy=active,
            rows=total,
            skipped_columns=skipped,
        )

    def compare(
        self, frame: pd.DataFrame, *, policy: DriftPolicy | None = None
    ) -> DistributionDriftReport:
        """Compare ``frame`` against this reference profile.

        The reference columns decide what is compared. Columns present only in
        ``frame`` are ignored; reference columns missing from ``frame`` are
        reported as structural errors.
        """
        data = _require_frame(frame)
        if len(data) == 0:
            raise ValueError("current frame is empty")
        if data.columns.duplicated().any():
            raise ValueError("frame has duplicate column labels")
        active = policy if policy is not None else self.policy
        total = len(data)
        column_rows: list[dict[str, object]] = []
        category_rows: list[dict[str, object]] = []

        for name, stats in self.columns.items():
            if name not in data.columns:
                column_rows.append(
                    self._row(
                        name,
                        stats,
                        total,
                        severity="error",
                        message="column is missing from the current frame",
                    )
                )
                continue

            series = data[name]
            current_kind = _column_kind(series)
            if not _kind_matches(stats.kind, current_kind):
                column_rows.append(
                    self._row(
                        name,
                        stats,
                        total,
                        severity="error",
                        message=(
                            f"kind changed from {stats.kind} to {current_kind}; "
                            "distribution metrics were skipped"
                        ),
                    )
                )
                continue

            if isinstance(stats, _NumericProfile):
                row = self._compare_numeric(name, stats, series, total, active)
                column_rows.append(row)
            else:
                row, categories = self._compare_categorical(
                    name, stats, series, total, active
                )
                column_rows.append(row)
                category_rows.extend(categories)

        columns = pd.DataFrame(
            column_rows,
            columns=[
                "column",
                "kind",
                "reference_rows",
                "current_rows",
                "psi",
                "wasserstein",
                "wasserstein_ratio",
                "missing_reference_pct",
                "missing_current_pct",
                "missing_delta_pp",
                "max_category_delta_pp",
                "other_categories",
                "severity",
                "status",
                "message",
            ],
        )
        categories = pd.DataFrame(
            category_rows,
            columns=[
                "column",
                "category",
                "reference_share_pct",
                "current_share_pct",
                "delta_pp",
                "other",
                "severity",
            ],
        )
        return DistributionDriftReport(
            columns=columns,
            categories=categories,
            reference_rows=self.rows,
            current_rows=total,
            policy=active,
            reference=self,
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation of the profile."""
        return cast(
            dict[str, object],
            json_safe(
                {
                    "rows": self.rows,
                    "policy": self.policy.to_dict(),
                    "skipped_columns": list(self.skipped_columns),
                    "columns": {
                        name: stats.to_dict() for name, stats in self.columns.items()
                    },
                }
            ),
        )

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DriftProfile:
        """Rebuild a profile from :meth:`to_dict` output."""
        raw_columns = data.get("columns")
        if not isinstance(raw_columns, dict):
            raise TypeError("profile 'columns' must be a mapping")
        profiled: dict[str, _ColumnProfile] = {}
        for name, payload in raw_columns.items():
            if not isinstance(payload, dict):
                raise TypeError(f"profile column '{name}' must be a mapping")
            kind = str(payload.get("kind", "categorical"))
            if kind in {"numeric", "datetime"}:
                profiled[str(name)] = _NumericProfile(
                    kind=kind,
                    missing_pct=float(payload.get("missing_pct", 0.0)),
                    edges=tuple(float(value) for value in payload.get("edges", ())),
                    proportions=tuple(
                        float(value) for value in payload.get("proportions", ())
                    ),
                    scale=(
                        None
                        if payload.get("scale") is None
                        else float(payload["scale"])
                    ),
                    quantiles=tuple(
                        float(value) for value in payload.get("quantiles", ())
                    ),
                )
            else:
                profiled[str(name)] = _CategoricalProfile(
                    kind="categorical",
                    missing_pct=float(payload.get("missing_pct", 0.0)),
                    levels=tuple(str(value) for value in payload.get("levels", ())),
                    proportions=tuple(
                        float(value) for value in payload.get("proportions", ())
                    ),
                    other_proportion=float(payload.get("other_proportion", 0.0)),
                )
        raw_policy = data.get("policy")
        policy = (
            DriftPolicy.from_dict(raw_policy)
            if isinstance(raw_policy, dict)
            else DriftPolicy()
        )
        raw_rows = data.get("rows", 0)
        rows = int(raw_rows) if isinstance(raw_rows, (int, float)) else 0
        raw_skipped = data.get("skipped_columns", ())
        skipped = (
            tuple(str(value) for value in raw_skipped)
            if isinstance(raw_skipped, (list, tuple))
            else ()
        )
        return cls(
            columns=profiled,
            policy=policy,
            rows=rows,
            skipped_columns=skipped,
        )

    def to_json(self, **kwargs: object) -> str:
        """Serialize the profile to JSON."""
        return json.dumps(self.to_dict(), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, text: str) -> DriftProfile:
        """Parse a profile from JSON."""
        return cls.from_dict(json.loads(text))

    def _row(
        self,
        name: str,
        stats: _ColumnProfile,
        current_rows: int,
        *,
        severity: Severity | None,
        message: str,
        psi: float | None = None,
        wasserstein: float | None = None,
        wasserstein_ratio: float | None = None,
        missing_current_pct: float | None = None,
        max_category_delta_pp: float | None = None,
        other: int = 0,
    ) -> dict[str, object]:
        reference_missing = stats.missing_pct
        current_missing = (
            reference_missing if missing_current_pct is None else missing_current_pct
        )
        return {
            "column": name,
            "kind": stats.kind,
            "reference_rows": self.rows,
            "current_rows": current_rows,
            "psi": psi,
            "wasserstein": wasserstein,
            "wasserstein_ratio": wasserstein_ratio,
            "missing_reference_pct": reference_missing,
            "missing_current_pct": current_missing,
            "missing_delta_pp": current_missing - reference_missing,
            "max_category_delta_pp": max_category_delta_pp,
            "other_categories": other,
            "severity": severity,
            "status": severity or _STABLE,
            "message": message,
        }

    def _compare_numeric(
        self,
        name: str,
        stats: _NumericProfile,
        series: pd.Series,
        total: int,
        policy: DriftPolicy,
    ) -> dict[str, object]:
        values = _numeric_values(series, stats.kind)
        missing = total - values.size
        edges = np.asarray(stats.edges, dtype="float64")
        if edges.size <= 2:
            # A constant or two-edge reference has a single split point. Splitting
            # there keeps a full shift between the two values visible to PSI
            # instead of collapsing into one bin.
            threshold = float(edges[0])
            below = float(np.count_nonzero(values <= threshold))
            counts = np.array([below, float(values.size) - below])
        else:
            codes = np.searchsorted(edges[1:-1], values, side="right")
            counts = np.bincount(codes, minlength=max(edges.size - 1, 1)).astype(
                "float64"
            )
        current = np.append(counts / total, missing / total)
        reference = np.asarray(stats.proportions, dtype="float64")
        if reference.size != current.size:
            raise ValueError(
                f"reference profile for column '{name}' has inconsistent buckets"
            )
        psi = _psi(reference, current)

        reference_sample = np.asarray(stats.quantiles, dtype="float64")
        if reference_sample.size and values.size:
            probabilities = (
                np.arange(reference_sample.size, dtype="float64") + 0.5
            ) / reference_sample.size
            current_sample = np.quantile(values, probabilities)
            wasserstein = float(np.mean(np.abs(reference_sample - current_sample)))
        else:
            wasserstein = None
        ratio = (
            wasserstein / stats.scale
            if wasserstein is not None and stats.scale not in (None, 0.0)
            else None
        )
        missing_pct = _pct(missing, total)

        psi_severity = _severity_for(psi, policy.psi_warning, policy.psi_error)
        missing_severity = _severity_for(
            abs(missing_pct - stats.missing_pct),
            policy.missing_delta_warning,
            policy.missing_delta_error,
        )
        wasserstein_severity = _severity_for(
            ratio, policy.wasserstein_warning, policy.wasserstein_error
        )
        severity = _worst(psi_severity, missing_severity, wasserstein_severity)
        severity = _downgrade(severity, self.rows, total, policy)
        reasons: list[str] = []
        if psi_severity:
            reasons.append(f"PSI {psi:.3f}")
        if missing_severity:
            reasons.append(f"missingness {missing_pct - stats.missing_pct:+.1f} pp")
        if wasserstein_severity and ratio is not None:
            reasons.append(f"Wasserstein ratio {ratio:.3f}")
        message = (
            "distribution is stable"
            if severity is None
            else ", ".join(reasons) + " exceeds the configured threshold"
        )
        return self._row(
            name,
            stats,
            total,
            severity=severity,
            message=message,
            psi=psi,
            wasserstein=wasserstein,
            wasserstein_ratio=ratio,
            missing_current_pct=missing_pct,
        )

    def _compare_categorical(
        self,
        name: str,
        stats: _CategoricalProfile,
        series: pd.Series,
        total: int,
        policy: DriftPolicy,
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        strings = series.dropna().astype(str)
        counts = strings.value_counts()
        level_index = {level: index for index, level in enumerate(stats.levels)}
        codes = (
            strings.map(level_index).fillna(len(stats.levels)).to_numpy(dtype="int64")
        )
        buckets = np.bincount(codes, minlength=len(stats.levels) + 1).astype("float64")
        missing = int(series.isna().sum())
        current = np.append(buckets / total, missing / total)
        reference = np.concatenate(
            [
                np.asarray(stats.proportions, dtype="float64"),
                np.asarray(
                    [stats.other_proportion, stats.missing_pct / 100.0],
                    dtype="float64",
                ),
            ]
        )
        if reference.size != current.size:
            raise ValueError(
                f"reference profile for column '{name}' has inconsistent buckets"
            )
        psi = _psi(reference, current)
        missing_pct = _pct(missing, total)

        current_counts = {str(label): int(count) for label, count in counts.items()}
        outside = {
            label: count
            for label, count in current_counts.items()
            if label not in level_index
        }
        categories: list[dict[str, object]] = []
        max_delta = 0.0
        for level in stats.levels:
            reference_share = float(stats.proportions[level_index[level]]) * 100.0
            current_share = current_counts.get(level, 0) / total * 100.0
            delta = current_share - reference_share
            max_delta = max(max_delta, abs(delta))
            categories.append(
                {
                    "column": name,
                    "category": level,
                    "reference_share_pct": reference_share,
                    "current_share_pct": current_share,
                    "delta_pp": delta,
                    "other": False,
                    "severity": _severity_for(
                        abs(delta),
                        policy.category_delta_warning,
                        policy.category_delta_error,
                    ),
                }
            )

        # The reference profile keeps only the most common levels and folds the
        # rest into ``other``. Aggregate every current label outside the retained
        # levels into that same bucket so a rare reference level that reappears is
        # measured against its real reference share instead of being called new.
        current_other = sum(outside.values())
        reference_other = stats.other_proportion * 100.0
        if reference_other > 0.0 or current_other > 0:
            current_other_share = current_other / total * 100.0
            other_delta = current_other_share - reference_other
            max_delta = max(max_delta, abs(other_delta))
            categories.append(
                {
                    "column": name,
                    "category": _OTHER_LABEL,
                    "reference_share_pct": reference_other,
                    "current_share_pct": current_other_share,
                    "delta_pp": other_delta,
                    "other": True,
                    "severity": _severity_for(
                        abs(other_delta),
                        policy.category_delta_warning,
                        policy.category_delta_error,
                    ),
                }
            )

        psi_severity = _severity_for(psi, policy.psi_warning, policy.psi_error)
        missing_severity = _severity_for(
            abs(missing_pct - stats.missing_pct),
            policy.missing_delta_warning,
            policy.missing_delta_error,
        )
        category_severity = _severity_for(
            max_delta,
            policy.category_delta_warning,
            policy.category_delta_error,
        )
        severity = _worst(psi_severity, missing_severity, category_severity)
        severity = _downgrade(severity, self.rows, total, policy)
        reasons: list[str] = []
        if psi_severity:
            reasons.append(f"PSI {psi:.3f}")
        if missing_severity:
            reasons.append(f"missingness {missing_pct - stats.missing_pct:+.1f} pp")
        if category_severity:
            reasons.append(f"max category delta {max_delta:.1f} pp")
        message = (
            "distribution is stable"
            if severity is None
            else ", ".join(reasons) + " exceeds the configured threshold"
        )
        row = self._row(
            name,
            stats,
            total,
            severity=severity,
            message=message,
            psi=psi,
            missing_current_pct=missing_pct,
            max_category_delta_pp=max_delta,
            other=len(outside),
        )
        return row, categories


def _downgrade(
    severity: Severity | None,
    reference_rows: int,
    current_rows: int,
    policy: DriftPolicy,
) -> Severity | None:
    if severity != "error" or policy.min_sample <= 0:
        return severity
    if reference_rows < policy.min_sample or current_rows < policy.min_sample:
        return "warning"
    return severity


def _psi(reference: np.ndarray, current: np.ndarray) -> float:
    reference = np.clip(reference, _EPSILON, None)
    current = np.clip(current, _EPSILON, None)
    return float(np.sum((current - reference) * np.log(current / reference)))


@dataclass(eq=False)
class DistributionDriftReport:
    """Reference-versus-current statistical drift for a set of columns.

    ``columns`` holds one row per compared column with PSI, Wasserstein distance,
    its scale-free ratio, missingness deltas, and the largest category delta.
    ``categories`` holds the bounded per-category detail for categorical columns.
    """

    columns: pd.DataFrame
    categories: pd.DataFrame
    reference_rows: int
    current_rows: int
    policy: DriftPolicy
    reference: DriftProfile | None = None

    @property
    def has_drift(self) -> bool:
        """Whether any column left the stable band."""
        return self.drifted_columns != ()

    @property
    def drifted_columns(self) -> tuple[str, ...]:
        """Names of columns whose status is not ``stable``."""
        if self.columns.empty:
            return ()
        drifted = self.columns[self.columns["status"] != _STABLE]
        return tuple(str(value) for value in drifted["column"])

    @property
    def errors(self) -> pd.DataFrame:
        """Column-level findings with error severity."""
        if self.columns.empty:
            return self.columns
        return self.columns[self.columns["severity"] == "error"]

    @property
    def warnings(self) -> pd.DataFrame:
        """Column-level findings with warning severity."""
        if self.columns.empty:
            return self.columns
        return self.columns[self.columns["severity"] == "warning"]

    @property
    def has_errors(self) -> bool:
        """Whether at least one column has an error-severity finding."""
        return not self.errors.empty

    @property
    def has_warnings(self) -> bool:
        """Whether at least one column has a warning-severity finding."""
        return not self.warnings.empty

    def summary(self) -> str:
        """Return a short human-readable description of the drift."""
        if self.columns.empty:
            return "no columns were compared"
        if not self.has_drift:
            return (
                f"no distribution drift across {len(self.columns)} column(s) "
                f"({self.reference_rows} reference rows, {self.current_rows} current rows)"
            )
        lines = [f"{len(self.drifted_columns)} drifted column(s)"]
        for _, row in self.columns[self.columns["status"] != _STABLE].iterrows():
            lines.append(f"- [{row['severity']}] {row['column']}: {row['message']}")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render the comparison as Markdown."""
        status = "DRIFT" if self.has_drift else "STABLE"
        lines = [
            f"**{status}** — {len(self.drifted_columns)} drifted column(s), "
            f"{self.reference_rows} reference rows, {self.current_rows} current rows"
        ]
        if not self.columns.empty:
            lines.extend(["", _markdown_table(self.columns)])
        if not self.categories.empty and self.has_drift:
            lines.extend(
                ["", "### Category deltas", "", _markdown_table(self.categories)]
            )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation of the report."""
        return {
            "reference_rows": self.reference_rows,
            "current_rows": self.current_rows,
            "has_drift": self.has_drift,
            "has_errors": self.has_errors,
            "policy": self.policy.to_dict(),
            "columns": json_records(self.columns),
            "categories": json_records(self.categories),
            "reference": None if self.reference is None else self.reference.to_dict(),
        }

    def to_json(self, **kwargs: object) -> str:
        """Serialize the report to JSON."""
        return json.dumps(self.to_dict(), **kwargs)  # type: ignore[arg-type]

    def raise_if_drift(self, message: str = "Statistical drift detected") -> None:
        """Raise ``ValueError`` when an error-severity finding exists."""
        if self.has_errors:
            raise ValueError(f"{message}:\n{self.summary()}")


def _markdown_table(frame: pd.DataFrame) -> str:
    try:
        return frame.to_markdown(index=False)
    except ImportError:  # tabulate is optional
        return "```\n" + frame.to_string(index=False) + "\n```"


def compare_distributions(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    columns: list[str] | tuple[str, ...] | None = None,
    policy: DriftPolicy | None = None,
) -> DistributionDriftReport:
    """Compare the distributions of ``reference`` and ``current``.

    This is a convenience wrapper around
    :meth:`DriftProfile.from_frame` and :meth:`DriftProfile.compare`. Use the
    profile directly when the same reference is compared with many batches.
    """
    profile = DriftProfile.from_frame(reference, columns=columns, policy=policy)
    return profile.compare(current, policy=policy)
