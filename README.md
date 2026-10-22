# Universal Data Cleaner

[![CI](https://github.com/devlprkhan/universal-data-cleaner/actions/workflows/ci.yml/badge.svg)](https://github.com/devlprkhan/universal-data-cleaner/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-4f46e5.svg)](https://devlprkhan.github.io/universal-data-cleaner/)
[![PyPI](https://img.shields.io/pypi/v/universal-data-cleaner.svg)](https://pypi.org/project/universal-data-cleaner/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)
[![Managed with uv](https://img.shields.io/badge/managed%20with-uv-6f42c1.svg)](https://docs.astral.sh/uv/)

A small, production-oriented tabular cleaning transformer for pandas + scikit-learn.

It is designed for the part of an ML pipeline that is easy to get wrong: cleaning
training data and inference data with **exactly the same learned rules**.

## Documentation

The full documentation is the central reference:

**[devlprkhan.github.io/universal-data-cleaner](https://devlprkhan.github.io/universal-data-cleaner/)**

- [Quickstart](https://devlprkhan.github.io/universal-data-cleaner/quickstart/)
- [Leak-safe workflow](https://devlprkhan.github.io/universal-data-cleaner/leak-safe-workflow/)
- [Cleaning guide](https://devlprkhan.github.io/universal-data-cleaner/cleaning/)
- [Contracts & drift](https://devlprkhan.github.io/universal-data-cleaner/contracts/)
- [Validation, joins & dedup](https://devlprkhan.github.io/universal-data-cleaner/validation-joins/)
- [ML split audit](https://devlprkhan.github.io/universal-data-cleaner/ml-split-audit/)
- [API reference](https://devlprkhan.github.io/universal-data-cleaner/api/)
- [Changelog](https://devlprkhan.github.io/universal-data-cleaner/changelog/)

## Why this exists

A common notebook pattern is:

```python
df["Age"] = df["Age"].fillna(df["Age"].median())
```

That leaks information when it is run before the train/test split, and it silently
breaks at inference time because the median is recomputed on the new batch.

`DataCleaner` fits on training data, stores the learned values, and reuses them in
`transform()` and in saved artifacts.

## What it handles

- numeric coercion and median / mean / constant imputation
- optional IQR outlier capping (learned from training data only)
- categorical mode / constant imputation
- optional unseen-category policy: keep or replace
- boolean coercion and imputation
- datetime parsing plus calendar feature extraction
- optional missing-value indicator columns
- optional constant-column dropping
- stable output schema and column order
- declarative column contracts (roles, allowed values, ranges, patterns, uniqueness)
- automatic train-schema contract inference and transform-time drift reports
- `on_drift` policy: `raise`, `warn`, or `ignore`
- identifier columns that are never numeric-coerced, median-imputed, or capped
- train/test split audits for duplicate, group, temporal, and target leakage
- joblib save / load with artifact versioning
- scikit-learn `Pipeline`, `clone`, and `get_feature_names_out` compatibility

The cleaner never mutates the input DataFrame and never drops inference rows.

## Install from PyPI

```bash
pip install universal-data-cleaner
```

The distribution name is `universal-data-cleaner`; the import name is
`data_cleaner`.

```python
from data_cleaner import CleanerConfig, DataCleaner
```

## Development setup with uv

```bash
git clone https://github.com/devlprkhan/universal-data-cleaner.git
cd universal-data-cleaner
uv sync
```

Run the test suite:

```bash
uv run pytest -q
```

Open the reference notebook:

```bash
uv run jupyter lab Universal_Data_Cleaner.ipynb
```

The notebook is also verified headlessly in CI-style environments with
`nbclient`; both tools are in the `dev` dependency group.

### Install directly from GitHub

```bash
uv add "git+https://github.com/devlprkhan/universal-data-cleaner.git"
# or
pip install "git+https://github.com/devlprkhan/universal-data-cleaner.git"
```

## Quick start

```python
import pandas as pd
from data_cleaner import CleanerConfig, DataCleaner

train = pd.DataFrame(
    {
        "age": [34, 41, None, 29],
        "salary": [70_000, 82_000, 91_000, 55_000],
        "dept": ["IT", "HR", "IT", None],
        "joined": ["2022-01-03", "2021-11-20", "2023-04-01", "bad-date"],
    }
)

config = CleanerConfig(
    datetime_columns=("joined",),
    add_missing_indicators=True,
    drop_constant_columns=True,
)

cleaner = DataCleaner(config).fit(train)
train_clean = cleaner.transform(train)
print(cleaner.cleaning_summary())
print(cleaner.outlier_summary())
```

For a column that should be numeric even though it arrived as dirty strings:

```python
config = CleanerConfig(
    numeric_columns=("salary",),  # force numeric parsing
    datetime_columns=("joined",),  # parse dates instead of treating them as categories
    unseen_category="keep",  # or "fill" to replace unseen labels
)
```

## Leak-safe workflow

```python
from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

cleaner = DataCleaner(config).fit(X_train)

X_train_clean = cleaner.transform(X_train)
X_test_clean = cleaner.transform(X_test)  # uses train statistics only
```

Save the fitted cleaner with the model artifact:

```python
cleaner.save("artifacts/data_cleaner.joblib")
restored = DataCleaner.load("artifacts/data_cleaner.joblib")
```

## Column contracts and drift detection

A contract makes the assumptions about your data explicit and checks them again
on every batch.

```python
from data_cleaner import ColumnSpec, DataContract, CleanerConfig, DataCleaner

contract = DataContract(
    columns=[
        ColumnSpec("customer_id", role="id"),
        ColumnSpec("age", role="numeric", min_value=0, max_value=120),
        ColumnSpec("plan", role="category", allowed_values=("free", "pro", "team")),
    ],
)

cleaner = DataCleaner(CleanerConfig(contract=contract, on_drift="warn")).fit(X_train)

X_test_clean = cleaner.transform(X_test)  # drift is detected, never mutates
print(cleaner.drift_report())
```

If you do not pass a contract, a conservative one is inferred from the training
schema automatically. Drift is then reported without any configuration:

```python
cleaner = DataCleaner().fit(X_train)
cleaner.transform(X_test)
report = cleaner.drift_report()

if not report.empty:
    print(report[["column", "check", "severity", "message"]])
```

Supported drift checks: `missing_column`, `unexpected_column`, `dtype_change`,
`unexpected_missing`, `unexpected_category`, `value_out_of_range`,
`pattern_mismatch`, and `duplicate_values`.

Control what happens when drift is found with `CleanerConfig.on_drift`:

| `on_drift` | Behavior |
| --- | --- |
| `"warn"` (default) | Log the drift report and continue |
| `"raise"` | Raise `ValueError` when any error-severity finding exists |
| `"ignore"` | Record findings in `drift_report()` without logging |

`role="id"` is worth calling out: identifier columns are treated as text, never
numeric-imputed, never outlier-capped, and rendered without a trailing `.0`.
Use `role="ignore"` to drop operational columns from the output.

Contracts can be version-controlled and shared between training and serving:

```python
contract.to_json()  # store it with the model artifact
restored = DataContract.from_json(payload)

# Optional YAML support requires `pip install pyyaml`
# restored = DataContract.from_yaml(contract.to_yaml())
```

## Expectations, joins, and referential integrity

### Expectations and validation reports

Run lightweight expectations against any batch and get a shareable report:

```python
from data_cleaner import (
    between,
    has_dtype,
    in_set,
    matches_pattern,
    not_null,
    row_count_between,
    unique,
    validate,
)

report = validate(
    orders_new,
    [
        not_null("order_id"),
        unique("order_id"),
        in_set("status", ["new", "paid", "shipped"]),
        between("amount", 0, 100_000),
        matches_pattern("email", r"[^@]+@[^@]+\.[^@]+"),
        has_dtype("created_at", "datetime"),
        row_count_between(min_rows=1),
    ],
)
print(report.to_markdown())
report.raise_if_failed()
```

`report.success` is true when no error-severity expectation failed.
`report.failures` includes warnings too, so use `severity="warning"` for soft
checks. `has_dtype` accepts broad kinds (`numeric`, `categorical`, `boolean`,
`datetime`) or an exact pandas dtype such as `float64`.

Contracts can validate a batch directly and return the same report type:

```python
from data_cleaner import DataContract

contract = DataContract.from_frame(orders_train)
result = contract.validate(orders_new)
result.failures.to_markdown()
```

`Contract` is a shorthand alias for `DataContract`.

### Join diagnostics

```python
from data_cleaner import diagnose_join

report = diagnose_join(orders, customers, on="customer_id", how="left")

report.safe  # False on cardinality mismatch, left/right row multiplication, or null keys
report.cardinality  # e.g. "1:m"
report.row_multiplier  # output rows / left rows
report.unmatched_left
report.unmatched_right
report.warnings
report.raise_if_unsafe()
```

`diagnose_join` defaults to `how="left"` and `validate="1:1"`. It reports
duplicate keys, null keys, unmatched rows, and the actual output row count
without materializing the full joined frame.

### Referential integrity

```python
from data_cleaner import check_referential_integrity

report = check_referential_integrity(
    orders, customers, child_key="customer_id", parent_key="id"
)
report.orphan_rows
report.orphan_keys
report.raise_if_invalid()
```

Null child keys are reported but allowed by default (`allow_null_keys=True`).
Duplicate parent keys make the relationship invalid because the parent key is
not a unique reference target.

### Business-key deduplication

```python
from data_cleaner import deduplicate_by_business_key

deduped, report = deduplicate_by_business_key(
    orders, key="order_id", keep="last", tie_breaker="updated_at"
)
report.removed_rows
report.removed  # the actual rows that were dropped
```

The returned frame preserves the input row order and index. `tie_breaker`
prefers non-null values, and null business keys are reported explicitly.
The input frame is never mutated.

## ML split audits

Audit a train/test split for contamination and distribution surprises before
training:

```python
from data_cleaner import audit_split

audit = audit_split(
    X_train,
    X_test,
    y_train,
    y_test,
    groups=groups,  # combined train+test labels, or pass groups_test=
    time_col="event_time",
    id_cols=["customer_id"],
)

audit.valid  # False when an error-severity finding exists
audit.findings  # check, column, severity, message, train, test
audit.summary()
audit.to_markdown()
audit.raise_if_invalid()
```

Schema problems such as missing columns, empty splits, exact duplicate overlap,
group leakage, temporal leakage, and unparseable or numeric timestamps are
errors. Near-duplicates, constant / near-constant columns, high-cardinality
identifiers, missingness and distribution shift, target-leakage heuristics, and
target shift are warnings because they can be legitimate properties of a
dataset. The audit only reports; it never repairs or reorders a split.

`groups` may hold labels for both splits (`len(X_train) + len(X_test)`); pass
`groups_test` when it only covers the training rows. Duplicate checks exclude
`id_cols` and `time_col`; declared identifiers are still reported under
`high_cardinality_identifier` when their cardinality is high. Near-duplicates
are approximated deterministically by hashing rows with numeric features
rounded to `near_duplicate_decimals` (default `3`).

Findings never include raw cell values. Messages carry column names, counts,
rates, and statistics only, so reports can be logged safely.

## Audit trail, manifests, and fingerprints

Every learned or configured decision is recorded during `fit()` and exposed as
a tidy DataFrame:

```python
log = cleaner.decision_log()
# columns: column, action, reason, source, before, after
log[log["action"] == "cap_outliers"]
```

`source` says whether a rule was `learned` from the training data, supplied via
`config`, declared in a `contract`, or `inferred` by the library. Imputation
values, outlier bounds, datetime expansion, missing indicators, dropped
constants, and identifier handling are all explained instead of hidden.

Build a JSON-serializable manifest for logs or a model registry:

```python
import json

manifest = cleaner.to_manifest(X_train, include_fingerprint=True)
# library_version, artifact_version, environment, config, contract,
# input_schema, output_columns, fitted, decisions, fingerprint

json.dumps(manifest)  # safe to ship to a registry or a log line
```

`save()` embeds the manifest and the training fingerprint in the artifact, and
`load()` restores them:

```python
cleaner.save("cleaner.joblib")
restored = DataCleaner.load("cleaner.joblib")
restored.artifact_manifest()
```

Fingerprints are stable SHA-256 hashes of the schema plus summary statistics.
They never hash raw values, so they are safe to log:

```python
from data_cleaner import (
    assert_schema_stable,
    compare_fingerprints,
    fingerprint_dataframe,
)

expected = fingerprint_dataframe(X_train)
same = compare_fingerprints(expected, fingerprint_dataframe(X_new))
assert_schema_stable(X_new, expected)  # raises ValueError on schema/stat drift
```

Set `CleanerConfig(fingerprint_on_fit=True)` to compute the training fingerprint
once during `fit()`, so `to_manifest(include_fingerprint=True)` needs no data.

## scikit-learn Pipeline

```python
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

numeric = ["age", "salary", "joined__year"]
categorical = ["dept"]
boolean = []

preprocess = ColumnTransformer(
    [
        ("num", StandardScaler(), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), categorical),
        ("bool", "passthrough", boolean),
    ],
    remainder="drop",
)

pipeline = Pipeline(
    [
        ("cleaner", DataCleaner(config)),
        ("features", preprocess),
        ("model", Ridge(alpha=1.0)),
    ]
)
pipeline.fit(X_train, y_train)
predictions = pipeline.predict(X_test)
```

## Public API

| Name | Purpose |
| --- | --- |
| `CleanerConfig` | Validated cleaning configuration |
| `DataCleaner` | Fit/transform cleaner with save/load and drift reporting |
| `CleaningDecision` | One auditable learned or configured decision |
| `ColumnSpec` | Declarative expectations and semantics for one column |
| `DataContract` | A set of column specs, with inference and (de)serialization |
| `Contract` | Shorthand alias for `DataContract` |
| `DataContract.validate()` | Check a batch and return a `ValidationReport` |
| `DriftReport` | Findings from a contract check, with a Markdown summary |
| `Expectation` | One reusable expectation produced by a factory |
| `validate` | Evaluate expectations against a frame |
| `not_null`, `unique`, `in_set`, `between` | Expectation factories |
| `matches_pattern`, `has_dtype` | Expectation factories |
| `row_count_between` | Frame-level row-count expectation |
| `ValidationReport` | Pass/fail results, failures table, Markdown, and raise helper |
| `diagnose_join` | Diagnose key duplication, cardinality, and row multiplication |
| `JoinDiagnosis` | Join report with multiplier, unmatched counts, and warnings |
| `check_referential_integrity` | Find orphan child keys and non-unique parent keys |
| `ReferentialIntegrityReport` | Orphan counts/keys, null keys, and validity |
| `deduplicate_by_business_key` | Deduplicate by key and report removed rows |
| `DeduplicationReport` | Removed rows, duplicate-key counts, and tie-breaker details |
| `audit_split` | Audit a train/test split for leakage and distribution shift |
| `SplitAudit` | Findings table with validity, Markdown, and raise helper |
| `DataCleaner.drift_report()` | Drift findings from the last `transform` |
| `DataCleaner.fitted_contract()` | The contract used by the fitted cleaner |
| `DataCleaner.decision_log()` | Tidy DataFrame of cleaning decisions |
| `DataCleaner.to_manifest()` | JSON-serializable artifact manifest |
| `DataCleaner.artifact_manifest()` | Manifest stored in a loaded artifact |
| `DataCleaner.fingerprint()` | Stable schema + statistics fingerprint |
| `fingerprint_dataframe` | Fingerprint any DataFrame for lineage |
| `compare_fingerprints` | Compare two fingerprints |
| `assert_schema_stable` | Raise when a frame's fingerprint changed |
| `profile_dataframe` | Column-level missing/type/cardinality profile |
| `dataset_summary` | Row/column/missing/duplicate summary |
| `drop_duplicate_rows` | Explicit duplicate removal helper |
| `assert_frame_clean` | Guard against missing/infinite output values |

## Important production notes

- Fit the cleaner **after** splitting and **only** on training data.
- Do not pass IDs, free-text notes, or the target column to the cleaner.
- Mark identifier columns with `ColumnSpec(..., role="id")` so they are never
  treated as numeric measurements.
- Set `on_drift="raise"` in production when an unexpected schema change should
  stop the job instead of silently cleaning it.
- Keep `DataSource`-style constant columns out of the model, or let
  `drop_constant_columns=True` remove them.
- `unseen_category="keep"` is the default because one-hot encoders with
  `handle_unknown="ignore"` can handle an unseen label safely.
- Datetime columns are replaced by calendar features. Their missing values are
  represented by the generated feature NaNs plus an optional missing indicator.
- IQR capping is skipped automatically when the IQR is zero, so constant or
  near-constant numeric columns are not accidentally destroyed.
- Persist `cleaner.to_manifest(X_train, include_fingerprint=True)` alongside the
  model so you can audit exactly which cleaning rules produced an artifact.
- `decision_log()` explains every learned or configured rule; ship it to your
  experiment tracker when a model's preprocessing changes.

## Project layout

```text
.
├── src/data_cleaner/                  # typed, pip-installable package
│   ├── __init__.py                    # public API re-exports
│   ├── _version.py                    # version metadata
│   ├── _roles.py                      # semantic roles and dtype helpers
│   ├── artifacts.py                   # fingerprints and runtime metadata
│   ├── contract.py                    # ColumnSpec / DataContract / DriftReport
│   ├── config.py                      # CleanerConfig
│   ├── cleaner.py                     # DataCleaner
│   ├── decisions.py                   # CleaningDecision and decision log
│   ├── integration.py                 # joins, referential integrity, dedup
│   ├── ml_audit.py                    # train/test leakage and shift audit
│   ├── profiling.py                   # profiling and validation helpers
│   ├── validation.py                  # expectations and ValidationReport
│   └── py.typed                       # PEP 561 marker
├── Universal_Data_Cleaner.ipynb       # end-to-end reference workflow
├── tests/test_data_cleaner.py         # core unit and integration tests
├── tests/test_validation.py           # expectations and integration tests
├── tests/test_ml_audit.py             # split/leakage audit tests
├── docs/                              # MkDocs guides, API page, and assets
├── mkdocs.yml                         # documentation site configuration
├── pyproject.toml                     # package metadata and dev tooling
├── uv.lock                            # reproducible dependency lock
├── .pre-commit-config.yaml            # local lint/format/type hooks
├── README.md
├── ROADMAP.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

The package ships a `py.typed` marker, so `mypy`, `pyright`, and IDE tooling
pick up the type annotations automatically. Linting (`ruff`), formatting, and
type checking (`mypy`) run in CI and via `pre-commit`.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the local
setup, test command, and pull-request expectations.

## License

Released under the [MIT License](LICENSE).
