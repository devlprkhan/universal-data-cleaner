# ML split audit

Cleaning rules can leak. So can the split itself.

`audit_split()` checks a train/test split for contamination and distribution
surprises **before** you train. It only reports; it never repairs, reorders, or
mutates the data.

```python
from data_cleaner import audit_split

audit = audit_split(
    X_train,
    X_test,
    y_train,
    y_test,
    groups=groups,  # combined train + test labels
    time_col="event_time",
    id_cols=["customer_id"],
)

audit.valid  # False when an error-severity finding exists
audit.findings  # check, column, severity, message, train, test
audit.summary()
audit.to_markdown()
audit.raise_if_invalid()
```

## What it checks

| Check | Severity | What it means |
| --- | --- | --- |
| `missing_column` | error | A training column is absent from test |
| `extra_column` | warning | A test column is absent from train |
| `empty_split` | error | One of the splits has no rows |
| `dtype_change` | warning | A shared column has a different dtype |
| `duplicate_rows` | error | Test rows exactly duplicate training rows |
| `near_duplicate_rows` | warning | Test rows are near-duplicates of training rows |
| `group_leakage` | error | The same group appears in both splits |
| `group_nulls` | warning | Group labels contain nulls |
| `temporal_leakage` | error | Training timestamps reach the test period |
| `time_parse_error` | error | Some timestamps could not be parsed |
| `time_format_error` | error | `time_col` is numeric and therefore ambiguous |
| `time_nulls` | warning | No valid timestamps were available to check order |
| `target_all_null` | warning | The training target has no non-null values |
| `constant_column` | warning | A column is constant |
| `near_constant_column` | warning | One value dominates a column |
| `high_cardinality` | warning | A feature is mostly unique |
| `high_cardinality_identifier` | warning | A declared identifier is mostly unique |
| `missingness_shift` | warning | The missing rate changed between splits |
| `distribution_shift` | warning | A numeric or categorical distribution shifted |
| `target_leakage` | warning | A feature is suspiciously predictive of the target |
| `unseen_target_class` | warning | Test contains a target class absent from train |
| `target_shift` | warning | The target distribution shifted |

Errors make `audit.valid` false. Warnings are reported but do not invalidate the
split, because they can be legitimate properties of a dataset.

## Groups

Group leakage is often the most damaging split bug: the same customer, patient,
store, or device appears in both training and test.

```python
audit = audit_split(
    X_train,
    X_test,
    groups=pd.concat([train_groups, test_groups], ignore_index=True),
)
```

`groups` may cover both splits (`len(X_train) + len(X_test)`). If you only have
training labels, pass `groups_test` too:

```python
audit = audit_split(
    X_train,
    X_test,
    groups=train_groups,
    groups_test=test_groups,
)
```

Null group labels are reported as `group_nulls` and are **not** treated as one
shared group.

## Time

Declare a timestamp column to activate temporal checks:

```python
audit = audit_split(
    X_train,
    X_test,
    time_col="event_time",
)
```

The audit reports `temporal_leakage` when the latest training timestamp is at or
after the earliest test timestamp. Mixed text formats are parsed, and
unparseable values produce `time_parse_error`.

Numeric timestamp columns are rejected as ambiguous, because pandas interprets
integers as nanoseconds. Convert them to datetimes first.

## Target leakage

With `y_train` and `y_test`, the audit looks for features that are too predictive:

- numeric features use absolute correlation for regression and binary
  classification
- categorical features use normalized mutual information (NMI)
- multiclass targets use NMI with a cardinality guard

```python
audit = audit_split(
    X_train,
    X_test,
    y_train,
    y_test,
    task="auto",  # or "classification" / "regression"
)
```

`task="auto"` treats boolean, categorical, string, and low-cardinality integer
targets as classification. Set the task explicitly if inference is wrong.

!!! note "Heuristic, not proof"

    A high correlation or NMI is a prompt to investigate. It is not proof of
    leakage: a genuinely predictive feature can score highly. Conversely, a
    continuous feature that perfectly encodes a multiclass target may not be
    flagged because NMI only evaluates limited-cardinality features.

## Duplicates

Exact duplicates are compared on feature columns after excluding declared
`id_cols` and `time_col`.

- Exact hashing is dtype-independent: `1` and `1.0` compare equal.
- Object numbers and strings stay distinct.
- Near-duplicates round numeric features to `near_duplicate_decimals` (default
  `3`) and hash the resulting row signature.

Near-duplicate counts exclude rows already counted as exact duplicates. Set
`near_duplicate_decimals=None` to disable the near-duplicate check.

This is a deterministic approximation, not a nearest-neighbour search. It is
fast and reproducible without extra dependencies.

## Thresholds

| Parameter | Default | Meaning |
| --- | --- | --- |
| `near_duplicate_decimals` | `3` | Rounding precision; `None` disables |
| `constant_threshold` | `0.99` | Share of the top value for near-constant |
| `high_cardinality_threshold` | `0.9` | Unique share for high-cardinality |
| `high_cardinality_min_unique` | `20` | Minimum unique values to flag |
| `missingness_shift_threshold` | `0.1` | Absolute missing-rate change |
| `distribution_shift_threshold` | `0.5` | Standardized mean difference |
| `categorical_shift_threshold` | `0.2` | Total variation distance |
| `target_correlation_threshold` | `0.95` | Absolute correlation |
| `target_nmi_threshold` | `0.9` | Normalized mutual information |
| `target_shift_threshold` | `0.5` | TVD (classification) or SMD (regression) |
| `classification_max_classes` | `20` | Auto-classification integer cardinality |
| `max_target_leak_categories` | `50` | Max feature cardinality for NMI |

Start with the defaults. Tighten thresholds if your domain has strong natural
signals, or loosen them if the report is noisy.

## Reading the report

```python
audit.findings
```

```text
            check   column severity                                            message
0  duplicate_rows     None   error  3 test row(s) exactly duplicate a training row ...
1  distribution_shift  age  warning  numeric distribution shifted (standardized mean ...
2  target_leakage  revenue  warning  feature correlates 0.99 with the target ...
```

`SplitAudit` also exposes:

| Member | Purpose |
| --- | --- |
| `valid` | `True` when no error-severity finding exists |
| `errors` | Error-severity findings |
| `warnings` | Warning-severity findings |
| `has_errors` / `has_warnings` | Boolean shortcuts |
| `summary()` | Short text summary |
| `to_markdown()` | Shareable Markdown table |
| `to_dict()` | JSON-friendly representation |
| `raise_if_invalid()` | Raise `ValueError` when errors exist |

Counts are also available as attributes: `duplicate_overlap_rows`,
`near_duplicate_overlap_rows`, `group_overlap`, and `time_overlap_rows`.

## Privacy

Findings never include raw cell values. Messages contain column names, counts,
rates, and statistics only, so reports can be logged safely.

## Recommended workflow

1. Split the data.
2. Run `audit_split()` with targets, groups, and time columns.
3. Fix error-severity findings by fixing the split.
4. Inspect warnings; keep the legitimate ones.
5. Fit the cleaner on `X_train` only.
6. Transform both splits and train the model.
