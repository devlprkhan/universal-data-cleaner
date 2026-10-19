"""Configuration object for :class:`~data_cleaner.DataCleaner`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ._roles import _ALLOWED_DATETIME_FEATURES
from .contract import DataContract


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
    contract: DataContract | None = None
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
            raise ValueError("categorical_imputation must be one of: mode, constant")
        if self.outlier_multiplier <= 0:
            raise ValueError("outlier_multiplier must be > 0")
        if self.unseen_category not in {"keep", "fill"}:
            raise ValueError("unseen_category must be one of: keep, fill")
        if self.on_drift not in {"raise", "warn", "ignore"}:
            raise ValueError("on_drift must be one of: raise, warn, ignore")
        if self.contract is not None and not isinstance(self.contract, DataContract):
            raise TypeError("contract must be a DataContract instance or None")
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
