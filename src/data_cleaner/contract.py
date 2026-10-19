"""Column specifications, data contracts, and drift reports."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import pandas as pd

from ._roles import (
    _DRIFT_COLUMNS,
    _ROLE_TO_KIND,
    _normalize_kind,
    _normalize_role,
    _series_kind,
)

if TYPE_CHECKING:
    from .config import CleanerConfig


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """Declarative expectations and semantics for a single column.

    ``role`` tells the cleaner how the column should be treated
    (``numeric``, ``category``, ``boolean``, ``datetime``, ``id``, ``text``,
    ``ignore``). The remaining fields describe optional contract checks.
    """

    name: str
    role: str | None = None
    dtype: str | None = None
    nullable: bool = True
    unique: bool = False
    allowed_values: tuple[object, ...] | None = None
    min_value: float | None = None
    max_value: float | None = None
    pattern: str | None = None
    date_format: str | None = None
    preserve_leading_zeros: bool = False
    severity: Literal["error", "warning"] = "error"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("ColumnSpec.name must be a non-empty string")
        object.__setattr__(self, "role", _normalize_role(self.role))
        object.__setattr__(self, "dtype", _normalize_kind(self.dtype))
        if self.allowed_values is not None:
            object.__setattr__(self, "allowed_values", tuple(self.allowed_values))
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError(
                f"min_value is greater than max_value for column '{self.name}'"
            )
        if self.pattern is not None:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(
                    f"Invalid pattern for column '{self.name}': {exc}"
                ) from exc
        if self.severity not in {"error", "warning"}:
            raise ValueError("severity must be 'error' or 'warning'")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the spec."""
        return {
            "name": self.name,
            "role": self.role,
            "dtype": self.dtype,
            "nullable": self.nullable,
            "unique": self.unique,
            "allowed_values": (
                list(self.allowed_values) if self.allowed_values is not None else None
            ),
            "min_value": self.min_value,
            "max_value": self.max_value,
            "pattern": self.pattern,
            "date_format": self.date_format,
            "preserve_leading_zeros": self.preserve_leading_zeros,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> ColumnSpec:
        """Rebuild a spec from :meth:`to_dict` output."""
        return cls(**data)  # type: ignore[arg-type]


@dataclass(eq=False)
class DriftReport:
    """Container for column-contract findings produced during ``transform``."""

    findings: pd.DataFrame

    @classmethod
    def empty(cls) -> DriftReport:
        return cls(pd.DataFrame(columns=_DRIFT_COLUMNS))

    @property
    def has_drift(self) -> bool:
        return not self.findings.empty

    @property
    def errors(self) -> pd.DataFrame:
        if not self.has_drift:
            return self.findings
        return self.findings[self.findings["severity"] == "error"]

    @property
    def warnings(self) -> pd.DataFrame:
        if not self.has_drift:
            return self.findings
        return self.findings[self.findings["severity"] == "warning"]

    @property
    def has_errors(self) -> bool:
        return not self.errors.empty

    @property
    def has_warnings(self) -> bool:
        return not self.warnings.empty

    def summary(self) -> str:
        """Return a short human-readable description of the findings."""
        if not self.has_drift:
            return "no drift detected"
        lines = [
            f"- [{row['severity']}] {row['column']}: {row['message']}"
            for _, row in self.findings.iterrows()
        ]
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render findings as a Markdown table (falls back to plain text)."""
        if not self.has_drift:
            return "No drift detected."
        try:
            return self.findings.to_markdown(index=False)
        except ImportError:  # tabulate is optional
            return self.findings.to_string(index=False)

    def raise_if_errors(self, message: str = "Schema drift detected") -> None:
        """Raise ``ValueError`` when at least one error-severity finding exists."""
        if self.has_errors:
            raise ValueError(f"{message}:\n{self.summary()}")


@dataclass(frozen=True, slots=True)
class DataContract:
    """A set of :class:`ColumnSpec` objects describing expected input columns.

    ``strict=True`` also reports columns present in the frame but not declared
    in the contract.
    """

    columns: tuple[ColumnSpec, ...] = ()
    strict: bool = False

    def __post_init__(self) -> None:
        coerced: list[ColumnSpec] = []
        for item in self.columns:
            if isinstance(item, ColumnSpec):
                coerced.append(item)
            else:
                raise TypeError(
                    "DataContract.columns must contain ColumnSpec instances"
                )
        names = [spec.name for spec in coerced]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"Duplicate column specs in contract: {duplicates}")
        object.__setattr__(self, "columns", tuple(coerced))

    def spec_for(self, name: str) -> ColumnSpec | None:
        """Return the spec for ``name``, or ``None`` when it is not declared."""
        for spec in self.columns:
            if spec.name == name:
                return spec
        return None

    @classmethod
    def infer_from(
        cls,
        frame: pd.DataFrame,
        config: CleanerConfig | None = None,
        strict: bool = True,
    ) -> DataContract:
        """Infer a conservative contract from a training frame."""
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("frame must be a pandas DataFrame")
        specs: list[ColumnSpec] = []
        for column in frame.columns:
            role: str | None = None
            if config is not None:
                if column in config.numeric_columns:
                    role = "numeric"
                elif column in config.categorical_columns:
                    role = "category"
                elif column in config.datetime_columns:
                    role = "datetime"
            series = frame[column]
            kind = _ROLE_TO_KIND.get(role) if role else _series_kind(series)
            specs.append(
                ColumnSpec(
                    name=column,
                    role=role,
                    dtype=kind,
                    nullable=bool(series.isna().any()),
                )
            )
        return cls(columns=tuple(specs), strict=strict)

    @staticmethod
    def _finding(
        spec: ColumnSpec,
        check: str,
        expected: object,
        actual: object,
        message: str,
    ) -> dict[str, object]:
        return {
            "column": spec.name,
            "check": check,
            "severity": spec.severity,
            "expected": expected,
            "actual": actual,
            "message": message,
        }

    def check(self, frame: pd.DataFrame) -> DriftReport:
        """Compare ``frame`` against the contract and collect every difference."""
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("frame must be a pandas DataFrame")
        findings: list[dict[str, object]] = []
        declared = {spec.name for spec in self.columns}

        for spec in self.columns:
            if spec.role == "ignore":
                continue
            if spec.name not in frame.columns:
                findings.append(
                    self._finding(
                        spec,
                        "missing_column",
                        "column present",
                        "column missing",
                        f"expected column '{spec.name}' is missing",
                    )
                )
                continue

            series = frame[spec.name]
            actual_kind = _series_kind(series)
            expected_kind = (
                _ROLE_TO_KIND.get(spec.role)
                if spec.role
                else _normalize_kind(spec.dtype)
            )
            if expected_kind and actual_kind != expected_kind:
                # Identifier and text columns legitimately arrive as either
                # numeric-looking or object dtype, so that is not drift.
                tolerated = spec.role in {"id", "text"} and actual_kind in {
                    "numeric",
                    "categorical",
                }
                if not tolerated:
                    findings.append(
                        self._finding(
                            spec,
                            "dtype_change",
                            expected_kind,
                            actual_kind,
                            f"'{spec.name}' changed kind from "
                            f"{expected_kind} to {actual_kind}",
                        )
                    )

            missing_count = int(series.isna().sum())
            if not spec.nullable and missing_count:
                findings.append(
                    self._finding(
                        spec,
                        "unexpected_missing",
                        "no missing values",
                        f"{missing_count} missing",
                        f"'{spec.name}' has {missing_count} missing value(s) "
                        "but the contract marks it non-nullable",
                    )
                )

            if spec.allowed_values is not None:
                mask = series.notna() & ~series.isin(list(spec.allowed_values))
                if bool(mask.any()):
                    unseen = [str(value) for value in pd.unique(series[mask])[:10]]
                    findings.append(
                        self._finding(
                            spec,
                            "unexpected_category",
                            list(spec.allowed_values),
                            unseen,
                            f"'{spec.name}' contains values outside allowed_values",
                        )
                    )

            if spec.min_value is not None or spec.max_value is not None:
                numeric = pd.to_numeric(series, errors="coerce").dropna()
                if not numeric.empty:
                    violations = pd.Series(False, index=numeric.index)
                    if spec.min_value is not None:
                        violations |= numeric < spec.min_value
                    if spec.max_value is not None:
                        violations |= numeric > spec.max_value
                    count = int(violations.sum())
                    if count:
                        findings.append(
                            self._finding(
                                spec,
                                "value_out_of_range",
                                f"min={spec.min_value} max={spec.max_value}",
                                f"{count} value(s) outside",
                                f"'{spec.name}' has {count} value(s) outside "
                                "the declared range",
                            )
                        )

            if spec.pattern is not None:
                non_null = series.dropna()
                if not non_null.empty:
                    matches = non_null.astype(str).str.fullmatch(spec.pattern)
                    count = int((~matches.fillna(False)).sum())
                    if count:
                        findings.append(
                            self._finding(
                                spec,
                                "pattern_mismatch",
                                f"pattern={spec.pattern!r}",
                                f"{count} value(s) mismatch",
                                f"'{spec.name}' has {count} value(s) that do "
                                "not match the declared pattern",
                            )
                        )

            if spec.unique:
                duplicates = int(series.duplicated().sum())
                if duplicates:
                    findings.append(
                        self._finding(
                            spec,
                            "duplicate_values",
                            "unique values",
                            f"{duplicates} duplicate(s)",
                            f"'{spec.name}' is expected to be unique",
                        )
                    )

        if self.strict:
            for column in frame.columns:
                if column not in declared:
                    findings.append(
                        {
                            "column": column,
                            "check": "unexpected_column",
                            "severity": "warning",
                            "expected": "column declared in contract",
                            "actual": "column present",
                            "message": f"unexpected column '{column}' is not "
                            "part of the contract",
                        }
                    )

        return DriftReport(pd.DataFrame(findings, columns=_DRIFT_COLUMNS))

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the contract."""
        return {
            "strict": self.strict,
            "columns": [spec.to_dict() for spec in self.columns],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DataContract:
        """Rebuild a contract from :meth:`to_dict` output."""
        raw = data.get("columns") or ()
        if not isinstance(raw, (list, tuple)):
            raise TypeError("contract 'columns' must be a list or tuple")
        columns = tuple(
            ColumnSpec.from_dict(item) if isinstance(item, dict) else item
            for item in raw
        )
        return cls(columns=columns, strict=bool(data.get("strict", False)))

    def to_json(self, **kwargs: object) -> str:
        """Serialize the contract to JSON."""
        return json.dumps(self.to_dict(), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, text: str) -> DataContract:
        """Parse a contract from JSON."""
        return cls.from_dict(json.loads(text))

    def to_yaml(self) -> str:
        """Serialize to YAML (requires the optional ``pyyaml`` package)."""
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "PyYAML is required for YAML contracts. Install it with "
                "`pip install pyyaml` or use to_json()/from_json()."
            ) from exc
        return yaml.safe_dump(self.to_dict(), sort_keys=False)

    @classmethod
    def from_yaml(cls, text: str) -> DataContract:
        """Parse YAML (requires the optional ``pyyaml`` package)."""
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "PyYAML is required for YAML contracts. Install it with "
                "`pip install pyyaml` or use to_json()/from_json()."
            ) from exc
        return cls.from_dict(yaml.safe_load(text))
