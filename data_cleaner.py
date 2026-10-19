"""Universal Data Cleaner — production-oriented tabular cleaning transformer.

The module is intentionally small and dependency-light:

- pandas + numpy for data handling
- scikit-learn base classes for Pipeline / clone compatibility
- joblib for artifact persistence
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import joblib
import numpy as np
import pandas as pd
from pandas.api import types as ptypes
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted

LOGGER = logging.getLogger(__name__)

__version__ = "2.1.0"
_ARTIFACT_VERSION = 1

__all__ = [
    "CleanerConfig",
    "ColumnSpec",
    "DataCleaner",
    "DataContract",
    "DriftReport",
    "assert_frame_clean",
    "dataset_summary",
    "drop_duplicate_rows",
    "profile_dataframe",
]

_ALLOWED_DATETIME_FEATURES = {
    "year",
    "month",
    "day",
    "dayofweek",
    "quarter",
    "dayofyear",
    "weekofyear",
    "is_weekend",
    "hour",
    "minute",
}

_ROLE_ALIASES = {
    "numeric": "numeric",
    "measure": "numeric",
    "number": "numeric",
    "float": "numeric",
    "int": "numeric",
    "integer": "numeric",
    "category": "category",
    "categorical": "category",
    "object": "category",
    "string": "category",
    "str": "category",
    "boolean": "boolean",
    "bool": "boolean",
    "datetime": "datetime",
    "date": "datetime",
    "timestamp": "datetime",
    "id": "id",
    "identifier": "id",
    "text": "text",
    "ignore": "ignore",
    "drop": "ignore",
}

_ROLE_TO_KIND = {
    "numeric": "numeric",
    "category": "categorical",
    "boolean": "boolean",
    "datetime": "datetime",
    "id": "categorical",
    "text": "categorical",
    "ignore": None,
}

_DRIFT_COLUMNS = ["column", "check", "severity", "expected", "actual", "message"]

_ID_STRING_KINDS = (int, np.integer)


def _normalize_role(value: object) -> str | None:
    """Map role aliases to a canonical role name."""
    if value is None:
        return None
    key = str(value).strip().lower()
    if key not in _ROLE_ALIASES:
        valid = sorted(set(_ROLE_ALIASES.values()))
        raise ValueError(f"Unsupported column role '{value}'. Valid roles: {valid}")
    return _ROLE_ALIASES[key]


def _normalize_kind(value: object) -> str | None:
    """Map dtype strings to a broad kind: numeric/categorical/boolean/datetime."""
    if value is None:
        return None
    key = str(value).strip().lower()
    mapping = {
        "numeric": "numeric",
        "number": "numeric",
        "int": "numeric",
        "integer": "numeric",
        "float": "numeric",
        "double": "numeric",
        "int64": "numeric",
        "int32": "numeric",
        "int16": "numeric",
        "int8": "numeric",
        "float64": "numeric",
        "float32": "numeric",
        "boolean": "boolean",
        "bool": "boolean",
        "datetime": "datetime",
        "datetime64": "datetime",
        "datetime64[ns]": "datetime",
        "date": "datetime",
        "timestamp": "datetime",
        "categorical": "categorical",
        "category": "categorical",
        "object": "categorical",
        "string": "categorical",
        "str": "categorical",
        "text": "categorical",
        "id": "categorical",
    }
    return mapping.get(key, key)


def _series_kind(series: pd.Series) -> str:
    """Return the broad semantic kind of a pandas Series."""
    if ptypes.is_bool_dtype(series):
        return "boolean"
    if ptypes.is_datetime64_any_dtype(series):
        return "datetime"
    if ptypes.is_numeric_dtype(series):
        return "numeric"
    return "categorical"


def _stringify_identifier(value: object) -> object:
    """Render an identifier without a trailing ``.0`` while preserving NaN."""
    if value is None:
        return value
    try:
        if pd.isna(value):
            return value
    except (TypeError, ValueError):
        pass
    if isinstance(value, _ID_STRING_KINDS):
        return str(int(value))
    if isinstance(value, (float, np.floating)) and float(value).is_integer():
        return str(int(value))
    return str(value)


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
                list(self.allowed_values)
                if self.allowed_values is not None
                else None
            ),
            "min_value": self.min_value,
            "max_value": self.max_value,
            "pattern": self.pattern,
            "date_format": self.date_format,
            "preserve_leading_zeros": self.preserve_leading_zeros,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ColumnSpec":
        """Rebuild a spec from :meth:`to_dict` output."""
        return cls(**data)  # type: ignore[arg-type]


@dataclass(eq=False)
class DriftReport:
    """Container for column-contract findings produced during ``transform``."""

    findings: pd.DataFrame

    @classmethod
    def empty(cls) -> "DriftReport":
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
class CleanerConfig:
    """Configuration for :class:`DataCleaner`."""

    numeric_imputation: Literal["median", "mean", "constant"] = "median"
    categorical_imputation: Literal["mode", "constant"] = "mode"
    numeric_fill_value: float = 0.0
    categorical_fill_value: str = "Unknown"
    cap_outliers: bool = True
    outlier_multiplier: float = 1.5
    add_missing_indicators: bool = False
    drop_constant_columns: bool = True
    numeric_columns: tuple[str, ...] = ()
    categorical_columns: tuple[str, ...] = ()
    datetime_columns: tuple[str, ...] = ()
    datetime_features: tuple[str, ...] = (
        "year",
        "month",
        "day",
        "dayofweek",
        "is_weekend",
    )
    unseen_category: Literal["keep", "fill"] = "keep"
    contract: "DataContract | None" = None
    on_drift: Literal["raise", "warn", "ignore"] = "warn"
    infer_contract: bool = True
    verbose: bool = True

    def __post_init__(self) -> None:
        for name in (
            "numeric_columns",
            "categorical_columns",
            "datetime_columns",
            "datetime_features",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))

        if self.numeric_imputation not in {"median", "mean", "constant"}:
            raise ValueError(
                "numeric_imputation must be one of: median, mean, constant"
            )
        if self.categorical_imputation not in {"mode", "constant"}:
            raise ValueError(
                "categorical_imputation must be one of: mode, constant"
            )
        if self.outlier_multiplier <= 0:
            raise ValueError("outlier_multiplier must be > 0")
        if self.unseen_category not in {"keep", "fill"}:
            raise ValueError("unseen_category must be one of: keep, fill")
        if self.on_drift not in {"raise", "warn", "ignore"}:
            raise ValueError("on_drift must be one of: raise, warn, ignore")
        if self.contract is not None and not isinstance(self.contract, DataContract):
            raise TypeError(
                "contract must be a DataContract instance or None"
            )
        if not self.datetime_features:
            raise ValueError("datetime_features cannot be empty")
        if len(set(self.datetime_features)) != len(self.datetime_features):
            raise ValueError("datetime_features must be unique")
        unknown_features = set(self.datetime_features) - _ALLOWED_DATETIME_FEATURES
        if unknown_features:
            raise ValueError(
                f"Unsupported datetime features: {sorted(unknown_features)}"
            )

        configured_sets = {
            "numeric_columns": set(self.numeric_columns),
            "categorical_columns": set(self.categorical_columns),
            "datetime_columns": set(self.datetime_columns),
        }
        for left_name, left in configured_sets.items():
            for right_name, right in configured_sets.items():
                if left_name < right_name and left & right:
                    raise ValueError(
                        f"{left_name} and {right_name} overlap: {sorted(left & right)}"
                    )


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
            elif isinstance(item, dict):
                coerced.append(ColumnSpec.from_dict(item))
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
        config: "CleanerConfig | None" = None,
        strict: bool = True,
    ) -> "DataContract":
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
    def from_dict(cls, data: dict[str, object]) -> "DataContract":
        """Rebuild a contract from :meth:`to_dict` output."""
        raw = data.get("columns", ())
        columns = tuple(
            ColumnSpec.from_dict(item) if isinstance(item, dict) else item
            for item in raw  # type: ignore[union-attr]
        )
        return cls(columns=columns, strict=bool(data.get("strict", False)))

    def to_json(self, **kwargs: object) -> str:
        """Serialize the contract to JSON."""
        return json.dumps(self.to_dict(), **kwargs)  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, text: str) -> "DataContract":
        """Parse a contract from JSON."""
        return cls.from_dict(json.loads(text))

    def to_yaml(self) -> str:
        """Serialize to YAML (requires the optional ``pyyaml`` package)."""
        try:
            import yaml  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "PyYAML is required for YAML contracts. Install it with "
                "`pip install pyyaml` or use to_json()/from_json()."
            ) from exc
        return yaml.safe_dump(self.to_dict(), sort_keys=False)  # type: ignore[no-any-return]

    @classmethod
    def from_yaml(cls, text: str) -> "DataContract":
        """Parse YAML (requires the optional ``pyyaml`` package)."""
        try:
            import yaml  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "PyYAML is required for YAML contracts. Install it with "
                "`pip install pyyaml` or use to_json()/from_json()."
            ) from exc
        return cls.from_dict(yaml.safe_load(text))


class DataCleaner(TransformerMixin, BaseEstimator):
    """Fit/transform data cleaner that prevents train/test leakage.

    The cleaner learns imputers, outlier bounds, category policies and schema
    information on training data, then applies exactly those learned rules to
    validation, test, or inference batches.
    """

    def __init__(self, config: CleanerConfig | None = None) -> None:
        self.config = config if config is not None else CleanerConfig()

    def fit(self, X: pd.DataFrame, y: object | None = None) -> "DataCleaner":
        """Learn cleaning rules from training data."""
        frame = self._validate_frame(X, required=None, allow_empty=False)
        self.contract_ = self._resolve_contract(frame)
        frame = self._drop_ignored_columns(frame)
        roles = self._infer_roles(frame)
        self.id_columns_ = [
            column for column in frame.columns if self._role_for(column) == "id"
        ]
        self.text_columns_ = [
            column for column in frame.columns if self._role_for(column) == "text"
        ]
        prepared, missing_flags, generated = self._prepare_frame(frame, roles)

        self.feature_names_in_ = np.asarray(list(frame.columns), dtype=object)
        self.n_features_in_ = len(frame.columns)
        self.roles_ = roles
        self.drift_report_ = DriftReport.empty().findings
        self.datetime_feature_columns_ = generated
        self.missing_counts_ = {
            column: int(flags.sum()) for column, flags in missing_flags.items()
        }

        self.numeric_columns_ = [
            column
            for column, role in roles.items()
            if role == "numeric" and column in prepared.columns
        ] + [column for columns in generated.values() for column in columns]
        self.calendar_columns_ = [
            column for columns in generated.values() for column in columns
        ]
        self.boolean_columns_ = [
            column for column, role in roles.items() if role == "boolean"
        ]
        self.categorical_columns_ = [
            column for column, role in roles.items() if role == "categorical"
        ]

        self.fill_values_: dict[str, object] = {}
        self.outlier_bounds_: dict[str, tuple[float, float]] = {}
        self.outlier_counts_: dict[str, int] = {}
        self.outlier_quartiles_: dict[str, tuple[float, float]] = {}
        self.known_categories_: dict[str, frozenset | None] = {}

        self._fit_numeric(prepared, roles)
        self._fit_boolean(prepared)
        self._fit_categorical(prepared)

        self.indicator_columns_: dict[str, str] = {}
        if self.config.add_missing_indicators:
            used = set(prepared.columns)
            for source, flags in missing_flags.items():
                if not bool(flags.any()):
                    continue
                base = f"{source}__is_missing"
                name = base
                suffix = 2
                while name in used:
                    name = f"{base}_{suffix}"
                    suffix += 1
                prepared[name] = flags.astype(bool)
                used.add(name)
                self.indicator_columns_[source] = name

        self.constant_columns_ = [
            column
            for column in prepared.columns
            if prepared[column].nunique(dropna=False) <= 1
        ]
        dropped = (
            set(self.constant_columns_) if self.config.drop_constant_columns else set()
        )
        output_order: list[str] = []
        for source in frame.columns:
            if roles[source] == "datetime":
                output_order.extend(generated[source])
            else:
                output_order.append(source)
        output_order.extend(self.indicator_columns_.values())
        self.columns_ = [
            column
            for column in output_order
            if column in prepared.columns and column not in dropped
        ]
        self.dropped_columns_ = sorted(
            set(frame.columns).difference(self.columns_).intersection(roles)
        )

        self._build_summary()
        self.n_samples_fit_ = len(frame)
        self.fitted_at_ = datetime.now(timezone.utc).isoformat()
        if self.config.verbose:
            LOGGER.info(
                "DataCleaner fitted on %d rows, %d input columns, %d output columns",
                len(frame),
                len(self.feature_names_in_),
                len(self.columns_),
            )
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Apply learned cleaning rules without fitting anything."""
        self._ensure_fitted()
        frame = self._validate_frame(X, required=None, allow_empty=True)
        report = self._contract_report(frame)
        self.drift_report_ = report.findings
        missing = [
            column for column in self.feature_names_in_ if column not in frame.columns
        ]
        if missing:
            raise ValueError(
                "DataFrame is missing required columns: "
                f"{missing}. Fit the cleaner on the training schema first."
                f"\nDrift details:\n{report.summary()}"
            )
        self._handle_drift(report)
        expected = list(self.feature_names_in_)
        extra = [column for column in frame.columns if column not in expected]
        if extra:
            LOGGER.warning(
                "Ignoring %d unexpected column(s) at transform time: %s",
                len(extra),
                extra,
            )
        frame = frame.loc[:, expected]
        prepared, missing_flags, _ = self._prepare_frame(frame, self.roles_)

        for column in self.numeric_columns_:
            series = prepared[column].astype("float64")
            fill = self.fill_values_[column]
            lower, upper = self.outlier_bounds_[column]
            prepared[column] = (
                series.fillna(fill).clip(lower=lower, upper=upper).astype("float64")
            )

        for column in self.boolean_columns_:
            series = prepared[column].astype("boolean")
            prepared[column] = (
                series.fillna(self.fill_values_[column]).astype(bool)
            )

        for column in self.categorical_columns_:
            series = prepared[column].astype(object)
            fill = self.fill_values_[column]
            protected = column in self.id_columns_ or column in self.text_columns_
            if self.config.unseen_category == "fill" and not protected:
                known = self.known_categories_.get(column)
                if known is not None:
                    unseen = series.notna() & ~series.isin(known)
                    series = series.mask(unseen, self.config.categorical_fill_value)
            prepared[column] = series.fillna(fill).astype(object)

        for source, indicator in self.indicator_columns_.items():
            prepared[indicator] = missing_flags[source].astype(bool)

        if self.config.drop_constant_columns and self.constant_columns_:
            prepared = prepared.drop(
                columns=[c for c in self.constant_columns_ if c in prepared.columns]
            )

        missing_output = [c for c in self.columns_ if c not in prepared.columns]
        if missing_output:
            raise RuntimeError(
                f"Internal error: expected cleaned columns missing: {missing_output}"
            )
        return prepared.reindex(columns=self.columns_)

    def fit_transform(
        self, X: pd.DataFrame, y: object | None = None
    ) -> pd.DataFrame:
        """Fit on ``X`` and return the cleaned training DataFrame."""
        return self.fit(X, y).transform(X)

    def get_feature_names_out(
        self, input_features: list[str] | None = None
    ) -> np.ndarray:
        """Return cleaned output column names."""
        self._ensure_fitted()
        if input_features is not None and list(input_features) != list(
            self.feature_names_in_
        ):
            raise ValueError(
                "input_features must match the columns seen during fit"
            )
        return np.asarray(self.columns_, dtype=object)

    def cleaning_summary(self) -> pd.DataFrame:
        """Return a learned cleaning summary for auditing/debugging."""
        self._ensure_fitted()
        return self.cleaning_summary_.copy()

    def outlier_summary(self) -> pd.DataFrame:
        """Return outlier bounds learned for numeric columns."""
        self._ensure_fitted()
        rows = []
        for column in self.numeric_columns_:
            lower, upper = self.outlier_bounds_[column]
            q1, q3 = self.outlier_quartiles_.get(column, (np.nan, np.nan))
            rows.append(
                {
                    "column": column,
                    "q1": q1,
                    "q3": q3,
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "outliers_capped": self.outlier_counts_.get(column, 0),
                    "method": "iqr"
                    if np.isfinite(lower) or np.isfinite(upper)
                    else "disabled",
                }
            )
        return pd.DataFrame(rows)

    def drift_report(self) -> pd.DataFrame:
        """Return the column-contract drift findings seen at the last ``transform``."""
        self._ensure_fitted()
        return self.drift_report_.copy()

    def fitted_contract(self) -> "DataContract | None":
        """Return the contract used by this fitted cleaner."""
        self._ensure_fitted()
        return self.contract_

    def _resolve_contract(self, frame: pd.DataFrame) -> "DataContract | None":
        if self.config.contract is not None:
            return self.config.contract
        if not self.config.infer_contract:
            return None
        return DataContract.infer_from(frame, config=self.config)

    def _drop_ignored_columns(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.contract_ is None:
            return frame
        ignored = [
            column
            for column in frame.columns
            if (
                (spec := self.contract_.spec_for(column)) is not None
                and spec.role == "ignore"
            )
        ]
        return frame.drop(columns=ignored) if ignored else frame

    def _role_for(self, column: str) -> str | None:
        if self.contract_ is None:
            return None
        spec = self.contract_.spec_for(column)
        return spec.role if spec is not None else None

    def _contract_report(self, frame: pd.DataFrame) -> DriftReport:
        if self.contract_ is None:
            return DriftReport.empty()
        return self.contract_.check(frame)

    def _handle_drift(self, report: DriftReport) -> None:
        if not report.has_drift:
            return
        if self.config.on_drift == "raise" and report.has_errors:
            raise ValueError(f"Schema drift detected:\n{report.summary()}")
        if self.config.on_drift in {"raise", "warn"}:
            LOGGER.warning("Schema drift detected:\n%s", report.summary())

    def save(self, path: str | Path) -> Path:
        """Persist the fitted cleaner as a joblib artifact."""
        self._ensure_fitted()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "artifact_version": _ARTIFACT_VERSION,
            "library_version": __version__,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "cleaner": self,
        }
        joblib.dump(payload, target, compress=3)
        return target

    @classmethod
    def load(cls, path: str | Path, verify_version: bool = True) -> "DataCleaner":
        """Load a saved cleaner artifact."""
        payload = joblib.load(Path(path))
        if not isinstance(payload, dict) or "cleaner" not in payload:
            raise ValueError("File is not a valid DataCleaner artifact")
        cleaner = payload["cleaner"]
        if not isinstance(cleaner, cls):
            raise TypeError("Artifact does not contain a DataCleaner")
        artifact_version = payload.get("artifact_version")
        library_version = payload.get("library_version")
        if verify_version and library_version != __version__:
            LOGGER.warning(
                "Artifact was created with library version %s, current version is %s",
                library_version,
                __version__,
            )
        if artifact_version != _ARTIFACT_VERSION:
            LOGGER.warning(
                "Artifact version %s is not the current version %s",
                artifact_version,
                _ARTIFACT_VERSION,
            )
        return cleaner

    def _ensure_fitted(self) -> None:
        check_is_fitted(self, attributes=["columns_"])

    def _validate_frame(
        self,
        frame: pd.DataFrame,
        *,
        required: list[str] | None,
        allow_empty: bool,
    ) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("X must be a pandas DataFrame")
        if frame.columns.has_duplicates:
            duplicates = frame.columns[frame.columns.duplicated()].tolist()
            raise ValueError(f"Duplicate column names are not allowed: {duplicates}")
        if required:
            missing = [column for column in required if column not in frame.columns]
            if missing:
                raise ValueError(
                    "DataFrame is missing required columns: "
                    f"{missing}. Fit the cleaner on the training schema first."
                )
        if not allow_empty and frame.empty:
            raise ValueError("Cannot fit DataCleaner on an empty DataFrame")
        return frame.copy(deep=True)

    def _infer_roles(self, frame: pd.DataFrame) -> dict[str, str]:
        cfg = self.config
        configured = (
            list(cfg.numeric_columns)
            + list(cfg.categorical_columns)
            + list(cfg.datetime_columns)
        )
        missing = [column for column in configured if column not in frame.columns]
        if missing:
            raise ValueError(
                f"Configured columns not found in DataFrame: {missing}"
            )

        roles: dict[str, str] = {}
        for column in frame.columns:
            hint = self._role_for(column)
            if hint == "ignore":
                roles[column] = "ignore"
                continue
            if hint == "numeric":
                roles[column] = "numeric"
                continue
            if hint in {"category", "id", "text"}:
                roles[column] = "categorical"
                continue
            if hint == "boolean":
                roles[column] = "boolean"
                continue
            if hint == "datetime":
                roles[column] = "datetime"
                continue
            if column in cfg.datetime_columns:
                roles[column] = "datetime"
            elif column in cfg.numeric_columns:
                roles[column] = "numeric"
            elif column in cfg.categorical_columns:
                roles[column] = "categorical"
            elif ptypes.is_bool_dtype(frame[column]):
                roles[column] = "boolean"
            elif ptypes.is_datetime64_any_dtype(frame[column]):
                raise ValueError(
                    f"Column '{column}' is datetime-like but is not configured. "
                    "Add it to CleanerConfig.datetime_columns."
                )
            elif ptypes.is_complex_dtype(frame[column]):
                raise TypeError(f"Column '{column}' has unsupported complex dtype")
            elif ptypes.is_numeric_dtype(frame[column]):
                roles[column] = "numeric"
            else:
                roles[column] = "categorical"
        return roles

    def _parse_datetime(self, series: pd.Series) -> pd.Series:
        try:
            return pd.to_datetime(series, errors="coerce", format="mixed")
        except (TypeError, ValueError):
            return pd.to_datetime(series, errors="coerce")

    @staticmethod
    def _coerce_numeric(series: pd.Series) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce").astype("float64")
        return numeric.replace([np.inf, -np.inf], np.nan)

    @staticmethod
    def _as_float(values: object) -> pd.Series:
        return pd.to_numeric(values, errors="coerce").astype("float64")

    def _extract_datetime_features(self, parsed: pd.Series, source: str) -> pd.DataFrame:
        features: dict[str, pd.Series] = {}
        for feature in self.config.datetime_features:
            if feature == "year":
                values = parsed.dt.year
            elif feature == "month":
                values = parsed.dt.month
            elif feature == "day":
                values = parsed.dt.day
            elif feature == "dayofweek":
                values = parsed.dt.dayofweek
            elif feature == "quarter":
                values = parsed.dt.quarter
            elif feature == "dayofyear":
                values = parsed.dt.dayofyear
            elif feature == "weekofyear":
                values = parsed.dt.isocalendar().week
            elif feature == "hour":
                values = parsed.dt.hour
            elif feature == "minute":
                values = parsed.dt.minute
            else:  # is_weekend
                day_of_week = parsed.dt.dayofweek
                values = pd.Series(np.nan, index=parsed.index, dtype="float64")
                valid = day_of_week.notna()
                values.loc[valid] = day_of_week.loc[valid].ge(5).astype(float)
            features[f"{source}__{feature}"] = self._as_float(values)
        return pd.DataFrame(features, index=parsed.index)

    def _prepare_frame(
        self, frame: pd.DataFrame, roles: dict[str, str]
    ) -> tuple[pd.DataFrame, dict[str, pd.Series], dict[str, list[str]]]:
        cfg = self.config
        prepared: dict[str, pd.Series] = {}
        missing_flags: dict[str, pd.Series] = {}
        generated: dict[str, list[str]] = {}

        reserved = set(frame.columns)
        for source in frame.columns:
            if roles[source] != "datetime":
                continue
            names = [f"{source}__{feature}" for feature in cfg.datetime_features]
            collisions = set(names) & reserved
            if collisions:
                raise ValueError(
                    f"Generated datetime feature names collide with existing columns: "
                    f"{sorted(collisions)}"
                )
            reserved.update(names)

        for source in frame.columns:
            role = roles[source]
            series = frame[source]
            if role == "datetime":
                parsed = self._parse_datetime(series)
                missing_flags[source] = parsed.isna()
                features = self._extract_datetime_features(parsed, source)
                generated[source] = list(features.columns)
                for name in features.columns:
                    prepared[name] = features[name]
            elif role == "numeric":
                numeric = self._coerce_numeric(series)
                missing_flags[source] = numeric.isna()
                prepared[source] = numeric
            elif role == "boolean":
                boolean = series.astype("boolean")
                missing_flags[source] = boolean.isna()
                prepared[source] = boolean
            else:
                categorical = series.astype(object)
                if source in self.id_columns_:
                    categorical = categorical.map(_stringify_identifier)
                missing_flags[source] = categorical.isna()
                prepared[source] = categorical

        return pd.DataFrame(prepared, index=frame.index), missing_flags, generated

    def _fit_numeric(
        self, prepared: pd.DataFrame, roles: dict[str, str]
    ) -> None:
        cfg = self.config
        for column in self.numeric_columns_:
            series = prepared[column].astype("float64")
            valid = series.dropna()
            if cfg.numeric_imputation == "median":
                fill = valid.median() if not valid.empty else cfg.numeric_fill_value
            elif cfg.numeric_imputation == "mean":
                fill = valid.mean() if not valid.empty else cfg.numeric_fill_value
            else:
                fill = cfg.numeric_fill_value

            try:
                fill = float(fill)
            except (TypeError, ValueError):
                fill = cfg.numeric_fill_value
            if not np.isfinite(fill):
                fill = cfg.numeric_fill_value

            lower, upper = -np.inf, np.inf
            q1 = q3 = np.nan
            outliers = 0
            should_cap = (
                cfg.cap_outliers
                and roles.get(column) == "numeric"
                and not valid.empty
            )
            if should_cap:
                q1 = float(valid.quantile(0.25))
                q3 = float(valid.quantile(0.75))
                iqr = q3 - q1
                if iqr > 0:
                    lower = q1 - cfg.outlier_multiplier * iqr
                    upper = q3 + cfg.outlier_multiplier * iqr
                    outliers = int(((valid < lower) | (valid > upper)).sum())

            cleaned = series.fillna(fill).clip(lower=lower, upper=upper)
            prepared[column] = cleaned.astype("float64")
            self.fill_values_[column] = fill
            self.outlier_bounds_[column] = (lower, upper)
            self.outlier_counts_[column] = outliers
            self.outlier_quartiles_[column] = (q1, q3)

    def _fit_boolean(self, prepared: pd.DataFrame) -> None:
        for column in self.boolean_columns_:
            series = prepared[column].astype("boolean")
            valid = series.dropna()
            fill = bool(valid.mode().iloc[0]) if not valid.empty else False
            prepared[column] = series.fillna(fill).astype(bool)
            self.fill_values_[column] = fill

    def _fit_categorical(self, prepared: pd.DataFrame) -> None:
        cfg = self.config
        for column in self.categorical_columns_:
            series = prepared[column].astype(object)
            valid = series.dropna()
            protected = column in self.id_columns_ or column in self.text_columns_
            if cfg.categorical_imputation == "mode" and not protected:
                modes = valid.mode(dropna=True)
                fill = modes.iloc[0] if not modes.empty else cfg.categorical_fill_value
            else:
                fill = cfg.categorical_fill_value

            prepared[column] = series.fillna(fill).astype(object)
            self.fill_values_[column] = fill
            if cfg.unseen_category == "fill":
                try:
                    self.known_categories_[column] = frozenset(valid.unique())
                except TypeError:
                    self.known_categories_[column] = None
            else:
                self.known_categories_[column] = None

    def _build_summary(self) -> None:
        rows: list[dict[str, object]] = []
        for source, role in self.roles_.items():
            if role == "datetime":
                rows.append(
                    {
                        "column": source,
                        "kind": "datetime",
                        "missing_in_fit": self.missing_counts_.get(source, 0),
                        "fill_value": "",
                        "lower_bound": np.nan,
                        "upper_bound": np.nan,
                        "outliers_capped": 0,
                        "status": "expanded",
                        "generated_columns": ", ".join(
                            self.datetime_feature_columns_.get(source, [])
                        ),
                    }
                )
                continue

            if role in {"numeric", "boolean", "categorical"}:
                rows.append(
                    {
                        "column": source,
                        "kind": role,
                        "missing_in_fit": self.missing_counts_.get(source, 0),
                        "fill_value": self.fill_values_.get(source, ""),
                        "lower_bound": self.outlier_bounds_.get(
                            source, (np.nan, np.nan)
                        )[0],
                        "upper_bound": self.outlier_bounds_.get(
                            source, (np.nan, np.nan)
                        )[1],
                        "outliers_capped": self.outlier_counts_.get(source, 0),
                        "status": "dropped_constant"
                        if source in self.constant_columns_
                        else "retained",
                        "generated_columns": "",
                    }
                )

        for column in self.calendar_columns_:
            source = next(
                source
                for source, columns in self.datetime_feature_columns_.items()
                if column in columns
            )
            rows.append(
                {
                    "column": column,
                    "kind": "calendar",
                    "missing_in_fit": self.missing_counts_.get(source, 0),
                    "fill_value": self.fill_values_[column],
                    "lower_bound": np.nan,
                    "upper_bound": np.nan,
                    "outliers_capped": 0,
                    "status": "dropped_constant"
                    if column in self.constant_columns_
                    else "retained",
                    "generated_columns": "",
                }
            )

        for source, indicator in self.indicator_columns_.items():
            rows.append(
                {
                    "column": indicator,
                    "kind": "indicator",
                    "missing_in_fit": self.missing_counts_.get(source, 0),
                    "fill_value": "",
                    "lower_bound": np.nan,
                    "upper_bound": np.nan,
                    "outliers_capped": 0,
                    "status": "retained",
                    "generated_columns": "",
                }
            )

        self.cleaning_summary_ = pd.DataFrame(rows)


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
                "missing_pct": round((missing / row_count * 100) if row_count else 0.0, 2),
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
    keep: str = "first",
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
