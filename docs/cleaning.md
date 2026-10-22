# Cleaning data

`DataCleaner` applies a small, opinionated set of cleaning rules and records
every decision it makes. This page covers the available options and how each
column kind is treated.

## Configuration at a glance

| Option | Default | Effect |
| --- | --- | --- |
| `numeric_imputation` | `"median"` | Numeric fill strategy: `median`, `mean`, or `constant` |
| `categorical_imputation` | `"mode"` | Categorical fill strategy: `mode` or `constant` |
| `numeric_fill_value` | `0.0` | Fill value when numeric imputation is `constant` |
| `categorical_fill_value` | `"Unknown"` | Fill value for constant categorical imputation and unseen labels |
| `cap_outliers` | `True` | Clip numeric values to learned IQR bounds |
| `outlier_multiplier` | `1.5` | IQR multiplier used for the bounds |
| `add_missing_indicators` | `False` | Add `<column>__is_missing` for columns missing during fit |
| `drop_constant_columns` | `True` | Drop columns that are constant after cleaning |
| `numeric_columns` | `()` | Force columns to be treated as numeric |
| `categorical_columns` | `()` | Force columns to be treated as categorical |
| `datetime_columns` | `()` | Columns to parse as datetimes |
| `datetime_features` | `("year", "month", "day", "dayofweek", "is_weekend")` | Calendar features to generate |
| `unseen_category` | `"keep"` | Keep unseen categories or replace them with the fill value |
| `contract` | `None` | Optional `DataContract` with column roles and checks |
| `on_drift` | `"warn"` | Drift policy: `raise`, `warn`, or `ignore` |
| `infer_contract` | `True` | Infer a contract from the training schema |
| `fingerprint_on_fit` | `False` | Compute the training fingerprint during `fit` |
| `verbose` | `True` | Print a short fit summary |

```python
from data_cleaner import CleanerConfig

config = CleanerConfig(
    numeric_imputation="median",
    categorical_imputation="mode",
    cap_outliers=True,
    add_missing_indicators=True,
    drop_constant_columns=True,
    unseen_category="keep",
)
```

## Column roles

Roles tell the cleaner how to treat a column. They come from a contract, from
explicit configuration, or from dtype inference.

| Role | Treatment |
| --- | --- |
| `numeric` | Coerce to numeric, impute, optionally cap outliers |
| `category` | Treat as categorical, impute, apply the unseen policy |
| `boolean` | Coerce to boolean and impute |
| `datetime` | Parse and expand into calendar features |
| `id` | Treat as text; never numeric-impute or cap |
| `text` | Treat as categorical text; protected from the unseen policy |
| `ignore` | Drop from the output |

Aliases such as `measure`, `categorical`, `bool`, `date`, and `identifier` are
normalized to these roles. Unsupported roles raise a `ValueError`.

## Numeric columns

Numeric columns are coerced with `pd.to_numeric(errors="coerce")`, then filled
with the strategy learned during `fit`.

```python
config = CleanerConfig(
    numeric_imputation="median",  # or "mean" / "constant"
    numeric_fill_value=0.0,  # only used with "constant"
    cap_outliers=True,
    outlier_multiplier=1.5,
)
```

### Outlier capping

With `cap_outliers=True`, the cleaner learns lower and upper IQR bounds from the
training column:

\[
\text{lower} = Q_1 - k \cdot IQR, \qquad
\text{upper} = Q_3 + k \cdot IQR
\]

where `k` is `outlier_multiplier`. Values outside the bounds are clipped, not
removed. If the IQR is zero, capping is skipped so constant or near-constant
columns are not destroyed.

Inspect the learned bounds:

```python
cleaner.outlier_summary()
```

## Categorical columns

Categorical columns are filled with the training mode, or a constant.

```python
config = CleanerConfig(
    categorical_imputation="mode",  # or "constant"
    categorical_fill_value="Unknown",
    unseen_category="keep",  # or "fill"
)
```

### Unseen categories

At transform time, a category that did not appear during training has two
possible treatments:

| Policy | Behavior |
| --- | --- |
| `"keep"` | Leave the unseen label in the output |
| `"fill"` | Replace it with `categorical_fill_value` |

`"keep"` is the default because one-hot encoders with
`handle_unknown="ignore"` can handle an unseen label safely. Identifier and text
columns are protected from the unseen policy.

## Boolean columns

Boolean-like columns are coerced to pandas nullable booleans, imputed with the
learned fill value, and returned as `bool`. Declare a column with
`ColumnSpec(..., role="boolean")` when its dtype is ambiguous.

## Datetime columns

Datetime columns must be declared explicitly:

```python
config = CleanerConfig(
    datetime_columns=("joined", "updated_at"),
    datetime_features=("year", "month", "day", "dayofweek", "is_weekend"),
)
```

The original datetime column is **replaced** by one column per generated
feature, named `<source>__<feature>`:

```text
joined  ->  joined__year
            joined__month
            joined__day
            joined__dayofweek
            joined__is_weekend
```

Supported features are `year`, `month`, `day`, `dayofweek`, `quarter`,
`dayofyear`, `weekofyear`, `is_weekend`, `hour`, and `minute`.

Parsing uses mixed-format datetime parsing. Unparseable values become missing
values and are then represented by the generated feature nulls. A datetime-like
column that is not declared raises an error instead of being silently treated as
a category.

## Missing indicators

Set `add_missing_indicators=True` to preserve the signal that a value was
missing before imputation:

```python
config = CleanerConfig(add_missing_indicators=True)
```

The cleaner adds an indicator only for columns that actually had missing values
during `fit`, named `<column>__is_missing`. If that name collides with an existing
column, a numeric suffix is used (`__is_missing_2`, and so on).

## Constant columns

With `drop_constant_columns=True` (the default), columns with a single unique
value after cleaning are dropped. This includes columns that became constant
because every value was missing and was filled with the same value.

Set it to `False` if a downstream component expects the column to remain.

## Identifier columns

Identifiers need different treatment from measurements. Use a contract or a
configured role:

```python
from data_cleaner import ColumnSpec, DataContract, CleanerConfig, DataCleaner

contract = DataContract(
    columns=[
        ColumnSpec("customer_id", role="id"),
        ColumnSpec("notes", role="text"),
        ColumnSpec("internal_flag", role="ignore"),
    ]
)

cleaner = DataCleaner(CleanerConfig(contract=contract))
```

Identifier columns are:

- rendered without a trailing `.0` for integer-like values
- never numeric-coerced, median-imputed, or outlier-capped
- not subject to the unseen-category replacement policy

Columns with `role="ignore"` are dropped from the output.

## Inspect the decisions

Every learned or configured rule is recorded:

```python
log = cleaner.decision_log()
log[log["action"] == "cap_outliers"]
```

The columns are `column`, `action`, `reason`, `source`, `before`, and `after`.
Typical actions include `impute`, `cap_outliers`, `expand_datetime`,
`add_missing_indicator`, `drop_column`, and `unseen_category_policy`.

## A realistic configuration

```python
config = CleanerConfig(
    numeric_columns=("salary", "age"),
    datetime_columns=("signup_date",),
    datetime_features=("year", "month", "dayofweek", "is_weekend"),
    numeric_imputation="median",
    categorical_imputation="mode",
    cap_outliers=True,
    outlier_multiplier=1.5,
    add_missing_indicators=True,
    drop_constant_columns=True,
    unseen_category="keep",
    contract=contract,
    on_drift="warn",
)
```

Next: make the assumptions explicit with [contracts and drift detection](contracts.md).
