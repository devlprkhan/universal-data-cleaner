"""Composable cross-column, conditional, and grouped validation rules.

Expectations cover single columns and the frame size. These rules add the rest
of the common validation surface without turning the library into a Pandera
replacement: row predicates over several columns, rules that apply only when a
condition holds, per-group checks, combination uniqueness, and arithmetic
consistency.

Every rule implements the same :class:`~data_cleaner.validation.Validatable`
protocol as an expectation, so it can be passed to
:func:`~data_cleaner.validate` and mixed in one report.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from numbers import Real

import numpy as np
import pandas as pd

from .validation import Severity, Validatable, ValidationResult

_OPERATOR_SYMBOLS = {
    "eq": "==",
    "ne": "!=",
    "lt": "<",
    "le": "<=",
    "gt": ">",
    "ge": ">=",
}


def _require_frame(frame: object) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas DataFrame")
    return frame


def _check_severity(severity: str) -> Severity:
    if severity not in {"error", "warning"}:
        raise ValueError("severity must be 'error' or 'warning'")
    return severity  # type: ignore[return-value]


def _check_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    return name


def _check_column(column: str | None) -> str | None:
    if column is not None and (not isinstance(column, str) or not column):
        raise ValueError("column must be a non-empty string or None")
    return column


def _check_column_names(columns: Sequence[str], field: str) -> tuple[str, ...]:
    if isinstance(columns, str):
        raise TypeError(f"{field} must be a sequence of column names, not a string")
    names = tuple(columns)
    if not names:
        raise ValueError(f"{field} must contain at least one column")
    for name in names:
        if not isinstance(name, str) or not name:
            raise ValueError(f"{field} entries must be non-empty strings")
    if len(set(names)) != len(names):
        raise ValueError(f"{field} must not contain duplicates")
    return names


def _check_tolerance(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("tolerance must be a real number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError("tolerance must be a finite non-negative number")
    return number


def _truncate(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _missing(columns: Sequence[str], frame: pd.DataFrame) -> str | None:
    for column in columns:
        if column not in frame.columns:
            return column
    return None


def _outcomes(
    outcome: ValidationResult | list[ValidationResult],
) -> list[ValidationResult]:
    if isinstance(outcome, ValidationResult):
        return [outcome]
    return list(outcome)


def _inner_value_column(rule: object) -> str | None:
    value = getattr(rule, "value_column", None)
    if isinstance(value, str):
        return value
    column = getattr(rule, "column", None)
    if isinstance(column, str) and "," not in column and " + " not in column:
        return column
    return None


class Condition:
    """A boolean row predicate over one or more columns."""

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        """Return a boolean mask aligned with ``frame``."""
        raise NotImplementedError

    def known(self, frame: pd.DataFrame) -> pd.Series:
        """Return rows where the condition can be evaluated.

        Comparisons drop rows where either operand is missing. Those rows are
        not treated as failures, so a rule does not flag missing data unless the
        rule explicitly uses ``col(...).isna()``.
        """
        return pd.Series(True, index=frame.index)

    def describe(self) -> str:
        """Return a short, stable human-readable description."""
        raise NotImplementedError

    def columns(self) -> tuple[str, ...]:
        """Return the columns the condition reads."""
        raise NotImplementedError

    def __and__(self, other: object) -> Condition:
        if not isinstance(other, Condition):
            raise TypeError("Conditions can only be combined with Conditions")
        return _All((self, other))

    def __or__(self, other: object) -> Condition:
        if not isinstance(other, Condition):
            raise TypeError("Conditions can only be combined with Conditions")
        return _Any((self, other))

    def __invert__(self) -> Condition:
        return _Not(self)

    def require(
        self, *, name: str | None = None, severity: Severity = "error"
    ) -> PredicateRule:
        """Turn this condition into a row-level rule."""
        return row_rule(self, name=name, severity=severity)


class ColumnRef:
    """A reference to a column inside a :class:`Condition`."""

    __slots__ = ("name",)
    __hash__ = None  # type: ignore[assignment]

    def __init__(self, name: str) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("column name must be a non-empty string")
        self.name = name

    def __repr__(self) -> str:
        return f"col({self.name!r})"

    def __eq__(self, other: object) -> bool:
        raise TypeError("Use .eq() or .ne() to build a condition, not == or !=")

    def __ne__(self, other: object) -> bool:
        raise TypeError("Use .eq() or .ne() to build a condition, not == or !=")

    def eq(self, other: object) -> Condition:
        """Require equality with a value or another column."""
        return _Comparison(self, "eq", other)

    def ne(self, other: object) -> Condition:
        """Require inequality with a value or another column."""
        return _Comparison(self, "ne", other)

    def lt(self, other: object) -> Condition:
        """Require a value strictly less than ``other``."""
        return _Comparison(self, "lt", other)

    def le(self, other: object) -> Condition:
        """Require a value less than or equal to ``other``."""
        return _Comparison(self, "le", other)

    def gt(self, other: object) -> Condition:
        """Require a value strictly greater than ``other``."""
        return _Comparison(self, "gt", other)

    def ge(self, other: object) -> Condition:
        """Require a value greater than or equal to ``other``."""
        return _Comparison(self, "ge", other)

    def isin(self, values: Sequence[object]) -> Condition:
        """Require membership in ``values``."""
        return _Membership(self, tuple(values), negate=False)

    def not_in(self, values: Sequence[object]) -> Condition:
        """Require non-membership in ``values``."""
        return _Membership(self, tuple(values), negate=True)

    def between(
        self,
        lower: object | None = None,
        upper: object | None = None,
        *,
        inclusive: bool = True,
    ) -> Condition:
        """Require a value within the given bounds."""
        return _Between(self, lower, upper, inclusive)

    def isna(self) -> Condition:
        """Require a missing value."""
        return _IsNull(self, negate=False)

    def notna(self) -> Condition:
        """Require a present value."""
        return _IsNull(self, negate=True)

    def matches(self, pattern: str) -> Condition:
        """Require a full-string regular-expression match."""
        return _Matches(self, pattern)


def col(name: str) -> ColumnRef:
    """Start a condition from a column reference."""
    return ColumnRef(name)


def _operand(frame: pd.DataFrame, value: object) -> pd.Series | object:
    if isinstance(value, ColumnRef):
        return frame[value.name]
    return value


def _operand_text(value: object) -> str:
    if isinstance(value, ColumnRef):
        return value.name
    return _truncate(repr(value), 40)


@dataclass(frozen=True, slots=True, eq=False)
class _Comparison(Condition):
    left: ColumnRef
    operator: str
    right: object

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        left = data[self.left.name]
        right = _operand(data, self.right)
        valid = left.notna()
        if isinstance(right, pd.Series):
            valid = valid & right.notna()
        if self.operator == "eq":
            result = left == right
        elif self.operator == "ne":
            result = left != right
        elif self.operator == "lt":
            result = left < right
        elif self.operator == "le":
            result = left <= right
        elif self.operator == "gt":
            result = left > right
        else:
            result = left >= right
        return (result & valid).fillna(False).astype(bool)

    def known(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        left = data[self.left.name]
        right = _operand(data, self.right)
        known = left.notna()
        if isinstance(right, pd.Series):
            known = known & right.notna()
        return known.fillna(False).astype(bool)

    def describe(self) -> str:
        symbol = _OPERATOR_SYMBOLS.get(self.operator, self.operator)
        return f"{self.left.name} {symbol} {_operand_text(self.right)}"

    def columns(self) -> tuple[str, ...]:
        if isinstance(self.right, ColumnRef):
            return (self.left.name, self.right.name)
        return (self.left.name,)


@dataclass(frozen=True, slots=True, eq=False)
class _Membership(Condition):
    column: ColumnRef
    values: tuple[object, ...]
    negate: bool

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        series = data[self.column.name]
        result = series.isin(list(self.values))
        if self.negate:
            result = ~result
        return (result & series.notna()).fillna(False).astype(bool)

    def known(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        return data[self.column.name].notna()

    def describe(self) -> str:
        shown = ", ".join(_operand_text(value) for value in self.values[:10])
        if len(self.values) > 10:
            shown += ", ..."
        keyword = "not in" if self.negate else "in"
        return f"{self.column.name} {keyword} [{shown}]"

    def columns(self) -> tuple[str, ...]:
        return (self.column.name,)


@dataclass(frozen=True, slots=True, eq=False)
class _Between(Condition):
    column: ColumnRef
    lower: object | None
    upper: object | None
    inclusive: bool

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        series = data[self.column.name]
        mask = series.notna()
        if self.lower is not None:
            mask &= series >= self.lower if self.inclusive else series > self.lower
        if self.upper is not None:
            mask &= series <= self.upper if self.inclusive else series < self.upper
        return mask.fillna(False).astype(bool)

    def known(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        return data[self.column.name].notna()

    def describe(self) -> str:
        left = "[" if self.inclusive else "("
        right = "]" if self.inclusive else ")"
        lower = "-inf" if self.lower is None else _operand_text(self.lower)
        upper = "inf" if self.upper is None else _operand_text(self.upper)
        return f"{self.column.name} in {left}{lower}, {upper}{right}"

    def columns(self) -> tuple[str, ...]:
        return (self.column.name,)


@dataclass(frozen=True, slots=True, eq=False)
class _IsNull(Condition):
    column: ColumnRef
    negate: bool

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        series = data[self.column.name]
        return series.notna() if self.negate else series.isna()

    def describe(self) -> str:
        return f"{self.column.name} is {'present' if self.negate else 'missing'}"

    def columns(self) -> tuple[str, ...]:
        return (self.column.name,)


@dataclass(frozen=True, slots=True, eq=False)
class _Matches(Condition):
    column: ColumnRef
    pattern: str

    def __post_init__(self) -> None:
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(f"Invalid pattern: {exc}") from exc

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        series = data[self.column.name]
        matches = series.astype(str).str.fullmatch(self.pattern).fillna(False)
        return (series.notna() & matches).astype(bool)

    def known(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        return data[self.column.name].notna()

    def describe(self) -> str:
        return f"{self.column.name} matches {self.pattern!r}"

    def columns(self) -> tuple[str, ...]:
        return (self.column.name,)


@dataclass(frozen=True, slots=True, eq=False)
class _All(Condition):
    conditions: tuple[Condition, ...]

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        mask = pd.Series(True, index=data.index)
        for condition in self.conditions:
            mask &= condition.mask(data)
        return mask.fillna(False).astype(bool)

    def known(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        if not self.conditions:
            return pd.Series(True, index=data.index)
        all_known = pd.Series(True, index=data.index)
        any_false = pd.Series(False, index=data.index)
        for condition in self.conditions:
            known = condition.known(data)
            all_known &= known
            any_false |= known & ~condition.mask(data)
        # A conjunction is determined when every operand is known, or when any
        # known operand is already false regardless of the missing ones.
        return (all_known | any_false).fillna(False).astype(bool)

    def describe(self) -> str:
        return "(" + " and ".join(item.describe() for item in self.conditions) + ")"

    def columns(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(name for item in self.conditions for name in item.columns())
        )


@dataclass(frozen=True, slots=True, eq=False)
class _Any(Condition):
    conditions: tuple[Condition, ...]

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        mask = pd.Series(False, index=data.index)
        for condition in self.conditions:
            mask |= condition.mask(data)
        return mask.fillna(False).astype(bool)

    def known(self, frame: pd.DataFrame) -> pd.Series:
        data = _require_frame(frame)
        if not self.conditions:
            return pd.Series(True, index=data.index)
        all_known = pd.Series(True, index=data.index)
        any_true = pd.Series(False, index=data.index)
        for condition in self.conditions:
            known = condition.known(data)
            all_known &= known
            any_true |= known & condition.mask(data)
        # A disjunction is determined when every operand is known, or when any
        # known operand is already true regardless of the missing ones.
        return (all_known | any_true).fillna(False).astype(bool)

    def describe(self) -> str:
        return "(" + " or ".join(item.describe() for item in self.conditions) + ")"

    def columns(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(name for item in self.conditions for name in item.columns())
        )


@dataclass(frozen=True, slots=True, eq=False)
class _Not(Condition):
    condition: Condition

    def mask(self, frame: pd.DataFrame) -> pd.Series:
        return ~self.condition.mask(frame)

    def known(self, frame: pd.DataFrame) -> pd.Series:
        return self.condition.known(frame)

    def describe(self) -> str:
        return f"not ({self.condition.describe()})"

    def columns(self) -> tuple[str, ...]:
        return self.condition.columns()


@dataclass(frozen=True, slots=True, eq=False)
class PredicateRule:
    """A row-level rule: every row must satisfy ``condition``."""

    condition: Condition
    name: str
    severity: Severity = "error"
    column: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.condition, Condition):
            raise TypeError("condition must be a Condition built from col()")
        object.__setattr__(self, "name", _check_name(self.name))
        object.__setattr__(self, "severity", _check_severity(self.severity))
        object.__setattr__(self, "column", _check_column(self.column))

    @property
    def value_column(self) -> str | None:
        """The single column a failing value can be read from, if any."""
        columns = self.condition.columns()
        return columns[0] if len(columns) == 1 else None

    def check(self, frame: pd.DataFrame) -> ValidationResult:
        data = _require_frame(frame)
        missing = _missing(self.condition.columns(), data)
        if missing is not None:
            return ValidationResult(
                self.name,
                missing,
                False,
                self.severity,
                f"column '{missing}' is missing",
                None,
            )
        failing = int((self.condition.known(data) & ~self.condition.mask(data)).sum())
        description = self.condition.describe()
        message = (
            f"condition '{description}' holds for all rows"
            if failing == 0
            else f"condition '{description}' failed for {failing} row(s)"
        )
        return ValidationResult(
            self.name, self.column, failing == 0, self.severity, message, failing
        )

    def failing_mask(self, frame: pd.DataFrame) -> pd.Series | None:
        data = _require_frame(frame)
        if _missing(self.condition.columns(), data) is not None:
            return None
        return (
            (self.condition.known(data) & ~self.condition.mask(data))
            .fillna(False)
            .astype(bool)
        )


@dataclass(frozen=True, slots=True, eq=False)
class ConditionalRule:
    """Apply a rule only to rows where ``condition`` holds."""

    condition: Condition
    rule: Validatable
    name: str
    severity: Severity = "error"
    column: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.condition, Condition):
            raise TypeError("condition must be a Condition built from col()")
        if not callable(getattr(self.rule, "check", None)):
            raise TypeError("rule must provide a check(frame) method")
        object.__setattr__(self, "name", _check_name(self.name))
        object.__setattr__(self, "severity", _check_severity(self.severity))
        object.__setattr__(self, "column", _check_column(self.column))

    @property
    def value_column(self) -> str | None:
        """The single column the inner rule reports a value for, if any."""
        return _inner_value_column(self.rule)

    def check(self, frame: pd.DataFrame) -> ValidationResult:
        data = _require_frame(frame)
        missing = _missing(self.condition.columns(), data)
        if missing is not None:
            return ValidationResult(
                self.name,
                missing,
                False,
                self.severity,
                f"column '{missing}' is missing",
                None,
            )
        scope = self.condition.mask(data)
        matched = int(scope.sum())
        description = self.condition.describe()
        if matched == 0:
            return ValidationResult(
                self.name,
                self.column,
                True,
                self.severity,
                f"no rows matched '{description}'; nothing to check",
                0,
            )
        results = _outcomes(self.rule.check(data.loc[scope]))
        failures = [result for result in results if not result.success]
        success = not failures
        if success:
            message = (
                f"'{self.rule.name}' holds for {matched} row(s) matching "
                f"'{description}'"
            )
        else:
            detail = "; ".join(result.message for result in failures[:3])
            message = (
                f"{len(failures)} check(s) failed in {matched} row(s) matching "
                f"'{description}': {detail}"
            )
        column = self.column or next(
            (result.column for result in failures if result.column), None
        )
        return ValidationResult(
            self.name, column, success, self.severity, message, len(failures)
        )

    def failing_mask(self, frame: pd.DataFrame) -> pd.Series | None:
        data = _require_frame(frame)
        if _missing(self.condition.columns(), data) is not None:
            return None
        masker = getattr(self.rule, "failing_mask", None)
        if not callable(masker):
            return None
        scope = self.condition.mask(data)
        inner = masker(data.loc[scope])
        if inner is None:
            return None
        values = np.asarray(inner, dtype=bool)
        if values.shape != (int(scope.sum()),):
            return None
        result = np.zeros(len(data), dtype=bool)
        result[np.flatnonzero(scope.to_numpy())] = values
        return pd.Series(result, index=data.index)


@dataclass(frozen=True, slots=True, eq=False)
class GroupedRule:
    """Apply a rule independently inside each group of ``by``."""

    by: tuple[str, ...]
    rule: Validatable
    name: str
    severity: Severity = "error"
    column: str | None = None
    max_groups: int = 10
    include_groups: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "by", _check_column_names(self.by, "by"))
        if not callable(getattr(self.rule, "check", None)):
            raise TypeError("rule must provide a check(frame) method")
        object.__setattr__(self, "name", _check_name(self.name))
        object.__setattr__(self, "severity", _check_severity(self.severity))
        object.__setattr__(self, "column", _check_column(self.column))
        if isinstance(self.max_groups, bool) or self.max_groups < 0:
            raise ValueError("max_groups must be a non-negative integer")
        object.__setattr__(self, "max_groups", int(self.max_groups))

    @property
    def value_column(self) -> str | None:
        """Grouped findings cannot be attributed to a single value."""
        return None

    def check(self, frame: pd.DataFrame) -> ValidationResult:
        data = _require_frame(frame)
        missing = _missing(self.by, data)
        if missing is not None:
            return ValidationResult(
                self.name,
                missing,
                False,
                self.severity,
                f"column '{missing}' is missing",
                None,
            )
        failing_groups = 0
        total = 0
        labels: list[str] = []
        for key, group in data.groupby(
            list(self.by), dropna=False, observed=True, sort=True
        ):
            total += 1
            results = _outcomes(self.rule.check(group))
            if any(not result.success for result in results):
                failing_groups += 1
                if self.include_groups and len(labels) < self.max_groups:
                    labels.append(_truncate(str(key), 60))
        success = failing_groups == 0
        message = (
            f"'{self.rule.name}' holds in all {total} group(s)"
            if success
            else f"'{self.rule.name}' failed in {failing_groups} of {total} group(s)"
        )
        if labels:
            message += f"; first failing groups: {labels}"
        return ValidationResult(
            self.name,
            self.column,
            success,
            self.severity,
            message,
            failing_groups,
        )

    def failing_mask(self, frame: pd.DataFrame) -> pd.Series | None:
        # Individual rows cannot be attributed to a group-level aggregate.
        return None


@dataclass(frozen=True, slots=True)
class UniqueCombinationRule:
    """Require the combination of ``columns`` to be unique."""

    columns: tuple[str, ...]
    name: str = "unique_combination"
    severity: Severity = "error"
    column: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "columns", _check_column_names(self.columns, "columns")
        )
        object.__setattr__(self, "name", _check_name(self.name))
        object.__setattr__(self, "severity", _check_severity(self.severity))
        object.__setattr__(self, "column", _check_column(self.column))

    @property
    def value_column(self) -> str | None:
        """Only a single-column rule has a value to show."""
        return self.columns[0] if len(self.columns) == 1 else None

    def check(self, frame: pd.DataFrame) -> ValidationResult:
        data = _require_frame(frame)
        missing = _missing(self.columns, data)
        if missing is not None:
            return ValidationResult(
                self.name,
                missing,
                False,
                self.severity,
                f"column '{missing}' is missing",
                None,
            )
        mask = self.failing_mask(data)
        duplicates = int(mask.sum()) if mask is not None else 0
        success = duplicates == 0
        message = (
            f"columns {list(self.columns)} are unique in combination"
            if success
            else f"columns {list(self.columns)} have {duplicates} duplicate "
            "combination(s)"
        )
        return ValidationResult(
            self.name, self.column, success, self.severity, message, duplicates
        )

    def failing_mask(self, frame: pd.DataFrame) -> pd.Series | None:
        data = _require_frame(frame)
        if _missing(self.columns, data) is not None:
            return None
        keys = data[list(self.columns)]
        duplicated = keys.duplicated(keep="first")
        return (duplicated & keys.notna().all(axis=1)).fillna(False).astype(bool)


@dataclass(frozen=True, slots=True)
class SumEqualsRule:
    """Require the sum of ``columns`` to equal ``target`` within ``tolerance``."""

    columns: tuple[str, ...]
    target: str
    tolerance: float
    name: str = "sum_equals"
    severity: Severity = "error"
    column: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "columns", _check_column_names(self.columns, "columns")
        )
        if not isinstance(self.target, str) or not self.target:
            raise ValueError("target must be a non-empty column name")
        object.__setattr__(self, "tolerance", _check_tolerance(self.tolerance))
        object.__setattr__(self, "name", _check_name(self.name))
        object.__setattr__(self, "severity", _check_severity(self.severity))
        object.__setattr__(self, "column", _check_column(self.column))

    @property
    def value_column(self) -> str | None:
        """The target column is the value to show when a row fails."""
        return self.target

    def check(self, frame: pd.DataFrame) -> ValidationResult:
        data = _require_frame(frame)
        missing = _missing((*self.columns, self.target), data)
        if missing is not None:
            return ValidationResult(
                self.name,
                missing,
                False,
                self.severity,
                f"column '{missing}' is missing",
                None,
            )
        mask = self.failing_mask(data)
        mismatches = int(mask.sum()) if mask is not None else 0
        success = mismatches == 0
        message = (
            f"sum({list(self.columns)}) equals '{self.target}' within "
            f"{self.tolerance:g}"
            if success
            else f"sum({list(self.columns)}) failed for {mismatches} row(s) "
            f"against '{self.target}' within {self.tolerance:g}"
        )
        return ValidationResult(
            self.name, self.column, success, self.severity, message, mismatches
        )

    def failing_mask(self, frame: pd.DataFrame) -> pd.Series | None:
        data = _require_frame(frame)
        if _missing((*self.columns, self.target), data) is not None:
            return None
        raw = data[list(self.columns)]
        numeric = raw.apply(pd.to_numeric, errors="coerce")
        target_raw = data[self.target]
        target = pd.to_numeric(target_raw, errors="coerce")
        non_numeric = (raw.notna() & numeric.isna()).any(axis=1) | (
            target_raw.notna() & target.isna()
        )
        missing = raw.isna().any(axis=1) | target_raw.isna()
        difference = (numeric.sum(axis=1) - target).abs()
        mismatch = ~missing & (difference > self.tolerance)
        return (non_numeric | mismatch).fillna(False).astype(bool)


def row_rule(
    condition: Condition,
    *,
    name: str | None = None,
    severity: Severity = "error",
) -> PredicateRule:
    """Require every row to satisfy ``condition``.

    Comparisons drop rows where either side is missing, so a missing value does
    not fail a predicate unless the predicate explicitly asks for it with
    ``col(...).isna()``.
    """
    if not isinstance(condition, Condition):
        raise TypeError("condition must be a Condition built from col()")
    return PredicateRule(
        condition=condition,
        name=name or f"row_rule[{_truncate(condition.describe(), 50)}]",
        severity=_check_severity(severity),
        column=", ".join(condition.columns()) or None,
    )


def conditional(
    condition: Condition,
    rule: Validatable,
    *,
    name: str | None = None,
    severity: Severity | None = None,
) -> ConditionalRule:
    """Apply ``rule`` only to rows where ``condition`` holds.

    Rows outside the condition are not evaluated. If no row matches, the rule
    passes and reports that nothing was checked.
    """
    if not isinstance(condition, Condition):
        raise TypeError("condition must be a Condition built from col()")
    if not callable(getattr(rule, "check", None)):
        raise TypeError("rule must provide a check(frame) method")
    active = severity if severity is not None else getattr(rule, "severity", "error")
    return ConditionalRule(
        condition=condition,
        rule=rule,
        name=name or f"{rule.name} when {_truncate(condition.describe(), 40)}",
        severity=_check_severity(active),
        column=getattr(rule, "column", None),
    )


def grouped(
    by: str | Sequence[str],
    rule: Validatable,
    *,
    name: str | None = None,
    severity: Severity | None = None,
    max_groups: int = 10,
    include_groups: bool = False,
) -> GroupedRule:
    """Apply ``rule`` independently inside each group.

    The result reports how many groups failed. Group labels are omitted by
    default because they can contain personal data; pass ``include_groups=True``
    to list up to ``max_groups`` failing labels.
    """
    keys = (by,) if isinstance(by, str) else tuple(by)
    keys = _check_column_names(keys, "by")
    if not callable(getattr(rule, "check", None)):
        raise TypeError("rule must provide a check(frame) method")
    if isinstance(max_groups, bool) or max_groups < 0:
        raise ValueError("max_groups must be a non-negative integer")
    active = severity if severity is not None else getattr(rule, "severity", "error")
    return GroupedRule(
        by=keys,
        rule=rule,
        name=name or f"{rule.name} by {', '.join(keys)}",
        severity=_check_severity(active),
        column=getattr(rule, "column", None) or ", ".join(keys),
        max_groups=max_groups,
        include_groups=include_groups,
    )


def unique_combination(
    columns: Sequence[str],
    *,
    name: str | None = None,
    severity: Severity = "error",
) -> UniqueCombinationRule:
    """Require the combination of ``columns`` to be unique.

    Rows where any key is missing are ignored, matching :func:`unique` for a
    single column.
    """
    keys = _check_column_names(columns, "columns")
    return UniqueCombinationRule(
        columns=keys,
        name=name or "unique_combination",
        severity=_check_severity(severity),
        column=" + ".join(keys),
    )


def sum_equals(
    columns: Sequence[str],
    target: str,
    *,
    tolerance: float = 1e-9,
    name: str | None = None,
    severity: Severity = "error",
) -> SumEqualsRule:
    """Require the numeric sum of ``columns`` to equal ``target`` per row."""
    keys = _check_column_names(columns, "columns")
    if not isinstance(target, str) or not target:
        raise ValueError("target must be a non-empty column name")
    amount = _check_tolerance(tolerance)
    return SumEqualsRule(
        columns=keys,
        target=target,
        tolerance=amount,
        name=name or "sum_equals",
        severity=_check_severity(severity),
        column=target,
    )


__all__ = [
    "ColumnRef",
    "Condition",
    "PredicateRule",
    "col",
    "conditional",
    "grouped",
    "row_rule",
    "sum_equals",
    "unique_combination",
]
