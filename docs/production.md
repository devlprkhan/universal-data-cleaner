# Production guide

A cleaner that works in a notebook can still fail in production. This page is the
deployment checklist: what to fit, what to store, and what to check on every
batch.
{: .lead }

## The short checklist

1. Split the data before fitting anything.
2. Audit the split for leakage.
3. Fit the cleaner on `X_train` only.
4. Save the cleaner, contract, and manifest together.
5. Load the same artifact for test and production batches.
6. Transform, validate, and monitor drift.

```python
from data_cleaner import audit_split

audit = audit_split(
    X_train,
    X_test,
    y_train,
    y_test,
    groups=groups,
    time_col="event_time",
    id_cols=["customer_id"],
)

audit.raise_if_invalid()

cleaner = DataCleaner(config).fit(X_train)
cleaner.save("artifacts/data_cleaner.joblib")
```

## Configuration that fails loudly

The defaults are designed to keep pipelines running. In production, choose the
stricter options where a silent change is worse than a failed job.

```python
from data_cleaner import CleanerConfig, ColumnSpec, DataContract

contract = DataContract(
    columns=[
        ColumnSpec("customer_id", role="id"),
        ColumnSpec("age", role="numeric", min_value=0, max_value=120),
        ColumnSpec("plan", role="category", allowed_values=("free", "pro", "team")),
        ColumnSpec("notes", role="text"),
        ColumnSpec("internal_flag", role="ignore"),
    ],
    strict=True,
)

config = CleanerConfig(
    contract=contract,
    on_drift="raise",
    unseen_category="keep",
    add_missing_indicators=True,
    drop_constant_columns=True,
)
```

| Setting | Production recommendation |
| --- | --- |
| `on_drift` | `"raise"` when schema changes should stop the job |
| `contract` | Declare roles, ranges, categories, and uniqueness explicitly |
| `unseen_category` | `"keep"` for `handle_unknown="ignore"` encoders; `"fill"` if downstream must see a known label |
| `add_missing_indicators` | `True` when missingness itself is predictive |
| `drop_constant_columns` | Keep `True` unless a downstream component requires the column |
| `cap_outliers` | Keep `True` for learned IQR clipping; set `False` when extremes are meaningful |

## Never fit on the wrong data

The most important production rule is also the simplest:

```python
# Once, on training data.
cleaner = DataCleaner(config).fit(X_train)

# Everywhere else, reuse the fitted object or load the saved artifact.
X_test_clean = cleaner.transform(X_test)
X_prod_clean = cleaner.transform(X_prod)
```

Do not:

- fit before the train/test split
- fit a second cleaner on test or production data
- recompute medians, modes, or outlier bounds in a serving function
- pass the target column to the cleaner

## Protect identifiers and text

Identifiers are not measurements. Declare them so they are never
numeric-imputed, outlier-capped, or stripped of leading zeros:

```python
ColumnSpec("customer_id", role="id", preserve_leading_zeros=True)
```

Use `role="text"` for free-text fields and `role="ignore"` for operational
columns that should not reach the model. See
[Contracts & drift](contracts.md) for the full role reference.

## Watch the schema on every batch

```python
X_batch_clean = cleaner.transform(X_batch)

report = cleaner.drift_report()
if not report.empty:
    print(report[["column", "check", "severity", "message"]])
```

With `on_drift="raise"`, error-severity findings stop the batch before the model
sees malformed data. With `on_drift="warn"`, the report is logged and cleaning
continues.

## Keep the artifact bundle together

```text
artifacts/
├── data_cleaner.joblib
├── contract.json
└── manifest.json
```

```python
from pathlib import Path

cleaner.save("artifacts/data_cleaner.joblib")
Path("artifacts/contract.json").write_text(contract.to_json())
manifest = cleaner.to_manifest(X_train, include_fingerprint=True)
```

See [Artifacts & reproducibility](artifacts.md) for the manifest and fingerprint
details.

## Validate cleaned output

A final guard catches values that survived cleaning:

```python
from data_cleaner import assert_frame_clean

X_batch_clean = cleaner.transform(X_batch)
assert_frame_clean(X_batch_clean)
```

`assert_frame_clean()` raises when the output still contains missing or infinite
values. Run it in tests and in a pre-model validation step.

## Monitor these failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Required column missing | Upstream schema changed | Contract + `on_drift="raise"` |
| IDs gained `.0` or lost zeros | ID was treated as numeric | `ColumnSpec(..., role="id")` |
| Category exploded into rare labels | Unseen values kept | `unseen_category="fill"` or encoder `handle_unknown` |
| Scores dropped after deploy | Different imputation or bounds | Reuse the saved fitted cleaner |
| Dates disappeared | Datetime column not declared | Add it to `datetime_columns` |
| Constant feature reached the model | Constant dropping disabled | `drop_constant_columns=True` |
| Batch rows vanished | Leakage bug or bad join | Audit the join and the split |

## Related guides

- [Leak-safe workflow](leak-safe-workflow.md)
- [Cleaning data](cleaning.md)
- [Contracts & drift](contracts.md)
- [Validation, joins & dedup](validation-joins.md)
- [ML split audit](ml-split-audit.md)
- [Artifacts & reproducibility](artifacts.md)
