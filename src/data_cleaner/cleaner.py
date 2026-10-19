"""The leak-safe :class:`DataCleaner` transformer."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from pandas.api import types as ptypes
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.utils.validation import check_is_fitted

from ._roles import _stringify_identifier
from ._version import _ARTIFACT_VERSION, __version__
from .config import CleanerConfig
from .contract import DataContract, DriftReport

LOGGER = logging.getLogger(__name__)


class DataCleaner(TransformerMixin, BaseEstimator):
    """Fit/transform data cleaner that prevents train/test leakage.

    The cleaner learns imputers, outlier bounds, category policies and schema
    information on training data, then applies exactly those learned rules to
    validation, test, or inference batches.
    """

    def __init__(self, config: CleanerConfig | None = None) -> None:
        self.config = config if config is not None else CleanerConfig()

    def fit(self, X: pd.DataFrame, y: object | None = None) -> DataCleaner:
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

        self.fill_values_: dict[str, Any] = {}
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
            numeric_series = prepared[column].astype("float64")
            fill = self.fill_values_[column]
            lower, upper = self.outlier_bounds_[column]
            prepared[column] = (
                numeric_series.fillna(fill)
                .clip(lower=lower, upper=upper)
                .astype("float64")
            )

        for column in self.boolean_columns_:
            boolean_series = prepared[column].astype("boolean")
            prepared[column] = boolean_series.fillna(self.fill_values_[column]).astype(
                bool
            )

        for column in self.categorical_columns_:
            categorical_series = prepared[column].astype(object)
            fill = self.fill_values_[column]
            protected = column in self.id_columns_ or column in self.text_columns_
            if self.config.unseen_category == "fill" and not protected:
                known = self.known_categories_.get(column)
                if known is not None:
                    unseen = categorical_series.notna() & ~categorical_series.isin(
                        known
                    )
                    categorical_series = categorical_series.mask(
                        unseen, self.config.categorical_fill_value
                    )
            prepared[column] = categorical_series.fillna(fill).astype(object)

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

    def fit_transform(self, X: pd.DataFrame, y: object | None = None) -> pd.DataFrame:
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
            raise ValueError("input_features must match the columns seen during fit")
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

    def fitted_contract(self) -> DataContract | None:
        """Return the contract used by this fitted cleaner."""
        self._ensure_fitted()
        return self.contract_

    def _resolve_contract(self, frame: pd.DataFrame) -> DataContract | None:
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
    def load(cls, path: str | Path, verify_version: bool = True) -> DataCleaner:
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
            raise ValueError(f"Configured columns not found in DataFrame: {missing}")

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
    def _as_float(values: pd.Series) -> pd.Series:
        return pd.to_numeric(values, errors="coerce").astype("float64")

    def _extract_datetime_features(
        self, parsed: pd.Series, source: str
    ) -> pd.DataFrame:
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

    def _fit_numeric(self, prepared: pd.DataFrame, roles: dict[str, str]) -> None:
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
                cfg.cap_outliers and roles.get(column) == "numeric" and not valid.empty
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
