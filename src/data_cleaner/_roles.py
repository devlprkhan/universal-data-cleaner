"""Semantic roles, dtype normalization, and identifier helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pandas.api import types as ptypes

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


def _stringify_identifier(value: Any) -> object:
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
