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
6. Audit, transform, validate, and monitor drift on every batch.

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
| `cap_outliers` | `False` by default; enable it or list `outlier_columns` only when clipping extremes is intended |

## Ingest with an audit trail

Read CSV or Excel input through the contract instead of letting pandas infer
types independently on every run:

```python
from data_cleaner import read_csv_safe, read_excel_safe

X_batch, ingestion = read_csv_safe(
    "incoming.csv",
    contract=contract,
    on_error="raise",
)

# Or, with the optional `excel` extra:
X_batch, ingestion = read_excel_safe(
    "incoming.xlsx",
    contract=contract,
    sheet_name="Orders",
    on_error="raise",
)

if not ingestion.success:
    raise RuntimeError(ingestion.summary())
```

`on_error="raise"` fails before the model sees an unparseable ID, date, or
boolean. Contract `unique=True` columns are checked within the frame, and
`iter_csv_safe()` checks them across chunks. The report records normalization
counts without logging raw cell values. See [Safe ingestion](ingestion.md) for
the policy and guardrails.

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
continues. A missing fitted input column is always fatal, regardless of the
policy: the cleaner cannot safely reconstruct the learned parameters for a
column that is absent.

## Audit the whole batch

Drift is only one signal. `CleanerReport` combines the profile, contract, validation,
ingestion, and the fitted cleaner's decisions into one review object:

```python
from data_cleaner import CleanerReport

report = CleanerReport.from_cleaner(
    cleaner,
    X_batch,
    source="production",
    ingestion=ingestion,
)
report.raise_if_failed("Batch rejected")

if report.has_warnings:
    logger.warning(report.summary())
```

In a deploy or scheduled job, run the CLI and let the exit code gate the batch:

```bash
python -m data_cleaner audit incoming.csv \
  --cleaner artifacts/data_cleaner.joblib \
  --format json \
  --output artifacts/audit.json \
  --fail-on-warning
```

`0` means the batch passed, `1` means error findings (or warnings with
`--fail-on-warning`), and `2` means the input or artifact could not be read. See
[Batch reporting](reporting.md) for all options.

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
| Required column missing | Upstream schema changed | Restore the column; a missing fitted column is always fatal. Use a contract + `on_drift="raise"` for other drift |
| IDs gained `.0` or lost zeros | ID was treated as numeric | `ColumnSpec(..., role="id")` and `read_csv_safe()` |
| Excel IDs lost leading zeros | Cell was stored as a number | Store IDs as text; `read_excel_safe()` reports `numeric_identifier` |
| Currency or percent strings stayed text | Spreadsheet formatting leaked into the file | `read_csv_safe()` / `read_excel_safe()` and a numeric `ColumnSpec` |
| Category exploded into rare labels | Unseen values kept | `unseen_category="fill"` or encoder `handle_unknown` |
| Scores dropped after deploy | Different imputation or bounds | Reuse the saved fitted cleaner |
| Dates disappeared | Datetime column not declared | Add it to `datetime_columns` |
| Constant feature reached the model | Constant dropping disabled | `drop_constant_columns=True` |
| Batch rows vanished | Leakage bug or bad join | Audit the join and the split |

## Verify a release

Release builds attach PEP 740 provenance to each PyPI artifact, signed through
the `publish.yml` workflow with GitHub OIDC. Verify a downloaded package against
the source repository:

```bash
uvx "pypi-attestations==0.0.31" verify pypi \
  --repository https://github.com/devlprkhan/universal-data-cleaner \
  pypi:universal_data_cleaner-2.9.0-py3-none-any.whl
```

GitHub also stores a build-provenance attestation for the same artifacts under
the repository's **Attestations** tab. Check it with the GitHub CLI:

```bash
gh attestation verify universal_data_cleaner-2.9.0-py3-none-any.whl \
  --repo devlprkhan/universal-data-cleaner
```

Publishing uses PyPI Trusted Publishing, so no long-lived PyPI token is stored in
the repository. The workflow refuses to publish if the `.publish.attestation`
files are missing.

## Related guides

- [Leak-safe workflow](leak-safe-workflow.md)
- [Cleaning data](cleaning.md)
- [Contracts & drift](contracts.md)
- [Safe ingestion](ingestion.md)
- [Batch reporting](reporting.md)
- [Validation, joins & dedup](validation-joins.md)
- [ML split audit](ml-split-audit.md)
- [Artifacts & reproducibility](artifacts.md)
